"""Exclusivity and exhaustiveness as compiler properties, executed.

Experiment B's decisive finding was that hand-written overlapping guards are
refused by nothing, and that the business outcome is then settled by the Engine's
selection policy — host configuration the authored flow never mentions. It also
found that a non-exhaustive rung set strands observations silently.

Here the compiler owns both properties:

* **Exclusivity** comes from the generated ``NOT`` chain, so deliberately
  overlapping authored predicates still lower to at most one enabled candidate.
* **Exhaustiveness** comes from the generated chain plus the structural-cover
  check (``test_inet_kernel.py``), so a gap is refused at authoring time.

The grid below is the executed version of that claim over the *whole* state
space this net can be in — marking included, which B's predicate-only grid could
not reach.
"""

from itertools import product

from petrus.impetus.petrinet import Marking, NetPath, Token
from petrus.impetus.petrinet.enabledness import candidates

from inet_harness import FakeProviderLedger, compiled_filters, create, deliver_ci, deliver_head, drain, fired_branches
from inet_kernel import await_, branch, choice, flow, fork, join, lifecycle, otherwise
from inet_lowering import EVALUATIONS, compile_flow
from inet_scenario import readiness_flow
from inet_tokens import (
    UNSEEN,
    CIObserved,
    EvidenceId,
    EvidenceWatermark,
    HeadFact,
    HeadObserved,
    to_data,
)

HEAD = HeadFact("h2", 2, "L2")

WATERMARKS = (EvidenceWatermark(UNSEEN), EvidenceWatermark(EvidenceId(20, 1)))

EVENTS = tuple(
    CIObserved(head, EvidenceId(run, attempt), conclusion, fingerprint)
    for head in ("h2", "h9")
    for run, attempt in ((10, 1), (20, 1), (20, 2))
    for conclusion in ("success", "failure")
    for fingerprint in (None, "build")
)


def _marking(rerun: bool, repair: bool, published: bool, watermark: EvidenceWatermark, event: CIObserved) -> Marking:
    queues: dict[NetPath, tuple[Token, ...]] = {
        NetPath("events.ci"): (Token("CIObserved", to_data(event)),),
        NetPath("readiness.head"): (Token("HeadFact", to_data(HEAD)),),
        NetPath("readiness.watermark"): (Token("EvidenceWatermark", to_data(watermark)),),
    }
    if rerun:
        queues[NetPath("ladder.rerun")] = (Token("RerunRung", {}),)
    if repair:
        queues[NetPath("ladder.repair")] = (Token("RepairRung", {}),)
    if published:
        queues[NetPath("publication.admitted")] = (Token("PublicationClaim", {}),)
    return Marking(queues)


GRID = tuple(product((True, False), (True, False), (True, False), WATERMARKS, EVENTS))


def test_exactly_one_branch_is_enabled_over_the_whole_state_grid():
    """384 points of (ladder budget x publication latch x watermark x observation)."""
    compiled = compile_flow(readiness_flow())
    guards = dict(compiled.guards)
    filters = compiled_filters(compiled)

    assert len(GRID) == 8 * len(WATERMARKS) * len(EVENTS) == 384

    reached: set[str] = set()
    conflicts = []
    for rerun, repair, published, watermark, event in GRID:
        marking = _marking(rerun, repair, published, watermark, event)
        enabled = candidates(compiled.built.net, marking, guards, filters)
        if len(enabled) != 1:
            conflicts.append((rerun, repair, published, watermark, event, [str(b.transition) for b in enabled]))
        else:
            reached.add(str(enabled[0].transition))

    assert conflicts == []
    # Not vacuous: every authored branch answers somewhere in the grid.
    assert reached == {plan.transition for plan in compiled.branches}


def test_no_state_in_the_grid_can_strand_an_observation():
    """Totality restated as the property that matters operationally: the net never rests holding work."""
    compiled = compile_flow(readiness_flow())
    guards = dict(compiled.guards)
    filters = compiled_filters(compiled)

    stalled = [
        (rerun, repair, published, watermark, event)
        for rerun, repair, published, watermark, event in GRID
        if not candidates(compiled.built.net, _marking(rerun, repair, published, watermark, event), guards, filters)
    ]

    assert stalled == []


# --- the overlap counterexample, re-run against a generated guard chain --------


def any_failure(ci: CIObserved) -> bool:
    """Deliberately broad. Overlaps ``fingerprinted_failure`` on every classified failure."""
    return ci.conclusion == "failure"


def fingerprinted_failure(ci: CIObserved) -> bool:
    return ci.conclusion == "failure" and ci.fingerprint is not None


def overlapping_flow():
    """Two authored predicates that are both true for a fingerprinted failure."""
    head = await_("head", HeadObserved, seeds=fork("open", HeadObserved.as_head_fact, HeadObserved.unseen_watermark))
    ci = await_("ci", CIObserved)
    return flow(
        "overlap",
        lifecycle=lifecycle("branch"),
        ports={CIObserved: "events.ci", HeadFact: "readiness.head", EvidenceWatermark: "readiness.watermark"},
        latches=(),
        joins=(join(ci, reads=(HeadFact,), folds=(EvidenceWatermark,)),),
        nodes=(
            head,
            ci
            >> choice(
                "decide",
                branch("alpha", when=any_failure, folds=(CIObserved.watermark,)),
                branch("beta", when=fingerprinted_failure, folds=(CIObserved.watermark,)),
                otherwise("rest", folds=(CIObserved.watermark,)),
            ),
        ),
    )


def test_the_authored_predicates_really_do_overlap():
    """Sanity: without the compiler, this is exactly B's counterexample."""
    observation = CIObserved("h1", EvidenceId(20, 1), "failure", "build")

    assert any_failure(observation) and fingerprinted_failure(observation)


def test_overlapping_predicates_still_lower_to_exclusive_generated_guards(tmp_path):
    """B: two enabled candidates, outcome settled by selection policy. Here: one, by construction."""
    compiled = compile_flow(overlapping_flow())
    plans = {plan.id: plan for plan in compiled.branches}

    assert plans["alpha"].negated == ()
    assert plans["beta"].negated == ("any_failure",)
    assert plans["rest"].negated == ("any_failure", "fingerprinted_failure")

    engine = create(compiled, tmp_path / "overlap.jsonl", FakeProviderLedger())
    try:
        scope = engine.open_scope("branch")
        deliver_head(engine, compiled, HeadObserved("h1", "new", 1, "L1"), identity="head", scope=scope)
        deliver_ci(
            engine,
            compiled,
            CIObserved("h1", EvidenceId(20, 1), "failure", "build"),
            identity="ci",
            scope=scope,
        )

        enabled = candidates(compiled.built.net, engine.marking, dict(compiled.guards), compiled_filters(compiled))
        assert [str(binding.transition) for binding in enabled] == ["decide.alpha"]

        drain(engine)
        assert fired_branches(engine.records) == ("alpha",)
        assert engine.marking.place(NetPath("events.ci")) == ()  # answered, not stranded
    finally:
        engine.close()


def test_an_overlapped_branch_is_dead_not_ambiguous(tmp_path):
    """First-match-wins: the later branch never sees an observation the earlier one claimed."""
    compiled = compile_flow(overlapping_flow())
    engine = create(compiled, tmp_path / "dead.jsonl", FakeProviderLedger())
    try:
        scope = engine.open_scope("branch")
        deliver_head(engine, compiled, HeadObserved("h1", "new", 1, "L1"), identity="head", scope=scope)
        for index, fingerprint in enumerate((None, "build"), start=1):
            deliver_ci(
                engine,
                compiled,
                CIObserved("h1", EvidenceId(20, index), "failure", fingerprint),
                identity=f"ci-{index}",
                scope=scope,
            )
            drain(engine)

        assert fired_branches(engine.records) == ("alpha", "alpha")
    finally:
        engine.close()


# --- the price of the chain ----------------------------------------------------


def test_the_generated_chain_costs_measurable_predicate_evaluations(tmp_path):
    """Guard evaluation is never recorded, so it is only visible if counted deliberately."""
    compiled = compile_flow(readiness_flow())
    engine = create(compiled, tmp_path / "cost.jsonl", FakeProviderLedger())
    try:
        scope = engine.open_scope("branch")
        deliver_head(engine, compiled, HeadObserved("h1", "new", 1, "L1"), identity="head", scope=scope)
        drain(engine)
        EVALUATIONS.clear()
        deliver_ci(engine, compiled, CIObserved("h1", EvidenceId(10, 1), "success"), identity="ci", scope=scope)
        drain(engine)
        measured = dict(EVALUATIONS)
        answered = fired_branches(engine.records)
    finally:
        engine.close()

    # One clean decision, two enabledness surveys (select, then come to rest).
    # The counts are lower than the chain lengths suggest because both the
    # generated conjunction and its NOT chain short-circuit, and because the CEL
    # arc filter keeps a non-matching observation from ever assembling a binding
    # for the publish branches at all.
    predicates = {
        "is_for_another_head": 6,
        "is_not_newer_than": 6,
        "is_clean": 4,
        "is_classified_failure": 2,
    }
    assert {name: measured[name] for name in predicates} == predicates
    assert sum(predicates.values()) == 18  # against v1's single route_ci call and B's ten
    # ... against exactly one evaluation of the branch's own fold and request.
    assert measured["watermark"] == 1
    assert measured["publish_request"] == 1
    assert answered == ("publish",)


def test_token_multiplicity_is_outside_the_cover_proofs_model(tmp_path):
    """The cover proof models Boolean latch occupancy, not multiplicity (review finding).

    Two same-generation head deliveries are host-discipline violations v1 also
    documents, but here they corrupt STRUCTURE: the marking holds duplicate
    watermark and latch tokens, ``candidates(...)`` offers eight
    ``decide.rerun`` bindings for one observation, and the single firing that
    proceeds consumes only one token per port — leaving a surviving rerun
    latch that could spend the rung a second time. Exactly one firing still
    happens (grain holds); exclusivity-by-construction does not extend to
    duplicated tokens.
    """
    compiled = compile_flow(readiness_flow())
    engine = create(compiled, tmp_path / "duplicated.jsonl", FakeProviderLedger())
    try:
        scope = engine.open_scope("branch")
        deliver_head(engine, compiled, HeadObserved("h1", "new", 1, "L1"), identity="head-a", scope=scope)
        deliver_head(engine, compiled, HeadObserved("h1", "new", 1, "L1"), identity="head-b", scope=scope)
        deliver_ci(
            engine, compiled, CIObserved("h1", EvidenceId(20, 1), "failure", "build"), identity="ci", scope=scope
        )

        enabled = candidates(compiled.built.net, engine.marking, dict(compiled.guards), compiled_filters(compiled))
        assert [str(binding.transition) for binding in enabled] == ["decide.rerun"] * 8

        fired = drain(engine)
        assert [str(firing.transition) for firing in fired] == ["decide.rerun"]
        # The structural budget is now corrupted: one rerun latch survived.
        assert len(engine.marking.place(NetPath("ladder.rerun"))) == 1
        assert len(engine.marking.place(NetPath("readiness.watermark"))) == 2
    finally:
        engine.close()
