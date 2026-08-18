"""Public-Engine DST profiles over production LocalDispatch custody."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import ClassVar, cast

from pydantic import JsonValue

from petrus.engine import Engine
from petrus.impetus.history import ActivityCompleted, ActivityFailed, ActivityRequested, FiringCompleted, FiringFailed
from petrus.impetus.history_store import JsonlHistoryStore
from petrus.impetus.petrinet import Arc, Marking, Net, NetPath, Place, Token, Transition
from petrus.motus.activity import ActivityFailure, ActivityInvocation, ExecutionPolicy
from petrus.motus.dispatch import ActivityAttempt, LocalDispatch, LocalWorkerDispatch
from petrus.testing.dst import (
    ActionDisposition,
    ApplyResult,
    Budget,
    CheckResult,
    CheckerIdentity,
    Command,
    Disposition,
    Fault,
    GenerationStart,
    Observation,
    ObservationRequest,
    ProfileIdentity,
    ScenarioArtifactV3,
    ScenarioContext,
    ScheduledCommand,
    World,
    digest_json,
)

INPUT = NetPath("input")
DONE = NetPath("done")
WORK = NetPath("work")
INSTANCE_ID = "dst-world-retry-recovery"
SCENARIO_ID = "retry-crash-exhaustion-world-v3"
TERMINAL_SCENARIO_ID = "local-terminal-redelivery-world-v3"

PROFILE_DEFINITION = {
    "commands": {
        "engine.drive": [],
        "worker.claim": [],
        "worker.fail": ["attempt", "error"],
    },
    "dispatch": "local",
    "instance": INSTANCE_ID,
    "policy": {"attempts": 2, "initial_interval": 0},
    "observations": [
        "activity-requested",
        "engine.retry-authority",
        "retry-claimed",
        "retry-exhausted",
        "retry-recovered",
    ],
}
PROFILE_IDENTITY = ProfileIdentity(
    name="petrus.engine.local-dispatch-retry",
    version=1,
    digest=digest_json(PROFILE_DEFINITION),
)
CHECKER_IDENTITY = CheckerIdentity(
    name="petrus.engine.retry-authority",
    version=1,
    digest=digest_json(
        {
            "properties": [
                "retry claims preserve one logical invocation across exact epochs",
                "a terminal Activity failure requires exhaustion of both authored attempts",
                "retry exhaustion produces no business projection",
            ]
        }
    ),
)
TERMINAL_PROFILE_IDENTITY = ProfileIdentity(
    name="petrus.engine.local-dispatch-terminal",
    version=1,
    digest=digest_json(
        {
            "commands": {
                "engine.drive": [],
                "worker.claim": [],
                "worker.complete": ["result"],
            },
            "dispatch": "local",
            "instance": INSTANCE_ID,
            "policy": {"attempts": 2, "initial_interval": 0},
            "observations": [
                "engine.local-terminal-authority",
                "local-terminal-converged",
                "local-terminal-durable",
                "local-terminal-requested",
            ],
        }
    ),
)
TERMINAL_CHECKER_IDENTITY = CheckerIdentity(
    name="petrus.engine.local-terminal-authority",
    version=1,
    digest=digest_json(
        {
            "properties": [
                "the first accepted provider result remains authoritative",
                "an exact provider report is idempotent and a conflicting report is refused",
                "one durable provider result produces at most one canonical terminal and projection",
            ]
        }
    ),
)
WORLD_BUDGET = Budget(
    actions=40,
    queued_commands=8,
    timer_advances=0,
    logical_instant=0,
    reloads=1,
    predicate_polls=16,
    artifact_bytes=262_144,
)


def application_net() -> Net:
    return Net(
        places=[Place(INPUT), Place(DONE)],
        transitions=[Transition(WORK, handler="bridge")],
        arcs=[Arc(INPUT, WORK), Arc(WORK, DONE)],
        name="dst-world-retry-recovery",
    )


class RetryBridge:
    def __init__(self) -> None:
        self.prepared = 0
        self.projected = 0

    def prepare(self, binding) -> ActivityInvocation:
        self.prepared += 1
        return ActivityInvocation(
            "work",
            input=binding.tokens[0].data,
            policy=ExecutionPolicy(attempts=2, initial_interval=0),
        )

    def project(self, binding, result):
        del binding
        self.projected += 1
        return {DONE: (Token("Done", result),)}


class WorldClock:
    def __init__(self, context: ScenarioContext):
        self.context = context

    def now(self) -> int:
        return self.context.now()

    def observe(self, instant: int) -> int | None:
        return self.context.now() if self.context.now() >= instant else None


@dataclass
class RetryGeneration:
    engine: Engine
    history: JsonlHistoryStore
    dispatch: LocalDispatch
    bridge: RetryBridge
    worker: LocalWorkerDispatch | None = None
    attempt: ActivityAttempt | None = None
    drives: int = 0
    poisoned: bool = False


class RetryEngineProfile:
    """Opaque public Engine plus durable LocalDispatch retry custody."""

    identity = PROFILE_IDENTITY
    _debug_fields = (
        "attempts",
        "bridge",
        "drives",
        "drops",
        "failures_delivered",
        "frontier",
        "in_flight",
        "marking",
        "record_types",
        "status",
    )
    observation_fields: ClassVar[dict[str, tuple[str, ...]]] = {
        "activity-requested": _debug_fields,
        "engine.retry-authority": (
            "attempts",
            "failures_delivered",
            "record_types",
        ),
        "retry-claimed": _debug_fields,
        "retry-exhausted": _debug_fields,
        "retry-recovered": _debug_fields,
    }

    def __init__(self, history_path: Path, dispatch_path: Path):
        self.history_path = history_path
        self.dispatch_path = dispatch_path
        self.attempts: list[dict[str, JsonValue]] = []
        self.failures_delivered = 0
        self.drops = 0
        self.closes = 0

    def validate(self, command: Command) -> Command:
        payload = command.payload
        if command.name in {"engine.drive", "worker.claim"}:
            if payload != {}:
                raise ValueError(f"{command.name} payload must be an empty object")
            return command
        if command.name == "worker.fail":
            if type(payload) is not dict or set(payload) != {"attempt", "error"}:
                raise ValueError("worker.fail requires exact attempt and error fields")
            attempt = payload["attempt"]
            if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt not in {1, 2}:
                raise ValueError("worker.fail attempt must be 1 or 2")
            if not isinstance(payload["error"], str) or not payload["error"]:
                raise ValueError("worker.fail error must be a non-empty string")
            return command
        raise ValueError(f"unknown retry Engine profile command {command.name!r}")

    def validate_fault(self, fault: Fault) -> Fault:
        raise ValueError(f"retry Engine profile has no fault named {fault.name!r}")

    def create(self, context: ScenarioContext) -> GenerationStart[RetryGeneration]:
        generation = self._generation(context, load=False)
        return GenerationStart(generation, (self._scheduled(context),))

    def load(self, context: ScenarioContext) -> GenerationStart[RetryGeneration]:
        generation = self._generation(context, load=True)
        return GenerationStart(generation, (self._scheduled(context),))

    def apply(
        self,
        generation: RetryGeneration,
        command: Command,
        context: ScenarioContext,
    ) -> ApplyResult:
        payload = cast(dict[str, JsonValue], command.payload)
        if command.name == "worker.claim":
            if generation.attempt is not None:
                raise RuntimeError("retry generation already holds an Activity attempt")
            worker = generation.dispatch.worker(worker_id=f"dst-worker-{len(self.attempts) + 1}")
            attempt = worker.claim()
            if attempt is None:
                raise RuntimeError("LocalDispatch has no eligible Activity retry")
            generation.worker = worker
            generation.attempt = attempt
            detached = self._attempt_view(attempt)
            self.attempts.append(detached)
            return self._applied(generation, {"attempt": detached})

        if command.name == "worker.fail":
            worker = generation.worker
            attempt = generation.attempt
            if worker is None or attempt is None:
                raise RuntimeError("worker.fail requires one claimed Activity attempt")
            expected_epoch = cast(int, payload["attempt"])
            if int(attempt.epoch) != expected_epoch:
                raise ValueError(f"worker.fail expected epoch {expected_epoch}, found {attempt.epoch}")
            worker.fail(
                attempt,
                ActivityFailure(
                    cast(str, payload["error"]),
                    kind="Unavailable",
                    details={"attempt": expected_epoch},
                    retryable=True,
                    retry_after=0,
                ),
            )
            worker.close()
            generation.worker = None
            generation.attempt = None
            self.failures_delivered += 1
            scheduled = [self._scheduled(context)] if expected_epoch == 2 else []
            return self._applied(generation, {"failed_epoch": expected_epoch}, scheduled=scheduled)

        generation.drives += 1
        try:
            outcome = generation.engine.advance()
        except RuntimeError as error:
            records = generation.history.records
            if (
                len(records) < 2
                or not isinstance(records[-2], ActivityFailed)
                or not isinstance(records[-1], FiringFailed)
            ):
                raise
            generation.poisoned = True
            return ApplyResult(
                disposition=ActionDisposition.QUARANTINED.value,
                value={"error": str(error), "frontier": len(records)},
                scheduled=[],
            )

        current = generation.engine.snapshot()["current"]
        assert isinstance(current, dict)
        status = current["status"]
        records = generation.history.records
        activity_pending = any(isinstance(record, ActivityRequested) for record in records) and not any(
            isinstance(record, ActivityFailed) for record in records
        )
        scheduled = []
        if status not in {"completed", "terminated"} and outcome.ready and not activity_pending:
            scheduled.append(self._scheduled(context))
        return ApplyResult(
            disposition=ActionDisposition.APPLIED.value,
            value={
                "firings": [str(firing.transition) for firing in outcome.firings],
                "frontier": len(records),
                "ready": outcome.ready,
                "status": status,
                "waiting": outcome.waiting,
            },
            scheduled=scheduled,
        )

    def observe(
        self,
        generation: RetryGeneration,
        request: ObservationRequest,
        context: ScenarioContext,
    ) -> JsonValue:
        del context
        if request.name not in self.observation_fields:
            raise ValueError(f"unknown retry Engine profile observation {request.name!r}")
        if request.payload not in (None, {}):
            raise ValueError("retry Engine profile observations do not accept parameters")
        state = self._observation_state(generation)
        return {field: state[field] for field in self.observation_fields[request.name]}

    def drop(self, generation: RetryGeneration) -> None:
        self.drops += 1
        if generation.worker is not None:
            generation.worker.close()
        generation.engine.close()

    def close(self, generation: RetryGeneration) -> None:
        self.closes += 1
        if generation.worker is not None:
            generation.worker.close()
        generation.engine.close()

    def _generation(self, context: ScenarioContext, *, load: bool) -> RetryGeneration:
        history = JsonlHistoryStore(self.history_path)
        dispatch = LocalDispatch(self.dispatch_path, instance=INSTANCE_ID)
        bridge = RetryBridge()
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
                marking=Marking({INPUT: (Token("Input", 3),)}),
                handlers={"bridge": bridge},
                clock=WorldClock(context),
            )
        return RetryGeneration(engine, history, dispatch, bridge)

    def _observation_state(self, generation: RetryGeneration) -> dict[str, JsonValue]:
        records = generation.history.records
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
        return cast(
            dict[str, JsonValue],
            {
                "attempts": self.attempts,
                "bridge": {
                    "prepared": generation.bridge.prepared,
                    "projected": generation.bridge.projected,
                },
                "drives": generation.drives,
                "drops": self.drops,
                "failures_delivered": self.failures_delivered,
                "frontier": len(records),
                "in_flight": in_flight,
                "marking": marking,
                "record_types": [type(record).__name__ for record in records],
                "status": status,
            },
        )

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
                "instance": attempt.instance,
                "policy": asdict(invocation.policy),
                "queue": attempt.queue,
            },
        )

    def _applied(
        self,
        generation: RetryGeneration,
        value: dict[str, JsonValue],
        *,
        scheduled: list[ScheduledCommand] | None = None,
    ) -> ApplyResult:
        return ApplyResult(
            disposition=ActionDisposition.APPLIED.value,
            value={"frontier": len(generation.history), **value},
            scheduled=[] if scheduled is None else scheduled,
        )

    def _scheduled(self, context: ScenarioContext) -> ScheduledCommand:
        return ScheduledCommand(
            instant=context.now(),
            command=Command(profile=self.identity, name="engine.drive", payload={}),
        )


class TerminalEngineProfile(RetryEngineProfile):
    """Public Engine plus LocalDispatch terminal durability and redelivery."""

    identity = TERMINAL_PROFILE_IDENTITY
    _terminal_debug_fields = (
        "accepted_results",
        "attempts",
        "bridge",
        "drives",
        "drops",
        "frontier",
        "in_flight",
        "marking",
        "record_types",
        "status",
        "terminal_reports",
    )
    observation_fields: ClassVar[dict[str, tuple[str, ...]]] = {
        "engine.local-terminal-authority": (
            "accepted_results",
            "attempts",
            "bridge",
            "marking",
            "record_types",
            "status",
            "terminal_reports",
        ),
        "local-terminal-converged": _terminal_debug_fields,
        "local-terminal-durable": _terminal_debug_fields,
        "local-terminal-requested": _terminal_debug_fields,
    }

    def __init__(self, history_path: Path, dispatch_path: Path):
        super().__init__(history_path, dispatch_path)
        self.accepted_results: list[JsonValue] = []
        self.terminal_reports: list[dict[str, JsonValue]] = []

    def validate(self, command: Command) -> Command:
        if command.name in {"engine.drive", "worker.claim"}:
            if command.payload != {}:
                raise ValueError(f"{command.name} payload must be an empty object")
            return command
        if command.name == "worker.complete":
            if type(command.payload) is not dict or set(command.payload) != {"result"}:
                raise ValueError("worker.complete requires one exact result field")
            return command
        raise ValueError(f"unknown terminal Engine profile command {command.name!r}")

    def validate_fault(self, fault: Fault) -> Fault:
        raise ValueError(f"terminal Engine profile has no fault named {fault.name!r}")

    def apply(
        self,
        generation: RetryGeneration,
        command: Command,
        context: ScenarioContext,
    ) -> ApplyResult:
        if command.name != "worker.complete":
            return super().apply(generation, command, context)

        worker = generation.worker
        attempt = generation.attempt
        if worker is None or attempt is None:
            raise RuntimeError("worker.complete requires one claimed Activity attempt")
        payload = cast(dict[str, JsonValue], command.payload)
        result = payload["result"]
        try:
            worker.complete(attempt, result)
        except ValueError as error:
            if "conflicting terminal report" not in str(error):
                raise
            disposition = ActionDisposition.REFUSED_EXPECTED
        else:
            if not self.accepted_results:
                self.accepted_results.append(result)
                disposition = ActionDisposition.APPLIED
            elif result == self.accepted_results[0]:
                disposition = ActionDisposition.IDEMPOTENT
            else:
                raise AssertionError("LocalDispatch accepted a conflicting terminal report")
        report = cast(dict[str, JsonValue], {"disposition": disposition.value, "result": result})
        self.terminal_reports.append(report)
        return ApplyResult(
            disposition=disposition.value,
            value={"frontier": len(generation.history), "report": report},
            scheduled=[],
        )

    def _observation_state(self, generation: RetryGeneration) -> dict[str, JsonValue]:
        state = super()._observation_state(generation)
        state["accepted_results"] = self.accepted_results
        state["terminal_reports"] = self.terminal_reports
        return state


class RetryAuthorityChecker:
    """Independent retry and terminal bounds from authored provider facts."""

    identity = CHECKER_IDENTITY
    request = ObservationRequest(name="engine.retry-authority", payload={})

    def check(self, observation: Observation) -> CheckResult:
        value = cast(dict[str, JsonValue], observation.value)
        attempts = cast(list[dict[str, JsonValue]], value["attempts"])
        failures = cast(int, value["failures_delivered"])
        records = cast(list[JsonValue], value["record_types"])
        requested = records.count(ActivityRequested.__name__)
        activity_failed = records.count(ActivityFailed.__name__)
        firing_failed = records.count(FiringFailed.__name__)
        projected = records.count(FiringCompleted.__name__)
        expected_epochs = list(range(1, len(attempts) + 1))
        epochs = [attempt["epoch"] for attempt in attempts]
        logical_invocations = [
            {name: field for name, field in attempt.items() if name != "epoch"} for attempt in attempts
        ]
        invocation_stable = not logical_invocations or all(
            invocation == logical_invocations[0] for invocation in logical_invocations
        )
        accepted_terminal_limit = 1 if failures >= 2 else 0
        passed = (
            requested <= 1
            and len(attempts) <= 2
            and epochs == expected_epochs
            and invocation_stable
            and 0 <= failures <= len(attempts)
            and activity_failed <= accepted_terminal_limit
            and firing_failed == activity_failed
            and projected == 0
        )
        return CheckResult(
            passed=passed,
            detail={
                "accepted_terminal_limit": accepted_terminal_limit,
                "activity_failed": activity_failed,
                "activity_requested": requested,
                "attempt_epochs": epochs,
                "failures_delivered": failures,
                "firing_completed": projected,
                "firing_failed": firing_failed,
                "invocation_stable": invocation_stable,
            },
        )


class TerminalAuthorityChecker:
    """Judge canonical terminal projection from authored provider reports."""

    identity = TERMINAL_CHECKER_IDENTITY
    request = ObservationRequest(name="engine.local-terminal-authority", payload={})

    def check(self, observation: Observation) -> CheckResult:
        value = cast(dict[str, JsonValue], observation.value)
        reports = cast(list[dict[str, JsonValue]], value["terminal_reports"])
        accepted_results = cast(list[JsonValue], value["accepted_results"])
        attempts = cast(list[dict[str, JsonValue]], value["attempts"])
        records = cast(list[JsonValue], value["record_types"])
        bridge = cast(dict[str, JsonValue], value["bridge"])
        marking = cast(list[dict[str, JsonValue]], value["marking"])

        authority: list[JsonValue] = []
        expected_dispositions: list[str] = []
        for report in reports:
            result = report["result"]
            if not authority:
                authority.append(result)
                expected_dispositions.append(ActionDisposition.APPLIED.value)
            elif result == authority[0]:
                expected_dispositions.append(ActionDisposition.IDEMPOTENT.value)
            else:
                expected_dispositions.append(ActionDisposition.REFUSED_EXPECTED.value)

        reported_dispositions = [cast(str, report["disposition"]) for report in reports]
        requested = records.count(ActivityRequested.__name__)
        completed = records.count(ActivityCompleted.__name__)
        firing_completed = records.count(FiringCompleted.__name__)
        activity_failed = records.count(ActivityFailed.__name__)
        firing_failed = records.count(FiringFailed.__name__)
        attempt_epochs = [attempt["epoch"] for attempt in attempts]
        projected_results = [
            token["data"]
            for place in marking
            if place["place"] == str(DONE)
            for token in cast(list[dict[str, JsonValue]], place["tokens"])
        ]
        terminal_limit = 1 if authority else 0
        expected_projection = authority if firing_completed else []
        passed = (
            requested <= 1
            and attempt_epochs in ([], [1])
            and reported_dispositions == expected_dispositions
            and accepted_results == authority
            and completed <= terminal_limit
            and firing_completed == completed
            and activity_failed == firing_failed == 0
            and bridge["projected"] == firing_completed
            and projected_results == expected_projection
        )
        return CheckResult(
            passed=passed,
            detail={
                "accepted_results": accepted_results,
                "activity_completed": completed,
                "activity_failed": activity_failed,
                "activity_requested": requested,
                "attempt_epochs": attempt_epochs,
                "expected_dispositions": expected_dispositions,
                "firing_completed": firing_completed,
                "firing_failed": firing_failed,
                "projected_results": projected_results,
                "reported_dispositions": reported_dispositions,
                "terminal_limit": terminal_limit,
            },
        )


def execute_retry_story(history_path: Path, dispatch_path: Path) -> tuple[World, RetryEngineProfile]:
    """Retry once, crash, reclaim the exact invocation, and exhaust it."""

    profile = RetryEngineProfile(history_path, dispatch_path)
    world = World(profile, WORLD_BUDGET, checkers=(RetryAuthorityChecker(),))
    timeline = world.timeline()

    requested = timeline.run_until(
        "activity-requested",
        lambda observation: ActivityRequested.__name__ in cast(dict[str, JsonValue], observation.value)["record_types"],
    )
    requested_value = cast(dict[str, JsonValue], requested.value)
    assert requested_value["bridge"] == {"prepared": 1, "projected": 0}
    assert requested_value["attempts"] == []

    first_claim = timeline.command("worker.claim", {})
    first = cast(dict[str, JsonValue], first_claim.value)["attempt"]
    assert isinstance(first, dict)
    assert first["epoch"] == 1
    timeline.command("worker.fail", {"attempt": 1, "error": "temporary-1"})

    timeline.crash("retry_epoch_1_durable")
    world.restart()
    timeline = world.timeline()
    recovered = timeline.run_until(
        "retry-recovered",
        lambda observation: cast(dict[str, JsonValue], observation.value)["drives"] == 1,
    )
    recovered_value = cast(dict[str, JsonValue], recovered.value)
    assert recovered_value["bridge"] == {"prepared": 0, "projected": 0}
    assert recovered_value["failures_delivered"] == 1
    assert recovered_value["record_types"].count(ActivityRequested.__name__) == 1
    assert ActivityFailed.__name__ not in recovered_value["record_types"]

    second_claim = timeline.command("worker.claim", {})
    second = cast(dict[str, JsonValue], second_claim.value)["attempt"]
    assert isinstance(second, dict)
    assert second["epoch"] == 2
    assert {name: value for name, value in second.items() if name != "epoch"} == {
        name: value for name, value in first.items() if name != "epoch"
    }
    claimed = timeline.observe("retry-claimed")
    assert [attempt["epoch"] for attempt in cast(dict[str, JsonValue], claimed.value)["attempts"]] == [1, 2]

    timeline.command("worker.fail", {"attempt": 2, "error": "temporary-2"})
    timeline.begin_fair()
    exhausted = timeline.run_until(
        "retry-exhausted",
        lambda observation: cast(dict[str, JsonValue], observation.value)["status"] == "poisoned",
    )
    exhausted_value = cast(dict[str, JsonValue], exhausted.value)
    records = cast(list[JsonValue], exhausted_value["record_types"])
    assert records.count(ActivityFailed.__name__) == records.count(FiringFailed.__name__) == 1
    assert FiringCompleted.__name__ not in records
    assert exhausted_value["bridge"] == {"prepared": 0, "projected": 0}
    timeline.finish(Disposition.QUARANTINED)
    return world, profile


def build_retry_artifact(history_path: Path, dispatch_path: Path) -> ScenarioArtifactV3:
    world, _ = execute_retry_story(history_path, dispatch_path)
    try:
        artifact = world.artifact(SCENARIO_ID)
        assert isinstance(artifact, ScenarioArtifactV3)
        return artifact
    finally:
        world.close()


def execute_terminal_story(history_path: Path, dispatch_path: Path) -> tuple[World, TerminalEngineProfile]:
    """Retain one terminal, refuse ambiguity, crash before collect, and recover."""

    profile = TerminalEngineProfile(history_path, dispatch_path)
    world = World(profile, WORLD_BUDGET, checkers=(TerminalAuthorityChecker(),))
    timeline = world.timeline()

    requested = timeline.run_until(
        "local-terminal-requested",
        lambda observation: ActivityRequested.__name__ in cast(dict[str, JsonValue], observation.value)["record_types"],
    )
    requested_value = cast(dict[str, JsonValue], requested.value)
    assert requested_value["bridge"] == {"prepared": 1, "projected": 0}

    claim = timeline.command("worker.claim", {})
    attempt = cast(dict[str, JsonValue], claim.value)["attempt"]
    assert isinstance(attempt, dict)
    assert attempt["epoch"] == 1

    terminal = {"value": 6}
    accepted = timeline.command("worker.complete", {"result": terminal})
    duplicate = timeline.command("worker.complete", {"result": terminal})
    conflict = timeline.command("worker.complete", {"result": {"value": 7}})
    assert accepted.disposition == ActionDisposition.APPLIED.value
    assert duplicate.disposition == ActionDisposition.IDEMPOTENT.value
    assert conflict.disposition == ActionDisposition.REFUSED_EXPECTED.value

    durable = timeline.observe("local-terminal-durable")
    durable_value = cast(dict[str, JsonValue], durable.value)
    assert durable_value["accepted_results"] == [terminal]
    assert ActivityCompleted.__name__ not in durable_value["record_types"]
    assert durable_value["bridge"] == {"prepared": 1, "projected": 0}

    timeline.crash("local_terminal_durable_before_collect")
    world.restart()
    timeline = world.timeline()
    timeline.begin_fair()
    converged = timeline.run_until(
        "local-terminal-converged",
        lambda observation: cast(dict[str, JsonValue], observation.value)["status"] == "terminated",
    )
    converged_value = cast(dict[str, JsonValue], converged.value)
    records = cast(list[JsonValue], converged_value["record_types"])
    assert records.count(ActivityCompleted.__name__) == records.count(FiringCompleted.__name__) == 1
    assert converged_value["bridge"] == {"prepared": 0, "projected": 1}
    assert converged_value["marking"] == [{"place": str(DONE), "tokens": [{"color": "Done", "data": terminal}]}]
    timeline.finish(Disposition.CONVERGED)
    return world, profile


def build_terminal_artifact(history_path: Path, dispatch_path: Path) -> ScenarioArtifactV3:
    world, _ = execute_terminal_story(history_path, dispatch_path)
    try:
        artifact = world.artifact(TERMINAL_SCENARIO_ID)
        assert isinstance(artifact, ScenarioArtifactV3)
        return artifact
    finally:
        world.close()
