"""Strict data contract and the narrow CV19.DS1 replay profile."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from petrus.engine import Engine
from petrus.impetus.history import ActivityCompleted, ActivityRequested, FiringCompleted
from petrus.impetus.history_store import JsonlHistoryStore
from petrus.impetus.petrinet import Arc, Marking, Net, NetPath, Place, Token, Transition
from petrus.motus.activity import ActivityInvocation
from petrus.motus.dispatch import InMemoryDispatch


FORMAT = "petrus-dst-scenario"
VERSION = 1
PROFILE = "engine-coordinator-v1"
RESULT_FORMAT = "petrus-dst-replay-result"
APPLICATION_PROFILE = "projection-recovery-v1"
APPLICATION_DEFINITION = {
    "activity": "calculate",
    "name": "dst-projection-recovery",
    "places": ["done", "input"],
    "projection": "Done(result)",
    "transition": {"handler": "bridge", "input": "input", "output": "done", "path": "project"},
}
APPLICATION_DIGEST = (
    "sha256:"
    + hashlib.sha256(
        json.dumps(APPLICATION_DEFINITION, allow_nan=False, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()
)

_SAFETY_PROPERTIES = Literal[
    "S1-replay-agreement",
    "S2-history-validity",
    "S3-stable-invocation",
    "S4-terminal-before-projection",
    "S5-delivery-identity",
    "S6-lifecycle-isolation",
    "S7-commit-authority",
    "S8-profile-bounds",
    "L1-fair-convergence",
]
_DISPOSITIONS = Literal[
    "applied", "idempotent", "refused_expected", "quarantined", "bounded_exhaustion", "harness_failure"
]
_CUTS = Literal[
    "instance_created",
    "delivery_accepted",
    "activity_requested",
    "external_effect",
    "activity_terminal_frozen",
    "projection_committed",
    "semantic_batch_refused",
    "scope_fenced",
    "terminal_acknowledged",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class TokenValue(StrictModel):
    color: str | None
    data: JsonValue


class MarkingEntry(StrictModel):
    place: str = Field(min_length=1)
    tokens: list[TokenValue] = Field(min_length=1)


class ScopeValue(StrictModel):
    name: str = Field(min_length=1)
    generation: int = Field(ge=1)


class DeliverEvent(StrictModel):
    kind: Literal["deliver"]
    source: str = Field(min_length=1)
    tokens: list[TokenValue] = Field(min_length=1)
    identity: str = Field(min_length=1)


class DriveEvent(StrictModel):
    kind: Literal["drive"]
    max_actions: int = Field(ge=1, le=256)


class AdvanceTimeEvent(StrictModel):
    kind: Literal["advance_time"]
    instant: int = Field(ge=0, le=1_000_000_000)


class DispatchTerminalEvent(StrictModel):
    kind: Literal["dispatch_terminal"]
    occurrence: int = Field(ge=1)
    outcome: Literal["completed", "failed"]
    value: JsonValue


class CloseScopeEvent(StrictModel):
    kind: Literal["close_scope"]
    scope: ScopeValue


class ResetScopeEvent(StrictModel):
    kind: Literal["reset_scope"]
    scope: ScopeValue


class CrashEvent(StrictModel):
    kind: Literal["crash"]
    cut: _CUTS


class RestartEvent(StrictModel):
    kind: Literal["restart"]


class BeginFairEvent(StrictModel):
    kind: Literal["begin_fair"]


type ScenarioEvent = Annotated[
    DeliverEvent
    | DriveEvent
    | AdvanceTimeEvent
    | DispatchTerminalEvent
    | CloseScopeEvent
    | ResetScopeEvent
    | CrashEvent
    | RestartEvent
    | BeginFairEvent,
    Field(discriminator="kind"),
]


class ScenarioFault(StrictModel):
    kind: Literal[
        "history_refuse",
        "history_commit_refuse",
        "dispatch_refuse",
        "dispatch_delay",
        "dispatch_duplicate",
        "dispatch_conflict",
        "ack_refuse",
        "process_crash",
        "history_unreadable",
        "projection_raise",
    ]
    cut: _CUTS
    count: int = Field(ge=1, le=64)
    error: str | None

    @model_validator(mode="after")
    def allowed_cut(self) -> ScenarioFault:
        allowed = {
            "history_refuse": {
                "instance_created",
                "delivery_accepted",
                "activity_requested",
                "activity_terminal_frozen",
                "projection_committed",
                "scope_fenced",
            },
            "history_commit_refuse": {
                "instance_created",
                "delivery_accepted",
                "activity_requested",
                "activity_terminal_frozen",
                "projection_committed",
                "scope_fenced",
            },
            "dispatch_refuse": {"activity_requested", "scope_fenced"},
            "dispatch_delay": {"external_effect"},
            "dispatch_duplicate": {
                "activity_terminal_frozen",
                "projection_committed",
                "terminal_acknowledged",
            },
            "dispatch_conflict": {"activity_terminal_frozen"},
            "ack_refuse": {"delivery_accepted", "activity_terminal_frozen", "terminal_acknowledged"},
            "process_crash": {
                "instance_created",
                "delivery_accepted",
                "activity_requested",
                "external_effect",
                "activity_terminal_frozen",
                "projection_committed",
                "semantic_batch_refused",
                "scope_fenced",
                "terminal_acknowledged",
            },
            "history_unreadable": {"semantic_batch_refused"},
            "projection_raise": {"activity_terminal_frozen"},
        }
        if self.cut not in allowed[self.kind]:
            raise ValueError(f"DST fault {self.kind!r} is not valid at cut {self.cut!r}")
        if (self.kind == "projection_raise") != (self.error is not None):
            raise ValueError("only projection_raise requires a non-null error")
        return self


class StepExpectation(StrictModel):
    disposition: _DISPOSITIONS
    history_frontier: int = Field(ge=0, le=50_000)
    error: str | None


class ScenarioStep(StrictModel):
    position: int = Field(ge=0, le=511)
    event: ScenarioEvent
    faults: list[ScenarioFault] = Field(max_length=64)
    expect: StepExpectation


class DependencyIdentity(StrictModel):
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)


class RuntimeIdentity(StrictModel):
    implementation: str = Field(min_length=1)
    version: str = Field(min_length=1)


class ShrinkLineage(StrictModel):
    parent_scenario_id: str | None
    steps: int = Field(ge=0)


class ScenarioOrigin(StrictModel):
    seed: int = Field(ge=0)
    petrus_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    runtime: RuntimeIdentity
    dependencies: list[DependencyIdentity] = Field(min_length=1)
    property: _SAFETY_PROPERTIES
    shrink: ShrinkLineage

    @model_validator(mode="after")
    def unique_dependencies(self) -> ScenarioOrigin:
        names = [dependency.name for dependency in self.dependencies]
        if len(names) != len(set(names)):
            raise ValueError("DST dependency identities must have unique names")
        return self


class ApplicationIdentity(StrictModel):
    profile: str = Field(min_length=1)
    definition_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class ScenarioLimits(StrictModel):
    events: int = Field(ge=1, le=512)
    faults: int = Field(ge=0, le=64)
    crash_restart_pairs: int = Field(ge=0, le=32)
    actions_per_drive: int = Field(ge=1, le=256)
    total_actions: int = Field(ge=1, le=4096)
    logical_instant: int = Field(ge=0, le=1_000_000_000)
    history_records: int = Field(ge=1, le=50_000)
    history_payload_bytes: int = Field(ge=1, le=4_194_304)
    retained_tokens: int = Field(ge=1, le=4096)
    retained_token_bytes: int = Field(ge=1, le=4_194_304)
    pending_outcomes: int = Field(ge=0, le=256)
    in_flight_activities: int = Field(ge=0, le=64)
    artifact_bytes: int = Field(ge=1, le=4_194_304)
    watchdog_seconds: int = Field(ge=1, le=30)


class ScenarioInitial(StrictModel):
    instance_id: str = Field(min_length=1)
    instant: int = Field(ge=0, le=1_000_000_000)
    marking: list[MarkingEntry]


class ExpectedSnapshot(StrictModel):
    marking: list[MarkingEntry]
    status: Literal["running", "terminated", "completed", "stuck", "awaiting"]
    watermark: int = Field(ge=0, le=1_000_000_000)
    in_flight: list[int]


class ExpectedObservation(StrictModel):
    name: str = Field(min_length=1)
    value: JsonValue


class ExpectedCheck(StrictModel):
    property: _SAFETY_PROPERTIES
    outcome: Literal["pass"]


class ScenarioExpected(StrictModel):
    disposition: Literal["quiescent", "terminal", "quarantined", "bounded_exhaustion", "external_wait"]
    history_record_types: list[str]
    snapshot: ExpectedSnapshot
    observations: list[ExpectedObservation]
    checks: list[ExpectedCheck] = Field(min_length=1)


class ScenarioArtifact(StrictModel):
    format: Literal["petrus-dst-scenario"]
    version: Literal[1]
    profile: Literal["engine-coordinator-v1"]
    scenario_id: str = Field(min_length=1)
    origin: ScenarioOrigin
    application: ApplicationIdentity
    limits: ScenarioLimits
    initial: ScenarioInitial
    schedule: list[ScenarioStep] = Field(min_length=1, max_length=512)
    expected: ScenarioExpected

    @model_validator(mode="after")
    def coherent_bounds(self) -> ScenarioArtifact:
        if [step.position for step in self.schedule] != list(range(len(self.schedule))):
            raise ValueError("DST schedule positions must be dense and zero-based")
        if len({entry.place for entry in self.initial.marking}) != len(self.initial.marking):
            raise ValueError("DST initial marking must name each place at most once")
        if len({entry.place for entry in self.expected.snapshot.marking}) != len(self.expected.snapshot.marking):
            raise ValueError("DST expected marking must name each place at most once")
        if len(self.schedule) > self.limits.events:
            raise ValueError("DST schedule exceeds its event limit")
        if sum(fault.count for step in self.schedule for fault in step.faults) > self.limits.faults:
            raise ValueError("DST schedule exceeds its fault limit")
        crashes = sum(isinstance(step.event, CrashEvent) for step in self.schedule)
        restarts = sum(isinstance(step.event, RestartEvent) for step in self.schedule)
        if crashes != restarts or crashes > self.limits.crash_restart_pairs:
            raise ValueError("DST crash and restart counts must pair within their limit")
        if any(
            isinstance(step.event, DriveEvent) and step.event.max_actions > self.limits.actions_per_drive
            for step in self.schedule
        ):
            raise ValueError("DST drive exceeds its per-event action limit")
        if any(
            isinstance(step.event, AdvanceTimeEvent) and step.event.instant > self.limits.logical_instant
            for step in self.schedule
        ):
            raise ValueError("DST event instant exceeds its logical-time limit")
        if (
            self.initial.instant > self.limits.logical_instant
            or self.expected.snapshot.watermark > self.limits.logical_instant
        ):
            raise ValueError("DST instant exceeds its logical-time limit")
        frontiers = [step.expect.history_frontier for step in self.schedule]
        if frontiers != sorted(frontiers) or frontiers[-1] != len(self.expected.history_record_types):
            raise ValueError("DST expected History frontiers must be monotone and end at the expected record count")
        if frontiers[-1] > self.limits.history_records:
            raise ValueError("DST expected History exceeds its record limit")
        if sum(len(entry.tokens) for entry in self.initial.marking) > self.limits.retained_tokens:
            raise ValueError("DST initial marking exceeds its retained-token limit")
        observation_names = [observation.name for observation in self.expected.observations]
        if len(observation_names) != len(set(observation_names)):
            raise ValueError("DST expected observation names must be unique")
        checks = [check.property for check in self.expected.checks]
        if len(checks) != len(set(checks)) or self.origin.property not in checks:
            raise ValueError("DST checks must be unique and include the originating property")
        live = True
        for step in self.schedule:
            if isinstance(step.event, CrashEvent):
                if not live:
                    raise ValueError("DST cannot crash an already discarded runtime")
                live = False
            elif isinstance(step.event, RestartEvent):
                if live:
                    raise ValueError("DST cannot restart while the prior runtime is still live")
                live = True
            elif not live:
                raise ValueError("DST must restart immediately after a crash")
        if not live:
            raise ValueError("DST schedule must end with a live runtime")
        return self


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field {key!r}")
        result[key] = value
    return result


def _refuse_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number {value}")


def _strict_bytes(value: object) -> int:
    return len(json.dumps(value, allow_nan=False, separators=(",", ":"), sort_keys=True).encode())


def load_scenario(path: Path) -> ScenarioArtifact:
    """Decode one strict, bounded, closed-vocabulary DST scenario artifact."""

    payload = path.read_bytes()
    try:
        value = json.loads(payload, object_pairs_hook=_strict_object, parse_constant=_refuse_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{path}: invalid strict JSON: {error}") from None
    scenario = ScenarioArtifact.model_validate(value, strict=True)
    if len(payload) > scenario.limits.artifact_bytes:
        raise ValueError(f"{path}: artifact has {len(payload)} bytes; limit is {scenario.limits.artifact_bytes}")
    if _strict_bytes(scenario.initial.model_dump(mode="json")) > scenario.limits.retained_token_bytes:
        raise ValueError(f"{path}: initial marking exceeds its retained-token byte limit")
    return scenario


def _token(value: TokenValue) -> Token:
    return Token(value.color, value.data)


def _marking(entries: list[MarkingEntry]) -> Marking:
    return Marking({NetPath(entry.place): tuple(_token(token) for token in entry.tokens) for entry in entries})


def _encoded_marking(marking: Marking) -> list[dict[str, JsonValue]]:
    return [
        {
            "place": str(place),
            "tokens": [{"color": token.color, "data": token.data} for token in tokens],
        }
        for place, tokens in sorted(marking, key=lambda item: str(item[0]))
    ]


INPUT, DONE, PROJECT = NetPath("input"), NetPath("done"), NetPath("project")


def _application_net() -> Net:
    return Net(
        places=[Place(INPUT), Place(DONE)],
        transitions=[Transition(PROJECT, handler="bridge")],
        arcs=[Arc(INPUT, PROJECT), Arc(PROJECT, DONE)],
        name="dst-projection-recovery",
    )


class _ProjectionBridge:
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


@dataclass(frozen=True)
class ReplayReport:
    scenario_id: str
    property: str
    events_applied: int
    history_frontier: int
    history_record_types: tuple[str, ...]
    snapshot: dict[str, object]
    observations: dict[str, JsonValue]
    checks: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "format": RESULT_FORMAT,
            "version": VERSION,
            "profile": PROFILE,
            "scenario_id": self.scenario_id,
            "property": self.property,
            "outcome": "pass",
            "events_applied": self.events_applied,
            "history_frontier": self.history_frontier,
            "history_record_types": list(self.history_record_types),
            "snapshot": self.snapshot,
            "observations": self.observations,
            "checks": list(self.checks),
        }


def replay_scenario(scenario: ScenarioArtifact) -> ReplayReport:
    """Replay the DS1 projection-crash fixture through fresh production Engines."""

    if scenario.application.profile != APPLICATION_PROFILE:
        raise ValueError(f"unsupported DST application profile {scenario.application.profile!r}")
    if scenario.application.definition_digest != APPLICATION_DIGEST:
        raise ValueError("DST application definition digest does not match projection-recovery-v1")

    with TemporaryDirectory(prefix="petrus-dst-") as directory:
        history_path = Path(directory) / "history.jsonl"
        history = JsonlHistoryStore(history_path)
        dispatch: InMemoryDispatch | None = InMemoryDispatch()
        bridge: _ProjectionBridge | None = _ProjectionBridge()
        engine: Engine | None = Engine.create(
            _application_net(),
            scenario.initial.instance_id,
            history=history,
            dispatch=dispatch,
            marking=_marking(scenario.initial.marking),
            at=scenario.initial.instant,
            handlers={"bridge": bridge},
        )
        first_invocation: ActivityInvocation | None = None
        observations: dict[str, JsonValue] = {}
        accepted_actions = 0
        ready_outcomes = 0
        engine_poisoned = False

        for step in scenario.schedule:
            error: str | None = None
            disposition = "applied"
            frontier_before = len(history)
            for fault in step.faults:
                if fault.kind != "projection_raise" or not isinstance(step.event, DriveEvent):
                    raise ValueError(
                        f"projection-recovery-v1 cannot apply fault {fault.kind!r} to event {step.event.kind!r}"
                    )
                if fault.count != 1 or bridge is None or fault.error is None:
                    raise ValueError("projection-recovery-v1 requires one projection_raise fault on a live bridge")
                bridge.projection_error = fault.error

            try:
                match step.event:
                    case DriveEvent(max_actions=max_actions):
                        if engine is None:
                            raise ValueError("cannot drive without a live Engine")
                        for _ in range(max_actions):
                            outcome = engine.advance()
                            ready_outcomes = 0
                            if outcome.ready or outcome.firings:
                                accepted_actions += 1
                            if dispatch is not None and dispatch.pending and first_invocation is None:
                                first_invocation = next(iter(dispatch.pending.values()))
                            if not outcome.ready:
                                break
                    case DispatchTerminalEvent(occurrence=occurrence, outcome=outcome, value=value):
                        if dispatch is None:
                            raise ValueError("cannot report a Dispatch terminal without a live Dispatch")
                        if outcome == "completed":
                            dispatch.complete(occurrence, value)
                        else:
                            if not isinstance(value, str):
                                raise ValueError("projection-recovery-v1 requires a string failed outcome")
                            dispatch.fail(occurrence, value)
                        ready_outcomes += 1
                    case CrashEvent(cut=cut):
                        if cut == "activity_terminal_frozen":
                            records = history.records
                            if not any(isinstance(record, ActivityCompleted) for record in records) or any(
                                isinstance(record, FiringCompleted) for record in records
                            ):
                                raise ValueError("crash cut is not after terminal freeze and before projection")
                        if engine is not None:
                            engine.close()
                        if bridge is not None:
                            observations["prepared_before_crash"] = bridge.prepared
                            observations["projected_before_crash"] = bridge.projected
                        engine = None
                        dispatch = None
                        bridge = None
                        engine_poisoned = False
                    case RestartEvent():
                        if engine is not None or dispatch is not None or bridge is not None:
                            raise ValueError("restart requires all prior live runtime objects to be discarded")
                        history = JsonlHistoryStore(history_path)
                        dispatch = InMemoryDispatch()
                        bridge = _ProjectionBridge()
                        engine = Engine.load(
                            _application_net(),
                            scenario.initial.instance_id,
                            history=history,
                            dispatch=dispatch,
                            handlers={"bridge": bridge},
                        )
                        engine_poisoned = False
                    case _:
                        raise ValueError(
                            f"projection-recovery-v1 does not implement event {step.event.kind!r}; "
                            "the strict contract admits it for later DS2 profiles"
                        )
            except RuntimeError as caught:
                error = str(caught)
                disposition = "refused_expected"
                ready_outcomes = 0
                if isinstance(step.event, DriveEvent) and len(history) > frontier_before:
                    accepted_actions += 1
                    engine_poisoned = True

            if disposition != step.expect.disposition or error != step.expect.error:
                raise AssertionError(
                    f"step {step.position} expected {step.expect.disposition}/{step.expect.error!r}, "
                    f"observed {disposition}/{error!r}"
                )
            if len(history) != step.expect.history_frontier:
                raise AssertionError(
                    f"step {step.position} expected History frontier {step.expect.history_frontier}, found {len(history)}"
                )
            if accepted_actions > scenario.limits.total_actions:
                raise AssertionError("DST replay exceeded its total accepted-action limit")
            if history_path.exists() and history_path.stat().st_size > scenario.limits.history_payload_bytes:
                raise AssertionError("DST replay exceeded its History payload byte limit")
            if (
                engine is not None
                and not engine_poisoned
                and len(engine.in_flight) > scenario.limits.in_flight_activities
            ):
                raise AssertionError("DST replay exceeded its in-flight Activity limit")
            if ready_outcomes > scenario.limits.pending_outcomes:
                raise AssertionError("DST replay exceeded its pending collaborator-outcome limit")
            if engine is not None and not engine_poisoned:
                retained_tokens = sum(len(tokens) for _, tokens in engine.marking)
                if retained_tokens > scenario.limits.retained_tokens:
                    raise AssertionError("DST replay exceeded its retained-token limit")
                if _strict_bytes(_encoded_marking(engine.marking)) > scenario.limits.retained_token_bytes:
                    raise AssertionError("DST replay exceeded its retained-token byte limit")

        if engine is None or dispatch is None or bridge is None:
            raise AssertionError("DST scenario ended without a live reconstructed Engine")
        observations.update(
            {
                "prepared_after_restart": bridge.prepared,
                "projected_after_restart": bridge.projected,
                "dispatch_pending_after_restart": len(dispatch.pending),
            }
        )
        current = engine.snapshot()["current"]
        snapshot = {
            "marking": _encoded_marking(engine.marking),
            "status": current["status"],
            "watermark": current["watermark"],
            "in_flight": [entry["occurrence"] for entry in current["in_flight"]],
        }
        record_types = tuple(type(record).__name__ for record in history.records)
        actual_disposition = "terminal" if snapshot["status"] in ("terminated", "completed") else "quiescent"

        expected_snapshot = scenario.expected.snapshot.model_dump(mode="json")
        if snapshot != expected_snapshot:
            raise AssertionError(f"expected final snapshot {expected_snapshot!r}, found {snapshot!r}")
        if record_types != tuple(scenario.expected.history_record_types):
            raise AssertionError("final History record types do not match the scenario")
        if actual_disposition != scenario.expected.disposition:
            raise AssertionError(
                f"expected final disposition {scenario.expected.disposition!r}, found {actual_disposition!r}"
            )
        expected_observations = {entry.name: entry.value for entry in scenario.expected.observations}
        if observations != expected_observations:
            raise AssertionError(f"expected observations {expected_observations!r}, found {observations!r}")

        requested = [record for record in history.records if isinstance(record, ActivityRequested)]
        completed = [record for record in history.records if isinstance(record, ActivityCompleted)]
        completion_position = next(
            index for index, record in enumerate(history.records) if isinstance(record, ActivityCompleted)
        )
        projection_position = next(
            index for index, record in enumerate(history.records) if isinstance(record, FiringCompleted)
        )
        computed_checks = {
            "S3-stable-invocation": len(requested) == 1
            and first_invocation is not None
            and ActivityInvocation(
                requested[0].activity,
                input=requested[0].input,
                policy=requested[0].policy,
                correlation=requested[0].correlation,
                idempotency=requested[0].idempotency,
            )
            == first_invocation,
            "S4-terminal-before-projection": len(completed) == 1
            and completion_position < projection_position
            and observations["prepared_after_restart"] == 0
            and observations["projected_after_restart"] == 1,
        }

        engine.close()
        final_bridge = _ProjectionBridge()
        final_engine = Engine.load(
            _application_net(),
            scenario.initial.instance_id,
            history=JsonlHistoryStore(history_path),
            dispatch=InMemoryDispatch(),
            handlers={"bridge": final_bridge},
        )
        computed_checks["S1-replay-agreement"] = final_engine.snapshot()["current"] == current
        final_engine.close()

        expected_checks = tuple(check.property for check in scenario.expected.checks)
        if any(not computed_checks.get(check, False) for check in expected_checks):
            raise AssertionError(f"DST checker failure: {computed_checks!r}")
        if scenario.origin.property not in expected_checks:
            raise AssertionError("the originating property must be among the replay checks")

        return ReplayReport(
            scenario_id=scenario.scenario_id,
            property=scenario.origin.property,
            events_applied=len(scenario.schedule),
            history_frontier=len(history),
            history_record_types=record_types,
            snapshot=snapshot,
            observations=observations,
            checks=expected_checks,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", type=Path, help="strict petrus-dst-scenario JSON artifact")
    arguments = parser.parse_args()
    report = replay_scenario(load_scenario(arguments.scenario))
    print(json.dumps(report.as_dict(), allow_nan=False, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
