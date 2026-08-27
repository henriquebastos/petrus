"""Portable Petrus Net documents with optional view and execution lineage."""

from __future__ import annotations

from hashlib import sha256
import json
import math
from typing import Literal, Mapping, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from petrus.impetus.net_definition import (
    JSON_SAFE_INTEGER_MAX,
    JSON_SAFE_INTEGER_MIN,
    NetDefinitionV3,
    compile_net_definition,
    project_net_definition,
    serialize_net_definition,
)
from petrus.impetus.petrinet import Net, NetPath


class NetDocumentError(ValueError):
    """A Net document is malformed, noncanonical, or semantically invalid."""


class _DocumentModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def _path(value: str) -> str:
    path = NetPath(value)
    if str(path) != value:
        raise ValueError("node must use canonical dotted NetPath spelling")
    return value


def _tuple(value: object) -> object:
    """JSON arrays are the one wire spelling for immutable model tuples."""
    return tuple(value) if isinstance(value, list) else value


def _coordinate(value: object) -> object:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("coordinate must be a JSON number")
    try:
        finite = math.isfinite(float(value))
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError("coordinate must be a finite interoperable JSON number")
    return value


def _unicode_scalar_key(value: str) -> tuple[int, ...]:
    return tuple(ord(character) for character in value)


def _version_one(value: object) -> object:
    if type(value) is not int or value != 1:
        raise ValueError("version must be the integer 1")
    return value


def _strict_json_container(value: list[object] | dict[object, object]) -> object:
    if isinstance(value, list):
        for item in value:
            _strict_json(item)
        return value
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError("JSON object member names must be strings")
        _strict_json(key)
        _strict_json(item)
    return value


def _strict_json_number(value: int | float) -> int | float:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("JSON numbers must be finite")
    if isinstance(value, int) or value.is_integer():
        if not JSON_SAFE_INTEGER_MIN <= value <= JSON_SAFE_INTEGER_MAX:
            raise ValueError("integral JSON numbers must be within the JavaScript safe-integer range")
    return value


def _strict_json(value: object) -> object:
    if value is None or type(value) is bool:
        return value
    if type(value) is int:
        return _strict_json_number(value)
    if isinstance(value, str):
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise ValueError("JSON strings must contain Unicode scalar values")
        return value
    if isinstance(value, float):
        return _strict_json_number(value)
    if isinstance(value, list):
        return _strict_json_container(cast(list[object], value))
    if isinstance(value, dict):
        return _strict_json_container(cast(dict[object, object], value))
    raise ValueError(f"value of type {type(value).__name__} is not strict JSON")


def _metadata(value: object) -> object:
    if not isinstance(value, dict):
        raise ValueError("metadata must be an object")
    return _strict_json(value)


class NodePosition(_DocumentModel):
    """One canonical Net node's presentation position."""

    node: str
    x: int | float
    y: int | float

    _valid_node = field_validator("node")(_path)
    _valid_coordinate = field_validator("x", "y", mode="before")(_coordinate)


class PortableViewV1(_DocumentModel):
    """A partial, portable set of authored node positions."""

    version: Literal[1]
    nodes: tuple[NodePosition, ...]

    _valid_version = field_validator("version", mode="before")(_version_one)
    _tuple_nodes = field_validator("nodes", mode="before")(_tuple)

    @model_validator(mode="after")
    def canonical_nodes(self) -> PortableViewV1:
        paths = tuple(node.node for node in self.nodes)
        if len(paths) != len(set(paths)):
            raise ValueError("view node paths must be unique")
        if paths != tuple(sorted(paths, key=_unicode_scalar_key)):
            raise ValueError("view nodes must be sorted by Unicode scalar value")
        return self


class MarkingToken(_DocumentModel):
    """One token in a portable sparse marking."""

    color: str | None
    data: object

    _valid_data = field_validator("data", mode="before")(_strict_json)


class PlaceMarking(_DocumentModel):
    """The nonempty token queue currently held by one place."""

    place: str
    tokens: tuple[MarkingToken, ...]

    _valid_place = field_validator("place")(_path)
    _tuple_tokens = field_validator("tokens", mode="before")(_tuple)


class LineageEntry(_DocumentModel):
    """One dense, self-contained marking in a backward-linked lineage."""

    id: int = Field(ge=0, le=JSON_SAFE_INTEGER_MAX)
    parent: int | None = Field(ge=0, le=JSON_SAFE_INTEGER_MAX)
    provenance: Literal["observed", "simulated", "manual"]
    marking: tuple[PlaceMarking, ...]
    metadata: dict[str, object]

    _tuple_marking = field_validator("marking", mode="before")(_tuple)
    _valid_metadata = field_validator("metadata", mode="before")(_metadata)


class ExecutionLineage(_DocumentModel):
    """One flat, forkable sequence of complete sparse markings."""

    head: int = Field(ge=0, le=JSON_SAFE_INTEGER_MAX)
    entries: tuple[LineageEntry, ...]

    _tuple_entries = field_validator("entries", mode="before")(_tuple)


class NetDocumentV1(_DocumentModel):
    """One Net definition with optional view data and execution lineage."""

    format: Literal["petrus-net-document"]
    version: Literal[1]
    definition: NetDefinitionV3
    view: PortableViewV1 | None = None
    lineage: ExecutionLineage | None = None

    _valid_version = field_validator("version", mode="before")(_version_one)


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise NetDocumentError(f"duplicate JSON member {key!r}")
        result[key] = value
    return result


def _no_constant(value: str) -> None:
    raise NetDocumentError(f"non-finite JSON number {value}")


def _marking(
    value: tuple[PlaceMarking, ...],
    definition: NetDefinitionV3,
    path: str,
) -> None:
    places = {place.path: place for place in definition.definition.places}
    names = tuple(entry.place for entry in value)
    if names != tuple(sorted(names, key=_unicode_scalar_key)):
        raise NetDocumentError(f"{path} places must be sorted by Unicode scalar value")
    if len(names) != len(set(names)):
        raise NetDocumentError(f"{path} places must be unique")
    for index, entry in enumerate(value):
        item_path = f"{path}[{index}]"
        place = places.get(entry.place)
        if place is None:
            raise NetDocumentError(f"{item_path}.place names foreign place {entry.place!r}")
        if not entry.tokens:
            raise NetDocumentError(f"{item_path}.tokens must be nonempty in sparse marking form")
        for token_index, token in enumerate(entry.tokens):
            token_path = f"{item_path}.tokens[{token_index}]"
            if token.color is not None and not token.color:
                raise NetDocumentError(f"{token_path}.color must be a nonempty string or null")
            if place.color is not None and token.color != place.color:
                raise NetDocumentError(
                    f"{token_path}.color {token.color!r} does not match place {entry.place!r} color {place.color!r}"
                )


def _lineage(lineage: ExecutionLineage, definition: NetDefinitionV3) -> None:
    if not lineage.entries:
        raise NetDocumentError("lineage.entries must be nonempty")
    if lineage.head >= len(lineage.entries):
        raise NetDocumentError("lineage.head must name an existing entry")
    for index, entry in enumerate(lineage.entries):
        path = f"lineage.entries[{index}]"
        if entry.id != index:
            raise NetDocumentError(f"{path}.id must equal its array index")
        if index == 0:
            if entry.parent is not None:
                raise NetDocumentError("lineage.entries[0] must be the sole root with parent null")
        elif entry.parent is None or entry.parent >= index:
            raise NetDocumentError(f"{path}.parent must be a smaller entry id")
        _marking(entry.marking, definition, f"{path}.marking")


def _validate_document(document: NetDocumentV1) -> None:
    compile_net_definition(document.definition)
    if document.view is not None:
        body = document.definition.definition
        definition_nodes = {place.path for place in body.places} | {transition.path for transition in body.transitions}
        foreign = tuple(node.node for node in document.view.nodes if node.node not in definition_nodes)
        if foreign:
            raise NetDocumentError(f"view contains foreign definition node {foreign[0]!r}")
    if document.lineage is not None:
        _lineage(document.lineage, document.definition)


def parse_net_document(payload: bytes | str) -> NetDocumentV1:
    """Strictly parse and semantically admit one portable Net document."""
    try:
        text = payload.decode("utf-8", errors="strict") if isinstance(payload, bytes) else payload
        value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_no_constant)
        _strict_json(value)
        if isinstance(value, dict):
            for component in ("view", "lineage"):
                if component in value and value[component] is None:
                    raise NetDocumentError(f"{component} must be absent or an object, not null")
        document = NetDocumentV1.model_validate(value, strict=True)
        _validate_document(document)
        return document
    except NetDocumentError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, ValueError, RecursionError) as error:
        raise NetDocumentError(f"invalid Petrus Net document v1: {error}") from None


def serialize_net_document(document: NetDocumentV1) -> bytes:
    """Validate and deterministically serialize one portable Net document."""
    try:
        document = NetDocumentV1.model_validate(document.model_dump(mode="python"), strict=True)
        _validate_document(document)
        value = document.model_dump(mode="json")
        if document.view is None:
            del value["view"]
        if document.lineage is None:
            del value["lineage"]
        _strict_json(value)
        return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode()
    except NetDocumentError:
        raise
    except (UnicodeEncodeError, ValidationError, ValueError, RecursionError) as error:
        raise NetDocumentError(f"cannot serialize Petrus Net document v1: {error}") from None


def project_net_document(
    net: Net,
    positions: Mapping[str | NetPath, tuple[int | float, int | float]] | None = None,
    *,
    lineage: ExecutionLineage | None = None,
) -> NetDocumentV1:
    """Project a runtime Net, optional positions, and optional lineage."""
    try:
        view = None
        if positions is not None:
            nodes = tuple(
                NodePosition(node=str(node), x=position[0], y=position[1])
                for node, position in sorted(positions.items(), key=lambda item: _unicode_scalar_key(str(item[0])))
            )
            view = PortableViewV1(version=1, nodes=nodes)
        document = NetDocumentV1(
            format="petrus-net-document",
            version=1,
            definition=project_net_definition(net),
            view=view,
            lineage=lineage,
        )
        _validate_document(document)
        return document
    except NetDocumentError:
        raise
    except (ValidationError, ValueError, IndexError, TypeError, OverflowError) as error:
        raise NetDocumentError(f"cannot project Petrus Net document v1: {error}") from None


def definition_identity(document: NetDocumentV1) -> str:
    """Return the lowercase SHA-256 identity of the canonical embedded definition."""
    return sha256(serialize_net_definition(document.definition)).hexdigest()


__all__ = [
    "ExecutionLineage",
    "LineageEntry",
    "MarkingToken",
    "NetDocumentError",
    "NetDocumentV1",
    "NodePosition",
    "PlaceMarking",
    "PortableViewV1",
    "definition_identity",
    "parse_net_document",
    "project_net_document",
    "serialize_net_document",
]
