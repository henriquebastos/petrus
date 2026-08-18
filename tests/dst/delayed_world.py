"""Public-Engine DST profile for delayed external terminal reconstruction."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar, cast

from pydantic import JsonValue

from petrus.impetus.history import ActivityCompleted, ActivityFailed, FiringCompleted
from petrus.testing.dst import (
    ActionDisposition,
    ApplyResult,
    Budget,
    CheckResult,
    CheckerIdentity,
    Command,
    Disposition,
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
from tests.dst.engine_world import EngineGeneration, EngineProfile

SCENARIO_ID = "delayed-terminal-recovery-world-v3"
TERMINAL_INSTANT = 5

PROFILE_IDENTITY = ProfileIdentity(
    name="petrus.engine.delayed-terminal",
    version=1,
    digest=digest_json(
        {
            "commands": {
                "engine.complete": ["occurrence", "result"],
                "engine.drive": [],
                "provider.schedule-terminal": ["instant", "occurrence", "result"],
            },
            "instance": "dst-world-projection-recovery",
            "observations": [
                "activity-requested",
                "delayed-recovered",
                "delayed-scheduled",
                "delayed-terminal",
                "engine.delayed-authority",
            ],
        }
    ),
)
CHECKER_IDENTITY = CheckerIdentity(
    name="petrus.engine.delayed-terminal-authority",
    version=1,
    digest=digest_json(
        {
            "properties": [
                "no canonical terminal precedes its authored external delivery",
                "a delivered external terminal produces at most one canonical terminal and projection",
                "canonical completion cannot precede the authored logical delivery instant",
            ]
        }
    ),
)
WORLD_BUDGET = Budget(
    actions=32,
    queued_commands=4,
    timer_advances=1,
    logical_instant=TERMINAL_INSTANT,
    reloads=1,
    predicate_polls=16,
    artifact_bytes=262_144,
)


class DelayedEngineProfile(EngineProfile):
    """Retain modeled external terminal truth while World owns delivery order."""

    identity = PROFILE_IDENTITY
    _debug_fields = (
        "bridge",
        "frontier",
        "marking",
        "pending",
        "record_types",
        "scheduled_terminal",
        "status",
        "terminal_deliveries",
    )
    observation_fields: ClassVar[dict[str, tuple[str, ...]]] = {
        "activity-requested": (
            "frontier",
            "pending",
            "record_types",
            "scheduled_terminal",
            "status",
            "terminal_deliveries",
        ),
        "delayed-recovered": _debug_fields,
        "delayed-scheduled": _debug_fields,
        "delayed-terminal": _debug_fields,
        "engine.delayed-authority": (
            "record_types",
            "scheduled_terminal",
            "terminal_deliveries",
        ),
    }

    def __init__(self, history_path: Path):
        super().__init__(history_path)
        self.scheduled_terminal: dict[str, JsonValue] | None = None
        self.terminal_deliveries = 0

    def validate(self, command: Command) -> Command:
        if command.name != "provider.schedule-terminal":
            return super().validate(command)
        payload = command.payload
        if type(payload) is not dict or set(payload) != {"instant", "occurrence", "result"}:
            raise ValueError("provider.schedule-terminal requires exact instant, occurrence, and result fields")
        if payload["instant"] != TERMINAL_INSTANT:
            raise ValueError("provider.schedule-terminal requires the supported logical instant")
        occurrence = payload["occurrence"]
        if isinstance(occurrence, bool) or not isinstance(occurrence, int) or occurrence < 1:
            raise ValueError("provider.schedule-terminal occurrence must be a positive integer")
        return command

    def load(self, context: ScenarioContext) -> GenerationStart[EngineGeneration]:
        started = super().load(context)
        scheduled = list(started.scheduled)
        if self.scheduled_terminal is not None and self.terminal_deliveries == 0:
            scheduled.append(self._terminal_command())
        return GenerationStart(started.generation, tuple(scheduled))

    def apply(
        self,
        generation: EngineGeneration,
        command: Command,
        context: ScenarioContext,
    ) -> ApplyResult:
        if command.name == "provider.schedule-terminal":
            payload = cast(dict[str, JsonValue], command.payload)
            proposal = {
                "instant": payload["instant"],
                "occurrence": payload["occurrence"],
                "result": payload["result"],
            }
            if self.scheduled_terminal is not None:
                raise ValueError("the delayed-terminal profile accepts one external terminal schedule")
            self.scheduled_terminal = proposal
            return ApplyResult(
                disposition=ActionDisposition.APPLIED.value,
                value={"frontier": len(generation.history), "scheduled_terminal": proposal},
                scheduled=[self._terminal_command()],
            )
        result = super().apply(generation, command, context)
        if command.name == "engine.complete":
            self.terminal_deliveries += 1
        return result

    def _observation_state(self, generation: EngineGeneration) -> dict[str, JsonValue]:
        state = super()._observation_state(generation)
        state.update(
            {
                "scheduled_terminal": self.scheduled_terminal,
                "terminal_deliveries": self.terminal_deliveries,
            }
        )
        return state

    def _terminal_command(self) -> ScheduledCommand:
        if self.scheduled_terminal is None:
            raise RuntimeError("no delayed external terminal has been scheduled")
        return ScheduledCommand(
            instant=cast(int, self.scheduled_terminal["instant"]),
            command=Command(
                profile=self.identity,
                name="engine.complete",
                payload={
                    "occurrence": self.scheduled_terminal["occurrence"],
                    "result": self.scheduled_terminal["result"],
                },
            ),
        )


class DelayedAuthorityChecker:
    """Bound canonical terminal facts by authored external delivery and time."""

    identity = CHECKER_IDENTITY
    request = ObservationRequest(name="engine.delayed-authority", payload={})

    def check(self, observation: Observation) -> CheckResult:
        value = cast(dict[str, JsonValue], observation.value)
        records = cast(list[JsonValue], value["record_types"])
        scheduled = cast(dict[str, JsonValue] | None, value["scheduled_terminal"])
        deliveries = cast(int, value["terminal_deliveries"])
        completed = records.count(ActivityCompleted.__name__)
        failed = records.count(ActivityFailed.__name__)
        projected = records.count(FiringCompleted.__name__)
        terminal = completed + failed
        scheduled_instant = None if scheduled is None else cast(int, scheduled["instant"])
        passed = (
            deliveries <= (0 if scheduled is None else 1)
            and terminal <= deliveries
            and failed == 0
            and projected == completed
            and (terminal == 0 or (scheduled_instant is not None and observation.instant >= scheduled_instant))
        )
        return CheckResult(
            passed=passed,
            detail={
                "activity_completed": completed,
                "activity_failed": failed,
                "firing_completed": projected,
                "scheduled_instant": scheduled_instant,
                "terminal_deliveries": deliveries,
            },
        )


def execute_delayed_story(history_path: Path) -> tuple[World, DelayedEngineProfile]:
    """Lose one volatile delayed delivery, reconstruct it, and converge at time."""

    profile = DelayedEngineProfile(history_path)
    world = World(profile, WORLD_BUDGET, checkers=(DelayedAuthorityChecker(),))
    timeline = world.timeline()

    requested = timeline.run_until(
        "activity-requested",
        lambda observation: cast(dict[str, JsonValue], observation.value)["pending"] == [1],
    )
    assert cast(dict[str, JsonValue], requested.value)["frontier"] == 6

    scheduled = timeline.command(
        "provider.schedule-terminal",
        {"instant": TERMINAL_INSTANT, "occurrence": 1, "result": {"value": 3}},
    )
    assert scheduled.disposition == ActionDisposition.APPLIED.value
    held = timeline.observe("delayed-scheduled")
    held_value = cast(dict[str, JsonValue], held.value)
    assert held.instant == 0
    assert held_value["terminal_deliveries"] == 0

    timeline.crash("external_terminal_scheduled_before_delivery")
    world.restart()
    timeline = world.timeline()
    recovered = timeline.run_until(
        "delayed-recovered",
        lambda observation: cast(dict[str, JsonValue], observation.value)["pending"] == [1],
    )
    recovered_value = cast(dict[str, JsonValue], recovered.value)
    assert recovered.instant == 0
    assert recovered_value["bridge"] == {"prepared": 0, "projected": 0}
    assert recovered_value["terminal_deliveries"] == 0

    timeline.begin_fair()
    terminal = timeline.run_until(
        "delayed-terminal",
        lambda observation: cast(dict[str, JsonValue], observation.value)["status"] == "terminated",
    )
    terminal_value = cast(dict[str, JsonValue], terminal.value)
    assert terminal.instant == TERMINAL_INSTANT
    assert terminal_value["terminal_deliveries"] == 1
    assert terminal_value["bridge"] == {"prepared": 0, "projected": 1}
    assert terminal_value["marking"] == [{"place": "done", "tokens": [{"color": "Done", "data": {"value": 3}}]}]
    timeline.finish(Disposition.CONVERGED)
    return world, profile


def build_delayed_artifact(history_path: Path) -> ScenarioArtifactV3:
    world, _ = execute_delayed_story(history_path)
    try:
        artifact = world.artifact(SCENARIO_ID)
        assert isinstance(artifact, ScenarioArtifactV3)
        return artifact
    finally:
        world.close()
