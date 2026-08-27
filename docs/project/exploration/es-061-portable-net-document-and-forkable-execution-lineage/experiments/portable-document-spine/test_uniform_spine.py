"""Executable comparison evidence for uniform ES-061 lineage entries."""

from __future__ import annotations

import base64
from hashlib import sha256
import json

import pytest

from document_spine import DocumentError, parse_document
from examples import (
    EXAMPLES,
    UNIFORM_EXAMPLES,
    example_bytes,
    uniform_example_bytes,
    without_source_anchors,
)
from uniform_spine import (
    HistoryRecordFact,
    parse_anchored_document,
    parse_unanchored_document,
    serialize_anchored_document,
)


def encoded(value: dict[str, object]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def lineage(value: dict[str, object]) -> dict[str, object]:
    result = value["lineage"]
    assert isinstance(result, dict)
    return result


def entries(value: dict[str, object]) -> list[dict[str, object]]:
    result = lineage(value)["entries"]
    assert isinstance(result, list)
    return result


def sources(value: dict[str, object]) -> list[dict[str, object]]:
    result = lineage(value)["sources"]
    assert isinstance(result, list)
    return result


def replace_artifact(artifact: dict[str, object], change) -> None:
    base64_value = artifact["base64"]
    assert isinstance(base64_value, str)
    value = json.loads(base64.b64decode(base64_value))
    change(value)
    payload = encoded(value)
    artifact["base64"] = base64.b64encode(payload).decode("ascii")
    artifact["sha256"] = sha256(payload).hexdigest()


def rewrite_failed_token_data(value: object) -> None:
    if isinstance(value, dict):
        if value == {"result": "failed"}:
            value["result"] = "rewritten"
        else:
            for item in value.values():
                rewrite_failed_token_data(item)
    elif isinstance(value, list):
        for item in value:
            rewrite_failed_token_data(item)


class TestUniformDocumentForms:
    """The leading shape admits each bounded component combination without a public API."""

    @pytest.mark.parametrize("name", UNIFORM_EXAMPLES)
    def test_each_required_example_parses(self, name: str) -> None:
        parsed = parse_anchored_document(uniform_example_bytes(name))

        reopened = parse_anchored_document(serialize_anchored_document(parsed.wire))

        assert reopened == parsed

    def test_definition_only_and_float_view_share_definition_identity(self) -> None:
        definition_only = parse_anchored_document(uniform_example_bytes("definition-only"))
        arranged = parse_anchored_document(uniform_example_bytes("definition-with-view"))

        assert definition_only.definition_identity == arranged.definition_identity
        assert not definition_only.entries
        assert not arranged.entries
        assert arranged.wire.view is not None
        assert arranged.wire.view.nodes[1].x == -120.5

    def test_optional_checkpoint_is_an_assertion_not_a_navigation_container(self) -> None:
        value = UNIFORM_EXAMPLES["mixed-fork"]()
        parsed = parse_anchored_document(encoded(value))

        assert sum("checkpoint" in entry for entry in entries(value)) == 3
        assert len(parsed.entries) == len(entries(value)) == 15
        assert all(entry.marking is not None for entry in parsed.entries)


class TestOneListNavigation:
    """One consumer loop sees observed events, intervention, simulation, and sibling events."""

    def test_mixed_fork_is_one_dense_event_list_with_no_nested_timeline(self) -> None:
        parsed = parse_anchored_document(uniform_example_bytes("mixed-fork"))
        assert parsed.wire.lineage is not None

        visited = [(entry.id, entry.parent, entry.provenance, entry.event, entry.marking) for entry in parsed.entries]

        assert [(item[0], item[1], item[2], item[3]) for item in visited] == [
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
        assert parsed.wire.lineage.head == 9
        assert visited[9][4][0].place == "done"
        assert visited[14][4][0].place == "done"

    def test_observed_and_simulated_records_have_the_same_fact_shape(self) -> None:
        parsed = parse_anchored_document(uniform_example_bytes("mixed-fork"))
        assert parsed.wire.lineage is not None
        history_entries = [entry for entry in parsed.wire.lineage.entries if isinstance(entry.fact, HistoryRecordFact)]

        assert {entry.provenance for entry in history_entries} == {"observed", "simulated"}
        assert {type(entry.fact) for entry in history_entries} == {HistoryRecordFact}

    def test_later_capture_projects_only_its_nonduplicated_extension(self) -> None:
        value = UNIFORM_EXAMPLES["mixed-fork"]()
        projected = [
            entry["fact"]["position"]
            for entry in entries(value)
            if entry["provenance"] == "observed" and entry["fact"].get("source") == 2
        ]

        assert sources(value)[2]["after"] == 2
        assert projected == [2, 3, 4, 5, 6]


class TestShapeComparison:
    """The three executable shapes expose the navigation/custody trade-off directly."""

    def test_entries_only_shape_navigates_the_same_uniform_list(self) -> None:
        value = without_source_anchors(UNIFORM_EXAMPLES["mixed-fork"]())

        parsed = parse_unanchored_document(encoded(value))

        assert [(entry.parent, entry.provenance, entry.event) for entry in parsed.entries] == [
            (entry.parent, entry.provenance, entry.event)
            for entry in parse_anchored_document(uniform_example_bytes("mixed-fork")).entries
        ]

    def test_entries_only_shape_cannot_prove_imported_record_custody(self) -> None:
        value = UNIFORM_EXAMPLES["mixed-fork"]()
        for observed in entries(value)[10:]:
            record = observed["fact"]["record"]
            assert isinstance(record, dict)
            record["instant"] = 1

        with pytest.raises(DocumentError, match="differs from the exact retained source"):
            parse_anchored_document(encoded(value))

        unanchored = without_source_anchors(value)
        assert parse_unanchored_document(encoded(unanchored)).entries[10].event == "CandidateSelected"

    def test_control_exposes_four_containers_and_sixteen_nested_records(self) -> None:
        value = EXAMPLES["mixed-fork"]()
        parsed = parse_document(example_bytes("mixed-fork"))
        nested_records = 0
        control_steps = lineage(value)["steps"]
        assert isinstance(control_steps, list)
        for step in control_steps:
            artifact = step.get("capture", step.get("result"))
            if artifact is None:
                continue
            payload = base64.b64decode(artifact["base64"])
            nested_records += len(json.loads(payload)["history"]["records"])

        assert len(parsed.checkpoints) == 4
        assert nested_records == 16
        assert len(parse_anchored_document(uniform_example_bytes("mixed-fork")).entries) == 15


class TestStrictEnvelopeAndLineageRefusal:
    """Strict JSON, envelope discrimination, ids, parents, roots, and head are enforced."""

    @pytest.mark.parametrize(
        "payload",
        [
            b'{"format":"petrus-net-document","format":"petrus-net-document"}',
            b'{"format":"petrus-net-document","version":NaN}',
            b"\xff",
            b'{"format":"petrus-net-document","version":1,"definition":"\\ud800"}',
        ],
    )
    def test_non_strict_json_is_refused(self, payload: bytes) -> None:
        with pytest.raises(DocumentError):
            parse_anchored_document(payload)

    @pytest.mark.parametrize(
        ("change", "message"),
        [
            (lambda value: value.update(format="petrus-observation-capture"), "format"),
            (lambda value: value.update(version=True), "version"),
            (lambda value: value.update(extra={}), "extra"),
            (lambda value: value.update(view=None), "absent or an object"),
            (lambda value: value.update(lineage=None), "absent or an object"),
            (lambda value: value["definition"].update(format="petrus-canonical-net-inspection"), "format"),
        ],
    )
    def test_wrong_envelope_discriminator_unknown_field_or_null_is_refused(self, change, message: str) -> None:
        value = UNIFORM_EXAMPLES["definition-with-view"]()
        change(value)

        with pytest.raises(DocumentError, match=message):
            parse_anchored_document(encoded(value))

    @pytest.mark.parametrize(
        ("change", "message"),
        [
            (lambda value: lineage(value).update(entries=[]), "nonempty"),
            (lambda value: lineage(value).update(head=99), "existing entry"),
            (lambda value: entries(value)[0].update(parent=0), "sole root"),
            (lambda value: entries(value)[1].update(id=7), "equal its array index"),
            (lambda value: entries(value)[1].update(parent=None), "smaller entry id"),
            (lambda value: entries(value)[2].update(parent=2), "smaller entry id"),
            (lambda value: entries(value)[2].update(parent=9), "smaller entry id"),
            (lambda value: entries(value)[1].update(id=True), "id"),
        ],
    )
    def test_invalid_identity_parent_root_or_head_is_refused(self, change, message: str) -> None:
        value = UNIFORM_EXAMPLES["mixed-fork"]()
        change(value)

        with pytest.raises(DocumentError, match=message):
            parse_anchored_document(encoded(value))

    def test_source_ids_are_dense_array_positions(self) -> None:
        value = UNIFORM_EXAMPLES["mixed-fork"]()
        sources(value)[1]["id"] = 7

        with pytest.raises(DocumentError, match="source.*array index"):
            parse_anchored_document(encoded(value))


class TestProvenanceAndEvidenceRefusal:
    """Provenance, exact record relation, source extension, and checkpoints cannot be confused."""

    def test_observed_record_cannot_claim_simulated_provenance(self) -> None:
        value = UNIFORM_EXAMPLES["mixed-fork"]()
        entries(value)[10]["provenance"] = "simulated"

        with pytest.raises(DocumentError, match="provenance contradicts"):
            parse_anchored_document(encoded(value))

    def test_manual_fact_cannot_claim_observed_provenance(self) -> None:
        value = UNIFORM_EXAMPLES["mixed-fork"]()
        entries(value)[2]["provenance"] = "observed"

        with pytest.raises(DocumentError, match="manual fact requires manual provenance"):
            parse_anchored_document(encoded(value))

    def test_source_kind_cannot_hide_the_other_artifact_envelope(self) -> None:
        value = UNIFORM_EXAMPLES["mixed-fork"]()
        sources(value)[1]["kind"] = "observation-capture"

        with pytest.raises(DocumentError, match="observation capture schema|exactly fields"):
            parse_anchored_document(encoded(value))

    def test_projected_record_must_equal_its_exact_source_position(self) -> None:
        value = UNIFORM_EXAMPLES["mixed-fork"]()
        record = entries(value)[13]["fact"]["record"]
        assert isinstance(record, dict)
        record["tokens"][0]["data"] = {"result": "rewritten"}

        with pytest.raises(DocumentError, match="differs from the exact retained source"):
            parse_anchored_document(encoded(value))

    def test_later_observed_source_must_exactly_extend_the_parent_history(self) -> None:
        value = UNIFORM_EXAMPLES["mixed-fork"]()
        artifact = sources(value)[2]["artifact"]
        assert isinstance(artifact, dict)
        replace_artifact(artifact, rewrite_failed_token_data)

        with pytest.raises(DocumentError, match="exactly extend"):
            parse_anchored_document(encoded(value))

    def test_observed_extension_cannot_descend_from_manual_hypothesis(self) -> None:
        value = UNIFORM_EXAMPLES["mixed-fork"]()
        entries(value)[10]["parent"] = 2

        with pytest.raises(DocumentError, match="History-record parent|same-provenance"):
            parse_anchored_document(encoded(value))

    def test_simulated_source_initial_marking_must_equal_parent_state(self) -> None:
        value = UNIFORM_EXAMPLES["mixed-fork"]()
        marking = entries(value)[2]["fact"]["marking"]
        assert isinstance(marking, list)
        marking[0]["tokens"][0]["data"] = {"result": "different-hypothesis"}

        with pytest.raises(DocumentError, match="initial marking must equal"):
            parse_anchored_document(encoded(value))

    def test_checkpoint_must_equal_replay_derived_state(self) -> None:
        value = UNIFORM_EXAMPLES["mixed-fork"]()
        checkpoint = entries(value)[14]["checkpoint"]
        assert isinstance(checkpoint, list)
        checkpoint[0]["tokens"][0]["data"] = {"result": "not-observed"}

        with pytest.raises(DocumentError, match="checkpoint disagrees"):
            parse_anchored_document(encoded(value))

    def test_each_source_position_from_after_to_frontier_is_projected_once(self) -> None:
        value = UNIFORM_EXAMPLES["mixed-fork"]()
        entries(value)[14]["fact"]["source"] = 0

        with pytest.raises(DocumentError, match="projected range|each source position"):
            parse_anchored_document(encoded(value))
