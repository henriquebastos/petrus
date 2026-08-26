"""Engine-executed Hamsterdan-shaped semantics over the compiled flow.

Assertions inspect canonical History records and the marking, not only the
fake provider ledger: the record class plus transition path is what
establishes each durable boundary.
"""

import pytest

from petrus.impetus.dsl import petri_handler
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

from algebra import CompositionError, await_event, drop, effect, lifecycle, low_level, machine, on, terminal
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
    RepairLanded,
    RepairRequested,
    RerunAccepted,
    RerunRequested,
    to_data,
)
from harness import FakeProviderLedger, create, deliver_ci, deliver_head, drain, value_at, values_at
from lowering import FragmentPorts, compile_flow
from scenario import accept_publish, admit_head, publish, readiness_flow, repair, rerun, route_ci

COMPILED = compile_flow(readiness_flow())


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
    accept_index = records.index(accept_begun[0])
    assert completed_index < accept_index
    assert len(engine.marking.place(NetPath("effects.publish.done"))) == 1

    state = value_at(engine, "readiness.state", ReadinessState)
    assert state.publication_operation == "publish:h1:g1"


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


def test_failure_after_repair_surfaces_human_needed(tmp_path):
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

    deliver_ci(
        engine,
        COMPILED,
        CIObserved("h1", Evidence(20, 3), "failure", fingerprint="build"),
        identity="ci-20-3-g1",
        scope=scope,
    )
    drain(engine)

    assert value_at(engine, "terminal.human_needed", HumanNeeded) == HumanNeeded("h1", "L1", "build")
    assert ledger.attempts == {"rerun:L1:build": 1, "repair:L1:build": 1}
    assert len([record for record in engine.records if isinstance(record, ActivityRequested)]) == 2


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


def _open_gate(gate):
    """The counterfactual publication fragment: identical, minus inhibitors."""
    pending = gate.place("pending", role="latch")
    done = gate.place("done", role="latch")
    work = gate.place("work", color=gate.input_type, role="work")
    ack = gate.place("ack", color=gate.returns, role="ack")

    def authorize_publication(binding, outputs):
        del outputs
        [(_, (request,))] = binding.consumed
        return {work: (request,), pending: (Token.black(),)}

    def accept_acknowledgement(binding, outputs):
        del outputs
        (_, _pending), (_, (acknowledged,)) = binding.consumed
        return {gate.output: (acknowledged,), done: (Token.black(),)}

    authorize = gate.transition("authorize", petri_handler(authorize_publication), role="admit")
    execute = gate.activity_transition("execute", publish, role="effect")
    accept = gate.transition("accept", petri_handler(accept_acknowledgement), role="accept")

    gate.consume(gate.input, authorize)
    gate.produce(authorize, work)
    gate.produce(authorize, pending)
    gate.consume(work, execute)
    gate.produce(execute, ack)
    gate.consume(pending, accept)
    gate.consume(ack, accept)
    gate.produce(accept, gate.output)
    gate.produce(accept, done)

    return FragmentPorts(input=gate.input, output=gate.output)


def _flow_with_gate(gate_fragment):
    return machine(
        "readiness",
        lifecycle=lifecycle("branch"),
        handlers=(
            on(await_event("head", HeadObserved)).project("admit_head", admit_head),
            on(await_event("ci", CIObserved))
            .decide("route_ci", route_ci)
            .choose(
                {
                    PublishRequested: low_level("publish_once", gate_fragment, returns=PublishAcknowledged),
                    RerunRequested: effect("rerun", rerun),
                    RepairRequested: effect("repair", repair),
                    HumanNeeded: terminal("human_needed"),
                    Ignored: drop(),
                }
            ),
            on(PublishAcknowledged).fold("accept_publish", accept_publish).to(terminal("published")),
        ),
    )


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


def test_publication_inhibitor_allows_only_one_pending_operation(tmp_path):
    two_requests = Marking(
        {
            NetPath("commands.publish"): (
                Token("PublishRequested", to_data(PublishRequested("publish:h1:g1", "h1", 1))),
                Token("PublishRequested", to_data(PublishRequested("publish:h9:g1", "h9", 1))),
            )
        }
    )

    # Counterfactual first: without the inhibitor arcs, both directly supplied
    # requests become CONCURRENTLY pending — peak occupancy is genuinely two
    # at once, not two sequential publications.
    open_compiled = compile_flow(_flow_with_gate(_open_gate))
    open_ledger = FakeProviderLedger()
    open_engine = create(open_compiled, tmp_path / "open.jsonl", open_ledger, marking=two_requests)
    drain(open_engine)
    assert len(_firings_of(open_engine, "effects.publish.authorize")) == 2
    assert sorted(open_ledger.attempts) == ["publish:h1:g1", "publish:h9:g1"]
    assert _peak_occupancy(open_engine, "effects.publish.pending") == 2

    # The authored gate: the inhibitors admit one publication — at most one
    # pending concurrently, and the ``done`` latch refuses a serial second.
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
    delivered_identities = {record.identity for record in engine.records if isinstance(record, ExternalEventDelivered)}
    assert delivered_identities == {"head-h1-g1"}
    with pytest.raises(ValueError, match="delivery identity conflict"):
        deliver_ci(
            engine,
            COMPILED,
            CIObserved("h1", Evidence(31, 1), "success"),
            identity="ci-future-g5",
            scope=future,
        )


def test_head_generation_must_match_its_exact_delivery_scope(tmp_path):
    engine = _engine(tmp_path)
    scope = engine.open_scope("branch")

    with pytest.raises(ValueError, match="claims generation 7"):
        deliver_head(engine, COMPILED, HeadObserved("h1", "new", 7, "L1"), identity="head-h1-g7", scope=scope)

    assert not any(isinstance(record, ExternalEventDelivered) for record in engine.records)


def test_low_level_fragment_cannot_reach_outside_its_scope():
    def escaping_gate(gate):
        def steal(binding, outputs):
            del outputs
            return {}

        authorize = gate.transition("authorize", petri_handler(steal), role="escape attempt")
        gate.consume("readiness.state", authorize)  # not a supplied port
        return FragmentPorts(input=gate.input, output=gate.output)

    with pytest.raises(CompositionError, match=r"readiness\.state is outside scope effects\.publish"):
        compile_flow(_flow_with_gate(escaping_gate))
