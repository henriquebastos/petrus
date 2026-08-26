"""Engine-executed semantics over the guarded decision net.

Every claim v1's ``test_scenario.py`` makes is re-made here, plus the one only
this variant can make: the fired transition path names the ladder rung, so
canonical History says *which* rule answered the observation — including the
rung that deliberately did nothing.
"""

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
    Published,
    PublishRequested,
    ReadinessState,
    RepairLanded,
    RerunAccepted,
    to_data,
)
from guarded_harness import fired_rungs
from guarded_lowering import compile_guarded_flow
from guarded_run import BRANCH
from guarded_scenario import guarded_readiness_flow
from harness import FakeProviderLedger, create, deliver_ci, deliver_head, drain, value_at, values_at
from scenario import admit_head

COMPILED = compile_guarded_flow(guarded_readiness_flow())


def _engine(tmp_path, ledger=None):
    return create(COMPILED, tmp_path / "history.jsonl", ledger or FakeProviderLedger())


def _firings_of(engine, transition: str) -> list[FiringBegun]:
    path = NetPath(transition)
    return [record for record in engine.records if isinstance(record, FiringBegun) and record.transition == path]


def test_clean_ci_publishes_once_after_typed_acknowledgement(tmp_path):
    ledger = FakeProviderLedger()
    engine = _engine(tmp_path, ledger)
    scope = engine.open_scope("branch")
    deliver_head(engine, COMPILED, HeadObserved("h1", "new", 1, "L1"), identity="head-h1-g1", scope=scope)
    deliver_ci(engine, COMPILED, CIObserved("h1", Evidence(10, 1), "success"), identity="ci-10-1-g1", scope=scope)

    drain(engine)

    assert ledger.attempts == {"publish:h1:g1": 1}
    assert value_at(engine, "terminal.published", Published) == Published("h1", 1, "publish:h1:g1")
    assert fired_rungs(engine.records, BRANCH) == ("publish",)

    records = list(engine.records)
    [request] = [record for record in records if isinstance(record, ActivityRequested)]
    assert request.transition == NetPath("effects.publish.execute")
    assert request.correlation == request.idempotency == "publish:h1:g1"

    # Publication is accepted only after the typed Activity terminal crosses
    # the separate durable acceptance transition.
    accept_begun = _firings_of(engine, "effects.publish.accept")
    assert len(accept_begun) == 1
    completed_index = next(
        index for index, record in enumerate(records) if type(record).__name__ == "ActivityCompleted"
    )
    assert completed_index < records.index(accept_begun[0])
    assert len(engine.marking.place(NetPath("effects.publish.done"))) == 1
    assert value_at(engine, "readiness.state", ReadinessState).publication_operation == "publish:h1:g1"


def test_first_failure_reruns_once_and_the_absorbed_duplicate_names_its_rung(tmp_path):
    """v1's documented Ignored-invisibility limit, closed.

    v1 answered a duplicate observation with a ``readiness.route_ci.fire``
    firing that produced only state — the *reason* nothing happened was not in
    canonical History at all. Here the fired transition is
    ``readiness.route_ci.ignore.fire``, so "why nothing happened" is durable.
    """
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

    # Petrus-level idempotent redelivery: prior acknowledgement, no new firing.
    before = len(engine.records)
    acknowledged = deliver_ci(engine, COMPILED, failure, identity="ci-20-1-g1", scope=scope)
    assert isinstance(acknowledged, PriorAcknowledgement)
    assert len(engine.records) == before

    # Domain-level absorption: same evidence under a new ingress identity.
    deliver_ci(engine, COMPILED, failure, identity="ci-20-1-g1-echo", scope=scope)
    drain(engine)
    assert ledger.attempts == {"rerun:L1:build": 1}
    assert len([record for record in engine.records if isinstance(record, ActivityRequested)]) == 1
    assert value_at(engine, "readiness.state", ReadinessState) == state_after_rerun

    assert fired_rungs(engine.records, BRANCH) == ("rerun", "ignore")
    absorbed = _firings_of(engine, "readiness.route_ci.ignore.fire")
    assert len(absorbed) == 1
    produced = [
        record
        for record in engine.records
        if isinstance(record, TokensProduced) and record.occurrence == absorbed[0].occurrence
    ]
    assert [str(record.place) for record in produced] == ["readiness.state"]


def test_newer_persistent_failure_repairs_without_a_second_rerun(tmp_path):
    ledger = FakeProviderLedger()
    engine = _engine(tmp_path, ledger)
    scope = engine.open_scope("branch")
    deliver_head(engine, COMPILED, HeadObserved("h1", "new", 1, "L1"), identity="head-h1-g1", scope=scope)
    deliver_ci(
        engine,
        COMPILED,
        CIObserved("h1", Evidence(20, 1), "failure", fingerprint="build"),
        identity="ci-20-1-g1",
        scope=scope,
    )
    drain(engine)
    deliver_ci(
        engine,
        COMPILED,
        CIObserved("h1", Evidence(20, 2), "failure", fingerprint="build"),
        identity="ci-20-2-g1",
        scope=scope,
    )
    drain(engine)

    assert ledger.attempts == {"rerun:L1:build": 1, "repair:L1:build": 1}
    requests = [record for record in engine.records if isinstance(record, ActivityRequested)]
    assert [str(record.transition) for record in requests] == ["effects.rerun.fire", "effects.repair.fire"]
    assert values_at(engine, "facts.repair_landed", RepairLanded) == (RepairLanded("repair:L1:build", "h1", "h1r"),)
    assert fired_rungs(engine.records, BRANCH) == ("rerun", "repair")


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
    # The whole ladder, rung by rung, readable straight off canonical History.
    assert fired_rungs(engine.records, BRANCH) == ("rerun", "repair", "human")


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

    # Confirmed repair movement: the generation advances, the lineage stays.
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

    # Unrelated branch movement: fresh lineage and a fresh retry lineage.
    third = engine.reset_scope(second)
    assert third == LifecycleScope("branch", 3)
    assert engine.marking == Marking()
    deliver_head(engine, COMPILED, HeadObserved("h3", "superseded", 3, "L4"), identity="head-h3-g3", scope=third)
    state = value_at(engine, "readiness.state", ReadinessState)
    assert state.lineage == "L4"
    assert state.ladder == admit_head(HeadObserved("h3", "superseded", 3, "L4")).ladder
    assert engine.active_scopes == {"branch": third}


def _peak_occupancy(engine, place: str) -> int:
    """Replay movement records in append order to find the place's peak occupancy."""
    path = NetPath(place)
    occupancy = peak = 0
    for record in engine.records:
        if isinstance(record, TokensProduced) and record.place == path:
            occupancy += len(record.tokens)
            peak = max(peak, occupancy)
        elif isinstance(record, TokensConsumed) and record.place == path:
            occupancy -= len(record.tokens)
    return peak


def test_the_publication_inhibitor_still_admits_only_one_operation(tmp_path):
    """v1's descent fragment is imported unchanged; the rung split does not weaken it.

    (v1 owns the no-inhibitor counterfactual; repeating it here would only
    duplicate a hand-copied fragment.)
    """
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
    assert fired_rungs(engine.records, BRANCH) == ()
    with pytest.raises(ValueError, match="delivery identity conflict"):
        deliver_ci(
            engine, COMPILED, CIObserved("h1", Evidence(31, 1), "success"), identity="ci-future-g5", scope=future
        )
