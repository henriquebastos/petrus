"""Bounded implementation-free simulation production."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from tests.simulation_support import build_scenario, export
import tests.simulation_support as export_application
from petrus.engine import Engine
from petrus.impetus.dsl import BuiltNet
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.petrinet import ANONYMOUS, Arc, Cel, Delay, Marking, Net, NetPath, Place, Token, Transition
from petrus.motus.dispatch import InlineDispatch
from petrus.simulation import SimulationProfileError, simulate
import petrus.simulation as simulation

FIXTURE = Path("spec/net-document-v1-simulation.json")
A, T = NetPath("a"), NetPath("t")


def strict_json(payload: bytes) -> Any:
    def object_without_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key {key!r}")
            result[key] = value
        return result

    def refuse_constant(value):
        raise ValueError(f"nonfinite number {value}")

    return json.loads(payload, object_pairs_hook=object_without_duplicates, parse_constant=refuse_constant)


def entries(document: dict[str, Any]) -> list[dict[str, Any]]:
    return document["lineage"]["entries"]


def summary(document: dict[str, Any]) -> dict[str, Any]:
    return entries(document)[0]["metadata"]


def records(document: dict[str, Any]) -> list[dict[str, Any]]:
    return [entry["metadata"]["history_record"] for entry in entries(document)]


def current_marking(document: dict[str, Any]) -> list[dict[str, Any]]:
    return entries(document)[document["lineage"]["head"]]["marking"]


def test_owner_fixture_is_exact_strict_and_complete() -> None:
    built, marking = build_scenario()
    payload = simulate(built, marking, max_actions=32)
    result = strict_json(payload)

    assert payload == FIXTURE.read_bytes()
    assert result["format"] == "petrus-net-document"
    assert result["version"] == 1
    assert [entry["id"] for entry in entries(result)] == list(range(len(entries(result))))
    assert all(entry["provenance"] == "simulated" for entry in entries(result))
    events = [record["record"] for record in records(result)]
    assert events.count("TimerMatured") == 1
    assert summary(result)["status"] == "completed"
    assert summary(result)["outcome"]["actions_applied"] == 2


def test_rest_and_exact_action_limit_have_no_extra_probe() -> None:
    idle = BuiltNet(Net([Place(A)], [], []))
    assert summary(strict_json(simulate(idle, Marking(), max_actions=1)))["outcome"] == {
        "actions_applied": 0,
        "reason": "rest",
    }

    loop = BuiltNet(Net([Place(A)], [Transition(T)], [Arc(A, T), Arc(T, A)]))
    limited = strict_json(simulate(loop, Marking({A: (Token.black(),)}), max_actions=3))
    assert summary(limited)["outcome"] == {"actions_applied": 3, "reason": "action_limit"}
    assert sum(record["record"] == "FiringCompleted" for record in records(limited)) == 3


@pytest.mark.parametrize("value", [True, False, 0, -1, 257, 1.5, "1"])
def test_max_actions_is_a_positive_bounded_non_boolean_integer(value) -> None:
    with pytest.raises(SimulationProfileError, match="max_actions"):
        simulate(BuiltNet(Net([], [], [])), Marking(), max_actions=value)


@pytest.mark.parametrize("declaration", ["named", ANONYMOUS])
def test_named_and_anonymous_handlers_are_refused_before_engine_creation(declaration) -> None:
    built = BuiltNet(Net([], [Transition(T, handler=declaration)], []))
    with pytest.raises(SimulationProfileError, match="handler.*absent"):
        simulate(built, Marking(), max_actions=1)


def test_implementation_maps_and_non_json_tokens_are_refused() -> None:
    net = Net([Place(A)], [Transition(T, handler="named")], [])
    handler_uri = net.handler_uri(T)
    assert handler_uri is not None
    with pytest.raises(SimulationProfileError, match="handler implementations"):
        simulate(BuiltNet(net, handlers={handler_uri: lambda *_: {}}), Marking(), max_actions=1)
    with pytest.raises(SimulationProfileError, match="strict JSON-faithful"):
        simulate(BuiltNet(Net([Place(A)], [], [])), Marking({A: (Token("X", float("nan")),)}), max_actions=1)


def test_graph_initial_token_and_payload_bounds() -> None:
    too_many_places = BuiltNet(Net([Place(NetPath(f"p{n}")) for n in range(129)], [], []))
    with pytest.raises(SimulationProfileError, match="places limit"):
        simulate(too_many_places, Marking(), max_actions=1)
    with pytest.raises(SimulationProfileError, match="initial token limit"):
        simulate(
            BuiltNet(Net([Place(A)], [], [])),
            Marking({A: (Token.black(),) * 513}),
            max_actions=1,
        )


def test_transition_arc_cel_definition_and_result_bounds(monkeypatch) -> None:
    monkeypatch.setattr(simulation, "MAX_TRANSITIONS", 0)
    with pytest.raises(SimulationProfileError, match="transitions limit"):
        simulate(BuiltNet(Net([], [Transition(T)], [])), Marking(), max_actions=1)
    monkeypatch.setattr(simulation, "MAX_TRANSITIONS", 128)
    monkeypatch.setattr(simulation, "MAX_ARCS", 0)
    with pytest.raises(SimulationProfileError, match="arcs limit"):
        simulate(BuiltNet(Net([Place(A)], [Transition(T)], [Arc(A, T)])), Marking(), max_actions=1)
    monkeypatch.setattr(simulation, "MAX_ARCS", 512)
    monkeypatch.setattr(simulation, "MAX_CEL_BYTES", 1)
    with pytest.raises(SimulationProfileError, match="CEL expression limit"):
        simulate(
            BuiltNet(Net([Place(A)], [Transition(T, guards=(Cel("xx"),))], [Arc(A, T)])),
            Marking(),
            max_actions=1,
        )
    monkeypatch.setattr(simulation, "MAX_CEL_BYTES", 4096)
    monkeypatch.setattr(simulation, "MAX_DEFINITION_BYTES", 1)
    with pytest.raises(SimulationProfileError, match="definition limit"):
        simulate(BuiltNet(Net([], [], [])), Marking(), max_actions=1)
    monkeypatch.setattr(simulation, "MAX_DEFINITION_BYTES", 1_000_000)
    monkeypatch.setattr(simulation, "MAX_RESULT_BYTES", 1)
    with pytest.raises(SimulationProfileError, match="serialized result limit"):
        simulate(BuiltNet(Net([], [], [])), Marking(), max_actions=1)


def test_retained_history_and_candidate_work_limits_precede_next_advance(monkeypatch) -> None:
    loop = BuiltNet(Net([Place(A)], [Transition(T)], [Arc(A, T), Arc(T, A)]))
    marking = Marking({A: (Token.black(),)})
    monkeypatch.setattr(simulation, "MAX_RETAINED_TOKENS", 0)
    with pytest.raises(SimulationProfileError, match="retained token limit"):
        simulate(loop, marking, max_actions=1)
    monkeypatch.setattr(simulation, "MAX_RETAINED_TOKENS", 4096)
    monkeypatch.setattr(simulation, "MAX_HISTORY_RECORDS", 0)
    with pytest.raises(SimulationProfileError, match="History record limit"):
        simulate(loop, marking, max_actions=1)
    monkeypatch.setattr(simulation, "MAX_HISTORY_RECORDS", 50_000)
    monkeypatch.setattr(simulation, "MAX_RETAINED_PAYLOAD_BYTES", 1)
    with pytest.raises(SimulationProfileError, match="retained token payload limit"):
        simulate(loop, marking, max_actions=1)
    monkeypatch.setattr(simulation, "MAX_RETAINED_PAYLOAD_BYTES", 4_194_304)
    monkeypatch.setattr(simulation, "MAX_HISTORY_PAYLOAD_BYTES", 1)
    with pytest.raises(SimulationProfileError, match="History payload limit"):
        simulate(loop, marking, max_actions=1)
    monkeypatch.setattr(simulation, "MAX_HISTORY_PAYLOAD_BYTES", 4_194_304)
    monkeypatch.setattr(simulation, "MAX_CANDIDATE_OFFERS", 0)
    calls = 0

    def forbidden_advance(self):
        nonlocal calls
        calls += 1
        raise AssertionError("advance reached")

    monkeypatch.setattr(Engine, "advance", forbidden_advance)
    with pytest.raises(SimulationProfileError, match="reachable input-scan limit"):
        simulate(loop, marking, max_actions=1)
    assert calls == 0


def test_legal_graph_cross_transition_scan_sum_is_refused_before_engine_create(monkeypatch) -> None:
    transitions = [Transition(NetPath(f"t{position}")) for position in range(20)]
    arcs = [Arc(A, transition.path) for transition in transitions]
    built = BuiltNet(Net([Place(A)], transitions, arcs))
    marking = Marking({A: (Token.black(),) * 512})

    def forbidden_create(*args, **kwargs):
        raise AssertionError("Engine.create reached")

    monkeypatch.setattr(Engine, "create", forbidden_create)
    with pytest.raises(SimulationProfileError, match="reachable input-scan limit.*bound 10240"):
        simulate(built, marking, max_actions=1)


def test_completion_reports_completed_without_halting_an_enabled_action() -> None:
    b = NetPath("b")
    done = NetPath("done")
    built = BuiltNet(
        Net(
            [Place(A), Place(b), Place(done)],
            [Transition(T)],
            [Arc(b, T), Arc(T, done)],
            completion=Cel("size(a) > 0"),
        )
    )
    result = strict_json(simulate(built, Marking({A: (Token.black(),), b: (Token.black(),)}), max_actions=2))
    assert summary(result)["outcome"] == {"actions_applied": 1, "reason": "rest"}
    assert summary(result)["status"] == "completed"
    assert current_marking(result) == [
        {"place": "a", "tokens": [{"color": None, "data": None}]},
        {"place": "done", "tokens": [{"color": None, "data": None}]},
    ]


def test_simulation_does_not_change_a_separate_live_engine() -> None:
    net = Net([Place(A)], [], [])
    live = Engine.create(
        net,
        "live",
        history=InMemoryHistoryStore(),
        dispatch=InlineDispatch({}),
        marking=Marking({A: (Token.black(),)}),
        at=0,
    )
    try:
        before_marking = live.marking
        before_records = live.records
        simulate(BuiltNet(net), Marking(), max_actions=1)
        assert live.marking == before_marking
        assert live.records == before_records
    finally:
        live.close()


def test_admission_is_field_complete_and_precedes_engine_create(monkeypatch) -> None:
    reached = False

    def forbidden_create(*args, **kwargs):
        nonlocal reached
        reached = True
        raise AssertionError("Engine.create reached")

    monkeypatch.setattr(Engine, "create", forbidden_create)
    cases = []
    malformed_timer = Delay(-1)
    cases.append(
        (
            BuiltNet(Net([Place(A)], [Transition(T, timers=(malformed_timer,))], [Arc(A, T)])),
            Marking(),
            "non-negative",
        )
    )
    cases.append((BuiltNet(Net([Place(A)], [], [])), Marking({NetPath("foreign"): (Token.black(),)}), "foreign place"))
    cases.append(
        (
            BuiltNet(Net([Place(A)], [], [])),
            Marking(cast(Any, {A: (SimpleNamespace(color=None, data=None),)})),
            "exactly Token",
        )
    )
    cases.append((BuiltNet(Net([Place(A, "X")], [], [])), Marking({A: (Token("Y"),)}), "does not match"))
    cases.append((BuiltNet(Net([Place(A)], [Transition(T, guards=("named",))], [Arc(A, T)])), Marking(), "inline Cel"))
    cases.append(
        (BuiltNet(Net([Place(A)], [Transition(T, guards=(ANONYMOUS,))], [Arc(A, T)])), Marking(), "inline Cel")
    )
    cases.append((BuiltNet(Net([Place(A)], [Transition(T)], [Arc(A, T, filter="named")])), Marking(), "filter"))
    anonymous_filter = Net([Place(A)], [Transition(T)], [Arc(A, T)])
    object.__setattr__(anonymous_filter.arcs[0], "filter", ANONYMOUS)
    cases.append((BuiltNet(anonymous_filter), Marking(), "filter"))
    cases.append((BuiltNet(Net([], [], [], completion="named")), Marking(), "completion"))
    anonymous_completion = Net([], [], [])
    anonymous_completion.completion = cast(Any, ANONYMOUS)
    cases.append((BuiltNet(anonymous_completion), Marking(), "completion"))
    named_guard_net = Net([Place(A)], [Transition(T, guards=("named",))], [Arc(A, T)])
    cases.append(
        (
            BuiltNet(named_guard_net, guards={named_guard_net.guard_uris(T)[0]: lambda _: True}),
            Marking(),
            "guard implementations",
        )
    )
    cases.append((BuiltNet(Net([], [Transition(T, handler="named")], [])), Marking(), "handler"))
    cases.append((BuiltNet(Net([Place(A)], [], [])), Marking({A: (Token("X", float("inf")),)}), "strict JSON"))
    for built, marking, message in cases:
        with pytest.raises(SimulationProfileError, match=message):
            simulate(built, marking, max_actions=1)
    assert not reached


def test_malformed_weight_and_multiple_selecting_inputs_are_explicitly_refused(monkeypatch) -> None:
    arc = Arc(A, T)
    object.__setattr__(arc, "weight", True)
    with pytest.raises(SimulationProfileError, match="exact non-boolean integer 1"):
        simulate(BuiltNet(Net([Place(A)], [Transition(T)], [arc])), Marking(), max_actions=1)
    b = NetPath("b")
    with pytest.raises(SimulationProfileError, match="at most one selecting"):
        simulate(
            BuiltNet(Net([Place(A), Place(b)], [Transition(T)], [Arc(A, T), Arc(b, T)])),
            Marking(),
            max_actions=1,
        )


def test_read_selection_and_output_fanout_are_refused_before_engine_create(monkeypatch) -> None:
    b = NetPath("b")
    c = NetPath("c")

    def forbidden_create(*args, **kwargs):
        raise AssertionError("Engine.create reached")

    monkeypatch.setattr(Engine, "create", forbidden_create)
    read_arc = Arc(A, T)
    read_net = Net([Place(A)], [Transition(T)], [read_arc])
    object.__setattr__(read_net.arcs[0], "mode", simulation.ArcMode.READ)
    with pytest.raises(SimulationProfileError, match="selecting input arc to consume"):
        simulate(
            BuiltNet(read_net),
            Marking({A: (Token.black(),)}),
            max_actions=1,
        )
    with pytest.raises(SimulationProfileError, match="at most one output arc"):
        simulate(
            BuiltNet(Net([Place(A), Place(b), Place(c)], [Transition(T)], [Arc(A, T), Arc(T, b), Arc(T, c)])),
            Marking({A: (Token("X", "x" * 999_000),)}),
            max_actions=1,
        )


def test_consume_plus_many_inhibits_is_rejected_by_reachable_scan_bound(monkeypatch) -> None:
    blocker = NetPath("blocker")
    transition = Transition(T)
    arcs = [Arc(A, T)] + [Arc(blocker, T, mode=simulation.ArcMode.INHIBIT) for _ in range(20)]
    built = BuiltNet(Net([Place(A), Place(blocker)], [transition], arcs))
    marking = Marking({A: (Token.black(),), blocker: (Token.black(),) * 511})

    def forbidden_create(*args, **kwargs):
        raise AssertionError("Engine.create reached")

    monkeypatch.setattr(Engine, "create", forbidden_create)
    with pytest.raises(SimulationProfileError, match="reachable input-scan limit"):
        simulate(built, marking, max_actions=1)


def test_mutating_input_after_simulate_cannot_change_returned_bytes() -> None:
    data = {"nested": [1]}
    payload = simulate(BuiltNet(Net([Place(A)], [], [])), Marking({A: (Token("X", data),)}), max_actions=1)
    data["nested"].append(2)
    assert summary(strict_json(payload))["scenario"]["initial_marking"][0]["tokens"][0]["data"] == {"nested": [1]}


def test_dispatch_is_structurally_impossible() -> None:
    with pytest.raises(SimulationProfileError, match="forbids Dispatch"):
        simulation._ForbiddenDispatch().dispatch(None, None)
    with pytest.raises(SimulationProfileError, match="payload limit"):
        simulate(
            BuiltNet(Net([Place(A)], [], [])),
            Marking({A: (Token("X", "x" * 1_000_001),)}),
            max_actions=1,
        )


def test_failed_atomic_replace_preserves_the_previous_destination(tmp_path: Path, monkeypatch) -> None:
    destination = tmp_path / "result.petrus-simulation.json"
    destination.write_bytes(b"previous")

    def fail_replace(source, target):
        del source, target
        raise OSError("replace failed")

    monkeypatch.setattr(export_application.os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        export(destination)
    assert destination.read_bytes() == b"previous"
    assert list(tmp_path.iterdir()) == [destination]


@pytest.mark.parametrize("failure", ["write", "fsync"])
def test_failed_temp_publication_preserves_destination_and_cleans_temp(tmp_path: Path, monkeypatch, failure) -> None:
    destination = tmp_path / "result.petrus-simulation.json"
    destination.write_bytes(b"previous")
    if failure == "write":
        original = export_application.tempfile.NamedTemporaryFile

        class RefusingWrite:
            def __init__(self, stream):
                self.stream = stream
                self.name = stream.name

            def __enter__(self):
                self.stream.__enter__()
                return self

            def __exit__(self, *args):
                return self.stream.__exit__(*args)

            def write(self, payload):
                del payload
                raise OSError("write failed")

        monkeypatch.setattr(
            export_application.tempfile,
            "NamedTemporaryFile",
            lambda **kwargs: RefusingWrite(original(**kwargs)),
        )
    else:
        monkeypatch.setattr(export_application.os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("fsync failed")))
    with pytest.raises(OSError, match=f"{failure} failed"):
        export(destination)
    assert destination.read_bytes() == b"previous"
    assert list(tmp_path.iterdir()) == [destination]
