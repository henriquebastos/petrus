"""Behavior evidence for the ES-061 portable-document candidate shape."""

from __future__ import annotations

import base64
from copy import deepcopy
from hashlib import sha256
import json

import pytest

from document_spine import DocumentError, parse_document, serialize_document
from examples import EXAMPLES, example_bytes, mixed_material


def encoded(value: dict[str, object]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def source_bytes(artifact: dict[str, object]) -> bytes:
    value = artifact["base64"]
    assert isinstance(value, str)
    return base64.b64decode(value)


def replace_source(artifact: dict[str, object], change) -> None:
    value = json.loads(source_bytes(artifact))
    change(value)
    payload = encoded(value)
    artifact["base64"] = base64.b64encode(payload).decode("ascii")
    artifact["sha256"] = sha256(payload).hexdigest()


def lineage(value: dict[str, object]) -> dict[str, object]:
    result = value["lineage"]
    assert isinstance(result, dict)
    return result


def steps(value: dict[str, object]) -> list[dict[str, object]]:
    result = lineage(value)["steps"]
    assert isinstance(result, list)
    return result


class TestAcceptedDocumentForms:
    """One strict envelope admits every progressively available component combination."""

    @pytest.mark.parametrize("name", EXAMPLES)
    def test_each_required_example_parses_and_round_trips(self, name: str) -> None:
        parsed = parse_document(example_bytes(name))

        reopened = parse_document(serialize_document(parsed.wire))

        assert reopened == parsed

    def test_definition_only_and_view_share_definition_identity(self) -> None:
        definition_only = parse_document(example_bytes("definition-only"))
        arranged = parse_document(example_bytes("definition-with-view"))

        assert definition_only.definition_identity == arranged.definition_identity
        assert not definition_only.checkpoints
        assert not arranged.checkpoints
        assert arranged.wire.view is not None

    def test_mixed_fork_is_one_checkpoint_list_with_two_children_of_observed_root(self) -> None:
        parsed = parse_document(example_bytes("mixed-fork"))

        assert [(step.id, step.parent, step.provenance) for step in parsed.checkpoints] == [
            (0, None, "observed"),
            (1, 0, "manual"),
            (2, 1, "simulated"),
            (3, 0, "observed"),
        ]
        assert parsed.wire.lineage is not None
        assert parsed.wire.lineage.head == 2
        assert parsed.checkpoints[2].marking[0].place == "done"
        assert parsed.checkpoints[3].marking[0].place == "done"

    def test_embedded_capture_and_simulation_bytes_are_recovered_exactly(self) -> None:
        value = EXAMPLES["mixed-fork"]()
        _, root_capture, future_capture, simulation_result, _ = mixed_material()
        retained = steps(value)

        parse_document(encoded(value))

        assert source_bytes(retained[0]["capture"]) == root_capture
        assert source_bytes(retained[2]["result"]) == simulation_result
        assert source_bytes(retained[3]["capture"]) == future_capture


class TestStrictEnvelopeRefusal:
    """Malformed JSON and neighboring Petrus envelopes never enter the document model."""

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
            parse_document(payload)

    @pytest.mark.parametrize(
        ("change", "message"),
        [
            (lambda value: value.update(format="petrus-net-definition"), "format"),
            (lambda value: value.update(version=True), "version"),
            (lambda value: value.update(extra={}), "extra"),
            (lambda value: value.update(view=None), "absent or an object"),
            (lambda value: value.update(lineage=None), "absent or an object"),
            (lambda value: value["definition"].update(format="petrus-canonical-net-inspection"), "format"),
            (lambda value: value["view"].update(version=True), "view.version"),
        ],
    )
    def test_wrong_discriminator_type_unknown_field_or_null_component_is_refused(self, change, message: str) -> None:
        value = EXAMPLES["definition-with-view"]()
        change(value)

        with pytest.raises(DocumentError, match=message):
            parse_document(encoded(value))

    def test_observed_step_cannot_embed_a_simulation_envelope(self) -> None:
        value = EXAMPLES["observed"]()
        simulation = steps(EXAMPLES["simulated"]())[0]["result"]
        steps(value)[0]["capture"] = simulation

        with pytest.raises(DocumentError, match="observation capture schema 1|exactly fields"):
            parse_document(encoded(value))

    def test_simulated_step_cannot_embed_an_observation_envelope(self) -> None:
        value = EXAMPLES["simulated"]()
        capture = steps(EXAMPLES["observed"]())[0]["capture"]
        steps(value)[0]["result"] = capture

        with pytest.raises(DocumentError, match="simulation result schema 1|exactly fields"):
            parse_document(encoded(value))


class TestLineageInvariants:
    """Step ids, parents, roots, and head make an append-only acyclic list by construction."""

    @pytest.mark.parametrize(
        ("change", "message"),
        [
            (lambda value: lineage(value).update(steps=[]), "nonempty"),
            (lambda value: lineage(value).update(head=99), "existing step"),
            (lambda value: steps(value)[0].update(parent=0), "root parent"),
            (lambda value: steps(value)[1].update(id=7), "equal its array index"),
            (lambda value: steps(value)[1].update(parent=None), "parent"),
            (lambda value: steps(value)[1].update(parent=1), "smaller existing step"),
            (lambda value: steps(value)[2].update(parent=3), "smaller existing step"),
            (lambda value: steps(value)[1].update(id=True), "id"),
        ],
    )
    def test_invalid_identity_parent_or_head_is_refused(self, change, message: str) -> None:
        value = EXAMPLES["mixed-fork"]()
        change(value)

        with pytest.raises(DocumentError, match=message):
            parse_document(encoded(value))

    def test_cycle_attempt_cannot_be_encoded_without_a_forward_parent(self) -> None:
        value = EXAMPLES["mixed-fork"]()
        steps(value)[1]["parent"] = 2

        with pytest.raises(DocumentError, match="smaller existing step"):
            parse_document(encoded(value))

    def test_manual_step_cannot_be_the_root_because_intervention_requires_a_basis(self) -> None:
        value = EXAMPLES["manual"]()
        lineage(value)["steps"] = [deepcopy(steps(value)[1])]
        steps(value)[0].update(id=0, parent=None)
        lineage(value)["head"] = 0

        with pytest.raises(DocumentError, match="parent"):
            parse_document(encoded(value))

    def test_five_thousand_step_shallow_document_validates_iteratively(self) -> None:
        value = EXAMPLES["manual"]()
        root, manual = deepcopy(steps(value)[0]), deepcopy(steps(value)[1])
        long_steps = [root]
        for step_id in range(1, 5_001):
            item = deepcopy(manual)
            item.update(id=step_id, parent=step_id - 1)
            long_steps.append(item)
        lineage(value).update(head=5_000, steps=long_steps)

        parsed = parse_document(encoded(value))

        assert len(parsed.checkpoints) == 5_001
        assert parsed.checkpoints[-1].parent == 4_999


class TestProvenanceAndAuthorityRefusal:
    """Each provenance has one disjoint payload and source authority remains internally coherent."""

    @pytest.mark.parametrize(
        "change",
        [
            lambda step: step.update(provenance="manual"),
            lambda step: step.update(marking=[]),
            lambda step: step.update(result=step.pop("capture")),
        ],
    )
    def test_observed_payload_cannot_be_relabelled_or_mixed(self, change) -> None:
        value = EXAMPLES["observed"]()
        change(steps(value)[0])

        with pytest.raises(DocumentError):
            parse_document(encoded(value))

    def test_manual_step_accepts_only_explicit_replacement_marking(self) -> None:
        value = EXAMPLES["manual"]()
        steps(value)[1]["operation"] = "patch-token"

        with pytest.raises(DocumentError, match="operation"):
            parse_document(encoded(value))

    def test_changed_retained_bytes_without_matching_digest_are_refused(self) -> None:
        value = EXAMPLES["observed"]()
        artifact = steps(value)[0]["capture"]
        assert isinstance(artifact, dict)
        artifact["base64"] = artifact["base64"][:-4] + "AAAA"

        with pytest.raises(DocumentError, match="sha256"):
            parse_document(encoded(value))

    def test_capture_definition_must_equal_the_document_definition(self) -> None:
        value = EXAMPLES["observed"]()
        artifact = steps(value)[0]["capture"]
        assert isinstance(artifact, dict)
        replace_source(artifact, lambda capture: capture["snapshot"]["definition"].update(name="other"))

        with pytest.raises(DocumentError, match="does not match"):
            parse_document(encoded(value))

    def test_capture_history_position_must_equal_its_array_index(self) -> None:
        value = EXAMPLES["observed"]()
        artifact = steps(value)[0]["capture"]
        assert isinstance(artifact, dict)
        replace_source(artifact, lambda capture: capture["history"]["records"][1].update(position=9))

        with pytest.raises(DocumentError, match="array index"):
            parse_document(encoded(value))

    def test_capture_record_must_keep_its_exact_canonical_fields(self) -> None:
        value = EXAMPLES["observed"]()
        artifact = steps(value)[0]["capture"]
        assert isinstance(artifact, dict)
        replace_source(artifact, lambda capture: capture["history"]["records"][0]["record"].update(extra=True))

        with pytest.raises(DocumentError, match="canonical History record"):
            parse_document(encoded(value))

    def test_observed_child_cannot_descend_from_manual_hypothesis(self) -> None:
        value = EXAMPLES["mixed-fork"]()
        steps(value)[3]["parent"] = 1

        with pytest.raises(DocumentError, match="never a hypothesis"):
            parse_document(encoded(value))

    def test_observed_child_must_be_an_exact_history_extension(self) -> None:
        value = EXAMPLES["mixed-fork"]()
        child = steps(value)[3]["capture"]
        assert isinstance(child, dict)
        replace_source(
            child,
            lambda capture: capture["history"]["records"][1]["record"]["tokens"][0].update(
                data={"result": "rewritten"}
            ),
        )

        with pytest.raises(DocumentError, match="replayed History|strict exact extension|cannot be replayed"):
            parse_document(encoded(value))

    def test_simulated_child_initial_marking_must_equal_parent_checkpoint(self) -> None:
        value = EXAMPLES["mixed-fork"]()
        result = steps(value)[2]["result"]
        assert isinstance(result, dict)
        replace_source(
            result,
            lambda simulation: simulation["scenario"]["initial_marking"][0]["tokens"][0].update(
                data={"result": "another-hypothesis"}
            ),
        )

        with pytest.raises(DocumentError, match="initial marking must equal"):
            parse_document(encoded(value))

    def test_view_cannot_name_a_foreign_node_or_change_definition_identity(self) -> None:
        value = EXAMPLES["definition-with-view"]()
        accepted = parse_document(encoded(value))
        value["view"]["nodes"][0]["node"] = "foreign"

        with pytest.raises(DocumentError, match="foreign node"):
            parse_document(encoded(value))

        assert accepted.definition_identity == parse_document(example_bytes("definition-only")).definition_identity
