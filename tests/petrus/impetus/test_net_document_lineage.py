"""Conformance tests for uniform, marking-first Net document lineage."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import cast

import pytest

from petrus.impetus.net_document import (
    LineageEntry,
    MarkingToken,
    NetDocumentError,
    parse_net_document,
    serialize_net_document,
)


ROOT = Path(__file__).parents[3]
LINEAGE_FIXTURE = ROOT / "spec" / "net-document-v1-lineage.json"
INVALID_LINEAGE_FIXTURE = ROOT / "spec" / "net-document-v1-invalid-lineage.json"


def fixture_value() -> dict[str, object]:
    value = json.loads(LINEAGE_FIXTURE.read_bytes())
    assert isinstance(value, dict)
    return value


def lineage(value: dict[str, object]) -> dict[str, object]:
    return cast(dict[str, object], value["lineage"])


def entries(value: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], lineage(value)["entries"])


def encoded(value: dict[str, object]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def test_fixture_is_one_uniform_marking_first_navigation_sequence() -> None:
    document = parse_net_document(LINEAGE_FIXTURE.read_bytes())
    assert document.lineage is not None

    assert [(entry.id, entry.parent, entry.provenance) for entry in document.lineage.entries] == [
        (0, None, "observed"),
        (1, 0, "observed"),
        (2, 0, "manual"),
        (3, 2, "simulated"),
        (4, 1, "manual"),
        (5, 4, "simulated"),
    ]
    assert document.lineage.head == 3
    assert document.lineage.entries[1].marking[0].place == "done"
    assert document.lineage.entries[2].marking[0].place == "pending"
    assert document.lineage.entries[3].marking[0].tokens[0].data == {"result": "succeeded-hypothesis"}


def test_observed_manual_and_simulated_entries_have_the_same_core_shape() -> None:
    value = fixture_value()

    assert {tuple(entry) for entry in entries(value)} == {("id", "parent", "provenance", "marking", "metadata")}
    assert {entry["provenance"] for entry in entries(value)} == {
        "observed",
        "simulated",
        "manual",
    }
    assert cast(dict[str, object], entries(value)[0]["metadata"])["history_records"]
    assert cast(dict[str, object], entries(value)[2]["metadata"])["note"]
    assert cast(dict[str, object], entries(value)[4]["metadata"]) == {}


def test_fixture_round_trip_is_exact_without_hidden_evidence_or_replay_state() -> None:
    payload = serialize_net_document(parse_net_document(LINEAGE_FIXTURE.read_bytes()))

    assert payload == LINEAGE_FIXTURE.read_bytes()
    assert b'"sources"' not in payload
    assert b'"fact"' not in payload
    assert b'"checkpoint"' not in payload
    assert b'"base64"' not in payload


def set_entry_id(value: dict[str, object]) -> None:
    entries(value)[4]["id"] = 5


def set_parent_forward(value: dict[str, object]) -> None:
    entries(value)[2]["parent"] = 2


def set_second_root(value: dict[str, object]) -> None:
    entries(value)[2]["parent"] = None


def set_unknown_head(value: dict[str, object]) -> None:
    lineage(value)["head"] = 6


def remove_entries(value: dict[str, object]) -> None:
    lineage(value)["entries"] = []


def remove_metadata(value: dict[str, object]) -> None:
    del entries(value)[0]["metadata"]


def use_non_object_metadata(value: dict[str, object]) -> None:
    entries(value)[0]["metadata"] = []


def add_old_source_custody(value: dict[str, object]) -> None:
    lineage(value)["sources"] = []


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (set_entry_id, "id must equal"),
        (set_parent_forward, "parent must be a smaller"),
        (set_second_root, "parent must be a smaller"),
        (set_unknown_head, "head must name"),
        (remove_entries, "entries must be nonempty"),
        (remove_metadata, "metadata"),
        (use_non_object_metadata, "metadata must be an object"),
        (add_old_source_custody, "Extra inputs are not permitted"),
    ],
)
def test_lineage_shape_is_strict(change, expected: str) -> None:
    value = fixture_value()
    change(value)

    with pytest.raises(NetDocumentError, match=expected):
        parse_net_document(encoded(value))


def duplicate_place(value: dict[str, object]) -> None:
    marking = cast(list[dict[str, object]], entries(value)[0]["marking"])
    marking.append(deepcopy(marking[0]))


def unsorted_places(value: dict[str, object]) -> None:
    entries(value)[0]["marking"] = [
        {"place": "pending", "tokens": [{"color": "Work", "data": None}]},
        {"place": "done", "tokens": [{"color": "Work", "data": None}]},
    ]


def empty_sparse_place(value: dict[str, object]) -> None:
    marking = cast(list[dict[str, object]], entries(value)[0]["marking"])
    marking[0]["tokens"] = []


def foreign_place(value: dict[str, object]) -> None:
    marking = cast(list[dict[str, object]], entries(value)[0]["marking"])
    marking[0]["place"] = "foreign"


def wrong_color(value: dict[str, object]) -> None:
    marking = cast(list[dict[str, object]], entries(value)[0]["marking"])
    tokens = cast(list[dict[str, object]], marking[0]["tokens"])
    tokens[0]["color"] = "Foreign"


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (duplicate_place, "places must be unique"),
        (unsorted_places, "places must be sorted"),
        (empty_sparse_place, "tokens must be nonempty"),
        (foreign_place, "names foreign place"),
        (wrong_color, "does not match place"),
    ],
)
def test_every_entry_contains_one_complete_valid_sparse_marking(change, expected: str) -> None:
    value = fixture_value()
    change(value)

    with pytest.raises(NetDocumentError, match=expected):
        parse_net_document(encoded(value))


def test_exact_negative_fixture_is_refused() -> None:
    with pytest.raises(NetDocumentError, match="names foreign place"):
        parse_net_document(INVALID_LINEAGE_FIXTURE.read_bytes())


def test_metadata_is_non_authoritative_strict_json() -> None:
    document = parse_net_document(LINEAGE_FIXTURE.read_bytes())
    assert document.lineage is not None
    entry = document.lineage.entries[2]

    changed = LineageEntry(
        id=entry.id,
        parent=entry.parent,
        provenance=entry.provenance,
        marking=entry.marking,
        metadata={"history_records": [{"record": "Invented"}], "anything": [True, None, 3.5]},
    )

    assert changed.marking == entry.marking
    assert changed.metadata["anything"] == [True, None, 3.5]
    for metadata in (
        ("not", "json"),
        {1: "non-string-key"},
        {"number": float("inf")},
        {"number": 2**53},
        {"number": float(10**20)},
    ):
        with pytest.raises(ValueError, match="strict JSON|member names|finite|object|safe-integer"):
            LineageEntry(
                id=entry.id,
                parent=entry.parent,
                provenance=entry.provenance,
                marking=entry.marking,
                metadata=cast(dict[str, object], metadata),
            )


def test_caller_mutation_does_not_change_parsed_lineage() -> None:
    value = fixture_value()
    original = deepcopy(value)

    document = parse_net_document(encoded(value))
    entries(value)[0]["id"] = 99
    cast(dict[str, object], entries(value)[0]["metadata"])["instance"] = "mutated"

    assert serialize_net_document(document) == encoded(original)


@pytest.mark.parametrize(
    "data",
    [("not", "json"), {1: "non-string-key"}, {"number": float("inf")}, {"number": 2**53}],
)
def test_direct_token_data_must_already_be_strict_json(data: object) -> None:
    with pytest.raises(ValueError, match="strict JSON|member names|finite|safe-integer"):
        MarkingToken(color=None, data=data)
