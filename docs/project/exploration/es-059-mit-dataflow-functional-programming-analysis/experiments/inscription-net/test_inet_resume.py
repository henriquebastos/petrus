"""Restart, replay, attribution, and the retained evidence bundle.

The claims deliberately **not** made: OS-process kill, power-loss durability,
remote Worker recovery, or exactly-once effects. This is in-process
object-reconstruction evidence over a real durable JSONL store, and the fake
provider simulates an idempotency boundary — it proves nothing about real
providers.
"""

import json
from pathlib import Path

import pytest

from petrus.impetus.history import ActivityCompleted, ActivityRequested, FiringCompleted
from petrus.impetus.petrinet import NetPath

from inet_explain import decisions, explain_history, serialize_explained, unattributed_records
from inet_harness import FakeProviderLedger, create, deliver_ci, deliver_head, drain, load, value_at
from inet_lowering import EVALUATIONS, compile_flow
from inet_run import ARTIFACT_FILES, GOLDEN_FILES, build_evidence, run_fixture
from inet_scenario import readiness_flow
from inet_tokens import CIObserved, EvidenceId, HeadFact, HeadObserved

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "golden"
ARTIFACTS = HERE / "artifacts"


def test_the_uninterrupted_fixture_reaches_every_expected_outcome(tmp_path):
    run = run_fixture(tmp_path / "readiness.jsonl", interrupt=False)
    try:
        assert run.ledger.attempts == {
            "publish:h1:g1": 1,
            "rerun:L2:build": 1,
            "repair:L2:build": 1,
            "publish:h2r:g3": 1,
        }
        assert run.branches == ("publish", "rerun", "stale", "repair", "publish")
    finally:
        run.engine.close()


def test_activity_requested_restart_redispatches_one_logical_operation(tmp_path):
    """Interrupted after ``ActivityRequested`` for the repair, before its terminal is accepted."""
    run = run_fixture(tmp_path / "readiness.jsonl", interrupt=True)
    try:
        assert run.ledger.attempts_for("repair:L2:build") == 2  # two delivery attempts
        assert len(run.ledger.results["repair:L2:build"]) > 0  # one logical repair operation

        repairs = [
            record
            for record in run.records
            if isinstance(record, ActivityRequested) and str(record.transition) == "decide.repair"
        ]
        completions = [
            record
            for record in run.records
            if isinstance(record, ActivityCompleted) and str(record.transition) == "decide.repair"
        ]
        assert len(completions) == 1  # one completion record
        assert {record.correlation for record in repairs} == {"repair:L2:build"}
        assert {record.idempotency for record in repairs} == {"repair:L2:build"}
    finally:
        run.engine.close()


def test_restarted_and_uninterrupted_runs_have_identical_canonical_history(tmp_path):
    plain = run_fixture(tmp_path / "plain.jsonl", interrupt=False)
    restarted = run_fixture(tmp_path / "restarted.jsonl", interrupt=True)
    try:
        assert (tmp_path / "plain.jsonl").read_bytes() == (tmp_path / "restarted.jsonl").read_bytes()
        assert plain.engine.marking == restarted.engine.marking
        assert dict(plain.engine.active_scopes) == dict(restarted.engine.active_scopes)
        assert plain.branches == restarted.branches
    finally:
        plain.engine.close()
        restarted.engine.close()


def test_engine_load_rebuilds_marking_and_structure_without_executing_any_pure_inscription(tmp_path):
    """Replay is reapplication of recorded movements; no authored function runs."""
    compiled = compile_flow(readiness_flow())
    ledger = FakeProviderLedger()
    history = tmp_path / "readiness.jsonl"
    engine = create(compiled, history, ledger)
    scope = engine.open_scope("branch")
    deliver_head(engine, compiled, HeadObserved("h2", "new", 1, "L2"), identity="head", scope=scope)
    deliver_ci(engine, compiled, CIObserved("h2", EvidenceId(20, 1), "failure", "build"), identity="ci", scope=scope)
    drain(engine)
    before_marking, before_scopes = engine.marking, dict(engine.active_scopes)
    engine.close()

    EVALUATIONS.clear()
    reloaded = compile_flow(readiness_flow())
    resumed = load(reloaded, history, ledger)
    try:
        assert EVALUATIONS == {}  # reconstruction alone evaluates nothing
        drain(resumed)
        assert EVALUATIONS == {}  # and the net is at rest, so not even a guard runs
        assert resumed.marking == before_marking
        assert dict(resumed.active_scopes) == before_scopes
        assert value_at(resumed, "readiness.head", HeadFact) == HeadFact("h2", 1, "L2")
        assert resumed.marking.place(NetPath("ladder.rerun")) == ()
        assert ledger.attempts == {"rerun:L2:build": 1}
    finally:
        resumed.close()


def test_every_observed_record_explains_back_to_an_authored_construct(tmp_path):
    run = run_fixture(tmp_path / "readiness.jsonl", interrupt=False)
    try:
        compiled = run.compiled
        assert unattributed_records(run.records, compiled.source_map) == ()

        document = explain_history(run.records, compiled.source_map)
        assert all(entry["source"] is not None or entry["role"] == "neutral" for entry in document["entries"])
    finally:
        run.engine.close()


def test_every_decision_names_the_branch_that_answered_and_its_authored_line(tmp_path):
    """The durable "why nothing happened" spelling, at v1's grain."""
    run = run_fixture(tmp_path / "readiness.jsonl", interrupt=False)
    try:
        rows = decisions(run.records, run.compiled.source_map)
        assert [row["branch"] for row in rows] == list(run.branches)

        absorbed = next(row for row in rows if row["branch"] == "stale")
        assert absorbed["role"] == "guarded branch [stale] — durable absorption"
        assert absorbed["source"]["file"] == "inet_scenario.py"  # type: ignore[index]
        assert absorbed["source"]["symbol"] == "stale"  # type: ignore[index]

        # Every decision firing is one occurrence, and the effect records ride it.
        occurrences = {row["occurrence"] for row in rows}
        assert len(occurrences) == len(rows)
        firings = [
            record
            for record in run.records
            if isinstance(record, FiringCompleted) and str(record.transition).startswith("decide.")
        ]
        assert {record.occurrence for record in firings} == occurrences
    finally:
        run.engine.close()


def test_the_explained_history_matches_its_golden_and_is_not_execution_authority(tmp_path):
    run = run_fixture(tmp_path / "readiness.jsonl", interrupt=False)
    try:
        payload = serialize_explained(explain_history(run.records, run.compiled.source_map))
    finally:
        run.engine.close()

    assert payload == (GOLDEN / "inscription.explained-history-v1.json").read_bytes()
    document = json.loads(payload)
    assert document["definition_sha256"] == run.compiled.source_map.definition_sha256
    assert document["format"] == "petrus-experiment-explained-history"


@pytest.mark.parametrize("name", GOLDEN_FILES + ARTIFACT_FILES)
def test_the_retained_evidence_bundle_regenerates_byte_identically(tmp_path, name):
    """A stale golden or artifact fails loud instead of quietly describing an older net."""
    build_evidence(tmp_path)
    retained = (GOLDEN if name in GOLDEN_FILES else ARTIFACTS) / name

    assert (tmp_path / name).read_bytes() == retained.read_bytes()
