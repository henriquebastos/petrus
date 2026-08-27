"""Conformance tests for the portable Net document definition/view foundation."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pytest

from petrus.impetus.net_definition import (
    compile_net_definition,
    parse_net_definition,
    serialize_net_definition,
)
from petrus.impetus.net_document import (
    NetDocumentError,
    NetDocumentV1,
    definition_identity,
    parse_net_document,
    project_net_document,
    serialize_net_document,
)


ROOT = Path(__file__).parents[3]
DEFINITION_FIXTURE = ROOT / "spec" / "net-definition-v3.json"
DOCUMENT_FIXTURE = ROOT / "spec" / "net-document-v1.json"
INVALID_VIEW_FIXTURE = ROOT / "spec" / "net-document-v1-invalid-foreign-view.json"


def definition():
    return parse_net_definition(DEFINITION_FIXTURE.read_bytes())


def document_value() -> dict[str, object]:
    return {
        "format": "petrus-net-document",
        "version": 1,
        "definition": definition().model_dump(mode="json"),
        "view": {
            "version": 1,
            "nodes": [
                {"node": "review.correctness.pending", "x": 20.5, "y": -40},
                {"node": "review.correctness.review", "x": 240, "y": 80.25},
            ],
        },
    }


def test_projection_parse_serialize_and_identity_fixed_points() -> None:
    canonical = definition()
    net = compile_net_definition(canonical)
    projected = project_net_document(
        net,
        {
            "review.correctness.pending": (20.5, -40),
            "review.correctness.review": (240, 80.25),
        },
    )

    encoded = serialize_net_document(projected)
    parsed = parse_net_document(encoded)

    assert parsed == projected
    assert parsed.definition == canonical
    assert serialize_net_document(parsed) == encoded
    assert encoded == DOCUMENT_FIXTURE.read_bytes()
    assert encoded.endswith(b"\n")
    assert definition_identity(parsed) == sha256(serialize_net_definition(canonical)).hexdigest()


def test_definition_only_document_omits_view_and_view_never_changes_identity() -> None:
    net = compile_net_definition(definition())
    plain = project_net_document(net)
    arranged = project_net_document(net, {"ingest": (1.25, 2.5)})

    assert plain.view is None
    assert "view" not in json.loads(serialize_net_document(plain))
    assert definition_identity(plain) == definition_identity(arranged)


def test_partial_fractional_view_is_valid_and_schema_is_strict() -> None:
    document = parse_net_document(json.dumps(document_value(), ensure_ascii=False))
    schema = NetDocumentV1.model_json_schema()

    assert [node.node for node in document.view.nodes] == [
        "review.correctness.pending",
        "review.correctness.review",
    ]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["format"]["const"] == "petrus-net-document"
    assert schema["properties"]["version"]["const"] == 1
    assert all(item.get("additionalProperties") is False for item in schema["$defs"].values())


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (lambda value: value.update(version=True), "version"),
        (lambda value: value.update(format="petrus-net-definition"), "format"),
        (lambda value: value.update(extra=True), "extra"),
        (lambda value: value.update(view=None), "absent or an object"),
        (lambda value: value["view"].update(version=True), "view.version"),
        (lambda value: value["view"].update(extra=True), "extra"),
        (lambda value: value["view"]["nodes"].reverse(), "Unicode scalar"),
        (
            lambda value: value["view"]["nodes"].append(deepcopy(value["view"]["nodes"][0])),
            "unique",
        ),
        (lambda value: value["view"]["nodes"][0].update(node="foreign"), "foreign"),
        (lambda value: value["view"]["nodes"][0].update(node="review..pending"), "NetPath"),
        (lambda value: value["definition"].update(version=2), "definition"),
    ],
)
def test_malformed_or_confused_documents_are_refused(change, expected: str) -> None:
    value = document_value()
    change(value)

    with pytest.raises(NetDocumentError, match=expected):
        parse_net_document(json.dumps(value, ensure_ascii=False))


@pytest.mark.parametrize(
    "payload",
    [
        b'{"format":"petrus-net-document","format":"petrus-net-document","version":1,"definition":{}}',
        b'{"format":"petrus-net-document","version":1,"definition":{},"view":{"version":1,"nodes":[],"x":NaN}}',
        b"\xff",
        b'{"format":"petrus-net-document","version":1,"definition":"\\ud800"}',
    ],
)
def test_strict_json_refuses_duplicate_nonfinite_utf8_and_surrogate(payload: bytes) -> None:
    with pytest.raises(NetDocumentError):
        parse_net_document(payload)


def test_negative_interoperability_fixture_is_refused() -> None:
    with pytest.raises(NetDocumentError, match="foreign"):
        parse_net_document(INVALID_VIEW_FIXTURE.read_bytes())


@pytest.mark.parametrize("coordinate", [float("nan"), float("inf"), float("-inf"), 10**400, True, "20"])
def test_view_coordinates_must_be_finite_interoperable_json_numbers(coordinate: object) -> None:
    value = document_value()
    value["view"]["nodes"][0]["x"] = coordinate

    if isinstance(coordinate, float) and not coordinate.is_integer():
        payload = json.dumps(value, allow_nan=True)
    else:
        payload = json.dumps(value)
    with pytest.raises(NetDocumentError, match="coordinate|finite|number"):
        parse_net_document(payload)


def test_direct_model_serialization_revalidates_foreign_nodes_and_nonfinite_coordinates() -> None:
    value = document_value()
    document = NetDocumentV1.model_validate(value, strict=True)
    value["view"]["nodes"][0]["node"] = "foreign"
    foreign = NetDocumentV1.model_validate(value, strict=True)

    with pytest.raises(NetDocumentError, match="foreign"):
        serialize_net_document(foreign)
    with pytest.raises(NetDocumentError):
        project_net_document(compile_net_definition(definition()), {"ingest": (float("inf"), 0)})
    assert serialize_net_document(document) == DOCUMENT_FIXTURE.read_bytes()
