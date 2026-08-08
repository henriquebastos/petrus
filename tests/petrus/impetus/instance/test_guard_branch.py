"""
Impetus-native tests for guards.

A guard is a pure boolean over the full firing binding, evaluated on peeked
(unconsumed) tokens during candidate computation: selections are enumerated from
arcs first, then the assembled bindings are filtered by guards
[firing-semantics.md Enabledness]. A transition may declare multiple guards;
they compose as conjunction [handler-contract.md Symbols]. Implementations bind
to declared symbols through a mapping validated before the instance can run
[handler-contract.md Symbols]. A guard that raises on a concrete token makes
that binding not satisfied — skipped deterministically and surfaced as a
diagnostic, never silently swallowed [firing-semantics.md Enabledness]; the
Navigator ruled the diagnostic channel is a ``GuardEvaluationWarning``.

``TestGuardBranch`` mirrors the ``guard_branch`` golden fixture inline:
complementary deterministic guards routing Payment tokens on their data.
"""

from __future__ import annotations

# Pip imports
import pytest

# Internal imports
from petrus.impetus.petrinet import Binding, GuardEvaluationWarning
from petrus.impetus.petrinet import Marking, Token
from petrus.impetus.instance import Instance
from petrus.impetus.petrinet import ANONYMOUS, Arc, ArcMode, Net, NetPath, Place, Transition


def amount_gte_100(binding: Binding) -> bool:
    return binding.peeked[0].data["amount"] >= 100


def amount_lt_100(binding: Binding) -> bool:
    return binding.peeked[0].data["amount"] < 100


class TestGuardDeclarationBindings:
    PENDING, LEFT, RIGHT = map(NetPath, ("pending", "left", "right"))

    def net(self, *, anonymous: bool = False) -> Net:
        declaration = ANONYMOUS if anonymous else "shared"
        return Net(
            places=[Place(self.PENDING)],
            transitions=[
                Transition(self.LEFT, guards=(declaration,)),
                Transition(self.RIGHT, guards=(declaration,)),
            ],
            arcs=[Arc(self.PENDING, self.LEFT), Arc(self.PENDING, self.RIGHT)],
        )

    def test_exact_declaration_uris_bind_same_named_guards_independently(self):
        net = self.net()
        instance = Instance(
            net,
            Marking({self.PENDING: (Token.black(),)}),
            guards={
                net.guard_uris(self.LEFT)[0]: lambda binding: True,
                net.guard_uris(self.RIGHT)[0]: lambda binding: False,
            },
        )

        assert [binding.transition for binding in instance.candidates()] == [self.LEFT]

    def test_local_symbol_deliberately_shares_one_guard(self):
        instance = Instance(
            self.net(),
            Marking({self.PENDING: (Token.black(),)}),
            guards={"shared": lambda binding: True},
        )

        assert [binding.transition for binding in instance.candidates()] == [self.LEFT, self.RIGHT]

    def test_exact_and_local_binding_for_one_guard_is_ambiguous(self):
        net = self.net()
        with pytest.raises(ValueError, match="both an exact implementation and local symbol 'shared'"):
            Instance(net, guards={"shared": lambda binding: True, net.guard_uris(self.LEFT)[0]: lambda binding: False})

    def test_anonymous_guard_requires_its_exact_declaration_uri(self):
        net = self.net(anonymous=True)
        with pytest.raises(ValueError, match=r"transition:/left#guard:\$0"):
            Instance(net, guards={})


class TestGuardBranch:
    """Two transitions compete for one place with complementary guards over token data."""

    PENDING, ACCEPT, REJECT = NetPath("pending"), NetPath("accept"), NetPath("reject")
    ACCEPTED, REJECTED = NetPath("accepted"), NetPath("rejected")
    BIG = Token("Payment", {"amount": 150, "currency": "USD"})
    SMALL = Token("Payment", {"amount": 40, "currency": "USD"})
    GUARDS = {"amount_gte_100": amount_gte_100, "amount_lt_100": amount_lt_100}

    def net(self) -> Net:
        return Net(
            places=[Place(self.PENDING), Place(self.ACCEPTED), Place(self.REJECTED)],
            transitions=[
                Transition(self.ACCEPT, guards=("amount_gte_100",)),
                Transition(self.REJECT, guards=("amount_lt_100",)),
            ],
            arcs=[
                Arc(self.PENDING, self.ACCEPT),
                Arc(self.PENDING, self.REJECT),
                Arc(self.ACCEPT, self.ACCEPTED),
                Arc(self.REJECT, self.REJECTED),
            ],
        )

    def seeded(self) -> Instance:
        return Instance(self.net(), Marking({self.PENDING: (self.BIG, self.SMALL)}), guards=self.GUARDS)

    def test_a_guard_failed_head_does_not_mask_a_deeper_admissible_selection(self):
        # The per-binding guard skip, whole [debt 2026-07-09T2110Z paid]:
        # reject's guard fails the FIFO head (150), but the small token deeper
        # in the queue satisfies it under another binding — the transition is
        # enabled under that selection, never disabled by the head alone.
        enabled = self.seeded().candidates()
        assert [(b.transition, b.tokens) for b in enabled] == [
            (self.ACCEPT, (self.BIG,)),
            (self.REJECT, (self.SMALL,)),
        ]

    def test_each_token_routes_by_its_own_guard(self):
        # The fixture walk end-to-end: 150 routes to accepted, then 40 to rejected.
        instance = self.seeded()
        instance.run()
        assert instance.marking == Marking({self.ACCEPTED: (self.BIG,), self.REJECTED: (self.SMALL,)})

    def test_missing_guard_implementation_fails_at_construction(self):
        # Declared symbols are validated against the implementation mapping
        # before the instance can run -- never mid-firing.
        with pytest.raises(ValueError, match="amount_lt_100"):
            Instance(self.net(), Marking(), guards={"amount_gte_100": amount_gte_100})


class TestGuardsSeeTheFullBinding:
    """Cross-token correlation lives in guards: a guard reads consumed and read selections together."""

    CONFIG, PENDING, APPROVE, OUT = NetPath("config"), NetPath("pending"), NetPath("approve"), NetPath("out")
    PAYMENT = Token("Payment", {"amount": 150})

    @staticmethod
    def within_limit(binding: Binding) -> bool:
        [(_, (config,))] = binding.read
        [payment] = binding.tokens
        return payment.data["amount"] <= config.data["limit"]

    def instance(self, limit: int) -> Instance:
        net = Net(
            places=[Place(self.CONFIG), Place(self.PENDING), Place(self.OUT)],
            transitions=[Transition(self.APPROVE, guards=("within_limit",))],
            arcs=[
                Arc(self.CONFIG, self.APPROVE, ArcMode.READ),
                Arc(self.PENDING, self.APPROVE, ArcMode.CONSUME),
                Arc(self.APPROVE, self.OUT),
            ],
        )
        marking = Marking({self.CONFIG: (Token("Config", {"limit": limit}),), self.PENDING: (self.PAYMENT,)})
        return Instance(net, marking, guards={"within_limit": self.within_limit})

    def test_guard_correlates_consumed_and_read_tokens(self):
        assert self.instance(limit=200).enabled_transitions() == [self.APPROVE]
        assert self.instance(limit=100).enabled_transitions() == []

    def test_peeked_is_consumed_then_read_selections(self):
        # The ordering is contract: a guard indexing into peeked relies on
        # consumed selections coming first, read selections after.
        [binding] = self.instance(limit=200).candidates()
        assert binding.peeked == (self.PAYMENT, Token("Config", {"limit": 200}))


class TestGuardComposition:
    """Multiple declared guards compose as conjunction; order is irrelevant because guards are pure."""

    P, T, OUT = NetPath("p"), NetPath("t"), NetPath("out")

    def instance(self, **guards) -> Instance:
        net = Net(
            places=[Place(self.P), Place(self.OUT)],
            transitions=[Transition(self.T, guards=tuple(guards))],
            arcs=[Arc(self.P, self.T), Arc(self.T, self.OUT)],
        )
        return Instance(net, Marking({self.P: (Token("X"),)}), guards=guards)

    def test_all_guards_must_hold(self):
        truthy, falsy = (lambda b: True), (lambda b: False)
        assert self.instance(a=truthy, b=truthy).enabled_transitions() == [self.T]
        assert self.instance(a=truthy, b=falsy).enabled_transitions() == []


class TestGuardEvaluationErrors:
    """A raising guard means the binding is not satisfied: skipped, surfaced, never swallowed."""

    P, Q, GUARDED, PLAIN, OUT = NetPath("p"), NetPath("q"), NetPath("guarded"), NetPath("plain"), NetPath("out")

    def instance(self) -> Instance:
        # `guarded` peeks a black token (data None), so the guard raises TypeError;
        # `plain` shares no guard and must stay enabled.
        net = Net(
            places=[Place(self.P), Place(self.Q), Place(self.OUT)],
            transitions=[Transition(self.GUARDED, guards=("needs_amount",)), Transition(self.PLAIN)],
            arcs=[
                Arc(self.P, self.GUARDED),
                Arc(self.Q, self.PLAIN),
                Arc(self.GUARDED, self.OUT),
                Arc(self.PLAIN, self.OUT),
            ],
        )
        marking = Marking({self.P: (Token.black(),), self.Q: (Token.black(),)})
        return Instance(net, marking, guards={"needs_amount": lambda b: b.peeked[0].data["amount"] >= 100})

    def test_raising_guard_skips_the_binding_and_enablement_continues(self):
        instance = self.instance()
        with pytest.warns(GuardEvaluationWarning):
            assert instance.enabled_transitions() == [self.PLAIN]

    def test_an_unreadable_token_does_not_mask_a_deeper_valid_binding(self):
        # The ruled sentence itself [DR 2026-07-08 guard-filter-evaluation-
        # errors]: "one unreadable token must not mask other valid bindings of
        # the same transition". The black head raises (skipped, surfaced); the
        # Payment behind it satisfies the guard, and that binding enables.
        payment = Token("Payment", {"amount": 150})
        net = Net(
            places=[Place(self.P), Place(self.OUT)],
            transitions=[Transition(self.GUARDED, guards=("needs_amount",))],
            arcs=[Arc(self.P, self.GUARDED), Arc(self.GUARDED, self.OUT)],
        )
        instance = Instance(
            net,
            Marking({self.P: (Token.black(), payment)}),
            guards={"needs_amount": lambda b: b.peeked[0].data["amount"] >= 100},
        )
        with pytest.warns(GuardEvaluationWarning):
            [binding] = instance.candidates()
        assert binding.tokens == (payment,)

    def test_the_diagnostic_carries_guard_transition_error_and_token(self):
        # The ruled diagnostic payload is (expression, token, error): the token
        # is what distinguishes a typo'd guard from a healthy false.
        with pytest.warns(GuardEvaluationWarning, match=r"needs_amount.*guarded.*TypeError.*Token\.black\(\)"):
            self.instance().enabled_transitions()
