"""CV19.DS2 joined source-seal transaction proof."""

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
from tests.dst.joined_seal_world import (
    ACK_LOSS_SCENARIO_ID,
    REFUSAL_SCENARIO_ID,
    JoinedSealAckLossProfile,
    JoinedSealAuthorityChecker,
    JoinedSealRefusalProfile,
    build_joined_seal_ack_loss_artifact,
    build_joined_seal_refusal_artifact,
)
from tests.dst.postgres_support import isolated_absurd_database

REFUSAL_FIXTURE = Path("tests/dst/fixtures/joined-seal-commit-refusal-world-v3.json")
ACK_LOSS_FIXTURE = Path("tests/dst/fixtures/joined-seal-ack-loss-world-v3.json")


def test_joined_seal_refusal_is_exact_and_replayable(absurd_dsn: str) -> None:
    with isolated_absurd_database(absurd_dsn) as authored_dsn:
        artifact = build_joined_seal_refusal_artifact(authored_dsn)

    assert artifact.scenario_id == REFUSAL_SCENARIO_ID
    assert artifact.origin is None
    assert encode_artifact(artifact) == REFUSAL_FIXTURE.read_bytes().rstrip(b"\n")

    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedSealRefusalProfile(replay_dsn))
        registry.register_checker(JoinedSealAuthorityChecker())
        result = replay(artifact, registry)

    assert result.version == RESULT_VERSION
    assert result.outcome == "pass"
    assert result.disposition == Disposition.CONVERGED.value


def test_retained_joined_seal_refusal_replays_without_authored_scenario(absurd_dsn: str) -> None:
    artifact = load_artifact(REFUSAL_FIXTURE)
    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedSealRefusalProfile(replay_dsn))
        registry.register_checker(JoinedSealAuthorityChecker())
        result = replay(artifact, registry)

    assert result.scenario_id == REFUSAL_SCENARIO_ID
    assert result.outcome == "pass"


def test_joined_seal_ack_loss_is_exact_and_replayable(absurd_dsn: str) -> None:
    with isolated_absurd_database(absurd_dsn) as authored_dsn:
        artifact = build_joined_seal_ack_loss_artifact(authored_dsn)

    assert artifact.scenario_id == ACK_LOSS_SCENARIO_ID
    assert artifact.origin is None
    assert encode_artifact(artifact) == ACK_LOSS_FIXTURE.read_bytes().rstrip(b"\n")

    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedSealAckLossProfile(replay_dsn))
        registry.register_checker(JoinedSealAuthorityChecker())
        result = replay(artifact, registry)

    assert result.version == RESULT_VERSION
    assert result.outcome == "pass"
    assert result.disposition == Disposition.CONVERGED.value


def test_retained_joined_seal_ack_loss_replays_without_authored_scenario(absurd_dsn: str) -> None:
    artifact = load_artifact(ACK_LOSS_FIXTURE)
    with isolated_absurd_database(absurd_dsn) as replay_dsn:
        registry = ScenarioRegistry()
        registry.register_profile(JoinedSealAckLossProfile(replay_dsn))
        registry.register_checker(JoinedSealAuthorityChecker())
        result = replay(artifact, registry)

    assert result.scenario_id == ACK_LOSS_SCENARIO_ID
    assert result.outcome == "pass"


def test_joined_seal_checker_rejects_phantom_close_ack_loss_and_armed_reload() -> None:
    checker = JoinedSealAuthorityChecker()
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
    projection = {
        "accepted": True,
        "dispatch_attempted": False,
        "record_types": ["TokensProduced", "DeliveryRegistrationOpened", "FiringCompleted"],
    }
    refused_seal = {
        "accepted": False,
        "phase": "source_seal",
        "record_types": ["DeliveryRegistrationClosed", "DeliveryRegistrationClosed"],
    }
    accepted_seal = {**refused_seal, "accepted": True}
    open_registrations = [
        {"key": "default", "kind": "opened", "occurrence": None, "source": "source"},
        {"key": "subscription", "kind": "opened", "occurrence": 1, "source": "source"},
    ]
    closed_registrations = [
        *open_registrations,
        {"key": "default", "kind": "closed", "occurrence": None, "source": "source"},
        {"key": "subscription", "kind": "closed", "occurrence": None, "source": "source"},
    ]
    base = {
        "drive_calls": 2,
        "durable_tasks": [{"idempotency": "dst-world-joined-begin-refusal:occurrence-1", "state": "completed"}],
        "frontier": 13,
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
            "DeliveryRegistrationOpened",
            "FiringCompleted",
            "DeliveryRegistrationClosed",
            "DeliveryRegistrationClosed",
        ],
        "seal_calls": 1,
        "seal_refusals": 0,
        "transaction_attempts": [begin, terminal, projection],
        "worker_completions": 1,
    }
    phantom = Observation(
        name="engine.joined-seal-authority",
        value={
            **base,
            "canonical_registrations": closed_registrations,
            "engine_armed": None,
            "lifecycle_attempts": [refused_seal],
            "seal_ack_losses": 0,
            "seal_refusals": 1,
            "status": "poisoned",
        },
        instant=0,
        generation=1,
        sequence=0,
    )
    ack_without_acceptance = Observation(
        name="engine.joined-seal-authority",
        value={
            **base,
            "canonical_registrations": open_registrations,
            "engine_armed": None,
            "frontier": 11,
            "lifecycle_attempts": [refused_seal],
            "record_types": base["record_types"][:11],
            "seal_ack_losses": 1,
            "seal_refusals": 1,
            "status": "poisoned",
        },
        instant=0,
        generation=1,
        sequence=0,
    )
    wrong_reload = Observation(
        name="engine.joined-seal-authority",
        value={
            **base,
            "canonical_registrations": closed_registrations,
            "engine_armed": [
                {"key": "default", "source": "source"},
                {"key": "subscription", "source": "source"},
            ],
            "lifecycle_attempts": [accepted_seal],
            "seal_ack_losses": 1,
            "status": "terminated",
        },
        instant=0,
        generation=2,
        sequence=0,
    )

    phantom_result = checker.check(phantom)
    ack_result = checker.check(ack_without_acceptance)
    reload_result = checker.check(wrong_reload)

    assert phantom_result.passed is False
    assert phantom_result.detail["accepted_seals"] == 0
    assert ack_result.passed is False
    assert ack_result.detail["ack_losses"] == 1
    assert reload_result.passed is False
    assert reload_result.detail["engine_coherent"] is False
