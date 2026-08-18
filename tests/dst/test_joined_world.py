"""CV19.DS2 joined begin-transaction refusal and recovery proof."""

from __future__ import annotations

from pathlib import Path

from petrus.testing.dst import (
    RESULT_VERSION,
    CheckResult,
    Disposition,
    Observation,
    ScenarioRegistry,
    encode_artifact,
    load_artifact,
    replay,
)
from tests.dst.joined_world import (
    ACK_LOSS_SCENARIO_ID,
    CANCELLATION_ACK_LOSS_SCENARIO_ID,
    CANCELLATION_SCENARIO_ID,
    CLOSE_ACK_LOSS_SCENARIO_ID,
    CLOSE_REFUSAL_SCENARIO_ID,
    DELIVERY_ACK_LOSS_SCENARIO_ID,
    DELIVERY_REFUSAL_SCENARIO_ID,
    DISPATCH_SCENARIO_ID,
    FAILURE_ACK_LOSS_SCENARIO_ID,
    FAILURE_REFUSAL_SCENARIO_ID,
    PROJECTION_ACK_LOSS_SCENARIO_ID,
    PROJECTION_SCENARIO_ID,
    RESET_ACK_LOSS_SCENARIO_ID,
    RESET_REFUSAL_SCENARIO_ID,
    SCENARIO_ID,
    TERMINAL_ACK_LOSS_SCENARIO_ID,
    TERMINAL_REFUSAL_SCENARIO_ID,
    JoinedAcceptedCancellationAuthorityChecker,
    JoinedAcceptedCloseAuthorityChecker,
    JoinedAcceptedTerminalAuthorityChecker,
    JoinedBeginProfile,
    JoinedBeginAckLossProfile,
    JoinedAcceptedBeginAuthorityChecker,
    JoinedCancellationAckLossProfile,
    JoinedCancellationAuthorityChecker,
    JoinedCancellationProfile,
    JoinedCloseAckLossProfile,
    JoinedCloseRefusalAuthorityChecker,
    JoinedCloseRefusalProfile,
    JoinedCommitAuthorityChecker,
    JoinedDeliveryAckLossProfile,
    JoinedDeliveryAuthorityChecker,
    JoinedDeliveryRefusalProfile,
    JoinedDispatchProfile,
    JoinedAcceptedFailureAuthorityChecker,
    JoinedFailureAckLossProfile,
    JoinedFailureAuthorityChecker,
    JoinedFailureRefusalProfile,
    JoinedAcceptedResetAuthorityChecker,
    JoinedProjectionAuthorityChecker,
    JoinedAcceptedProjectionAuthorityChecker,
    JoinedProjectionAckLossProfile,
    JoinedProjectionProfile,
    JoinedResetAckLossProfile,
    JoinedResetRefusalAuthorityChecker,
    JoinedResetRefusalProfile,
    JoinedTerminalAuthorityChecker,
    JoinedTerminalAckLossProfile,
    JoinedTerminalRefusalProfile,
    build_joined_begin_artifact,
    build_joined_ack_loss_artifact,
    build_joined_cancellation_ack_loss_artifact,
    build_joined_dispatch_artifact,
    build_joined_cancellation_artifact,
    build_joined_close_ack_loss_artifact,
    build_joined_close_refusal_artifact,
    build_joined_delivery_ack_loss_artifact,
    build_joined_delivery_refusal_artifact,
    build_joined_failure_ack_loss_artifact,
    build_joined_failure_refusal_artifact,
    build_joined_projection_ack_loss_artifact,
    build_joined_projection_artifact,
    build_joined_reset_ack_loss_artifact,
    build_joined_reset_refusal_artifact,
    build_joined_terminal_ack_loss_artifact,
    build_joined_terminal_refusal_artifact,
)
from tests.dst.postgres_support import isolated_absurd_database

FIXTURE = Path("tests/dst/fixtures/joined-begin-commit-refusal-world-v3.json")
DISPATCH_FIXTURE = Path("tests/dst/fixtures/joined-dispatch-refusal-world-v3.json")
FAILURE_ACK_LOSS_FIXTURE = Path("tests/dst/fixtures/joined-failure-ack-loss-world-v3.json")
FAILURE_REFUSAL_FIXTURE = Path("tests/dst/fixtures/joined-failure-commit-refusal-world-v3.json")
PROJECTION_FIXTURE = Path("tests/dst/fixtures/joined-projection-commit-refusal-world-v3.json")
PROJECTION_ACK_LOSS_FIXTURE = Path("tests/dst/fixtures/joined-projection-ack-loss-world-v3.json")
RESET_ACK_LOSS_FIXTURE = Path("tests/dst/fixtures/joined-reset-ack-loss-world-v3.json")
RESET_REFUSAL_FIXTURE = Path("tests/dst/fixtures/joined-reset-commit-refusal-world-v3.json")
ACK_LOSS_FIXTURE = Path("tests/dst/fixtures/joined-begin-ack-loss-world-v3.json")
TERMINAL_ACK_LOSS_FIXTURE = Path("tests/dst/fixtures/joined-terminal-ack-loss-world-v3.json")
TERMINAL_REFUSAL_FIXTURE = Path("tests/dst/fixtures/joined-terminal-commit-refusal-world-v3.json")
CANCELLATION_FIXTURE = Path("tests/dst/fixtures/joined-cancellation-commit-refusal-world-v3.json")
CANCELLATION_ACK_LOSS_FIXTURE = Path("tests/dst/fixtures/joined-cancellation-ack-loss-world-v3.json")
DELIVERY_REFUSAL_FIXTURE = Path("tests/dst/fixtures/joined-delivery-commit-refusal-world-v3.json")
DELIVERY_ACK_LOSS_FIXTURE = Path("tests/dst/fixtures/joined-delivery-ack-loss-world-v3.json")
CLOSE_REFUSAL_FIXTURE = Path("tests/dst/fixtures/joined-close-commit-refusal-world-v3.json")
CLOSE_ACK_LOSS_FIXTURE = Path("tests/dst/fixtures/joined-close-ack-loss-world-v3.json")


def test_joined_begin_commit_refusal_is_exact_and_replayable(absurd_dsn: str) -> None:
    with isolated_absurd_database(absurd_dsn) as authored_dsn:
        artifact = build_joined_begin_artifact(authored_dsn)

    assert artifact.scenario_id == SCENARIO_ID
    assert artifact.origin is None
    assert encode_artifact(artifact) == FIXTURE.read_bytes().rstrip(b"\n")

    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedBeginProfile(replay_dsn))
        registry.register_checker(JoinedCommitAuthorityChecker())
        result = replay(artifact, registry)

    assert result.version == RESULT_VERSION
    assert result.outcome == "pass"
    assert result.disposition == Disposition.EXTERNAL_WAIT.value
    assert result.operations == len(artifact.operations)


def test_retained_joined_begin_fixture_replays_without_the_authored_scenario(absurd_dsn: str) -> None:
    artifact = load_artifact(FIXTURE)
    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedBeginProfile(replay_dsn))
        registry.register_checker(JoinedCommitAuthorityChecker())
        result = replay(artifact, registry)

    assert result.scenario_id == SCENARIO_ID
    assert result.outcome == "pass"
    assert result.disposition == Disposition.EXTERNAL_WAIT.value


def test_joined_dispatch_refusal_is_exact_and_replayable(absurd_dsn: str) -> None:
    with isolated_absurd_database(absurd_dsn) as authored_dsn:
        artifact = build_joined_dispatch_artifact(authored_dsn)

    assert artifact.scenario_id == DISPATCH_SCENARIO_ID
    assert artifact.origin is None
    assert encode_artifact(artifact) == DISPATCH_FIXTURE.read_bytes().rstrip(b"\n")

    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedDispatchProfile(replay_dsn))
        registry.register_checker(JoinedCommitAuthorityChecker())
        result = replay(artifact, registry)

    assert result.version == RESULT_VERSION
    assert result.outcome == "pass"
    assert result.disposition == Disposition.EXTERNAL_WAIT.value
    assert result.operations == len(artifact.operations)


def test_retained_joined_dispatch_fixture_replays_without_the_authored_scenario(absurd_dsn: str) -> None:
    artifact = load_artifact(DISPATCH_FIXTURE)
    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedDispatchProfile(replay_dsn))
        registry.register_checker(JoinedCommitAuthorityChecker())
        result = replay(artifact, registry)

    assert result.scenario_id == DISPATCH_SCENARIO_ID
    assert result.outcome == "pass"
    assert result.disposition == Disposition.EXTERNAL_WAIT.value


def test_joined_begin_ack_loss_is_exact_and_replayable(absurd_dsn: str) -> None:
    with isolated_absurd_database(absurd_dsn) as authored_dsn:
        artifact = build_joined_ack_loss_artifact(authored_dsn)

    assert artifact.scenario_id == ACK_LOSS_SCENARIO_ID
    assert artifact.origin is None
    assert encode_artifact(artifact) == ACK_LOSS_FIXTURE.read_bytes().rstrip(b"\n")

    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedBeginAckLossProfile(replay_dsn))
        registry.register_checker(JoinedAcceptedBeginAuthorityChecker())
        result = replay(artifact, registry)

    assert result.version == RESULT_VERSION
    assert result.outcome == "pass"
    assert result.disposition == Disposition.EXTERNAL_WAIT.value
    assert result.operations == len(artifact.operations)


def test_retained_joined_begin_ack_loss_replays_without_the_authored_scenario(absurd_dsn: str) -> None:
    artifact = load_artifact(ACK_LOSS_FIXTURE)
    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedBeginAckLossProfile(replay_dsn))
        registry.register_checker(JoinedAcceptedBeginAuthorityChecker())
        result = replay(artifact, registry)

    assert result.scenario_id == ACK_LOSS_SCENARIO_ID
    assert result.outcome == "pass"
    assert result.disposition == Disposition.EXTERNAL_WAIT.value


def test_joined_accepted_begin_checker_refuses_ack_loss_without_durable_truth() -> None:
    checker = JoinedAcceptedBeginAuthorityChecker()
    observation = Observation(
        name="engine.joined-accepted-begin-authority",
        value={
            "commit_ack_losses": 1,
            "durable_tasks": [],
            "prepare_calls": 1,
            "record_types": ["InstanceCreated", "TokensInitialized"],
            "transaction_attempts": [],
        },
        instant=0,
        generation=1,
        sequence=0,
    )

    result: CheckResult = checker.check(observation)

    assert result.passed is False
    assert result.detail["ack_losses"] == 1
    assert result.detail["accepted_begins"] == 0


def test_joined_delivery_commit_refusal_is_exact_and_replayable(absurd_dsn: str) -> None:
    with isolated_absurd_database(absurd_dsn) as authored_dsn:
        artifact = build_joined_delivery_refusal_artifact(authored_dsn)

    assert artifact.scenario_id == DELIVERY_REFUSAL_SCENARIO_ID
    assert artifact.origin is None
    assert encode_artifact(artifact) == DELIVERY_REFUSAL_FIXTURE.read_bytes().rstrip(b"\n")

    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedDeliveryRefusalProfile(replay_dsn))
        registry.register_checker(JoinedDeliveryAuthorityChecker())
        result = replay(artifact, registry)

    assert result.version == RESULT_VERSION
    assert result.outcome == "pass"
    assert result.disposition == Disposition.EXTERNAL_WAIT.value
    assert result.operations == len(artifact.operations)


def test_retained_joined_delivery_refusal_replays_without_the_authored_scenario(absurd_dsn: str) -> None:
    artifact = load_artifact(DELIVERY_REFUSAL_FIXTURE)
    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedDeliveryRefusalProfile(replay_dsn))
        registry.register_checker(JoinedDeliveryAuthorityChecker())
        result = replay(artifact, registry)

    assert result.scenario_id == DELIVERY_REFUSAL_SCENARIO_ID
    assert result.outcome == "pass"
    assert result.disposition == Disposition.EXTERNAL_WAIT.value


def test_joined_delivery_ack_loss_is_exact_and_replayable(absurd_dsn: str) -> None:
    with isolated_absurd_database(absurd_dsn) as authored_dsn:
        artifact = build_joined_delivery_ack_loss_artifact(authored_dsn)

    assert artifact.scenario_id == DELIVERY_ACK_LOSS_SCENARIO_ID
    assert artifact.origin is None
    assert encode_artifact(artifact) == DELIVERY_ACK_LOSS_FIXTURE.read_bytes().rstrip(b"\n")

    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedDeliveryAckLossProfile(replay_dsn))
        registry.register_checker(JoinedDeliveryAuthorityChecker())
        result = replay(artifact, registry)

    assert result.version == RESULT_VERSION
    assert result.outcome == "pass"
    assert result.disposition == Disposition.EXTERNAL_WAIT.value
    assert result.operations == len(artifact.operations)


def test_retained_joined_delivery_ack_loss_replays_without_the_authored_scenario(absurd_dsn: str) -> None:
    artifact = load_artifact(DELIVERY_ACK_LOSS_FIXTURE)
    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedDeliveryAckLossProfile(replay_dsn))
        registry.register_checker(JoinedDeliveryAuthorityChecker())
        result = replay(artifact, registry)

    assert result.scenario_id == DELIVERY_ACK_LOSS_SCENARIO_ID
    assert result.outcome == "pass"
    assert result.disposition == Disposition.EXTERNAL_WAIT.value


def test_joined_delivery_checker_refuses_phantom_acceptance_and_ack_loss() -> None:
    checker = JoinedDeliveryAuthorityChecker()
    refused_only = Observation(
        name="engine.joined-delivery-authority",
        value={
            "canonical_deliveries": [{"identity": "event-3", "occurrence": 1, "value": 3}],
            "delivery_ack_losses": 0,
            "delivery_attempts": [{"disposition": "refused_expected", "identity": "event-3", "value": 3}],
            "delivery_refusals": 1,
            "firing_completed": 1,
            "produced_values": [3],
            "transaction_attempts": [
                {
                    "accepted": False,
                    "dispatch_attempted": False,
                    "record_types": ["ExternalEventDelivered", "FiringBegun", "TokensProduced", "FiringCompleted"],
                }
            ],
        },
        instant=0,
        generation=1,
        sequence=0,
    )
    ack_without_acceptance = Observation(
        name="engine.joined-delivery-authority",
        value={
            "canonical_deliveries": [],
            "delivery_ack_losses": 1,
            "delivery_attempts": [{"disposition": "refused_expected", "identity": "event-3", "value": 3}],
            "delivery_refusals": 0,
            "firing_completed": 0,
            "produced_values": [],
            "transaction_attempts": [],
        },
        instant=0,
        generation=1,
        sequence=0,
    )

    phantom_result: CheckResult = checker.check(refused_only)
    missing_result: CheckResult = checker.check(ack_without_acceptance)

    assert phantom_result.passed is False
    assert phantom_result.detail["accepted_transactions"] == 0
    assert missing_result.passed is False
    assert missing_result.detail["ack_losses"] == 1


def test_joined_terminal_commit_refusal_is_exact_and_replayable(absurd_dsn: str) -> None:
    with isolated_absurd_database(absurd_dsn) as authored_dsn:
        artifact = build_joined_terminal_refusal_artifact(authored_dsn)

    assert artifact.scenario_id == TERMINAL_REFUSAL_SCENARIO_ID
    assert artifact.origin is None
    assert encode_artifact(artifact) == TERMINAL_REFUSAL_FIXTURE.read_bytes().rstrip(b"\n")

    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedTerminalRefusalProfile(replay_dsn))
        registry.register_checker(JoinedTerminalAuthorityChecker())
        result = replay(artifact, registry)

    assert result.version == RESULT_VERSION
    assert result.outcome == "pass"
    assert result.disposition == Disposition.CONVERGED.value
    assert result.operations == len(artifact.operations)


def test_retained_joined_terminal_refusal_replays_without_the_authored_scenario(absurd_dsn: str) -> None:
    artifact = load_artifact(TERMINAL_REFUSAL_FIXTURE)
    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedTerminalRefusalProfile(replay_dsn))
        registry.register_checker(JoinedTerminalAuthorityChecker())
        result = replay(artifact, registry)

    assert result.scenario_id == TERMINAL_REFUSAL_SCENARIO_ID
    assert result.outcome == "pass"
    assert result.disposition == Disposition.CONVERGED.value


def test_joined_terminal_checker_refuses_a_canonical_terminal_after_refused_transaction() -> None:
    checker = JoinedTerminalAuthorityChecker()
    observation = Observation(
        name="engine.joined-terminal-authority",
        value={
            "durable_tasks": [
                {
                    "idempotency": "dst-world-joined-begin-refusal:occurrence-1",
                    "state": "completed",
                }
            ],
            "prepare_calls": 1,
            "record_types": [
                "InstanceCreated",
                "TokensInitialized",
                "CandidateSelected",
                "FiringBegun",
                "TokensConsumed",
                "ActivityRequested",
                "ActivityCompleted",
            ],
            "terminal_refusals": 1,
            "transaction_attempts": [
                {
                    "accepted": True,
                    "dispatch_attempted": True,
                    "record_types": ["CandidateSelected", "FiringBegun", "TokensConsumed", "ActivityRequested"],
                },
                {
                    "accepted": False,
                    "dispatch_attempted": False,
                    "record_types": ["ActivityCompleted"],
                },
            ],
            "worker_completions": 1,
        },
        instant=0,
        generation=1,
        sequence=0,
    )

    result: CheckResult = checker.check(observation)

    assert result.passed is False
    assert result.detail["accepted_terminals"] == 0
    assert result.detail["canonical_terminals"] == 1


def test_joined_failure_commit_refusal_is_exact_and_replayable(absurd_dsn: str) -> None:
    with isolated_absurd_database(absurd_dsn) as authored_dsn:
        artifact = build_joined_failure_refusal_artifact(authored_dsn)

    assert artifact.scenario_id == FAILURE_REFUSAL_SCENARIO_ID
    assert artifact.origin is None
    assert encode_artifact(artifact) == FAILURE_REFUSAL_FIXTURE.read_bytes().rstrip(b"\n")

    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedFailureRefusalProfile(replay_dsn))
        registry.register_checker(JoinedFailureAuthorityChecker())
        result = replay(artifact, registry)

    assert result.version == RESULT_VERSION
    assert result.outcome == "pass"
    assert result.disposition == Disposition.QUARANTINED.value
    assert result.operations == len(artifact.operations)


def test_retained_joined_failure_refusal_replays_without_the_authored_scenario(absurd_dsn: str) -> None:
    artifact = load_artifact(FAILURE_REFUSAL_FIXTURE)
    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedFailureRefusalProfile(replay_dsn))
        registry.register_checker(JoinedFailureAuthorityChecker())
        result = replay(artifact, registry)

    assert result.scenario_id == FAILURE_REFUSAL_SCENARIO_ID
    assert result.outcome == "pass"
    assert result.disposition == Disposition.QUARANTINED.value


def test_joined_failure_checker_refuses_a_canonical_failure_after_refused_transaction() -> None:
    checker = JoinedFailureAuthorityChecker()
    observation = Observation(
        name="engine.joined-failure-authority",
        value={
            "durable_tasks": [
                {
                    "idempotency": "dst-world-joined-begin-refusal:occurrence-1",
                    "state": "failed",
                }
            ],
            "prepare_calls": 1,
            "record_types": [
                "InstanceCreated",
                "TokensInitialized",
                "CandidateSelected",
                "FiringBegun",
                "TokensConsumed",
                "ActivityRequested",
                "ActivityFailed",
            ],
            "terminal_refusals": 1,
            "transaction_attempts": [
                {
                    "accepted": True,
                    "dispatch_attempted": True,
                    "record_types": ["CandidateSelected", "FiringBegun", "TokensConsumed", "ActivityRequested"],
                },
                {
                    "accepted": False,
                    "dispatch_attempted": False,
                    "record_types": ["ActivityFailed"],
                },
            ],
            "worker_failures": 1,
        },
        instant=0,
        generation=1,
        sequence=0,
    )

    result: CheckResult = checker.check(observation)

    assert result.passed is False
    assert result.detail["accepted_failures"] == 0
    assert result.detail["canonical_failures"] == 1


def test_joined_failure_ack_loss_is_exact_and_replayable(absurd_dsn: str) -> None:
    with isolated_absurd_database(absurd_dsn) as authored_dsn:
        artifact = build_joined_failure_ack_loss_artifact(authored_dsn)

    assert artifact.scenario_id == FAILURE_ACK_LOSS_SCENARIO_ID
    assert artifact.origin is None
    assert encode_artifact(artifact) == FAILURE_ACK_LOSS_FIXTURE.read_bytes().rstrip(b"\n")

    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedFailureAckLossProfile(replay_dsn))
        registry.register_checker(JoinedAcceptedFailureAuthorityChecker())
        result = replay(artifact, registry)

    assert result.version == RESULT_VERSION
    assert result.outcome == "pass"
    assert result.disposition == Disposition.QUARANTINED.value
    assert result.operations == len(artifact.operations)


def test_retained_joined_failure_ack_loss_replays_without_the_authored_scenario(absurd_dsn: str) -> None:
    artifact = load_artifact(FAILURE_ACK_LOSS_FIXTURE)
    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedFailureAckLossProfile(replay_dsn))
        registry.register_checker(JoinedAcceptedFailureAuthorityChecker())
        result = replay(artifact, registry)

    assert result.scenario_id == FAILURE_ACK_LOSS_SCENARIO_ID
    assert result.outcome == "pass"
    assert result.disposition == Disposition.QUARANTINED.value


def test_joined_accepted_failure_checker_refuses_ack_loss_without_accepted_failure() -> None:
    checker = JoinedAcceptedFailureAuthorityChecker()
    observation = Observation(
        name="engine.joined-accepted-failure-authority",
        value={
            "durable_tasks": [
                {
                    "idempotency": "dst-world-joined-begin-refusal:occurrence-1",
                    "state": "failed",
                }
            ],
            "prepare_calls": 1,
            "record_types": [
                "InstanceCreated",
                "TokensInitialized",
                "CandidateSelected",
                "FiringBegun",
                "TokensConsumed",
                "ActivityRequested",
                "ActivityFailed",
            ],
            "terminal_ack_losses": 1,
            "transaction_attempts": [
                {
                    "accepted": True,
                    "dispatch_attempted": True,
                    "record_types": ["CandidateSelected", "FiringBegun", "TokensConsumed", "ActivityRequested"],
                }
            ],
            "worker_failures": 1,
        },
        instant=0,
        generation=1,
        sequence=0,
    )

    result: CheckResult = checker.check(observation)

    assert result.passed is False
    assert result.detail["accepted_failures"] == 0
    assert result.detail["ack_losses"] == 1


def test_joined_terminal_ack_loss_is_exact_and_replayable(absurd_dsn: str) -> None:
    with isolated_absurd_database(absurd_dsn) as authored_dsn:
        artifact = build_joined_terminal_ack_loss_artifact(authored_dsn)

    assert artifact.scenario_id == TERMINAL_ACK_LOSS_SCENARIO_ID
    assert artifact.origin is None
    assert encode_artifact(artifact) == TERMINAL_ACK_LOSS_FIXTURE.read_bytes().rstrip(b"\n")

    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedTerminalAckLossProfile(replay_dsn))
        registry.register_checker(JoinedAcceptedTerminalAuthorityChecker())
        result = replay(artifact, registry)

    assert result.version == RESULT_VERSION
    assert result.outcome == "pass"
    assert result.disposition == Disposition.CONVERGED.value
    assert result.operations == len(artifact.operations)


def test_retained_joined_terminal_ack_loss_replays_without_the_authored_scenario(absurd_dsn: str) -> None:
    artifact = load_artifact(TERMINAL_ACK_LOSS_FIXTURE)
    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedTerminalAckLossProfile(replay_dsn))
        registry.register_checker(JoinedAcceptedTerminalAuthorityChecker())
        result = replay(artifact, registry)

    assert result.scenario_id == TERMINAL_ACK_LOSS_SCENARIO_ID
    assert result.outcome == "pass"
    assert result.disposition == Disposition.CONVERGED.value


def test_joined_accepted_terminal_checker_refuses_projection_without_accepted_transaction() -> None:
    checker = JoinedAcceptedTerminalAuthorityChecker()
    observation = Observation(
        name="engine.joined-accepted-terminal-authority",
        value={
            "durable_tasks": [
                {
                    "idempotency": "dst-world-joined-begin-refusal:occurrence-1",
                    "state": "completed",
                }
            ],
            "prepare_calls": 1,
            "record_types": [
                "InstanceCreated",
                "TokensInitialized",
                "CandidateSelected",
                "FiringBegun",
                "TokensConsumed",
                "ActivityRequested",
                "ActivityCompleted",
                "TokensProduced",
                "FiringCompleted",
            ],
            "terminal_ack_losses": 1,
            "transaction_attempts": [
                {
                    "accepted": True,
                    "dispatch_attempted": True,
                    "record_types": ["CandidateSelected", "FiringBegun", "TokensConsumed", "ActivityRequested"],
                },
                {
                    "accepted": True,
                    "dispatch_attempted": False,
                    "record_types": ["ActivityCompleted"],
                },
            ],
            "worker_completions": 1,
        },
        instant=0,
        generation=1,
        sequence=0,
    )

    result: CheckResult = checker.check(observation)

    assert result.passed is False
    assert result.detail["accepted_projections"] == 0
    assert result.detail["canonical_projections"] == 1


def test_joined_projection_commit_refusal_is_exact_and_replayable(absurd_dsn: str) -> None:
    with isolated_absurd_database(absurd_dsn) as authored_dsn:
        artifact = build_joined_projection_artifact(authored_dsn)

    assert artifact.scenario_id == PROJECTION_SCENARIO_ID
    assert artifact.origin is None
    assert encode_artifact(artifact) == PROJECTION_FIXTURE.read_bytes().rstrip(b"\n")

    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedProjectionProfile(replay_dsn))
        registry.register_checker(JoinedProjectionAuthorityChecker())
        result = replay(artifact, registry)

    assert result.version == RESULT_VERSION
    assert result.outcome == "pass"
    assert result.disposition == Disposition.CONVERGED.value
    assert result.operations == len(artifact.operations)


def test_retained_joined_projection_fixture_replays_without_the_authored_scenario(absurd_dsn: str) -> None:
    artifact = load_artifact(PROJECTION_FIXTURE)
    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedProjectionProfile(replay_dsn))
        registry.register_checker(JoinedProjectionAuthorityChecker())
        result = replay(artifact, registry)

    assert result.scenario_id == PROJECTION_SCENARIO_ID
    assert result.outcome == "pass"
    assert result.disposition == Disposition.CONVERGED.value


def test_joined_projection_checker_refuses_projection_after_refused_transaction() -> None:
    checker = JoinedProjectionAuthorityChecker()
    observation = Observation(
        name="engine.joined-projection-authority",
        value={
            "durable_tasks": [
                {
                    "idempotency": "dst-world-joined-begin-refusal:occurrence-1",
                    "state": "completed",
                }
            ],
            "prepare_calls": 1,
            "projection_refusals": 1,
            "record_types": [
                "InstanceCreated",
                "TokensInitialized",
                "CandidateSelected",
                "FiringBegun",
                "TokensConsumed",
                "ActivityRequested",
                "ActivityCompleted",
                "TokensProduced",
                "FiringCompleted",
            ],
            "transaction_attempts": [
                {
                    "accepted": True,
                    "dispatch_attempted": True,
                    "record_types": ["CandidateSelected", "FiringBegun", "TokensConsumed", "ActivityRequested"],
                },
                {
                    "accepted": True,
                    "dispatch_attempted": False,
                    "record_types": ["ActivityCompleted"],
                },
                {
                    "accepted": False,
                    "dispatch_attempted": False,
                    "record_types": ["TokensProduced", "FiringCompleted"],
                },
            ],
            "worker_completions": 1,
        },
        instant=0,
        generation=1,
        sequence=0,
    )

    result: CheckResult = checker.check(observation)

    assert result.passed is False
    assert result.detail["accepted_projections"] == 0
    assert result.detail["canonical_projections"] == 1


def test_joined_projection_ack_loss_is_exact_and_replayable(absurd_dsn: str) -> None:
    with isolated_absurd_database(absurd_dsn) as authored_dsn:
        artifact = build_joined_projection_ack_loss_artifact(authored_dsn)

    assert artifact.scenario_id == PROJECTION_ACK_LOSS_SCENARIO_ID
    assert artifact.origin is None
    assert encode_artifact(artifact) == PROJECTION_ACK_LOSS_FIXTURE.read_bytes().rstrip(b"\n")

    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedProjectionAckLossProfile(replay_dsn))
        registry.register_checker(JoinedAcceptedProjectionAuthorityChecker())
        result = replay(artifact, registry)

    assert result.version == RESULT_VERSION
    assert result.outcome == "pass"
    assert result.disposition == Disposition.CONVERGED.value
    assert result.operations == len(artifact.operations)


def test_retained_joined_projection_ack_loss_replays_without_the_authored_scenario(absurd_dsn: str) -> None:
    artifact = load_artifact(PROJECTION_ACK_LOSS_FIXTURE)
    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedProjectionAckLossProfile(replay_dsn))
        registry.register_checker(JoinedAcceptedProjectionAuthorityChecker())
        result = replay(artifact, registry)

    assert result.scenario_id == PROJECTION_ACK_LOSS_SCENARIO_ID
    assert result.outcome == "pass"
    assert result.disposition == Disposition.CONVERGED.value


def test_joined_accepted_projection_checker_refuses_ack_loss_without_accepted_projection() -> None:
    checker = JoinedAcceptedProjectionAuthorityChecker()
    observation = Observation(
        name="engine.joined-accepted-projection-authority",
        value={
            "durable_tasks": [
                {
                    "idempotency": "dst-world-joined-begin-refusal:occurrence-1",
                    "state": "completed",
                }
            ],
            "prepare_calls": 1,
            "projection_ack_losses": 1,
            "record_types": [
                "InstanceCreated",
                "TokensInitialized",
                "CandidateSelected",
                "FiringBegun",
                "TokensConsumed",
                "ActivityRequested",
                "ActivityCompleted",
            ],
            "transaction_attempts": [
                {
                    "accepted": True,
                    "dispatch_attempted": True,
                    "record_types": ["CandidateSelected", "FiringBegun", "TokensConsumed", "ActivityRequested"],
                },
                {
                    "accepted": True,
                    "dispatch_attempted": False,
                    "record_types": ["ActivityCompleted"],
                },
            ],
            "worker_completions": 1,
        },
        instant=0,
        generation=1,
        sequence=0,
    )

    result: CheckResult = checker.check(observation)

    assert result.passed is False
    assert result.detail["accepted_projections"] == 0
    assert result.detail["ack_losses"] == 1


def test_joined_commit_checker_refuses_a_phantom_task_after_rollback() -> None:
    checker = JoinedCommitAuthorityChecker()
    observation = Observation(
        name="engine.joined-commit-authority",
        value={
            "durable_tasks": [
                {
                    "idempotency": "dst-world-joined-begin-refusal:occurrence-1",
                    "state": "pending",
                }
            ],
            "prepare_calls": 1,
            "record_types": ["InstanceCreated", "TokensInitialized"],
            "transaction_attempts": [
                {
                    "accepted": False,
                    "dispatch_attempted": True,
                    "record_types": ["CandidateSelected", "FiringBegun", "TokensConsumed", "ActivityRequested"],
                }
            ],
        },
        instant=0,
        generation=1,
        sequence=0,
    )

    result: CheckResult = checker.check(observation)

    assert result.passed is False
    assert result.detail["accepted_joined_begins"] == 0
    assert result.detail["durable_tasks"] == 1


def test_joined_reset_commit_refusal_is_exact_and_replayable(absurd_dsn: str) -> None:
    with isolated_absurd_database(absurd_dsn) as authored_dsn:
        artifact = build_joined_reset_refusal_artifact(authored_dsn)

    assert artifact.scenario_id == RESET_REFUSAL_SCENARIO_ID
    assert artifact.origin is None
    assert encode_artifact(artifact) == RESET_REFUSAL_FIXTURE.read_bytes().rstrip(b"\n")

    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedResetRefusalProfile(replay_dsn))
        registry.register_checker(JoinedResetRefusalAuthorityChecker())
        result = replay(artifact, registry)

    assert result.version == RESULT_VERSION
    assert result.outcome == "pass"
    assert result.disposition == Disposition.QUIESCENT.value
    assert result.operations == len(artifact.operations)


def test_retained_joined_reset_refusal_replays_without_the_authored_scenario(absurd_dsn: str) -> None:
    artifact = load_artifact(RESET_REFUSAL_FIXTURE)
    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedResetRefusalProfile(replay_dsn))
        registry.register_checker(JoinedResetRefusalAuthorityChecker())
        result = replay(artifact, registry)

    assert result.scenario_id == RESET_REFUSAL_SCENARIO_ID
    assert result.outcome == "pass"
    assert result.disposition == Disposition.QUIESCENT.value


def test_joined_reset_checker_refuses_a_canonical_fence_after_refused_reset() -> None:
    checker = JoinedResetRefusalAuthorityChecker()
    observation = Observation(
        name="engine.joined-reset-refusal-authority",
        value={
            "cancellation_refusals": 0,
            "durable_tasks": [
                {
                    "idempotency": "dst-world-joined-begin-refusal:occurrence-2",
                    "state": "running",
                }
            ],
            "lifecycle_attempts": [{"accepted": False, "phase": "scope_reset", "record_types": ["ScopeReset"]}],
            "prepare_calls": 1,
            "record_types": [
                "InstanceCreated",
                "DeliveryRegistrationOpened",
                "ScopeOpened",
                "ExternalEventDelivered",
                "FiringBegun",
                "TokensProduced",
                "FiringCompleted",
                "CandidateSelected",
                "FiringBegun",
                "TokensConsumed",
                "ActivityRequested",
                "ScopeReset",
            ],
            "reset_refusals": 1,
            "scope_opens": 1,
            "scope_resets": 1,
            "source_deliveries": 1,
            "stale_worker_refusals": 0,
            "transaction_attempts": [
                {
                    "accepted": True,
                    "dispatch_attempted": False,
                    "record_types": ["ExternalEventDelivered", "FiringBegun", "TokensProduced", "FiringCompleted"],
                },
                {
                    "accepted": True,
                    "dispatch_attempted": True,
                    "record_types": ["CandidateSelected", "FiringBegun", "TokensConsumed", "ActivityRequested"],
                },
            ],
            "worker_claims": 1,
            "worker_completions": 0,
        },
        instant=0,
        generation=1,
        sequence=0,
    )

    result: CheckResult = checker.check(observation)

    assert result.passed is False
    assert result.detail["canonical_resets"] == 1
    assert result.detail["reset_refusals"] == 1


def test_joined_reset_ack_loss_is_exact_and_replayable(absurd_dsn: str) -> None:
    with isolated_absurd_database(absurd_dsn) as authored_dsn:
        artifact = build_joined_reset_ack_loss_artifact(authored_dsn)

    assert artifact.scenario_id == RESET_ACK_LOSS_SCENARIO_ID
    assert artifact.origin is None
    assert encode_artifact(artifact) == RESET_ACK_LOSS_FIXTURE.read_bytes().rstrip(b"\n")

    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedResetAckLossProfile(replay_dsn))
        registry.register_checker(JoinedAcceptedResetAuthorityChecker())
        result = replay(artifact, registry)

    assert result.version == RESULT_VERSION
    assert result.outcome == "pass"
    assert result.disposition == Disposition.QUIESCENT.value
    assert result.operations == len(artifact.operations)


def test_joined_close_commit_refusal_is_exact_and_replayable(absurd_dsn: str) -> None:
    with isolated_absurd_database(absurd_dsn) as authored_dsn:
        artifact = build_joined_close_refusal_artifact(authored_dsn)

    assert artifact.scenario_id == CLOSE_REFUSAL_SCENARIO_ID
    assert artifact.origin is None
    assert encode_artifact(artifact) == CLOSE_REFUSAL_FIXTURE.read_bytes().rstrip(b"\n")

    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedCloseRefusalProfile(replay_dsn))
        registry.register_checker(JoinedCloseRefusalAuthorityChecker())
        result = replay(artifact, registry)

    assert result.outcome == "pass"
    assert result.disposition == Disposition.QUIESCENT.value


def test_retained_joined_close_refusal_replays_without_the_authored_scenario(absurd_dsn: str) -> None:
    artifact = load_artifact(CLOSE_REFUSAL_FIXTURE)
    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedCloseRefusalProfile(replay_dsn))
        registry.register_checker(JoinedCloseRefusalAuthorityChecker())
        result = replay(artifact, registry)

    assert result.scenario_id == CLOSE_REFUSAL_SCENARIO_ID
    assert result.outcome == "pass"


def test_joined_close_ack_loss_is_exact_and_replayable(absurd_dsn: str) -> None:
    with isolated_absurd_database(absurd_dsn) as authored_dsn:
        artifact = build_joined_close_ack_loss_artifact(authored_dsn)

    assert artifact.scenario_id == CLOSE_ACK_LOSS_SCENARIO_ID
    assert artifact.origin is None
    assert encode_artifact(artifact) == CLOSE_ACK_LOSS_FIXTURE.read_bytes().rstrip(b"\n")

    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedCloseAckLossProfile(replay_dsn))
        registry.register_checker(JoinedAcceptedCloseAuthorityChecker())
        result = replay(artifact, registry)

    assert result.outcome == "pass"
    assert result.disposition == Disposition.QUIESCENT.value


def test_retained_joined_close_ack_loss_replays_without_the_authored_scenario(absurd_dsn: str) -> None:
    artifact = load_artifact(CLOSE_ACK_LOSS_FIXTURE)
    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedCloseAckLossProfile(replay_dsn))
        registry.register_checker(JoinedAcceptedCloseAuthorityChecker())
        result = replay(artifact, registry)

    assert result.scenario_id == CLOSE_ACK_LOSS_SCENARIO_ID
    assert result.outcome == "pass"


def test_retained_joined_reset_ack_loss_replays_without_the_authored_scenario(absurd_dsn: str) -> None:
    artifact = load_artifact(RESET_ACK_LOSS_FIXTURE)
    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedResetAckLossProfile(replay_dsn))
        registry.register_checker(JoinedAcceptedResetAuthorityChecker())
        result = replay(artifact, registry)

    assert result.scenario_id == RESET_ACK_LOSS_SCENARIO_ID
    assert result.outcome == "pass"
    assert result.disposition == Disposition.QUIESCENT.value


def test_joined_accepted_reset_checker_refuses_ack_loss_without_accepted_reset() -> None:
    checker = JoinedAcceptedResetAuthorityChecker()
    observation = Observation(
        name="engine.joined-accepted-reset-authority",
        value={
            "cancellation_refusals": 0,
            "durable_tasks": [
                {
                    "idempotency": "dst-world-joined-begin-refusal:occurrence-2",
                    "state": "running",
                }
            ],
            "lifecycle_attempts": [],
            "prepare_calls": 1,
            "record_types": [
                "InstanceCreated",
                "DeliveryRegistrationOpened",
                "ScopeOpened",
                "ExternalEventDelivered",
                "FiringBegun",
                "TokensProduced",
                "FiringCompleted",
                "CandidateSelected",
                "FiringBegun",
                "TokensConsumed",
                "ActivityRequested",
            ],
            "reset_ack_losses": 1,
            "reset_refusals": 0,
            "scope_opens": 1,
            "scope_resets": 0,
            "source_deliveries": 1,
            "stale_worker_refusals": 0,
            "transaction_attempts": [
                {
                    "accepted": True,
                    "dispatch_attempted": False,
                    "record_types": ["ExternalEventDelivered", "FiringBegun", "TokensProduced", "FiringCompleted"],
                },
                {
                    "accepted": True,
                    "dispatch_attempted": True,
                    "record_types": ["CandidateSelected", "FiringBegun", "TokensConsumed", "ActivityRequested"],
                },
            ],
            "worker_claims": 1,
        },
        instant=0,
        generation=1,
        sequence=0,
    )

    result: CheckResult = checker.check(observation)

    assert result.passed is False
    assert result.detail["accepted_resets"] == 0
    assert result.detail["ack_losses"] == 1


def test_joined_cancellation_commit_refusal_is_exact_and_replayable(absurd_dsn: str) -> None:
    with isolated_absurd_database(absurd_dsn) as authored_dsn:
        artifact = build_joined_cancellation_artifact(authored_dsn)

    assert artifact.scenario_id == CANCELLATION_SCENARIO_ID
    assert artifact.origin is None
    assert encode_artifact(artifact) == CANCELLATION_FIXTURE.read_bytes().rstrip(b"\n")

    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedCancellationProfile(replay_dsn))
        registry.register_checker(JoinedCancellationAuthorityChecker())
        result = replay(artifact, registry)

    assert result.version == RESULT_VERSION
    assert result.outcome == "pass"
    assert result.disposition == Disposition.QUIESCENT.value
    assert result.operations == len(artifact.operations)


def test_retained_joined_cancellation_fixture_replays_without_the_authored_scenario(absurd_dsn: str) -> None:
    artifact = load_artifact(CANCELLATION_FIXTURE)
    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedCancellationProfile(replay_dsn))
        registry.register_checker(JoinedCancellationAuthorityChecker())
        result = replay(artifact, registry)

    assert result.scenario_id == CANCELLATION_SCENARIO_ID
    assert result.outcome == "pass"
    assert result.disposition == Disposition.QUIESCENT.value


def test_joined_cancellation_checker_refuses_a_tombstone_after_refused_only_transaction() -> None:
    checker = JoinedCancellationAuthorityChecker()
    observation = Observation(
        name="engine.joined-cancellation-authority",
        value={
            "cancellation_refusals": 1,
            "drops": 0,
            "drive_calls": 1,
            "durable_tasks": [{"idempotency": "dst-world-joined-begin-refusal:occurrence-2", "state": "cancelled"}],
            "frontier": 12,
            "lifecycle_attempts": [
                {"accepted": True, "phase": "scope_reset", "record_types": ["ScopeReset"]},
                {"accepted": False, "phase": "cancellation", "record_types": []},
            ],
            "prepare_calls": 1,
            "record_types": [
                "InstanceCreated",
                "DeliveryRegistrationOpened",
                "ScopeOpened",
                "ExternalEventDelivered",
                "FiringBegun",
                "TokensProduced",
                "FiringCompleted",
                "CandidateSelected",
                "FiringBegun",
                "TokensConsumed",
                "ActivityRequested",
                "ScopeReset",
            ],
            "scope_opens": 1,
            "scope_resets": 1,
            "source_deliveries": 1,
            "stale_worker_refusals": 0,
            "status": "poisoned",
            "transaction_attempts": [
                {
                    "accepted": True,
                    "dispatch_attempted": False,
                    "record_types": [
                        "ExternalEventDelivered",
                        "FiringBegun",
                        "TokensProduced",
                        "FiringCompleted",
                    ],
                },
                {
                    "accepted": True,
                    "dispatch_attempted": True,
                    "record_types": ["CandidateSelected", "FiringBegun", "TokensConsumed", "ActivityRequested"],
                },
            ],
            "worker_claims": 1,
        },
        instant=0,
        generation=1,
        sequence=0,
    )

    result: CheckResult = checker.check(observation)

    assert result.passed is False
    assert result.detail["accepted_cancellations"] == 0
    assert result.detail["task_state"] == "cancelled"


def test_joined_cancellation_ack_loss_is_exact_and_replayable(absurd_dsn: str) -> None:
    with isolated_absurd_database(absurd_dsn) as authored_dsn:
        artifact = build_joined_cancellation_ack_loss_artifact(authored_dsn)

    assert artifact.scenario_id == CANCELLATION_ACK_LOSS_SCENARIO_ID
    assert artifact.origin is None
    assert encode_artifact(artifact) == CANCELLATION_ACK_LOSS_FIXTURE.read_bytes().rstrip(b"\n")

    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedCancellationAckLossProfile(replay_dsn))
        registry.register_checker(JoinedAcceptedCancellationAuthorityChecker())
        result = replay(artifact, registry)

    assert result.version == RESULT_VERSION
    assert result.outcome == "pass"
    assert result.disposition == Disposition.QUIESCENT.value
    assert result.operations == len(artifact.operations)


def test_retained_joined_cancellation_ack_loss_replays_without_the_authored_scenario(absurd_dsn: str) -> None:
    artifact = load_artifact(CANCELLATION_ACK_LOSS_FIXTURE)
    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedCancellationAckLossProfile(replay_dsn))
        registry.register_checker(JoinedAcceptedCancellationAuthorityChecker())
        result = replay(artifact, registry)

    assert result.scenario_id == CANCELLATION_ACK_LOSS_SCENARIO_ID
    assert result.outcome == "pass"
    assert result.disposition == Disposition.QUIESCENT.value


def test_joined_accepted_cancellation_checker_refuses_ack_loss_without_accepted_tombstone() -> None:
    checker = JoinedAcceptedCancellationAuthorityChecker()
    observation = Observation(
        name="engine.joined-accepted-cancellation-authority",
        value={
            "cancellation_ack_losses": 1,
            "cancellation_refusals": 0,
            "durable_tasks": [{"idempotency": "dst-world-joined-begin-refusal:occurrence-2", "state": "cancelled"}],
            "lifecycle_attempts": [
                {"accepted": True, "phase": "scope_reset", "record_types": ["ScopeReset"]},
            ],
            "prepare_calls": 1,
            "record_types": [
                "InstanceCreated",
                "DeliveryRegistrationOpened",
                "ScopeOpened",
                "ExternalEventDelivered",
                "FiringBegun",
                "TokensProduced",
                "FiringCompleted",
                "CandidateSelected",
                "FiringBegun",
                "TokensConsumed",
                "ActivityRequested",
                "ScopeReset",
            ],
            "scope_opens": 1,
            "scope_resets": 1,
            "source_deliveries": 1,
            "stale_worker_refusals": 0,
            "transaction_attempts": [
                {
                    "accepted": True,
                    "dispatch_attempted": False,
                    "record_types": [
                        "ExternalEventDelivered",
                        "FiringBegun",
                        "TokensProduced",
                        "FiringCompleted",
                    ],
                },
                {
                    "accepted": True,
                    "dispatch_attempted": True,
                    "record_types": ["CandidateSelected", "FiringBegun", "TokensConsumed", "ActivityRequested"],
                },
            ],
            "worker_claims": 1,
        },
        instant=0,
        generation=1,
        sequence=0,
    )

    result: CheckResult = checker.check(observation)

    assert result.passed is False
    assert result.detail["accepted_cancellations"] == 0
    assert result.detail["ack_losses"] == 1
