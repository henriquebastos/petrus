"""Public-Engine DST profile for timer crash and reconstruction semantics."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, cast

from pydantic import JsonValue

from petrus.engine import Engine
from petrus.impetus.history import FiringCompleted, TimerMatured
from petrus.impetus.history_store import JsonlHistoryStore
from petrus.impetus.petrinet import Arc, Delay, Marking, Net, NetPath, Place, Token, Transition
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

WAITING = NetPath("waiting")
DONE = NetPath("done")
RELEASE = NetPath("release")
INSTANCE_ID = "dst-world-timer-recovery"
SCENARIO_ID = "timer-crash-recovery-world-v3"
MATURATION_INSTANT = 5

PROFILE_DEFINITION = {
    "commands": {"engine.drive": []},
    "instance": INSTANCE_ID,
    "net": {
        "delay": MATURATION_INSTANT,
        "places": ["done", "waiting"],
        "transition": "release",
    },
    "observations": [
        "engine.timer-authority",
        "timer-armed",
        "timer-recovered",
        "timer-terminal",
    ],
}
PROFILE_IDENTITY = ProfileIdentity(
    name="petrus.engine.timer-recovery",
    version=1,
    digest=digest_json(PROFILE_DEFINITION),
)
CHECKER_IDENTITY = CheckerIdentity(
    name="petrus.engine.timer-authority",
    version=1,
    digest=digest_json(
        {
            "properties": [
                "timer maturation never precedes its authored deadline",
                "one authored timer matures and fires at most once",
                "a delayed firing requires its canonical maturation fact",
            ]
        }
    ),
)
WORLD_BUDGET = Budget(
    actions=32,
    queued_commands=8,
    timer_advances=1,
    logical_instant=MATURATION_INSTANT,
    reloads=1,
    predicate_polls=16,
    artifact_bytes=262_144,
)


def application_net() -> Net:
    return Net(
        places=[Place(WAITING), Place(DONE)],
        transitions=[Transition(RELEASE, timers=(Delay(MATURATION_INSTANT),))],
        arcs=[Arc(WAITING, RELEASE), Arc(RELEASE, DONE)],
        name="dst-world-timer-recovery",
    )


class WorldClock:
    """Engine Clock which observes only the World's deterministic instant."""

    def __init__(self, context: ScenarioContext):
        self.context = context

    def now(self) -> int:
        return self.context.now()

    def observe(self, instant: int) -> int | None:
        return self.context.now() if self.context.now() >= instant else None


@dataclass
class TimerGeneration:
    engine: Engine
    history: JsonlHistoryStore
    dispatch: InMemoryDispatch
    drives: int = 0


class TimerEngineProfile:
    """Opaque public-Engine generation around one reconstructable timer."""

    identity = PROFILE_IDENTITY
    _debug_fields = (
        "current_instant",
        "drives",
        "drops",
        "frontier",
        "marking",
        "next_maturation",
        "record_types",
        "status",
        "timer_maturations",
    )
    observation_fields: ClassVar[dict[str, tuple[str, ...]]] = {
        "engine.timer-authority": (
            "authored_maturation_instant",
            "current_instant",
            "record_types",
            "timer_maturations",
        ),
        "timer-armed": _debug_fields,
        "timer-recovered": _debug_fields,
        "timer-terminal": _debug_fields,
    }

    def __init__(self, history_path: Path):
        self.history_path = history_path
        self.drops = 0
        self.closes = 0

    def validate(self, command: Command) -> Command:
        if command.name != "engine.drive" or command.payload != {}:
            raise ValueError("timer Engine profile accepts only engine.drive with an empty payload")
        return command

    def validate_fault(self, fault: Fault) -> Fault:
        raise ValueError(f"timer Engine profile has no fault named {fault.name!r}")

    def create(self, context: ScenarioContext) -> GenerationStart[TimerGeneration]:
        generation = self._generation(context, load=False)
        return GenerationStart(generation, (self._scheduled(context, context.now()),))

    def load(self, context: ScenarioContext) -> GenerationStart[TimerGeneration]:
        generation = self._generation(context, load=True)
        return GenerationStart(generation, (self._scheduled(context, context.now()),))

    def apply(
        self,
        generation: TimerGeneration,
        command: Command,
        context: ScenarioContext,
    ) -> ApplyResult:
        del command
        outcome = generation.engine.advance()
        generation.drives += 1
        current = generation.engine.snapshot()["current"]
        assert isinstance(current, dict)
        status = current["status"]
        scheduled = []
        if status not in {"completed", "terminated"}:
            if outcome.ready:
                scheduled.append(self._scheduled(context, context.now()))
            elif outcome.next_maturation is not None:
                scheduled.append(self._scheduled(context, outcome.next_maturation))
        return ApplyResult(
            disposition=ActionDisposition.APPLIED.value,
            value={
                "firings": [str(firing.transition) for firing in outcome.firings],
                "frontier": len(generation.history),
                "next_maturation": outcome.next_maturation,
                "ready": outcome.ready,
                "status": status,
                "waiting": outcome.waiting,
            },
            scheduled=scheduled,
        )

    def observe(
        self,
        generation: TimerGeneration,
        request: ObservationRequest,
        context: ScenarioContext,
    ) -> JsonValue:
        if request.name not in self.observation_fields:
            raise ValueError(f"unknown timer Engine profile observation {request.name!r}")
        if request.payload not in (None, {}):
            raise ValueError("timer Engine profile observations do not accept parameters")
        state = self._observation_state(generation, context)
        return {field: state[field] for field in self.observation_fields[request.name]}

    def drop(self, generation: TimerGeneration) -> None:
        self.drops += 1
        generation.engine.close()

    def close(self, generation: TimerGeneration) -> None:
        self.closes += 1
        generation.engine.close()

    def _generation(self, context: ScenarioContext, *, load: bool) -> TimerGeneration:
        history = JsonlHistoryStore(self.history_path)
        dispatch = InMemoryDispatch()
        if load:
            engine = Engine.load(
                application_net(),
                INSTANCE_ID,
                history=history,
                dispatch=dispatch,
                clock=WorldClock(context),
            )
        else:
            engine = Engine.create(
                application_net(),
                INSTANCE_ID,
                history=history,
                dispatch=dispatch,
                marking=Marking({WAITING: (Token("Waiting"),)}),
                clock=WorldClock(context),
            )
        return TimerGeneration(engine, history, dispatch)

    def _observation_state(
        self,
        generation: TimerGeneration,
        context: ScenarioContext,
    ) -> dict[str, JsonValue]:
        records = generation.history.records
        current = generation.engine.snapshot()["current"]
        assert isinstance(current, dict)
        return cast(
            dict[str, JsonValue],
            {
                "authored_maturation_instant": MATURATION_INSTANT,
                "current_instant": context.now(),
                "drives": generation.drives,
                "drops": self.drops,
                "frontier": len(records),
                "marking": current["marking"],
                "next_maturation": current["next_maturation"],
                "record_types": [type(record).__name__ for record in records],
                "status": current["status"],
                "timer_maturations": [
                    {
                        "instant": record.instant,
                        "maturation_instant": record.maturation_instant,
                    }
                    for record in records
                    if isinstance(record, TimerMatured)
                ],
            },
        )

    def _scheduled(self, context: ScenarioContext, instant: int) -> ScheduledCommand:
        del context
        return ScheduledCommand(
            instant=instant,
            command=Command(profile=self.identity, name="engine.drive", payload={}),
        )


class TimerAuthorityChecker:
    """Independent deadline and cardinality checks over canonical timer facts."""

    identity = CHECKER_IDENTITY
    request = ObservationRequest(name="engine.timer-authority", payload={})

    def check(self, observation: Observation) -> CheckResult:
        value = cast(dict[str, JsonValue], observation.value)
        deadline = cast(int, value["authored_maturation_instant"])
        current = cast(int, value["current_instant"])
        records = cast(list[JsonValue], value["record_types"])
        maturations = cast(list[dict[str, JsonValue]], value["timer_maturations"])
        firing_completed = records.count(FiringCompleted.__name__)
        valid_maturations = all(
            maturation["maturation_instant"] == deadline
            and isinstance(maturation["instant"], int)
            and deadline <= maturation["instant"] <= current
            for maturation in maturations
        )
        passed = (
            len(maturations) <= 1
            and valid_maturations
            and firing_completed <= len(maturations)
            and (current >= deadline or not maturations and firing_completed == 0)
        )
        return CheckResult(
            passed=passed,
            detail={
                "authored_maturation_instant": deadline,
                "current_instant": current,
                "firing_completed": firing_completed,
                "timer_maturations": maturations,
            },
        )


def execute_timer_story(history_path: Path) -> tuple[World, TimerEngineProfile]:
    """Arm one delayed transition, crash, reload, and mature it exactly once."""

    profile = TimerEngineProfile(history_path)
    world = World(profile, WORLD_BUDGET, checkers=(TimerAuthorityChecker(),))
    timeline = world.timeline()

    armed = timeline.run_until(
        "timer-armed",
        lambda observation: (
            cast(dict[str, JsonValue], observation.value)["drives"] == 1
            and cast(dict[str, JsonValue], observation.value)["next_maturation"] == MATURATION_INSTANT
        ),
    )
    armed_value = cast(dict[str, JsonValue], armed.value)
    assert armed_value["current_instant"] == 0
    assert armed_value["timer_maturations"] == []
    assert armed_value["marking"] == [{"place": "waiting", "tokens": [{"color": "Waiting", "data": None}]}]

    timeline.crash("timer_observed_before_maturation")
    world.restart()
    timeline = world.timeline()
    recovered = timeline.run_until(
        "timer-recovered",
        lambda observation: cast(dict[str, JsonValue], observation.value)["drives"] == 1,
    )
    recovered_value = cast(dict[str, JsonValue], recovered.value)
    assert recovered_value["current_instant"] == 0
    assert recovered_value["drops"] == 1
    assert recovered_value["next_maturation"] == MATURATION_INSTANT
    assert recovered_value["timer_maturations"] == []

    timeline.begin_fair()
    terminal = timeline.run_until(
        "timer-terminal",
        lambda observation: cast(dict[str, JsonValue], observation.value)["status"] == "terminated",
    )
    terminal_value = cast(dict[str, JsonValue], terminal.value)
    assert terminal_value["current_instant"] == MATURATION_INSTANT
    assert terminal_value["timer_maturations"] == [
        {"instant": MATURATION_INSTANT, "maturation_instant": MATURATION_INSTANT}
    ]
    assert terminal_value["marking"] == [{"place": "done", "tokens": [{"color": "Waiting", "data": None}]}]
    timeline.finish(Disposition.CONVERGED)
    return world, profile


def build_timer_artifact(history_path: Path) -> ScenarioArtifact:
    world, _ = execute_timer_story(history_path)
    try:
        return world.artifact(SCENARIO_ID)
    finally:
        world.close()
