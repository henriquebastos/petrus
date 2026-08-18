"""CV19.DS2 joined initial-creation transaction refusal and recovery proof."""

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
from tests.dst.joined_creation_world import (
    ACK_LOSS_SCENARIO_ID,
    REFUSAL_SCENARIO_ID,
    JoinedCreationAckLossProfile,
    JoinedCreationAuthorityChecker,
    JoinedCreationProfile,
    build_joined_creation_ack_loss_artifact,
    build_joined_creation_refusal_artifact,
)
from tests.dst.postgres_support import isolated_absurd_database

REFUSAL_FIXTURE = Path("tests/dst/fixtures/joined-creation-commit-refusal-world-v3.json")
ACK_LOSS_FIXTURE = Path("tests/dst/fixtures/joined-creation-ack-loss-world-v3.json")


def test_joined_creation_commit_refusal_is_exact_and_replayable(absurd_dsn: str) -> None:
    with isolated_absurd_database(absurd_dsn) as authored_dsn:
        artifact = build_joined_creation_refusal_artifact(authored_dsn)

    assert artifact.scenario_id == REFUSAL_SCENARIO_ID
    assert artifact.origin is None
    assert encode_artifact(artifact) == REFUSAL_FIXTURE.read_bytes().rstrip(b"\n")

    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedCreationProfile(replay_dsn))
        registry.register_checker(JoinedCreationAuthorityChecker())
        result = replay(artifact, registry)

    assert result.version == RESULT_VERSION
    assert result.outcome == "pass"
    assert result.disposition == Disposition.EXTERNAL_WAIT.value
    assert result.operations == len(artifact.operations)


def test_retained_joined_creation_refusal_replays_without_the_authored_scenario(absurd_dsn: str) -> None:
    artifact = load_artifact(REFUSAL_FIXTURE)
    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedCreationProfile(replay_dsn))
        registry.register_checker(JoinedCreationAuthorityChecker())
        result = replay(artifact, registry)

    assert result.scenario_id == REFUSAL_SCENARIO_ID
    assert result.outcome == "pass"
    assert result.disposition == Disposition.EXTERNAL_WAIT.value


def test_joined_creation_ack_loss_is_exact_and_replayable(absurd_dsn: str) -> None:
    with isolated_absurd_database(absurd_dsn) as authored_dsn:
        artifact = build_joined_creation_ack_loss_artifact(authored_dsn)

    assert artifact.scenario_id == ACK_LOSS_SCENARIO_ID
    assert artifact.origin is None
    assert encode_artifact(artifact) == ACK_LOSS_FIXTURE.read_bytes().rstrip(b"\n")

    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedCreationAckLossProfile(replay_dsn))
        registry.register_checker(JoinedCreationAuthorityChecker())
        result = replay(artifact, registry)

    assert result.version == RESULT_VERSION
    assert result.outcome == "pass"
    assert result.disposition == Disposition.EXTERNAL_WAIT.value
    assert result.operations == len(artifact.operations)


def test_retained_joined_creation_ack_loss_replays_without_the_authored_scenario(absurd_dsn: str) -> None:
    artifact = load_artifact(ACK_LOSS_FIXTURE)
    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedCreationAckLossProfile(replay_dsn))
        registry.register_checker(JoinedCreationAuthorityChecker())
        result = replay(artifact, registry)

    assert result.scenario_id == ACK_LOSS_SCENARIO_ID
    assert result.outcome == "pass"
    assert result.disposition == Disposition.EXTERNAL_WAIT.value


def test_joined_creation_checker_refuses_phantom_instance_and_ack_loss() -> None:
    checker = JoinedCreationAuthorityChecker()
    phantom = Observation(
        name="engine.joined-creation-authority",
        value={
            "canonical_instances": ["dst-world-joined-creation"],
            "canonical_tokens": [1],
            "commit_ack_losses": 0,
            "commit_refusals": 1,
            "creation_attempts": [{"disposition": "refused_expected", "frontier": 0}],
            "drops": 0,
            "engine_present": False,
            "engine_record_types": [],
            "engine_tokens": [],
            "frontier": 2,
            "record_types": ["InstanceCreated", "TokensInitialized"],
            "transaction_attempts": [{"accepted": False, "record_types": ["InstanceCreated", "TokensInitialized"]}],
        },
        instant=0,
        generation=1,
        sequence=0,
    )
    ack_without_acceptance = Observation(
        name="engine.joined-creation-authority",
        value={
            "canonical_instances": [],
            "canonical_tokens": [],
            "commit_ack_losses": 1,
            "commit_refusals": 0,
            "creation_attempts": [{"disposition": "refused_expected", "frontier": 0}],
            "drops": 0,
            "engine_present": False,
            "engine_record_types": [],
            "engine_tokens": [],
            "frontier": 0,
            "record_types": [],
            "transaction_attempts": [],
        },
        instant=0,
        generation=1,
        sequence=0,
    )
    accepted_but_not_loaded = Observation(
        name="engine.joined-creation-authority",
        value={
            "canonical_instances": ["dst-world-joined-creation"],
            "canonical_tokens": [1],
            "commit_ack_losses": 1,
            "commit_refusals": 0,
            "creation_attempts": [{"disposition": "refused_expected", "frontier": 2}],
            "drops": 1,
            "engine_present": False,
            "engine_record_types": [],
            "engine_tokens": [],
            "frontier": 2,
            "record_types": ["InstanceCreated", "TokensInitialized"],
            "transaction_attempts": [{"accepted": True, "record_types": ["InstanceCreated", "TokensInitialized"]}],
        },
        instant=0,
        generation=2,
        sequence=0,
    )

    phantom_result: CheckResult = checker.check(phantom)
    missing_result: CheckResult = checker.check(ack_without_acceptance)
    unloaded_result: CheckResult = checker.check(accepted_but_not_loaded)

    assert phantom_result.passed is False
    assert phantom_result.detail["accepted_transactions"] == 0
    assert missing_result.passed is False
    assert missing_result.detail["ack_losses"] == 1
    assert unloaded_result.passed is False
    assert unloaded_result.detail["engine_coherent"] is False
