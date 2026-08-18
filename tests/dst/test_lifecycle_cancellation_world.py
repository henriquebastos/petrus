"""CV19.DS2 lifecycle cancellation-refusal World/Timeline proof."""

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
from tests.dst.lifecycle_world import (
    CANCELLATION_SCENARIO_ID,
    CancellationAuthorityChecker,
    LifecycleCancellationRefusalProfile,
    build_lifecycle_cancellation_artifact,
)

FIXTURE = Path("tests/dst/fixtures/lifecycle-cancellation-refusal-world-v3.json")


def test_lifecycle_cancellation_refusal_is_exact_and_replayable(tmp_path: Path) -> None:
    artifact = build_lifecycle_cancellation_artifact(tmp_path / "cancellation-author.jsonl")

    assert artifact.scenario_id == CANCELLATION_SCENARIO_ID
    assert artifact.origin is None
    assert encode_artifact(artifact) == FIXTURE.read_bytes().rstrip(b"\n")

    registry = ScenarioRegistry()
    registry.register_profile(LifecycleCancellationRefusalProfile(tmp_path / "cancellation-replay.jsonl"))
    registry.register_checker(CancellationAuthorityChecker())
    result = replay(artifact, registry)

    assert result.version == RESULT_VERSION
    assert result.outcome == "pass"
    assert result.disposition == Disposition.QUIESCENT.value
    assert result.operations == len(artifact.operations)


def test_lifecycle_cancellation_manual_replay_route_is_deterministic() -> None:
    command = [sys.executable, "-m", "tests.dst.replay_world", str(FIXTURE)]
    first = subprocess.run(command, check=True, capture_output=True, text=True)
    second = subprocess.run(command, check=True, capture_output=True, text=True)

    assert first.stderr == second.stderr == ""
    assert first.stdout == second.stdout
    result = json.loads(first.stdout)
    assert result["version"] == RESULT_VERSION
    assert result["scenario_id"] == CANCELLATION_SCENARIO_ID
    assert result["outcome"] == "pass"
    assert result["disposition"] == Disposition.QUIESCENT.value


def test_cancellation_checker_refuses_a_changed_repair_instruction() -> None:
    checker = CancellationAuthorityChecker()
    observation = Observation(
        name="engine.cancellation-authority",
        value={
            "active_scopes": {"draft": 2},
            "authored_scope_generation": 2,
            "authored_scope_opens": 1,
            "authored_scope_resets": 1,
            "authored_source_deliveries": 1,
            "authored_terminal_deliveries": 0,
            "cancellation_attempts": [
                {
                    "accepted": False,
                    "activity": "calculate",
                    "correlation": "occurrence-2",
                    "disposition": None,
                    "history_position": 9,
                    "idempotency": "occurrence-2",
                    "input": 3,
                    "occurrence": 2,
                    "policy": {},
                },
                {
                    "accepted": True,
                    "activity": "different",
                    "correlation": "occurrence-2",
                    "disposition": "tombstoned",
                    "history_position": 9,
                    "idempotency": "occurrence-2",
                    "input": 3,
                    "occurrence": 2,
                    "policy": {},
                },
            ],
            "record_types": ["ScopeOpened", "FiringCompleted", "ActivityRequested", "ScopeReset"],
        },
        instant=0,
        generation=2,
        sequence=0,
    )

    result: CheckResult = checker.check(observation)

    assert result.passed is False
    assert result.detail["instruction_stable"] is False


def test_cancellation_checker_keeps_reset_as_late_terminal_authority() -> None:
    checker = CancellationAuthorityChecker()
    observation = Observation(
        name="engine.cancellation-authority",
        value={
            "active_scopes": {"draft": 2},
            "authored_scope_generation": 2,
            "authored_scope_opens": 1,
            "authored_scope_resets": 1,
            "authored_source_deliveries": 1,
            "authored_terminal_deliveries": 1,
            "cancellation_attempts": [],
            "record_types": [
                "ScopeOpened",
                "FiringCompleted",
                "ActivityRequested",
                "ScopeReset",
                "ActivityTerminalQuarantined",
            ],
        },
        instant=0,
        generation=2,
        sequence=0,
    )

    result: CheckResult = checker.check(observation)

    assert result.passed is True
    assert result.detail["accepted_cancellations"] == 0
    assert result.detail["terminal_quarantined"] == 1
