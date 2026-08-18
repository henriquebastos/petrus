"""CV19.DS2 LocalDispatch terminal-custody World/Timeline proof."""

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
    TERMINAL_SCENARIO_ID,
    TerminalAuthorityChecker,
    TerminalEngineProfile,
    build_terminal_artifact,
)

FIXTURE = Path("tests/dst/fixtures/local-terminal-redelivery-world-v3.json")


def test_local_terminal_redelivery_is_exact_and_replayable(tmp_path: Path) -> None:
    artifact = build_terminal_artifact(tmp_path / "terminal-author.jsonl", tmp_path / "terminal-author.db")

    assert artifact.scenario_id == TERMINAL_SCENARIO_ID
    assert artifact.origin is None
    assert encode_artifact(artifact) == FIXTURE.read_bytes().rstrip(b"\n")

    registry = ScenarioRegistry()
    registry.register_profile(
        TerminalEngineProfile(tmp_path / "terminal-replay.jsonl", tmp_path / "terminal-replay.db")
    )
    registry.register_checker(TerminalAuthorityChecker())
    result = replay(artifact, registry)

    assert result.version == RESULT_VERSION
    assert result.outcome == "pass"
    assert result.disposition == Disposition.CONVERGED.value
    assert result.operations == len(artifact.operations)


def test_local_terminal_manual_replay_route_is_deterministic() -> None:
    command = [sys.executable, "-m", "tests.dst.replay_world", str(FIXTURE)]
    first = subprocess.run(command, check=True, capture_output=True, text=True)
    second = subprocess.run(command, check=True, capture_output=True, text=True)

    assert first.stderr == second.stderr == ""
    assert first.stdout == second.stdout
    result = json.loads(first.stdout)
    assert result["version"] == RESULT_VERSION
    assert result["scenario_id"] == TERMINAL_SCENARIO_ID
    assert result["outcome"] == "pass"
    assert result["disposition"] == Disposition.CONVERGED.value


def test_local_terminal_checker_refuses_conflicting_projection() -> None:
    checker = TerminalAuthorityChecker()
    observation = Observation(
        name="engine.local-terminal-authority",
        value={
            "accepted_results": [{"value": 6}],
            "attempts": [{"epoch": 1}],
            "bridge": {"prepared": 0, "projected": 1},
            "marking": [{"place": "done", "tokens": [{"color": "Done", "data": {"value": 7}}]}],
            "record_types": [
                "InstanceCreated",
                "ActivityRequested",
                "ActivityCompleted",
                "FiringCompleted",
            ],
            "status": "completed",
            "terminal_reports": [
                {"disposition": "applied", "result": {"value": 6}},
                {"disposition": "idempotent", "result": {"value": 6}},
                {"disposition": "refused_expected", "result": {"value": 7}},
            ],
        },
        instant=0,
        generation=2,
        sequence=0,
    )

    result: CheckResult = checker.check(observation)

    assert result.passed is False
    assert result.detail["projected_results"] == [{"value": 7}]
