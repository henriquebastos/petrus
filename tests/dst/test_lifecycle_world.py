"""CV19.DS2 lifecycle-race World/Timeline proof."""

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
    SCENARIO_ID,
    LifecycleAuthorityChecker,
    LifecycleEngineProfile,
    build_lifecycle_artifact,
)

FIXTURE = Path("tests/dst/fixtures/lifecycle-reset-late-terminal-world-v3.json")


def test_lifecycle_reset_late_terminal_is_exact_and_replayable(tmp_path: Path) -> None:
    artifact = build_lifecycle_artifact(tmp_path / "lifecycle-author.jsonl")

    assert artifact.scenario_id == SCENARIO_ID
    assert artifact.origin is None
    assert encode_artifact(artifact) == FIXTURE.read_bytes().rstrip(b"\n")

    registry = ScenarioRegistry()
    registry.register_profile(LifecycleEngineProfile(tmp_path / "lifecycle-replay.jsonl"))
    registry.register_checker(LifecycleAuthorityChecker())
    result = replay(artifact, registry)

    assert result.version == RESULT_VERSION
    assert result.outcome == "pass"
    assert result.disposition == Disposition.QUIESCENT.value
    assert result.operations == len(artifact.operations)


def test_lifecycle_manual_replay_route_is_deterministic() -> None:
    command = [sys.executable, "-m", "tests.dst.replay_world", str(FIXTURE)]
    first = subprocess.run(command, check=True, capture_output=True, text=True)
    second = subprocess.run(command, check=True, capture_output=True, text=True)

    assert first.stderr == second.stderr == ""
    assert first.stdout == second.stdout
    result = json.loads(first.stdout)
    assert result["version"] == RESULT_VERSION
    assert result["scenario_id"] == SCENARIO_ID
    assert result["outcome"] == "pass"
    assert result["disposition"] == Disposition.QUIESCENT.value


def test_lifecycle_checker_refuses_projection_of_cancelled_work() -> None:
    checker = LifecycleAuthorityChecker()
    observation = Observation(
        name="engine.lifecycle-authority",
        value={
            "active_scopes": {"draft": 2},
            "authored_scope_generation": 2,
            "authored_scope_opens": 1,
            "authored_scope_resets": 1,
            "authored_source_deliveries": 1,
            "authored_terminal_deliveries": 1,
            "record_types": [
                "ScopeOpened",
                "FiringCompleted",
                "ScopeReset",
                "ActivityCompleted",
                "FiringCompleted",
            ],
        },
        instant=0,
        generation=2,
        sequence=0,
    )

    result: CheckResult = checker.check(observation)

    assert result.passed is False
    assert result.detail["activity_terminals"] == 1
