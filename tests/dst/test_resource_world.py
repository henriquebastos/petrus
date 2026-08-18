"""CV19.DS2 version-4 profile-resource accounting proof."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from petrus.testing.dst import (
    ARTIFACT_VERSION,
    RESULT_VERSION,
    Disposition,
    FailureOperation,
    ScenarioRegistry,
    encode_artifact,
    replay,
)
from tests.dst.engine_world import (
    RESOURCE_BUDGET_FAILURE_SCENARIO_ID,
    RESOURCE_SCENARIO_ID,
    EngineHistoryChecker,
    ResourceBoundedEngineProfile,
    build_resource_bounded_artifact,
    build_resource_budget_failure_artifact,
)

GREEN_FIXTURE = Path("tests/dst/fixtures/resource-bounded-recovery-world-v4.json")
FAILURE_FIXTURE = Path("tests/dst/fixtures/history-record-budget-exhaustion-world-v4.json")


def test_resource_bounded_recovery_is_exact_and_replayable(tmp_path: Path) -> None:
    artifact = build_resource_bounded_artifact(tmp_path / "resource-author.jsonl")

    assert artifact.version == ARTIFACT_VERSION
    assert artifact.scenario_id == RESOURCE_SCENARIO_ID
    assert artifact.expected.disposition == Disposition.CONVERGED.value
    assert encode_artifact(artifact) == GREEN_FIXTURE.read_bytes().rstrip(b"\n")

    registry = ScenarioRegistry()
    registry.register_profile(ResourceBoundedEngineProfile(tmp_path / "resource-replay.jsonl"))
    registry.register_checker(EngineHistoryChecker())
    result = replay(artifact, registry)

    assert result.version == RESULT_VERSION
    assert result.outcome == "pass"
    assert result.disposition == Disposition.CONVERGED.value
    assert result.operations == 14
    assert result.journal_entries == 39


def test_history_resource_overage_retains_the_accepted_engine_operation(tmp_path: Path) -> None:
    artifact = build_resource_budget_failure_artifact(tmp_path / "resource-failure-author.jsonl")

    assert artifact.version == ARTIFACT_VERSION
    assert artifact.scenario_id == RESOURCE_BUDGET_FAILURE_SCENARIO_ID
    assert encode_artifact(artifact) == FAILURE_FIXTURE.read_bytes().rstrip(b"\n")
    failure = artifact.operations[-1]
    assert isinstance(failure, FailureOperation)
    assert failure.accepted_operations == 1
    assert failure.attempt.kind == "step"
    assert failure.failure.kind == "budget_exhausted"
    assert failure.failure.bound == "profile_resources:retained.history_records"
    assert artifact.operations[-2].kind == "execute"

    registry = ScenarioRegistry()
    registry.register_profile(ResourceBoundedEngineProfile(tmp_path / "resource-failure-replay.jsonl"))
    registry.register_checker(EngineHistoryChecker())
    result = replay(artifact, registry)

    assert result.outcome == "pass"
    assert result.disposition == Disposition.BUDGET_EXHAUSTED.value
    assert result.failure == artifact.expected.failure
    assert result.operations == 3
    assert result.journal_entries == 10


@pytest.mark.parametrize(
    ("fixture", "scenario_id", "disposition"),
    [
        (GREEN_FIXTURE, RESOURCE_SCENARIO_ID, Disposition.CONVERGED),
        (FAILURE_FIXTURE, RESOURCE_BUDGET_FAILURE_SCENARIO_ID, Disposition.BUDGET_EXHAUSTED),
    ],
)
def test_resource_manual_replay_route_is_deterministic(
    fixture: Path,
    scenario_id: str,
    disposition: Disposition,
) -> None:
    command = [sys.executable, "-m", "tests.dst.replay_world", str(fixture)]
    first = subprocess.run(command, check=True, capture_output=True, text=True)
    second = subprocess.run(command, check=True, capture_output=True, text=True)

    assert first.stderr == second.stderr == ""
    assert first.stdout == second.stdout
    result = json.loads(first.stdout)
    assert result["version"] == RESULT_VERSION
    assert result["scenario_id"] == scenario_id
    assert result["outcome"] == "pass"
    assert result["disposition"] == disposition.value
