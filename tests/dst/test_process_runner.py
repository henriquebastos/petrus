"""CV19.DS2 process-isolated wall-clock containment proof."""

from __future__ import annotations

from pathlib import Path

import pytest

from petrus.testing.dst import (
    PROCESS_RESULT_VERSION,
    PROCESS_RUNNER_API_COMPATIBILITY,
    Disposition,
    ProcessBudget,
    ProcessRunSpec,
    ScenarioRegistry,
    SubmitAttempt,
    replay,
    run_process_scenario,
)
from tests.dst.engine_world import (
    RESOURCE_SCENARIO_ID,
    EngineHistoryChecker,
    ResourceBoundedEngineProfile,
)
from tests.dst.process_world import HANG_SCENARIO_ID

PROCESS_PROGRESS_BYTES = 4_194_304


def test_process_input_budget_refuses_a_scenario_before_launch() -> None:
    spec = ProcessRunSpec(
        scenario_id=HANG_SCENARIO_ID,
        entrypoint="tests.dst.process_world:hang_during_command",
        payload=None,
        budget=ProcessBudget(
            wall_clock_ms=2_000,
            termination_grace_ms=100,
            input_bytes=1,
            progress_bytes=PROCESS_PROGRESS_BYTES,
        ),
    )

    with pytest.raises(ValueError, match="process run spec has .* bytes; limit is 1"):
        run_process_scenario(spec)


def test_complete_public_engine_world_runs_and_replays_from_a_fresh_process(tmp_path: Path) -> None:
    result = run_process_scenario(
        ProcessRunSpec(
            scenario_id=RESOURCE_SCENARIO_ID,
            entrypoint="tests.dst.process_world:resource_recovery",
            payload={"history_path": str(tmp_path / "process-author.jsonl")},
            budget=ProcessBudget(
                wall_clock_ms=30_000,
                termination_grace_ms=500,
                input_bytes=64_000,
                progress_bytes=PROCESS_PROGRESS_BYTES,
            ),
        )
    )

    assert result.version == PROCESS_RESULT_VERSION
    assert result.api == PROCESS_RUNNER_API_COMPATIBILITY
    assert result.outcome == "completed"
    assert result.termination == "exited"
    assert result.failure is None
    assert result.unfinished_attempt is None
    assert result.artifact is not None
    assert result.prefix.disposition == Disposition.CONVERGED.value
    assert len(result.prefix.operations) == 14
    assert len(result.prefix.journal) == 39
    assert result.prefix.last_resource is not None
    assert result.prefix.last_check is not None

    registry = ScenarioRegistry()
    registry.register_profile(ResourceBoundedEngineProfile(tmp_path / "process-replay.jsonl"))
    registry.register_checker(EngineHistoryChecker())
    replayed = replay(result.artifact, registry)
    assert replayed.outcome == "pass"
    assert replayed.disposition == Disposition.CONVERGED.value


def test_watchdog_terminates_and_reaps_a_hung_profile_with_its_acknowledged_prefix() -> None:
    result = run_process_scenario(
        ProcessRunSpec(
            scenario_id=HANG_SCENARIO_ID,
            entrypoint="tests.dst.process_world:hang_during_command",
            payload=None,
            budget=ProcessBudget(
                wall_clock_ms=2_000,
                termination_grace_ms=100,
                input_bytes=64_000,
                progress_bytes=PROCESS_PROGRESS_BYTES,
            ),
        )
    )

    assert result.outcome == "harness_failure"
    assert result.termination == "killed"
    assert result.returncode != 0
    assert result.failure is not None
    assert result.failure.kind == "wall_clock_timeout"
    assert result.failure.bound == "wall_clock_ms"
    assert result.failure.limit == 2_000
    assert result.artifact is None
    assert isinstance(result.unfinished_attempt, SubmitAttempt)
    assert result.unfinished_attempt.command.name == "runtime.hang"
    assert result.prefix.operations == []
    assert [entry.kind for entry in result.prefix.journal] == ["created"]
    assert result.prefix.disposition is None
