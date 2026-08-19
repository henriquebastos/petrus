"""CV19.DS2 joined handler-registration projection transaction proof."""

from __future__ import annotations

from pathlib import Path

from petrus.testing.dst import (
    RESULT_VERSION,
    Disposition,
    Observation,
    ScenarioRegistry,
    encode_artifact,
    load_artifact,
    replay,
)
from tests.dst.joined_registration_world import (
    ACK_LOSS_SCENARIO_ID,
    REFUSAL_SCENARIO_ID,
    JoinedRegistrationProjectionAckLossProfile,
    JoinedRegistrationProjectionAuthorityChecker,
    JoinedRegistrationProjectionProfile,
    build_joined_registration_projection_ack_loss_artifact,
    build_joined_registration_projection_refusal_artifact,
)
from tests.dst.postgres_support import isolated_absurd_database

REFUSAL_FIXTURE = Path("tests/dst/fixtures/joined-registration-projection-commit-refusal-world-v3.json")
ACK_LOSS_FIXTURE = Path("tests/dst/fixtures/joined-registration-projection-ack-loss-world-v3.json")


def test_joined_registration_projection_refusal_is_exact_and_replayable(absurd_dsn: str) -> None:
    with isolated_absurd_database(absurd_dsn) as authored_dsn:
        artifact = build_joined_registration_projection_refusal_artifact(authored_dsn)

    assert artifact.scenario_id == REFUSAL_SCENARIO_ID
    assert artifact.origin is None
    assert encode_artifact(artifact) == REFUSAL_FIXTURE.read_bytes().rstrip(b"\n")

    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedRegistrationProjectionProfile(replay_dsn))
        registry.register_checker(JoinedRegistrationProjectionAuthorityChecker())
        result = replay(artifact, registry)

    assert result.version == RESULT_VERSION
    assert result.outcome == "pass"
    assert result.disposition == Disposition.EXTERNAL_WAIT.value


def test_retained_joined_registration_projection_refusal_replays_without_authored_scenario(
    absurd_dsn: str,
) -> None:
    artifact = load_artifact(REFUSAL_FIXTURE)
    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedRegistrationProjectionProfile(replay_dsn))
        registry.register_checker(JoinedRegistrationProjectionAuthorityChecker())
        result = replay(artifact, registry)

    assert result.scenario_id == REFUSAL_SCENARIO_ID
    assert result.outcome == "pass"


def test_joined_registration_projection_ack_loss_is_exact_and_replayable(absurd_dsn: str) -> None:
    with isolated_absurd_database(absurd_dsn) as authored_dsn:
        artifact = build_joined_registration_projection_ack_loss_artifact(authored_dsn)

    assert artifact.scenario_id == ACK_LOSS_SCENARIO_ID
    assert artifact.origin is None
    assert encode_artifact(artifact) == ACK_LOSS_FIXTURE.read_bytes().rstrip(b"\n")

    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedRegistrationProjectionAckLossProfile(replay_dsn))
        registry.register_checker(JoinedRegistrationProjectionAuthorityChecker())
        result = replay(artifact, registry)

    assert result.version == RESULT_VERSION
    assert result.outcome == "pass"
    assert result.disposition == Disposition.EXTERNAL_WAIT.value


def test_retained_joined_registration_projection_ack_loss_replays_without_authored_scenario(
    absurd_dsn: str,
) -> None:
    artifact = load_artifact(ACK_LOSS_FIXTURE)
    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedRegistrationProjectionAckLossProfile(replay_dsn))
        registry.register_checker(JoinedRegistrationProjectionAuthorityChecker())
        result = replay(artifact, registry)

    assert result.scenario_id == ACK_LOSS_SCENARIO_ID
    assert result.outcome == "pass"


def test_joined_registration_checker_rejects_phantom_effects_ack_loss_and_wrong_reload() -> None:
    checker = JoinedRegistrationProjectionAuthorityChecker()
    begin = {
        "accepted": True,
        "dispatch_attempted": True,
        "record_types": ["CandidateSelected", "FiringBegun", "TokensConsumed", "ActivityRequested"],
    }
    terminal = {
        "accepted": True,
        "dispatch_attempted": False,
        "record_types": ["ActivityCompleted"],
    }
    refused_projection = {
        "accepted": False,
        "dispatch_attempted": False,
        "record_types": [
            "TokensProduced",
            "DeliveryRegistrationClosed",
            "DeliveryRegistrationOpened",
            "FiringCompleted",
        ],
    }
    accepted_projection = {**refused_projection, "accepted": True}
    base = {
        "drive_calls": 2,
        "durable_tasks": [{"idempotency": "dst-world-joined-begin-refusal:occurrence-1", "state": "completed"}],
        "frontier": 12,
        "prepare_calls": 1,
        "record_types": [
            "InstanceCreated",
            "TokensInitialized",
            "DeliveryRegistrationOpened",
            "CandidateSelected",
            "FiringBegun",
            "TokensConsumed",
            "ActivityRequested",
            "ActivityCompleted",
            "TokensProduced",
            "DeliveryRegistrationClosed",
            "DeliveryRegistrationOpened",
            "FiringCompleted",
        ],
        "worker_completions": 1,
    }
    registrations = [
        {"key": "default", "kind": "opened", "occurrence": None, "source": "source"},
        {"key": "default", "kind": "closed", "occurrence": 1, "source": "source"},
        {"key": "replacement", "kind": "opened", "occurrence": 1, "source": "source"},
    ]
    phantom = Observation(
        name="engine.joined-registration-projection-authority",
        value={
            **base,
            "canonical_registrations": registrations,
            "engine_armed": None,
            "projection_ack_losses": 0,
            "projection_refusals": 1,
            "status": "poisoned",
            "transaction_attempts": [begin, terminal, refused_projection],
        },
        instant=0,
        generation=1,
        sequence=0,
    )
    ack_without_acceptance = Observation(
        name="engine.joined-registration-projection-authority",
        value={
            **base,
            "canonical_registrations": [{"key": "default", "kind": "opened", "occurrence": None, "source": "source"}],
            "engine_armed": None,
            "frontier": 8,
            "projection_ack_losses": 1,
            "projection_refusals": 1,
            "record_types": base["record_types"][:8],
            "status": "poisoned",
            "transaction_attempts": [begin, terminal, refused_projection],
        },
        instant=0,
        generation=1,
        sequence=0,
    )
    wrong_reload = Observation(
        name="engine.joined-registration-projection-authority",
        value={
            **base,
            "canonical_registrations": registrations,
            "engine_armed": [{"key": "default", "source": "source"}],
            "projection_ack_losses": 1,
            "projection_refusals": 0,
            "status": "awaiting",
            "transaction_attempts": [begin, terminal, accepted_projection],
        },
        instant=0,
        generation=2,
        sequence=0,
    )

    phantom_result = checker.check(phantom)
    missing_result = checker.check(ack_without_acceptance)
    reload_result = checker.check(wrong_reload)

    assert phantom_result.passed is False
    assert phantom_result.detail["accepted_projections"] == 0
    assert missing_result.passed is False
    assert missing_result.detail["ack_losses"] == 1
    assert reload_result.passed is False
    assert reload_result.detail["engine_coherent"] is False
