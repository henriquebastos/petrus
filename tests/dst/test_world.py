"""CV19.DS2 supported World/Timeline vertical slice."""

from __future__ import annotations

import inspect
import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

import petrus
from petrus.testing import dst
from petrus.testing.dst import (
    API_COMPATIBILITY,
    ARTIFACT_FORMAT,
    ARTIFACT_VERSION,
    LEGACY_API_COMPATIBILITY,
    LEGACY_ARTIFACT_VERSION,
    PREVIOUS_API_COMPATIBILITY,
    PREVIOUS_ARTIFACT_VERSION,
    RESULT_VERSION,
    ActionDisposition,
    ApplyResult,
    Budget,
    BudgetExhausted,
    CheckResult,
    CheckerIdentity,
    ChoiceAuthority,
    ChoiceStreams,
    Command,
    Disposition,
    DstError,
    FailureOperation,
    GenerationStart,
    InvariantViolation,
    Observation,
    ObservationRequest,
    PendingWork,
    ProfileIdentity,
    ReplayMismatch,
    RunUntilFailed,
    ScenarioRegistry,
    ScenarioArtifactV1,
    ScenarioArtifactV2,
    ScheduledCommand,
    ScenarioContext,
    StaleGeneration,
    World,
    decode_artifact,
    encode_artifact,
    load_artifact,
    replay,
)
from tests.dst.engine_world import (
    BUDGET_FAILURE_SCENARIO_ID,
    CHECKER_IDENTITY,
    INVARIANT_FAILURE_SCENARIO_ID,
    LEGACY_SCENARIO_ID,
    PROFILE_IDENTITY,
    SCENARIO_ID,
    SCENARIO_SEED,
    SEEDED_SCENARIO_ID,
    WORLD_BUDGET,
    EngineHistoryChecker,
    EngineProfile,
    TerminalRefusalChecker,
    build_budget_failure_artifact,
    build_invariant_failure_artifact,
    build_projection_artifact,
    build_seeded_projection_artifact,
    execute_projection_story,
)

LEGACY_FIXTURE = Path("tests/dst/fixtures/projection-crash-recovery-world-v1.json")
BUDGET_FAILURE_FIXTURE = Path("tests/dst/fixtures/action-budget-exhaustion-world-v2.json")
INVARIANT_FAILURE_FIXTURE = Path("tests/dst/fixtures/terminal-checker-failure-world-v2.json")
SEEDED_FIXTURE = Path("tests/dst/fixtures/seeded-projection-crash-recovery-world-v3.json")


class QueueProfile:
    identity = ProfileIdentity(
        name="petrus.testing.queue-proof",
        version=1,
        digest=dst.digest_json({"command": "queue.record", "observation": "queue.state"}),
    )

    def __init__(self):
        self.values = []
        self.closes = 0

    def validate(self, command: Command) -> Command:
        if command.name != "queue.record" or not isinstance(command.payload, dict):
            raise ValueError("queue proof accepts only queue.record objects")
        return command

    def validate_fault(self, fault):
        raise ValueError("queue proof does not accept faults")

    def create(self, context: ScenarioContext) -> GenerationStart[list[str]]:
        commands = tuple(
            ScheduledCommand(
                instant=5,
                command=Command(
                    profile=self.identity,
                    name="queue.record",
                    payload={"id": context.stable_id("queue")},
                ),
            )
            for _ in range(2)
        )
        return GenerationStart(self.values, commands)

    def load(self, context: ScenarioContext) -> GenerationStart[list[str]]:
        del context
        return GenerationStart(self.values)

    def apply(self, generation, command: Command, context: ScenarioContext) -> ApplyResult:
        del context
        identifier = command.payload["id"]
        assert isinstance(identifier, str)
        generation.append(identifier)
        return ApplyResult(
            disposition=ActionDisposition.APPLIED.value,
            value={"values": list(generation)},
            scheduled=[],
        )

    def observe(self, generation, request: ObservationRequest, context: ScenarioContext):
        del context
        if request.name != "queue.state":
            raise ValueError("unknown queue proof observation")
        return {"values": list(generation)}

    def drop(self, generation) -> None:
        del generation

    def close(self, generation) -> None:
        del generation
        self.closes += 1


class RejectingChecker:
    identity = CheckerIdentity(
        name="petrus.testing.rejecting-checker",
        version=1,
        digest=dst.digest_json({"result": "reject"}),
    )
    request = ObservationRequest(name="queue.state", payload={})

    def check(self, observation: Observation) -> CheckResult:
        return CheckResult(passed=False, detail={"values": observation.value})


class RejectBadValueChecker:
    identity = CheckerIdentity(
        name="petrus.testing.reject-bad-value",
        version=1,
        digest=dst.digest_json({"property": "queue values never contain bad"}),
    )
    request = ObservationRequest(name="queue.state", payload={})

    def check(self, observation: Observation) -> CheckResult:
        value = observation.value
        assert isinstance(value, dict)
        values = value["values"]
        assert isinstance(values, list)
        return CheckResult(passed="bad" not in values, detail={"values": values})


class PassingBadValueChecker(RejectBadValueChecker):
    def check(self, observation: Observation) -> CheckResult:
        value = observation.value
        assert isinstance(value, dict)
        values = value["values"]
        assert isinstance(values, list)
        return CheckResult(passed=True, detail={"values": values})


class RaisingReservedExceptionChecker:
    identity = CheckerIdentity(
        name="petrus.testing.raises-reserved-exception",
        version=1,
        digest=dst.digest_json({"bug": "raises instead of returning a check result"}),
    )
    request = ObservationRequest(name="queue.state", payload={})

    def check(self, observation: Observation) -> CheckResult:
        value = observation.value
        assert isinstance(value, dict)
        values = value["values"]
        assert isinstance(values, list)
        if values:
            raise InvariantViolation("checker implementation raised the reserved exception")
        return CheckResult(passed=True, detail={"values": values})


class RaisingReservedExceptionProfile(QueueProfile):
    def apply(self, generation, command: Command, context: ScenarioContext) -> ApplyResult:
        del generation, command, context
        raise BudgetExhausted("profile-owned", 1)


def test_world_owns_stable_ids_total_tie_order_and_logical_time() -> None:
    budget = Budget(
        actions=4,
        queued_commands=2,
        timer_advances=1,
        logical_instant=5,
        reloads=0,
        predicate_polls=1,
        artifact_bytes=65_536,
    )
    profile = QueueProfile()
    world = World(profile, budget)
    timeline = world.timeline()
    first = world.step()
    second = world.step()
    observation = timeline.observe("queue.state")
    timeline.finish(Disposition.QUIESCENT)
    artifact = world.artifact("stable-order-v1")
    world.close()

    assert (first.instant, first.queue_order, second.instant, second.queue_order) == (5, 0, 5, 1)
    assert observation.value == {"values": ["queue-00000001", "queue-00000002"]}

    registry = ScenarioRegistry()
    registry.register_profile(QueueProfile())
    result = replay(artifact, registry)
    assert result.outcome == "pass"
    assert result.disposition == Disposition.QUIESCENT.value


def test_predicate_poll_budget_ends_explicitly(tmp_path: Path) -> None:
    budget = Budget(
        actions=3,
        queued_commands=2,
        timer_advances=0,
        logical_instant=0,
        reloads=0,
        predicate_polls=1,
        artifact_bytes=65_536,
    )
    world = World(EngineProfile(tmp_path / "bounded-history.jsonl"), budget)
    timeline = world.timeline()
    try:
        with pytest.raises(BudgetExhausted, match="predicate_polls"):
            timeline.run_until("activity-requested", lambda observation: False)
        assert world.disposition is Disposition.BUDGET_EXHAUSTED
    finally:
        world.close()


def test_constructor_closes_an_installed_generation_when_initial_checker_refuses() -> None:
    profile = QueueProfile()

    with pytest.raises(InvariantViolation, match="rejecting-checker"):
        World(
            profile,
            Budget(
                actions=8,
                queued_commands=2,
                timer_advances=1,
                logical_instant=5,
                reloads=0,
                predicate_polls=1,
                artifact_bytes=65_536,
            ),
            checkers=(RejectingChecker(),),
        )

    assert profile.closes == 1


@pytest.mark.parametrize(
    "disposition",
    [Disposition.CONVERGED, Disposition.QUIESCENT, Disposition.EXTERNAL_WAIT, Disposition.QUARANTINED],
)
def test_every_authored_finish_refuses_scheduled_work(disposition: Disposition) -> None:
    world = World(
        QueueProfile(),
        Budget(
            actions=2,
            queued_commands=2,
            timer_advances=1,
            logical_instant=5,
            reloads=0,
            predicate_polls=1,
            artifact_bytes=65_536,
        ),
    )
    try:
        with pytest.raises(PendingWork):
            world.timeline().finish(disposition)
    finally:
        world.close()


def test_fair_phase_drains_profile_work_without_new_authored_interference() -> None:
    world = World(
        QueueProfile(),
        Budget(
            actions=8,
            queued_commands=2,
            timer_advances=1,
            logical_instant=5,
            reloads=0,
            predicate_polls=1,
            artifact_bytes=65_536,
        ),
    )
    timeline = world.timeline()
    try:
        world.step()
        world.step()
        timeline.begin_fair()

        with pytest.raises(DstError, match="authored commands"):
            timeline.command("queue.record", {"id": "late"})
        with pytest.raises(DstError, match="faults"):
            timeline.activate_fault("late", "cut")
        with pytest.raises(DstError, match="process crashes"):
            timeline.crash("cut")
        with pytest.raises(DstError, match="already begun"):
            timeline.begin_fair()
        with pytest.raises(DstError, match="external wait"):
            timeline.finish(Disposition.EXTERNAL_WAIT)

        timeline.finish(Disposition.QUIESCENT)
    finally:
        world.close()


def test_profile_validates_fault_when_it_is_activated() -> None:
    world = World(
        QueueProfile(),
        Budget(
            actions=2,
            queued_commands=2,
            timer_advances=1,
            logical_instant=5,
            reloads=0,
            predicate_polls=1,
            artifact_bytes=65_536,
        ),
    )
    try:
        with pytest.raises(ValueError, match="does not accept faults"):
            world.timeline().activate_fault("unsupported", "cut")
        assert all(operation.kind != "activate_fault" for operation in world.operations)
    finally:
        world.close()


def test_generation_start_requires_detached_scheduled_values() -> None:
    with pytest.raises(TypeError, match="tuple of ScheduledCommand"):
        GenerationStart([], [])  # type: ignore[arg-type]


def test_action_timer_and_logical_time_budgets_end_explicitly() -> None:
    action_world = World(
        QueueProfile(),
        Budget(
            actions=1,
            queued_commands=2,
            timer_advances=1,
            logical_instant=5,
            reloads=0,
            predicate_polls=1,
            artifact_bytes=65_536,
        ),
    )
    try:
        action_world.step()
        with pytest.raises(BudgetExhausted, match="actions"):
            action_world.step()
        artifact = action_world.artifact("budget-exhaustion")
        assert artifact.expected.disposition == Disposition.BUDGET_EXHAUSTED.value
        assert isinstance(artifact.operations[-1], FailureOperation)
    finally:
        action_world.close()

    timer_world = World(
        QueueProfile(),
        Budget(
            actions=1,
            queued_commands=2,
            timer_advances=0,
            logical_instant=5,
            reloads=0,
            predicate_polls=1,
            artifact_bytes=65_536,
        ),
    )
    try:
        with pytest.raises(BudgetExhausted, match="timer_advances"):
            timer_world.step()
    finally:
        timer_world.close()

    profile = QueueProfile()
    with pytest.raises(BudgetExhausted, match="logical_instant"):
        World(
            profile,
            Budget(
                actions=1,
                queued_commands=2,
                timer_advances=1,
                logical_instant=4,
                reloads=0,
                predicate_polls=1,
                artifact_bytes=65_536,
            ),
        )
    assert profile.closes == 1


def test_queue_reload_and_artifact_byte_budgets_end_explicitly() -> None:
    profile = QueueProfile()
    with pytest.raises(BudgetExhausted, match="queued_commands"):
        World(
            profile,
            Budget(
                actions=1,
                queued_commands=1,
                timer_advances=1,
                logical_instant=5,
                reloads=0,
                predicate_polls=1,
                artifact_bytes=65_536,
            ),
        )
    assert profile.closes == 1

    reload_world = World(
        QueueProfile(),
        Budget(
            actions=2,
            queued_commands=2,
            timer_advances=1,
            logical_instant=5,
            reloads=0,
            predicate_polls=1,
            artifact_bytes=65_536,
        ),
    )
    reload_world.timeline().crash("cut")
    with pytest.raises(BudgetExhausted, match="reloads"):
        reload_world.restart()
    reload_world.close()

    value = json.loads(LEGACY_FIXTURE.read_bytes())
    value["budget"]["artifact_bytes"] = 1
    artifact = ScenarioArtifactV1.model_validate(value, strict=True)
    with pytest.raises(ValueError, match="artifact has"):
        encode_artifact(artifact)


def test_executable_story_generates_a_strict_version_three_artifact(tmp_path: Path) -> None:
    artifact = build_projection_artifact(tmp_path / "authored-history.jsonl")

    assert artifact.format == ARTIFACT_FORMAT
    assert artifact.version == ARTIFACT_VERSION
    assert artifact.api == API_COMPATIBILITY
    assert artifact.scenario_id == SCENARIO_ID
    assert artifact.profile == PROFILE_IDENTITY
    assert artifact.checkers == [CHECKER_IDENTITY]
    assert artifact.origin is None
    assert decode_artifact(encode_artifact(artifact)) == artifact


def test_choice_authorities_are_repeatable_and_stream_isolated() -> None:
    first = ChoiceStreams(SCENARIO_SEED)
    second = ChoiceStreams(SCENARIO_SEED)

    first_workload = [first.index(ChoiceAuthority.WORKLOAD, 1_000) for _ in range(4)]
    second_workload = [second.index(ChoiceAuthority.WORKLOAD, 1_000) for _ in range(4)]
    assert first_workload == second_workload == [584, 541, 292, 147]
    assert (
        first.identifier("scenario") == second.identifier("scenario") == ("scenario-4a6cb3d68a08da140c56fd1ed8bcbce2")
    )

    baseline = ChoiceStreams(SCENARIO_SEED)
    perturbed = ChoiceStreams(SCENARIO_SEED)
    baseline_workload = [baseline.index(ChoiceAuthority.WORKLOAD, 1_000) for _ in range(2)]
    first_perturbed = perturbed.index(ChoiceAuthority.WORKLOAD, 1_000)
    for _ in range(8):
        perturbed.index(ChoiceAuthority.FAULT, 17)
    perturbed.identifier("diagnostic")
    perturbed.index(ChoiceAuthority.EVENT_ORDER, 5)
    second_perturbed = perturbed.index(ChoiceAuthority.WORKLOAD, 1_000)

    assert [first_perturbed, second_perturbed] == baseline_workload
    assert perturbed.provenance().draws == {
        "event_order": 1,
        "fault": 8,
        "identifier:diagnostic": 1,
        "workload": 2,
    }

    baseline_ids = ChoiceStreams(SCENARIO_SEED)
    perturbed_ids = ChoiceStreams(SCENARIO_SEED)
    expected_ids = [baseline_ids.identifier("scenario") for _ in range(2)]
    first_id = perturbed_ids.identifier("scenario")
    for _ in range(8):
        perturbed_ids.identifier("diagnostic")
    second_id = perturbed_ids.identifier("scenario")
    assert [first_id, second_id] == expected_ids


def test_choice_authorities_refuse_implicit_or_malformed_inputs() -> None:
    with pytest.raises(ValueError, match="choice seed"):
        ChoiceStreams(True)

    choices = ChoiceStreams(SCENARIO_SEED)
    with pytest.raises(AttributeError):
        choices.seed = SCENARIO_SEED + 1  # type: ignore[misc]
    with pytest.raises(AttributeError):
        choices.algorithm = "other"  # type: ignore[misc]
    with pytest.raises(TypeError, match="ChoiceAuthority"):
        choices.index("workload", 2)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match=r"identifier\(\)"):
        choices.index(ChoiceAuthority.IDENTIFIER, 2)
    with pytest.raises(ValueError, match="integer from 1"):
        choices.index(ChoiceAuthority.WORKLOAD, True)
    with pytest.raises(ValueError, match="integer from 1"):
        choices.index(ChoiceAuthority.WORKLOAD, 2**53)
    with pytest.raises(ValueError, match="identifier namespace"):
        choices.identifier("")

    provenance = ChoiceStreams(SCENARIO_SEED).provenance().model_dump(mode="json")
    provenance["draws"] = {"workload": 2**53}
    with pytest.raises(ValidationError, match="JSON-portable"):
        dst.ChoiceProvenance.model_validate(provenance, strict=True)

    world = World(
        QueueProfile(),
        Budget(
            actions=2,
            queued_commands=2,
            timer_advances=1,
            logical_instant=5,
            reloads=0,
            predicate_polls=1,
            artifact_bytes=65_536,
        ),
    )
    try:
        with pytest.raises(DstError, match="no seeded choice authorities"):
            _ = world.choices
    finally:
        world.close()


def test_seeded_story_is_exact_and_replay_uses_expanded_operations(tmp_path: Path) -> None:
    first = build_seeded_projection_artifact(tmp_path / "seeded-first.jsonl")
    second = build_seeded_projection_artifact(tmp_path / "seeded-second.jsonl")

    assert first == second
    assert first.scenario_id == SEEDED_SCENARIO_ID
    assert first.origin is not None
    assert first.origin.seed == SCENARIO_SEED
    assert first.origin.draws == {
        "event_order": 1,
        "fault": 1,
        "identifier:scenario": 1,
        "workload": 1,
    }
    assert encode_artifact(first) == SEEDED_FIXTURE.read_bytes().rstrip(b"\n")

    value = json.loads(SEEDED_FIXTURE.read_bytes())
    value["origin"]["seed"] = SCENARIO_SEED + 1
    changed_provenance = decode_artifact(json.dumps(value, allow_nan=False).encode())
    registry = ScenarioRegistry()
    registry.register_profile(EngineProfile(tmp_path / "seeded-replay.jsonl"))
    registry.register_checker(EngineHistoryChecker())
    result = replay(changed_provenance, registry)

    assert result.version == RESULT_VERSION
    assert result.scenario_id == SEEDED_SCENARIO_ID
    assert result.disposition == Disposition.CONVERGED.value
    assert result.operations == len(first.operations)


def test_seeded_manual_replay_route_is_deterministic() -> None:
    command = [sys.executable, "-m", "tests.dst.replay_world", str(SEEDED_FIXTURE)]
    first = subprocess.run(command, check=True, capture_output=True, text=True)
    second = subprocess.run(command, check=True, capture_output=True, text=True)

    assert first.stderr == second.stderr == ""
    assert first.stdout == second.stdout
    result = json.loads(first.stdout)
    assert result["version"] == RESULT_VERSION
    assert result["scenario_id"] == SEEDED_SCENARIO_ID
    assert result["outcome"] == "pass"


def test_legacy_version_one_artifact_remains_byte_exact() -> None:
    artifact = load_artifact(LEGACY_FIXTURE)

    assert isinstance(artifact, ScenarioArtifactV1)
    assert artifact.version == LEGACY_ARTIFACT_VERSION
    assert artifact.api == LEGACY_API_COMPATIBILITY
    assert artifact.scenario_id == LEGACY_SCENARIO_ID
    assert encode_artifact(artifact) == LEGACY_FIXTURE.read_bytes().rstrip(b"\n")


def test_retained_artifact_replays_through_the_same_interpreter(tmp_path: Path) -> None:
    registry = ScenarioRegistry()
    profile = EngineProfile(tmp_path / "replay-history.jsonl")
    registry.register_profile(profile)
    registry.register_checker(EngineHistoryChecker())

    result = replay(load_artifact(LEGACY_FIXTURE), registry)

    assert result.outcome == "pass"
    assert result.disposition == Disposition.CONVERGED.value
    assert result.operations == 15
    assert profile.drops == 1
    assert profile.closes == 1


def test_legacy_manual_replay_route_is_deterministic() -> None:
    command = [sys.executable, "-m", "tests.dst.replay_world", str(LEGACY_FIXTURE)]
    first = subprocess.run(command, check=True, capture_output=True, text=True)
    second = subprocess.run(command, check=True, capture_output=True, text=True)

    result = json.loads(first.stdout)
    assert first.stderr == second.stderr == ""
    assert first.stdout == second.stdout
    assert result["format"] == "petrus-dst-world-replay-result"
    assert result["scenario_id"] == LEGACY_SCENARIO_ID
    assert result["outcome"] == "pass"
    assert "failure" not in result


@pytest.mark.parametrize(
    ("build", "scenario_id", "disposition", "operations"),
    [
        (
            build_budget_failure_artifact,
            BUDGET_FAILURE_SCENARIO_ID,
            Disposition.BUDGET_EXHAUSTED,
            2,
        ),
        (
            build_invariant_failure_artifact,
            INVARIANT_FAILURE_SCENARIO_ID,
            Disposition.INVARIANT_FAILURE,
            6,
        ),
    ],
)
def test_failed_attempt_artifacts_are_exact_and_replayable(
    tmp_path: Path,
    build,
    scenario_id: str,
    disposition: Disposition,
    operations: int,
) -> None:
    artifact = build(tmp_path / f"author-{scenario_id}.jsonl")
    assert artifact.version == ARTIFACT_VERSION
    assert artifact.origin is None
    assert artifact.expected.disposition == disposition.value
    assert artifact.expected.failure is not None
    assert isinstance(artifact.operations[-1], FailureOperation)

    registry = ScenarioRegistry()
    registry.register_profile(EngineProfile(tmp_path / f"replay-{scenario_id}.jsonl"))
    registry.register_checker(EngineHistoryChecker())
    registry.register_checker(TerminalRefusalChecker())
    result = replay(artifact, registry)

    assert result.version == RESULT_VERSION
    assert result.scenario_id == scenario_id
    assert result.outcome == "pass"
    assert result.disposition == disposition.value
    assert result.failure == artifact.expected.failure
    assert result.operations == operations


@pytest.mark.parametrize(
    ("fixture", "scenario_id", "disposition", "operations"),
    [
        (
            BUDGET_FAILURE_FIXTURE,
            BUDGET_FAILURE_SCENARIO_ID,
            Disposition.BUDGET_EXHAUSTED,
            2,
        ),
        (
            INVARIANT_FAILURE_FIXTURE,
            INVARIANT_FAILURE_SCENARIO_ID,
            Disposition.INVARIANT_FAILURE,
            6,
        ),
    ],
)
def test_retained_version_two_failure_artifacts_remain_exact_and_replayable(
    tmp_path: Path,
    fixture: Path,
    scenario_id: str,
    disposition: Disposition,
    operations: int,
) -> None:
    artifact = load_artifact(fixture)
    assert isinstance(artifact, ScenarioArtifactV2)
    assert artifact.version == PREVIOUS_ARTIFACT_VERSION
    assert artifact.api == PREVIOUS_API_COMPATIBILITY
    assert encode_artifact(artifact) == fixture.read_bytes().rstrip(b"\n")

    registry = ScenarioRegistry()
    registry.register_profile(EngineProfile(tmp_path / f"replay-v2-{scenario_id}.jsonl"))
    registry.register_checker(EngineHistoryChecker())
    registry.register_checker(TerminalRefusalChecker())
    result = replay(artifact, registry)

    assert result.version == RESULT_VERSION
    assert result.scenario_id == scenario_id
    assert result.disposition == disposition.value
    assert result.operations == operations


def test_authored_command_checker_failure_replays_the_submit_attempt() -> None:
    budget = Budget(
        actions=4,
        queued_commands=2,
        timer_advances=1,
        logical_instant=5,
        reloads=0,
        predicate_polls=1,
        artifact_bytes=65_536,
    )
    world = World(QueueProfile(), budget, checkers=(RejectBadValueChecker(),))
    timeline = world.timeline()
    try:
        world.step()
        world.step()
        with pytest.raises(InvariantViolation, match="reject-bad-value"):
            timeline.command("queue.record", {"id": "bad"})
        artifact = world.artifact("authored-checker-failure")
    finally:
        world.close()

    failure = artifact.operations[-1]
    assert isinstance(failure, FailureOperation)
    assert failure.attempt.kind == "submit"
    assert failure.accepted_operations == 1

    registry = ScenarioRegistry()
    registry.register_profile(QueueProfile())
    registry.register_checker(RejectBadValueChecker())
    result = replay(artifact, registry)
    assert result.disposition == Disposition.INVARIANT_FAILURE.value
    assert result.failure == artifact.expected.failure


def test_replay_does_not_apply_an_accepted_failed_attempt_twice() -> None:
    budget = Budget(
        actions=4,
        queued_commands=2,
        timer_advances=1,
        logical_instant=5,
        reloads=0,
        predicate_polls=1,
        artifact_bytes=65_536,
    )
    world = World(QueueProfile(), budget, checkers=(RejectBadValueChecker(),))
    try:
        world.step()
        world.step()
        with pytest.raises(InvariantViolation, match="reject-bad-value"):
            world.timeline().command("queue.record", {"id": "bad"})
        artifact = world.artifact("accepted-failed-attempt")
    finally:
        world.close()

    replay_profile = QueueProfile()
    registry = ScenarioRegistry()
    registry.register_profile(replay_profile)
    registry.register_checker(PassingBadValueChecker())
    with pytest.raises(ReplayMismatch, match="did not reproduce its terminal failed attempt"):
        replay(artifact, registry)

    assert replay_profile.values == ["queue-00000001", "queue-00000002", "bad"]


def test_profile_and_checker_exceptions_are_not_reclassified_as_world_failures() -> None:
    budget = Budget(
        actions=4,
        queued_commands=2,
        timer_advances=1,
        logical_instant=5,
        reloads=0,
        predicate_polls=1,
        artifact_bytes=65_536,
    )
    profile_world = World(RaisingReservedExceptionProfile(), budget)
    try:
        with pytest.raises(BudgetExhausted, match="profile-owned"):
            profile_world.step()
        assert profile_world.disposition is None
        assert all(not isinstance(operation, FailureOperation) for operation in profile_world.operations)
        assert all(entry.kind != "failure" for entry in profile_world.journal)
    finally:
        profile_world.close()

    checker_world = World(QueueProfile(), budget, checkers=(RaisingReservedExceptionChecker(),))
    try:
        with pytest.raises(InvariantViolation, match="checker implementation"):
            checker_world.step()
        assert checker_world.disposition is None
        assert all(not isinstance(operation, FailureOperation) for operation in checker_world.operations)
        assert all(entry.kind != "failure" for entry in checker_world.journal)
    finally:
        checker_world.close()


@pytest.mark.parametrize(
    ("fixture", "disposition"),
    [
        (BUDGET_FAILURE_FIXTURE, Disposition.BUDGET_EXHAUSTED),
        (INVARIANT_FAILURE_FIXTURE, Disposition.INVARIANT_FAILURE),
    ],
)
def test_failed_attempt_manual_replay_is_deterministic(fixture: Path, disposition: Disposition) -> None:
    command = [sys.executable, "-m", "tests.dst.replay_world", str(fixture)]
    first = subprocess.run(command, check=True, capture_output=True, text=True)
    second = subprocess.run(command, check=True, capture_output=True, text=True)

    result = json.loads(first.stdout)
    assert first.stderr == second.stderr == ""
    assert first.stdout == second.stdout
    assert result["version"] == RESULT_VERSION
    assert result["disposition"] == disposition.value
    assert result["failure"]["kind"] == disposition.value


def test_crash_revokes_before_drop_and_close_remains_distinct(tmp_path: Path) -> None:
    world, profile, stale = execute_projection_story(tmp_path / "generation-history.jsonl")
    try:
        assert profile.drops == 1
        assert profile.closes == 0
        with pytest.raises(StaleGeneration, match="generation 1 is stale"):
            stale.command("engine.drive", {})
    finally:
        world.close()

    assert profile.closes == 1


def test_checker_runs_after_create_actions_crash_and_fresh_load(tmp_path: Path) -> None:
    world, _, _ = execute_projection_story(tmp_path / "checker-history.jsonl")
    try:
        triggers = [
            entry.value["trigger"] for entry in world.journal if entry.kind == "check" and isinstance(entry.value, dict)
        ]
    finally:
        world.close()

    assert triggers == [
        "create",
        "engine.drive",
        "fault:projection.raise",
        "engine.complete",
        "engine.drive",
        "crash:activity_terminal_frozen",
        "load",
        "begin_fair",
        "engine.drive",
    ]


def test_run_until_external_wait_has_checkpoint_diagnostics(tmp_path: Path) -> None:
    profile = EngineProfile(tmp_path / "wait-history.jsonl")
    world = World(profile, WORLD_BUDGET)
    timeline = world.timeline()
    try:
        timeline.run_until(
            "activity-requested",
            lambda observation: isinstance(observation.value, dict) and observation.value["pending"] == [1],
        )
        with pytest.raises(RunUntilFailed) as caught:
            timeline.run_until("terminal", lambda observation: observation.value == {"impossible": True})
    finally:
        world.close()

    assert caught.value.disposition is Disposition.EXTERNAL_WAIT
    assert caught.value.pending == []
    assert caught.value.observation.name == "terminal"
    assert "journal_tail=" in str(caught.value)


def test_supported_surface_has_no_root_reexports_or_private_runtime_handles() -> None:
    assert not hasattr(petrus, "World")
    assert not hasattr(petrus, "ScenarioProfile")
    assert "Coordinator" not in dst.__all__
    assert "Engine" not in dst.__all__
    assert not hasattr(dst.ScenarioContext, "schedule")
    assert not hasattr(dst.ScenarioContext, "submit")
    assert not hasattr(dst.ScenarioContext, "choices")
    assert set(inspect.signature(dst.ScenarioProfile.apply).parameters) == {
        "self",
        "generation",
        "command",
        "context",
    }


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update({"unknown": True}),
        lambda value: value.update({"api": "petrus.testing.dst/v2"}),
        lambda value: value["profile"].update({"digest": "sha256:" + "0" * 64}),
        lambda value: value["operations"][0].update({"position": 99}),
        lambda value: value["operations"][0]["observation"].update({"generation": True}),
        lambda value: value["budget"].update({"actions": True}),
    ],
)
def test_unknown_mismatched_or_non_strict_artifacts_refuse(mutate) -> None:
    value = deepcopy(json.loads(LEGACY_FIXTURE.read_bytes()))
    mutate(value)

    with pytest.raises((ValidationError, ValueError)):
        decode_artifact(json.dumps(value, allow_nan=False).encode())


def test_duplicate_and_nonfinite_artifact_data_refuses() -> None:
    with pytest.raises(ValueError, match="duplicate JSON field"):
        decode_artifact(b'{"format":"petrus-dst-world","format":"other"}')
    with pytest.raises(ValueError, match="non-finite JSON number"):
        decode_artifact(b'{"value":NaN}')


def test_version_two_failure_artifact_requires_one_exact_terminal_failure() -> None:
    value = deepcopy(json.loads(INVARIANT_FAILURE_FIXTURE.read_bytes()))
    value["operations"].pop()

    with pytest.raises(ValidationError, match="exactly one failure operation"):
        decode_artifact(json.dumps(value, allow_nan=False).encode())

    value = deepcopy(json.loads(BUDGET_FAILURE_FIXTURE.read_bytes()))
    value["operations"][-1]["accepted_operations"] = 1
    with pytest.raises(ValidationError, match="does not identify its accepted operation"):
        decode_artifact(json.dumps(value, allow_nan=False).encode())


def test_failure_replay_refuses_a_changed_expected_failure_location(tmp_path: Path) -> None:
    value = deepcopy(json.loads(BUDGET_FAILURE_FIXTURE.read_bytes()))
    changed = "DST budget 'actions' exhausted somewhere else"
    value["operations"][-1]["failure"]["error"] = changed
    value["expected"]["failure"]["error"] = changed
    artifact = decode_artifact(json.dumps(value, allow_nan=False).encode())
    registry = ScenarioRegistry()
    registry.register_profile(EngineProfile(tmp_path / "changed-failure.jsonl"))

    with pytest.raises(ReplayMismatch, match="operation 1 diverged"):
        replay(artifact, registry)


def test_replay_fails_closed_on_manifest_or_journal_digest_mismatch(tmp_path: Path) -> None:
    checker_value = deepcopy(json.loads(LEGACY_FIXTURE.read_bytes()))
    checker_value["checkers"][0]["version"] = 2
    checker_artifact = decode_artifact(json.dumps(checker_value, allow_nan=False).encode())
    registry = ScenarioRegistry()
    registry.register_profile(EngineProfile(tmp_path / "checker-mismatch.jsonl"))
    registry.register_checker(EngineHistoryChecker())

    with pytest.raises(ValueError, match="checker is not registered exactly"):
        replay(checker_artifact, registry)

    digest_value = deepcopy(json.loads(LEGACY_FIXTURE.read_bytes()))
    digest_value["expected"]["journal_digest"] = "sha256:" + "0" * 64
    digest_artifact = decode_artifact(json.dumps(digest_value, allow_nan=False).encode())
    digest_registry = ScenarioRegistry()
    digest_registry.register_profile(EngineProfile(tmp_path / "digest-mismatch.jsonl"))
    digest_registry.register_checker(EngineHistoryChecker())

    with pytest.raises(ReplayMismatch, match="journal digest diverged"):
        replay(digest_artifact, digest_registry)


def test_registry_fails_closed_on_profile_or_checker_identity_mismatch(tmp_path: Path) -> None:
    artifact = load_artifact(LEGACY_FIXTURE)
    registry = ScenarioRegistry()
    registry.register_profile(EngineProfile(tmp_path / "identity-history.jsonl"))

    with pytest.raises(ValueError, match="checker is not registered exactly"):
        replay(artifact, registry)

    other = ProfileIdentity(name=PROFILE_IDENTITY.name, version=2, digest=PROFILE_IDENTITY.digest)
    command = Command(profile=other, name="engine.drive", payload={})
    profile = EngineProfile(tmp_path / "command-history.jsonl")
    world = World(profile, artifact.budget)
    try:
        world.step()
        with pytest.raises(ValueError, match="command profile does not match"):
            world.submit(command, generation=1)
        world.timeline().command("engine.complete", {"occurrence": 1, "result": None})
        with pytest.raises(PendingWork):
            world.timeline().command("engine.complete", {"occurrence": 1, "result": None})
    finally:
        world.close()
