"""
Impetus-native tests for arc filters and colored input selection.

An input inscription narrows what an arc admits: a declared color admits its
color only (nominal match), and an optional filter — a pure single-token
boolean, spelled as a named symbol (``str``) or an inline CEL expression
(``Cel``) — narrows further [net-schema.md Inscriptions]. An arc's HEAD
selection is FIFO-first-match: scanning its place's queue front-to-back, the
first ``weight`` admitted tokens, so an untyped unfiltered arc degenerates to
the front of the queue (Navigator ruling); candidate enumeration considers
the deeper admitted combinations as further bindings, head first
(``test_enabledness.TestMultiBindingEnumeration``). Filters apply to every input
mode; an inhibit arc gates on the absence of a *matching* token. An inline CEL
expression sees the token's data fields as bare variables (``amount >= 100``);
color matching stays outside CEL, on the arc (Navigator ruling). A filter that
raises on a concrete token means that token is not admitted — uniformly across
modes, surfaced as a ``FilterEvaluationWarning``, never silently swallowed
[firing-semantics.md Enabledness; Navigator ruling: uniform error-means-false].
"""

from __future__ import annotations

# Pip imports
import pytest

# Internal imports
from petrus.impetus.petrinet import FilterEvaluationWarning, admitted
from petrus.impetus.history import (
    FiringBegun,
    FiringCompleted,
    TokensConsumed,
    TokensProduced,
    replay_marking,
)
from petrus.impetus.petrinet import Marking, Token
from petrus.impetus.instance import Instance
from petrus.impetus.petrinet import Arc, ArcMode, Cel, Net, NetPath, NetUri, Place, Transition

INVOICE = Token("Invoice", {"number": 7})
BIG = Token("Payment", {"amount": 150, "currency": "USD"})
SMALL = Token("Payment", {"amount": 40, "currency": "EUR"})


def is_big(token: Token) -> bool:
    return token.data["amount"] >= 100


class TestColoredConsumeSelection:
    """A typed consume arc selects by nominal color match, FIFO-first, not by queue front."""

    PENDING, CASH, OUT = NetPath("pending"), NetPath("cash"), NetPath("out")

    def instance(self, queue: tuple[Token, ...], weight: int = 1) -> Instance:
        net = Net(
            places=[Place(self.PENDING), Place(self.OUT)],
            transitions=[Transition(self.CASH)],
            arcs=[Arc(self.PENDING, self.CASH, weight=weight, color="Payment"), Arc(self.CASH, self.OUT)],
        )
        return Instance(net, Marking({self.PENDING: queue}))

    def test_selects_the_first_matching_token_not_the_queue_front(self):
        # The crux of the slice: an Invoice sits at the front, yet the typed
        # arc binds the Payment behind it -- selection is by admission, the
        # FIFO order only breaks ties among admitted tokens.
        [binding] = self.instance((INVOICE, BIG)).candidates()
        assert binding.consumed == ((self.PENDING, (BIG,)),)

    def test_no_matching_token_disables_the_transition(self):
        assert self.instance((INVOICE,)).enabled_transitions() == []

    def test_fire_consumes_the_selected_token_mid_queue(self):
        instance = self.instance((INVOICE, BIG))
        instance.step()
        assert instance.marking == Marking({self.PENDING: (INVOICE,), self.OUT: (BIG,)})

    def test_movement_records_carry_the_selected_token_and_replay(self):
        # The record contract ports to colored selection: consume precedes
        # produce, both carry the mid-queue token, and replaying the recorded
        # movements rebuilds the marking (mid-queue consumption must round-trip).
        instance = self.instance((INVOICE, BIG))
        firing = instance.step()
        assert firing.records == (
            FiringBegun(self.CASH, occurrence=1),
            TokensConsumed(self.PENDING, (BIG,), occurrence=1),
            TokensProduced(self.OUT, (BIG,), occurrence=1),
            FiringCompleted(self.CASH, occurrence=1),
        )
        assert firing.consumed == (BIG,)
        assert firing.produced == ((self.OUT, BIG),)
        assert replay_marking(instance.history) == instance.marking

    def test_weight_counts_admitted_tokens_only(self):
        # Weight 2 needs two Payments; a non-matching token between them
        # neither contributes nor blocks.
        other = Token("Payment", {"amount": 5, "currency": "USD"})
        enabled = self.instance((BIG, INVOICE, other), weight=2)
        assert [b.consumed for b in enabled.candidates()] == [((self.PENDING, (BIG, other)),)]
        assert self.instance((BIG, INVOICE), weight=2).enabled_transitions() == []


class TestNamedFilterSelection:
    """A named-symbol filter binds at the instance level and narrows selection per token."""

    PENDING, PAY, OUT = NetPath("pending"), NetPath("pay"), NetPath("out")

    def net(self) -> Net:
        return Net(
            places=[Place(self.PENDING), Place(self.OUT)],
            transitions=[Transition(self.PAY)],
            arcs=[Arc(self.PENDING, self.PAY, color="Payment", filter="is_big"), Arc(self.PAY, self.OUT)],
        )

    def test_filter_narrows_which_tokens_the_arc_admits(self):
        instance = Instance(self.net(), Marking({self.PENDING: (SMALL, BIG)}), filters={"is_big": is_big})
        instance.run()
        assert instance.marking == Marking({self.PENDING: (SMALL,), self.OUT: (BIG,)})

    def test_movement_records_carry_the_filter_selected_token_and_replay(self):
        # The record contract ports to filter selection: the filter-selected
        # mid-queue token is what consume and produce record, and replaying
        # the movements rebuilds the marking.
        instance = Instance(self.net(), Marking({self.PENDING: (SMALL, BIG)}), filters={"is_big": is_big})
        firing = instance.step()
        assert firing.records == (
            FiringBegun(self.PAY, occurrence=1),
            TokensConsumed(self.PENDING, (BIG,), occurrence=1),
            TokensProduced(self.OUT, (BIG,), occurrence=1),
            FiringCompleted(self.PAY, occurrence=1),
        )
        assert firing.consumed == (BIG,)
        assert firing.produced == ((self.OUT, BIG),)
        assert replay_marking(instance.history) == instance.marking

    def test_missing_filter_implementation_fails_at_construction(self):
        # Declared filter symbols are validated against the implementation
        # mapping before the instance can run -- never mid-selection.
        with pytest.raises(ValueError, match="is_big"):
            Instance(self.net(), Marking())

    def test_exact_filter_uris_bind_same_named_declarations_independently(self):
        p, t, out = self.PENDING, self.PAY, self.OUT
        net = Net(
            [Place(p), Place(out)],
            [Transition(t)],
            [Arc(p, t, filter="choice"), Arc(p, t, ArcMode.READ, filter="choice"), Arc(t, out)],
        )
        first, second = tuple(net.filter_declarations)
        instance = Instance(
            net,
            Marking({p: (SMALL, BIG)}),
            filters={first: lambda token: token is BIG, second: lambda token: token is SMALL},
        )

        [binding] = instance.candidates()
        assert binding.consumed == ((p, (BIG,)),)
        assert binding.read == ((p, (SMALL,)),)

    def test_bare_symbol_deliberately_shares_one_filter_implementation(self):
        p, t, out = self.PENDING, self.PAY, self.OUT
        net = Net(
            [Place(p), Place(out)],
            [Transition(t)],
            [Arc(p, t, filter="choice"), Arc(p, t, ArcMode.READ, filter="choice"), Arc(t, out)],
        )

        def shared(token):
            return token is BIG

        [binding] = Instance(net, Marking({p: (SMALL, BIG)}), filters={"choice": shared}).candidates()
        assert binding.consumed == binding.read == ((p, (BIG,)),)

    def test_exact_and_bare_filter_binding_is_ambiguous(self):
        net = self.net()
        [uri] = net.filter_declarations
        with pytest.raises(ValueError, match=r"both an exact implementation and local symbol 'is_big'"):
            Instance(net, Marking(), filters={"is_big": is_big, uri: is_big})


class TestReadAndInhibitFilters:
    """Filters apply to every input arc mode, not only consume."""

    CONFIG, PENDING, APPROVE, OUT = NetPath("config"), NetPath("pending"), NetPath("approve"), NetPath("out")
    USD_CONFIG = Token("Config", {"currency": "USD", "limit": 500})
    EUR_CONFIG = Token("Config", {"currency": "EUR", "limit": 100})

    def test_read_arc_filter_selects_the_matching_token_and_leaves_it_in_place(self):
        net = Net(
            places=[Place(self.CONFIG), Place(self.PENDING), Place(self.OUT)],
            transitions=[Transition(self.APPROVE)],
            arcs=[
                Arc(self.CONFIG, self.APPROVE, ArcMode.READ, filter="usd"),
                Arc(self.PENDING, self.APPROVE, ArcMode.CONSUME),
                Arc(self.APPROVE, self.OUT),
            ],
        )
        marking = Marking({self.CONFIG: (self.EUR_CONFIG, self.USD_CONFIG), self.PENDING: (BIG,)})
        instance = Instance(net, marking, filters={"usd": lambda t: t.data["currency"] == "USD"})
        [binding] = instance.candidates()
        assert binding.read == ((self.CONFIG, (self.USD_CONFIG,)),)
        instance.step()
        assert instance.marking.place(self.CONFIG) == (self.EUR_CONFIG, self.USD_CONFIG)

    def inhibited(self, blocker_queue: tuple[Token, ...]) -> Instance:
        blocker, trigger, gate, done = NetPath("blocker"), NetPath("trigger"), NetPath("gate"), NetPath("done")
        net = Net(
            places=[Place(blocker), Place(trigger), Place(done)],
            transitions=[Transition(gate)],
            arcs=[
                Arc(blocker, gate, ArcMode.INHIBIT, color="Alarm", filter="armed"),
                Arc(trigger, gate, ArcMode.CONSUME),
                Arc(gate, done),
            ],
        )
        marking = Marking({blocker: blocker_queue, trigger: (Token.black(),)})
        return Instance(net, marking, filters={"armed": lambda t: t.data["armed"]})

    def test_inhibit_gates_on_a_matching_token(self):
        assert self.inhibited((Token("Alarm", {"armed": True}),)).enabled_transitions() == []

    def test_inhibit_ignores_tokens_the_inscription_does_not_match(self):
        # A different color and an Alarm failing the filter both leave the
        # inhibitor satisfied: absence of a *matching* token, not emptiness.
        gate = [NetPath("gate")]
        assert self.inhibited((Token("Note", {"armed": True}),)).enabled_transitions() == gate
        assert self.inhibited((Token("Alarm", {"armed": False}),)).enabled_transitions() == gate

    def test_typed_place_resolves_color_before_evaluating_an_uncolored_filtered_arc(self):
        pending, pay, out = map(NetPath, ("pending", "pay", "out"))
        net = Net(
            places=[Place(pending, color="Payment"), Place(out)],
            transitions=[Transition(pay)],
            arcs=[Arc(pending, pay, filter="is_big"), Arc(pay, out)],
        )
        consulted = []
        filters = {"is_big": lambda token: consulted.append(token) or token.data["amount"] >= 100}
        [arc] = net.inputs(pay)

        assert admitted(arc, Token("Other", {"amount": 100}), filters) is False
        assert admitted(arc, BIG, filters) is True

        assert consulted == [BIG]


class TestCelFilterSelection:
    """An inline CEL filter sees the token's data fields as bare variables."""

    PENDING, PAY, OUT = NetPath("pending"), NetPath("pay"), NetPath("out")

    def instance(self, expression: str, queue: tuple[Token, ...], color: str | None = "Payment") -> Instance:
        net = Net(
            places=[Place(self.PENDING), Place(self.OUT)],
            transitions=[Transition(self.PAY)],
            arcs=[Arc(self.PENDING, self.PAY, color=color, filter=Cel(expression)), Arc(self.PAY, self.OUT)],
        )
        return Instance(net, Marking({self.PENDING: queue}))

    def test_cel_filter_selects_by_bare_data_fields(self):
        instance = self.instance("amount >= 100", (SMALL, BIG))
        instance.run()
        assert instance.marking == Marking({self.PENDING: (SMALL,), self.OUT: (BIG,)})

    def test_cel_selection_consumes_and_replays_like_any_other(self):
        # CEL is an encoding, not a separate pipeline: the selected token
        # flows through the same consume/produce records and replays.
        instance = self.instance("amount >= 100", (SMALL, BIG))
        firing = instance.step()
        assert firing.consumed == (BIG,)
        assert [r for r in firing.records if isinstance(r, TokensConsumed)] == [
            TokensConsumed(self.PENDING, (BIG,), occurrence=1)
        ]
        assert replay_marking(instance.history) == instance.marking

    def test_cel_composes_over_several_fields(self):
        instance = self.instance('amount >= 100 && currency == "USD"', (SMALL, BIG))
        [binding] = instance.candidates()
        assert binding.tokens == (BIG,)

    def test_invalid_cel_fails_at_construction_and_never_evaluates(self):
        # A syntactically invalid expression is a declared mismatch: an
        # instantiation-time error, not a per-token evaluation error.
        with pytest.raises(ValueError, match="CEL"):
            self.instance("amount >=", (BIG,))

    def test_exact_override_of_inline_cel_filter_is_refused(self):
        p, t, out = self.PENDING, self.PAY, self.OUT
        net = Net([Place(p), Place(out)], [Transition(t)], [Arc(p, t, filter=Cel("true")), Arc(t, out)])
        [uri] = net.filter_declarations
        with pytest.raises(ValueError, match=r"inline filter declaration .* already supplies"):
            Instance(net, Marking(), filters={uri: lambda token: True})

    def test_empty_cel_expression_is_rejected(self):
        with pytest.raises(ValueError, match="non-empty"):
            Cel("")

    def test_cel_error_on_a_concrete_token_skips_it_not_the_scan(self):
        # Permissive default: an untyped arc lets the black token reach the
        # filter, and a black token has no data fields, so evaluation errs.
        # That token is not admitted, the diagnostic is emitted, and the scan
        # still finds the Payment behind it -- an unreadable token masks
        # nothing. (A declared color would have excluded it before the filter.)
        instance = self.instance("amount >= 100", (Token.black(), BIG), color=None)
        with pytest.warns(FilterEvaluationWarning):
            [binding] = instance.candidates()
        assert binding.tokens == (BIG,)


class TestFilterEvaluationErrors:
    """A raising filter means the token is not admitted: skipped, surfaced, never swallowed."""

    PENDING, PAY, OUT = NetPath("pending"), NetPath("pay"), NetPath("out")

    def instance(self, queue: tuple[Token, ...]) -> Instance:
        net = Net(
            places=[Place(self.PENDING), Place(self.OUT)],
            transitions=[Transition(self.PAY)],
            arcs=[Arc(self.PENDING, self.PAY, filter="is_big"), Arc(self.PAY, self.OUT)],
        )
        return Instance(net, Marking({self.PENDING: queue}), filters={"is_big": is_big})

    def test_the_diagnostic_carries_filter_arc_token_and_error(self):
        # The ruled diagnostic payload is (expression, token, error), plus the
        # arc as the expression's address: the token is what distinguishes a
        # typo'd filter from a healthy false.
        with pytest.warns(FilterEvaluationWarning, match=r"is_big.*pending.*pay.*TypeError.*Token\.black\(\)"):
            self.instance((Token.black(),)).enabled_transitions()

    def test_an_unreadable_token_does_not_mask_a_later_match(self):
        instance = self.instance((Token.black(), BIG))
        with pytest.warns(FilterEvaluationWarning):
            [binding] = instance.candidates()
        assert binding.consumed == ((self.PENDING, (BIG,)),)

    def test_parallel_filter_warning_names_the_exact_occurrence_and_scan_continues(self):
        p, t, out = self.PENDING, self.PAY, self.OUT
        net = Net(
            [Place(p), Place(out)],
            [Transition(t)],
            [Arc(p, t, filter="first"), Arc(p, t, ArcMode.READ, filter="second"), Arc(t, out)],
        )
        first, second = tuple(net.filter_declarations)
        assert first == NetUri("arc:/pending->/pay#filter:$0")
        assert second == NetUri("arc:/pending->/pay#filter:$1")

        def raising(token):
            return token.data["amount"] > 0

        instance = Instance(net, Marking({p: (Token.black(), BIG)}), filters={first: raising, second: raising})

        with pytest.warns(FilterEvaluationWarning) as warnings:
            [binding] = instance.candidates()
        assert {"#filter:$0", "#filter:$1"} <= {
            marker for warning in warnings for marker in ("#filter:$0", "#filter:$1") if marker in str(warning.message)
        }
        assert binding.consumed == binding.read == ((p, (BIG,)),)

    def test_inhibit_filter_error_means_no_match_and_does_not_block(self):
        # Navigator ruling: error-means-false uniformly across modes. On an
        # inhibit arc an unreadable token does not gate the transition out;
        # the mandatory diagnostic is the safety net.
        blocker, trigger, gate, done = NetPath("blocker"), NetPath("trigger"), NetPath("gate"), NetPath("done")
        net = Net(
            places=[Place(blocker), Place(trigger), Place(done)],
            transitions=[Transition(gate)],
            arcs=[
                Arc(blocker, gate, ArcMode.INHIBIT, filter="is_big"),
                Arc(trigger, gate, ArcMode.CONSUME),
                Arc(gate, done),
            ],
        )
        marking = Marking({blocker: (Token.black(),), trigger: (Token.black(),)})
        instance = Instance(net, marking, filters={"is_big": is_big})
        with pytest.warns(FilterEvaluationWarning):
            assert instance.enabled_transitions() == [gate]


class TestFilterValidation:
    """The schema rejects filter spellings it cannot honor."""

    def test_filter_on_an_output_arc_is_rejected(self):
        # A filter is an input inscription; on an output arc it would be
        # silently ignored surface, so the net refuses it at build.
        p, t = NetPath("p"), NetPath("t")
        with pytest.raises(ValueError, match="output arc"):
            Net(places=[Place(p)], transitions=[Transition(t)], arcs=[Arc(p, t), Arc(t, p, filter="is_big")])

    def test_a_non_symbol_non_cel_filter_is_rejected_at_construction(self):
        # The arc accepts the two declared encodings only; anything else
        # fails as a declared mismatch, not as the CEL adapter's internals.
        with pytest.raises(ValueError, match="symbol name or an inline Cel"):
            Arc(NetPath("p"), NetPath("t"), filter=is_big)

    def test_enabledness_with_filters_leaves_the_marking_untouched(self):
        # Filters constrain selection; they never consume. Enabledness stays
        # a pure function of net, marking, and implementations.
        p, t, out = NetPath("p"), NetPath("t"), NetPath("out")
        net = Net(
            places=[Place(p), Place(out)],
            transitions=[Transition(t)],
            arcs=[Arc(p, t, filter="is_big"), Arc(t, out)],
        )
        instance = Instance(net, Marking({p: (SMALL, BIG)}), filters={"is_big": is_big})
        instance.enabled_transitions()
        assert instance.marking == Marking({p: (SMALL, BIG)})
