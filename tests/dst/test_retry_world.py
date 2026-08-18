"""CV19.DS2 LocalDispatch retry reconstruction World/Timeline proof."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from petrus.testing.dst import (
    RESULT_VERSION,
    CheckResult,
    Disposition,
    Observation,
    ScenarioRegistry,
    encode_artifact,
    replay,
)
from tests.dst.retry_world import (
    DELAYED_RETRY_SCENARIO_ID,
    RETRY_AVAILABLE_INSTANT,
    SCENARIO_ID,
    DelayedRetryAuthorityChecker,
    DelayedRetryEngineProfile,
    RetryAuthorityChecker,
    RetryEngineProfile,
    build_delayed_retry_artifact,
    build_retry_artifact,
)

FIXTURE = Path("tests/dst/fixtures/retry-crash-exhaustion-world-v3.json")
DELAYED_FIXTURE = Path("tests/dst/fixtures/delayed-retry-crash-recovery-world-v3.json")


def test_retry_crash_exhaustion_is_exact_and_replayable(tmp_path: Path) -> None:
    artifact = build_retry_artifact(tmp_path / "retry-author.jsonl", tmp_path / "retry-author.db")

    assert artifact.scenario_id == SCENARIO_ID
    assert artifact.origin is None
    assert encode_artifact(artifact) == FIXTURE.read_bytes().rstrip(b"\n")

    registry = ScenarioRegistry()
    registry.register_profile(RetryEngineProfile(tmp_path / "retry-replay.jsonl", tmp_path / "retry-replay.db"))
    registry.register_checker(RetryAuthorityChecker())
    result = replay(artifact, registry)

    assert result.version == RESULT_VERSION
    assert result.outcome == "pass"
    assert result.disposition == Disposition.QUARANTINED.value
    assert result.operations == len(artifact.operations)


def test_retry_manual_replay_route_is_deterministic() -> None:
    command = [sys.executable, "-m", "tests.dst.replay_world", str(FIXTURE)]
    first = subprocess.run(command, check=True, capture_output=True, text=True)
    second = subprocess.run(command, check=True, capture_output=True, text=True)

    assert first.stderr == second.stderr == ""
    assert first.stdout == second.stdout
    result = json.loads(first.stdout)
    assert result["version"] == RESULT_VERSION
    assert result["scenario_id"] == SCENARIO_ID
    assert result["outcome"] == "pass"
    assert result["disposition"] == Disposition.QUARANTINED.value


def test_delayed_retry_crash_recovery_is_exact_and_replayable(tmp_path: Path) -> None:
    artifact = build_delayed_retry_artifact(
        tmp_path / "delayed-retry-author.jsonl", tmp_path / "delayed-retry-author.db"
    )

    assert artifact.scenario_id == DELAYED_RETRY_SCENARIO_ID
    assert artifact.origin is None
    assert encode_artifact(artifact) == DELAYED_FIXTURE.read_bytes().rstrip(b"\n")

    registry = ScenarioRegistry()
    registry.register_profile(
        DelayedRetryEngineProfile(tmp_path / "delayed-retry-replay.jsonl", tmp_path / "delayed-retry-replay.db")
    )
    registry.register_checker(DelayedRetryAuthorityChecker())
    result = replay(artifact, registry)

    assert result.version == RESULT_VERSION
    assert result.outcome == "pass"
    assert result.disposition == Disposition.QUARANTINED.value
    assert result.operations == len(artifact.operations)


def test_delayed_retry_manual_replay_route_is_deterministic() -> None:
    command = [sys.executable, "-m", "tests.dst.replay_world", str(DELAYED_FIXTURE)]
    first = subprocess.run(command, check=True, capture_output=True, text=True)
    second = subprocess.run(command, check=True, capture_output=True, text=True)

    assert first.stderr == second.stderr == ""
    assert first.stdout == second.stdout
    result = json.loads(first.stdout)
    assert result["version"] == RESULT_VERSION
    assert result["scenario_id"] == DELAYED_RETRY_SCENARIO_ID
    assert result["outcome"] == "pass"
    assert result["disposition"] == Disposition.QUARANTINED.value


def test_retry_checker_refuses_terminal_before_exhaustion() -> None:
    checker = RetryAuthorityChecker()
    observation = Observation(
        name="engine.retry-authority",
        value={
            "attempts": [
                {
                    "activity": "work",
                    "correlation": "occurrence-1",
                    "epoch": 1,
                    "idempotency": "occurrence-1",
                    "input": 3,
                    "instance": "dst-world-retry-recovery",
                    "policy": {},
                    "queue": "default",
                }
            ],
            "failures_delivered": 1,
            "record_types": [
                "InstanceCreated",
                "ActivityRequested",
                "ActivityFailed",
                "FiringFailed",
            ],
        },
        instant=0,
        generation=1,
        sequence=0,
    )

    result: CheckResult = checker.check(observation)

    assert result.passed is False
    assert result.detail["accepted_terminal_limit"] == 0


def test_delayed_retry_checker_refuses_an_early_second_claim() -> None:
    checker = DelayedRetryAuthorityChecker()
    attempt = {
        "activity": "work",
        "correlation": "occurrence-1",
        "idempotency": "occurrence-1",
        "input": 3,
        "instance": "dst-world-retry-recovery",
        "policy": {"initial_interval": RETRY_AVAILABLE_INSTANT},
        "queue": "default",
    }
    observation = Observation(
        name="engine.delayed-retry-authority",
        value={
            "attempts": [{**attempt, "epoch": 1}, {**attempt, "epoch": 2}],
            "claim_checks": [
                {"available": True, "epoch": 1, "instant": 0},
                {"available": True, "epoch": 2, "instant": RETRY_AVAILABLE_INSTANT - 1},
            ],
            "current_instant": RETRY_AVAILABLE_INSTANT - 1,
            "failures_delivered": 1,
            "record_types": ["InstanceCreated", "ActivityRequested"],
        },
        instant=RETRY_AVAILABLE_INSTANT - 1,
        generation=2,
        sequence=0,
    )

    result = checker.check(observation)

    assert result.passed is False
    assert result.detail["exact_prefix"] is False
    assert result.detail["no_early_retry"] is False
