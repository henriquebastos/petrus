"""CV19.DS2 post-commit History acknowledgement-loss proof."""

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
    HISTORY_ACK_LOSS_SCENARIO_ID,
    AcceptedCommitAuthorityChecker,
    HistoryAckLossEngineProfile,
    build_history_ack_loss_artifact,
)

FIXTURE = Path("tests/dst/fixtures/history-ack-loss-recovery-world-v3.json")


def test_history_ack_loss_recovery_is_exact_and_replayable(tmp_path: Path) -> None:
    artifact = build_history_ack_loss_artifact(tmp_path / "ack-loss-author.jsonl")

    assert artifact.scenario_id == HISTORY_ACK_LOSS_SCENARIO_ID
    assert artifact.origin is None
    assert encode_artifact(artifact) == FIXTURE.read_bytes().rstrip(b"\n")

    registry = ScenarioRegistry()
    registry.register_profile(HistoryAckLossEngineProfile(tmp_path / "ack-loss-replay.jsonl"))
    registry.register_checker(AcceptedCommitAuthorityChecker())
    result = replay(artifact, registry)

    assert result.version == RESULT_VERSION
    assert result.outcome == "pass"
    assert result.disposition == Disposition.CONVERGED.value
    assert result.operations == len(artifact.operations)


def test_history_ack_loss_manual_replay_route_is_deterministic() -> None:
    command = [sys.executable, "-m", "tests.dst.replay_world", str(FIXTURE)]
    first = subprocess.run(command, check=True, capture_output=True, text=True)
    second = subprocess.run(command, check=True, capture_output=True, text=True)

    assert first.stderr == second.stderr == ""
    assert first.stdout == second.stdout
    result = json.loads(first.stdout)
    assert result["version"] == RESULT_VERSION
    assert result["scenario_id"] == HISTORY_ACK_LOSS_SCENARIO_ID
    assert result["outcome"] == "pass"
    assert result["disposition"] == Disposition.CONVERGED.value


def test_accepted_commit_checker_refuses_missing_durable_terminal() -> None:
    checker = AcceptedCommitAuthorityChecker()
    observation = Observation(
        name="engine.accepted-commit-authority",
        value={
            "record_types": ["ActivityRequested"],
            "terminal_ack_losses": 1,
            "terminal_deliveries": 1,
        },
        instant=0,
        generation=1,
        sequence=0,
    )

    result: CheckResult = checker.check(observation)

    assert result.passed is False
    assert result.detail["durable_activity_terminals"] == 0
