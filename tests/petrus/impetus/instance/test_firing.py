"""Behavioral tests for passthrough, the scheduler, and the begin/end firing lifecycle."""

from __future__ import annotations

# Internal imports
from petrus.impetus.petrinet import (
    Binding,
    ConsumedTokens,
    ProducedTokens,
    ReadTokens,
    begin_firing,
    candidates,
    complete_firing,
    route,
)
from petrus.impetus.binding import HandlerResult, passthrough
from petrus.impetus.instance import (
    FiringOccurrence,
    begin_firing as instance_begin_firing,
    complete_firing as instance_complete_firing,
    select_conservative,
)
from petrus.impetus.history import (
    DeliveryRegistration,
    DeliveryRegistrationClosed,
    DeliveryRegistrationOpened,
    FiringBegun,
    FiringCompleted,
    TokensConsumed,
    TokensProduced,
)
from petrus.impetus.petrinet import Marking, Token
from petrus.impetus.petrinet import Arc, ArcMode, Net, NetPath, Place, Transition


# ── route ────────────────────────────────────────────────────


class TestRoute:
    """Direct unit tests of routing — the glossary verb passthrough's comprehension IS: each token to every output arc that admits it, order preserved, concatenated per target."""

    T = NetPath("t")

    def test_each_token_goes_to_every_admitting_arc_order_preserved(self):
        x1, x2, y = Token("X", {"n": 1}), Token("X", {"n": 2}), Token("Y")
        typed = Arc(self.T, NetPath("b"), color="X")
        untyped = Arc(self.T, NetPath("c"))

        assert route((x1, y, x2), (typed, untyped)) == {
            NetPath("b"): (x1, x2),
            NetPath("c"): (x1, y, x2),
        }

    def test_two_arcs_to_one_target_concatenate_in_arc_order(self):
        x, y = Token("X"), Token("Y")
        to_b_x = Arc(self.T, NetPath("b"), color="X")
        to_b_y = Arc(self.T, NetPath("b"), color="Y")

        assert route((y, x), (to_b_x, to_b_y)) == {NetPath("b"): (x, y)}

    def test_unrouted_tokens_drop_silently(self):
        # The ruled passthrough posture: no arc admits it, no deposit — the
        # validation run and the type layer own declaration typos.
        assert route((Token("X"),), (Arc(self.T, NetPath("b"), color="Y"),)) == {}


# ── passthrough ──────────────────────────────────────────────


class TestPassthrough:
    def test_forwards_each_token_through_every_admitting_output_arc(self):
        # Color-routed: a typed arc admits its color, an untyped arc admits
        # anything; output tokens come back keyed by destination.
        token = Token("X")
        binding = Binding(NetPath("t"), ((NetPath("a"), (token,)),))
        typed = Arc(NetPath("t"), NetPath("b"), color="X")
        untyped = Arc(NetPath("t"), NetPath("c"))
        other = Arc(NetPath("t"), NetPath("d"), color="Y")
        assert passthrough(binding, (typed, untyped, other)) == {NetPath("b"): (token,), NetPath("c"): (token,)}

    def test_forwards_only_consumed_selections(self):
        # Read selections stay in place and are never forwarded.
        token = Token("X")
        binding = Binding(NetPath("t"), (), read=((NetPath("a"), (token,)),))
        assert passthrough(binding, (Arc(NetPath("t"), NetPath("b")),)) == {}

    def test_a_transition_with_no_output_arcs_is_a_sink(self):
        binding = Binding(NetPath("t"), ((NetPath("a"), (Token.black(),)),))
        assert passthrough(binding, ()) == {}

    def test_forwards_delivered_tokens_of_a_source_firing(self):
        # Runtime injection IS passthrough over the delivered tokens: a source
        # binding consumes nothing, so its delivered tokens are what the
        # default handler color-routes.
        token = Token("X")
        binding = Binding(NetPath("t"), (), delivered=(token,))
        assert passthrough(binding, (Arc(NetPath("t"), NetPath("b")),)) == {NetPath("b"): (token,)}


# ── scheduler ────────────────────────────────────────────────


class TestSelectConservative:
    def test_picks_the_first_binding(self):
        bindings = [Binding(NetPath("t1"), ()), Binding(NetPath("t2"), ())]
        assert select_conservative(bindings) is bindings[0]

    def test_returns_none_when_empty(self):
        assert select_conservative([]) is None


# ── begin/end firing ─────────────────────────────────────────


def _line_net():
    a, b, t = NetPath("a"), NetPath("b"), NetPath("t")
    return Net(places=[Place(a), Place(b)], transitions=[Transition(t)], arcs=[Arc(a, t), Arc(t, b)])


def _fork_net():
    """One transition consuming from ``a`` and fanning out to ``b`` and ``c``."""
    a, b, c, t = NetPath("a"), NetPath("b"), NetPath("c"), NetPath("t")
    return Net(
        places=[Place(a), Place(b), Place(c)],
        transitions=[Transition(t)],
        arcs=[Arc(a, t), Arc(t, b), Arc(t, c)],
    )


def _fire(net, marking, binding, handler):
    """Drive the two history-independent Petrinet transforms."""
    begin_effects, begun = begin_firing(marking, binding)
    projected = handler(binding, net.outputs(binding.transition))
    produced, after = complete_firing(net, begun, binding.transition, projected)
    return after, begin_effects, produced


class TestBeginEndFiring:
    def test_petrinet_source_binding_begins_with_no_movement_effects(self):
        binding = Binding(NetPath("source"), (), (), delivered=(Token("event"),))

        effects, after = begin_firing(Marking(), binding)

        assert effects == ()
        assert after == Marking()

    def test_petrinet_consume_precedes_read_and_same_token_fails_loud(self):
        place = NetPath("shared")
        token = Token("X")
        binding = Binding(NetPath("t"), ((place, (token,)),), ((place, (token,)),))

        try:
            begin_firing(Marking({place: (token,)}), binding)
        except ValueError as error:
            assert "cannot read" in str(error) and "shared" in str(error)
        else:
            raise AssertionError("a firing cannot read the token its consume selection removes")

    def test_instance_begin_firing_retains_its_record_authoring_contract(self):
        net = _line_net()
        token = Token("X")
        marking = Marking({NetPath("a"): (token,)})
        [binding] = candidates(net, marking)

        after, records = instance_begin_firing(marking, binding, occurrence=7, instant=11)

        assert after == Marking()
        assert records == (
            FiringBegun(NetPath("t"), occurrence=7, instant=11),
            TokensConsumed(NetPath("a"), (token,), occurrence=7, instant=11),
        )

    def test_instance_complete_firing_retains_its_outcome_and_registration_contract(self):
        net = _line_net()
        token = Token("X")
        [binding] = candidates(net, Marking({NetPath("a"): (token,)}))
        begun, begin_records = instance_begin_firing(
            Marking({NetPath("a"): (token,)}), binding, occurrence=7, instant=11
        )
        occurrence = FiringOccurrence(7, binding, begin_records)
        close = DeliveryRegistration(NetPath("source"), "old")
        open_ = DeliveryRegistration(NetPath("source"), "new")

        after, outcome, appended = instance_complete_firing(
            net,
            begun,
            occurrence,
            HandlerResult({"b": (token,)}, closes=(close,), opens=(open_,)),
            instant=12,
        )

        assert after == Marking({NetPath("b"): (token,)})
        assert appended == (
            TokensProduced(NetPath("b"), (token,), occurrence=7, instant=12),
            DeliveryRegistrationClosed(NetPath("source"), "old", occurrence=7, instant=12),
            DeliveryRegistrationOpened(NetPath("source"), "new", occurrence=7, instant=12),
            FiringCompleted(NetPath("t"), occurrence=7, instant=12),
        )
        assert outcome.consumed == (token,)
        assert outcome.produced == ((NetPath("b"), token),)
        assert outcome.records == begin_records + appended

    def test_begin_consumes_and_end_produces(self):
        net = _line_net()
        token = Token("X")
        marking = Marking({NetPath("a"): (token,)})
        [binding] = candidates(net, marking)

        after, begin_effects, produced = _fire(net, marking, binding, passthrough)

        assert after == Marking({NetPath("b"): (token,)})
        assert begin_effects == (ConsumedTokens(NetPath("a"), (token,)),)
        assert produced == (ProducedTokens(NetPath("b"), (token,)),)

    def test_returns_movements_in_lifecycle_order(self):
        net = _line_net()
        token = Token("X")
        marking = Marking({NetPath("a"): (token,)})
        [binding] = candidates(net, marking)

        _, begun, completed = _fire(net, marking, binding, passthrough)

        assert begun == (ConsumedTokens(NetPath("a"), (token,)),)
        assert completed == (ProducedTokens(NetPath("b"), (token,)),)

    def test_begin_fails_loud_on_a_stale_selection_before_any_record_matters(self):
        # The ADR 0007 duplicate-worker protection: a binding whose tokens are
        # gone cannot begin — the consume raises, nothing is partially begun.
        net = _line_net()
        [binding] = candidates(net, Marking({NetPath("a"): (Token("X"),)}))

        try:
            begin_firing(Marking(), binding)
        except ValueError:
            pass
        else:
            raise AssertionError("a stale selection must not begin")

    def test_begin_records_read_selections_after_the_consumes_in_input_arc_order(self):
        # The category-5 read fact [ADR 0031]: begin emits one TokensRead per
        # read arc, after the TokensConsumed records, in input-arc order — the
        # canonical history shows the whole input binding the handler
        # observed [ADR 0034], and the read tokens never leave the marking.
        a, gate, t, b = NetPath("a"), NetPath("gate"), NetPath("t"), NetPath("b")
        settings = Token("Config", {"mode": "strict"})
        net = Net(
            places=[Place(a), Place(gate), Place(b)],
            transitions=[Transition(t)],
            arcs=[Arc(a, t), Arc(gate, t, mode=ArcMode.READ), Arc(t, b)],
        )
        marking = Marking({a: (Token.black(),), gate: (settings,)})
        [binding] = candidates(net, marking)

        effects, after = begin_firing(marking, binding)

        assert effects == (
            ConsumedTokens(a, (Token.black(),)),
            ReadTokens(gate, (settings,)),
        )
        assert after == Marking({gate: (settings,)})  # read leaves its token in place

    def test_a_stale_read_selection_cannot_begin(self):
        # The read half of ADR 0007's protection: under interleaved
        # occurrences another firing can consume a read token between
        # enabledness and begin — the stale read fails loud exactly like a
        # stale consume, and nothing is partially begun.
        a, gate, t, b = NetPath("a"), NetPath("gate"), NetPath("t"), NetPath("b")
        net = Net(
            places=[Place(a), Place(gate), Place(b)],
            transitions=[Transition(t)],
            arcs=[Arc(a, t), Arc(gate, t, mode=ArcMode.READ), Arc(t, b)],
        )
        [binding] = candidates(net, Marking({a: (Token.black(),), gate: (Token("Config"),)}))
        gone = Marking({a: (Token.black(),)})  # the gate token was consumed elsewhere

        try:
            begin_firing(gone, binding)
        except ValueError as error:
            assert "cannot read" in str(error) and "gate" in str(error)
        else:
            raise AssertionError("a stale read selection must not begin")

    def test_a_user_handlers_projection_records_movements_only(self):
        # A plain callable is a pure deterministic projection [DR 2026-07-14
        # source-delivery-projection-and-identity]: its effects ARE the
        # projection, so its lifecycle records match passthrough's shape —
        # no activity records — and a token no arc admits simply drops from
        # the deposit (the validation run owns declaration typos).
        net = _line_net()
        marking = Marking({NetPath("a"): (Token("X"),)})
        [binding] = candidates(net, marking)
        handler = lambda b, outputs: {NetPath("b"): (Token("Y"),), "nowhere": (Token("Z"),)}  # noqa: E731

        after, begun, completed = _fire(net, marking, binding, handler)

        assert after == Marking({NetPath("b"): (Token("Y"),)})
        assert begun == (ConsumedTokens(NetPath("a"), (Token("X"),)),)
        assert completed == (ProducedTokens(NetPath("b"), (Token("Y"),)),)

    def test_fans_one_token_out_to_every_output_place(self):
        net = _fork_net()
        token = Token("X")
        marking = Marking({NetPath("a"): (token,)})
        [binding] = candidates(net, marking)

        after, _, produced = _fire(net, marking, binding, passthrough)

        assert after == Marking({NetPath("b"): (token,), NetPath("c"): (token,)})
        assert produced == (
            ProducedTokens(NetPath("b"), (token,)),
            ProducedTokens(NetPath("c"), (token,)),
        )

    def test_registration_effects_are_not_part_of_the_petrinet_transform(self):
        a, b, t, src = NetPath("a"), NetPath("b"), NetPath("t"), NetPath("src")
        net = Net(
            places=[Place(a), Place(b)],
            transitions=[Transition(t, handler="h"), Transition(src)],
            arcs=[Arc(a, t), Arc(t, b), Arc(src, b)],
        )
        marking = Marking({a: (Token("X"),)})
        [binding] = candidates(net, marking)
        result = HandlerResult(
            {b: (Token("Y"),)}, closes=(DeliveryRegistration(src, "old"),), opens=(DeliveryRegistration(src, "new"),)
        )
        _, begun = begin_firing(marking, binding)

        effects, _ = complete_firing(net, begun, binding.transition, result.tokens)

        assert effects == (ProducedTokens(b, (Token("Y"),)),)

    def test_deposits_the_supplied_handler_tokens(self):
        net = _line_net()
        marking = Marking({NetPath("a"): (Token("X"),)})
        [binding] = candidates(net, marking)

        after, _, produced = _fire(net, marking, binding, lambda b, outputs: {NetPath("b"): (Token("Y"),)})

        assert after == Marking({NetPath("b"): (Token("Y"),)})
        assert produced == (ProducedTokens(NetPath("b"), (Token("Y"),)),)

    def test_handler_destination_keys_may_be_plain_strings(self):
        # The Handler contract admits NetPath | str keys; end firing
        # normalizes, so firing.produced and the records always speak NetPath.
        net = _line_net()
        marking = Marking({NetPath("a"): (Token("X"),)})
        [binding] = candidates(net, marking)

        _, _, produced = _fire(net, marking, binding, lambda b, outputs: {"b": (Token("Y"),)})

        assert produced == (ProducedTokens(NetPath("b"), (Token("Y"),)),)

    def test_destination_keys_resolving_to_one_place_coalesce_into_one_record(self):
        # A place has one identity in a firing's movement records, however the
        # handler spelled the key.
        net = _line_net()
        marking = Marking({NetPath("a"): (Token("X"),)})
        [binding] = candidates(net, marking)

        _, _, produced = _fire(
            net, marking, binding, lambda b, outputs: {"b": (Token("Y"),), NetPath("b"): (Token("Z"),)}
        )

        assert produced == (ProducedTokens(NetPath("b"), (Token("Y"), Token("Z"))),)
