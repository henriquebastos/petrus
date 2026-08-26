"""Deterministic lowering, canonical Net v3 integrity, and the source-map sidecar."""

import hashlib
from pathlib import Path

from petrus.impetus.binding import ActivityHandler
from petrus.impetus.net_definition import compile_net_definition, parse_net_definition, project_net_definition
from petrus.impetus.petrinet import ArcMode, NetPath, Token
from petrus.impetus.petrinet.dot import to_dot
from petrus.impetus.petrinet.enabledness import Binding

from domain import RerunRequested, Evidence, to_data
from lowering import compile_flow
from scenario import readiness_flow
from source_map import serialize_source_map

GOLDEN = Path(__file__).resolve().parent / "golden"

EXPECTED_PLACES = {
    "commands.publish",
    "commands.rerun",
    "commands.repair",
    "effects.publish.ack",
    "effects.publish.done",
    "effects.publish.pending",
    "effects.publish.work",
    "events.ci",
    "facts.publish_acknowledged",
    "facts.repair_landed",
    "facts.rerun_accepted",
    "readiness.state",
    "terminal.human_needed",
    "terminal.published",
}

# The fixed durable-transition table: every transition is a durable boundary;
# a compiler-only connector, dispatch, map, or format transition would appear
# here as an unexpected member and fail the exact-set assertion.
EXPECTED_ARC_COUNTS = (
    ("ingress.head", 1),
    ("ingress.ci", 1),
    ("readiness.route_ci.fire", 7),
    ("effects.rerun.fire", 2),
    ("effects.repair.fire", 2),
    ("effects.publish.authorize", 5),
    ("effects.publish.execute", 2),
    ("effects.publish.accept", 4),
    ("readiness.accept_publish.fire", 4),
)


def test_repeated_lowering_is_byte_stable_and_matches_net_v3_golden():
    first = compile_flow(readiness_flow())
    second = compile_flow(readiness_flow())

    assert first.definition_bytes == second.definition_bytes
    assert first.definition_bytes == (GOLDEN / "readiness.net-v3.json").read_bytes()


def test_net_v3_round_trips_through_current_parser_and_compiler():
    compiled = compile_flow(readiness_flow())

    document = parse_net_definition(compiled.definition_bytes)
    net = compile_net_definition(document)

    assert project_net_definition(net) == document
    # Both the authored net and the canonical parsed net render through the
    # current DOT presentation; the canonical rendering is deterministic
    # across two independent lowerings and parses. (The two renderings differ
    # deliberately: the authored net keeps authoring order and anonymous
    # display names, which canonical v3 does not carry.)
    assert to_dot(compiled.built.net).startswith("digraph")
    fresh = compile_net_definition(parse_net_definition(compile_flow(readiness_flow()).definition_bytes))
    assert to_dot(net) == to_dot(fresh)


def test_expected_topology_has_only_durable_transitions():
    net = compile_flow(readiness_flow()).built.net

    assert {str(path) for path in net.places} == EXPECTED_PLACES
    assert {str(path) for path in net.transitions} == {name for name, _ in EXPECTED_ARC_COUNTS}
    assert len(net.arcs) == 28

    # Arc order is semantic in v3: arcs group contiguously per transition in
    # the fixed role-table order, with the exact per-transition counts.
    attached = []
    for candidate in net.arcs:
        transition = candidate.source if candidate.source in net.transitions else candidate.target
        attached.append(str(transition))
    expected = [name for name, count in EXPECTED_ARC_COUNTS for _ in range(count)]
    assert attached == expected


def test_every_place_transition_and_handler_has_source_ownership():
    compiled = compile_flow(readiness_flow())
    net = compiled.built.net
    source_map = compiled.source_map

    mapped = {(element.kind, element.path) for element in source_map.elements}
    assert len(mapped) == len(source_map.elements)
    assert mapped == {("place", str(path)) for path in net.places} | {
        ("transition", str(path)) for path in net.transitions
    }

    source_ids = {source.id for source in source_map.sources}
    assert all(element.source in source_ids for element in source_map.elements)
    assert all(scope.source in source_ids for scope in source_map.lifecycle_scopes)

    # Handler attribution flows through the owning transition's element.
    for path in net.transitions:
        if net.handler_uri(path) is not None:
            assert source_map.element_for(str(path)) is not None


def test_source_map_is_stable_hash_bound_and_matches_golden():
    first = compile_flow(readiness_flow())
    second = compile_flow(readiness_flow())

    assert serialize_source_map(first.source_map) == serialize_source_map(second.source_map)
    assert first.source_map.definition_sha256 == hashlib.sha256(first.definition_bytes).hexdigest()
    assert serialize_source_map(first.source_map) == (GOLDEN / "readiness.source-map-v1.json").read_bytes()


def test_low_level_publication_gate_uses_an_inhibitor_and_canonical_validation():
    compiled = compile_flow(readiness_flow())
    net = compiled.built.net

    inhibitors = [candidate for candidate in net.arcs if candidate.mode is ArcMode.INHIBIT]
    assert {(str(candidate.source), str(candidate.target)) for candidate in inhibitors} == {
        ("effects.publish.pending", "effects.publish.authorize"),
        ("effects.publish.done", "effects.publish.authorize"),
    }

    fragment_nodes = [str(path) for path in (*net.places, *net.transitions) if str(path).startswith("effects.publish.")]
    assert sorted(fragment_nodes) == [
        "effects.publish.accept",
        "effects.publish.ack",
        "effects.publish.authorize",
        "effects.publish.done",
        "effects.publish.execute",
        "effects.publish.pending",
        "effects.publish.work",
    ]

    # The whole net — descent fragment included — still round-trips strictly.
    assert parse_net_definition(compiled.definition_bytes) == project_net_definition(net)


def test_activity_bindings_use_canonical_handler_uris_and_stable_operation_identity():
    compiled = compile_flow(readiness_flow())
    net = compiled.built.net

    for path in ("effects.rerun.fire", "effects.repair.fire", "effects.publish.execute"):
        uri = net.handler_uri(NetPath(path))
        assert uri is not None
        assert isinstance(compiled.handlers[uri], ActivityHandler)

    handler = compiled.handlers[net.handler_uri(NetPath("effects.rerun.fire"))]
    request = RerunRequested("rerun:L2:build", "h2", "L2", "build", Evidence(20, 1))
    binding = Binding(
        NetPath("effects.rerun.fire"),
        consumed=((NetPath("commands.rerun"), (Token("RerunRequested", to_data(request)),)),),
    )

    invocation = handler.prepare(binding)

    assert invocation.activity == "rerun"
    assert invocation.correlation == "rerun:L2:build"
    assert invocation.idempotency == "rerun:L2:build"
    assert invocation.policy.attempts == 1
