"""Public-Engine DST profile and executable projection recovery story."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import ClassVar, cast

from pydantic import JsonValue

from petrus.engine import Engine
from petrus.impetus.history import ActivityCompleted, ActivityFailed, ActivityRequested, FiringCompleted, Record
from petrus.impetus.history_store import HistoryStore, JsonlHistoryStore
from petrus.impetus.petrinet import Arc, Marking, Net, NetPath, Place, Token, Transition
from petrus.motus.activity import ActivityInvocation
from petrus.motus.dispatch import InMemoryDispatch
from petrus.testing.dst import (
    ActionDisposition,
    ApplyResult,
    Budget,
    BudgetV4,
    BudgetExhausted,
    CheckResult,
    CheckerIdentity,
    ChoiceAuthority,
    Command,
    Disposition,
    Fault,
    FaultDisposition,
    GenerationStart,
    InvariantViolation,
    Observation,
    ObservationRequest,
    ProfileIdentity,
    ResourceUsage,
    ScenarioArtifact,
    ScenarioArtifactV3,
    ScenarioContext,
    ScheduledCommand,
    Timeline,
    World,
    digest_json,
)

INPUT = NetPath("input")
DONE = NetPath("done")
PROJECT = NetPath("project")
INSTANCE_ID = "dst-world-projection-recovery"
LEGACY_SCENARIO_ID = "projection-crash-recovery-world-v1"
SCENARIO_ID = "projection-crash-recovery-world-v3"
SEEDED_SCENARIO_ID = "seeded-projection-crash-recovery-world-v3"
SCENARIO_SEED = 1729
HISTORY_REFUSAL_SCENARIO_ID = "history-refusal-crash-recovery-world-v3"
HISTORY_ACK_LOSS_SCENARIO_ID = "history-ack-loss-recovery-world-v3"
INVARIANT_FAILURE_SCENARIO_ID = "terminal-checker-failure-world-v2"
BUDGET_FAILURE_SCENARIO_ID = "action-budget-exhaustion-world-v2"
RESOURCE_SCENARIO_ID = "resource-bounded-recovery-world-v4"
RESOURCE_BUDGET_FAILURE_SCENARIO_ID = "history-record-budget-exhaustion-world-v4"

PROFILE_DEFINITION = {
    "commands": ["engine.complete", "engine.drive"],
    "cut": "activity_terminal_frozen",
    "instance": INSTANCE_ID,
    "net": {
        "activity": "calculate",
        "places": ["done", "input"],
        "transition": "project",
    },
    "observations": [
        "activity-requested",
        "engine.safety",
        "projection-refused",
        "terminal",
    ],
}
PROFILE_IDENTITY = ProfileIdentity(
    name="petrus.engine.projection-recovery",
    version=1,
    digest=digest_json(PROFILE_DEFINITION),
)
RESOURCE_PROFILE_IDENTITY = ProfileIdentity(
    name="petrus.engine.resource-bounded-recovery",
    version=1,
    digest=digest_json(
        {
            "commands": ["engine.complete", "engine.drive"],
            "instance": INSTANCE_ID,
            "observations": ["activity-requested", "engine.safety", "terminal"],
            "resources": [
                "pending.dispatch",
                "pending.in_flight",
                "retained.history_bytes",
                "retained.history_records",
                "retained.marking_bytes",
                "retained.marking_tokens",
            ],
        }
    ),
)
HISTORY_REFUSAL_PROFILE_IDENTITY = ProfileIdentity(
    name="petrus.engine.history-refusal-recovery",
    version=1,
    digest=digest_json(
        {
            "commands": ["engine.complete", "engine.drive"],
            "fault": {
                "disposition": "refuse",
                "name": "history.refuse",
                "target": "activity_terminal_frozen",
            },
            "instance": INSTANCE_ID,
            "observations": [
                "activity-requested",
                "engine.commit-authority",
                "engine.safety",
                "recovered-request",
                "semantic-batch-refused",
                "terminal",
            ],
            "pending_invocation": [
                "activity",
                "correlation",
                "idempotency",
                "input",
                "occurrence",
                "policy",
            ],
        }
    ),
)
HISTORY_ACK_LOSS_PROFILE_IDENTITY = ProfileIdentity(
    name="petrus.engine.history-ack-loss-recovery",
    version=1,
    digest=digest_json(
        {
            "commands": ["engine.complete", "engine.drive"],
            "fault": {
                "disposition": "raise",
                "name": "history.lose-ack",
                "target": "activity_terminal_frozen",
            },
            "instance": INSTANCE_ID,
            "observations": [
                "activity-requested",
                "engine.accepted-commit-authority",
                "terminal-ack-lost",
                "terminal-recovered",
            ],
        }
    ),
)
CHECKER_IDENTITY = CheckerIdentity(
    name="petrus.engine.history-order",
    version=1,
    digest=digest_json(
        {
            "properties": [
                "one activity request",
                "one frozen terminal",
                "terminal precedes projection",
            ]
        }
    ),
)
COMMIT_AUTHORITY_CHECKER_IDENTITY = CheckerIdentity(
    name="petrus.engine.commit-authority",
    version=1,
    digest=digest_json(
        {
            "property": (
                "activity terminals and projections never exceed authored terminal deliveries "
                "minus pre-commit history refusals"
            )
        }
    ),
)
ACCEPTED_COMMIT_AUTHORITY_CHECKER_IDENTITY = CheckerIdentity(
    name="petrus.engine.accepted-commit-authority",
    version=1,
    digest=digest_json(
        {
            "property": (
                "a post-commit acknowledgement loss implies one durable terminal, "
                "which remains bounded by authored terminal delivery"
            )
        }
    ),
)
TERMINAL_REFUSAL_CHECKER_IDENTITY = CheckerIdentity(
    name="petrus.engine.deliberate-terminal-refusal",
    version=1,
    digest=digest_json({"property": "terminal firing is rejected to prove exact checker-failure replay"}),
)
WORLD_BUDGET = Budget(
    actions=32,
    queued_commands=8,
    timer_advances=0,
    logical_instant=0,
    reloads=1,
    predicate_polls=16,
    artifact_bytes=262_144,
)


def resource_world_budget(*, history_records: int = 16) -> BudgetV4:
    return BudgetV4(
        actions=32,
        queued_commands=8,
        timer_advances=0,
        logical_instant=0,
        reloads=1,
        predicate_polls=16,
        artifact_bytes=262_144,
        profile_resources={
            "pending.dispatch": 4,
            "pending.in_flight": 4,
            "retained.history_bytes": 65_536,
            "retained.history_records": history_records,
            "retained.marking_bytes": 8_192,
            "retained.marking_tokens": 16,
        },
    )


def application_net() -> Net:
    return Net(
        places=[Place(INPUT), Place(DONE)],
        transitions=[Transition(PROJECT, handler="bridge")],
        arcs=[Arc(INPUT, PROJECT), Arc(PROJECT, DONE)],
        name="dst-world-projection-recovery",
    )


class ProjectionBridge:
    def __init__(self) -> None:
        self.prepared = 0
        self.projected = 0
        self.projection_error: str | None = None

    def prepare(self, binding) -> ActivityInvocation:
        self.prepared += 1
        return ActivityInvocation("calculate", input=binding.tokens[0].data)

    def project(self, binding, result):
        del binding
        self.projected += 1
        if self.projection_error is not None:
            raise RuntimeError(self.projection_error)
        return {DONE: (Token("Done", result),)}


class WorldClock:
    """Engine Clock which can observe only the World's current logical instant."""

    def __init__(self, context: ScenarioContext):
        self.context = context

    def now(self) -> int:
        return self.context.now()

    def observe(self, instant: int) -> int | None:
        return self.context.now() if self.context.now() >= instant else None


class RefusingJsonlHistoryStore:
    """JSONL delegate which can refuse one terminal append before acceptance."""

    def __init__(self, path: Path, on_refusal: Callable[[], None]) -> None:
        self._delegate = JsonlHistoryStore(path)
        self._on_refusal = on_refusal
        self._terminal_error: str | None = None

    @property
    def records(self) -> tuple[Record, ...]:
        return self._delegate.records

    def __iter__(self) -> Iterator[Record]:
        return iter(self._delegate)

    def __len__(self) -> int:
        return len(self._delegate)

    def append(self, record: Record) -> None:
        if self._terminal_error is not None and isinstance(record, (ActivityCompleted, ActivityFailed)):
            message = self._terminal_error
            self._terminal_error = None
            self._on_refusal()
            raise OSError(message)
        self._delegate.append(record)

    def extend(self, records: list[Record]) -> None:
        self._delegate.extend(records)

    def refuse_terminal(self, message: str) -> None:
        self._terminal_error = message


class AckLosingJsonlHistoryStore:
    """JSONL delegate which loses one acknowledgement after durable acceptance."""

    def __init__(self, path: Path, on_ack_loss: Callable[[], None]) -> None:
        self._delegate = JsonlHistoryStore(path)
        self._on_ack_loss = on_ack_loss
        self._terminal_error: str | None = None

    @property
    def records(self) -> tuple[Record, ...]:
        return self._delegate.records

    def __iter__(self) -> Iterator[Record]:
        return iter(self._delegate)

    def __len__(self) -> int:
        return len(self._delegate)

    def append(self, record: Record) -> None:
        self._delegate.append(record)
        if self._terminal_error is not None and isinstance(record, (ActivityCompleted, ActivityFailed)):
            message = self._terminal_error
            self._terminal_error = None
            self._on_ack_loss()
            raise OSError(message)

    def extend(self, records: list[Record]) -> None:
        self._delegate.extend(records)

    def lose_terminal_ack(self, message: str) -> None:
        self._terminal_error = message


@dataclass
class EngineGeneration:
    engine: Engine
    history: HistoryStore
    dispatch: InMemoryDispatch
    bridge: ProjectionBridge
    poisoned: bool = False
    dropped: bool = False


class EngineProfile:
    """Petrus-owned profile composed exclusively through public Engine doors."""

    identity = PROFILE_IDENTITY
    observation_fields: ClassVar[dict[str, tuple[str, ...]]] = {
        "activity-requested": ("frontier", "pending", "status"),
        "projection-refused": ("bridge", "frontier", "record_types", "status"),
        "terminal": ("bridge", "drops", "frontier", "marking", "record_types", "status"),
    }

    def __init__(self, history_path: Path):
        self.history_path = history_path
        self.drops = 0
        self.closes = 0

    def validate(self, command: Command) -> Command:
        if command.name == "engine.drive":
            if command.payload != {}:
                raise ValueError("engine.drive payload must be an empty object")
            return command
        if command.name == "engine.complete":
            payload = command.payload
            if type(payload) is not dict or set(payload) != {"occurrence", "result"}:
                raise ValueError("engine.complete requires exact occurrence and result fields")
            occurrence = payload["occurrence"]
            if isinstance(occurrence, bool) or not isinstance(occurrence, int) or occurrence < 1:
                raise ValueError("engine.complete occurrence must be a positive integer")
            return command
        raise ValueError(f"unknown public-Engine profile command {command.name!r}")

    def validate_fault(self, fault: Fault) -> Fault:
        if (
            fault.name != "projection.raise"
            or fault.target != "activity_terminal_frozen"
            or fault.disposition != FaultDisposition.RAISE.value
            or type(fault.payload) is not dict
            or set(fault.payload) != {"message"}
            or not isinstance(fault.payload["message"], str)
        ):
            raise ValueError("unsupported public-Engine profile fault")
        return fault

    def create(self, context: ScenarioContext) -> GenerationStart[EngineGeneration]:
        history = self._history(context)
        dispatch = InMemoryDispatch()
        bridge = ProjectionBridge()
        engine = Engine.create(
            application_net(),
            INSTANCE_ID,
            history=history,
            dispatch=dispatch,
            marking=Marking({INPUT: (Token("Input", 3),)}),
            handlers={"bridge": bridge},
            clock=WorldClock(context),
        )
        generation = EngineGeneration(engine, history, dispatch, bridge)
        return GenerationStart(generation, (self._scheduled(context, "engine.drive", {}),))

    def load(self, context: ScenarioContext) -> GenerationStart[EngineGeneration]:
        history = self._history(context)
        dispatch = InMemoryDispatch()
        bridge = ProjectionBridge()
        engine = Engine.load(
            application_net(),
            INSTANCE_ID,
            history=history,
            dispatch=dispatch,
            handlers={"bridge": bridge},
            clock=WorldClock(context),
        )
        generation = EngineGeneration(engine, history, dispatch, bridge)
        return GenerationStart(generation, (self._scheduled(context, "engine.drive", {}),))

    def apply(
        self,
        generation: EngineGeneration,
        command: Command,
        context: ScenarioContext,
    ) -> ApplyResult:
        if command.name == "engine.complete":
            payload = cast(dict[str, JsonValue], command.payload)
            generation.dispatch.complete(cast(int, payload["occurrence"]), payload["result"])
            self._terminal_ready()
            return ApplyResult(
                disposition=ActionDisposition.APPLIED.value,
                value={"frontier": len(generation.history)},
                scheduled=[self._scheduled(context, "engine.drive", {})],
            )

        expected_errors = self._configure_faults(generation, context)

        try:
            outcome = generation.engine.advance()
        except Exception as error:
            if not any(isinstance(error, kind) and str(error) == message for kind, message in expected_errors):
                raise
            generation.poisoned = True
            return ApplyResult(
                disposition=ActionDisposition.REFUSED_EXPECTED.value,
                value={"error": str(error), "frontier": len(generation.history)},
                scheduled=[],
            )

        current = generation.engine.snapshot()["current"]
        assert isinstance(current, dict)
        status = current["status"]
        scheduled = []
        if status not in {"completed", "terminated"} and outcome.ready and not generation.dispatch.pending:
            scheduled.append(self._scheduled(context, "engine.drive", {}))
        return ApplyResult(
            disposition=ActionDisposition.APPLIED.value,
            value={
                "firings": [str(firing.transition) for firing in outcome.firings],
                "frontier": len(generation.history),
                "ready": outcome.ready,
                "status": status,
                "waiting": outcome.waiting,
            },
            scheduled=scheduled,
        )

    def observe(
        self,
        generation: EngineGeneration,
        request: ObservationRequest,
        context: ScenarioContext,
    ) -> JsonValue:
        del context
        if request.name != "engine.safety" and request.name not in self.observation_fields:
            raise ValueError(f"unknown public-Engine profile observation {request.name!r}")
        if request.payload not in (None, {}):
            raise ValueError("public-Engine profile observations do not accept parameters")
        state = self._observation_state(generation)
        if request.name == "engine.safety":
            return {"record_types": state["record_types"]}
        fields = self.observation_fields[request.name]
        return {field: state[field] for field in fields}

    def _observation_state(self, generation: EngineGeneration) -> dict[str, JsonValue]:
        records = generation.history.records
        record_types = [type(record).__name__ for record in records]
        if generation.poisoned:
            status = "poisoned"
            marking = None
            in_flight = None
        else:
            current = generation.engine.snapshot()["current"]
            assert isinstance(current, dict)
            status = current["status"]
            marking = current["marking"]
            in_flight = current["in_flight"]
        state = {
            "bridge": {
                "prepared": generation.bridge.prepared,
                "projected": generation.bridge.projected,
            },
            "drops": self.drops,
            "frontier": len(records),
            "in_flight": in_flight,
            "marking": marking,
            "pending": sorted(generation.dispatch.pending),
            "pending_invocations": [
                {
                    "activity": invocation.activity,
                    "correlation": invocation.correlation,
                    "idempotency": invocation.idempotency,
                    "input": invocation.input,
                    "occurrence": occurrence,
                    "policy": asdict(invocation.policy),
                }
                for occurrence, invocation in sorted(generation.dispatch.pending.items())
            ],
            "record_types": record_types,
            "status": status,
        }
        return cast(dict[str, JsonValue], state)

    def drop(self, generation: EngineGeneration) -> None:
        self.drops += 1
        generation.dropped = True
        generation.engine.close()

    def close(self, generation: EngineGeneration) -> None:
        self.closes += 1
        generation.engine.close()

    def _scheduled(self, context: ScenarioContext, name: str, payload: object) -> ScheduledCommand:
        return ScheduledCommand(
            instant=context.now(),
            command=Command(profile=self.identity, name=name, payload=payload),
        )

    def _history(self, context: ScenarioContext) -> HistoryStore:
        del context
        return JsonlHistoryStore(self.history_path)

    def _terminal_ready(self) -> None:
        pass

    def _configure_faults(
        self, generation: EngineGeneration, context: ScenarioContext
    ) -> tuple[tuple[type[Exception], str], ...]:
        expected = []
        for fault in context.faults("activity_terminal_frozen"):
            if fault.name != "projection.raise" or fault.disposition != FaultDisposition.RAISE.value:
                raise ValueError(f"unsupported public-Engine profile fault {fault.name!r}")
            if type(fault.payload) is not dict or set(fault.payload) != {"message"}:
                raise ValueError("projection.raise requires an exact message payload")
            message = fault.payload["message"]
            if not isinstance(message, str):
                raise ValueError("projection.raise message must be a string")
            generation.bridge.projection_error = message
            expected.append((RuntimeError, message))
        return tuple(expected)


class ResourceBoundedEngineProfile(EngineProfile):
    """Public-Engine profile with complete detached retained/pending gauges."""

    identity = RESOURCE_PROFILE_IDENTITY

    def validate_fault(self, fault: Fault) -> Fault:
        del fault
        raise ValueError("resource-bounded public-Engine profile does not accept faults")

    def resource_usage(self, generation: EngineGeneration | None) -> ResourceUsage:
        history = JsonlHistoryStore(self.history_path) if generation is None else generation.history
        history_bytes = self.history_path.stat().st_size if self.history_path.exists() else 0
        if generation is None:
            marking: list[JsonValue] = []
            in_flight: list[JsonValue] = []
            dispatch_pending = 0
        else:
            current = generation.engine.snapshot()["current"]
            assert isinstance(current, dict)
            marking = cast(list[JsonValue], current["marking"])
            in_flight = cast(list[JsonValue], current["in_flight"])
            dispatch_pending = len(generation.dispatch.pending)
        marking_bytes = len(json.dumps(marking, allow_nan=False, separators=(",", ":"), sort_keys=True).encode())
        marking_tokens = sum(
            len(cast(list[JsonValue], cast(dict[str, JsonValue], entry)["tokens"])) for entry in marking
        )
        return ResourceUsage(
            values={
                "pending.dispatch": dispatch_pending,
                "pending.in_flight": len(in_flight),
                "retained.history_bytes": history_bytes,
                "retained.history_records": len(history),
                "retained.marking_bytes": marking_bytes,
                "retained.marking_tokens": marking_tokens,
            }
        )


class HistoryRefusalEngineProfile(EngineProfile):
    """Public-Engine profile with one unambiguously pre-commit terminal cut."""

    identity = HISTORY_REFUSAL_PROFILE_IDENTITY
    observation_fields = {
        "activity-requested": (
            *EngineProfile.observation_fields["activity-requested"],
            "pending_invocations",
        ),
        "engine.commit-authority": (
            "record_types",
            "terminal_deliveries",
            "terminal_refusals",
        ),
        "recovered-request": (
            "bridge",
            "frontier",
            "pending",
            "pending_invocations",
            "record_types",
            "status",
            "terminal_deliveries",
            "terminal_refusals",
        ),
        "semantic-batch-refused": (
            "bridge",
            "frontier",
            "record_types",
            "status",
            "terminal_deliveries",
            "terminal_refusals",
        ),
        "terminal": EngineProfile.observation_fields["terminal"],
    }

    def __init__(self, history_path: Path):
        super().__init__(history_path)
        self.terminal_deliveries = 0
        self.terminal_refusals = 0

    def validate_fault(self, fault: Fault) -> Fault:
        if (
            fault.name != "history.refuse"
            or fault.target != "activity_terminal_frozen"
            or fault.disposition != FaultDisposition.REFUSE.value
            or type(fault.payload) is not dict
            or set(fault.payload) != {"message"}
            or not isinstance(fault.payload["message"], str)
        ):
            raise ValueError("unsupported history-refusal Engine profile fault")
        return fault

    def _observation_state(self, generation: EngineGeneration) -> dict[str, JsonValue]:
        state = super()._observation_state(generation)
        state.update(
            {
                "terminal_deliveries": self.terminal_deliveries,
                "terminal_refusals": self.terminal_refusals,
            }
        )
        return state

    def _history(self, context: ScenarioContext) -> HistoryStore:
        del context
        return RefusingJsonlHistoryStore(self.history_path, self._terminal_refused)

    def _terminal_ready(self) -> None:
        self.terminal_deliveries += 1

    def _terminal_refused(self) -> None:
        self.terminal_refusals += 1

    def _configure_faults(
        self, generation: EngineGeneration, context: ScenarioContext
    ) -> tuple[tuple[type[Exception], str], ...]:
        expected = []
        for fault in context.faults("activity_terminal_frozen"):
            if fault.name != "history.refuse" or fault.disposition != FaultDisposition.REFUSE.value:
                raise ValueError(f"unsupported history-refusal Engine profile fault {fault.name!r}")
            if type(fault.payload) is not dict or set(fault.payload) != {"message"}:
                raise ValueError("history.refuse requires an exact message payload")
            message = fault.payload["message"]
            if not isinstance(message, str):
                raise ValueError("history.refuse message must be a string")
            history = generation.history
            if not isinstance(history, RefusingJsonlHistoryStore):
                raise TypeError("history-refusal Engine profile requires its faulting History adapter")
            history.refuse_terminal(message)
            expected.append((OSError, message))
        return tuple(expected)


class HistoryAckLossEngineProfile(EngineProfile):
    """Public-Engine profile with one terminal append accepted before its acknowledgement is lost."""

    identity = HISTORY_ACK_LOSS_PROFILE_IDENTITY
    observation_fields = {
        "activity-requested": EngineProfile.observation_fields["activity-requested"],
        "engine.accepted-commit-authority": (
            "record_types",
            "terminal_ack_losses",
            "terminal_deliveries",
        ),
        "terminal-ack-lost": (
            "bridge",
            "frontier",
            "record_types",
            "status",
            "terminal_ack_losses",
            "terminal_deliveries",
        ),
        "terminal-recovered": EngineProfile.observation_fields["terminal"],
    }

    def __init__(self, history_path: Path):
        super().__init__(history_path)
        self.terminal_deliveries = 0
        self.terminal_ack_losses = 0

    def validate_fault(self, fault: Fault) -> Fault:
        if (
            fault.name != "history.lose-ack"
            or fault.target != "activity_terminal_frozen"
            or fault.disposition != FaultDisposition.RAISE.value
            or type(fault.payload) is not dict
            or set(fault.payload) != {"message"}
            or not isinstance(fault.payload["message"], str)
        ):
            raise ValueError("unsupported History acknowledgement-loss Engine profile fault")
        return fault

    def _observation_state(self, generation: EngineGeneration) -> dict[str, JsonValue]:
        state = super()._observation_state(generation)
        state.update(
            {
                "terminal_ack_losses": self.terminal_ack_losses,
                "terminal_deliveries": self.terminal_deliveries,
            }
        )
        return state

    def _history(self, context: ScenarioContext) -> HistoryStore:
        del context
        return AckLosingJsonlHistoryStore(self.history_path, self._terminal_ack_lost)

    def _terminal_ready(self) -> None:
        self.terminal_deliveries += 1

    def _terminal_ack_lost(self) -> None:
        self.terminal_ack_losses += 1

    def _configure_faults(
        self, generation: EngineGeneration, context: ScenarioContext
    ) -> tuple[tuple[type[Exception], str], ...]:
        expected = []
        for fault in context.faults("activity_terminal_frozen"):
            if fault.name != "history.lose-ack" or fault.disposition != FaultDisposition.RAISE.value:
                raise ValueError(f"unsupported History acknowledgement-loss fault {fault.name!r}")
            if type(fault.payload) is not dict or set(fault.payload) != {"message"}:
                raise ValueError("history.lose-ack requires an exact message payload")
            message = fault.payload["message"]
            if not isinstance(message, str):
                raise ValueError("history.lose-ack message must be a string")
            history = generation.history
            if not isinstance(history, AckLosingJsonlHistoryStore):
                raise TypeError("History acknowledgement-loss profile requires its faulting adapter")
            history.lose_terminal_ack(message)
            expected.append((OSError, message))
        return tuple(expected)


class EngineHistoryChecker:
    """Independent ordering checker over detached canonical record names."""

    identity = CHECKER_IDENTITY
    request = ObservationRequest(name="engine.safety", payload={})

    def check(self, observation: Observation) -> CheckResult:
        value = cast(dict[str, JsonValue], observation.value)
        records = cast(list[JsonValue], value["record_types"])
        requested = [index for index, name in enumerate(records) if name == ActivityRequested.__name__]
        completed = [index for index, name in enumerate(records) if name == ActivityCompleted.__name__]
        projected = [index for index, name in enumerate(records) if name == FiringCompleted.__name__]
        passed = len(requested) <= 1 and len(completed) <= 1
        if projected:
            passed = passed and len(completed) == 1 and completed[0] < projected[0]
        return CheckResult(
            passed=passed,
            detail={
                "activity_completed": len(completed),
                "activity_requested": len(requested),
                "firing_completed": len(projected),
            },
        )


class CommitAuthorityChecker:
    """Independent terminal bound derived from authored external-world facts."""

    identity = COMMIT_AUTHORITY_CHECKER_IDENTITY
    request = ObservationRequest(name="engine.commit-authority", payload={})

    def check(self, observation: Observation) -> CheckResult:
        value = cast(dict[str, JsonValue], observation.value)
        records = cast(list[JsonValue], value["record_types"])
        deliveries = cast(int, value["terminal_deliveries"])
        refusals = cast(int, value["terminal_refusals"])
        completed = records.count(ActivityCompleted.__name__) + records.count(ActivityFailed.__name__)
        projected = records.count(FiringCompleted.__name__)
        accepted_limit = deliveries - refusals
        passed = 0 <= refusals <= deliveries and completed <= accepted_limit and projected <= completed <= 1
        return CheckResult(
            passed=passed,
            detail={
                "accepted_terminal_limit": accepted_limit,
                "activity_terminals": completed,
                "authored_terminal_deliveries": deliveries,
                "firing_completed": projected,
                "history_refusals": refusals,
            },
        )


class AcceptedCommitAuthorityChecker:
    """Treat the adapter's post-commit callback as independent durable acceptance evidence."""

    identity = ACCEPTED_COMMIT_AUTHORITY_CHECKER_IDENTITY
    request = ObservationRequest(name="engine.accepted-commit-authority", payload={})

    def check(self, observation: Observation) -> CheckResult:
        value = cast(dict[str, JsonValue], observation.value)
        records = cast(list[JsonValue], value["record_types"])
        deliveries = cast(int, value["terminal_deliveries"])
        ack_losses = cast(int, value["terminal_ack_losses"])
        terminals = records.count(ActivityCompleted.__name__) + records.count(ActivityFailed.__name__)
        projected = records.count(FiringCompleted.__name__)
        passed = 0 <= ack_losses <= deliveries <= 1 and ack_losses <= terminals <= deliveries and projected <= terminals
        return CheckResult(
            passed=passed,
            detail={
                "durable_activity_terminals": terminals,
                "firing_completed": projected,
                "terminal_ack_losses": ack_losses,
                "terminal_deliveries": deliveries,
            },
        )


class TerminalRefusalChecker:
    """Deliberate independent failure used to prove failed-attempt retention."""

    identity = TERMINAL_REFUSAL_CHECKER_IDENTITY
    request = ObservationRequest(name="engine.safety", payload={})

    def check(self, observation: Observation) -> CheckResult:
        value = cast(dict[str, JsonValue], observation.value)
        records = cast(list[JsonValue], value["record_types"])
        terminal = FiringCompleted.__name__ in records
        return CheckResult(passed=not terminal, detail={"terminal_firing": terminal})


def execute_projection_story(history_path: Path, *, seed: int | None = None) -> tuple[World, EngineProfile, Timeline]:
    """Author the vertical scenario as an imperative debugger-like pytest story."""

    profile = EngineProfile(history_path)
    world = World(profile, WORLD_BUDGET, checkers=(EngineHistoryChecker(),), seed=seed)
    timeline = world.timeline()

    requested = timeline.run_until(
        "activity-requested",
        lambda observation: cast(dict[str, JsonValue], observation.value)["pending"] == [1],
    )
    assert cast(dict[str, JsonValue], requested.value)["frontier"] == 6

    result = 3
    fault_message = "dst projection fault"
    if seed is not None:
        result = (3, 5, 8)[world.choices.index(ChoiceAuthority.WORKLOAD, 3)]
        fault_label = ("projection", "bridge")[world.choices.index(ChoiceAuthority.FAULT, 2)]
        identifier = world.choices.identifier("scenario")
        observations = ["activity-requested", "projection-refused"]
        if world.choices.index(ChoiceAuthority.EVENT_ORDER, 2):
            observations.reverse()
        for name in observations:
            timeline.observe(name)
        fault_message = f"dst {fault_label} fault {identifier}"

    timeline.activate_fault(
        "projection.raise",
        "activity_terminal_frozen",
        disposition=FaultDisposition.RAISE,
        payload={"message": fault_message},
    )
    timeline.command("engine.complete", {"occurrence": 1, "result": {"value": result}})
    refused = timeline.run_until(
        "projection-refused",
        lambda observation: cast(dict[str, JsonValue], observation.value)["status"] == "poisoned",
    )
    assert cast(dict[str, JsonValue], refused.value)["frontier"] == 7

    stale = timeline
    timeline.crash("activity_terminal_frozen")
    world.restart()
    timeline = world.timeline()
    timeline.begin_fair()
    terminal = timeline.run_until(
        "terminal",
        lambda observation: cast(dict[str, JsonValue], observation.value)["status"] == "terminated",
    )
    terminal_value = cast(dict[str, JsonValue], terminal.value)
    assert terminal_value["frontier"] == 9
    assert terminal_value["marking"] == [{"place": "done", "tokens": [{"color": "Done", "data": {"value": result}}]}]
    timeline.finish(Disposition.CONVERGED)
    return world, profile, stale


def build_projection_artifact(history_path: Path) -> ScenarioArtifactV3:
    world, _, _ = execute_projection_story(history_path)
    try:
        artifact = world.artifact(SCENARIO_ID)
        assert isinstance(artifact, ScenarioArtifactV3)
        return artifact
    finally:
        world.close()


def build_seeded_projection_artifact(history_path: Path) -> ScenarioArtifactV3:
    world, _, _ = execute_projection_story(history_path, seed=SCENARIO_SEED)
    try:
        artifact = world.artifact(SEEDED_SCENARIO_ID)
        assert isinstance(artifact, ScenarioArtifactV3)
        return artifact
    finally:
        world.close()


def execute_resource_bounded_story(history_path: Path) -> tuple[World, ResourceBoundedEngineProfile]:
    """Bound retained resources across abrupt public-Engine reconstruction."""

    profile = ResourceBoundedEngineProfile(history_path)
    world = World(profile, resource_world_budget(), checkers=(EngineHistoryChecker(),))
    timeline = world.timeline()
    requested = timeline.run_until(
        "activity-requested",
        lambda observation: cast(dict[str, JsonValue], observation.value)["pending"] == [1],
    )
    assert cast(dict[str, JsonValue], requested.value)["frontier"] == 6

    timeline.crash("activity_request_durable")
    world.restart()
    timeline = world.timeline()
    recovered = timeline.run_until(
        "activity-requested",
        lambda observation: cast(dict[str, JsonValue], observation.value)["pending"] == [1],
    )
    assert cast(dict[str, JsonValue], recovered.value)["frontier"] == 6

    timeline.command("engine.complete", {"occurrence": 1, "result": {"value": 3}})
    timeline.begin_fair()
    terminal = timeline.run_until(
        "terminal",
        lambda observation: cast(dict[str, JsonValue], observation.value)["status"] == "terminated",
    )
    assert cast(dict[str, JsonValue], terminal.value)["frontier"] == 9
    timeline.finish(Disposition.CONVERGED)
    return world, profile


def build_resource_bounded_artifact(history_path: Path) -> ScenarioArtifact:
    world, _ = execute_resource_bounded_story(history_path)
    try:
        artifact = world.artifact(RESOURCE_SCENARIO_ID)
        assert isinstance(artifact, ScenarioArtifact)
        return artifact
    finally:
        world.close()


def build_resource_budget_failure_artifact(history_path: Path) -> ScenarioArtifact:
    profile = ResourceBoundedEngineProfile(history_path)
    world = World(
        profile,
        resource_world_budget(history_records=5),
        checkers=(EngineHistoryChecker(),),
    )
    try:
        try:
            world.timeline().run_until(
                "activity-requested",
                lambda observation: cast(dict[str, JsonValue], observation.value)["pending"] == [1],
            )
        except BudgetExhausted:
            pass
        else:
            raise AssertionError("the deliberate History-record resource budget did not exhaust")
        artifact = world.artifact(RESOURCE_BUDGET_FAILURE_SCENARIO_ID)
        assert isinstance(artifact, ScenarioArtifact)
        return artifact
    finally:
        world.close()


def execute_history_refusal_story(
    history_path: Path,
) -> tuple[World, HistoryRefusalEngineProfile, Timeline]:
    """Refuse one terminal commit, crash, reload, redeliver, and converge."""

    profile = HistoryRefusalEngineProfile(history_path)
    world = World(profile, WORLD_BUDGET, checkers=(CommitAuthorityChecker(),))
    timeline = world.timeline()

    requested = timeline.run_until(
        "activity-requested",
        lambda observation: cast(dict[str, JsonValue], observation.value)["pending"] == [1],
    )
    requested_value = cast(dict[str, JsonValue], requested.value)
    assert requested_value["frontier"] == 6
    requested_invocations = requested_value["pending_invocations"]
    assert requested_invocations == [
        {
            "activity": "calculate",
            "correlation": "occurrence-1",
            "idempotency": "occurrence-1",
            "input": 3,
            "occurrence": 1,
            "policy": {
                "attempts": 1,
                "coefficient": 2,
                "heartbeat_timeout": 30,
                "initial_interval": 0,
                "jitter": 0,
                "max_interval": 60,
                "schedule_to_close": None,
                "start_to_close": None,
            },
        }
    ]

    timeline.activate_fault(
        "history.refuse",
        "activity_terminal_frozen",
        disposition=FaultDisposition.REFUSE,
        payload={"message": "dst terminal history refused"},
    )
    timeline.command("engine.complete", {"occurrence": 1, "result": {"value": 3}})
    refused = timeline.run_until(
        "semantic-batch-refused",
        lambda observation: cast(dict[str, JsonValue], observation.value)["status"] == "poisoned",
    )
    refused_value = cast(dict[str, JsonValue], refused.value)
    assert refused_value["frontier"] == 6
    assert refused_value["terminal_deliveries"] == refused_value["terminal_refusals"] == 1
    assert ActivityCompleted.__name__ not in cast(list[JsonValue], refused_value["record_types"])
    assert cast(dict[str, JsonValue], refused_value["bridge"])["projected"] == 0

    stale = timeline
    timeline.crash("semantic_batch_refused")
    world.restart()
    timeline = world.timeline()
    recovered = timeline.run_until(
        "recovered-request",
        lambda observation: cast(dict[str, JsonValue], observation.value)["pending"] == [1],
    )
    recovered_value = cast(dict[str, JsonValue], recovered.value)
    assert recovered_value["frontier"] == 6
    assert cast(dict[str, JsonValue], recovered_value["bridge"]) == {"prepared": 0, "projected": 0}
    assert recovered_value["pending_invocations"] == requested_invocations

    timeline.command("engine.complete", {"occurrence": 1, "result": {"value": 3}})
    timeline.begin_fair()
    terminal = timeline.run_until(
        "terminal",
        lambda observation: cast(dict[str, JsonValue], observation.value)["status"] == "terminated",
    )
    terminal_value = cast(dict[str, JsonValue], terminal.value)
    assert terminal_value["frontier"] == 9
    assert cast(dict[str, JsonValue], terminal_value["bridge"]) == {"prepared": 0, "projected": 1}
    assert terminal_value["marking"] == [{"place": "done", "tokens": [{"color": "Done", "data": {"value": 3}}]}]
    timeline.finish(Disposition.CONVERGED)
    return world, profile, stale


def build_history_refusal_artifact(history_path: Path) -> ScenarioArtifactV3:
    world, _, _ = execute_history_refusal_story(history_path)
    try:
        artifact = world.artifact(HISTORY_REFUSAL_SCENARIO_ID)
        assert isinstance(artifact, ScenarioArtifactV3)
        return artifact
    finally:
        world.close()


def execute_history_ack_loss_story(
    history_path: Path,
) -> tuple[World, HistoryAckLossEngineProfile]:
    """Lose a post-commit acknowledgement, crash, reload, and project the durable terminal."""

    profile = HistoryAckLossEngineProfile(history_path)
    world = World(profile, WORLD_BUDGET, checkers=(AcceptedCommitAuthorityChecker(),))
    timeline = world.timeline()

    requested = timeline.run_until(
        "activity-requested",
        lambda observation: cast(dict[str, JsonValue], observation.value)["pending"] == [1],
    )
    assert cast(dict[str, JsonValue], requested.value)["frontier"] == 6

    timeline.activate_fault(
        "history.lose-ack",
        "activity_terminal_frozen",
        disposition=FaultDisposition.RAISE,
        payload={"message": "dst terminal acknowledgement lost"},
    )
    timeline.command("engine.complete", {"occurrence": 1, "result": {"value": 3}})
    lost = timeline.run_until(
        "terminal-ack-lost",
        lambda observation: cast(dict[str, JsonValue], observation.value)["status"] == "poisoned",
    )
    lost_value = cast(dict[str, JsonValue], lost.value)
    assert lost_value["frontier"] == 7
    assert lost_value["terminal_ack_losses"] == lost_value["terminal_deliveries"] == 1
    assert cast(list[JsonValue], lost_value["record_types"]).count(ActivityCompleted.__name__) == 1
    assert lost_value["bridge"] == {"prepared": 1, "projected": 0}

    timeline.crash("terminal_commit_accepted_ack_lost")
    world.restart()
    timeline = world.timeline()
    timeline.begin_fair()
    terminal = timeline.run_until(
        "terminal-recovered",
        lambda observation: cast(dict[str, JsonValue], observation.value)["status"] == "terminated",
    )
    terminal_value = cast(dict[str, JsonValue], terminal.value)
    assert terminal_value["frontier"] == 9
    assert terminal_value["bridge"] == {"prepared": 0, "projected": 1}
    assert terminal_value["marking"] == [{"place": "done", "tokens": [{"color": "Done", "data": {"value": 3}}]}]
    timeline.finish(Disposition.CONVERGED)
    return world, profile


def build_history_ack_loss_artifact(history_path: Path) -> ScenarioArtifactV3:
    world, _ = execute_history_ack_loss_story(history_path)
    try:
        artifact = world.artifact(HISTORY_ACK_LOSS_SCENARIO_ID)
        assert isinstance(artifact, ScenarioArtifactV3)
        return artifact
    finally:
        world.close()


def build_invariant_failure_artifact(history_path: Path) -> ScenarioArtifactV3:
    profile = EngineProfile(history_path)
    world = World(
        profile,
        WORLD_BUDGET,
        checkers=(EngineHistoryChecker(), TerminalRefusalChecker()),
    )
    timeline = world.timeline()
    try:
        timeline.run_until(
            "activity-requested",
            lambda observation: cast(dict[str, JsonValue], observation.value)["pending"] == [1],
        )
        timeline.command("engine.complete", {"occurrence": 1, "result": {"value": 3}})
        try:
            world.step()
        except InvariantViolation:
            pass
        else:
            raise AssertionError("the deliberate terminal checker did not reject the Engine boundary")
        artifact = world.artifact(INVARIANT_FAILURE_SCENARIO_ID)
        assert isinstance(artifact, ScenarioArtifactV3)
        return artifact
    finally:
        world.close()


def build_budget_failure_artifact(history_path: Path) -> ScenarioArtifactV3:
    profile = EngineProfile(history_path)
    budget = Budget(
        actions=1,
        queued_commands=8,
        timer_advances=0,
        logical_instant=0,
        reloads=0,
        predicate_polls=1,
        artifact_bytes=262_144,
    )
    world = World(profile, budget)
    timeline = world.timeline()
    try:
        world.step()
        try:
            timeline.observe("activity-requested")
        except BudgetExhausted:
            pass
        else:
            raise AssertionError("the deliberate action budget did not exhaust")
        artifact = world.artifact(BUDGET_FAILURE_SCENARIO_ID)
        assert isinstance(artifact, ScenarioArtifactV3)
        return artifact
    finally:
        world.close()
