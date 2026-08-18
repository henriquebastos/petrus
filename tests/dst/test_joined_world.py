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
    SCENARIO_ID,
    JoinedBeginProfile,
    JoinedCommitAuthorityChecker,
    build_joined_begin_artifact,
)
from tests.dst.postgres_support import isolated_absurd_database

FIXTURE = Path("tests/dst/fixtures/joined-begin-commit-refusal-world-v3.json")


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
