"""The proof obligation the rung split creates, and what happens when it fails.

v1 could not have these tests: one pure function returning one tagged outcome
is exclusive and exhaustive *by construction*. Five independently guarded
transitions are neither, and Petrus cannot check it for you — selection has no
case priority, so simultaneously true guards are a genuine conflict.

Three claims live here:

1. the authored rung set is exclusive and exhaustive over a systematic grid;
2. each rung's fold+emit reproduces v1's ``route_ci`` exactly over that grid,
   so the split preserved semantics rather than approximating them; and
3. the deliberate counterexamples in ``guarded_counterexample.py`` compile,
   validate, and run — the mistakes surface only as a wrong outcome.
"""

import pytest

from petrus.impetus.net_definition import parse_net_definition, project_net_definition
from petrus.impetus.petrinet import NetPath
from petrus.impetus.petrinet.enabledness import candidates
from petrus.impetus.selection import Priority, SelectionPipeline

from domain import CIObserved, Evidence, HeadObserved, Ignored, Ladder, ReadinessState
from guarded_counterexample import ALPHA, BETA, BRANCH, incomplete_flow, overlapping_flow
from guarded_harness import create_selecting, fired_rungs
from guarded_lowering import compile_guarded_flow
from guarded_scenario import (
    absorb,
    exhaust,
    first_clean,
    fresh_failure,
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
from harness import deliver_ci, deliver_head, drain
from scenario import route_ci

# (predicate, fold, emit) in authored rung order; ``emit is None`` is the drop.
RUNGS = (
    ("ignore", not_actionable, absorb, None),
    ("publish", first_clean, note_publication, request_publication),
    ("rerun", fresh_failure, spend_rerun, request_rerun),
    ("repair", repeated_failure, spend_repair, request_repair),
    ("human", ladder_exhausted, exhaust, surface_human_needed),
)

LADDERS = (
    Ladder("L2", None, False, False, None),
    Ladder("L2", "build", False, False, Evidence(20, 1)),
    Ladder("L2", "build", True, False, Evidence(20, 1)),
    Ladder("L2", "build", True, True, Evidence(20, 2)),
    Ladder("L2", "test", True, True, Evidence(20, 2)),
    Ladder("L1", "build", True, False, Evidence(20, 1)),  # ladder lineage differs from the state's
)

STATES = tuple(
    ReadinessState("h2", 2, "L2", ladder, publication) for ladder in LADDERS for publication in (None, "publish:h2:g2")
)

EVENTS = tuple(
    CIObserved(head, Evidence(run, attempt), conclusion, fingerprint)
    for head in ("h2", "h9")
    for run, attempt in ((10, 1), (20, 1), (20, 2), (21, 1))
    for conclusion in ("success", "failure")
    for fingerprint in (None, "build", "test")
)

GRID = tuple((state, event) for state in STATES for event in EVENTS)


def _selected(state: ReadinessState, event: CIObserved) -> list[str]:
    return [name for name, when, _, _ in RUNGS if when(state, event)]


def test_exactly_one_rung_predicate_holds_over_a_systematic_grid():
    """Executable exclusivity + exhaustiveness. It cannot be proved statically."""
    assert len(GRID) == 576

    overlaps = [(state, event, hits) for state, event in GRID if len(hits := _selected(state, event)) != 1]

    assert overlaps == []
    # Every rung is actually reachable in the grid, so the check is not vacuous.
    covered = {_selected(state, event)[0] for state, event in GRID}
    assert covered == {name for name, _, _, _ in RUNGS}


def test_each_rung_reproduces_v1_route_ci_state_and_outcome_over_the_grid():
    """Semantics preserved at the decision level, not only at the fixture level."""
    for state, event in GRID:
        [name] = _selected(state, event)
        _, _, fold, emit = next(entry for entry in RUNGS if entry[0] == name)
        expected = route_ci(state, event)

        assert fold(state, event) == expected.state, (name, state, event)
        if emit is None:
            assert isinstance(expected.outcome, Ignored), (name, state, event)
        else:
            assert emit(state, event) == expected.outcome, (name, state, event)


def test_overlapping_rung_guards_are_refused_by_nothing_and_conflict_at_runtime(tmp_path):
    """The counterexample: two true guards compile, validate, and conflict."""
    compiled = compile_guarded_flow(overlapping_flow())  # no CompositionError
    assert parse_net_definition(compiled.definition_bytes) == project_net_definition(compiled.built.net)

    engine = create_selecting(compiled, tmp_path / "overlap.jsonl")
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

        # Both rungs are enabled on the same tokens: a conflict, not a case table.
        enabled = candidates(compiled.built.net, engine.marking, dict(compiled.guards))
        assert sorted(str(binding.transition) for binding in enabled) == [ALPHA, BETA]
    finally:
        engine.close()


def _run_overlap(path, selection) -> tuple[tuple[str, ...], int, int]:
    compiled = compile_guarded_flow(overlapping_flow())
    engine = create_selecting(compiled, path, selection=selection)
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
        return (
            fired_rungs(engine.records, BRANCH),
            len(engine.marking.place(NetPath("terminal.alpha_seen"))),
            len(engine.marking.place(NetPath("terminal.beta_seen"))),
        )
    finally:
        engine.close()


def test_an_overlapping_conflict_is_settled_by_the_selection_policy_not_the_domain(tmp_path):
    """The finding: not coin-flip nondeterminism — worse, silently reconfigurable.

    One authored source and one identical observation produce two different
    durable domain outcomes depending on the Engine's selection policy, which
    is host configuration the authored flow never mentions. Under the default
    ``SelectionPipeline`` the path-first rung always wins, so a conflict is
    reproducible — and therefore easy to mistake for intended case priority.
    """
    default = _run_overlap(tmp_path / "default.jsonl", None)
    prioritized = _run_overlap(tmp_path / "prioritized.jsonl", SelectionPipeline(strategy=Priority({BETA: 1})))

    assert default == (("alpha",), 1, 0)
    assert prioritized == (("beta",), 0, 1)
    # Exactly one rung fires either way, so the conflict is invisible in the
    # grain: no duplicate firing, no error, just the other rung's outcome.
    assert len(default[0]) == len(prioritized[0]) == 1


def test_a_non_exhaustive_rung_set_silently_strands_the_observation(tmp_path):
    """The other half of the obligation: a gap is not an error, it is a stall."""
    compiled = compile_guarded_flow(incomplete_flow())
    engine = create_selecting(compiled, tmp_path / "gap.jsonl")
    try:
        scope = engine.open_scope("branch")
        deliver_head(engine, compiled, HeadObserved("h1", "new", 1, "L1"), identity="head", scope=scope)
        deliver_ci(engine, compiled, CIObserved("h1", Evidence(20, 1), "success"), identity="ci", scope=scope)
        drain(engine)

        assert fired_rungs(engine.records, BRANCH) == ()
        assert len(engine.marking.place(NetPath("events.ci"))) == 1  # admitted, never answered
        assert candidates(compiled.built.net, engine.marking, dict(compiled.guards)) == []
    finally:
        engine.close()


@pytest.mark.parametrize(
    ("state", "event", "expected"),
    [
        (STATES[0], CIObserved("h2", Evidence(10, 1), "success"), "publish"),
        (STATES[1], CIObserved("h2", Evidence(10, 1), "success"), "ignore"),  # publication already requested
        (STATES[0], CIObserved("h9", Evidence(10, 1), "success"), "ignore"),  # another head
        (STATES[0], CIObserved("h2", Evidence(10, 1), "failure"), "ignore"),  # no fingerprint, no rung
        (STATES[0], CIObserved("h2", Evidence(10, 1), "failure", "build"), "rerun"),
        (STATES[8], CIObserved("h2", Evidence(21, 1), "failure", "build"), "rerun"),  # fresh fingerprint
        (STATES[10], CIObserved("h2", Evidence(21, 1), "failure", "build"), "rerun"),  # fresh lineage
        (STATES[4], CIObserved("h2", Evidence(21, 1), "failure", "build"), "repair"),
        (STATES[6], CIObserved("h2", Evidence(21, 1), "failure", "build"), "human"),
        (STATES[6], CIObserved("h2", Evidence(20, 2), "failure", "build"), "ignore"),  # not newer than watermark
    ],
)
def test_named_ladder_positions_select_their_intended_rung(state, event, expected):
    """Readable spot checks behind the grid, so a regression names its case."""
    assert _selected(state, event) == [expected]
