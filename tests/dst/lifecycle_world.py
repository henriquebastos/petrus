"""Public-Engine DST profile for lifecycle reset and late terminal races."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, cast

from pydantic import JsonValue

from petrus.engine import Engine
from petrus.impetus.history import (
    ActivityCompleted,
    ActivityFailed,
    ActivityTerminalQuarantined,
    FiringCompleted,
    ScopeOpened,
    ScopeReset,
)
from petrus.impetus.history_store import JsonlHistoryStore
from petrus.impetus.petrinet import Arc, Net, NetPath, Place, Token, Transition
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
    GenerationStart,
    Observation,
    ObservationRequest,
    ProfileIdentity,
    ScenarioArtifact,
    ScenarioContext,
    ScheduledCommand,
    World,
    digest_json,
)

SOURCE = NetPath("source")
INPUT = NetPath("input")
DONE = NetPath("done")
PROJECT = NetPath("project")
INSTANCE_ID = "dst-world-lifecycle-race"
SCENARIO_ID = "lifecycle-reset-late-terminal-world-v3"
SCOPE_NAME = "draft"

PROFILE_DEFINITION = {
    "commands": {
        "activity.complete": ["occurrence", "result"],
        "engine.drive": [],
        "scope.open": ["name"],
        "scope.reset": ["name"],
        "source.deliver": ["identity", "scope", "value"],
    },
    "instance": INSTANCE_ID,
    "net": {
        "activity": "calculate",
        "places": ["done", "input"],
        "source": "source",
        "transition": "project",
    },
    "observations": [
        "activity-requested",
        "duplicate-acknowledged",
        "engine.lifecycle-authority",
        "recovered-reset",
        "reset-committed",
        "terminal-quarantined",
    ],
}
PROFILE_IDENTITY = ProfileIdentity(
    name="petrus.engine.lifecycle-race",
    version=1,
    digest=digest_json(PROFILE_DEFINITION),
)
CHECKER_IDENTITY = CheckerIdentity(
    name="petrus.engine.lifecycle-authority",
    version=1,
    digest=digest_json(
        {
            "properties": [
                "active scope generation equals authored lifecycle authority",
                "canonical opens, resets, and quarantines do not exceed authored external facts",
                "cancelled activity terminals never become ordinary terminal or projection facts",
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
        transitions=[Transition(SOURCE), Transition(PROJECT, handler="bridge")],
        arcs=[Arc(SOURCE, INPUT), Arc(INPUT, PROJECT), Arc(PROJECT, DONE)],
        name="dst-world-lifecycle-race",
    )


class ProjectionBridge:
    def __init__(self) -> None:
        self.prepared = 0
        self.projected = 0

    def prepare(self, binding) -> ActivityInvocation:
        self.prepared += 1
        return ActivityInvocation("calculate", input=binding.tokens[0].data)

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
class LifecycleGeneration:
    engine: Engine
    history: JsonlHistoryStore
    dispatch: InMemoryDispatch
    bridge: ProjectionBridge
    drives: int = 0


class LifecycleEngineProfile:
    """Opaque public-Engine generation plus authored lifecycle-world facts."""

    identity = PROFILE_IDENTITY
    observation_fields: ClassVar[dict[str, tuple[str, ...]]] = {
        "activity-requested": ("active_scopes", "bridge", "frontier", "pending", "record_types"),
        "duplicate-acknowledged": (
            "active_scopes",
            "bridge",
            "drives",
            "frontier",
            "quarantined_occurrences",
            "record_types",
        ),
        "engine.lifecycle-authority": (
            "active_scopes",
            "authored_scope_generation",
            "authored_scope_opens",
            "authored_scope_resets",
            "authored_source_deliveries",
            "authored_terminal_deliveries",
            "record_types",
        ),
        "recovered-reset": (
            "active_scopes",
            "bridge",
            "drives",
            "frontier",
            "pending",
            "record_types",
        ),
        "reset-committed": (
            "active_scopes",
            "bridge",
            "frontier",
            "pending",
            "record_types",
            "scope_resets",
        ),
        "terminal-quarantined": (
            "active_scopes",
            "bridge",
            "drives",
            "frontier",
            "quarantined_occurrences",
            "record_types",
        ),
    }

    def __init__(self, history_path: Path):
        self.history_path = history_path
        self.scope_generation = 0
        self.scope_opens = 0
        self.scope_resets = 0
        self.source_deliveries = 0
        self.terminal_deliveries = 0
        self.drops = 0
        self.closes = 0

    def validate(self, command: Command) -> Command:
        payload = command.payload
        if command.name == "engine.drive":
            if payload != {}:
                raise ValueError("engine.drive payload must be an empty object")
            return command
        if command.name in {"scope.open", "scope.reset"}:
            if type(payload) is not dict or payload != {"name": SCOPE_NAME}:
                raise ValueError(f"{command.name} requires the exact supported scope name")
            return command
        if command.name == "source.deliver":
            if type(payload) is not dict or set(payload) != {"identity", "scope", "value"}:
                raise ValueError("source.deliver requires exact identity, scope, and value fields")
            if not isinstance(payload["identity"], str) or not payload["identity"]:
                raise ValueError("source.deliver identity must be a non-empty string")
            if payload["scope"] != SCOPE_NAME:
                raise ValueError("source.deliver requires the supported scope")
            if isinstance(payload["value"], bool) or not isinstance(payload["value"], int):
                raise ValueError("source.deliver value must be an integer")
            return command
        if command.name == "activity.complete":
            if type(payload) is not dict or set(payload) != {"occurrence", "result"}:
                raise ValueError("activity.complete requires exact occurrence and result fields")
            occurrence = payload["occurrence"]
            if isinstance(occurrence, bool) or not isinstance(occurrence, int) or occurrence < 1:
                raise ValueError("activity.complete occurrence must be a positive integer")
            return command
        raise ValueError(f"unknown lifecycle Engine profile command {command.name!r}")

    def validate_fault(self, fault: Fault) -> Fault:
        raise ValueError(f"lifecycle Engine profile has no fault named {fault.name!r}")

    def create(self, context: ScenarioContext) -> GenerationStart[LifecycleGeneration]:
        generation = self._generation(context, load=False)
        return GenerationStart(generation)

    def load(self, context: ScenarioContext) -> GenerationStart[LifecycleGeneration]:
        generation = self._generation(context, load=True)
        return GenerationStart(generation, (self._scheduled(context, "engine.drive", {}),))

    def apply(
        self,
        generation: LifecycleGeneration,
        command: Command,
        context: ScenarioContext,
    ) -> ApplyResult:
        payload = cast(dict[str, JsonValue], command.payload)
        if command.name == "scope.open":
            scope = generation.engine.open_scope(SCOPE_NAME)
            self.scope_opens += 1
            self.scope_generation = scope.generation
            return self._applied(generation, {"generation": scope.generation})
        if command.name == "source.deliver":
            scope = generation.engine.active_scopes[cast(str, payload["scope"])]
            generation.engine.deliver(
                SOURCE,
                Token("Input", payload["value"]),
                identity=cast(str, payload["identity"]),
                scope=scope,
            )
            self.source_deliveries += 1
            return self._applied(
                generation,
                scheduled=[self._scheduled(context, "engine.drive", {})],
            )
        if command.name == "scope.reset":
            current = generation.engine.active_scopes[SCOPE_NAME]
            opened = generation.engine.reset_scope(current)
            self.scope_resets += 1
            self.scope_generation = opened.generation
            return self._applied(generation, {"generation": opened.generation})
        if command.name == "activity.complete":
            generation.dispatch.complete(cast(int, payload["occurrence"]), payload["result"])
            self.terminal_deliveries += 1
            return self._applied(
                generation,
                scheduled=[self._scheduled(context, "engine.drive", {})],
            )

        outcome = generation.engine.advance()
        generation.drives += 1
        current = generation.engine.snapshot()["current"]
        assert isinstance(current, dict)
        return self._applied(
            generation,
            {
                "firings": [str(firing.transition) for firing in outcome.firings],
                "ready": outcome.ready,
                "status": current["status"],
                "waiting": outcome.waiting,
            },
        )

    def observe(
        self,
        generation: LifecycleGeneration,
        request: ObservationRequest,
        context: ScenarioContext,
    ) -> JsonValue:
        del context
        if request.name not in self.observation_fields:
            raise ValueError(f"unknown lifecycle Engine profile observation {request.name!r}")
        if request.payload not in (None, {}):
            raise ValueError("lifecycle Engine profile observations do not accept parameters")
        state = self._observation_state(generation)
        return {field: state[field] for field in self.observation_fields[request.name]}

    def drop(self, generation: LifecycleGeneration) -> None:
        self.drops += 1
        generation.engine.close()

    def close(self, generation: LifecycleGeneration) -> None:
        self.closes += 1
        generation.engine.close()

    def _generation(self, context: ScenarioContext, *, load: bool) -> LifecycleGeneration:
        history = JsonlHistoryStore(self.history_path)
        dispatch = InMemoryDispatch()
        bridge = ProjectionBridge()
        factory = Engine.load if load else Engine.create
        engine = factory(
            application_net(),
            INSTANCE_ID,
            history=history,
            dispatch=dispatch,
            handlers={"bridge": bridge},
            clock=WorldClock(context),
        )
        return LifecycleGeneration(engine, history, dispatch, bridge)

    def _observation_state(self, generation: LifecycleGeneration) -> dict[str, JsonValue]:
        records = generation.history.records
        record_types = [type(record).__name__ for record in records]
        return cast(
            dict[str, JsonValue],
            {
                "active_scopes": {
                    name: scope.generation for name, scope in sorted(generation.engine.active_scopes.items())
                },
                "authored_scope_generation": self.scope_generation,
                "authored_scope_opens": self.scope_opens,
                "authored_scope_resets": self.scope_resets,
                "authored_source_deliveries": self.source_deliveries,
                "authored_terminal_deliveries": self.terminal_deliveries,
                "bridge": {
                    "prepared": generation.bridge.prepared,
                    "projected": generation.bridge.projected,
                },
                "drives": generation.drives,
                "frontier": len(records),
                "pending": sorted(generation.dispatch.pending),
                "quarantined_occurrences": [
                    record.occurrence for record in records if isinstance(record, ActivityTerminalQuarantined)
                ],
                "record_types": record_types,
                "scope_resets": [
                    {"closed": record.closed.generation, "opened": record.opened.generation}
                    for record in records
                    if isinstance(record, ScopeReset)
                ],
            },
        )

    def _applied(
        self,
        generation: LifecycleGeneration,
        value: dict[str, JsonValue] | None = None,
        *,
        scheduled: list[ScheduledCommand] | None = None,
    ) -> ApplyResult:
        detail: dict[str, JsonValue] = {"frontier": len(generation.history)}
        if value is not None:
            detail.update(value)
        return ApplyResult(
            disposition=ActionDisposition.APPLIED.value,
            value=detail,
            scheduled=[] if scheduled is None else scheduled,
        )

    def _scheduled(self, context: ScenarioContext, name: str, payload: JsonValue) -> ScheduledCommand:
        return ScheduledCommand(
            instant=context.now(),
            command=Command(profile=self.identity, name=name, payload=payload),
        )


class LifecycleAuthorityChecker:
    """Independent lifecycle expectations derived from authored world facts."""

    identity = CHECKER_IDENTITY
    request = ObservationRequest(name="engine.lifecycle-authority", payload={})

    def check(self, observation: Observation) -> CheckResult:
        value = cast(dict[str, JsonValue], observation.value)
        records = cast(list[JsonValue], value["record_types"])
        generation = cast(int, value["authored_scope_generation"])
        opens = cast(int, value["authored_scope_opens"])
        resets = cast(int, value["authored_scope_resets"])
        sources = cast(int, value["authored_source_deliveries"])
        terminals = cast(int, value["authored_terminal_deliveries"])
        actual_scopes = value["active_scopes"]
        expected_scopes: JsonValue = {} if generation == 0 else {SCOPE_NAME: generation}
        canonical_opens = records.count(ScopeOpened.__name__)
        canonical_resets = records.count(ScopeReset.__name__)
        quarantined = records.count(ActivityTerminalQuarantined.__name__)
        ordinary_terminals = records.count(ActivityCompleted.__name__) + records.count(ActivityFailed.__name__)
        projections = records.count(FiringCompleted.__name__)
        passed = (
            actual_scopes == expected_scopes
            and canonical_opens <= opens <= 1
            and canonical_resets <= resets <= 1
            and quarantined <= terminals
            and quarantined <= 1
            and ordinary_terminals == 0
            and projections <= sources <= 1
        )
        return CheckResult(
            passed=passed,
            detail={
                "activity_terminals": ordinary_terminals,
                "authored_scope_generation": generation,
                "authored_scope_opens": opens,
                "authored_scope_resets": resets,
                "authored_source_deliveries": sources,
                "authored_terminal_deliveries": terminals,
                "canonical_scope_opens": canonical_opens,
                "canonical_scope_resets": canonical_resets,
                "firing_completed": projections,
                "terminal_quarantined": quarantined,
            },
        )


def execute_lifecycle_story(
    history_path: Path,
) -> tuple[World, LifecycleEngineProfile]:
    """Reset in-flight work, crash, then quarantine and acknowledge its late terminal."""

    profile = LifecycleEngineProfile(history_path)
    world = World(profile, WORLD_BUDGET, checkers=(LifecycleAuthorityChecker(),))
    timeline = world.timeline()

    timeline.command("scope.open", {"name": SCOPE_NAME})
    timeline.command(
        "source.deliver",
        {"identity": "draft-input-3", "scope": SCOPE_NAME, "value": 3},
    )
    requested = timeline.run_until(
        "activity-requested",
        lambda observation: cast(dict[str, JsonValue], observation.value)["pending"] == [2],
    )
    requested_value = cast(dict[str, JsonValue], requested.value)
    assert requested_value["active_scopes"] == {SCOPE_NAME: 1}
    assert requested_value["bridge"] == {"prepared": 1, "projected": 0}

    timeline.command("scope.reset", {"name": SCOPE_NAME})
    reset = timeline.observe("reset-committed")
    reset_value = cast(dict[str, JsonValue], reset.value)
    assert reset_value["active_scopes"] == {SCOPE_NAME: 2}
    assert reset_value["pending"] == []
    assert reset_value["scope_resets"] == [{"closed": 1, "opened": 2}]

    timeline.crash("lifecycle_reset_before_late_terminal")
    world.restart()
    timeline = world.timeline()
    recovered = timeline.run_until(
        "recovered-reset",
        lambda observation: cast(dict[str, JsonValue], observation.value)["drives"] == 1,
    )
    recovered_value = cast(dict[str, JsonValue], recovered.value)
    assert recovered_value["active_scopes"] == {SCOPE_NAME: 2}
    assert recovered_value["pending"] == []
    assert recovered_value["bridge"] == {"prepared": 0, "projected": 0}

    timeline.command("activity.complete", {"occurrence": 2, "result": {"value": 3}})
    quarantined = timeline.run_until(
        "terminal-quarantined",
        lambda observation: cast(dict[str, JsonValue], observation.value)["quarantined_occurrences"] == [2],
    )
    quarantined_value = cast(dict[str, JsonValue], quarantined.value)
    assert quarantined_value["bridge"] == {"prepared": 0, "projected": 0}
    frontier = quarantined_value["frontier"]

    timeline.command("activity.complete", {"occurrence": 2, "result": {"value": 3}})
    acknowledged = timeline.run_until(
        "duplicate-acknowledged",
        lambda observation: cast(dict[str, JsonValue], observation.value)["drives"] == 3,
    )
    acknowledged_value = cast(dict[str, JsonValue], acknowledged.value)
    assert acknowledged_value["frontier"] == frontier
    assert acknowledged_value["quarantined_occurrences"] == [2]
    assert acknowledged_value["bridge"] == {"prepared": 0, "projected": 0}

    timeline.begin_fair()
    timeline.finish(Disposition.QUIESCENT)
    return world, profile


def build_lifecycle_artifact(history_path: Path) -> ScenarioArtifact:
    world, _ = execute_lifecycle_story(history_path)
    try:
        return world.artifact(SCENARIO_ID)
    finally:
        world.close()
