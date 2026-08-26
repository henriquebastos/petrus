"""Same runtime IR under a richer source: topology, bytes, and case attribution."""

import hashlib
from pathlib import Path

from petrus.impetus.binding import ActivityHandler
from petrus.impetus.net_definition import compile_net_definition, parse_net_definition, project_net_definition
from petrus.impetus.petrinet import ArcMode, NetPath, Token
from petrus.impetus.petrinet.dot import to_dot
from petrus.impetus.petrinet.enabledness import Binding

from algebra import await_event, effect, lifecycle, low_level, terminal
from domain import (
    CIObserved,
    Evidence,
    HeadObserved,
    HumanNeeded,
    PublishAcknowledged,
    PublishRequested,
    ReadinessState,
    RepairRequested,
    RerunRequested,
    to_data,
)
from scenario import accept_publish, admit_head, publication_gate
from source_map import serialize_source_map
from table_algebra import Match, case, machine, on
from table_lowering import compile_flow
from table_scenario import (
    advance,
    keep,
    not_newer,
    readiness_flow,
    refresh_ladder,
    repair,
    rerun,
)

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "golden"
V1_NET_GOLDEN = HERE.parent / "typed-flow-vertical-slice" / "golden" / "readiness.net-v3.json"

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

# The fixed durable-transition table, identical to v1's. Eight authored rungs
# still lower to exactly one decision transition with seven arcs.
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


def test_repeated_lowering_is_byte_stable_and_matches_the_v1_net_v3_golden():
    """The experiment's thesis: a richer source, the identical runtime IR."""
    first = compile_flow(readiness_flow())
    second = compile_flow(readiness_flow())

    assert first.definition_bytes == second.definition_bytes
    assert first.definition_bytes == V1_NET_GOLDEN.read_bytes()


def test_net_v3_round_trips_through_current_parser_and_compiler():
    compiled = compile_flow(readiness_flow())

    document = parse_net_definition(compiled.definition_bytes)
    net = compile_net_definition(document)

    assert project_net_definition(net) == document
    assert to_dot(compiled.built.net).startswith("digraph")
    fresh = compile_net_definition(parse_net_definition(compile_flow(readiness_flow()).definition_bytes))
    assert to_dot(net) == to_dot(fresh)


def test_expected_topology_has_only_durable_transitions():
    net = compile_flow(readiness_flow()).built.net

    assert {str(path) for path in net.places} == EXPECTED_PLACES
    assert {str(path) for path in net.transitions} == {name for name, _ in EXPECTED_ARC_COUNTS}
    assert len(net.arcs) == 28

    attached = []
    for candidate in net.arcs:
        transition = candidate.source if candidate.source in net.transitions else candidate.target
        attached.append(str(transition))
    expected = [name for name, count in EXPECTED_ARC_COUNTS for _ in range(count)]
    assert attached == expected


def test_one_decision_lowers_to_one_transition_regardless_of_rung_count():
    """Adding an absorbing rung is a source-only change: the IR does not move."""
    baseline = compile_flow(readiness_flow())
    grown = compile_flow(_flow_with_extra_absorbing_rung())

    assert len(grown.cases) == len(baseline.cases) + 1
    assert len(grown.built.net.transitions) == len(baseline.built.net.transitions) == 9
    assert len(grown.built.net.arcs) == len(baseline.built.net.arcs) == 28
    assert grown.definition_bytes == baseline.definition_bytes


def never(state: ReadinessState, event: CIObserved) -> bool:
    """A rung that never claims an observation; present only to grow the table."""
    del state, event
    return False


def _flow_with_extra_absorbing_rung():
    return machine(
        "readiness",
        lifecycle=lifecycle("branch"),
        handlers=(
            on(await_event("head", HeadObserved)).project("admit_head", admit_head),
            on(await_event("ci", CIObserved))
            .match(
                "route_ci",
                normalize=refresh_ladder,
                cases=(
                    case("quarantined", when=never, fold=keep).drop(),
                    *_authored_cases(),
                ),
            )
            .choose(
                {
                    PublishRequested: low_level("publish_once", publication_gate, returns=PublishAcknowledged),
                    RerunRequested: effect("rerun", rerun),
                    RepairRequested: effect("repair", repair),
                    HumanNeeded: terminal("human_needed"),
                }
            ),
            on(PublishAcknowledged).fold("accept_publish", accept_publish).to(terminal("published")),
        ),
    )


def _authored_cases():
    table = next(step for step in readiness_flow().handlers[1].steps if isinstance(step, Match))
    return table.cases


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

    for path in net.transitions:
        if net.handler_uri(path) is not None:
            assert source_map.element_for(str(path)) is not None


def test_every_authored_case_and_the_normalize_step_has_its_own_source_map_entry():
    """The attribution v1 could not give: one source entry per rung."""
    compiled = compile_flow(readiness_flow())
    ids = {source.id: source for source in compiled.source_map.sources}

    expected = {
        "readiness.route_ci.foreign",
        "readiness.route_ci.stale",
        "readiness.route_ci.publish",
        "readiness.route_ci.published",
        "readiness.route_ci.unclassified",
        "readiness.route_ci.rerun",
        "readiness.route_ci.repair",
        "readiness.route_ci.human",
    }
    assert expected <= set(ids)
    assert all(ids[source_id].file == "table_scenario.py" for source_id in expected)
    assert len({ids[source_id].line for source_id in expected}) == len(expected)  # eight distinct lines

    normalize = ids["readiness.route_ci.normalize"]
    assert (normalize.file, normalize.symbol) == ("table_scenario.py", "refresh_ladder")

    # The case index the explained History joins on.
    by_case = {entry.case_id: entry for entry in compiled.cases}
    assert by_case["stale"].when == "not_newer" and by_case["stale"].emit_color is None
    assert by_case["human"].when == "otherwise" and by_case["human"].emit_color == "HumanNeeded"
    assert [entry.case_id for entry in compiled.absorbing_cases] == [
        "foreign",
        "stale",
        "published",
        "unclassified",
    ]
    assert compiled.case_for_color("RerunRequested") is by_case["rerun"]
    assert compiled.case_for_color(None) is None


def test_source_map_is_stable_hash_bound_and_matches_golden():
    first = compile_flow(readiness_flow())
    second = compile_flow(readiness_flow())

    assert serialize_source_map(first.source_map) == serialize_source_map(second.source_map)
    assert first.source_map.definition_sha256 == hashlib.sha256(first.definition_bytes).hexdigest()
    assert serialize_source_map(first.source_map) == (GOLDEN / "readiness.source-map-v1.json").read_bytes()


def test_low_level_publication_gate_uses_an_inhibitor_and_canonical_validation():
    """The v1 descent fragment is imported unchanged and still validates."""
    compiled = compile_flow(readiness_flow())
    net = compiled.built.net

    inhibitors = [candidate for candidate in net.arcs if candidate.mode is ArcMode.INHIBIT]
    assert {(str(candidate.source), str(candidate.target)) for candidate in inhibitors} == {
        ("effects.publish.pending", "effects.publish.authorize"),
        ("effects.publish.done", "effects.publish.authorize"),
    }
    assert parse_net_definition(compiled.definition_bytes) == project_net_definition(net)
    gate = compiled.source_map.source_for("readiness.publish_once")
    assert gate is not None and gate.file == "scenario.py"  # imported read-only from the v1 slice


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
    assert invocation.correlation == invocation.idempotency == "rerun:L2:build"
    assert invocation.policy.attempts == 1


def test_helper_calculations_and_predicates_create_no_nodes():
    """``not_newer``/``advance`` and friends are ordinary code, never transitions."""
    net = compile_flow(readiness_flow()).built.net

    symbols = {not_newer.__name__, advance.__name__, keep.__name__, refresh_ladder.__name__}
    paths = {str(path) for path in (*net.places, *net.transitions)}
    assert not any(symbol in path for symbol in symbols for path in paths)
