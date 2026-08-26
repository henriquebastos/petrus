"""Semantic preservation: the case table decides exactly what v1's ``route_ci`` decided.

Two independent levels of evidence:

1. a pure exhaustive-shape comparison of the authored table against v1's
   ``route_ci`` over every combination of a state/event matrix, which also
   proves every rung is reachable; and
2. Engine-executed runs of v1's scenario claims over the compiled table flow,
   asserting canonical records and marking rather than only the fake ledger.
"""

import itertools

import pytest

from petrus.impetus.history import (
    ActivityRequested,
    ExternalEventDelivered,
    FiringBegun,
    ScopedDeliveryDropped,
    ScopedDeliveryQuarantined,
    TokensConsumed,
    TokensProduced,
)
from petrus.impetus.instance import DeliveryDisposition, PriorAcknowledgement, ScopedDeliveryAcknowledgement
from petrus.impetus.petrinet import Marking, NetPath, Token
from petrus.impetus.scope import LifecycleScope

from domain import (
    CIObserved,
    Evidence,
    HeadObserved,
    HumanNeeded,
    Ladder,
    PublishRequested,
    Published,
    ReadinessState,
    RepairLanded,
    RerunAccepted,
    to_data,
)
from harness import FakeProviderLedger, create, deliver_ci, deliver_head, drain, value_at, values_at
from scenario import admit_head, route_ci
from table_algebra import Match, evaluate_match
from table_lowering import compile_flow
from table_scenario import readiness_flow

COMPILED = compile_flow(readiness_flow())
TABLE = next(step for step in readiness_flow().handlers[1].steps if isinstance(step, Match))


def _engine(tmp_path, ledger=None):
    return create(COMPILED, tmp_path / "history.jsonl", ledger or FakeProviderLedger())


def _firings_of(engine, transition: str) -> list[FiringBegun]:
    path = NetPath(transition)
    return [record for record in engine.records if isinstance(record, FiringBegun) and record.transition == path]


def _state_matrix() -> list[ReadinessState]:
    states = []
    for head, generation, lineage in (("h1", 1, "L1"), ("h2", 2, "L2")):
        for fingerprint in (None, "build", "lint"):
            for rerun_used, repair_used in itertools.product((False, True), repeat=2):
                for watermark in (None, Evidence(10, 1), Evidence(20, 2)):
                    for publication in (None, "publish:h1:g1"):
                        states.append(
                            ReadinessState(
                                head,
                                generation,
                                lineage,
                                Ladder(lineage, fingerprint, rerun_used, repair_used, watermark),
                                publication,
                            )
                        )
    return states


def _event_matrix() -> list[CIObserved]:
    return [
        CIObserved(head, Evidence(run, attempt), conclusion, fingerprint)
        for head in ("h1", "h2", "h9")
        for run, attempt in ((10, 1), (20, 1), (20, 2), (30, 1))
        for conclusion in ("success", "failure")
        for fingerprint in (None, "build", "lint")
    ]


def test_the_case_table_decides_exactly_what_the_v1_decide_function_decided():
    """Every rung is reachable and no observation is decided differently."""
    fired_counts: dict[str, int] = {}
    pairs = 0

    for state in _state_matrix():
        for event in _event_matrix():
            pairs += 1
            expected = route_ci(state, event)
            fired, next_state, outcome = evaluate_match(TABLE, state, event)
            fired_counts[fired] = fired_counts.get(fired, 0) + 1
            # v1 spells absorption as the ``Ignored`` domain color routed to
            # ``drop()``; v2 spells it as a rung that emits nothing at all.
            expected_outcome = None if type(expected.outcome).__name__ == "Ignored" else expected.outcome
            assert next_state == expected.state, (state, event)
            assert outcome == expected_outcome, (state, event)

    assert pairs == 10368
    assert set(fired_counts) == {entry.id for entry in TABLE.cases}
    assert all(count > 0 for count in fired_counts.values())


def test_clean_ci_publishes_once_after_typed_acknowledgement(tmp_path):
    ledger = FakeProviderLedger()
    engine = _engine(tmp_path, ledger)
    scope = engine.open_scope("branch")
    deliver_head(engine, COMPILED, HeadObserved("h1", "new", 1, "L1"), identity="head-h1-g1", scope=scope)
    deliver_ci(engine, COMPILED, CIObserved("h1", Evidence(10, 1), "success"), identity="ci-10-1-g1", scope=scope)

    drain(engine)

    assert ledger.attempts == {"publish:h1:g1": 1}
    assert value_at(engine, "terminal.published", Published) == Published("h1", 1, "publish:h1:g1")

    records = list(engine.records)
    [request] = [record for record in records if isinstance(record, ActivityRequested)]
    assert request.transition == NetPath("effects.publish.execute")
    assert request.correlation == request.idempotency == "publish:h1:g1"

    accept_begun = _firings_of(engine, "effects.publish.accept")
    assert len(accept_begun) == 1
    completed_index = next(
        index for index, record in enumerate(records) if type(record).__name__ == "ActivityCompleted"
    )
    assert completed_index < records.index(accept_begun[0])
    assert len(engine.marking.place(NetPath("effects.publish.done"))) == 1
    assert value_at(engine, "readiness.state", ReadinessState).publication_operation == "publish:h1:g1"


def test_first_failure_reruns_once_and_duplicate_evidence_spends_nothing(tmp_path):
    ledger = FakeProviderLedger()
    engine = _engine(tmp_path, ledger)
    scope = engine.open_scope("branch")
    deliver_head(engine, COMPILED, HeadObserved("h1", "new", 1, "L1"), identity="head-h1-g1", scope=scope)
    failure = CIObserved("h1", Evidence(20, 1), "failure", fingerprint="build")
    deliver_ci(engine, COMPILED, failure, identity="ci-20-1-g1", scope=scope)
    drain(engine)

    assert ledger.attempts == {"rerun:L1:build": 1}
    [request] = [record for record in engine.records if isinstance(record, ActivityRequested)]
    assert request.transition == NetPath("effects.rerun.fire")
    assert values_at(engine, "facts.rerun_accepted", RerunAccepted) == (RerunAccepted("rerun:L1:build", "h1"),)
    state_after_rerun = value_at(engine, "readiness.state", ReadinessState)
    assert state_after_rerun.ladder.rerun_used is True

    before = len(engine.records)
    acknowledged = deliver_ci(engine, COMPILED, failure, identity="ci-20-1-g1", scope=scope)
    assert isinstance(acknowledged, PriorAcknowledgement)
    assert len(engine.records) == before

    # The ``stale`` rung absorbs the same evidence under a new ingress identity.
    deliver_ci(engine, COMPILED, failure, identity="ci-20-1-g1-echo", scope=scope)
    drain(engine)
    assert ledger.attempts == {"rerun:L1:build": 1}
    assert len([record for record in engine.records if isinstance(record, ActivityRequested)]) == 1
    assert value_at(engine, "readiness.state", ReadinessState) == state_after_rerun


def test_newer_persistent_failure_repairs_without_a_second_rerun(tmp_path):
    ledger = FakeProviderLedger()
    engine = _engine(tmp_path, ledger)
    scope = engine.open_scope("branch")
    deliver_head(engine, COMPILED, HeadObserved("h1", "new", 1, "L1"), identity="head-h1-g1", scope=scope)
    for attempt in (1, 2):
        deliver_ci(
            engine,
            COMPILED,
            CIObserved("h1", Evidence(20, attempt), "failure", fingerprint="build"),
            identity=f"ci-20-{attempt}-g1",
            scope=scope,
        )
        drain(engine)

    assert ledger.attempts == {"rerun:L1:build": 1, "repair:L1:build": 1}
    requests = [record for record in engine.records if isinstance(record, ActivityRequested)]
    assert [str(record.transition) for record in requests] == ["effects.rerun.fire", "effects.repair.fire"]
    assert values_at(engine, "facts.repair_landed", RepairLanded) == (RepairLanded("repair:L1:build", "h1", "h1r"),)


def test_failure_after_repair_surfaces_human_needed(tmp_path):
    ledger = FakeProviderLedger()
    engine = _engine(tmp_path, ledger)
    scope = engine.open_scope("branch")
    deliver_head(engine, COMPILED, HeadObserved("h1", "new", 1, "L1"), identity="head-h1-g1", scope=scope)
    for attempt in (1, 2, 3):
        deliver_ci(
            engine,
            COMPILED,
            CIObserved("h1", Evidence(20, attempt), "failure", fingerprint="build"),
            identity=f"ci-20-{attempt}-g1",
            scope=scope,
        )
        drain(engine)

    assert value_at(engine, "terminal.human_needed", HumanNeeded) == HumanNeeded("h1", "L1", "build")
    assert ledger.attempts == {"rerun:L1:build": 1, "repair:L1:build": 1}
    assert len([record for record in engine.records if isinstance(record, ActivityRequested)]) == 2


def test_a_changed_fingerprint_resets_the_rung_budget_through_normalize(tmp_path):
    """``refresh_ladder`` is load-bearing: a new (lineage, fingerprint) rearms rerun."""
    ledger = FakeProviderLedger()
    engine = _engine(tmp_path, ledger)
    scope = engine.open_scope("branch")
    deliver_head(engine, COMPILED, HeadObserved("h1", "new", 1, "L1"), identity="head-h1-g1", scope=scope)
    deliver_ci(
        engine,
        COMPILED,
        CIObserved("h1", Evidence(20, 1), "failure", fingerprint="build"),
        identity="ci-build",
        scope=scope,
    )
    drain(engine)
    deliver_ci(
        engine,
        COMPILED,
        CIObserved("h1", Evidence(21, 1), "failure", fingerprint="lint"),
        identity="ci-lint",
        scope=scope,
    )
    drain(engine)

    assert ledger.attempts == {"rerun:L1:build": 1, "rerun:L1:lint": 1}
    state = value_at(engine, "readiness.state", ReadinessState)
    assert state.ladder.fingerprint == "lint" and state.ladder.repair_used is False


def test_confirmed_repair_head_keeps_lineage_and_unrelated_head_resets_it(tmp_path):
    ledger = FakeProviderLedger()
    engine = _engine(tmp_path, ledger)
    first = engine.open_scope("branch")
    deliver_head(engine, COMPILED, HeadObserved("h2", "new", 1, "L2"), identity="head-h2-g1", scope=first)
    for attempt in (1, 2):
        deliver_ci(
            engine,
            COMPILED,
            CIObserved("h2", Evidence(20, attempt), "failure", fingerprint="build"),
            identity=f"ci-20-{attempt}-g1",
            scope=first,
        )
        drain(engine)
    assert values_at(engine, "facts.repair_landed", RepairLanded) == (RepairLanded("repair:L2:build", "h2", "h2r"),)

    second = engine.reset_scope(first)
    assert second == LifecycleScope("branch", 2)
    assert engine.marking == Marking()
    deliver_head(engine, COMPILED, HeadObserved("h2r", "confirmed", 2, "L2"), identity="head-h2r-g2", scope=second)
    state = value_at(engine, "readiness.state", ReadinessState)
    assert state.lineage == "L2"
    assert state.ladder.fingerprint is None and state.ladder.rerun_used is False
    deliver_ci(engine, COMPILED, CIObserved("h2r", Evidence(21, 1), "success"), identity="ci-21-1-g2", scope=second)
    drain(engine)
    assert value_at(engine, "terminal.published", Published) == Published("h2r", 2, "publish:h2r:g2")

    third = engine.reset_scope(second)
    deliver_head(engine, COMPILED, HeadObserved("h3", "superseded", 3, "L4"), identity="head-h3-g3", scope=third)
    state = value_at(engine, "readiness.state", ReadinessState)
    assert state.lineage == "L4"
    assert state.ladder == admit_head(HeadObserved("h3", "superseded", 3, "L4")).ladder
    assert engine.active_scopes == {"branch": third}


def _peak_occupancy(engine, place: str) -> int:
    path = NetPath(place)
    occupancy = peak = 0
    for record in engine.records:
        if isinstance(record, TokensProduced) and record.place == path:
            occupancy += len(record.tokens)
            peak = max(peak, occupancy)
        elif isinstance(record, TokensConsumed) and record.place == path:
            occupancy -= len(record.tokens)
    return peak


def test_publication_inhibitor_allows_only_one_pending_operation(tmp_path):
    two_requests = Marking(
        {
            NetPath("commands.publish"): (
                Token("PublishRequested", to_data(PublishRequested("publish:h1:g1", "h1", 1))),
                Token("PublishRequested", to_data(PublishRequested("publish:h9:g1", "h9", 1))),
            )
        }
    )

    ledger = FakeProviderLedger()
    engine = create(COMPILED, tmp_path / "gated.jsonl", ledger, marking=two_requests)
    drain(engine)

    assert len(_firings_of(engine, "effects.publish.authorize")) == 1
    assert ledger.attempts == {"publish:h1:g1": 1}
    assert _peak_occupancy(engine, "effects.publish.pending") == 1
    assert len(engine.marking.place(NetPath("commands.publish"))) == 1
    assert len(engine.marking.place(NetPath("effects.publish.done"))) == 1


def test_closed_generation_drops_and_future_generation_quarantines_ingress(tmp_path):
    engine = _engine(tmp_path)
    first = engine.open_scope("branch")
    deliver_head(engine, COMPILED, HeadObserved("h1", "new", 1, "L1"), identity="head-h1-g1", scope=first)
    second = engine.reset_scope(first)
    stale = CIObserved("h1", Evidence(30, 1), "success")

    dropped = deliver_ci(engine, COMPILED, stale, identity="ci-stale-g1", scope=first)
    assert dropped == ScopedDeliveryAcknowledgement("ci-stale-g1", DeliveryDisposition.DROPPED, first)

    future = LifecycleScope("branch", second.generation + 3)
    quarantined = deliver_ci(engine, COMPILED, stale, identity="ci-future-g5", scope=future)
    assert quarantined == ScopedDeliveryAcknowledgement("ci-future-g5", DeliveryDisposition.QUARANTINED, future)

    assert len([record for record in engine.records if isinstance(record, ScopedDeliveryDropped)]) == 1
    assert len([record for record in engine.records if isinstance(record, ScopedDeliveryQuarantined)]) == 1
    delivered = {record.identity for record in engine.records if isinstance(record, ExternalEventDelivered)}
    assert delivered == {"head-h1-g1"}
    with pytest.raises(ValueError, match="delivery identity conflict"):
        deliver_ci(
            engine, COMPILED, CIObserved("h1", Evidence(31, 1), "success"), identity="ci-future-g5", scope=future
        )
