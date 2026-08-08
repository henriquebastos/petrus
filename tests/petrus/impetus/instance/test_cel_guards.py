"""
Impetus-native tests for inline CEL guards.

A guard declares with the same pure expression tier as arc filters and the
completion condition: an inline CEL expression or a named symbol
[firing-semantics.md Enabledness, DR 2026-07-07
arc-filters-and-guards-cel-or-named-both-pure]. The Navigator ruled the guard
CEL environment place-keyed and completion-shaped: each consume/read input
place of the declaring transition is a bare variable bound to the binding's
selected tokens from that place, each token a ``{color, data}`` map — and only
those places resolve; an inhibit-only or foreign place reference is a declared
mismatch caught at construction. Evaluation keeps the slice-3 semantics:
conjunction, short-circuit, and a raising guard skipping the binding with a
``GuardEvaluationWarning`` [DR 2026-07-08 guard-filter-evaluation-errors].
"""

from __future__ import annotations

# Pip imports
import pytest

# Internal imports
from petrus.impetus.petrinet import GuardEvaluationWarning
from petrus.impetus.petrinet import Marking, Token
from petrus.impetus.instance import Instance
from petrus.impetus.petrinet import Arc, ArcMode, Cel, Net, NetPath, Place, Transition


class TestCelGuardRouting:
    """The guard_branch shape with inline CEL: complementary expressions routing Payment tokens on their data."""

    PENDING, ACCEPT, REJECT = NetPath("pending"), NetPath("accept"), NetPath("reject")
    ACCEPTED, REJECTED = NetPath("accepted"), NetPath("rejected")
    BIG = Token("Payment", {"amount": 150, "currency": "USD"})
    SMALL = Token("Payment", {"amount": 40, "currency": "USD"})

    def net(self) -> Net:
        return Net(
            places=[Place(self.PENDING), Place(self.ACCEPTED), Place(self.REJECTED)],
            transitions=[
                Transition(self.ACCEPT, guards=(Cel("pending[0].data.amount >= 100"),)),
                Transition(self.REJECT, guards=(Cel("pending[0].data.amount < 100"),)),
            ],
            arcs=[
                Arc(self.PENDING, self.ACCEPT),
                Arc(self.PENDING, self.REJECT),
                Arc(self.ACCEPT, self.ACCEPTED),
                Arc(self.REJECT, self.REJECTED),
            ],
        )

    def seeded(self) -> Instance:
        # No guards mapping: inline CEL binds by compilation, not by symbol.
        return Instance(self.net(), Marking({self.PENDING: (self.BIG, self.SMALL)}))

    def test_a_cel_guard_failed_head_does_not_mask_a_deeper_admissible_selection(self):
        # The named-guard flagship's inline twin [debt 2026-07-09T2110Z paid]:
        # reject's expression fails the FIFO head (150), but the small token
        # deeper in the queue satisfies it under another binding — enabled
        # under that selection, never disabled by the head alone.
        enabled = self.seeded().candidates()
        assert [(b.transition, b.tokens) for b in enabled] == [
            (self.ACCEPT, (self.BIG,)),
            (self.REJECT, (self.SMALL,)),
        ]

    def test_each_token_routes_by_its_own_cel_guard(self):
        instance = self.seeded()
        instance.run()
        assert instance.marking == Marking({self.ACCEPTED: (self.BIG,), self.REJECTED: (self.SMALL,)})


class TestCelGuardCorrelation:
    """Cross-token correlation reads by place name: consumed and read selections under their places."""

    CONFIG, PENDING, APPROVE, OUT = NetPath("config"), NetPath("pending"), NetPath("approve"), NetPath("out")
    PAYMENT = Token("Payment", {"amount": 150})

    def instance(self, limit: int) -> Instance:
        net = Net(
            places=[Place(self.CONFIG), Place(self.PENDING), Place(self.OUT)],
            transitions=[Transition(self.APPROVE, guards=(Cel("pending[0].data.amount <= config[0].data.limit"),))],
            arcs=[
                Arc(self.CONFIG, self.APPROVE, ArcMode.READ),
                Arc(self.PENDING, self.APPROVE, ArcMode.CONSUME),
                Arc(self.APPROVE, self.OUT),
            ],
        )
        marking = Marking({self.CONFIG: (Token("Config", {"limit": limit}),), self.PENDING: (self.PAYMENT,)})
        return Instance(net, marking)

    def test_cel_guard_correlates_consumed_and_read_tokens(self):
        assert self.instance(limit=200).enabled_transitions() == [self.APPROVE]
        assert self.instance(limit=100).enabled_transitions() == []


class TestMixedGuards:
    """Named symbols and inline CEL compose in one conjunction; each element binds by its own encoding."""

    P, T, OUT = NetPath("p"), NetPath("t"), NetPath("out")

    def instance(self, *expressions: str, **named) -> Instance:
        net = Net(
            places=[Place(self.P), Place(self.OUT)],
            transitions=[Transition(self.T, guards=(*named, *(Cel(e) for e in expressions)))],
            arcs=[Arc(self.P, self.T), Arc(self.T, self.OUT)],
        )
        return Instance(net, Marking({self.P: (Token("X", {"n": 7}),)}), guards=named)

    def test_named_and_cel_guards_compose_as_conjunction(self):
        truthy, falsy = (lambda b: True), (lambda b: False)
        assert self.instance("p[0].data.n > 0", check=truthy).enabled_transitions() == [self.T]
        assert self.instance("p[0].data.n > 9", check=truthy).enabled_transitions() == []
        assert self.instance("p[0].data.n > 0", check=falsy).enabled_transitions() == []

    def test_two_cel_guards_compose_as_conjunction(self):
        # The all-inline sibling of TestGuardComposition.test_all_guards_must_hold.
        assert self.instance("p[0].data.n > 0", "p[0].data.n < 9").enabled_transitions() == [self.T]
        assert self.instance("p[0].data.n > 0", "p[0].data.n > 9").enabled_transitions() == []

    def test_transitions_sharing_an_expression_share_one_sound_implementation(self):
        # Two transitions consuming the same place declare an equal Cel: one
        # mapping key, one compiled program — sound because the compiled
        # guard reads the binding by place name, not a captured scope. Both
        # must enable off their own bindings.
        net = Net(
            places=[Place(self.P), Place(self.OUT)],
            transitions=[
                Transition(self.T, guards=(Cel("p[0].data.n > 0"),)),
                Transition(NetPath("t2"), guards=(Cel("p[0].data.n > 0"),)),
            ],
            arcs=[Arc(self.P, self.T), Arc(self.T, self.OUT), Arc(self.P, NetPath("t2")), Arc(NetPath("t2"), self.OUT)],
        )
        instance = Instance(net, Marking({self.P: (Token("X", {"n": 7}),)}))
        assert instance.enabled_transitions() == [self.T, NetPath("t2")]


class TestCelGuardValidation:
    """Declared mismatches fail fast at construction and never evaluate."""

    P, Q, T, OUT = NetPath("p"), NetPath("q"), NetPath("t"), NetPath("out")

    def net(self, expression: str, q_mode: ArcMode | None = None) -> Net:
        arcs = [Arc(self.P, self.T), Arc(self.T, self.OUT)]
        if q_mode is not None:
            arcs.append(Arc(self.Q, self.T, q_mode))
        return Net(
            places=[Place(self.P), Place(self.Q), Place(self.OUT)],
            transitions=[Transition(self.T, guards=(Cel(expression),))],
            arcs=arcs,
        )

    def test_invalid_cel_fails_at_construction_and_never_evaluates(self):
        with pytest.raises(ValueError, match="invalid CEL"):
            Instance(self.net("p[0].data.amount >="), Marking())

    def test_a_place_not_feeding_the_transition_fails_at_construction(self):
        # `out` is a net place, but not among the transition's inputs: the
        # guard sees the binding, never the wider marking. The rejection
        # names the declaring transition, its scope, and the stray name.
        with pytest.raises(ValueError, match=r"on transition t .*\['p'\]: \['out'\]"):
            Instance(self.net("size(out) == 0"), Marking())

    def test_an_inhibit_only_place_is_outside_the_guard_scope(self):
        # An inhibit arc's satisfaction contributes no tokens to the binding,
        # so its place resolves to nothing a guard could read (Navigator
        # ruling: consume/read input places only).
        with pytest.raises(ValueError, match=r": \['q'\]"):
            Instance(self.net("size(q) == 0", q_mode=ArcMode.INHIBIT), Marking())

    def test_a_shared_expression_is_validated_against_each_declaring_transitions_scope(self):
        # Equal Cel declarations are one mapping key (frozen dataclass), so a
        # dedup refactor that compiled each unique expression once would skip
        # the second transition's scope check. Pin the per-declaration loop:
        # the same expression valid on `t` (consumes p) must still be rejected
        # for `t2` (consumes q).
        net = Net(
            places=[Place(self.P), Place(self.Q), Place(self.OUT)],
            transitions=[
                Transition(self.T, guards=(Cel("p[0].color == null"),)),
                Transition(NetPath("t2"), guards=(Cel("p[0].color == null"),)),
            ],
            arcs=[Arc(self.P, self.T), Arc(self.T, self.OUT), Arc(self.Q, NetPath("t2")), Arc(NetPath("t2"), self.OUT)],
        )
        with pytest.raises(ValueError, match=r"on transition t2 .*\['q'\]: \['p'\]"):
            Instance(net, Marking())

    def test_a_read_place_is_inside_the_guard_scope(self):
        Instance(self.net("q[0].color == null", q_mode=ArcMode.READ), Marking())

    def test_macro_bound_variables_are_not_place_references(self):
        Instance(self.net("p.all(t, t.data.n > 0)"), Marking())

    def test_a_non_symbol_non_cel_guard_is_rejected_at_declaration(self):
        # The two declared encodings only; anything else would surface later
        # as the CEL adapter's internal error instead of a declared mismatch.
        with pytest.raises(ValueError, match="guard"):
            Transition(self.T, guards=(42,))


class TestCelGuardEvaluationErrors:
    """A raising CEL guard means the binding is not satisfied: skipped, surfaced, never swallowed."""

    P, Q, GUARDED, PLAIN, OUT = NetPath("p"), NetPath("q"), NetPath("guarded"), NetPath("plain"), NetPath("out")

    def instance(self) -> Instance:
        # `guarded` peeks a black token (data null), so reading a data field
        # raises inside CEL; `plain` shares no guard and must stay enabled.
        net = Net(
            places=[Place(self.P), Place(self.Q), Place(self.OUT)],
            transitions=[
                Transition(self.GUARDED, guards=(Cel("p[0].data.amount >= 100"),)),
                Transition(self.PLAIN),
            ],
            arcs=[
                Arc(self.P, self.GUARDED),
                Arc(self.Q, self.PLAIN),
                Arc(self.GUARDED, self.OUT),
                Arc(self.PLAIN, self.OUT),
            ],
        )
        marking = Marking({self.P: (Token.black(),), self.Q: (Token.black(),)})
        return Instance(net, marking)

    def test_a_raising_cel_guard_skips_the_binding_and_enablement_continues(self):
        instance = self.instance()
        with pytest.warns(GuardEvaluationWarning):
            assert instance.enabled_transitions() == [self.PLAIN]

    def test_the_diagnostic_carries_expression_transition_error_and_tokens(self):
        # The ruled diagnostic payload is (expression, token, error), on the
        # same channel as named guards; the error class is the field that
        # distinguishes a typo'd expression from a healthy false.
        with pytest.warns(
            GuardEvaluationWarning, match=r"p\[0\]\.data\.amount.*guarded.*CELEvalError.*Token\.black\(\)"
        ):
            self.instance().enabled_transitions()
