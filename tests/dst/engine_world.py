"""Public-Engine DST profile and executable projection recovery story."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from pydantic import JsonValue

from petrus.engine import Engine
from petrus.impetus.history import ActivityCompleted, ActivityRequested, FiringCompleted
from petrus.impetus.history_store import JsonlHistoryStore
from petrus.impetus.petrinet import Arc, Marking, Net, NetPath, Place, Token, Transition
from petrus.motus.activity import ActivityInvocation
from petrus.motus.dispatch import InMemoryDispatch
from petrus.testing.dst import (
    ActionDisposition,
    ApplyResult,
    Budget,
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
    ScenarioArtifact,
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
SCENARIO_ID = "projection-crash-recovery-world-v1"

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
WORLD_BUDGET = Budget(
    actions=32,
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


@dataclass
class EngineGeneration:
    engine: Engine
    history: JsonlHistoryStore
    dispatch: InMemoryDispatch
    bridge: ProjectionBridge
    poisoned: bool = False
    dropped: bool = False


class EngineProfile:
    """Petrus-owned profile composed exclusively through public Engine doors."""

    identity = PROFILE_IDENTITY

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
        history = JsonlHistoryStore(self.history_path)
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
        history = JsonlHistoryStore(self.history_path)
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
            return ApplyResult(
                disposition=ActionDisposition.APPLIED.value,
                value={"frontier": len(generation.history)},
                scheduled=[self._scheduled(context, "engine.drive", {})],
            )

        faults = context.faults("activity_terminal_frozen")
        expected_error = None
        for fault in faults:
            if fault.name != "projection.raise" or fault.disposition != FaultDisposition.RAISE.value:
                raise ValueError(f"unsupported public-Engine profile fault {fault.name!r}")
            if type(fault.payload) is not dict or set(fault.payload) != {"message"}:
                raise ValueError("projection.raise requires an exact message payload")
            expected_error = fault.payload["message"]
            if not isinstance(expected_error, str):
                raise ValueError("projection.raise message must be a string")
            generation.bridge.projection_error = expected_error

        try:
            outcome = generation.engine.advance()
        except RuntimeError as error:
            if expected_error is None or str(error) != expected_error:
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
        if request.name not in {
            "activity-requested",
            "engine.safety",
            "projection-refused",
            "terminal",
        }:
            raise ValueError(f"unknown public-Engine profile observation {request.name!r}")
        if request.payload not in (None, {}):
            raise ValueError("public-Engine profile observations do not accept parameters")
        records = generation.history.records
        record_types = [type(record).__name__ for record in records]
        if request.name == "engine.safety":
            return {"record_types": record_types}
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
            "record_types": record_types,
            "status": status,
        }
        fields = {
            "activity-requested": ("frontier", "pending", "status"),
            "projection-refused": ("bridge", "frontier", "record_types", "status"),
            "terminal": ("bridge", "drops", "frontier", "marking", "record_types", "status"),
        }[request.name]
        return {field: state[field] for field in fields}

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


def execute_projection_story(history_path: Path) -> tuple[World, EngineProfile, Timeline]:
    """Author the vertical scenario as an imperative debugger-like pytest story."""

    profile = EngineProfile(history_path)
    world = World(profile, WORLD_BUDGET, checkers=(EngineHistoryChecker(),))
    timeline = world.timeline()

    requested = timeline.run_until(
        "activity-requested",
        lambda observation: cast(dict[str, JsonValue], observation.value)["pending"] == [1],
    )
    assert cast(dict[str, JsonValue], requested.value)["frontier"] == 6

    timeline.activate_fault(
        "projection.raise",
        "activity_terminal_frozen",
        disposition=FaultDisposition.RAISE,
        payload={"message": "dst projection fault"},
    )
    timeline.command("engine.complete", {"occurrence": 1, "result": {"value": 3}})
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
    assert terminal_value["marking"] == [{"place": "done", "tokens": [{"color": "Done", "data": {"value": 3}}]}]
    timeline.finish(Disposition.CONVERGED)
    return world, profile, stale


def build_projection_artifact(history_path: Path) -> ScenarioArtifact:
    world, _, _ = execute_projection_story(history_path)
    try:
        return world.artifact(SCENARIO_ID)
    finally:
        world.close()
