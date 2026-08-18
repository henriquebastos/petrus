"""CV19.DS2 Dispatch-refusal crash/recovery World/Timeline proof."""

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
from tests.dst.engine_world import (
    DISPATCH_REFUSAL_SCENARIO_ID,
    DispatchAuthorityChecker,
    DispatchRefusalEngineProfile,
    build_dispatch_refusal_artifact,
)

FIXTURE = Path("tests/dst/fixtures/dispatch-refusal-crash-recovery-world-v3.json")


def test_dispatch_refusal_recovery_is_exact_and_replayable(tmp_path: Path) -> None:
    artifact = build_dispatch_refusal_artifact(tmp_path / "dispatch-refusal-author.jsonl")

    assert artifact.scenario_id == DISPATCH_REFUSAL_SCENARIO_ID
    assert artifact.origin is None
    assert encode_artifact(artifact) == FIXTURE.read_bytes().rstrip(b"\n")

    registry = ScenarioRegistry()
    registry.register_profile(DispatchRefusalEngineProfile(tmp_path / "dispatch-refusal-replay.jsonl"))
    registry.register_checker(DispatchAuthorityChecker())
    result = replay(artifact, registry)

    assert result.version == RESULT_VERSION
    assert result.outcome == "pass"
    assert result.disposition == Disposition.CONVERGED.value
    assert result.operations == len(artifact.operations)


def test_dispatch_refusal_manual_replay_route_is_deterministic() -> None:
    command = [sys.executable, "-m", "tests.dst.replay_world", str(FIXTURE)]
    first = subprocess.run(command, check=True, capture_output=True, text=True)
    second = subprocess.run(command, check=True, capture_output=True, text=True)

    assert first.stderr == second.stderr == ""
    assert first.stdout == second.stdout
    result = json.loads(first.stdout)
    assert result["version"] == RESULT_VERSION
    assert result["scenario_id"] == DISPATCH_REFUSAL_SCENARIO_ID
    assert result["outcome"] == "pass"
    assert result["disposition"] == Disposition.CONVERGED.value


def test_dispatch_checker_refuses_repreparation_or_changed_redispatch() -> None:
    checker = DispatchAuthorityChecker()
    observation = Observation(
        name="engine.dispatch-authority",
        value={
            "dispatch_attempts": [
                {
                    "accepted": False,
                    "activity": "calculate",
                    "correlation": "occurrence-1",
                    "idempotency": "occurrence-1",
                    "input": 3,
                    "occurrence": 1,
                    "policy": {},
                },
                {
                    "accepted": True,
                    "activity": "different",
                    "correlation": "occurrence-1",
                    "idempotency": "occurrence-1",
                    "input": 3,
                    "occurrence": 1,
                    "policy": {},
                },
            ],
            "prepare_calls": 2,
            "record_types": ["ActivityRequested", "ActivityCompleted", "FiringCompleted"],
        },
        instant=0,
        generation=2,
        sequence=0,
    )

    result: CheckResult = checker.check(observation)

    assert result.passed is False
    assert result.detail["invocation_stable"] is False
    assert result.detail["prepare_calls"] == 2
