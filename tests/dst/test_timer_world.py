"""CV19.DS2 timer crash/reconstruction World/Timeline proof."""

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
from tests.dst.timer_world import (
    MATURATION_INSTANT,
    SCENARIO_ID,
    TimerAuthorityChecker,
    TimerEngineProfile,
    build_timer_artifact,
)

FIXTURE = Path("tests/dst/fixtures/timer-crash-recovery-world-v3.json")


def test_timer_crash_recovery_is_exact_and_replayable(tmp_path: Path) -> None:
    artifact = build_timer_artifact(tmp_path / "timer-author.jsonl")

    assert artifact.scenario_id == SCENARIO_ID
    assert artifact.origin is None
    assert encode_artifact(artifact) == FIXTURE.read_bytes().rstrip(b"\n")

    registry = ScenarioRegistry()
    registry.register_profile(TimerEngineProfile(tmp_path / "timer-replay.jsonl"))
    registry.register_checker(TimerAuthorityChecker())
    result = replay(artifact, registry)

    assert result.version == RESULT_VERSION
    assert result.outcome == "pass"
    assert result.disposition == Disposition.CONVERGED.value
    assert result.operations == len(artifact.operations)


def test_timer_manual_replay_route_is_deterministic() -> None:
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


def test_timer_checker_refuses_early_maturation() -> None:
    checker = TimerAuthorityChecker()
    observation = Observation(
        name="engine.timer-authority",
        value={
            "authored_maturation_instant": MATURATION_INSTANT,
            "current_instant": MATURATION_INSTANT - 1,
            "record_types": ["InstanceCreated", "TokensInitialized", "TimerMatured"],
            "timer_maturations": [
                {
                    "instant": MATURATION_INSTANT - 1,
                    "maturation_instant": MATURATION_INSTANT,
                }
            ],
        },
        instant=MATURATION_INSTANT - 1,
        generation=1,
        sequence=0,
    )

    result: CheckResult = checker.check(observation)

    assert result.passed is False
    assert result.detail["current_instant"] == MATURATION_INSTANT - 1
