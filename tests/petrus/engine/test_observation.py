"""Focused protocol-v1 observation and Engine-coherence evidence."""

from __future__ import annotations

import json
import math
import threading
from pathlib import Path

import pytest

import petrus.engine as engine_module
from petrus.engine import Engine
from petrus.impetus.dsl import NetSpec, arc, petri_handler
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.observation import definition, net_inspection
from petrus.impetus.petrinet import (
    ANONYMOUS,
    Arc,
    ArcMode,
    Cel,
    Delay,
    Marking,
    Net,
    NetPath,
    Place,
    Token,
    Transition,
    Until,
)
from petrus.motus.activity import ActivityInvocation
from petrus.motus.dispatch import InMemoryDispatch

FIXTURE_DIR = Path(__file__).parents[3] / "spec" / "observation"
SNAPSHOT_FIXTURE = FIXTURE_DIR / "engine-snapshot-v1.json"
HISTORY_FIXTURE = FIXTURE_DIR / "engine-history-page-v1.json"
CAPTURE_FIXTURE = FIXTURE_DIR / "engine-capture-v1.json"
NET_INSPECTION_FIXTURE = FIXTURE_DIR / "canonical-net-inspection-v1.json"
A, B, C = NetPath("a"), NetPath("b"), NetPath("c")
SOURCE, WORK = NetPath("source"), NetPath("work")


def strict_json(value: str) -> object:
    def object_without_duplicates(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON member {key!r}")
            result[key] = value
        return result

    def refuse_constant(value):
        raise ValueError(f"non-finite JSON number {value}")

    return json.loads(value, object_pairs_hook=object_without_duplicates, parse_constant=refuse_constant)


def strict_fixture(path: Path) -> object:
    return strict_json(path.read_text())


class Bridge:
    def prepare(self, binding):
        return ActivityInvocation(
            "canonical.activity",
            input={"nested": [binding.tokens[0].data]},
            correlation="canonical-correlation",
            idempotency="canonical-idempotency",
        )

    def project(self, binding, result):
        return {B: (Token("Done", result),)}


def canonical_engine(*, history=None, dispatch=None) -> Engine:
    net = Net(
        places=[Place(C), Place(A, "Input"), Place(B, "Done")],
        transitions=[Transition(WORK, handler="bridge"), Transition(SOURCE)],
        arcs=[Arc(SOURCE, C), Arc(A, WORK), Arc(WORK, B)],
        completion=Cel("size(b) > 0"),
        name="canonical-observation",
    )
    engine = Engine.create(
        net,
        "canonical-instance",
        history=history or InMemoryHistoryStore(),
        dispatch=dispatch or InMemoryDispatch(),
        marking=Marking({A: (Token("Input", {"ordinal": 1}), Token("Input", {"ordinal": 2}))}),
        handlers={"bridge": Bridge()},
        at=7,
    )
    assert engine.advance().ready
    return engine


def test_exact_definition_shape_order_declarations_uris_and_duplicate_arcs():
    z, t, z_place = NetPath("z"), NetPath("t"), NetPath("z-place")
    net = Net(
        places=[Place(z_place), Place(A, "Input")],
        transitions=[
            Transition(z, handler=ANONYMOUS),
            Transition(
                t,
                handler="named_handler",
                guards=("named_guard", ANONYMOUS, Cel("true")),
                timers=(Until(11), Delay(3)),
            ),
        ],
        arcs=[
            Arc(A, t, color="Input", filter="named_filter"),
            Arc(t, z_place),
            Arc(t, z_place),
            Arc(z_place, t, mode=ArcMode.READ, filter=Cel("true")),
        ],
        completion="done",
        name="shape",
    )

    projected = definition(net)

    assert [place["path"] for place in projected["places"]] == ["a", "z-place"]
    assert [transition["path"] for transition in projected["transitions"]] == ["t", "z"]
    transition = projected["transitions"][0]
    assert transition["handler"] == {
        "kind": "symbol",
        "name": "named_handler",
        "uri": "transition:/t#handler",
    }
    assert transition["guards"] == [
        {"kind": "symbol", "name": "named_guard", "uri": "transition:/t#guard:named_guard"},
        {"kind": "anonymous", "uri": "transition:/t#guard:$1"},
        {"kind": "cel", "expression": "true", "uri": "transition:/t#guard:$2"},
    ]
    assert transition["timers"] == [{"kind": "until", "instant": 11}, {"kind": "delay", "duration": 3}]
    assert [arc["position"] for arc in projected["arcs"]] == [0, 1, 2, 3]
    assert projected["arcs"][1] != projected["arcs"][2]
    assert projected["arcs"][0]["color"] == "Input"
    assert projected["arcs"][0]["filter"] == {"kind": "symbol", "name": "named_filter"}
    assert projected["arcs"][3]["filter"] == {"kind": "cel", "expression": "true"}
    assert {arc["filter"]["kind"] for arc in projected["arcs"] if arc["filter"] is not None} == {
        "symbol",
        "cel",
    }
    assert projected["transitions"][1]["handler"] == {
        "kind": "anonymous",
        "uri": "transition:/z#handler",
    }
    assert projected["transitions"][1]["handler"] is not None
    assert definition(Net([Place(A)], [Transition(SOURCE)], [Arc(SOURCE, A)]))["transitions"][0]["handler"] is None
    assert projected["completion"] == {"kind": "symbol", "name": "done"}
    assert "display_name" not in json.dumps(projected)
    assert "implementation" not in json.dumps(projected)


def test_canonical_net_inspection_fixture_is_exact_pre_instance_dsl_build_without_implementations():
    handler = lambda binding, outputs: {}  # noqa: E731 - implementation omission is under test
    lens = NetSpec("lens")
    review = lens.t.review(
        handler=petri_handler(handler),
        guards=("ready", Cel("true")),
        timers=(Delay(3), Until(11)),
    )
    lens.p.pending("Work") >> review >> lens.p.done("Done")
    lens.p.context("Context") >> arc.read(filter=Cel("true")) >> review
    lens.p.blocked("Block") >> arc.inhibit(filter="same_key") >> review

    root = NetSpec("canonical-design", completion=Cel("size(review.correctness.done) > 0"))
    correctness = root.s.review.s.correctness.stamp(lens)
    root.t.ingest >> correctness.p.pending
    correctness.t.review >> correctness.p.done
    built = root.build()

    produced = net_inspection(built.net)
    expected = strict_fixture(NET_INSPECTION_FIXTURE)

    assert expected == produced
    assert produced["format"] == "petrus-canonical-net-inspection"
    assert type(produced["version"]) is int and produced["version"] == 1
    assert produced["definition"] == definition(built.net)
    assert [arc["position"] for arc in produced["definition"]["arcs"]] == list(
        range(len(produced["definition"]["arcs"]))
    )
    parallel = [
        item
        for item in produced["definition"]["arcs"]
        if item["source"] == "review.correctness.review" and item["target"] == "review.correctness.done"
    ]
    assert [item["position"] for item in parallel] == [1, 5]
    encoded = json.dumps(produced, allow_nan=False)
    assert strict_json(encoded) == produced
    assert "canonical-instance" not in encoded
    assert "implementation" not in encoded
    assert "display_name" not in encoded
    assert "<lambda>" not in encoded
    assert set(built.handlers.values()) == {handler}


def test_canonical_fixture_is_exact_producer_output_and_has_typed_fifo_activity_pending_state():
    produced = canonical_engine().snapshot()
    expected = json.loads(SNAPSHOT_FIXTURE.read_text())

    assert expected == produced
    assert produced["current"]["marking"] == [{"place": "a", "tokens": [{"color": "Input", "data": {"ordinal": 2}}]}]
    occurrence = produced["current"]["in_flight"][0]
    assert occurrence["phase"] == "activity_pending"
    assert produced["current"]["armed"] == [{"source": "source", "key": "default"}]
    assert isinstance(produced["current"]["watermark"], int)


def test_canonical_history_fixture_is_exact_complete_page_with_schema4_typed_occurrences():
    engine = canonical_engine()
    produced = engine.history_page(0, 100)
    expected = json.loads(HISTORY_FIXTURE.read_text())

    assert expected == produced
    assert [item["position"] for item in produced["records"]] == list(range(produced["frontier"]))
    assert produced["next"] == produced["frontier"]
    assert all(item["record"]["schema"] == 4 for item in produced["records"])
    typed_tokens = [token for item in produced["records"] for token in item["record"].get("tokens", [])]
    assert {token["color"] for token in typed_tokens} >= {"Input"}
    occurrence_records = [item["record"] for item in produced["records"] if "occurrence" in item["record"]]
    assert occurrence_records
    assert {record["occurrence"] for record in occurrence_records if record["occurrence"] is not None} == {1}


def test_protocol_v1_history_transports_canonical_schema4_and_schema5_records_without_changing_unscoped_bytes():
    engine = canonical_engine()
    scope = engine.open_scope("draft")
    engine.deliver(SOURCE, Token("External", 1), identity="draft-1", scope=scope)
    engine.close_scope(scope)

    page = engine.history_page(0, 100)

    assert page["protocol"] == 1
    assert {item["record"]["schema"] for item in page["records"]} == {4, 5}
    lifecycle = [item["record"] for item in page["records"] if item["record"]["schema"] == 5]
    assert [record["record"] for record in lifecycle if record["record"].startswith("Scope")] == [
        "ScopeOpened",
        "ScopeClosed",
    ]
    assert all(record.get("scope", {}).get("name") == "draft" for record in lifecycle)
    assert page["records"][0]["record"]["schema"] == 4


def test_canonical_capture_fixture_is_exact_snapshot_and_complete_history_prefix():
    engine = canonical_engine()
    captured_snapshot = engine.snapshot()
    frontier = captured_snapshot["frontier"]
    captured_history = engine.history_page(0, frontier)
    produced = {
        "format": "petrus-observation-capture",
        "version": 1,
        "snapshot": captured_snapshot,
        "history": captured_history,
    }
    expected = json.loads(CAPTURE_FIXTURE.read_text())

    assert expected == produced
    assert captured_history["protocol"] == captured_snapshot["protocol"]
    assert captured_history["instance"] == captured_snapshot["instance"]
    assert captured_history["after"] == 0
    assert captured_history["next"] == captured_history["frontier"] == frontier
    assert [item["position"] for item in captured_history["records"]] == list(range(frontier))
    created = [item for item in captured_history["records"] if item["record"]["record"] == "InstanceCreated"]
    assert frontier >= 1
    assert created == [captured_history["records"][0]]
    assert created[0]["record"]["schema"] == 4
    assert created[0]["record"]["instance"] == captured_snapshot["instance"]


def test_capture_pages_freeze_snapshot_frontier_while_history_continues_to_append():
    engine = canonical_engine()
    captured_snapshot = engine.snapshot()
    frontier = captured_snapshot["frontier"]
    cursor = 0
    observed_frontier = frontier
    positions = []

    while cursor < frontier:
        limit = min(2, frontier - cursor)
        page = engine.history_page(cursor, limit)
        assert page["after"] == cursor
        assert page["protocol"] == captured_snapshot["protocol"]
        assert page["instance"] == captured_snapshot["instance"]
        assert page["frontier"] >= observed_frontier
        assert page["next"] == min(cursor + limit, page["frontier"])
        assert page["next"] <= frontier
        assert [item["position"] for item in page["records"]] == list(range(cursor, page["next"]))
        positions.extend(item["position"] for item in page["records"])
        cursor = page["next"]
        observed_frontier = page["frontier"]
        if cursor == 2:
            engine.seal(SOURCE)

    assert observed_frontier > frontier
    assert positions == list(range(frontier))


def test_snapshot_reports_pure_and_projection_pending_phases_and_detaches_frozen_result():
    pure = Engine.create(
        Net([Place(A), Place(B)], [Transition(WORK)], [Arc(A, WORK), Arc(WORK, B)]),
        "pure-pending",
        history=InMemoryHistoryStore(),
        dispatch=InMemoryDispatch(),
        marking=Marking({A: (Token("Input", {"nested": [1]}),)}),
    )
    pure._instance.begin(pure._instance.candidates()[0])  # noqa: SLF001 - public Instance operations create the phase
    assert pure.snapshot()["current"]["in_flight"][0]["phase"] == "pure_pending"

    projection = canonical_engine()
    occurrence = projection.in_flight[0]
    result = {"nested": [{"value": 1}]}
    projection._instance.record_activity_completion(occurrence, result, at=8)  # noqa: SLF001 - no Engine result door
    observed = projection.snapshot()
    result["nested"][0]["value"] = 99
    pending = observed["current"]["in_flight"][0]
    assert pending["phase"] == "projection_pending"
    assert pending["result"] == {"nested": [{"value": 1}]}


def test_snapshot_detaches_nested_tokens_and_activity_values():
    token_data = {"items": [{"value": 1}]}
    engine = Engine.create(
        Net([Place(A), Place(B)], [Transition(WORK, handler="bridge")], [Arc(A, WORK), Arc(WORK, B)]),
        "detached",
        history=InMemoryHistoryStore(),
        dispatch=InMemoryDispatch(),
        marking=Marking({A: (Token("Input", token_data),)}),
        handlers={"bridge": Bridge()},
    )
    engine.advance()
    observed = engine.snapshot()
    token_data["items"][0]["value"] = 99
    engine._instance.in_flight[0].invocation.input["nested"][0]["items"].append({"value": 2})  # noqa: SLF001

    assert observed["current"]["in_flight"][0]["binding"]["consumed"][0]["tokens"][0]["data"] == {
        "items": [{"value": 1}]
    }
    assert observed["current"]["in_flight"][0]["invocation"]["input"] == {"nested": [{"items": [{"value": 1}]}]}


@pytest.mark.parametrize(
    ("timer", "message"),
    [
        (Delay(True), "Delay duration"),
        (Delay(1.5), "Delay duration"),
        (Delay("1"), "Delay duration"),
        (Until(True), "Until instant"),
        (Until(1.5), "Until instant"),
        (Until("1"), "Until instant"),
    ],
)
def test_protocol_strictly_refuses_non_integer_timer_values(timer, message):
    net = Net([Place(A)], [Transition(WORK, timers=(timer,))], [Arc(A, WORK)])
    with pytest.raises(ValueError, match=rf"{message}.*integer"):
        definition(net)


def test_definition_strictly_refuses_non_json_output():
    net = Net([Place(A)], [], [], name="valid")
    net.name = object()
    with pytest.raises(ValueError, match="strict JSON-faithful"):
        definition(net)


def test_snapshot_emits_integer_next_maturation_and_refuses_boolean_when_reachable():
    engine = Engine.create(
        Net([Place(A)], [Transition(WORK, timers=(Delay(5),))], [Arc(A, WORK)]),
        "timed",
        history=InMemoryHistoryStore(),
        dispatch=InMemoryDispatch(),
        marking=Marking({A: (Token("X"),)}),
        at=2,
    )
    assert engine.snapshot()["current"]["next_maturation"] == 7

    bad = Engine.create(
        Net([Place(A)], [Transition(WORK, timers=(Until(True),))], [Arc(A, WORK)]),
        "bad-timed",
        history=InMemoryHistoryStore(),
        dispatch=InMemoryDispatch(),
        marking=Marking({A: (Token("X"),)}),
    )
    with pytest.raises(ValueError, match="next maturation.*integer"):
        bad.snapshot()


@pytest.mark.parametrize("after,limit", [(-1, 1), (True, 1), (0.5, 1), (0, 0), (0, True), (0, 1.5)])
def test_history_page_refuses_malformed_cursor_or_limit(after, limit):
    engine = canonical_engine()
    with pytest.raises(ValueError):
        engine.history_page(after, limit)


def test_strict_json_refuses_nonfinite_and_unencodable_nested_data_and_bad_current_time():
    for data in ({"bad": math.nan}, {"bad": object()}):
        engine = Engine.create(
            Net([Place(A)], [], []),
            "bad-data",
            history=InMemoryHistoryStore(),
            dispatch=InMemoryDispatch(),
            marking=Marking({A: (Token("X", data),)}),
        )
        with pytest.raises(ValueError, match="strict JSON-faithful"):
            engine.snapshot()
    engine = canonical_engine()
    engine._instance._watermark = True  # noqa: SLF001
    with pytest.raises(ValueError, match="watermark.*integer"):
        engine.snapshot()


def test_cursor_algebra_polling_concurrent_arrival_and_reconnect_have_no_gap_or_duplicate():
    engine = canonical_engine()
    frontier = engine.snapshot()["frontier"]
    first = engine.history_page(0, 2)
    positions = [item["position"] for item in first["records"]]
    cursor = first["next"]
    engine.seal(SOURCE)
    while True:
        page = engine.history_page(cursor, 2)
        positions.extend(item["position"] for item in page["records"])
        cursor = page["next"]
        if cursor == page["frontier"]:
            break
    assert positions == list(range(cursor))
    assert cursor > frontier
    assert engine.history_page(cursor, 1)["records"] == []
    with pytest.raises(ValueError, match="exceeds captured frontier"):
        engine.history_page(cursor + 1, 1)


class PausingHistory(InMemoryHistoryStore):
    def __init__(self):
        super().__init__()
        self.pause = False
        self.appended = threading.Event()
        self.resume = threading.Event()

    def extend(self, records):
        super().extend(records)
        if self.pause:
            self.appended.set()
            assert self.resume.wait(2)


def test_snapshot_blocks_between_append_and_projection_then_sees_coherent_after_state():
    history = PausingHistory()
    engine = Engine.create(
        Net([Place(A)], [Transition(SOURCE)], [Arc(SOURCE, A)]),
        "barrier",
        history=history,
        dispatch=InMemoryDispatch(),
    )
    history.pause = True
    errors = []

    def write():
        try:
            engine.deliver(SOURCE, Token("X"))
        except BaseException as error:
            errors.append(error)

    writer = threading.Thread(target=write)
    writer.start()
    assert history.appended.wait(1)
    completed = threading.Event()
    snapshots = []

    def read():
        try:
            snapshots.append(engine.snapshot())
        except BaseException as error:
            errors.append(error)
        finally:
            completed.set()

    reader = threading.Thread(target=read)
    reader.start()
    assert not completed.wait(0.02)
    history.resume.set()
    writer.join()
    reader.join()
    assert not writer.is_alive() and not reader.is_alive()
    assert errors == []
    assert snapshots[0]["frontier"] == len(engine.records)
    assert snapshots[0]["current"]["marking"][0]["tokens"] == [{"color": "X", "data": None}]


def test_same_thread_public_reentry_is_refused_but_sensor_status_observation_remains_supported():
    atomic = canonical_engine()
    with pytest.raises(RuntimeError, match="cannot re-enter"):
        atomic._guarded(atomic.snapshot)  # noqa: SLF001

    engine = canonical_engine()
    observed = []
    engine._guarded(lambda: observed.extend((engine.marking, engine.status, engine.in_flight, engine.records)))  # noqa: SLF001
    assert observed == [engine.marking, engine.status, engine.in_flight, engine.records]


def test_joined_commit_failure_poisons_observation_and_hides_uncommitted_frontier():
    history = InMemoryHistoryStore()
    engine = Engine.create(
        Net([Place(A)], [Transition(SOURCE)], [Arc(SOURCE, A)]),
        "poison",
        history=history,
        dispatch=InMemoryDispatch(),
    )
    committed_frontier = len(history)
    engine._resources = engine_module._EngineResources(  # noqa: SLF001
        commit=lambda: (_ for _ in ()).throw(RuntimeError("commit refused"))
    )
    with pytest.raises(RuntimeError, match="commit refused"):
        engine.deliver(SOURCE, Token("X"))
    assert committed_frontier < len(history)  # backend-owned double cannot roll back; Engine still refuses exposure
    with pytest.raises(RuntimeError, match="poisoned"):
        engine.snapshot()
    with pytest.raises(RuntimeError, match="poisoned"):
        engine.history_page(0, 10)
