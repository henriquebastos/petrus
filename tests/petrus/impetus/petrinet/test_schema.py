"""Behavioral tests for NetPath and Net construction/validation."""

from __future__ import annotations

# Pip imports
import pytest

# Internal imports
from petrus.impetus.petrinet import Token
from petrus.impetus.petrinet import (
    ANONYMOUS,
    AnonymousDeclaration,
    Arc,
    ArcMode,
    Cel,
    Color,
    Net,
    NetPath,
    NetUri,
    Place,
    Transition,
)


# ── NetPath ──────────────────────────────────────────────────


class TestNetPath:
    def test_single_segment(self):
        assert tuple(NetPath("start")) == ("start",)

    def test_dotted_string_splits_into_segments(self):
        assert tuple(NetPath("review.start")) == ("review", "start")

    def test_str_round_trips(self):
        assert str(NetPath("review.start")) == "review.start"

    def test_coercing_a_netpath_is_idempotent(self):
        p = NetPath("review.start")
        assert NetPath(p) is p

    def test_empty_address_is_rejected(self):
        with pytest.raises(ValueError, match="non-empty"):
            NetPath("")

    @pytest.mark.parametrize("value", [".a", "a.", "a..b"])
    def test_empty_path_segment_is_rejected(self, value):
        with pytest.raises(ValueError, match="segments"):
            NetPath(value)


# ── NetUri ───────────────────────────────────────────────────


class TestNetUri:
    def test_declaration_uri_escapes_path_segments_and_names_canonically(self):
        uri = NetUri.declaration("transition", NetPath("review/a.start"), "guard", "ready now?")

        assert str(uri) == "transition:/review%2Fa/start#guard:ready%20now%3F"
        assert repr(uri) == "NetUri('transition:/review%2Fa/start#guard:ready%20now%3F')"

    def test_declaration_uri_rejects_unknown_owner(self):
        with pytest.raises(ValueError, match="owner"):
            NetUri.declaration("net", NetPath("start"), "guard", "ready")

    def test_arc_and_filter_uris_escape_endpoint_segments_and_preserve_one_fragment(self):
        arc = NetUri.arc(NetPath("review/a.start"), NetPath("run now"), 1)

        assert str(arc) == "arc:/review%2Fa/start->/run%20now#$1"
        assert str(NetUri.arc_filter(arc)) == "arc:/review%2Fa/start->/run%20now#filter:$1"

    def test_arc_filter_refuses_a_declaration_uri_as_its_owner(self):
        with pytest.raises(ValueError, match="generated occurrence"):
            NetUri.arc_filter(NetUri("arc:/pending->/review#filter:$0"))

    @pytest.mark.parametrize("value", ["transition", "transition:/review start", "transition:/review%2fstart"])
    def test_noncanonical_uri_is_rejected(self, value):
        with pytest.raises(ValueError, match="NetUri"):
            NetUri(value)


# ── Net ──────────────────────────────────────────────────────


def _line_net():
    """a -> t -> b."""
    a, b, t = NetPath("a"), NetPath("b"), NetPath("t")
    return Net(
        places=[Place(a), Place(b)],
        transitions=[Transition(t)],
        arcs=[Arc(a, t, ArcMode.CONSUME), Arc(t, b, ArcMode.CONSUME)],
    )


class TestNet:
    def test_anonymous_declaration_display_name_is_non_semantic(self):
        named = AnonymousDeclaration("review_matches")

        assert named.display_name == "review_matches"
        assert named == ANONYMOUS
        assert hash(named) == hash(ANONYMOUS)

    @pytest.mark.parametrize("display_name", ["", 7])
    def test_anonymous_declaration_rejects_invalid_display_name(self, display_name):
        with pytest.raises(ValueError, match="display name"):
            AnonymousDeclaration(display_name)

    def test_transition_behavior_declaration_indexes_are_canonical_and_immutable(self):
        source, transition, target = map(NetPath, ("source", "review.publish", "target"))
        inline = Cel("source.color == 'Generation'")
        net = Net(
            places=[Place(source), Place(target)],
            transitions=[
                Transition(
                    transition,
                    handler=ANONYMOUS,
                    guards=("ready", ANONYMOUS, inline, ANONYMOUS),
                )
            ],
            arcs=[Arc(source, transition), Arc(transition, target)],
        )

        handler_uri = NetUri.declaration("transition", transition, "handler")
        guard_uris = (
            NetUri.declaration("transition", transition, "guard", "ready"),
            NetUri.declaration("transition", transition, "guard", "$1"),
            NetUri.declaration("transition", transition, "guard", "$2"),
            NetUri.declaration("transition", transition, "guard", "$3"),
        )
        assert net.handler_uri(transition) == handler_uri
        assert net.guard_uris(transition) == guard_uris
        assert net.handler_declarations == {handler_uri: ANONYMOUS}
        assert net.guard_declarations == dict(zip(guard_uris, ("ready", ANONYMOUS, inline, ANONYMOUS)))
        with pytest.raises(TypeError):
            net.guard_declarations[guard_uris[0]] = "other"

    def test_arc_occurrences_and_filters_are_position_aligned_and_immutable(self):
        p, t, out = map(NetPath, ("p", "t", "out"))
        repeated = Arc(p, t, filter="accept")
        output = Arc(t, out)
        net = Net([Place(p), Place(out)], [Transition(t)], [repeated, output, repeated])

        assert net.arcs == (repeated, output, repeated)
        assert all(type(arc) is Arc for arc in net.arcs)
        assert net.arc_uris() == (
            NetUri("arc:/p->/t#$0"),
            NetUri("arc:/t->/out"),
            NetUri("arc:/p->/t#$1"),
        )
        assert net.filter_uris() == (
            NetUri("arc:/p->/t#filter:$0"),
            None,
            NetUri("arc:/p->/t#filter:$1"),
        )
        assert net.inputs(t) == (repeated, repeated)
        assert net.input_positions(t) == (0, 2)
        assert net.filter_declarations == {
            NetUri("arc:/p->/t#filter:$0"): "accept",
            NetUri("arc:/p->/t#filter:$1"): "accept",
        }
        with pytest.raises(TypeError):
            net.filter_declarations[NetUri("arc:/p->/t#filter:$0")] = "other"

    def test_unique_arc_and_filter_use_unfragmented_occurrence_address(self):
        net = _line_net()

        assert net.arc_uri(0) == NetUri("arc:/a->/t")
        assert net.filter_uris() == (None, None)

    @pytest.mark.parametrize("configuration", [{"handler": "$generated"}, {"guards": ("$0",)}])
    def test_generated_declaration_namespace_is_reserved(self, configuration):
        with pytest.raises(ValueError, match="cannot start with '\\$'"):
            Transition(NetPath("t"), **configuration)

    def test_duplicate_named_guards_are_rejected(self):
        with pytest.raises(ValueError, match="duplicate named guard 'ready'"):
            Transition(NetPath("t"), guards=("ready", "ready"))

    def test_inputs_and_outputs_are_indexed(self):
        net = _line_net()
        t = NetPath("t")
        assert [arc.source for arc in net.inputs(t)] == [NetPath("a")]
        assert [arc.target for arc in net.outputs(t)] == [NetPath("b")]

    def test_transition_with_inputs_is_not_a_source(self):
        assert net_is_source("t") is False

    def test_transition_without_inputs_is_a_source(self):
        assert net_is_source("src") is True

    def test_name_collision_is_rejected(self):
        p = NetPath("x")
        with pytest.raises(ValueError, match="collision"):
            Net(places=[Place(p)], transitions=[Transition(p)], arcs=[])

    def test_duplicate_node_paths_are_rejected_before_dictionary_collapse(self):
        p, t = NetPath("p"), NetPath("t")
        with pytest.raises(ValueError, match="duplicate place"):
            Net(places=[Place(p), Place(p)], transitions=[Transition(t)], arcs=[])
        with pytest.raises(ValueError, match="duplicate transition"):
            Net(places=[Place(p)], transitions=[Transition(t), Transition(t)], arcs=[])

    def test_place_to_place_arc_is_rejected(self):
        a, b = NetPath("a"), NetPath("b")
        with pytest.raises(ValueError, match="connect a place and a transition"):
            Net(places=[Place(a), Place(b)], transitions=[], arcs=[Arc(a, b)])

    def test_input_arcs_preserve_definition_order_across_modes(self):
        # All three input modes are honored, and net.inputs preserves arc
        # definition order -- load-bearing: the replay contract requires consumed
        # tokens in input-arc order (spec/traces/README.md). A consume arc is
        # required; a read/inhibit-only transition is rejected (next test).
        p, q, r, t = NetPath("p"), NetPath("q"), NetPath("r"), NetPath("t")
        net = Net(
            places=[Place(p), Place(q), Place(r)],
            transitions=[Transition(t)],
            arcs=[Arc(p, t, ArcMode.READ), Arc(q, t, ArcMode.CONSUME), Arc(r, t, ArcMode.INHIBIT)],
        )
        assert [arc.mode for arc in net.inputs(t)] == [ArcMode.READ, ArcMode.CONSUME, ArcMode.INHIBIT]

    @pytest.mark.parametrize(
        ("mode", "expected"),
        [
            (ArcMode.CONSUME, (True, False, False)),
            (ArcMode.READ, (False, True, False)),
            (ArcMode.INHIBIT, (False, False, True)),
        ],
    )
    def test_arc_mode_predicates_expose_semantic_vocabulary(self, mode, expected):
        arc = Arc(NetPath("p"), NetPath("t"), mode)

        assert (arc.is_consume, arc.is_read, arc.is_inhibit) == expected

    def test_read_or_inhibit_only_transition_without_a_handler_is_rejected(self):
        # A passthrough-bound transition with no consume arc fires forever
        # consuming and producing nothing (livelock) -- permanently invalid.
        p, t = NetPath("p"), NetPath("t")
        with pytest.raises(ValueError, match="no consume input arc"):
            Net(places=[Place(p)], transitions=[Transition(t)], arcs=[Arc(p, t, ArcMode.READ)])

    def test_read_or_inhibit_only_transition_with_a_handler_is_legal(self):
        # A handler can drive a zero-consume emit (gated by its read/inhibit
        # arcs); whether the net self-gates is the author's design concern.
        p, t = NetPath("p"), NetPath("t")
        net = Net(places=[Place(p)], transitions=[Transition(t, handler="emit")], arcs=[Arc(p, t, ArcMode.READ)])
        assert net.inputs(t)

    def test_guards_on_a_source_transition_are_rejected(self):
        # A guard is enabledness machinery and source transitions are excluded
        # from enabledness — they fire only on external delivery. A declared
        # guard the kernel would never evaluate is refused at build, in both
        # encodings.
        p, src = NetPath("p"), NetPath("src")
        with pytest.raises(ValueError, match="transition src: guards on a source transition"):
            Net(places=[Place(p)], transitions=[Transition(src, guards=("ready",))], arcs=[Arc(src, p)])
        with pytest.raises(ValueError, match="transition src: guards on a source transition"):
            Net(places=[Place(p)], transitions=[Transition(src, guards=(Cel("1 == 1"),))], arcs=[Arc(src, p)])

    @pytest.mark.parametrize("weight", [0, True, 1.0, 1.5, "1"])
    def test_arc_weight_must_be_a_positive_integer(self, weight):
        # A value object rejects precondition violations; weight is semantically
        # active in all three modes now, and weight < 1 livelocks or mis-gates.
        with pytest.raises(ValueError, match="integer >= 1"):
            Arc(NetPath("a"), NetPath("t"), ArcMode.CONSUME, weight=weight)

    def test_arc_mode_must_be_the_closed_enum(self):
        with pytest.raises(ValueError, match="ArcMode"):
            Arc(NetPath("a"), NetPath("t"), "consume")

    @pytest.mark.parametrize("configuration", [{"filter": ""}, {"filter": "$generated"}])
    def test_filter_symbol_uses_the_authored_symbol_namespace(self, configuration):
        with pytest.raises(ValueError, match="filter symbol"):
            Arc(NetPath("a"), NetPath("t"), **configuration)

    def test_mode_on_an_output_arc_is_rejected(self):
        # Modes are input inscriptions; an ignored one would silently
        # mis-describe the deposit, so the net refuses it at build.
        p, t = NetPath("p"), NetPath("t")
        with pytest.raises(ValueError, match="modes are input inscriptions"):
            Net(places=[Place(p)], transitions=[Transition(t)], arcs=[Arc(p, t), Arc(t, p, ArcMode.READ)])

    def test_typed_output_arc_admits_its_color_only(self):
        arc = Arc(NetPath("t"), NetPath("b"), color="X")
        assert arc.admits(Token("X"))
        assert not arc.admits(Token("Y"))
        assert not arc.admits(Token.black())

    def test_untyped_arc_admits_anything(self):
        arc = Arc(NetPath("t"), NetPath("b"))
        assert arc.admits(Token("X"))
        assert arc.admits(Token.black())

    @pytest.mark.parametrize("mode", tuple(ArcMode))
    def test_typed_place_resolves_untyped_input_and_output_arcs_once(self, mode):
        source, target, transition = map(NetPath, ("source", "target", "move"))

        net = Net(
            places=[Place(source, color="Input"), Place(target, color="Output")],
            transitions=[Transition(transition, handler="move" if mode is not ArcMode.CONSUME else None)],
            arcs=[Arc(source, transition, mode), Arc(transition, target)],
        )

        assert net.inputs(transition) == (Arc(source, transition, mode, color="Input"),)
        assert net.outputs(transition) == (Arc(transition, target, color="Output"),)
        assert net.arcs == (
            Arc(source, transition, mode, color="Input"),
            Arc(transition, target, color="Output"),
        )

    def test_explicit_arc_color_remains_the_contract_of_an_untyped_place(self):
        source, target, transition = map(NetPath, ("source", "target", "move"))

        net = Net(
            places=[Place(source), Place(target)],
            transitions=[Transition(transition)],
            arcs=[Arc(source, transition, color="Input"), Arc(transition, target, color="Output")],
        )

        assert net.inputs(transition)[0].color == "Input"
        assert net.outputs(transition)[0].color == "Output"

    @pytest.mark.parametrize(
        ("arc", "endpoint"),
        [
            (Arc(NetPath("source"), NetPath("move"), color="Other"), "source -> move"),
            (Arc(NetPath("move"), NetPath("source"), color="Other"), "move -> source"),
        ],
    )
    def test_explicit_arc_color_cannot_conflict_with_its_place(self, arc, endpoint):
        source, transition = NetPath("source"), NetPath("move")

        with pytest.raises(ValueError, match=rf"arc {endpoint}.*Other.*place source.*Expected"):
            Net(
                places=[Place(source, color="Expected")],
                transitions=[Transition(transition)],
                arcs=[arc],
            )

    @pytest.mark.parametrize("color", ["", 7, False, Token])
    def test_place_color_must_be_a_non_empty_nominal_name_or_none(self, color):
        with pytest.raises(ValueError, match="place color must be a non-empty nominal color name or None"):
            Place(NetPath("typed"), color=color)

    @pytest.mark.parametrize("color", ["", 7, False, Token])
    def test_arc_color_must_be_a_non_empty_nominal_name_or_none(self, color):
        with pytest.raises(ValueError, match="arc color must be a non-empty nominal color name or None"):
            Arc(NetPath("source"), NetPath("transition"), color=color)

    def test_color_is_the_shared_language_neutral_nominal_name_alias(self):
        color: Color = "Generation"

        assert color == "Generation"

    def test_node_views_are_read_only(self):
        net = _line_net()
        with pytest.raises(TypeError):
            net.places[NetPath("z")] = Place(NetPath("z"))


def net_is_source(name: str) -> bool:
    a, t, src, out = NetPath("a"), NetPath("t"), NetPath("src"), NetPath("out")
    net = Net(
        places=[Place(a), Place(out)],
        transitions=[Transition(t), Transition(src)],
        arcs=[Arc(a, t), Arc(src, out)],
    )
    return net.is_source(NetPath(name))


# ── Cel ──────────────────────────────────────────────────────


class TestCel:
    def test_str_is_the_expression_source_presentation_only(self):
        # Presentation without identity: str() reads the source; equality,
        # hash, and registry keys stay the tagged dataclass's — an
        # expression is NOT a name (the vetoed str-subclass half), so a Cel
        # never collapses into the bare string it spells.
        declaration = Cel("amount >= 100")

        assert str(declaration) == "amount >= 100"
        assert declaration != "amount >= 100"
        assert repr(declaration) == "Cel(expression='amount >= 100')", "diagnostics keep the tag via !r"

    def test_a_named_symbol_and_an_equal_spelled_expression_stay_distinct_keys(self):
        # The registry collision the subclass would have caused: a bare
        # identifier expression and a symbol of the same spelling are two
        # different declarations.
        registry = {"armed": "symbol-bound", Cel("armed"): "expression-bound"}
        assert registry["armed"] == "symbol-bound"
        assert registry[Cel("armed")] == "expression-bound"

    def test_an_empty_expression_is_rejected(self):
        with pytest.raises(ValueError, match="non-empty"):
            Cel("")
