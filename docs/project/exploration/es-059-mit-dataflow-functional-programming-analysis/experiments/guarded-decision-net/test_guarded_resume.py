"""Restart through public doors, replay equivalence, attribution, and grain.

The grain claim is the one this variant must not lose: five transitions where
v1 had one must still mean **one firing and one History row set per decision**.
It is pinned twice — against this experiment's own fixture, and record-for-record
against v1's fixture over the identical trace.
"""

import run_experiment as v1_run
from petrus.impetus.history import ActivityCompleted, ActivityRequested
from petrus.impetus.petrinet import NetPath
from petrus.impetus.scope import LifecycleScope

from algebra import await_event, effect, lifecycle, low_level, terminal
from domain import (
    CIObserved,
    Evidence,
    HeadObserved,
    HumanNeeded,
    PublishAcknowledged,
    PublishRequested,
    ReadinessState,
    RepairRequested,
    RerunRequested,
)
from explain import explain_history, serialize_explained, unattributed_records
from guarded_algebra import guarded_machine, on, rung
from guarded_harness import fired_rungs, fired_transitions
from guarded_lowering import compile_guarded_flow
from guarded_run import ARTIFACTS, BRANCH, GOLDEN, build_evidence, compile_fixture_flow, run_fixture
from guarded_scenario import (
    absorb,
    exhaust,
    first_clean,
    fresh_failure,
    guarded_readiness_flow,
    ladder_exhausted,
    not_actionable,
    note_publication,
    repeated_failure,
    request_publication,
    request_repair,
    request_rerun,
    spend_repair,
    spend_rerun,
    surface_human_needed,
)
from harness import FakeProviderLedger, create, deliver_ci, deliver_head, drain, load, value_at
from scenario import accept_publish, admit_head, publication_gate, repair, rerun

REPAIR = NetPath("effects.repair.fire")
IGNORE = "readiness.route_ci.ignore.fire"


def test_activity_requested_restart_redispatches_one_logical_operation(tmp_path):
    run = run_fixture(tmp_path / "history.jsonl", interrupt=True)
    try:
        # Two operational delivery attempts, one logical repair effect.
        assert run.ledger.attempts["repair:L2:build"] == 2
        assert len([op for op in run.ledger.attempts if op.startswith("repair:")]) == 1
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
        # The rung that fired before the interruption is still the rung named
        # in History after reconstruction: guards are re-derived, not replayed.
        assert fired_rungs(run.records, BRANCH) == ("publish", "rerun", "ignore", "repair", "publish")
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
        # Only the fake provider's operational attempt count may differ.
        assert control.ledger.results == restarted.ledger.results
        assert control.ledger.attempts["repair:L2:build"] == 1
        assert restarted.ledger.attempts["repair:L2:build"] == 2
    finally:
        control.engine.close()
        restarted.engine.close()


def test_history_grain_equals_v1_record_for_record_over_the_same_trace(tmp_path):
    """Thirteen transitions, but the same durable grain as v1's nine.

    Same trace, same records in the same order, same domain outcomes — the
    only difference is *which* transition path each route firing names. That
    is the whole trade this experiment measures: topology grew, History did
    not.
    """
    guarded = run_fixture(tmp_path / "guarded.jsonl", interrupt=False)
    baseline = v1_run.run_fixture(tmp_path / "v1.jsonl", interrupt=False)
    try:
        assert len(guarded.records) == len(baseline.records) == 147
        assert [type(record).__name__ for record in guarded.records] == [
            type(record).__name__ for record in baseline.records
        ]
        assert guarded.ledger.attempts == baseline.ledger.attempts

        guarded_paths = fired_transitions(guarded.records)
        baseline_paths = fired_transitions(baseline.records)
        assert len(guarded_paths) == len(baseline_paths)
        # v1 spends five identical, anonymous route firings where v2 names the rung.
        assert [path for path in baseline_paths if path.startswith(BRANCH)] == ["readiness.route_ci.fire"] * 5
        assert [path for path in guarded_paths if path.startswith(BRANCH)] == [
            "readiness.route_ci.publish.fire",
            "readiness.route_ci.rerun.fire",
            IGNORE,
            "readiness.route_ci.repair.fire",
            "readiness.route_ci.publish.fire",
        ]
        # Every other transition firing is identical between the experiments.
        assert [path for path in guarded_paths if not path.startswith(BRANCH)] == [
            path for path in baseline_paths if not path.startswith(BRANCH)
        ]
    finally:
        guarded.engine.close()
        baseline.engine.close()


def _instrumented_flow(calls: dict[str, int]):
    """The authored flow with every pure rung function counted."""

    def counted(name, function):
        def wrapper(state, event):
            calls[name] = calls.get(name, 0) + 1
            return function(state, event)

        wrapper.__name__ = function.__name__
        wrapper.__annotations__ = dict(function.__annotations__)
        return wrapper

    def make(rung_id, when, fold, emit):
        draft = rung(rung_id, when=counted(f"when:{rung_id}", when), fold=counted(f"fold:{rung_id}", fold))
        return draft.drop() if emit is None else draft.emit(counted(f"emit:{rung_id}", emit))

    return guarded_machine(
        "readiness",
        lifecycle=lifecycle("branch"),
        handlers=(
            on(await_event("head", HeadObserved)).project("admit_head", admit_head),
            on(await_event("ci", CIObserved))
            .branch(
                "route_ci",
                rungs=(
                    make("ignore", not_actionable, absorb, None),
                    make("publish", first_clean, note_publication, request_publication),
                    make("rerun", fresh_failure, spend_rerun, request_rerun),
                    make("repair", repeated_failure, spend_repair, request_repair),
                    make("human", ladder_exhausted, exhaust, surface_human_needed),
                ),
            )
            .route(
                {
                    PublishRequested: low_level("publish_once", publication_gate, returns=PublishAcknowledged),
                    RerunRequested: effect("rerun", rerun),
                    RepairRequested: effect("repair", repair),
                    HumanNeeded: terminal("human_needed"),
                }
            ),
            on(PublishAcknowledged).fold("accept_publish", accept_publish).to(terminal("published")),
        ),
    )


def test_engine_load_rebuilds_marking_scope_and_ladder_without_reexecuting_rung_functions(tmp_path):
    run = run_fixture(tmp_path / "history.jsonl", interrupt=False)
    run.engine.close()
    attempts_before = dict(run.ledger.attempts)

    # Reconstruct every live runtime object through public doors only.
    engine = load(compile_fixture_flow(), run.history_path, run.ledger)
    try:
        drain(engine)
        assert dict(engine.active_scopes) == {"branch": LifecycleScope("branch", 4)}
        assert engine.marking == run.pre_reload_marking
        state = value_at(engine, "readiness.state", ReadinessState)
        assert state.head == "h3" and state.generation == 4 and state.lineage == "L4"
        assert state.ladder.fingerprint is None and state.ladder.watermark is None
        assert run.ledger.attempts == attempts_before
        assert engine.records == run.records
    finally:
        engine.close()

    # Direct instrumentation: replay reapplies recorded movements and never
    # re-runs a completed rung predicate, fold, or emission.
    calls: dict[str, int] = {}
    instrumented = compile_guarded_flow(_instrumented_flow(calls))
    ledger = FakeProviderLedger()
    live = create(instrumented, tmp_path / "instrumented.jsonl", ledger)
    scope = live.open_scope("branch")
    deliver_head(live, instrumented, HeadObserved("h1", "new", 1, "L1"), identity="head-h1-g1", scope=scope)
    deliver_ci(live, instrumented, CIObserved("h1", Evidence(10, 1), "success"), identity="ci-10-1-g1", scope=scope)
    drain(live)
    live.close()
    assert calls["fold:publish"] == calls["emit:publish"] == 1
    assert set(calls) >= {f"when:{name}" for name in ("ignore", "publish", "rerun", "repair", "human")}

    calls.clear()
    resumed = load(compile_guarded_flow(_instrumented_flow(calls)), tmp_path / "instrumented.jsonl", ledger)
    try:
        drain(resumed)
        assert calls == {}
        assert ledger.attempts == {"publish:h1:g1": 1}
    finally:
        resumed.close()


def test_guard_evaluation_repeats_per_enabledness_survey_and_never_enters_history(tmp_path):
    """The honest cost of moving the decision into guards.

    A guard is not evaluated once per decision: it is evaluated once per rung
    per enabledness survey while its arcs are satisfied. Petrus records none
    of that, so a refused rung leaves no canonical trace — only the rung that
    fired does.
    """
    calls: dict[str, int] = {}
    compiled = compile_guarded_flow(_instrumented_flow(calls))
    engine = create(compiled, tmp_path / "counted.jsonl", FakeProviderLedger())
    try:
        scope = engine.open_scope("branch")
        deliver_head(engine, compiled, HeadObserved("h1", "new", 1, "L1"), identity="head", scope=scope)
        deliver_ci(
            engine,
            compiled,
            CIObserved("h1", Evidence(20, 1), "failure", fingerprint="build"),
            identity="ci",
            scope=scope,
        )
        drain(engine)

        predicates = {name: count for name, count in calls.items() if name.startswith("when:")}
        # One decision, one rung firing — but five predicates evaluated, repeatedly.
        begun = fired_transitions(engine.records)
        assert begun == ("ingress.head", "ingress.ci", "readiness.route_ci.rerun.fire", "effects.rerun.fire")
        assert calls["fold:rerun"] == 1
        # Deterministic and pinned exactly: each of the five predicates runs
        # twice for this one decision — ten evaluations, a 10x amplification.
        assert predicates == {
            "when:ignore": 2,
            "when:publish": 2,
            "when:rerun": 2,
            "when:repair": 2,
            "when:human": 2,
        }

        # No canonical record names a guard, a guard URI, or a refused rung.
        text = " ".join(f"{type(record).__name__} {record!r}" for record in engine.records)
        assert "guard" not in text.lower()
        assert IGNORE not in text
    finally:
        engine.close()


def test_every_observed_firing_explains_back_to_authored_source(tmp_path):
    run = run_fixture(tmp_path / "history.jsonl", interrupt=False)
    try:
        assert unattributed_records(run.records, run.compiled.source_map) == ()
        explained = explain_history(run.records, run.compiled.source_map)
        for group in explained["occurrences"]:
            assert group["transition"] is not None
            assert group["source"] is not None
            assert group["source"]["file"] in ("scenario.py", "guarded_scenario.py")
    finally:
        run.engine.close()


def test_an_absorbed_observation_explains_why_nothing_happened(tmp_path):
    """The v1 limit this variant exists to close.

    v1 report §11: "An ``Ignored`` decision is attributable in History only as
    a state-reproducing ``readiness.route_ci.fire`` firing with no command
    token." Here the same absorption names its rung, its role, and the exact
    predicate that answered — durably, from canonical records plus the sidecar.
    """
    run = run_fixture(tmp_path / "history.jsonl", interrupt=False)
    try:
        explained = explain_history(run.records, run.compiled.source_map)
        absorbed = [group for group in explained["occurrences"] if group["transition"] == IGNORE]

        assert len(absorbed) == 1
        [group] = absorbed
        assert group["source"]["symbol"] == "not_actionable"
        assert group["source"]["file"] == "guarded_scenario.py"
        assert [token["color"] for token in group["accepted"]] == ["ReadinessState", "CIObserved"]
        assert [entry["place"] for entry in group["produced"]] == ["readiness.state"]
        assert group["ended"] == "FiringCompleted"

        entry = next(
            item for item in explained["entries"] if item["node"] == IGNORE and item["record"] == "FiringBegun"
        )
        assert "absorbing rung" in entry["role"]
    finally:
        run.engine.close()


def test_explained_history_matches_golden_and_is_not_execution_authority(tmp_path):
    run = run_fixture(tmp_path / "history.jsonl", interrupt=False)
    run.engine.close()

    # Regenerate purely from canonical records plus the source map — the
    # projection is detached and never consulted to execute or resume.
    reloaded = load(compile_fixture_flow(), run.history_path, FakeProviderLedger())
    try:
        explained = serialize_explained(explain_history(reloaded.records, run.compiled.source_map))
    finally:
        reloaded.close()

    assert explained == serialize_explained(explain_history(run.records, run.compiled.source_map))
    assert explained == (GOLDEN / "readiness.explained-history-v1.json").read_bytes()


def test_retained_goldens_and_artifacts_match_regenerated_evidence(tmp_path):
    """The whole retained evidence bundle regenerates byte-identically."""
    build_evidence(tmp_path)

    for name in ("readiness.net-v3.json", "readiness.source-map-v1.json", "readiness.explained-history-v1.json"):
        assert (tmp_path / name).read_bytes() == (GOLDEN / name).read_bytes(), name
    for name in ("readiness.net.dot", "experiment-report.json", "readiness.history.jsonl"):
        assert (tmp_path / name).read_bytes() == (ARTIFACTS / name).read_bytes(), name


def test_the_authored_flow_and_the_fixture_flow_are_the_same_value():
    assert guarded_readiness_flow() == guarded_readiness_flow()
    assert compile_fixture_flow().definition_bytes == compile_guarded_flow(guarded_readiness_flow()).definition_bytes
