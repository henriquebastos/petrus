"""What the compiler generates, and that it generates it the same way twice."""

from pathlib import Path

import pytest

from petrus.impetus.binding import ActivityHandler, DerivedActivityHandler, derive_typed_guard
from petrus.impetus.dsl import GuardSpec
from petrus.impetus.net_definition import (
    compile_net_definition,
    parse_net_definition,
    project_net_definition,
)
from petrus.impetus.petrinet import ArcMode, Cel, NetPath, Token
from petrus.impetus.petrinet.dot import to_dot
from petrus.impetus.petrinet.enabledness import Binding
from petrus.motus.activity import DataclassPayloadConverter

from inet_lowering import compile_flow
from inet_scenario import readiness_flow
from inet_tokens import CONVERTER, CIObserved, EvidenceWatermark, HeadFact
from source_map import parse_source_map, serialize_source_map

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "golden"

PLACES = (
    "events.ci",
    "facts.repair_landed",
    "facts.rerun_accepted",
    "ladder.repair",
    "ladder.rerun",
    "publication.admitted",
    "readiness.head",
    "readiness.watermark",
    "terminal.human_needed",
    "terminal.published",
)

# In lowering order, which is canonical arc order. The counts are the fixed arc
# role table: consume event, consume folded ports, consume taken latches, read
# read-ports, inhibit forbidden latches, then produce folds, fills, emissions,
# and the effect result.
TRANSITIONS = (
    ("ingress.head", 4),
    ("ingress.ci", 1),
    ("decide.foreign", 4),
    ("decide.stale", 4),
    ("decide.publish", 7),
    ("decide.republished", 6),
    ("decide.rerun", 6),
    ("decide.repair", 7),
    ("decide.human", 7),
    ("decide.unclassified", 4),
)


@pytest.fixture(scope="module")
def compiled():
    return compile_flow(readiness_flow())


def test_the_whole_readiness_rule_lowers_to_ten_transitions_and_eight_generated_guards(compiled):
    net = compiled.built.net

    assert sorted(str(path) for path in net.places) == sorted(PLACES)
    assert sorted(str(path) for path in net.transitions) == sorted(name for name, _ in TRANSITIONS)
    assert len(net.arcs) == 50
    assert len(compiled.guards) == 8

    # Only the eight ordered-choice branches carry a guard; ingress carries none
    # (a source transition cannot).
    guarded = {str(path) for path in net.transitions if net.transitions[path].guards}
    assert guarded == {name for name, _ in TRANSITIONS if name.startswith("decide.")}


def test_arc_order_follows_the_fixed_role_table(compiled):
    """Arc order is semantic in Net v3, so the role table is a contract."""
    grouped: list[tuple[str, int]] = []
    for candidate in compiled.built.net.arcs:
        owner = str(candidate.target) if str(candidate.target) in dict(TRANSITIONS) else str(candidate.source)
        if grouped and grouped[-1][0] == owner:
            grouped[-1] = (owner, grouped[-1][1] + 1)
        else:
            grouped.append((owner, 1))

    assert grouped == list(TRANSITIONS)


def test_state_as_marking_produced_three_latch_places_and_no_state_baton(compiled):
    """ "What state am I in" is "where the tokens are"."""
    net = compiled.built.net
    latches = {"ladder.rerun": "RerunRung", "ladder.repair": "RepairRung", "publication.admitted": "PublicationClaim"}

    for path, color in latches.items():
        assert net.places[NetPath(path)].color == color

    # The rung ladder's ordering is an inhibitor, not a predicate: repair is only
    # reachable once the rerun rung's place is empty, and human once both are.
    inhibited = {
        (str(candidate.source), str(candidate.target)) for candidate in net.arcs if candidate.mode is ArcMode.INHIBIT
    }
    assert inhibited == {
        ("publication.admitted", "decide.publish"),
        ("ladder.rerun", "decide.repair"),
        ("ladder.rerun", "decide.human"),
        ("ladder.repair", "decide.human"),
    }


def test_the_head_ingress_fuses_the_generation_opening_fork(compiled):
    """One durable source firing admits the head and opens the whole generation's structure."""
    net = compiled.built.net
    produced = {str(candidate.target) for candidate in net.outputs(NetPath("ingress.head"))}

    assert net.is_source(NetPath("ingress.head"))
    assert produced == {"readiness.head", "readiness.watermark", "ladder.rerun", "ladder.repair"}
    assert net.inputs(NetPath("ingress.head")) == ()


def test_every_branch_carries_exactly_one_generated_chain_guard(compiled):
    net = compiled.built.net
    plans = {plan.id: plan for plan in compiled.branches}

    for plan in compiled.branches:
        transition = net.transitions[NetPath(plan.transition)]
        assert len(transition.guards) == 1
        [uri] = net.guard_uris(NetPath(plan.transition))
        assert uri in compiled.guards

    # Ordered first-match-wins: each branch negates every earlier predicate that
    # is not already separated from it structurally.
    assert plans["foreign"].negated == ()
    assert plans["stale"].negated == ("is_for_another_head",)
    assert plans["publish"].negated == ("is_for_another_head", "is_not_newer_than")
    assert plans["unclassified"].negated == (
        "is_for_another_head",
        "is_not_newer_than",
        "is_clean",
        "is_classified_failure",
    )
    # The three ladder rungs share one predicate and are separated by latches
    # alone, so none of them negates the others.
    for rung in ("rerun", "repair", "human"):
        assert "is_classified_failure" not in plans[rung].negated
    assert plans["republished"].negated == ("is_for_another_head", "is_not_newer_than")


def _foreign_binding() -> Binding:
    return Binding(
        NetPath("decide.foreign"),
        consumed=(
            (
                NetPath("events.ci"),
                (
                    Token(
                        "CIObserved",
                        {
                            "head": "h1",
                            "evidence": {"run_id": 1, "attempt": 1},
                            "conclusion": "success",
                            "fingerprint": None,
                        },
                    ),
                ),
            ),
            (NetPath("readiness.watermark"), (Token("EvidenceWatermark", {"seen": {"run_id": 0, "attempt": 0}}),)),
        ),
        read=((NetPath("readiness.head"), (Token("HeadFact", {"head": "h1", "generation": 1, "lineage": "L1"}),)),),
    )


def test_generated_guards_require_the_experiment_token_converter(compiled):
    """The DSL default cannot reconstruct nested ``EvidenceId``; B pinned the same trap."""

    def naive(ciobserved: CIObserved, evidencewatermark: EvidenceWatermark, headfact: HeadFact) -> bool:
        return ciobserved.is_not_newer_than(evidencewatermark) and headfact.head == ciobserved.head

    binding = _foreign_binding()

    # With the experiment's converter the nested value reconstructs and the
    # predicate answers.
    with_converter = derive_typed_guard(compiled.built.net, NetPath("decide.foreign"), naive, converter=CONVERTER)
    assert with_converter(binding) is False

    # With the DSL default, `evidence` stays a dict and the failure surfaces at
    # evaluation time inside enabledness, never at derivation time.
    default = derive_typed_guard(
        compiled.built.net,
        NetPath("decide.foreign"),
        naive,
        converter=DataclassPayloadConverter(),
    )
    with pytest.raises(AttributeError):
        default(binding)

    # And every guard the compiler generated carries the converter explicitly.
    assert all(spec.converter is CONVERTER for spec in _authored_guard_specs())


def _authored_guard_specs():
    from inet_lowering import _Lowering  # noqa: PLC0415 - inspecting the compiler's own output

    lowering = _Lowering(readiness_flow())
    lowering.compile()
    return [
        guard
        for value in lowering.spec._transition_values.values()
        for guard in value.guards
        if isinstance(guard, GuardSpec)
    ]


def test_effect_branches_bind_a_compiler_owned_activity_bridge(compiled):
    """``DerivedActivityHandler`` refuses a fused branch: its outputs are not all the result color."""
    net = compiled.built.net
    effects = {"decide.publish": "publish", "decide.rerun": "rerun", "decide.repair": "repair"}

    for path, name in effects.items():
        uri = net.handler_uri(NetPath(path))
        assert uri is not None
        assert isinstance(compiled.handlers[uri], ActivityHandler)
        assert net.transitions[NetPath(path)].handler == name

    # A fused branch is exactly the shape `DerivedActivityHandler` refuses: its
    # inputs are the decision's ports, not the Activity's request color, and its
    # outputs include the folded state and the filled latches as well as the
    # result. Both refusals are real; the first one raised is the input one.
    definition = next(item for item in compiled.activities if item.declaration.name == "rerun")
    with pytest.raises(ValueError, match="parameter 'request' .RerunRequest. requires exactly one matching input arc"):
        DerivedActivityHandler(net, NetPath("decide.rerun"), definition)


def test_one_method_derived_predicate_reaches_canonical_net_v3_as_a_cel_arc_filter(compiled):
    """The CEL probe: a Cel filter's expression survives into the interchange bytes."""
    filtered = [candidate for candidate in compiled.built.net.arcs if candidate.filter is not None]

    assert [(str(item.source), str(item.target)) for item in filtered] == [
        ("events.ci", "decide.publish"),
        ("events.ci", "decide.republished"),
    ]
    assert all(item.filter == Cel('conclusion == "success"') for item in filtered)

    document = parse_net_definition(compiled.definition_bytes)
    carried = [arc for arc in document.definition.arcs if arc.filter is not None]
    assert [(arc.filter.kind, arc.filter.expression) for arc in carried] == [  # type: ignore[union-attr]
        ("cel", 'conclusion == "success"'),
        ("cel", 'conclusion == "success"'),
    ]
    # By contrast every Python-bound guard projects as an anonymous declaration.
    guards = [guard for transition in document.definition.transitions for guard in transition.guards]
    assert {guard.kind for guard in guards} == {"anonymous"}


def test_a_cel_guard_cannot_reach_any_place_of_this_net():
    """The precise CEL limit, executed: a guard binds place *paths* as bare identifiers."""
    from petrus.impetus.binding.cel import compile_guard

    scope = [NetPath("events.ci"), NetPath("readiness.watermark"), NetPath("readiness.head")]

    with pytest.raises(ValueError) as failure:
        compile_guard(Cel('events.ci[0].data.conclusion == "success"'), NetPath("decide.publish"), scope)

    # CEL parses `events.ci` as member access on `events`, so a dotted place path
    # is not addressable at all — no expression over these places can compile.
    assert "references name(s) outside its consume/read input places" in str(failure.value)
    assert "['events']" in str(failure.value)


def test_repeated_lowering_is_byte_stable_and_matches_the_net_v3_golden():
    first = compile_flow(readiness_flow())
    second = compile_flow(readiness_flow())

    assert first.definition_bytes == second.definition_bytes
    assert first.definition_bytes == (GOLDEN / "inscription.net-v3.json").read_bytes()


def test_net_v3_round_trips_through_the_current_parser_and_compiler(compiled):
    parsed = parse_net_definition(compiled.definition_bytes)
    canonical = compile_net_definition(parsed)

    assert parsed == project_net_definition(compiled.built.net)
    assert project_net_definition(canonical) == parsed
    assert to_dot(canonical) == to_dot(compile_net_definition(parse_net_definition(compiled.definition_bytes)))


def test_every_place_transition_and_handler_has_authored_source_ownership(compiled):
    net = compiled.built.net
    mapped = {(element.kind, element.path) for element in compiled.source_map.elements}

    assert mapped == {("place", str(path)) for path in net.places} | {
        ("transition", str(path)) for path in net.transitions
    }
    for element in compiled.source_map.elements:
        entry = compiled.source_map.source_for(element.source)
        assert entry is not None
        assert entry.file in {"inet_scenario.py", "inet_tokens.py"}
        assert entry.line > 0

    # Each branch transition is owned by its own authored branch(...) call site.
    for plan in compiled.branches:
        element = compiled.source_map.element_for(plan.transition)
        assert element is not None
        assert element.source == f"readiness.decide.{plan.id}"


def test_source_map_is_stable_hash_bound_and_matches_the_golden(compiled):
    payload = serialize_source_map(compiled.source_map)

    assert payload == (GOLDEN / "inscription.source-map-v1.json").read_bytes()
    assert parse_source_map(payload) == compiled.source_map
    import hashlib

    assert compiled.source_map.definition_sha256 == hashlib.sha256(compiled.definition_bytes).hexdigest()


def test_pure_token_methods_and_helpers_create_no_nodes(compiled):
    """Eleven pure methods on the tokens; ten transitions, all of them durable boundaries."""
    assert len(compiled.built.net.transitions) == len(TRANSITIONS)
    assert {str(path) for path in compiled.built.net.transitions} == {name for name, _ in TRANSITIONS}
