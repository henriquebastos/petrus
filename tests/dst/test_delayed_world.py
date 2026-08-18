"""CV19.DS2 delayed external-terminal World/Timeline proof."""

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
from tests.dst.delayed_world import (
    SCENARIO_ID,
    DelayedAuthorityChecker,
    DelayedEngineProfile,
    build_delayed_artifact,
)

FIXTURE = Path("tests/dst/fixtures/delayed-terminal-recovery-world-v3.json")


def test_delayed_terminal_recovery_is_exact_and_replayable(tmp_path: Path) -> None:
    artifact = build_delayed_artifact(tmp_path / "delayed-author.jsonl")

    assert artifact.scenario_id == SCENARIO_ID
    assert artifact.origin is None
    assert encode_artifact(artifact) == FIXTURE.read_bytes().rstrip(b"\n")

    registry = ScenarioRegistry()
    registry.register_profile(DelayedEngineProfile(tmp_path / "delayed-replay.jsonl"))
    registry.register_checker(DelayedAuthorityChecker())
    result = replay(artifact, registry)

    assert result.version == RESULT_VERSION
    assert result.outcome == "pass"
    assert result.disposition == Disposition.CONVERGED.value
    assert result.operations == len(artifact.operations)


def test_delayed_terminal_manual_replay_route_is_deterministic() -> None:
    command = [sys.executable, "-m", "tests.dst.replay_world", str(FIXTURE)]
    first = subprocess.run(command, check=True, capture_output=True, text=True)
    second = subprocess.run(command, check=True, capture_output=True, text=True)

    assert first.stderr == second.stderr == ""
    assert first.stdout == second.stdout
    result = json.loads(first.stdout)
    assert result["version"] == RESULT_VERSION
    assert result["scenario_id"] == SCENARIO_ID
    assert result["outcome"] == "pass"
    assert result["disposition"] == Disposition.CONVERGED.value


def test_delayed_checker_refuses_terminal_before_authored_instant() -> None:
    checker = DelayedAuthorityChecker()
    observation = Observation(
        name="engine.delayed-authority",
        value={
            "record_types": ["ActivityRequested", "ActivityCompleted", "FiringCompleted"],
            "scheduled_terminal": {"instant": 5, "occurrence": 1, "result": {"value": 3}},
            "terminal_deliveries": 1,
        },
        instant=4,
        generation=2,
        sequence=0,
    )

    result: CheckResult = checker.check(observation)

    assert result.passed is False
    assert result.detail["scheduled_instant"] == 5
