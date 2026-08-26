"""Restart through public doors, replay equivalence, and History attribution."""

from petrus.impetus.history import ActivityCompleted, ActivityRequested
from petrus.impetus.petrinet import NetPath
from petrus.impetus.scope import LifecycleScope

from algebra import Decision, await_event, drop, effect, lifecycle, low_level, machine, on, terminal
from domain import (
    CIObserved,
    Evidence,
    HeadObserved,
    HumanNeeded,
    Ignored,
    PublishAcknowledged,
    Published,
    PublishRequested,
    ReadinessState,
    RepairRequested,
    RerunRequested,
)
from explain import explain_history, serialize_explained, unattributed_records
from harness import FakeProviderLedger, create, deliver_ci, deliver_head, load, drain, value_at
from lowering import compile_flow
from run_experiment import ARTIFACTS, GOLDEN, build_evidence, run_fixture
from scenario import accept_publish, admit_head, publication_gate, readiness_flow, repair, rerun, route_ci

REPAIR = NetPath("effects.repair.fire")


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
        # The redispatch reused the recorded correlation/idempotency, which is
        # why the fake provider saw one logical operation.
        assert requests[0].correlation == requests[0].idempotency == "repair:L2:build"
        # No completed handler re-executed across the restart: every other
        # operation still shows exactly one provider attempt.
        assert {op: count for op, count in run.ledger.attempts.items() if op != "repair:L2:build"} == {
            "publish:h1:g1": 1,
            "rerun:L2:build": 1,
            "publish:h2r:g3": 1,
        }
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


def test_engine_load_rebuilds_marking_scope_and_ladder_without_reexecuting_completed_handlers(tmp_path):
    run = run_fixture(tmp_path / "history.jsonl", interrupt=False)
    run.engine.close()
    attempts_before = dict(run.ledger.attempts)

    # Reconstruct every live runtime object through public doors only.
    compiled = compile_flow(readiness_flow())
    engine = load(compiled, run.history_path, run.ledger)
    try:
        drain(engine)

        assert dict(engine.active_scopes) == {"branch": LifecycleScope("branch", 4)}
        assert engine.marking == run.pre_reload_marking
        state = value_at(engine, "readiness.state", ReadinessState)
        assert state.head == "h3" and state.generation == 4 and state.lineage == "L4"
        assert state.ladder.fingerprint is None and state.ladder.watermark is None
        # State and command token data stayed JSON-faithful through JSONL
        # reconstruction: the typed value above decoded from persisted bytes.
        assert run.ledger.attempts == attempts_before
        assert engine.records == run.records
    finally:
        engine.close()

    # Direct instrumentation: replay reapplies recorded movements and never
    # re-runs a completed pure handler — the counted domain functions of a
    # freshly compiled identical flow stay untouched across load + drain.
    calls = {"admit_head": 0, "route_ci": 0, "accept_publish": 0}

    def instrumented_flow():
        def counted_admit_head(event: HeadObserved) -> ReadinessState:
            calls["admit_head"] += 1
            return admit_head(event)

        def counted_route_ci(
            state: ReadinessState, event: CIObserved
        ) -> Decision[
            ReadinessState,
            PublishRequested | RerunRequested | RepairRequested | HumanNeeded | Ignored,
        ]:
            calls["route_ci"] += 1
            return route_ci(state, event)

        def counted_accept_publish(
            state: ReadinessState, event: PublishAcknowledged
        ) -> tuple[ReadinessState, Published]:
            calls["accept_publish"] += 1
            return accept_publish(state, event)

        return machine(
            "readiness",
            lifecycle=lifecycle("branch"),
            handlers=(
                on(await_event("head", HeadObserved)).project("admit_head", counted_admit_head),
                on(await_event("ci", CIObserved))
                .decide("route_ci", counted_route_ci)
                .choose(
                    {
                        PublishRequested: low_level("publish_once", publication_gate, returns=PublishAcknowledged),
                        RerunRequested: effect("rerun", rerun),
                        RepairRequested: effect("repair", repair),
                        HumanNeeded: terminal("human_needed"),
                        Ignored: drop(),
                    }
                ),
                on(PublishAcknowledged).fold("accept_publish", counted_accept_publish).to(terminal("published")),
            ),
        )

    instrumented = compile_flow(instrumented_flow())
    ledger = FakeProviderLedger()
    live = create(instrumented, tmp_path / "instrumented.jsonl", ledger)
    scope = live.open_scope("branch")
    deliver_head(live, instrumented, HeadObserved("h1", "new", 1, "L1"), identity="head-h1-g1", scope=scope)
    deliver_ci(live, instrumented, CIObserved("h1", Evidence(10, 1), "success"), identity="ci-10-1-g1", scope=scope)
    drain(live)
    live.close()
    assert calls == {"admit_head": 1, "route_ci": 1, "accept_publish": 1}

    calls.update(admit_head=0, route_ci=0, accept_publish=0)
    resumed = load(compile_flow(instrumented_flow()), tmp_path / "instrumented.jsonl", ledger)
    try:
        drain(resumed)
        assert calls == {"admit_head": 0, "route_ci": 0, "accept_publish": 0}
        assert ledger.attempts == {"publish:h1:g1": 1}
    finally:
        resumed.close()


def test_every_observed_firing_explains_back_to_authored_source(tmp_path):
    run = run_fixture(tmp_path / "history.jsonl", interrupt=False)
    try:
        assert unattributed_records(run.records, run.compiled.source_map) == ()
        explained = explain_history(run.records, run.compiled.source_map)
        for group in explained["occurrences"]:
            assert group["transition"] is not None
            assert group["source"] is not None
            assert group["source"]["file"] == "scenario.py"
    finally:
        run.engine.close()


def test_explained_history_matches_golden_and_is_not_execution_authority(tmp_path):
    run = run_fixture(tmp_path / "history.jsonl", interrupt=False)
    run.engine.close()

    # Regenerate purely from canonical records plus the source map — the
    # projection is detached and never consulted to execute or resume.
    reloaded = load(compile_flow(readiness_flow()), run.history_path, FakeProviderLedger())
    try:
        explained = serialize_explained(explain_history(reloaded.records, run.compiled.source_map))
    finally:
        reloaded.close()

    assert explained == serialize_explained(explain_history(run.records, run.compiled.source_map))
    assert explained == (GOLDEN / "readiness.explained-history-v1.json").read_bytes()


def test_retained_goldens_and_artifacts_match_regenerated_evidence(tmp_path):
    """The whole retained evidence bundle regenerates byte-identically.

    A change to the flow, the compiler, or the fixture that is not
    deliberately reflected in ``golden/`` and ``artifacts/`` fails here
    instead of leaving stale retained evidence behind.
    """
    build_evidence(tmp_path)

    for name in ("readiness.net-v3.json", "readiness.source-map-v1.json", "readiness.explained-history-v1.json"):
        assert (tmp_path / name).read_bytes() == (GOLDEN / name).read_bytes(), name
    for name in ("readiness.net.dot", "experiment-report.json", "readiness.history.jsonl"):
        assert (tmp_path / name).read_bytes() == (ARTIFACTS / name).read_bytes(), name
