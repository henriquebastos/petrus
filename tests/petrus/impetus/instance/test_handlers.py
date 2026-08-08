"""
Impetus-native tests for handlers.

A handler is the callable bound to a transition: it receives the firing
binding and the transition's output arcs, and returns output tokens keyed by
destination [handler-contract.md The handler contract, firing-semantics.md
Token production]. Handler symbols bind to implementations through the same
fail-fast-validated mapping as guards [handler-contract.md Symbols]. Each
output arc's inscription is a routing contract: the runtime deposits only
handler tokens whose color and destination match an output arc — the Navigator
ruled that unmatched handler tokens are dropped silently (the validation run
and the type layer own declaration typos, not end firing). A transition with
no handler symbol is default-bound to the pure color-routed ``passthrough`` —
a default binding, not an engine special case [firing-semantics.md Default
behavior].

``TestHandlerTokens`` mirrors the ``handler_tokens`` fixture net inline, under
Impetus semantics: the oracle merges the handler result with the consumed
tokens (its merged-token outlier); Impetus deposits exactly the
handler-supplied Receipt [DR output-production-per-arc-contract].
"""

from __future__ import annotations

# Pip imports
import pytest

# Internal imports
from petrus.impetus.petrinet import Binding
from petrus.impetus.history import (
    FiringBegun,
    FiringCompleted,
    TokensConsumed,
    TokensProduced,
    replay_marking,
)
from petrus.impetus.petrinet import Marking, Token
from petrus.impetus.instance import Instance
from petrus.impetus.petrinet import ANONYMOUS, Arc, ArcMode, Net, NetPath, Place, Transition


def price_order(binding: Binding, outputs) -> dict:
    [order] = binding.tokens
    total = order.data["qty"] * order.data["unit_price"]
    return {"receipt_out": (Token("Receipt", {"total": total, "currency": "USD"}),)}


def first_handler(binding: Binding, outputs) -> dict:
    return {}


def second_handler(binding: Binding, outputs) -> dict:
    return {}


class TestHandlerDeclarationBindings:
    LEFT, RIGHT = NetPath("left"), NetPath("right")

    def net(self, *, anonymous: bool = False) -> Net:
        declaration = ANONYMOUS if anonymous else "shared"
        return Net(
            places=[],
            transitions=[Transition(self.LEFT, handler=declaration), Transition(self.RIGHT, handler=declaration)],
            arcs=[],
        )

    def test_exact_declaration_uris_bind_same_named_handlers_independently(self):
        net = self.net()
        instance = Instance(
            net,
            handlers={net.handler_uri(self.LEFT): first_handler, net.handler_uri(self.RIGHT): second_handler},
        )

        assert instance.bound_handler(self.LEFT) is first_handler
        assert instance.bound_handler(self.RIGHT) is second_handler

    def test_local_symbol_deliberately_shares_one_handler(self):
        instance = Instance(self.net(), handlers={"shared": first_handler})

        assert instance.bound_handler(self.LEFT) is first_handler
        assert instance.bound_handler(self.RIGHT) is first_handler

    def test_exact_and_local_binding_for_one_handler_is_ambiguous(self):
        net = self.net()
        with pytest.raises(ValueError, match="both an exact implementation and local symbol 'shared'"):
            Instance(net, handlers={"shared": first_handler, net.handler_uri(self.LEFT): second_handler})

    def test_anonymous_handler_requires_its_exact_declaration_uri(self):
        net = self.net(anonymous=True)
        with pytest.raises(ValueError, match=r"transition:/left#handler"):
            Instance(net, handlers={})

        instance = Instance(
            net,
            handlers={net.handler_uri(self.LEFT): first_handler, net.handler_uri(self.RIGHT): second_handler},
        )
        assert instance.bound_handler(self.LEFT) is first_handler


class TestHandlerTokens:
    """The handler supplies the output tokens; the runtime deposits them, not the consumed input."""

    ORDER_IN, PRICE, RECEIPT_OUT = NetPath("order_in"), NetPath("price"), NetPath("receipt_out")
    ORDER = Token("Order", {"sku": "widget", "qty": 3, "unit_price": 25})
    RECEIPT = Token("Receipt", {"total": 75, "currency": "USD"})

    def net(self) -> Net:
        return Net(
            places=[Place(self.ORDER_IN), Place(self.RECEIPT_OUT)],
            transitions=[Transition(self.PRICE, handler="price_order")],
            arcs=[Arc(self.ORDER_IN, self.PRICE), Arc(self.PRICE, self.RECEIPT_OUT)],
        )

    def seeded(self) -> Instance:
        marking = Marking({self.ORDER_IN: (self.ORDER,)})
        return Instance(self.net(), marking, handlers={"price_order": price_order})

    def test_handler_supplied_token_is_deposited_not_the_consumed_one(self):
        # The oracle merges Order + Receipt into one token here; Impetus deposits
        # exactly what the handler supplied for the destination.
        instance = self.seeded()
        instance.run()
        assert instance.marking == Marking({self.RECEIPT_OUT: (self.RECEIPT,)})

    def test_firing_reports_consumed_input_and_handler_output(self):
        [firing] = self.seeded().run()
        assert firing.consumed == (self.ORDER,)
        assert firing.produced == ((self.RECEIPT_OUT, self.RECEIPT),)

    def test_handler_firing_records_movements_in_lifecycle_order(self):
        # replay_marking depends on consume records preceding produce records
        # on the handler path exactly as on the passthrough path. A plain
        # callable bound to a symbol is a pure deterministic projection
        # [DR 2026-07-14 source-delivery-projection-and-identity]: its firing
        # carries no activity records — those belong to ActivityHandler
        # transitions alone.
        [firing] = self.seeded().run()
        assert firing.records == (
            FiringBegun(self.PRICE, occurrence=1),
            TokensConsumed(self.ORDER_IN, (self.ORDER,), occurrence=1),
            TokensProduced(self.RECEIPT_OUT, (self.RECEIPT,), occurrence=1),
            FiringCompleted(self.PRICE, occurrence=1),
        )

    def test_history_replays_handler_supplied_tokens(self):
        # Handler results are recorded as explicit movements: replay re-applies
        # them and never re-runs the handler.
        instance = self.seeded()
        instance.run()
        assert replay_marking(instance.history) == instance.marking

    def test_missing_handler_implementation_fails_at_construction(self):
        with pytest.raises(ValueError, match="price_order"):
            Instance(self.net(), Marking(), handlers={})


class TestHandlerSeesTheFullBinding:
    """A handler reads consumed and read selections together, like a guard."""

    CONFIG, PENDING, CHARGE, OUT = NetPath("config"), NetPath("pending"), NetPath("charge"), NetPath("out")

    @staticmethod
    def apply_fee(binding: Binding, outputs) -> dict:
        [(_, (config,))] = binding.read
        [payment] = binding.tokens
        amount = payment.data["amount"] + config.data["fee"]
        return {NetPath("out"): (Token("Charged", {"amount": amount}),)}

    def test_handler_correlates_consumed_and_read_tokens(self):
        net = Net(
            places=[Place(self.CONFIG), Place(self.PENDING), Place(self.OUT)],
            transitions=[Transition(self.CHARGE, handler="apply_fee")],
            arcs=[
                Arc(self.CONFIG, self.CHARGE, ArcMode.READ),
                Arc(self.PENDING, self.CHARGE, ArcMode.CONSUME),
                Arc(self.CHARGE, self.OUT),
            ],
        )
        marking = Marking(
            {self.CONFIG: (Token("Config", {"fee": 5}),), self.PENDING: (Token("Payment", {"amount": 100}),)}
        )
        instance = Instance(net, marking, handlers={"apply_fee": self.apply_fee})
        instance.run()
        assert instance.marking.place(self.OUT) == (Token("Charged", {"amount": 105}),)
        # Read selections stay in place.
        assert instance.marking.place(self.CONFIG) == (Token("Config", {"fee": 5}),)


class TestPerArcOutputContracts:
    """Each output arc is a routing contract; one firing may carry different payloads per branch."""

    PENDING, SETTLE = NetPath("pending"), NetPath("settle")
    APPROVED, LEDGER = NetPath("approved"), NetPath("ledger")
    NOTICE = Token("ApprovalNotice", {"ok": True})
    ENTRY = Token("LedgerEntry", {"amount": 150})

    def net(self) -> Net:
        return Net(
            places=[Place(self.PENDING), Place(self.APPROVED), Place(self.LEDGER)],
            transitions=[Transition(self.SETTLE, handler="settle")],
            arcs=[
                Arc(self.PENDING, self.SETTLE),
                Arc(self.SETTLE, self.APPROVED, color="ApprovalNotice"),
                Arc(self.SETTLE, self.LEDGER, color="LedgerEntry"),
            ],
        )

    def fired(self, handler):
        marking = Marking({self.PENDING: (Token("Payment", {"amount": 150}),)})
        instance = Instance(self.net(), marking, handlers={"settle": handler})
        [firing] = instance.run()
        return instance, firing

    def test_heterogeneous_fanout_deposits_different_payloads_per_branch(self):
        # The capability the oracle's merged fan-out cannot express.
        def settle(binding, outputs):
            return {self.APPROVED: (self.NOTICE,), self.LEDGER: (self.ENTRY,)}

        instance, firing = self.fired(settle)
        assert instance.marking == Marking({self.APPROVED: (self.NOTICE,), self.LEDGER: (self.ENTRY,)})
        assert firing.produced == ((self.APPROVED, self.NOTICE), (self.LEDGER, self.ENTRY))

    def test_token_whose_color_matches_no_arc_at_its_destination_is_dropped(self):
        # Navigator ruling: dropped silently — the validation run owns typos.
        def settle(binding, outputs):
            return {self.APPROVED: (self.ENTRY,), self.LEDGER: (self.ENTRY,)}

        instance, firing = self.fired(settle)
        assert instance.marking == Marking({self.LEDGER: (self.ENTRY,)})
        assert firing.produced == ((self.LEDGER, self.ENTRY),)

    def test_token_keyed_to_a_place_with_no_output_arc_is_dropped(self):
        def settle(binding, outputs):
            return {self.PENDING: (self.NOTICE,), self.LEDGER: (self.ENTRY,)}

        instance, firing = self.fired(settle)
        assert instance.marking == Marking({self.LEDGER: (self.ENTRY,)})
        assert firing.produced == ((self.LEDGER, self.ENTRY),)

    def test_a_handler_may_consult_the_output_arcs_to_route(self):
        # ``outputs`` lets a reusable handler enumerate its routing contracts
        # instead of hard-coding destinations — the shape stdlib shaping
        # handlers (unpack) will take.
        def settle(binding, outputs):
            return {arc.target: (self.NOTICE,) for arc in outputs if arc.admits(self.NOTICE)}

        instance, firing = self.fired(settle)
        assert firing.produced == ((self.APPROVED, self.NOTICE),)
        assert instance.marking == Marking({self.APPROVED: (self.NOTICE,)})


class TestTypedPassthroughRouting:
    """Passthrough forwards each consumed token through every output arc that admits it."""

    IN, ROUTE = NetPath("in"), NetPath("route")
    XS, ANYTHING, YS = NetPath("xs"), NetPath("anything"), NetPath("ys")

    def instance(self) -> Instance:
        net = Net(
            places=[Place(self.IN), Place(self.XS), Place(self.ANYTHING), Place(self.YS)],
            transitions=[Transition(self.ROUTE)],
            arcs=[
                Arc(self.IN, self.ROUTE),
                Arc(self.ROUTE, self.XS, color="X"),
                Arc(self.ROUTE, self.ANYTHING),
                Arc(self.ROUTE, self.YS, color="Y"),
            ],
        )
        return Instance(net, Marking({self.IN: (Token("X"),)}))

    def test_forwards_through_admitting_arcs_only(self):
        # A typed arc admits its color, an untyped arc admits anything: the X
        # token lands in xs and anything, never in ys.
        instance = self.instance()
        instance.run()
        assert instance.marking == Marking({self.XS: (Token("X"),), self.ANYTHING: (Token("X"),)})

    def test_consumed_token_admitted_by_no_arc_is_simply_consumed(self):
        # Leftover consumption is allowed, not an error [DR permissive-flow-defaults].
        net = Net(
            places=[Place(self.IN), Place(self.YS)],
            transitions=[Transition(self.ROUTE)],
            arcs=[Arc(self.IN, self.ROUTE), Arc(self.ROUTE, self.YS, color="Y")],
        )
        instance = Instance(net, Marking({self.IN: (Token("X"),)}))
        instance.run()
        assert instance.marking == Marking()
        assert instance.is_quiescent


class TestZeroConsumeHandledEmitter:
    """A handled transition may fire without consuming: the handler drives the emit, gated by read/inhibit arcs."""

    SIGNAL, EMIT, OUT, DONE = NetPath("signal"), NetPath("emit"), NetPath("out"), NetPath("done")

    @staticmethod
    def emit_once(binding: Binding, outputs) -> dict:
        return {NetPath("out"): (Token("Emitted"),), NetPath("done"): (Token.black(),)}

    def test_self_inhibiting_emitter_fires_once_then_quiesces(self):
        net = Net(
            places=[Place(self.SIGNAL), Place(self.OUT), Place(self.DONE)],
            transitions=[Transition(self.EMIT, handler="emit_once")],
            arcs=[
                Arc(self.SIGNAL, self.EMIT, ArcMode.READ),
                Arc(self.DONE, self.EMIT, ArcMode.INHIBIT),
                Arc(self.EMIT, self.OUT),
                Arc(self.EMIT, self.DONE),
            ],
        )
        instance = Instance(net, Marking({self.SIGNAL: (Token.black(),)}), handlers={"emit_once": self.emit_once})
        firings = instance.run()
        assert len(firings) == 1
        assert firings[0].produced == ((self.OUT, Token("Emitted")), (self.DONE, Token.black()))
        assert instance.marking.place(self.OUT) == (Token("Emitted"),)
        assert instance.is_quiescent
