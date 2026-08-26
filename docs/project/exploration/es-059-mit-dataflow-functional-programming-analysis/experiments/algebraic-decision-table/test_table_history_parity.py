"""Canonical History parity with the v1 slice, restart, and case attribution.

The strongest semantic-preservation evidence this experiment can produce: the
same fixture trace over the case-table flow appends **byte-identical**
canonical History to the v1 slice's retained artifact. A different authoring
surface produced the same runtime facts, in the same order, with the same
token payloads.
"""

from petrus.impetus.history import ActivityCompleted, ActivityRequested
from petrus.impetus.petrinet import NetPath
from petrus.impetus.scope import LifecycleScope

from explain import unattributed_records
from harness import FakeProviderLedger, drain, load, value_at
from domain import ReadinessState
from table_explain import case_attribution_gaps, explain_history_with_cases, serialize_explained_cases
from table_lowering import compile_flow
from table_run import (
    ARTIFACTS,
    GOLDEN,
    V1_HISTORY_ARTIFACT,
    V1_NET_GOLDEN,
    build_evidence,
    run_fixture,
)
from table_scenario import readiness_flow

REPAIR = NetPath("effects.repair.fire")


def test_canonical_history_is_byte_identical_to_the_v1_decide_function_slice(tmp_path):
    run = run_fixture(tmp_path / "history.jsonl", interrupt=False)
    try:
        assert run.history_path.read_bytes() == V1_HISTORY_ARTIFACT.read_bytes()
        assert run.compiled.definition_bytes == V1_NET_GOLDEN.read_bytes()
    finally:
        run.engine.close()


def test_restarted_and_uninterrupted_runs_have_identical_canonical_history(tmp_path):
    control = run_fixture(tmp_path / "control.jsonl", interrupt=False)
    restarted = run_fixture(tmp_path / "restarted.jsonl", interrupt=True)
    try:
        assert control.history_path.read_bytes() == restarted.history_path.read_bytes()
        assert control.records == restarted.records
        assert control.engine.marking == restarted.engine.marking
        assert dict(control.engine.active_scopes) == dict(restarted.engine.active_scopes)
        assert control.ledger.results == restarted.ledger.results
        assert control.ledger.attempts["repair:L2:build"] == 1
        assert restarted.ledger.attempts["repair:L2:build"] == 2
    finally:
        control.engine.close()
        restarted.engine.close()


def test_activity_requested_restart_redispatches_one_logical_operation(tmp_path):
    run = run_fixture(tmp_path / "history.jsonl", interrupt=True)
    try:
        assert run.ledger.attempts["repair:L2:build"] == 2
        requests = [
            record for record in run.records if isinstance(record, ActivityRequested) and record.transition == REPAIR
        ]
        assert len(requests) == 1
        completions = [
            record
            for record in run.records
            if isinstance(record, ActivityCompleted) and record.occurrence == requests[0].occurrence
        ]
        assert len(completions) == 1
        assert requests[0].correlation == requests[0].idempotency == "repair:L2:build"
        assert {op: count for op, count in run.ledger.attempts.items() if op != "repair:L2:build"} == {
            "publish:h1:g1": 1,
            "rerun:L2:build": 1,
            "publish:h2r:g3": 1,
        }
    finally:
        run.engine.close()


def test_engine_load_rebuilds_marking_scope_and_ladder_without_reexecuting_the_table(tmp_path):
    run = run_fixture(tmp_path / "history.jsonl", interrupt=False)
    run.engine.close()
    attempts_before = dict(run.ledger.attempts)

    engine = load(compile_flow(readiness_flow()), run.history_path, run.ledger)
    try:
        drain(engine)
        assert dict(engine.active_scopes) == {"branch": LifecycleScope("branch", 4)}
        assert engine.marking == run.pre_reload_marking
        state = value_at(engine, "readiness.state", ReadinessState)
        assert state.head == "h3" and state.generation == 4 and state.lineage == "L4"
        assert run.ledger.attempts == attempts_before
        assert engine.records == run.records
    finally:
        engine.close()


def test_every_decision_firing_names_its_case_or_reports_the_absorbing_candidates(tmp_path):
    run = run_fixture(tmp_path / "history.jsonl", interrupt=False)
    try:
        assert unattributed_records(run.records, run.compiled.source_map) == ()
        document = explain_history_with_cases(run.records, run.compiled.source_map, run.compiled)

        decisions = [
            group for group in document["occurrences"] if group["transition"] == document["decision_transition"]
        ]
        assert len(decisions) == 5

        named = [group for group in decisions if group["case"] is not None]
        assert [group["case"]["case"] for group in named] == ["publish", "rerun", "repair", "publish"]
        for group in named:
            assert group["case"]["source"]["file"] == "table_scenario.py"
            assert group["case"]["emits"] is not None

        # The honest limit: an absorbing firing produces only the state token,
        # so canonical History cannot separate the four ``.drop()`` rungs.
        gaps = case_attribution_gaps(document)
        assert len(gaps) == 1
        [absorbed] = [group for group in decisions if group["case"] is None]
        assert absorbed["case_candidates"] == ["foreign", "stale", "published", "unclassified"]
    finally:
        run.engine.close()


def test_explained_history_with_cases_matches_golden_and_is_not_execution_authority(tmp_path):
    run = run_fixture(tmp_path / "history.jsonl", interrupt=False)
    run.engine.close()

    reloaded = load(compile_flow(readiness_flow()), run.history_path, FakeProviderLedger())
    try:
        regenerated = serialize_explained_cases(
            explain_history_with_cases(reloaded.records, run.compiled.source_map, run.compiled)
        )
    finally:
        reloaded.close()

    assert regenerated == serialize_explained_cases(
        explain_history_with_cases(run.records, run.compiled.source_map, run.compiled)
    )
    assert regenerated == (GOLDEN / "readiness.explained-history-cases-v1.json").read_bytes()


def test_retained_goldens_and_artifacts_match_regenerated_evidence(tmp_path):
    """The retained bundle regenerates byte-identically, v1 comparisons included."""
    report = build_evidence(tmp_path)

    assert report["results"]["net_v3_identical_to_v1"] is True
    assert report["results"]["history_identical_to_v1"] is True
    assert (tmp_path / "readiness.net-v3.json").read_bytes() == V1_NET_GOLDEN.read_bytes()
    assert (tmp_path / "readiness.history.jsonl").read_bytes() == V1_HISTORY_ARTIFACT.read_bytes()
    for name in ("readiness.source-map-v1.json", "readiness.explained-history-cases-v1.json"):
        assert (tmp_path / name).read_bytes() == (GOLDEN / name).read_bytes(), name
    assert (tmp_path / "experiment-report.json").read_bytes() == (ARTIFACTS / "experiment-report.json").read_bytes()
