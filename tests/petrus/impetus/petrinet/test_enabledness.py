"""Behavioral tests for the pure enabledness computation."""

from __future__ import annotations

# Python imports
import warnings

# Pip imports
import pytest

# Internal imports
from petrus.impetus.petrinet import (
    Alternative,
    Binding,
    FilterEvaluationWarning,
    Satisfied,
    Alternatives,
    Veto,
    admitted,
    candidates,
    offer,
    selection,
)
from petrus.impetus.petrinet import Marking, Token
from petrus.impetus.petrinet import Arc, ArcMode, Net, NetPath, Place, Transition


def _net():
    """Two transitions competing for place ``p``; ``src`` is a source (no inputs)."""
    p, t1, t2, src, out = NetPath("p"), NetPath("t1"), NetPath("t2"), NetPath("src"), NetPath("out")
    return Net(
        places=[Place(p), Place(out)],
        transitions=[Transition(t1), Transition(t2), Transition(src)],
        arcs=[Arc(p, t1), Arc(p, t2), Arc(src, out)],
    )


class TestCandidates:
    def test_source_transitions_are_excluded(self):
        net = _net()
        marking = Marking({NetPath("p"): (Token.black(),)})
        assert NetPath("src") not in [b.transition for b in candidates(net, marking)]

    def test_requires_available_tokens(self):
        net = _net()
        assert candidates(net, Marking()) == []

    def test_order_is_stable_and_path_sorted(self):
        net = _net()
        marking = Marking({NetPath("p"): (Token.black(),)})
        assert [b.transition for b in candidates(net, marking)] == [NetPath("t1"), NetPath("t2")]

    def test_binding_records_the_tokens_it_would_consume(self):
        net = _net()
        token = Token("X")
        [binding, *_] = candidates(net, Marking({NetPath("p"): (token,)}))
        assert isinstance(binding, Binding)
        assert binding.tokens == (token,)

    def test_delivered_tokens_join_the_binding_tokens(self):
        # A source firing's binding consumes nothing; external delivery
        # injects its tokens instead, and they flow (and are peeked) exactly
        # like consumed selections.
        token = Token("WebhookEvent", {"id": 1})
        binding = Binding(NetPath("src"), consumed=(), delivered=(token,))
        assert binding.tokens == (token,)
        assert binding.peeked == (token,)

    def test_a_delivered_binding_rejects_input_selections(self):
        # A delivered binding is a source firing and selects nothing: the
        # consumed+delivered hybrid is semantically meaningless (a source has
        # no input arcs) and the value object refuses it.
        token = Token("X")
        with pytest.raises(ValueError, match="a delivered binding is a source firing and selects nothing"):
            Binding(NetPath("src"), consumed=((NetPath("p"), (token,)),), delivered=(token,))
        with pytest.raises(ValueError, match="a delivered binding is a source firing and selects nothing"):
            Binding(NetPath("src"), consumed=(), read=((NetPath("p"), (token,)),), delivered=(token,))


class TestMultiBindingEnumeration:
    """
    A transition is enabled under EVERY admissible selection, not just the
    FIFO head [spec firing-semantics.md: "A transition may be enabled under
    many firing bindings at once"; ADR 0008: the core enumerates candidates,
    the scheduler chooses]. Enumeration order is the determinism contract:
    input-arc-major, FIFO-position-minor lexicographic, so the head selection
    is always the FIRST binding and a conservative scheduler keeps firing
    exactly what single-binding enumeration fired. Closes debt
    2026-07-09T2110Z (single-binding enumeration under-implements the
    per-binding guard skip).
    """

    P, Q, T, OUT = NetPath("p"), NetPath("q"), NetPath("t"), NetPath("out")
    A0, A1, B0, B1 = Token("X", {"n": 0}), Token("X", {"n": 1}), Token("Y", {"n": 0}), Token("Y", {"n": 1})

    def test_a_transition_is_enabled_under_every_admissible_selection(self):
        # Two tokens, one plain arc: two bindings for one transition — the
        # full candidate set is the scheduler's to choose from, and the FIFO
        # head stays first so bindings[0] is unchanged.
        net = Net(
            places=[Place(self.P), Place(self.OUT)],
            transitions=[Transition(self.T)],
            arcs=[Arc(self.P, self.T), Arc(self.T, self.OUT)],
        )
        enabled = candidates(net, Marking({self.P: (self.A0, self.A1)}))
        assert [b.consumed for b in enabled] == [((self.P, (self.A0,)),), ((self.P, (self.A1,)),)]

    def test_join_bindings_enumerate_input_arc_major_fifo_minor(self):
        # A join's alternatives cross-product in input-arc order: the first
        # arc's position is the major key. This ordering is what lets a
        # correlation guard pick the matching pair while the head pair stays
        # the default when no guard narrows.
        net = Net(
            places=[Place(self.P), Place(self.Q), Place(self.OUT)],
            transitions=[Transition(self.T)],
            arcs=[Arc(self.P, self.T, color="X"), Arc(self.Q, self.T, color="Y"), Arc(self.T, self.OUT)],
        )
        enabled = candidates(net, Marking({self.P: (self.A0, self.A1), self.Q: (self.B0, self.B1)}))
        assert [b.consumed for b in enabled] == [
            ((self.P, (self.A0,)), (self.Q, (self.B0,))),
            ((self.P, (self.A0,)), (self.Q, (self.B1,))),
            ((self.P, (self.A1,)), (self.Q, (self.B0,))),
            ((self.P, (self.A1,)), (self.Q, (self.B1,))),
        ]

    def test_a_weighted_arc_enumerates_admitted_combinations_in_order(self):
        # Weight w over n admitted tokens: the C(n, w) combinations, FIFO-
        # lexicographic, head combination (today's whole selection) first.
        net = Net(
            places=[Place(self.P), Place(self.OUT)],
            transitions=[Transition(self.T)],
            arcs=[Arc(self.P, self.T, weight=2), Arc(self.T, self.OUT)],
        )
        third = Token("X", {"n": 2})
        enabled = candidates(net, Marking({self.P: (self.A0, self.A1, third)}))
        assert [b.consumed for b in enabled] == [
            ((self.P, (self.A0, self.A1)),),
            ((self.P, (self.A0, third)),),
            ((self.P, (self.A1, third)),),
        ]


class TestSelection:
    """Direct unit tests of the pure per-arc selection: FIFO-first-match over admission — the HEAD selection, the first alternative candidate enumeration considers (deeper alternatives are enumeration's, not this function's)."""

    P, T = NetPath("p"), NetPath("t")
    X1, X2, X3, Y = Token("X", {"n": 1}), Token("X", {"n": 2}), Token("X", {"n": 3}), Token("Y", {"n": 9})

    def test_selects_the_first_weight_admitted_tokens_in_queue_order(self):
        arc = Arc(self.P, self.T, color="X", weight=2)
        assert selection(arc, (self.Y, self.X1, self.X2, self.X3), {}) == (self.X1, self.X2)

    def test_an_untyped_unfiltered_arc_degenerates_to_the_queue_front(self):
        arc = Arc(self.P, self.T)
        assert selection(arc, (self.Y, self.X1), {}) == (self.Y,)

    def test_admission_is_color_narrowed_by_filter(self):
        arc = Arc(self.P, self.T, color="X", filter="odd")
        filters = {"odd": lambda t: t.data["n"] % 2 == 1}
        assert selection(arc, (self.Y, self.X1, self.X2, self.X3), filters) == (self.X1,)

    def test_a_color_mismatch_never_reaches_the_filter(self):
        # Color narrows first; the filter sees only tokens of the declared
        # color, so a shape it cannot read on another color never warns.
        arc = Arc(self.P, self.T, color="X", filter="odd")
        filters = {"odd": lambda t: t.data["n"] % 2 == 1}
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert admitted(arc, Token("Y", None), filters) is False

    def test_a_raising_filter_means_not_admitted_plus_diagnostic(self):
        arc = Arc(self.P, self.T, filter="odd")
        filters = {"odd": lambda t: t.data["n"] % 2 == 1}
        with pytest.warns(FilterEvaluationWarning):
            assert admitted(arc, Token.black(), filters) is False


class TestOffer:
    """
    Direct unit tests of the per-arc offer — the arc's whole answer to a
    marking [glossary]: veto / satisfied-contributing-nothing / alternative
    selections with their timer anchors. The sum type is what _survey's
    cross product composes; the outcomes stop being control flow.
    """

    P, T = NetPath("p"), NetPath("t")
    X1, X2, X3 = Token("X", {"n": 1}), Token("X", {"n": 2}), Token("X", {"n": 3})

    def test_a_consume_arc_below_weight_vetoes(self):
        arc = Arc(self.P, self.T, color="X", weight=2)
        assert offer(arc, Marking({self.P: (self.X1,)}), {}) == Veto()

    def test_an_inhibit_arc_at_weight_vetoes(self):
        arc = Arc(self.P, self.T, mode=ArcMode.INHIBIT)
        assert offer(arc, Marking({self.P: (self.X1,)}), {}) == Veto()

    def test_an_inhibit_arc_below_weight_is_satisfied_contributing_nothing(self):
        arc = Arc(self.P, self.T, mode=ArcMode.INHIBIT, color="X")
        answer = offer(arc, Marking({self.P: (Token("Y"),)}), {})
        assert answer == Satisfied()

    def test_alternatives_enumerate_admitted_combinations_head_first(self):
        # FIFO-lexicographic over admitted positions: the head selection —
        # the first weight admitted tokens, front to back — is always the
        # first alternative enumerated.
        arc = Arc(self.P, self.T, color="X", weight=2)
        answer = offer(arc, Marking({self.P: (self.X1, Token("Y"), self.X2, self.X3)}), {})
        assert answer == Alternatives(
            arc,
            (
                Alternative((self.P, (self.X1, self.X2))),
                Alternative((self.P, (self.X1, self.X3))),
                Alternative((self.P, (self.X2, self.X3))),
            ),
        )

    def test_admission_is_color_narrowed_by_filter(self):
        arc = Arc(self.P, self.T, color="X", filter="odd")
        filters = {"odd": lambda t: t.data["n"] % 2 == 1}
        answer = offer(arc, Marking({self.P: (self.X1, self.X2, self.X3)}), filters)
        assert answer == Alternatives(arc, (Alternative((self.P, (self.X1,))), Alternative((self.P, (self.X3,)))))

    def test_anchors_ride_each_alternative_when_demanded(self):
        # The entry-instant threading's home: positions in the selection
        # index the place queue's recorded instants, and each alternative
        # carries its own anchors, position-aligned.
        arc = Arc(self.P, self.T, color="X")
        answer = offer(arc, Marking({self.P: (Token("Y"), self.X1, self.X2)}), {}, anchors={self.P: (0, 4, 9)})
        assert answer == Alternatives(
            arc,
            (Alternative((self.P, (self.X1,)), anchors=(4,)), Alternative((self.P, (self.X2,)), anchors=(9,))),
        )

    def test_no_anchor_demand_threads_no_instants(self):
        arc = Arc(self.P, self.T)
        answer = offer(arc, Marking({self.P: (self.X1,)}), {}, anchors=None)
        assert answer == Alternatives(arc, (Alternative((self.P, (self.X1,))),))

    def test_missing_or_misaligned_instants_fail_loud_when_demanded(self):
        # The selection reaches position 1; only one instant is recorded —
        # never a raw IndexError downstream.
        arc = Arc(self.P, self.T, color="X")
        with pytest.raises(ValueError, match="missing or misaligned"):
            offer(arc, Marking({self.P: (Token("Y"), self.X1)}), {}, anchors={self.P: (0,)})
