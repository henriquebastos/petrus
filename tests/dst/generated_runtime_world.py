"""Cross-layer public-Engine World for CV19.DS3 stateful generation."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import ClassVar, cast

from pydantic import JsonValue

from petrus.engine import Engine
from petrus.impetus.history import (
    ActivityCompleted,
    ActivityRequested,
    ActivityTerminalQuarantined,
    CandidateSelected,
    ExternalEventDelivered,
    FiringBegun,
    FiringCompleted,
    FiringFailed,
    Record,
    ScopeOpened,
    ScopeReset,
    TimerMatured,
    replay_marking,
    replay_scopes,
    replay_watermark,
)
from petrus.impetus.history_store import JsonlHistoryStore
from petrus.impetus.observation import marking as marking_view
from petrus.impetus.petrinet import Arc, Delay, Marking, Net, NetPath, Place, Token, Transition
from petrus.impetus.instance import PriorAcknowledgement
from petrus.motus.activity import ActivityFailure, ActivityInvocation, ExecutionPolicy
from petrus.motus.dispatch import ActivityAttempt, LocalDispatch, LocalWorkerDispatch
from petrus.testing.dst import (
    ActionDisposition,
    ApplyResult,
    BudgetV4,
    CheckResult,
    CheckerIdentity,
    Command,
    Disposition,
    Fault,
    FaultDisposition,
    GenerationStart,
    Observation,
    ObservationRequest,
    ProfileIdentity,
    ResourceUsage,
    ScenarioArtifact,
    ScenarioContext,
    ScheduledCommand,
    World,
    digest_json,
)

SOURCE = NetPath("source")
INPUT = NetPath("input")
RESULT = NetPath("result")
WAITING = NetPath("waiting")
RELEASED = NetPath("released")
WORK = NetPath("work")
RELEASE = NetPath("release")
SCOPE_NAME = "batch"
INSTANCE_ID = "dst-generated-runtime"
MATURATION_INSTANT = 5
SCENARIO_ID = "generated-runtime-cross-layer-world-v4"

PROFILE_DEFINITION = {
    "commands": {
        "engine.drive": [],
        "scope.open": ["name"],
        "scope.reset": ["name"],
        "source.deliver": ["identity", "value"],
        "worker.claim": [],
        "worker.complete": ["result"],
        "worker.fail": ["attempt", "error"],
    },
    "faults": {
        "dispatch.refuse": "activity_requested",
        "history.refuse": "projection_committed",
    },
    "instance": INSTANCE_ID,
    "observations": ["engine.generated-runtime-authority", "generated-runtime-state"],
    "resources": [
        "pending.dispatch_tasks",
        "pending.in_flight",
        "pending.worker_claim",
        "retained.dispatch_facts",
        "retained.external_facts",
        "retained.history_bytes",
        "retained.history_records",
        "retained.marking_bytes",
        "retained.marking_tokens",
    ],
    "timer": MATURATION_INSTANT,
}
PROFILE_IDENTITY = ProfileIdentity(
    name="petrus.engine.generated-runtime",
    version=1,
    digest=digest_json(PROFILE_DEFINITION),
)
CHECKER_IDENTITY = CheckerIdentity(
    name="petrus.engine.generated-runtime-authority",
    version=1,
    digest=digest_json(
        {
            "properties": [
                "live marking and watermark agree with canonical replay",
                "live in-flight and lifecycle state agrees with a small History fold",
                "occurrences remain dense and selected, begun, and terminal records stay writer-valid",
                "one stable invocation spans refusal, redispatch, retry, and reload",
                "provider execution never repeats after a frozen terminal",
                "identified deliveries have one canonical authority and exact redelivery acknowledgement",
                "scope reset fences late terminal projection",
                "refused projection exposes no firing completion",
                "world and retry work remain bounded",
            ]
        }
    ),
)
WORLD_BUDGET = BudgetV4(
    actions=96,
    queued_commands=8,
    timer_advances=1,
    logical_instant=MATURATION_INSTANT,
    reloads=4,
    predicate_polls=24,
    artifact_bytes=524_288,
    profile_resources={
        "pending.dispatch_tasks": 2,
        "pending.in_flight": 2,
        "pending.worker_claim": 1,
        "retained.dispatch_facts": 32,
        "retained.external_facts": 64,
        "retained.history_bytes": 65_536,
        "retained.history_records": 128,
        "retained.marking_bytes": 8_192,
        "retained.marking_tokens": 8,
    },
)


def application_net() -> Net:
    return Net(
        places=[Place(INPUT), Place(RESULT), Place(WAITING), Place(RELEASED)],
        transitions=[
            Transition(SOURCE),
            Transition(WORK, handler="bridge"),
            Transition(RELEASE, timers=(Delay(MATURATION_INSTANT),)),
        ],
        arcs=[
            Arc(SOURCE, INPUT),
            Arc(INPUT, WORK),
            Arc(WORK, RESULT),
            Arc(WAITING, RELEASE),
            Arc(RELEASE, RELEASED),
        ],
        name="dst-generated-runtime",
    )


class WorldClock:
    def __init__(self, context: ScenarioContext):
        self.context = context

    def now(self) -> int:
        return self.context.now()

    def observe(self, instant: int) -> int | None:
        return self.context.now() if self.context.now() >= instant else None


class WorldProviderClock:
    def __init__(self, context: ScenarioContext):
        self.context = context

    def now_ms(self) -> int:
        return self.context.now() * 1_000


class RuntimeBridge:
    def __init__(self, prepared, projected) -> None:
        self._prepared = prepared
        self._projected = projected

    def prepare(self, binding) -> ActivityInvocation:
        self._prepared()
        return ActivityInvocation(
            "calculate",
            input=binding.tokens[0].data,
            policy=ExecutionPolicy(attempts=2, initial_interval=0),
        )

    def project(self, binding, result):
        del binding
        self._projected()
        return {RESULT: (Token("Result", result),)}


def _invocation_view(occurrence: int, invocation: ActivityInvocation) -> dict[str, JsonValue]:
    return cast(
        dict[str, JsonValue],
        {
            "activity": invocation.activity,
            "correlation": invocation.correlation,
            "idempotency": invocation.idempotency,
            "input": invocation.input,
            "occurrence": occurrence,
            "policy": asdict(invocation.policy),
        },
    )


class RefusingLocalDispatch(LocalDispatch):
    """One-shot pre-custody refusal on the public LocalDispatch door."""

    def __init__(self, *args, attempts: list[dict[str, JsonValue]], **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._attempts = attempts
        self._refusal: str | None = None

    def refuse_next_dispatch(self, message: str) -> None:
        self._refusal = message

    def dispatch(self, occurrence: int, invocation: ActivityInvocation) -> None:
        attempt = _invocation_view(occurrence, invocation)
        if self._refusal is not None:
            message = self._refusal
            self._refusal = None
            self._attempts.append({"accepted": False, **attempt})
            raise OSError(message)
        super().dispatch(occurrence, invocation)
        self._attempts.append({"accepted": True, **attempt})


class RefusingProjectionHistory:
    """One-shot refusal before a work projection batch reaches JSONL."""

    def __init__(self, path: Path, attempts: list[dict[str, JsonValue]]) -> None:
        self._delegate = JsonlHistoryStore(path)
        self._attempts = attempts
        self._refusal: str | None = None

    @property
    def records(self) -> tuple[Record, ...]:
        return self._delegate.records

    def __iter__(self):
        return iter(self._delegate)

    def __len__(self) -> int:
        return len(self._delegate)

    def append(self, record: Record) -> None:
        self._delegate.append(record)

    def extend(self, records: list[Record]) -> None:
        work_projection = any(isinstance(record, FiringCompleted) and record.transition == WORK for record in records)
        if not work_projection:
            self._delegate.extend(records)
            return
        attempt = cast(
            dict[str, JsonValue],
            {"record_types": [type(record).__name__ for record in records]},
        )
        if self._refusal is not None:
            message = self._refusal
            self._refusal = None
            self._attempts.append({"accepted": False, **attempt})
            raise OSError(message)
        self._delegate.extend(records)
        self._attempts.append({"accepted": True, **attempt})

    def refuse_next_projection(self, message: str) -> None:
        self._refusal = message


@dataclass
class RuntimeGeneration:
    engine: Engine
    history: RefusingProjectionHistory
    dispatch: RefusingLocalDispatch
    worker: LocalWorkerDispatch | None = None
    attempt: ActivityAttempt | None = None
    poisoned: bool = False
    timer_scheduled: int | None = None


class GeneratedRuntimeProfile:
    """One opaque production Engine spanning DS3's generated vocabulary."""

    identity = PROFILE_IDENTITY
    observation_fields: ClassVar[set[str]] = {
        "engine.generated-runtime-authority",
        "generated-runtime-state",
    }

    def __init__(self, history_path: Path, dispatch_path: Path):
        self.history_path = history_path
        self.dispatch_path = dispatch_path
        self.delivery_attempts: list[dict[str, JsonValue]] = []
        self.dispatch_attempts: list[dict[str, JsonValue]] = []
        self.projection_attempts: list[dict[str, JsonValue]] = []
        self.worker_attempts: list[dict[str, JsonValue]] = []
        self.worker_failures: list[dict[str, JsonValue]] = []
        self.worker_completions: list[dict[str, JsonValue]] = []
        self.prepare_calls = 0
        self.project_calls = 0
        self.scope_generation = 0
        self.scope_opens = 0
        self.scope_resets = 0
        self.drops = 0
        self.closes = 0

    def validate(self, command: Command) -> Command:
        payload = command.payload
        if command.name in {"engine.drive", "worker.claim"}:
            if payload != {}:
                raise ValueError(f"{command.name} payload must be an empty object")
            return command
        if command.name in {"scope.open", "scope.reset"}:
            if payload != {"name": SCOPE_NAME}:
                raise ValueError(f"{command.name} requires the exact supported scope name")
            return command
        if command.name == "source.deliver":
            if type(payload) is not dict or set(payload) != {"identity", "value"}:
                raise ValueError("source.deliver requires exact identity and value fields")
            if not isinstance(payload["identity"], str) or not payload["identity"]:
                raise ValueError("source.deliver identity must be a non-empty string")
            if isinstance(payload["value"], bool) or not isinstance(payload["value"], int):
                raise ValueError("source.deliver value must be an integer")
            return command
        if command.name == "worker.fail":
            if type(payload) is not dict or set(payload) != {"attempt", "error"}:
                raise ValueError("worker.fail requires exact attempt and error fields")
            if payload["attempt"] not in {1, 2}:
                raise ValueError("worker.fail attempt must be 1 or 2")
            if not isinstance(payload["error"], str) or not payload["error"]:
                raise ValueError("worker.fail error must be a non-empty string")
            return command
        if command.name == "worker.complete":
            if type(payload) is not dict or set(payload) != {"result"}:
                raise ValueError("worker.complete requires one exact result field")
            return command
        raise ValueError(f"unknown generated-runtime command {command.name!r}")

    def validate_fault(self, fault: Fault) -> Fault:
        expected = {
            "dispatch.refuse": ("activity_requested", FaultDisposition.REFUSE.value),
            "history.refuse": ("projection_committed", FaultDisposition.REFUSE.value),
        }
        if fault.name not in expected or (fault.target, fault.disposition) != expected[fault.name]:
            raise ValueError(f"unsupported generated-runtime fault {fault.name!r}")
        if type(fault.payload) is not dict or set(fault.payload) != {"message"}:
            raise ValueError("generated-runtime faults require one exact message field")
        if not isinstance(fault.payload["message"], str) or not fault.payload["message"]:
            raise ValueError("generated-runtime fault message must be a non-empty string")
        return fault

    def create(self, context: ScenarioContext) -> GenerationStart[RuntimeGeneration]:
        return GenerationStart(self._generation(context, load=False))

    def load(self, context: ScenarioContext) -> GenerationStart[RuntimeGeneration]:
        generation = self._generation(context, load=True)
        return GenerationStart(generation, (self._scheduled(context, context.now()),))

    def apply(
        self,
        generation: RuntimeGeneration,
        command: Command,
        context: ScenarioContext,
    ) -> ApplyResult:
        payload = cast(dict[str, JsonValue], command.payload)
        if command.name == "scope.open":
            scope = generation.engine.open_scope(SCOPE_NAME)
            self.scope_generation = scope.generation
            self.scope_opens += 1
            return self._applied(generation, {"generation": scope.generation})
        if command.name == "scope.reset":
            scope = generation.engine.active_scopes[SCOPE_NAME]
            opened = generation.engine.reset_scope(scope)
            self.scope_generation = opened.generation
            self.scope_resets += 1
            return self._applied(generation, {"generation": opened.generation})
        if command.name == "source.deliver":
            return self._deliver(generation, payload, context)
        if command.name == "worker.claim":
            return self._claim(generation, context)
        if command.name == "worker.fail":
            return self._fail(generation, payload)
        if command.name == "worker.complete":
            return self._complete(generation, payload)
        return self._drive(generation, context)

    def observe(
        self,
        generation: RuntimeGeneration,
        request: ObservationRequest,
        context: ScenarioContext,
    ) -> JsonValue:
        if request.name not in self.observation_fields:
            raise ValueError(f"unknown generated-runtime observation {request.name!r}")
        if request.payload not in (None, {}):
            raise ValueError("generated-runtime observations do not accept parameters")
        return self._observation_state(generation, context)

    def drop(self, generation: RuntimeGeneration) -> None:
        self.drops += 1
        if generation.worker is not None:
            generation.worker.close()
        generation.engine.close()

    def close(self, generation: RuntimeGeneration) -> None:
        self.closes += 1
        if generation.worker is not None:
            generation.worker.close()
        generation.engine.close()

    def resource_usage(self, generation: RuntimeGeneration | None) -> ResourceUsage:
        records: tuple[Record, ...] = ()
        if generation is not None:
            records = generation.history.records
        elif self.history_path.exists():
            records = JsonlHistoryStore(self.history_path).records
        external_facts = sum(
            len(facts)
            for facts in (
                self.delivery_attempts,
                self.dispatch_attempts,
                self.projection_attempts,
                self.worker_attempts,
                self.worker_failures,
                self.worker_completions,
            )
        )
        begun = {record.occurrence for record in records if isinstance(record, FiringBegun)}
        ended = {record.occurrence for record in records if isinstance(record, (FiringCompleted, FiringFailed))}
        cancelled = {
            occurrence for record in records if isinstance(record, ScopeReset) for occurrence in record.cancelled
        }
        accepted_dispatch = {
            cast(int, attempt["occurrence"]) for attempt in self.dispatch_attempts if cast(bool, attempt["accepted"])
        }
        provider_terminals = {cast(int, completion["occurrence"]) for completion in self.worker_completions}
        marking = replay_marking(records) if records else Marking()
        marking_projection = marking_view(marking)
        return ResourceUsage(
            values={
                "pending.dispatch_tasks": len(accepted_dispatch - provider_terminals),
                "pending.in_flight": len(begun - ended - cancelled),
                "pending.worker_claim": int(generation is not None and generation.attempt is not None),
                "retained.dispatch_facts": len(accepted_dispatch)
                + len(self.worker_attempts)
                + len(self.worker_failures)
                + len(self.worker_completions),
                "retained.external_facts": external_facts,
                "retained.history_bytes": self.history_path.stat().st_size if self.history_path.exists() else 0,
                "retained.history_records": len(records),
                "retained.marking_bytes": len(
                    json.dumps(marking_projection, allow_nan=False, separators=(",", ":")).encode()
                ),
                "retained.marking_tokens": sum(len(tokens) for _, tokens in marking),
            }
        )

    def _generation(self, context: ScenarioContext, *, load: bool) -> RuntimeGeneration:
        history = RefusingProjectionHistory(self.history_path, self.projection_attempts)
        dispatch = RefusingLocalDispatch(
            self.dispatch_path,
            instance=INSTANCE_ID,
            clock=WorldProviderClock(context),
            attempts=self.dispatch_attempts,
        )
        bridge = RuntimeBridge(self._prepared, self._projected)
        if load:
            engine = Engine.load(
                application_net(),
                INSTANCE_ID,
                history=history,
                dispatch=dispatch,
                handlers={"bridge": bridge},
                clock=WorldClock(context),
            )
        else:
            engine = Engine.create(
                application_net(),
                INSTANCE_ID,
                history=history,
                dispatch=dispatch,
                marking=Marking({WAITING: (Token("Waiting"),)}),
                handlers={"bridge": bridge},
                clock=WorldClock(context),
            )
        return RuntimeGeneration(engine, history, dispatch)

    def _deliver(
        self,
        generation: RuntimeGeneration,
        payload: dict[str, JsonValue],
        context: ScenarioContext,
    ) -> ApplyResult:
        identity = cast(str, payload["identity"])
        value = cast(int, payload["value"])
        scope = generation.engine.active_scopes[SCOPE_NAME]
        outcome = generation.engine.deliver(SOURCE, Token("Input", value), identity=identity, scope=scope)
        disposition = (
            ActionDisposition.IDEMPOTENT if isinstance(outcome, PriorAcknowledgement) else ActionDisposition.APPLIED
        )
        attempt = cast(
            dict[str, JsonValue],
            {"disposition": disposition.value, "identity": identity, "value": value},
        )
        self.delivery_attempts.append(attempt)
        return ApplyResult(
            disposition=disposition.value,
            value={"attempt": attempt, "frontier": len(generation.history)},
            scheduled=[self._scheduled(context, context.now())],
        )

    def _claim(self, generation: RuntimeGeneration, context: ScenarioContext) -> ApplyResult:
        if generation.attempt is not None:
            raise RuntimeError("generated runtime already holds an Activity attempt")
        worker = generation.dispatch.worker(worker_id=f"dst-generated-worker-{len(self.worker_attempts) + 1}")
        attempt = worker.claim()
        if attempt is None:
            raise RuntimeError("LocalDispatch has no eligible generated-runtime Activity")
        generation.worker = worker
        generation.attempt = attempt
        detached = self._attempt_view(attempt)
        self.worker_attempts.append(detached)
        return self._applied(generation, {"attempt": detached, "instant": context.now()})

    def _fail(self, generation: RuntimeGeneration, payload: dict[str, JsonValue]) -> ApplyResult:
        worker, attempt = self._active_attempt(generation)
        expected = cast(int, payload["attempt"])
        if int(attempt.epoch) != expected:
            raise ValueError(f"worker.fail expected epoch {expected}, found {attempt.epoch}")
        failure = ActivityFailure(
            cast(str, payload["error"]),
            kind="Unavailable",
            details={"attempt": expected},
            retryable=True,
            retry_after=0,
        )
        worker.fail(attempt, failure)
        self.worker_failures.append({"attempt": expected, "error": failure.error})
        worker.close()
        generation.worker = None
        generation.attempt = None
        return self._applied(generation, {"failed_epoch": expected})

    def _complete(self, generation: RuntimeGeneration, payload: dict[str, JsonValue]) -> ApplyResult:
        worker, attempt = self._active_attempt(generation)
        result = payload["result"]
        worker.complete(attempt, result)
        occurrence = self._attempt_occurrence(attempt)
        cancelled = any(
            isinstance(record, ScopeReset) and occurrence in record.cancelled for record in generation.history.records
        )
        report = cast(
            dict[str, JsonValue],
            {
                "cancelled": cancelled,
                "epoch": int(attempt.epoch),
                "occurrence": occurrence,
                "result": result,
            },
        )
        self.worker_completions.append(report)
        worker.close()
        generation.worker = None
        generation.attempt = None
        return self._applied(generation, {"report": report})

    def _drive(self, generation: RuntimeGeneration, context: ScenarioContext) -> ApplyResult:
        if generation.timer_scheduled == context.now():
            generation.timer_scheduled = None
        expected_errors = self._configure_faults(generation, context)
        try:
            outcome = generation.engine.advance()
        except OSError as error:
            if str(error) not in expected_errors:
                raise
            generation.poisoned = True
            return ApplyResult(
                disposition=ActionDisposition.REFUSED_EXPECTED.value,
                value={"error": str(error), "frontier": len(generation.history)},
                scheduled=[],
            )

        current = cast(dict[str, JsonValue], generation.engine.snapshot()["current"])
        in_flight = cast(list[dict[str, JsonValue]], current["in_flight"])
        activity_pending = any(entry["phase"] == "activity_pending" for entry in in_flight)
        scheduled: list[ScheduledCommand] = []
        next_maturation = current["next_maturation"]
        if outcome.ready and not activity_pending:
            scheduled.append(self._scheduled(context, context.now()))
        elif isinstance(next_maturation, int) and generation.timer_scheduled != next_maturation:
            generation.timer_scheduled = next_maturation
            scheduled.append(self._scheduled(context, next_maturation))
        return ApplyResult(
            disposition=ActionDisposition.APPLIED.value,
            value={
                "firings": [str(firing.transition) for firing in outcome.firings],
                "frontier": len(generation.history),
                "ready": outcome.ready,
                "status": current["status"],
                "waiting": outcome.waiting,
            },
            scheduled=scheduled,
        )

    def _configure_faults(self, generation: RuntimeGeneration, context: ScenarioContext) -> set[str]:
        messages = set()
        for fault in context.faults("activity_requested"):
            message = self._fault_message(fault, "dispatch.refuse")
            generation.dispatch.refuse_next_dispatch(message)
            messages.add(message)
        for fault in context.faults("projection_committed"):
            message = self._fault_message(fault, "history.refuse")
            generation.history.refuse_next_projection(message)
            messages.add(message)
        return messages

    def _observation_state(
        self,
        generation: RuntimeGeneration,
        context: ScenarioContext,
    ) -> dict[str, JsonValue]:
        records = generation.history.records
        current = None if generation.poisoned else cast(dict[str, JsonValue], generation.engine.snapshot()["current"])
        selected = [
            {"occurrence": record.occurrence, "transition": str(record.transition)}
            for record in records
            if isinstance(record, CandidateSelected)
        ]
        begun = [
            {"occurrence": record.occurrence, "transition": str(record.transition)}
            for record in records
            if isinstance(record, FiringBegun)
        ]
        requested = [
            {
                "activity": record.activity,
                "correlation": record.correlation,
                "idempotency": record.idempotency,
                "input": record.input,
                "occurrence": record.occurrence,
                "policy": asdict(record.policy),
            }
            for record in records
            if isinstance(record, ActivityRequested)
        ]
        completed = [record.occurrence for record in records if isinstance(record, ActivityCompleted)]
        firing_completed = [
            {"occurrence": record.occurrence, "transition": str(record.transition)}
            for record in records
            if isinstance(record, FiringCompleted)
        ]
        deliveries = [
            {"identity": record.identity, "value": record.tokens[0].data}
            for record in records
            if isinstance(record, ExternalEventDelivered)
        ]
        active_scopes, _ = replay_scopes(records)
        live_scopes = (
            None
            if current is None
            else {name: scope.generation for name, scope in sorted(generation.engine.active_scopes.items())}
        )
        return cast(
            dict[str, JsonValue],
            {
                "active_scopes": {name: scope.generation for name, scope in sorted(active_scopes.items())},
                "authored_scope_generation": self.scope_generation,
                "authored_scope_opens": self.scope_opens,
                "authored_scope_resets": self.scope_resets,
                "canonical_deliveries": deliveries,
                "completed_occurrences": completed,
                "current_instant": context.now(),
                "delivery_attempts": self.delivery_attempts,
                "dispatch_attempts": self.dispatch_attempts,
                "drops": self.drops,
                "firing_begun": begun,
                "firing_completed": firing_completed,
                "firing_failed": [
                    {"occurrence": record.occurrence, "transition": str(record.transition)}
                    for record in records
                    if isinstance(record, FiringFailed)
                ],
                "firing_selected": selected,
                "frontier": len(records),
                "live_in_flight": None if current is None else current["in_flight"],
                "live_marking": None if current is None else current["marking"],
                "live_scopes": live_scopes,
                "live_watermark": None if current is None else current["watermark"],
                "prepare_calls": self.prepare_calls,
                "project_calls": self.project_calls,
                "projection_attempts": self.projection_attempts,
                "quarantined_occurrences": [
                    record.occurrence for record in records if isinstance(record, ActivityTerminalQuarantined)
                ],
                "record_types": [type(record).__name__ for record in records],
                "record_occurrences": [
                    {"kind": type(record).__name__, "occurrence": record.occurrence}
                    for record in records
                    if isinstance(getattr(record, "occurrence", None), int)
                ],
                "replay_marking": marking_view(replay_marking(records)),
                "replay_watermark": replay_watermark(records),
                "requested_invocations": requested,
                "scope_records": [
                    {"generation": record.scope.generation, "kind": "open"}
                    if isinstance(record, ScopeOpened)
                    else {
                        "cancelled": list(record.cancelled),
                        "closed": record.closed.generation,
                        "kind": "reset",
                        "opened": record.opened.generation,
                    }
                    for record in records
                    if isinstance(record, (ScopeOpened, ScopeReset))
                ],
                "status": "poisoned" if current is None else current["status"],
                "timer_maturations": [
                    {"instant": record.instant, "maturation_instant": record.maturation_instant}
                    for record in records
                    if isinstance(record, TimerMatured)
                ],
                "worker_attempts": self.worker_attempts,
                "worker_completions": self.worker_completions,
                "worker_failures": self.worker_failures,
            },
        )

    def _prepared(self) -> None:
        self.prepare_calls += 1

    def _projected(self) -> None:
        self.project_calls += 1

    @staticmethod
    def _fault_message(fault: Fault, name: str) -> str:
        if fault.name != name or type(fault.payload) is not dict:
            raise ValueError(f"unexpected generated-runtime fault {fault.name!r}")
        message = fault.payload.get("message")
        if not isinstance(message, str):
            raise ValueError(f"generated-runtime fault {name!r} requires a message")
        return message

    @staticmethod
    def _active_attempt(generation: RuntimeGeneration) -> tuple[LocalWorkerDispatch, ActivityAttempt]:
        if generation.worker is None or generation.attempt is None:
            raise RuntimeError("worker outcome requires one claimed Activity attempt")
        return generation.worker, generation.attempt

    @staticmethod
    def _attempt_occurrence(attempt: ActivityAttempt) -> int:
        value = json.loads(attempt.attempt_id)
        if not isinstance(value, list) or len(value) != 2 or not isinstance(value[1], int):
            raise ValueError("generated runtime received a malformed LocalDispatch attempt identity")
        return value[1]

    def _attempt_view(self, attempt: ActivityAttempt) -> dict[str, JsonValue]:
        invocation = attempt.invocation
        return cast(
            dict[str, JsonValue],
            {
                "activity": invocation.activity,
                "correlation": invocation.correlation,
                "epoch": int(attempt.epoch),
                "idempotency": invocation.idempotency,
                "input": invocation.input,
                "occurrence": self._attempt_occurrence(attempt),
                "policy": asdict(invocation.policy),
                "queue": attempt.queue,
            },
        )

    def _applied(
        self,
        generation: RuntimeGeneration,
        value: dict[str, JsonValue],
    ) -> ApplyResult:
        return ApplyResult(
            disposition=ActionDisposition.APPLIED.value,
            value={"frontier": len(generation.history), **value},
            scheduled=[],
        )

    def _scheduled(self, context: ScenarioContext, instant: int) -> ScheduledCommand:
        del context
        return ScheduledCommand(
            instant=instant,
            command=Command(profile=self.identity, name="engine.drive", payload={}),
        )


class GeneratedRuntimeAuthorityChecker:
    """Judge runtime facts from authored authority and detached canonical folds."""

    identity = CHECKER_IDENTITY
    request = ObservationRequest(name="engine.generated-runtime-authority", payload={})

    def __init__(self) -> None:
        self._frozen_execution_counts: dict[JsonValue, tuple[int, int]] = {}

    def check(self, observation: Observation) -> CheckResult:
        value = cast(dict[str, JsonValue], observation.value)
        live_marking = value["live_marking"]
        live_watermark = value["live_watermark"]
        replay_exact = live_marking is None or (
            live_marking == value["replay_marking"] and live_watermark == value["replay_watermark"]
        )

        selected = cast(list[dict[str, JsonValue]], value["firing_selected"])
        begun = cast(list[dict[str, JsonValue]], value["firing_begun"])
        begun_pairs = {(entry["occurrence"], entry["transition"]) for entry in begun}
        selected_pairs = {(entry["occurrence"], entry["transition"]) for entry in selected}
        occurrence_pairs = (
            selected_pairs <= begun_pairs
            and len(selected_pairs) == len(selected)
            and len({entry["occurrence"] for entry in begun}) == len(begun)
        )

        begun_occurrences = {entry["occurrence"] for entry in begun}
        completed_firings = cast(list[dict[str, JsonValue]], value["firing_completed"])
        failed_firings = cast(list[dict[str, JsonValue]], value["firing_failed"])
        completed_ids = [entry["occurrence"] for entry in completed_firings]
        failed_ids = [entry["occurrence"] for entry in failed_firings]
        record_occurrences = cast(list[dict[str, JsonValue]], value["record_occurrences"])
        history_writer_valid = (
            sorted(cast(int, occurrence) for occurrence in begun_occurrences) == list(range(1, len(begun) + 1))
            and all(entry["occurrence"] in begun_occurrences for entry in record_occurrences)
            and len(completed_ids) == len(set(completed_ids))
            and len(failed_ids) == len(set(failed_ids))
            and not set(completed_ids).intersection(failed_ids)
        )

        requests = cast(list[dict[str, JsonValue]], value["requested_invocations"])
        dispatches = cast(list[dict[str, JsonValue]], value["dispatch_attempts"])
        worker_attempts = cast(list[dict[str, JsonValue]], value["worker_attempts"])
        request_by_occurrence = {request["occurrence"]: request for request in requests}
        invocation_stable = all(
            {name: field for name, field in dispatch.items() if name != "accepted"}
            == request_by_occurrence.get(dispatch["occurrence"])
            for dispatch in dispatches
        ) and all(
            {name: field for name, field in attempt.items() if name not in {"epoch", "queue"}}
            == request_by_occurrence.get(attempt["occurrence"])
            for attempt in worker_attempts
        )
        preparation_exact = cast(int, value["prepare_calls"]) == len(requests)

        attempts_by_occurrence: dict[JsonValue, list[int]] = {}
        for attempt in worker_attempts:
            attempts_by_occurrence.setdefault(attempt["occurrence"], []).append(cast(int, attempt["epoch"]))
        retries_bounded = all(
            epochs == list(range(1, len(epochs) + 1)) and len(epochs) <= 2 for epochs in attempts_by_occurrence.values()
        )

        delivery_attempts = cast(list[dict[str, JsonValue]], value["delivery_attempts"])
        canonical_deliveries = cast(list[dict[str, JsonValue]], value["canonical_deliveries"])
        accepted: dict[str, JsonValue] = {}
        delivery_acknowledgements = True
        for attempt in delivery_attempts:
            identity = cast(str, attempt["identity"])
            payload = attempt["value"]
            if identity not in accepted:
                delivery_acknowledgements = delivery_acknowledgements and attempt["disposition"] == "applied"
                accepted[identity] = payload
            else:
                delivery_acknowledgements = delivery_acknowledgements and (
                    accepted[identity] == payload and attempt["disposition"] == "idempotent"
                )
        delivery_exact = canonical_deliveries == [
            {"identity": identity, "value": payload} for identity, payload in accepted.items()
        ]

        completed = cast(list[JsonValue], value["completed_occurrences"])
        quarantined = cast(list[JsonValue], value["quarantined_occurrences"])
        completions = cast(list[dict[str, JsonValue]], value["worker_completions"])
        terminal_unique = len(completed) == len(set(completed)) and len(quarantined) == len(set(quarantined))
        completion_occurrences = [completion["occurrence"] for completion in completions]
        terminal_authorized = set(completed).union(quarantined) <= set(completion_occurrences) and len(
            completion_occurrences
        ) == len(set(completion_occurrences))

        frozen_execution = True
        for occurrence in completed:
            execution_counts = (
                sum(attempt["occurrence"] == occurrence for attempt in dispatches),
                sum(attempt["occurrence"] == occurrence for attempt in worker_attempts),
            )
            previous = self._frozen_execution_counts.setdefault(occurrence, execution_counts)
            frozen_execution = frozen_execution and execution_counts == previous

        projection_attempts = cast(list[dict[str, JsonValue]], value["projection_attempts"])
        work_firings = [
            firing
            for firing in cast(list[dict[str, JsonValue]], value["firing_completed"])
            if firing["transition"] == str(WORK)
        ]
        projection_exact = (
            cast(int, value["project_calls"]) == len(projection_attempts)
            and len(work_firings) == sum(cast(bool, attempt["accepted"]) for attempt in projection_attempts)
            and set(firing["occurrence"] for firing in work_firings) <= set(completed)
        )

        active_scopes = value["active_scopes"]
        generation = cast(int, value["authored_scope_generation"])
        lifecycle_exact = active_scopes == ({} if generation == 0 else {SCOPE_NAME: generation})
        lifecycle_exact = (
            lifecycle_exact
            and (value["live_scopes"] is None or value["live_scopes"] == active_scopes)
            and cast(int, value["authored_scope_opens"]) <= 1
            and cast(int, value["authored_scope_resets"]) <= 1
            and all(completion["cancelled"] for completion in completions if completion["occurrence"] in quarantined)
        )

        cancelled = {
            occurrence
            for record in cast(list[dict[str, JsonValue]], value["scope_records"])
            for occurrence in cast(list[JsonValue], record.get("cancelled", []))
        }
        expected_in_flight = begun_occurrences - set(completed_ids) - set(failed_ids) - cancelled
        completed_activities = set(completed)
        request_occurrences = {request["occurrence"] for request in requests}
        expected_phases = {
            occurrence: (
                "projection_pending"
                if occurrence in completed_activities
                else "activity_pending"
                if occurrence in request_occurrences
                else "pure_pending"
            )
            for occurrence in expected_in_flight
        }
        live_in_flight = value["live_in_flight"]
        in_flight_exact = (
            live_in_flight is None
            or {entry["occurrence"]: entry["phase"] for entry in cast(list[dict[str, JsonValue]], live_in_flight)}
            == expected_phases
        )

        maturations = cast(list[dict[str, JsonValue]], value["timer_maturations"])
        timer_firings = [
            firing
            for firing in cast(list[dict[str, JsonValue]], value["firing_completed"])
            if firing["transition"] == str(RELEASE)
        ]
        timer_exact = (
            len(maturations) <= 1
            and all(
                maturation == {"instant": MATURATION_INSTANT, "maturation_instant": MATURATION_INSTANT}
                for maturation in maturations
            )
            and len(timer_firings) <= len(maturations)
        )

        bounds_hold = (
            len(cast(list[JsonValue], value["record_types"])) <= 128
            and len(delivery_attempts) <= 8
            and len(worker_attempts) <= 16
        )
        passed = all(
            (
                replay_exact,
                in_flight_exact,
                occurrence_pairs,
                history_writer_valid,
                invocation_stable,
                preparation_exact,
                retries_bounded,
                delivery_exact,
                delivery_acknowledgements,
                terminal_unique,
                terminal_authorized,
                frozen_execution,
                projection_exact,
                lifecycle_exact,
                timer_exact,
                bounds_hold,
            )
        )
        return CheckResult(
            passed=passed,
            detail={
                "bounds_hold": bounds_hold,
                "delivery_acknowledgements": delivery_acknowledgements,
                "delivery_exact": delivery_exact,
                "frozen_execution": frozen_execution,
                "history_writer_valid": history_writer_valid,
                "in_flight_exact": in_flight_exact,
                "invocation_stable": invocation_stable,
                "lifecycle_exact": lifecycle_exact,
                "occurrence_pairs": occurrence_pairs,
                "projection_exact": projection_exact,
                "preparation_exact": preparation_exact,
                "replay_exact": replay_exact,
                "retries_bounded": retries_bounded,
                "terminal_authorized": terminal_authorized,
                "terminal_unique": terminal_unique,
                "timer_exact": timer_exact,
            },
        )


def execute_generated_runtime_story(
    history_path: Path,
    dispatch_path: Path,
    *,
    first_value: int = 3,
    second_value: int = 7,
    retry_error: str = "generated retry",
    dispatch_error: str = "dst generated Dispatch custody refused",
    projection_error: str = "dst generated projection refused",
    finish: bool = True,
) -> tuple[World, GeneratedRuntimeProfile]:
    """Exercise every TS2 event/fault dimension in one interpreter run."""

    profile = GeneratedRuntimeProfile(history_path, dispatch_path)
    world = World(profile, WORLD_BUDGET, checkers=(GeneratedRuntimeAuthorityChecker(),))
    timeline = world.timeline()

    timeline.command("scope.open", {"name": SCOPE_NAME})
    timeline.activate_fault(
        "dispatch.refuse",
        "activity_requested",
        disposition=FaultDisposition.REFUSE,
        payload={"message": dispatch_error},
    )
    timeline.command("source.deliver", {"identity": "generated-event-1", "value": first_value})
    refused = world.step()
    assert refused.result.disposition == ActionDisposition.REFUSED_EXPECTED.value

    timeline.crash("generated_dispatch_refused")
    world.restart()
    timeline = world.timeline()
    requested = timeline.run_until(
        "generated-runtime-state",
        lambda observation: (
            sum(
                cast(bool, attempt["accepted"])
                for attempt in cast(
                    list[dict[str, JsonValue]], cast(dict[str, JsonValue], observation.value)["dispatch_attempts"]
                )
            )
            == 1
        ),
    )
    assert cast(dict[str, JsonValue], requested.value)["prepare_calls"] == 1

    first = timeline.command("worker.claim", {})
    assert cast(dict[str, JsonValue], first.value)["attempt"]["epoch"] == 1
    timeline.command("worker.fail", {"attempt": 1, "error": retry_error})
    second = timeline.command("worker.claim", {})
    assert cast(dict[str, JsonValue], second.value)["attempt"]["epoch"] == 2
    timeline.command("worker.complete", {"result": {"value": first_value}})

    timeline.activate_fault(
        "history.refuse",
        "projection_committed",
        disposition=FaultDisposition.REFUSE,
        payload={"message": projection_error},
    )
    projected = timeline.command("engine.drive", {})
    assert projected.disposition == ActionDisposition.REFUSED_EXPECTED.value
    frozen = timeline.observe("generated-runtime-state")
    frozen_value = cast(dict[str, JsonValue], frozen.value)
    assert frozen_value["completed_occurrences"] == [2]
    assert not any(
        firing["transition"] == str(WORK)
        for firing in cast(list[dict[str, JsonValue]], frozen_value["firing_completed"])
    )

    timeline.crash("generated_projection_refused")
    world.restart()
    timeline = world.timeline()
    recovered = timeline.run_until(
        "generated-runtime-state",
        lambda observation: any(
            firing["transition"] == str(WORK)
            for firing in cast(
                list[dict[str, JsonValue]],
                cast(dict[str, JsonValue], observation.value)["firing_completed"],
            )
        ),
    )
    recovered_value = cast(dict[str, JsonValue], recovered.value)
    assert recovered_value["prepare_calls"] == 1
    assert len(cast(list[JsonValue], recovered_value["worker_attempts"])) == 2

    while world.pending() and world.pending()[0]["instant"] == world.instant:
        world.step()
    duplicate = timeline.command(
        "source.deliver",
        {"identity": "generated-event-1", "value": first_value},
    )
    assert duplicate.disposition == ActionDisposition.IDEMPOTENT.value
    while world.pending() and world.pending()[0]["instant"] == world.instant:
        world.step()

    timeline.command("source.deliver", {"identity": "generated-event-2", "value": second_value})
    timeline.run_until(
        "generated-runtime-state",
        lambda observation: (
            len(cast(list[JsonValue], cast(dict[str, JsonValue], observation.value)["requested_invocations"])) == 2
        ),
    )
    late = timeline.command("worker.claim", {})
    late_occurrence = cast(dict[str, JsonValue], late.value)["attempt"]["occurrence"]
    timeline.command("scope.reset", {"name": SCOPE_NAME})
    timeline.command("worker.complete", {"result": {"value": second_value}})
    timeline.command("engine.drive", {})
    quarantined = timeline.observe("generated-runtime-state")
    assert late_occurrence in cast(
        list[JsonValue],
        cast(dict[str, JsonValue], quarantined.value)["quarantined_occurrences"],
    )
    assert cast(dict[str, JsonValue], quarantined.value)["active_scopes"] == {SCOPE_NAME: 2}

    timer = timeline.run_until(
        "generated-runtime-state",
        lambda observation: any(
            firing["transition"] == str(RELEASE)
            for firing in cast(
                list[dict[str, JsonValue]],
                cast(dict[str, JsonValue], observation.value)["firing_completed"],
            )
        ),
    )
    timer_value = cast(dict[str, JsonValue], timer.value)
    assert timer_value["current_instant"] == MATURATION_INSTANT
    assert timer_value["timer_maturations"] == [
        {"instant": MATURATION_INSTANT, "maturation_instant": MATURATION_INSTANT}
    ]
    while world.pending():
        world.step()
    if finish:
        timeline.finish(Disposition.EXTERNAL_WAIT)
    return world, profile


def build_generated_runtime_artifact(history_path: Path, dispatch_path: Path) -> ScenarioArtifact:
    world, _ = execute_generated_runtime_story(history_path, dispatch_path)
    try:
        artifact = world.artifact(SCENARIO_ID)
        assert isinstance(artifact, ScenarioArtifact)
        return artifact
    finally:
        world.close()
