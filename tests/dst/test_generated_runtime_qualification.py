"""CV19.DS3 fair-liveness, shrinking, and semantic-coverage qualification."""

from __future__ import annotations

import json
import subprocess
import sys
from itertools import count
from pathlib import Path
from typing import cast

import pytest
from hypothesis import Phase, find, settings, strategies as st
from pydantic import JsonValue

from petrus.testing.dst import (
    BudgetExhausted,
    Disposition,
    DstError,
    ExecuteOperation,
    FailureOperation,
    RunUntilFailed,
    ScenarioArtifact,
    ScenarioRegistry,
    World,
    encode_artifact,
    replay,
)
from tests.dst.generated_runtime_qualification import (
    BROAD_ONLY_SCENARIO_ID,
    DISCOVERY_SEED,
    FAIR_BUDGET,
    MINIMIZED_SCENARIO_ID,
    LivelockMutationProfile,
    build_broad_only_artifact,
    build_minimized_fair_regression_artifact,
    establish_fair_spine,
    semantic_coverage_report,
)
from tests.dst.generated_runtime_world import (
    SCENARIO_ID,
    SCOPE_NAME,
    GeneratedRuntimeAuthorityChecker,
    GeneratedRuntimeProfile,
    WORLD_BUDGET,
    build_generated_runtime_artifact,
)

FIXTURES = Path(__file__).parent / "fixtures"
MINIMIZED_FIXTURE = FIXTURES / "generated-runtime-minimized-fair-regression-v4.json"
COVERAGE_FIXTURE = FIXTURES / "generated-runtime-semantic-coverage-v1.json"


def _livelock_artifact(
    root: Path,
    *,
    retry: bool,
    perturbations: tuple[str, ...],
) -> ScenarioArtifact:
    profile = LivelockMutationProfile(root / "history.jsonl", root / "dispatch.db")
    world = World(profile, FAIR_BUDGET, checkers=(GeneratedRuntimeAuthorityChecker(),))
    try:
        establish_fair_spine(
            world,
            identity="shrinking-livelock-event",
            value=0,
            retry=retry,
            perturbations=perturbations,
        )
        with pytest.raises(BudgetExhausted, match="actions"):
            while world.pending():
                world.step()
        artifact = world.artifact("generated-runtime-minimized-livelock-mutation-v4")
        assert isinstance(artifact, ScenarioArtifact)
        return artifact
    finally:
        world.close()


def test_fair_phase_converges_and_minimized_regression_replays_exactly(tmp_path: Path) -> None:
    checked = build_minimized_fair_regression_artifact(
        tmp_path / "author-history.jsonl",
        tmp_path / "author-dispatch.db",
    )
    artifact = build_minimized_fair_regression_artifact(
        tmp_path / "fixture-history.jsonl",
        tmp_path / "fixture-dispatch.db",
        with_checker=False,
    )

    assert artifact.scenario_id == MINIMIZED_SCENARIO_ID
    assert artifact.expected.disposition == Disposition.QUIESCENT.value
    assert artifact.origin is not None
    assert artifact.origin.seed == DISCOVERY_SEED
    assert artifact.origin.draws == {"identifier:shrink-event": 1}
    assert any(operation.kind == "begin_fair" for operation in artifact.operations)
    assert checked.operations == artifact.operations
    assert checked.expected.checks
    assert all(cast(dict[str, JsonValue], entry.value)["result"]["passed"] is True for entry in checked.expected.checks)
    final_check = cast(dict[str, JsonValue], checked.expected.checks[-1].value)
    final_observation = cast(dict[str, JsonValue], final_check["observation"])
    final_state = cast(dict[str, JsonValue], final_observation["value"])
    assert final_state["status"] == "awaiting"
    assert final_state["live_in_flight"] == []
    assert {entry["transition"] for entry in cast(list[dict[str, JsonValue]], final_state["firing_completed"])} >= {
        "work",
        "release",
    }
    assert encode_artifact(artifact) == MINIMIZED_FIXTURE.read_bytes().rstrip(b"\n")

    registry = ScenarioRegistry()
    registry.register_profile(
        GeneratedRuntimeProfile(
            tmp_path / "replay-history.jsonl",
            tmp_path / "replay-dispatch.db",
        )
    )
    result = replay(artifact, registry)

    assert result.outcome == "pass"
    assert result.disposition == Disposition.QUIESCENT.value
    assert result.journal_digest == artifact.expected.journal_digest

    completed = subprocess.run(
        [sys.executable, "-m", "tests.dst.replay_world", str(MINIMIZED_FIXTURE)],
        check=True,
        capture_output=True,
        text=True,
    )
    manual = json.loads(completed.stdout)
    assert completed.stderr == ""
    assert manual["scenario_id"] == MINIMIZED_SCENARIO_ID
    assert manual["outcome"] == "pass"
    assert manual["disposition"] == Disposition.QUIESCENT.value


def test_external_wait_and_inadequate_fair_declaration_remain_distinct(tmp_path: Path) -> None:
    waiting = World(
        GeneratedRuntimeProfile(tmp_path / "wait-history.jsonl", tmp_path / "wait-dispatch.db"),
        WORLD_BUDGET,
    )
    try:
        waiting.timeline().command("scope.open", {"name": SCOPE_NAME})
        with pytest.raises(RunUntilFailed) as external:
            waiting.timeline().run_until("generated-runtime-state", lambda observation: False)
        assert external.value.disposition is Disposition.EXTERNAL_WAIT
        assert external.value.pending == []
    finally:
        waiting.close()

    inadequate = World(
        GeneratedRuntimeProfile(tmp_path / "fair-history.jsonl", tmp_path / "fair-dispatch.db"),
        WORLD_BUDGET,
    )
    try:
        timeline = inadequate.timeline()
        timeline.command("scope.open", {"name": SCOPE_NAME})
        timeline.begin_fair()
        with pytest.raises(RunUntilFailed) as stalled:
            timeline.run_until("generated-runtime-state", lambda observation: False)
        assert stalled.value.disposition is Disposition.EXTERNAL_WAIT
        assert stalled.value.pending == []
        with pytest.raises(DstError, match="active DST fair phase"):
            timeline.finish(Disposition.EXTERNAL_WAIT)
    finally:
        inadequate.close()


def test_fair_budget_exhaustion_is_exact_without_becoming_livelock(tmp_path: Path) -> None:
    budget = FAIR_BUDGET.model_copy(update={"actions": 9})
    profile = GeneratedRuntimeProfile(tmp_path / "author-history.jsonl", tmp_path / "author-dispatch.db")
    world = World(profile, budget, checkers=(GeneratedRuntimeAuthorityChecker(),))
    try:
        establish_fair_spine(world, identity="bounded-fair-event", value=0)
        with pytest.raises(BudgetExhausted, match="actions"):
            world.step()
        artifact = world.artifact("generated-runtime-fair-budget-exhaustion-v4")
    finally:
        world.close()

    failure = artifact.operations[-1]
    assert isinstance(failure, FailureOperation)
    assert failure.failure.kind == "budget_exhausted"
    assert failure.failure.bound == "actions"
    assert failure.accepted_operations == 0
    assert artifact.operations[-2].kind == "begin_fair"

    registry = ScenarioRegistry()
    registry.register_profile(
        GeneratedRuntimeProfile(tmp_path / "replay-history.jsonl", tmp_path / "replay-dispatch.db")
    )
    registry.register_checker(GeneratedRuntimeAuthorityChecker())
    result = replay(artifact, registry)
    assert result.disposition == Disposition.BUDGET_EXHAUSTED.value
    assert result.failure == artifact.expected.failure


def test_hypothesis_shrinks_safety_preserving_livelock_and_failure_replays(tmp_path: Path) -> None:
    cases = count()

    def reproduces(candidate: tuple[bool, tuple[str, ...]]) -> bool:
        retry, perturbations = candidate
        artifact = _livelock_artifact(
            tmp_path / f"search-{next(cases)}",
            retry=retry,
            perturbations=perturbations,
        )
        return artifact.expected.disposition == Disposition.BUDGET_EXHAUSTED.value

    strategy = st.tuples(
        st.booleans(),
        st.lists(st.sampled_from(("observe", "crash_reload")), max_size=3).map(tuple),
    )
    unreduced = _livelock_artifact(
        tmp_path / "unreduced",
        retry=True,
        perturbations=("observe", "crash_reload", "observe"),
    )
    minimized = find(
        strategy,
        reproduces,
        settings=settings(
            max_examples=20,
            derandomize=True,
            database=None,
            deadline=None,
            phases=(Phase.generate, Phase.shrink),
        ),
    )
    assert minimized == (False, ())

    artifact = _livelock_artifact(
        tmp_path / "minimized",
        retry=minimized[0],
        perturbations=minimized[1],
    )
    minimized_fair = next(operation.position for operation in artifact.operations if operation.kind == "begin_fair")
    unreduced_fair = next(operation.position for operation in unreduced.operations if operation.kind == "begin_fair")
    assert minimized_fair < unreduced_fair
    assert len(encode_artifact(artifact)) < len(encode_artifact(unreduced))
    assert artifact.expected.disposition == Disposition.BUDGET_EXHAUSTED.value
    assert artifact.expected.failure is not None
    assert all(
        cast(dict[str, JsonValue], entry.value)["result"]["passed"] is True for entry in artifact.expected.checks
    )

    drives = [
        operation
        for operation in artifact.operations
        if isinstance(operation, ExecuteOperation) and operation.command.name == "engine.drive"
    ]
    stalled = drives[-3:]
    assert len(stalled) == 3
    assert len({operation.instant for operation in stalled}) == 1
    assert len({cast(dict[str, JsonValue], operation.result.value)["frontier"] for operation in stalled}) == 1

    registry = ScenarioRegistry()
    registry.register_profile(
        LivelockMutationProfile(
            tmp_path / "mutation-replay-history.jsonl",
            tmp_path / "mutation-replay-dispatch.db",
        )
    )
    registry.register_checker(GeneratedRuntimeAuthorityChecker())
    result = replay(artifact, registry)

    assert result.outcome == "pass"
    assert result.disposition == Disposition.BUDGET_EXHAUSTED.value
    assert result.failure == artifact.expected.failure
    assert result.journal_digest == artifact.expected.journal_digest


def test_semantic_coverage_reports_broad_only_and_excluded_dimensions(tmp_path: Path) -> None:
    focused = build_generated_runtime_artifact(
        tmp_path / "focused-history.jsonl",
        tmp_path / "focused-dispatch.db",
        first_value=-3,
        second_value=0,
    )
    broad = build_broad_only_artifact(
        tmp_path / "broad-history.jsonl",
        tmp_path / "broad-dispatch.db",
    )
    report = semantic_coverage_report(focused, broad)

    assert focused.scenario_id == SCENARIO_ID
    assert broad.scenario_id == BROAD_ONLY_SCENARIO_ID
    assert report == json.loads(COVERAGE_FIXTURE.read_bytes())
    assert report["broad_only"] == ["retry-then-reset-before-terminal"]
    reached = cast(dict[str, JsonValue], report["reached"])
    assert reached["boundaries"] == [
        "action:applied",
        "action:idempotent",
        "action:refused_expected",
        "logical-time:deadline",
        "source-value:negative",
        "source-value:positive",
        "source-value:zero",
        "worker-epoch:1",
        "worker-epoch:2",
    ]
    assert len(cast(list[JsonValue], report["unreachable"])) == 3
    assert len(cast(list[JsonValue], report["intentionally_ungenerated"])) == 4

    registry = ScenarioRegistry()
    registry.register_profile(
        GeneratedRuntimeProfile(tmp_path / "broad-replay-history.jsonl", tmp_path / "broad-replay-dispatch.db")
    )
    registry.register_checker(GeneratedRuntimeAuthorityChecker())
    result = replay(broad, registry)
    assert result.outcome == "pass"
    assert result.disposition == Disposition.EXTERNAL_WAIT.value
