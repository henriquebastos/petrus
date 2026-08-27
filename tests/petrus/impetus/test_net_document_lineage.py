"""Conformance tests for portable, forkable Net document execution lineage."""

from __future__ import annotations

import base64
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from typing import cast

import pytest

from petrus.impetus.net_document import (
    HistoryRecordFact,
    MarkingToken,
    NetDocumentError,
    parse_net_document,
    resolve_lineage,
    serialize_net_document,
)


ROOT = Path(__file__).parents[3]
LINEAGE_FIXTURE = ROOT / "spec" / "net-document-v1-lineage.json"
INVALID_LINEAGE_FIXTURE = ROOT / "spec" / "net-document-v1-invalid-unanchored-lineage.json"


def fixture_value() -> dict[str, object]:
    value = json.loads(LINEAGE_FIXTURE.read_bytes())
    assert isinstance(value, dict)
    return value


def lineage(value: dict[str, object]) -> dict[str, object]:
    return cast(dict[str, object], value["lineage"])


def sources(value: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], lineage(value)["sources"])


def entries(value: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], lineage(value)["entries"])


def encoded(value: dict[str, object]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()


def replace_source(value: dict[str, object], index: int, change) -> None:
    artifact = cast(dict[str, str], sources(value)[index]["artifact"])
    source = json.loads(base64.b64decode(artifact["base64"], validate=True))
    change(source)
    payload = (json.dumps(source, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    artifact["sha256"] = sha256(payload).hexdigest()
    artifact["base64"] = base64.b64encode(payload).decode("ascii")


def test_producer_backed_mixed_fixture_is_one_uniform_navigation_sequence() -> None:
    document = parse_net_document(LINEAGE_FIXTURE.read_bytes())

    navigation = resolve_lineage(document)

    assert [(entry.id, entry.parent, entry.provenance, entry.event) for entry in navigation] == [
        (0, None, "observed", "InstanceCreated"),
        (1, 0, "observed", "TokensInitialized"),
        (2, 1, "manual", "ManualMarkingReplaced"),
        (3, 2, "simulated", "InstanceCreated"),
        (4, 3, "simulated", "TokensInitialized"),
        (5, 4, "simulated", "CandidateSelected"),
        (6, 5, "simulated", "FiringBegun"),
        (7, 6, "simulated", "TokensConsumed"),
        (8, 7, "simulated", "TokensProduced"),
        (9, 8, "simulated", "FiringCompleted"),
        (10, 1, "observed", "CandidateSelected"),
        (11, 10, "observed", "FiringBegun"),
        (12, 11, "observed", "TokensConsumed"),
        (13, 12, "observed", "TokensProduced"),
        (14, 13, "observed", "FiringCompleted"),
    ]
    assert document.lineage is not None
    assert document.lineage.head == 9
    assert navigation[9].marking[0].place == "done"
    assert navigation[14].marking[0].place == "done"


def test_fixture_round_trip_preserves_sources_and_optional_checkpoint_spelling() -> None:
    original = fixture_value()
    original_sources = [
        base64.b64decode(cast(dict[str, str], source["artifact"])["base64"], validate=True)
        for source in sources(original)
    ]

    payload = serialize_net_document(parse_net_document(LINEAGE_FIXTURE.read_bytes()))
    reopened = parse_net_document(payload)
    value = json.loads(payload)
    retained = [
        base64.b64decode(cast(dict[str, str], source["artifact"])["base64"], validate=True) for source in sources(value)
    ]

    assert payload == LINEAGE_FIXTURE.read_bytes()
    assert retained == original_sources
    assert resolve_lineage(reopened) == resolve_lineage(parse_net_document(payload))
    assert [entry["id"] for entry in entries(value) if "checkpoint" in entry] == [1, 9, 14]


def test_observed_and_simulated_entries_share_the_exact_history_record_fact() -> None:
    document = parse_net_document(LINEAGE_FIXTURE.read_bytes())
    assert document.lineage is not None
    facts = [entry.fact for entry in document.lineage.entries if isinstance(entry.fact, HistoryRecordFact)]

    assert {entry.provenance for entry in document.lineage.entries if isinstance(entry.fact, HistoryRecordFact)} == {
        "observed",
        "simulated",
    }
    assert {type(fact) for fact in facts} == {HistoryRecordFact}
    assert [
        entry.fact.position
        for entry in document.lineage.entries
        if isinstance(entry.fact, HistoryRecordFact) and entry.fact.source == 2
    ] == [2, 3, 4, 5, 6]


def set_entry_id(value: dict[str, object]) -> None:
    entries(value)[4]["id"] = 5


def set_parent_forward(value: dict[str, object]) -> None:
    entries(value)[2]["parent"] = 2


def set_unknown_head(value: dict[str, object]) -> None:
    lineage(value)["head"] = 15


def set_source_id(value: dict[str, object]) -> None:
    sources(value)[1]["id"] = 4


def remove_source_position(value: dict[str, object]) -> None:
    entries(value).pop()


def contradict_manual_provenance(value: dict[str, object]) -> None:
    entries(value)[2]["provenance"] = "observed"


def alter_retained_record_fact(value: dict[str, object]) -> None:
    fact = cast(dict[str, object], entries(value)[10]["fact"])
    record = cast(dict[str, object], fact["record"])
    record["instant"] = cast(int, record["instant"]) + 1


def contradict_checkpoint(value: dict[str, object]) -> None:
    entries(value)[1]["checkpoint"] = []


def null_checkpoint(value: dict[str, object]) -> None:
    entries(value)[0]["checkpoint"] = None


def non_integer_simulation_after(value: dict[str, object]) -> None:
    sources(value)[1]["after"] = False


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (set_entry_id, "id must equal"),
        (set_parent_forward, "parent must be a smaller"),
        (set_unknown_head, "head must name"),
        (set_source_id, "id must equal"),
        (remove_source_position, "project each source position"),
        (contradict_manual_provenance, "manual fact requires manual provenance"),
        (alter_retained_record_fact, "differs from the exact retained source"),
        (contradict_checkpoint, "checkpoint disagrees"),
        (null_checkpoint, "checkpoint must be absent"),
        (non_integer_simulation_after, "after"),
    ],
)
def test_lineage_shape_and_evidence_relationships_are_strict(change, expected: str) -> None:
    value = fixture_value()
    change(value)

    with pytest.raises(NetDocumentError, match=expected):
        parse_net_document(encoded(value))


def test_observed_extension_must_preserve_instance_identity_and_exact_prefix() -> None:
    value = fixture_value()

    def change(source: dict[str, object]) -> None:
        snapshot = cast(dict[str, object], source["snapshot"])
        history = cast(dict[str, object], source["history"])
        snapshot["instance"] = "foreign-observed-instance"
        history["instance"] = "foreign-observed-instance"
        records = cast(list[dict[str, object]], history["records"])
        first_record = cast(dict[str, object], records[0]["record"])
        first_record["instance"] = "foreign-observed-instance"

    replace_source(value, 2, change)

    with pytest.raises(NetDocumentError, match="preserve Instance identity"):
        parse_net_document(encoded(value))


def test_simulation_initial_marking_must_equal_its_parent_state() -> None:
    value = fixture_value()

    def change(source: dict[str, object]) -> None:
        scenario = cast(dict[str, object], source["scenario"])
        marking = cast(list[dict[str, object]], scenario["initial_marking"])
        tokens = cast(list[dict[str, object]], marking[0]["tokens"])
        tokens[0]["data"] = {"result": "different-hypothesis"}

    replace_source(value, 1, change)

    with pytest.raises(NetDocumentError, match="initial marking must equal its parent"):
        parse_net_document(encoded(value))


def test_source_snapshot_must_agree_with_replayed_history() -> None:
    value = fixture_value()

    def change(source: dict[str, object]) -> None:
        snapshot = cast(dict[str, object], source["snapshot"])
        current = cast(dict[str, object], snapshot["current"])
        marking = cast(list[dict[str, object]], current["marking"])
        tokens = cast(list[dict[str, object]], marking[0]["tokens"])
        tokens[0]["data"] = {"result": "rewritten"}

    replace_source(value, 0, change)

    with pytest.raises(NetDocumentError, match="marking disagrees with replayed History"):
        parse_net_document(encoded(value))


@pytest.mark.parametrize("field", ["sha256", "base64"])
def test_retained_source_bytes_require_matching_digest_and_canonical_base64(field: str) -> None:
    value = fixture_value()
    artifact = cast(dict[str, str], sources(value)[0]["artifact"])
    artifact[field] = "0" * 64 if field == "sha256" else artifact[field] + "\n"

    with pytest.raises(NetDocumentError, match="does not match|canonical base64"):
        parse_net_document(encoded(value))


def test_negative_interoperability_fixture_without_source_custody_is_refused() -> None:
    with pytest.raises(NetDocumentError, match="sources must be nonempty"):
        parse_net_document(INVALID_LINEAGE_FIXTURE.read_bytes())


def test_caller_mutation_does_not_change_parsed_frozen_lineage() -> None:
    value = fixture_value()
    original = deepcopy(value)

    document = parse_net_document(encoded(value))
    entries(value)[0]["id"] = 99

    assert serialize_net_document(document) == encoded(original)


@pytest.mark.parametrize("data", [("not", "json"), {1: "non-string-key"}, {"number": float("inf")}])
def test_direct_token_data_must_already_be_strict_json(data: object) -> None:
    with pytest.raises(ValueError, match="strict JSON|member names|finite"):
        MarkingToken(color=None, data=data)
