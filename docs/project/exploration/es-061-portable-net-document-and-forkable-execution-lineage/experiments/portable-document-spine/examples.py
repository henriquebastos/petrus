"""Executable positive ES-061 document examples built from Petrus-owned producers."""

from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path

from petrus.engine import Engine
from petrus.impetus.dsl import BuiltNet
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.net_definition import project_net_definition
from petrus.impetus.petrinet import Arc, Marking, Net, NetPath, Place, Token, Transition
from petrus.motus.dispatch import InMemoryDispatch
from petrus.simulation import simulate

from document_spine import EmbeddedArtifact


ROOT = Path(__file__).parents[6]
NET_DEFINITION_FIXTURE = ROOT / "spec" / "net-definition-v3.json"
SIMULATION_FIXTURE = ROOT / "spec" / "observation" / "simulation-result-v1.json"


def _strict_value(payload: bytes) -> dict[str, object]:
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise TypeError("fixture must be a JSON object")
    return value


def _artifact(payload: bytes) -> dict[str, object]:
    return EmbeddedArtifact.from_bytes(payload).model_dump(mode="json")


def _document(definition: dict[str, object]) -> dict[str, object]:
    return {
        "format": "petrus-net-document",
        "version": 1,
        "definition": deepcopy(definition),
    }


def definition_only() -> dict[str, object]:
    return _document(_strict_value(NET_DEFINITION_FIXTURE.read_bytes()))


def definition_with_view() -> dict[str, object]:
    document = definition_only()
    document["view"] = {
        "version": 1,
        "nodes": [
            {"node": "ingest", "x": 0, "y": 0},
            {"node": "review.correctness.blocked", "x": -120, "y": 80},
        ],
    }
    return document


def _capture(engine: Engine) -> bytes:
    snapshot = engine.snapshot()
    frontier = snapshot["frontier"]
    if not isinstance(frontier, int):
        raise TypeError("snapshot frontier must be an integer")
    value = {
        "format": "petrus-observation-capture",
        "version": 1,
        "snapshot": snapshot,
        "history": engine.history_page(0, frontier),
    }
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


@lru_cache(maxsize=1)
def mixed_material() -> tuple[dict[str, object], bytes, bytes, bytes, list[dict[str, object]]]:
    pending, done, advance = map(NetPath, ("pending", "done", "advance"))
    net = Net(
        places=[Place(pending, "Work"), Place(done, "Work")],
        transitions=[Transition(advance)],
        arcs=[Arc(pending, advance), Arc(advance, done)],
        name="portable-lineage",
    )
    observed_marking = Marking({pending: (Token("Work", {"result": "failed"}),)})
    history = InMemoryHistoryStore()
    engine = Engine.create(
        net,
        "observed-lineage",
        history=history,
        dispatch=InMemoryDispatch(),
        marking=observed_marking,
        at=0,
    )
    try:
        root_capture = _capture(engine)
        if not engine.advance().ready:
            raise RuntimeError("mixed example expected one observed action")
        future_capture = _capture(engine)
    finally:
        engine.close()

    manual_marking = [
        {
            "place": "pending",
            "tokens": [{"color": "Work", "data": {"result": "succeeded-hypothesis"}}],
        }
    ]
    simulated = simulate(
        BuiltNet(net),
        Marking({pending: (Token("Work", {"result": "succeeded-hypothesis"}),)}),
        max_actions=8,
    )
    definition = project_net_definition(net).model_dump(mode="json")
    return definition, root_capture, future_capture, simulated, manual_marking


def observed() -> dict[str, object]:
    definition, root_capture, _, _, _ = mixed_material()
    document = _document(definition)
    document["lineage"] = {
        "head": 0,
        "steps": [
            {
                "id": 0,
                "parent": None,
                "provenance": "observed",
                "capture": _artifact(root_capture),
            }
        ],
    }
    return document


def manual() -> dict[str, object]:
    definition, root_capture, _, _, manual_marking = mixed_material()
    document = _document(definition)
    document["lineage"] = {
        "head": 1,
        "steps": [
            {
                "id": 0,
                "parent": None,
                "provenance": "observed",
                "capture": _artifact(root_capture),
            },
            {
                "id": 1,
                "parent": 0,
                "provenance": "manual",
                "operation": "replace-marking",
                "marking": deepcopy(manual_marking),
            },
        ],
    }
    return document


def simulated() -> dict[str, object]:
    result = _strict_value(SIMULATION_FIXTURE.read_bytes())
    definition = {
        "format": "petrus-net-definition",
        "version": 3,
        "definition": deepcopy(result["snapshot"]["definition"]),
    }
    document = _document(definition)
    document["lineage"] = {
        "head": 0,
        "steps": [
            {
                "id": 0,
                "parent": None,
                "provenance": "simulated",
                "result": _artifact(SIMULATION_FIXTURE.read_bytes()),
            }
        ],
    }
    return document


def mixed_fork() -> dict[str, object]:
    definition, root_capture, future_capture, simulated_result, manual_marking = mixed_material()
    document = _document(definition)
    document["lineage"] = {
        "head": 2,
        "steps": [
            {
                "id": 0,
                "parent": None,
                "provenance": "observed",
                "capture": _artifact(root_capture),
            },
            {
                "id": 1,
                "parent": 0,
                "provenance": "manual",
                "operation": "replace-marking",
                "marking": deepcopy(manual_marking),
            },
            {
                "id": 2,
                "parent": 1,
                "provenance": "simulated",
                "result": _artifact(simulated_result),
            },
            {
                "id": 3,
                "parent": 0,
                "provenance": "observed",
                "capture": _artifact(future_capture),
            },
        ],
    }
    return document


def _source_value(payload: bytes) -> dict[str, object]:
    return _strict_value(payload)


def _history_records(payload: bytes) -> list[dict[str, object]]:
    value = _source_value(payload)
    history = value["history"]
    assert isinstance(history, dict)
    records = history["records"]
    assert isinstance(records, list)
    return records


def _source_marking(payload: bytes) -> list[dict[str, object]]:
    value = _source_value(payload)
    snapshot = value["snapshot"]
    assert isinstance(snapshot, dict)
    current = snapshot["current"]
    assert isinstance(current, dict)
    marking = current["marking"]
    assert isinstance(marking, list)
    return marking


def _project_records(
    entries: list[dict[str, object]],
    payload: bytes,
    *,
    source: int,
    after: int,
    parent: int | None,
    provenance: str,
    checkpoint: list[dict[str, object]] | None = None,
) -> int:
    records = _history_records(payload)
    for position in range(after, len(records)):
        wrapper = records[position]
        record = wrapper["record"]
        assert isinstance(record, dict)
        entry: dict[str, object] = {
            "id": len(entries),
            "parent": parent,
            "provenance": provenance,
            "fact": {
                "kind": "history-record",
                "source": source,
                "position": position,
                "record": deepcopy(record),
            },
        }
        if checkpoint is not None and position == len(records) - 1:
            entry["checkpoint"] = deepcopy(checkpoint)
        entries.append(entry)
        parent = len(entries) - 1
    if parent is None:
        raise RuntimeError("a source must project at least one History record")
    return parent


def uniform_definition_only() -> dict[str, object]:
    return definition_only()


def uniform_definition_with_view() -> dict[str, object]:
    document = definition_with_view()
    view = document["view"]
    assert isinstance(view, dict)
    nodes = view["nodes"]
    assert isinstance(nodes, list)
    nodes[1]["x"] = -120.5
    nodes[1]["y"] = 80.25
    return document


def uniform_observed() -> dict[str, object]:
    definition, root_capture, _, _, _ = mixed_material()
    document = _document(definition)
    entries: list[dict[str, object]] = []
    head = _project_records(
        entries,
        root_capture,
        source=0,
        after=0,
        parent=None,
        provenance="observed",
        checkpoint=_source_marking(root_capture),
    )
    document["lineage"] = {
        "sources": [
            {
                "id": 0,
                "kind": "observation-capture",
                "after": 0,
                "artifact": _artifact(root_capture),
            }
        ],
        "head": head,
        "entries": entries,
    }
    return document


def uniform_manual() -> dict[str, object]:
    definition, root_capture, _, _, manual_marking = mixed_material()
    document = uniform_observed()
    document["definition"] = deepcopy(definition)
    lineage = document["lineage"]
    assert isinstance(lineage, dict)
    entries = lineage["entries"]
    assert isinstance(entries, list)
    entries.append(
        {
            "id": len(entries),
            "parent": len(entries) - 1,
            "provenance": "manual",
            "fact": {
                "kind": "manual-replace-marking",
                "marking": deepcopy(manual_marking),
            },
        }
    )
    lineage["head"] = len(entries) - 1
    return document


def uniform_simulated() -> dict[str, object]:
    payload = SIMULATION_FIXTURE.read_bytes()
    result = _source_value(payload)
    snapshot = result["snapshot"]
    assert isinstance(snapshot, dict)
    definition = {
        "format": "petrus-net-definition",
        "version": 3,
        "definition": deepcopy(snapshot["definition"]),
    }
    document = _document(definition)
    entries: list[dict[str, object]] = []
    head = _project_records(
        entries,
        payload,
        source=0,
        after=0,
        parent=None,
        provenance="simulated",
        checkpoint=_source_marking(payload),
    )
    document["lineage"] = {
        "sources": [
            {
                "id": 0,
                "kind": "simulation-result",
                "after": 0,
                "artifact": _artifact(payload),
            }
        ],
        "head": head,
        "entries": entries,
    }
    return document


def uniform_mixed_fork() -> dict[str, object]:
    definition, root_capture, future_capture, simulated_result, manual_marking = mixed_material()
    document = _document(definition)
    entries: list[dict[str, object]] = []
    observed_root = _project_records(
        entries,
        root_capture,
        source=0,
        after=0,
        parent=None,
        provenance="observed",
        checkpoint=_source_marking(root_capture),
    )
    entries.append(
        {
            "id": len(entries),
            "parent": observed_root,
            "provenance": "manual",
            "fact": {
                "kind": "manual-replace-marking",
                "marking": deepcopy(manual_marking),
            },
        }
    )
    manual = len(entries) - 1
    simulated_head = _project_records(
        entries,
        simulated_result,
        source=1,
        after=0,
        parent=manual,
        provenance="simulated",
        checkpoint=_source_marking(simulated_result),
    )
    _project_records(
        entries,
        future_capture,
        source=2,
        after=len(_history_records(root_capture)),
        parent=observed_root,
        provenance="observed",
        checkpoint=_source_marking(future_capture),
    )
    document["lineage"] = {
        "sources": [
            {
                "id": 0,
                "kind": "observation-capture",
                "after": 0,
                "artifact": _artifact(root_capture),
            },
            {
                "id": 1,
                "kind": "simulation-result",
                "after": 0,
                "artifact": _artifact(simulated_result),
            },
            {
                "id": 2,
                "kind": "observation-capture",
                "after": len(_history_records(root_capture)),
                "artifact": _artifact(future_capture),
            },
        ],
        "head": simulated_head,
        "entries": entries,
    }
    return document


UNIFORM_EXAMPLES = {
    "definition-only": uniform_definition_only,
    "definition-with-view": uniform_definition_with_view,
    "observed": uniform_observed,
    "manual": uniform_manual,
    "simulated": uniform_simulated,
    "mixed-fork": uniform_mixed_fork,
}


def uniform_example_bytes(name: str) -> bytes:
    value = UNIFORM_EXAMPLES[name]()
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def without_source_anchors(value: dict[str, object]) -> dict[str, object]:
    result = deepcopy(value)
    lineage = result.get("lineage")
    if isinstance(lineage, dict):
        lineage.pop("sources")
    return result


EXAMPLES = {
    "definition-only": definition_only,
    "definition-with-view": definition_with_view,
    "observed": observed,
    "manual": manual,
    "simulated": simulated,
    "mixed-fork": mixed_fork,
}


def example_bytes(name: str) -> bytes:
    value = EXAMPLES[name]()
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


__all__ = [
    "EXAMPLES",
    "UNIFORM_EXAMPLES",
    "example_bytes",
    "mixed_material",
    "uniform_example_bytes",
    "without_source_anchors",
]
