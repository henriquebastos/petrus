"""The behavioural acceptance matrix, executed against canonical records and marking.

Behaviour parity with v1 is the claim; topology, paths, state representation, and
History bytes deliberately differ. Every assertion here reads canonical Petrus
truth (records, marking, scope dispositions) or the independent fake-provider
ledger — never the compiler's own bookkeeping.
"""

import pytest

from petrus.impetus.history import ActivityCompleted, ActivityRequested, FiringCompleted
from petrus.impetus.instance import DeliveryDisposition, PriorAcknowledgement, ScopedDeliveryAcknowledgement
from petrus.impetus.petrinet import NetPath
from petrus.impetus.petrinet.enabledness import candidates
from petrus.impetus.scope import LifecycleScope

from inet_harness import (
    FakeProviderLedger,
    compiled_filters,
    create,
    deliver_ci,
    deliver_head,
    drain,
    fired_branches,
    value_at,
    values_at,
)
from inet_lowering import compile_flow
from inet_scenario import readiness_flow
from inet_tokens import (
    CIObserved,
    EvidenceId,
    HeadFact,
    HeadObserved,
    HumanNeeded,
    Published,
    RepairLanded,
    RerunAccepted,
)


@pytest.fixture
def slice_(tmp_path):
    compiled = compile_flow(readiness_flow())
    ledger = FakeProviderLedger()
    engine = create(compiled, tmp_path / "readiness.jsonl", ledger)
    try:
        yield compiled, engine, ledger
    finally:
        engine.close()


def _open(engine, compiled, head: str, generation: int, lineage: str, scope=None, relation="new"):
    scope = engine.open_scope("branch") if scope is None else engine.reset_scope(scope)
    deliver_head(
        engine,
        compiled,
        HeadObserved(head, relation, generation, lineage),
        identity=f"head-{head}-g{generation}",
        scope=scope,
    )
    return scope


def test_clean_ci_publishes_once_and_reaches_a_terminal_published_fact(slice_):
    compiled, engine, ledger = slice_
    scope = _open(engine, compiled, "h1", 1, "L1")
    deliver_ci(engine, compiled, CIObserved("h1", EvidenceId(10, 1), "success"), identity="ci-10-1-g1", scope=scope)
    drain(engine)

    assert ledger.attempts == {"publish:h1:g1": 1}
    assert value_at(engine, "terminal.published", Published) == Published("publish:h1:g1", "h1", 1)
    assert fired_branches(engine.records) == ("publish",)


def test_one_publication_is_admitted_per_generation_by_the_inhibitor_latch(slice_):
    """The publication latch is structure: the second clean observation is absorbed, not re-published."""
    compiled, engine, ledger = slice_
    scope = _open(engine, compiled, "h1", 1, "L1")
    for run in (10, 11):
        deliver_ci(engine, compiled, CIObserved("h1", EvidenceId(run, 1), "success"), identity=f"ci-{run}", scope=scope)
        drain(engine)

    assert ledger.attempts == {"publish:h1:g1": 1}
    assert fired_branches(engine.records) == ("publish", "republished")
    assert len(engine.marking.place(NetPath("terminal.published"))) == 1
    assert len(engine.marking.place(NetPath("publication.admitted"))) == 1


def test_two_clean_observations_at_once_still_admit_only_one_publication(slice_):
    """Even delivered before any advance, the latch admits one — the structural claim, not a race."""
    compiled, engine, ledger = slice_
    scope = _open(engine, compiled, "h1", 1, "L1")
    deliver_ci(engine, compiled, CIObserved("h1", EvidenceId(10, 1), "success"), identity="a", scope=scope)
    deliver_ci(engine, compiled, CIObserved("h1", EvidenceId(11, 1), "success"), identity="b", scope=scope)
    drain(engine)

    assert ledger.attempts == {"publish:h1:g1": 1}
    assert sorted(fired_branches(engine.records)) == ["publish", "republished"]


def test_first_exact_head_failure_spends_the_rerun_rung_once(slice_):
    compiled, engine, ledger = slice_
    scope = _open(engine, compiled, "h2", 1, "L2")
    deliver_ci(
        engine,
        compiled,
        CIObserved("h2", EvidenceId(20, 1), "failure", "build"),
        identity="ci-20-1",
        scope=scope,
    )
    drain(engine)

    assert ledger.attempts == {"rerun:L2:build": 1}
    assert values_at(engine, "facts.rerun_accepted", RerunAccepted) == (RerunAccepted("rerun:L2:build", "h2"),)
    # The rung is spent because its place is empty; no boolean anywhere says so.
    assert engine.marking.place(NetPath("ladder.rerun")) == ()
    assert len(engine.marking.place(NetPath("ladder.repair"))) == 1


def test_identity_redelivery_answers_prior_acknowledgement_and_appends_nothing(slice_):
    compiled, engine, ledger = slice_
    scope = _open(engine, compiled, "h2", 1, "L2")
    failure = CIObserved("h2", EvidenceId(20, 1), "failure", "build")
    deliver_ci(engine, compiled, failure, identity="ci-20-1", scope=scope)
    drain(engine)
    before = len(engine.records)

    answer = deliver_ci(engine, compiled, failure, identity="ci-20-1", scope=scope)

    assert isinstance(answer, PriorAcknowledgement)
    assert len(engine.records) == before
    assert ledger.attempts == {"rerun:L2:build": 1}


def test_same_evidence_under_a_new_identity_is_absorbed_and_names_its_branch(slice_):
    compiled, engine, ledger = slice_
    scope = _open(engine, compiled, "h2", 1, "L2")
    failure = CIObserved("h2", EvidenceId(20, 1), "failure", "build")
    deliver_ci(engine, compiled, failure, identity="ci-20-1", scope=scope)
    drain(engine)
    deliver_ci(engine, compiled, failure, identity="ci-20-1-echo", scope=scope)
    drain(engine)

    assert ledger.attempts == {"rerun:L2:build": 1}  # no budget spent
    assert fired_branches(engine.records) == ("rerun", "stale")
    # "Why nothing happened" is a durable, named firing, not an absence.
    absorbed = [record for record in engine.records if isinstance(record, FiringCompleted)][-1]
    assert str(absorbed.transition) == "decide.stale"


def test_evidence_for_another_head_is_absorbed_by_its_own_branch(slice_):
    compiled, engine, ledger = slice_
    scope = _open(engine, compiled, "h2", 1, "L2")
    deliver_ci(engine, compiled, CIObserved("h9", EvidenceId(20, 1), "success"), identity="foreign", scope=scope)
    drain(engine)

    assert ledger.attempts == {}
    assert fired_branches(engine.records) == ("foreign",)
    assert len(engine.marking.place(NetPath("publication.admitted"))) == 0


def test_a_failure_without_a_fingerprint_is_absorbed_by_the_otherwise_branch(slice_):
    compiled, engine, ledger = slice_
    scope = _open(engine, compiled, "h2", 1, "L2")
    deliver_ci(engine, compiled, CIObserved("h2", EvidenceId(20, 1), "failure"), identity="raw", scope=scope)
    drain(engine)

    assert ledger.attempts == {}
    assert fired_branches(engine.records) == ("unclassified",)
    assert len(engine.marking.place(NetPath("ladder.rerun"))) == 1  # no rung spent


def test_a_strictly_newer_failure_spends_repair_not_a_second_rerun(slice_):
    compiled, engine, ledger = slice_
    scope = _open(engine, compiled, "h2", 1, "L2")
    for attempt in (1, 2):
        deliver_ci(
            engine,
            compiled,
            CIObserved("h2", EvidenceId(20, attempt), "failure", "build"),
            identity=f"ci-20-{attempt}",
            scope=scope,
        )
        drain(engine)

    assert ledger.attempts == {"rerun:L2:build": 1, "repair:L2:build": 1}
    assert fired_branches(engine.records) == ("rerun", "repair")
    assert values_at(engine, "facts.repair_landed", RepairLanded) == (RepairLanded("repair:L2:build", "h2", "h2r"),)


def test_a_further_matching_failure_after_repair_surfaces_human_needed_and_no_new_operation(slice_):
    compiled, engine, ledger = slice_
    scope = _open(engine, compiled, "h2", 1, "L2")
    for attempt in (1, 2, 3):
        deliver_ci(
            engine,
            compiled,
            CIObserved("h2", EvidenceId(20, attempt), "failure", "build"),
            identity=f"ci-20-{attempt}",
            scope=scope,
        )
        drain(engine)

    assert ledger.attempts == {"rerun:L2:build": 1, "repair:L2:build": 1}
    assert fired_branches(engine.records) == ("rerun", "repair", "human")
    assert values_at(engine, "terminal.human_needed", HumanNeeded) == (HumanNeeded("h2", "L2", "build"),)
    # The ladder is exhausted structurally: both rung places are empty.
    assert engine.marking.place(NetPath("ladder.rerun")) == ()
    assert engine.marking.place(NetPath("ladder.repair")) == ()


def test_a_confirmed_repair_head_keeps_its_lineage_and_an_unrelated_head_starts_a_fresh_one(slice_):
    compiled, engine, ledger = slice_
    generation_1 = _open(engine, compiled, "h2", 1, "L2")
    deliver_ci(
        engine,
        compiled,
        CIObserved("h2", EvidenceId(20, 1), "failure", "build"),
        identity="ci-20-1",
        scope=generation_1,
    )
    drain(engine)

    generation_2 = _open(engine, compiled, "h2r", 2, "L2", scope=generation_1, relation="confirmed")
    deliver_ci(
        engine, compiled, CIObserved("h2r", EvidenceId(21, 1), "success"), identity="ci-21-1", scope=generation_2
    )
    drain(engine)

    assert value_at(engine, "readiness.head", HeadFact) == HeadFact("h2r", 2, "L2")
    assert ledger.attempts["publish:h2r:g2"] == 1
    # The successor generation re-armed the whole ladder structurally.
    assert len(engine.marking.place(NetPath("ladder.rerun"))) == 1
    assert len(engine.marking.place(NetPath("ladder.repair"))) == 1

    generation_3 = _open(engine, compiled, "h3", 3, "L4", scope=generation_2, relation="superseded")
    deliver_ci(
        engine,
        compiled,
        CIObserved("h3", EvidenceId(30, 1), "failure", "build"),
        identity="ci-30-1",
        scope=generation_3,
    )
    drain(engine)

    assert value_at(engine, "readiness.head", HeadFact) == HeadFact("h3", 3, "L4")
    assert ledger.attempts["rerun:L4:build"] == 1  # a fresh lineage, a fresh budget


def test_scope_reset_discards_the_whole_generation_including_its_structural_state(slice_):
    compiled, engine, _ = slice_
    generation_1 = _open(engine, compiled, "h1", 1, "L1")
    deliver_ci(engine, compiled, CIObserved("h1", EvidenceId(10, 1), "success"), identity="ci", scope=generation_1)
    drain(engine)
    assert len(engine.marking.place(NetPath("publication.admitted"))) == 1

    generation_2 = engine.reset_scope(generation_1)

    for path in ("readiness.head", "readiness.watermark", "ladder.rerun", "ladder.repair", "publication.admitted"):
        assert engine.marking.place(NetPath(path)) == (), path
    assert generation_2.generation == 2


def test_closed_generation_drops_and_unproven_future_quarantines_idempotently(slice_):
    compiled, engine, _ = slice_
    generation_1 = _open(engine, compiled, "h1", 1, "L1")
    generation_2 = _open(engine, compiled, "h2", 2, "L2", scope=generation_1)
    stale = CIObserved("h1", EvidenceId(10, 1), "success")
    future = LifecycleScope("branch", 9)

    dropped = deliver_ci(engine, compiled, stale, identity="stale", scope=generation_1)
    quarantined = deliver_ci(engine, compiled, stale, identity="future", scope=future)
    again_dropped = deliver_ci(engine, compiled, stale, identity="stale", scope=generation_1)
    again_quarantined = deliver_ci(engine, compiled, stale, identity="future", scope=future)

    assert dropped == ScopedDeliveryAcknowledgement("stale", DeliveryDisposition.DROPPED, generation_1)
    assert quarantined == ScopedDeliveryAcknowledgement("future", DeliveryDisposition.QUARANTINED, future)
    assert again_dropped == dropped
    assert again_quarantined == quarantined
    assert fired_branches(engine.records) == ()
    assert generation_2.generation == 2


def test_fusing_the_fold_into_the_effect_serializes_decisions_while_it_is_in_flight(slice_):
    """The named semantic difference from v1, executed rather than argued.

    v1 returned the state baton immediately and requested its effect from a
    separate transition, so a second observation could be decided while the first
    effect was still running. Here the folded ports are consumed by the effect's
    own firing, so between ``ActivityRequested`` (durable) and
    ``ActivityCompleted`` no other observation can be decided at all.
    """
    compiled, engine, _ = slice_
    scope = _open(engine, compiled, "h2", 1, "L2")
    for attempt in (1, 2):
        deliver_ci(
            engine,
            compiled,
            CIObserved("h2", EvidenceId(20, attempt), "failure", "build"),
            identity=f"ci-20-{attempt}",
            scope=scope,
        )

    for _ in range(8):  # advance only until the first request is durable
        if any(isinstance(record, ActivityRequested) for record in engine.records):
            break
        engine.advance()

    requested = [record for record in engine.records if isinstance(record, ActivityRequested)]
    assert len(requested) == 1 and str(requested[0].transition) == "decide.rerun"
    assert not any(isinstance(record, ActivityCompleted) for record in engine.records)
    # The second observation is admitted and waiting, the folded watermark is
    # in flight with the effect, and nothing else can be decided.
    assert len(engine.marking.place(NetPath("events.ci"))) == 1
    assert engine.marking.place(NetPath("readiness.watermark")) == ()
    assert candidates(compiled.built.net, engine.marking, dict(compiled.guards), compiled_filters(compiled)) == []

    drain(engine)
    assert fired_branches(engine.records) == ("rerun", "repair")


def test_the_grain_is_exactly_one_firing_per_delivered_observation(slice_):
    """The whole point: guard decides, effect fires, state folds — one transition."""
    compiled, engine, _ = slice_
    scope = _open(engine, compiled, "h2", 1, "L2")
    observations = (
        CIObserved("h9", EvidenceId(10, 1), "success"),  # foreign
        CIObserved("h2", EvidenceId(20, 1), "failure", "build"),  # rerun (an Activity)
        CIObserved("h2", EvidenceId(20, 1), "failure", "build"),  # stale
        CIObserved("h2", EvidenceId(20, 2), "failure", "build"),  # repair (an Activity)
        CIObserved("h2", EvidenceId(20, 3), "failure"),  # unclassified
        CIObserved("h2", EvidenceId(20, 4), "failure", "build"),  # human
    )
    for index, observation in enumerate(observations):
        deliver_ci(engine, compiled, observation, identity=f"ci-{index}", scope=scope)
        drain(engine)

    assert fired_branches(engine.records) == ("foreign", "rerun", "stale", "repair", "unclassified", "human")
    # One firing per observation, effects included: the ActivityRequested that
    # makes a decision durable belongs to the branch's own occurrence.
    requests = [record for record in engine.records if isinstance(record, ActivityRequested)]
    completions = [record for record in engine.records if isinstance(record, FiringCompleted)]
    decisions = [record for record in completions if str(record.transition).startswith("decide.")]
    assert len(decisions) == len(observations)
    assert {record.occurrence for record in requests} <= {record.occurrence for record in decisions}


def test_a_failed_fused_effect_destroys_the_folded_state_and_wedges_the_decision_group(tmp_path):
    """The fusion's failure blast radius, pinned (adversarial review finding).

    v1 decided first and effected second, so a failed effect consumed only its
    command token. Fusing the fold into the effect means a terminal Activity
    failure consumes the CI event, the folded watermark, and the spent rung
    latch with no recovery projection: after the canonical ``ActivityFailed``
    + ``FiringFailed`` pair, the watermark port is empty and EVERY subsequent
    observation strands unanswered. Petrus's ``FailureProjectingActivityHandler``
    seam is where a promoted design must project a failure-survivable state.
    """
    from petrus.engine import Engine
    from petrus.impetus.history import ActivityFailed, FiringFailed
    from petrus.impetus.history_store.jsonl import JsonlHistoryStore
    from petrus.motus.activity import ActivityError
    from petrus.motus.dispatch import InlineDispatch

    from inet_harness import INSTANCE, _dispatch

    compiled = compile_flow(readiness_flow())

    def failing_rerun(invocation, *, context):
        raise ActivityError("provider rejected the rerun", retryable=False)

    def compose(door, activities):
        return door(
            compiled.built.net,
            INSTANCE,
            history=JsonlHistoryStore(tmp_path / "failing.jsonl"),
            dispatch=InlineDispatch(activities),
            handlers=dict(compiled.handlers),
            guards=dict(compiled.guards),
            activities=tuple(definition.declaration for definition in compiled.activities),
        )

    broken = dict(_dispatch(FakeProviderLedger()).activities)
    broken["rerun"] = failing_rerun
    engine = compose(Engine.create, broken)
    scope = engine.open_scope("branch")
    deliver_head(engine, compiled, HeadObserved("h1", "new", 1, "L1"), identity="head-h1-g1", scope=scope)
    deliver_ci(
        engine, compiled, CIObserved("h1", EvidenceId(20, 1), "failure", "build"), identity="ci-20-1", scope=scope
    )
    with pytest.raises(RuntimeError, match="failed terminally"):
        drain(engine)
    engine.close()

    healthy = dict(_dispatch(FakeProviderLedger()).activities)
    resumed = compose(Engine.load, healthy)
    try:
        drain(resumed)
        assert [
            type(record).__name__ for record in resumed.records if isinstance(record, (ActivityFailed, FiringFailed))
        ] == [
            "ActivityFailed",
            "FiringFailed",
        ]
        # The folded watermark and the spent rung latch died with the firing.
        assert not resumed.marking.place(NetPath("readiness.watermark"))
        assert not resumed.marking.place(NetPath("ladder.rerun"))
        # The wedge: a strictly newer matching failure now strands unanswered —
        # every decision branch folds the watermark, and there is none.
        deliver_ci(
            resumed,
            compiled,
            CIObserved("h1", EvidenceId(20, 2), "failure", "build"),
            identity="ci-20-2",
            scope=scope,
        )
        assert drain(resumed) == ()
        assert len(resumed.marking.place(NetPath("events.ci"))) == 1
    finally:
        resumed.close()
