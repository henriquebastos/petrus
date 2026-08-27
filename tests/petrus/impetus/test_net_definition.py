"""Conformance tests for the flat, language-neutral Net-definition protocol."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from petrus.impetus.net_definition import (
    JSON_SAFE_INTEGER_MAX,
    JSON_SAFE_INTEGER_MIN,
    NetDefinitionError,
    NetDefinitionV3,
    compile_net_definition,
    parse_net_definition,
    project_net_definition,
    serialize_net_definition,
)
from petrus.impetus.observation import definition as observation_definition
from petrus.impetus.petrinet import (
    ANONYMOUS,
    Arc,
    ArcMode,
    Cel,
    Delay,
    Net,
    NetPath,
    Place,
    Transition,
    Until,
)

ROOT = Path(__file__).parents[3]
FIXTURE = ROOT / "spec" / "net-definition-v3.json"
INTEROPERABILITY_FIXTURE = ROOT / "spec" / "net-definition-v3-interoperability.json"
INVALID_INTEGER_FIXTURE = ROOT / "spec" / "net-definition-v3-invalid-integer.json"
INVALID_UTF16_ORDER_FIXTURE = ROOT / "spec" / "net-definition-v3-invalid-utf16-order.json"
DOCUMENT_FIXTURE = ROOT / "spec" / "net-document-v1-inspection.json"


def rich_net() -> Net:
    source, pending, context, blocked, done, review = map(
        NetPath,
        ("source", "review.pending", "review.context", "review.blocked", "review.done", "review.run"),
    )
    return Net(
        places=(
            Place(pending, "Work"),
            Place(context, "Context"),
            Place(blocked, "Block"),
            Place(done, "Done"),
        ),
        transitions=(
            Transition(source),
            Transition(
                review,
                handler=ANONYMOUS,
                guards=("ready", Cel("size(review.pending) > 0"), ANONYMOUS),
                timers=(Delay(3), Until(11)),
            ),
        ),
        arcs=(
            Arc(source, pending),
            Arc(pending, review, filter=Cel("priority >= 1")),
            Arc(context, review, ArcMode.READ, filter="visible"),
            Arc(blocked, review, ArcMode.INHIBIT),
            Arc(review, done),
        ),
        completion=Cel("size(review.done) > 0"),
        name="portable-review",
    )


def document_dict() -> dict[str, object]:
    return project_net_definition(rich_net()).model_dump(mode="json")


def test_net_project_compile_and_json_fixed_points() -> None:
    document = project_net_definition(rich_net())

    encoded = serialize_net_definition(document)
    parsed = parse_net_definition(encoded)
    compiled = compile_net_definition(parsed)

    assert parsed == document
    assert project_net_definition(compiled) == document
    assert serialize_net_definition(parsed) == encoded
    assert observation_definition(compiled) == document.definition.model_dump(mode="json")
    assert encoded.endswith(b"\n")


def test_parallel_arcs_round_trip_without_wire_identity_and_rederive_the_same_uris() -> None:
    p, t, out = map(NetPath, ("p", "t", "out"))
    net = Net(
        [Place(p), Place(out)],
        [Transition(t)],
        [Arc(p, t, filter="same"), Arc(p, t, ArcMode.READ, filter="same"), Arc(t, out)],
    )

    document = project_net_definition(net)
    wire = serialize_net_definition(document)
    compiled = compile_net_definition(parse_net_definition(wire))

    assert compiled.arc_uris() == net.arc_uris()
    assert compiled.filter_uris() == net.filter_uris()
    assert serialize_net_definition(project_net_definition(compiled)) == wire
    assert all("identity" not in arc for arc in document.definition.model_dump(mode="json")["arcs"])


def test_exact_fixture_is_the_dsl_document_definition_in_loadable_v3_envelope() -> None:
    fixture = FIXTURE.read_bytes()
    document = parse_net_definition(fixture)
    portable = json.loads(DOCUMENT_FIXTURE.read_bytes())

    assert serialize_net_definition(document) == fixture
    assert document.model_dump(mode="json") == portable["definition"]
    assert project_net_definition(compile_net_definition(document)) == document


def test_cross_language_integer_and_scalar_order_fixture_is_an_exact_fixed_point() -> None:
    fixture = INTEROPERABILITY_FIXTURE.read_bytes()

    document = parse_net_definition(fixture)

    assert tuple(place.path for place in document.definition.places) == ("place.\ue000", "place.😀")
    assert tuple(transition.path for transition in document.definition.transitions) == (
        "transition.\ue000",
        "transition.😀",
    )
    assert document.definition.transitions[0].timers[0].duration == JSON_SAFE_INTEGER_MIN
    assert document.definition.transitions[1].timers[0].instant == JSON_SAFE_INTEGER_MAX
    assert document.definition.arcs[0].weight == JSON_SAFE_INTEGER_MAX
    assert serialize_net_definition(document) == fixture
    assert serialize_net_definition(project_net_definition(compile_net_definition(document))) == fixture


@pytest.mark.parametrize("fixture", [INVALID_INTEGER_FIXTURE, INVALID_UTF16_ORDER_FIXTURE])
def test_cross_language_negative_fixtures_are_refused(fixture: Path) -> None:
    with pytest.raises(NetDefinitionError):
        parse_net_definition(fixture.read_bytes())


def test_pydantic_schema_is_strict_and_versioned() -> None:
    schema = NetDefinitionV3.model_json_schema()

    assert schema["additionalProperties"] is False
    assert schema["properties"]["format"]["const"] == "petrus-net-definition"
    assert schema["properties"]["version"]["const"] == 3
    assert all(definition.get("additionalProperties") is False for definition in schema["$defs"].values())
    assert schema["$defs"]["DelayDefinition"]["properties"]["duration"] == {
        "maximum": JSON_SAFE_INTEGER_MAX,
        "minimum": JSON_SAFE_INTEGER_MIN,
        "title": "Duration",
        "type": "integer",
    }
    assert schema["$defs"]["UntilDefinition"]["properties"]["instant"] == {
        "maximum": JSON_SAFE_INTEGER_MAX,
        "minimum": JSON_SAFE_INTEGER_MIN,
        "title": "Instant",
        "type": "integer",
    }
    assert schema["$defs"]["ArcDefinition"]["properties"]["position"]["maximum"] == JSON_SAFE_INTEGER_MAX
    assert schema["$defs"]["ArcDefinition"]["properties"]["position"]["minimum"] == 0
    assert schema["$defs"]["ArcDefinition"]["properties"]["weight"]["maximum"] == JSON_SAFE_INTEGER_MAX
    assert schema["$defs"]["ArcDefinition"]["properties"]["weight"]["minimum"] == 1


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (lambda value: value.update(version=True), "version"),
        (lambda value: value.update(format="foreign-format"), "format"),
        (lambda value: value.update(extra=True), "extra"),
        (lambda value: value["definition"]["places"].reverse(), "Unicode scalar"),
        (lambda value: value["definition"]["places"].append(value["definition"]["places"][0]), "unique"),
        (lambda value: value["definition"]["arcs"][0].update(position=2), "dense ordered"),
        (lambda value: value["definition"]["arcs"][0].update(color=None), "exactly projectable"),
        (lambda value: value["definition"]["arcs"][0].update(target="missing"), "semantics"),
        (
            lambda value: value["definition"]["transitions"][0]["handler"].update(uri="transition:/wrong#handler"),
            "exactly projectable",
        ),
        (
            lambda value: value["definition"]["transitions"][1].update(
                guards=[{"kind": "cel", "expression": "true", "uri": "transition:/source#guard:$0"}]
            ),
            "semantics",
        ),
    ],
)
def test_noncanonical_or_invalid_documents_are_refused(change, expected: str) -> None:
    value = deepcopy(document_dict())
    change(value)

    with pytest.raises(NetDefinitionError, match=expected):
        parse_net_definition(json.dumps(value).encode())


@pytest.mark.parametrize(
    "payload",
    [
        b'{"format":"petrus-net-definition","format":"petrus-net-definition","version":3,"definition":{}}',
        b'{"format":"petrus-net-definition","version":3,"definition":NaN}',
        b"\xff",
        b'{"format":"petrus-net-definition","version":3,"definition":"\\ud800"}',
    ],
)
def test_strict_json_refuses_duplicate_nonfinite_utf8_and_surrogate(payload: bytes) -> None:
    with pytest.raises(NetDefinitionError):
        parse_net_definition(payload)


@pytest.mark.parametrize(
    "payload",
    [
        b'{"version":3.0}',
        b'{"version":3e0}',
        b'{"version":9007199254740992}',
        b'{"version":-9007199254740992}',
    ],
)
def test_every_json_number_token_is_interoperably_admitted_before_shape(payload: bytes) -> None:
    with pytest.raises(NetDefinitionError, match="integer token spelling|interoperable range"):
        parse_net_definition(payload)


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value.update(version=JSON_SAFE_INTEGER_MAX + 1),
        lambda value: value["definition"]["transitions"][0]["timers"][0].update(duration=JSON_SAFE_INTEGER_MIN - 1),
        lambda value: value["definition"]["transitions"][0]["timers"][1].update(instant=JSON_SAFE_INTEGER_MAX + 1),
        lambda value: value["definition"]["arcs"][0].update(position=JSON_SAFE_INTEGER_MAX + 1),
        lambda value: value["definition"]["arcs"][0].update(weight=JSON_SAFE_INTEGER_MAX + 1),
    ],
)
def test_every_schema_owned_integer_refuses_values_outside_interoperable_range(change) -> None:
    value = deepcopy(document_dict())
    change(value)

    with pytest.raises(NetDefinitionError, match="interoperable range"):
        parse_net_definition(json.dumps(value).encode())


def test_models_are_deeply_immutable() -> None:
    document = project_net_definition(rich_net())

    with pytest.raises((AttributeError, TypeError, ValidationError)):
        document.definition.places.append(document.definition.places[0])
    with pytest.raises((AttributeError, TypeError, ValidationError)):
        document.definition.name = "changed"


def test_runtime_projection_and_direct_model_serialization_refuse_surrogates() -> None:
    net = rich_net()
    net.name = "bad\ud800"
    with pytest.raises(NetDefinitionError, match="Unicode scalar"):
        project_net_definition(net)

    value = document_dict()
    value["definition"]["name"] = "bad\ud800"
    document = NetDefinitionV3.model_validate(value, strict=True)
    with pytest.raises(NetDefinitionError, match="Unicode scalar"):
        serialize_net_definition(document)


def test_adversarial_json_nesting_is_normalized_to_protocol_error() -> None:
    payload = b"[" * 2000 + b"]" * 2000
    with pytest.raises(NetDefinitionError):
        parse_net_definition(payload)


@pytest.mark.parametrize(
    "net",
    [
        Net(
            places=(Place(NetPath("place")),),
            transitions=(Transition(NetPath("transition"), timers=(Until(JSON_SAFE_INTEGER_MAX + 1),)),),
            arcs=(Arc(NetPath("place"), NetPath("transition")),),
        ),
        Net(
            places=(Place(NetPath("place")),),
            transitions=(Transition(NetPath("transition")),),
            arcs=(Arc(NetPath("place"), NetPath("transition"), weight=JSON_SAFE_INTEGER_MAX + 1),),
        ),
    ],
)
def test_runtime_projection_refuses_integers_outside_interoperable_range(net: Net) -> None:
    with pytest.raises(NetDefinitionError, match="interoperable range"):
        project_net_definition(net)
