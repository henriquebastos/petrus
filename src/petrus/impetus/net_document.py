"""Portable Petrus Net documents with optional presentation positions."""

from __future__ import annotations

from hashlib import sha256
import json
import math
from typing import Literal, Mapping

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

from petrus.impetus.net_definition import (
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


class NetDocumentV1(_DocumentModel):
    """One canonical Net definition with optional identity-neutral view data."""

    format: Literal["petrus-net-document"]
    version: Literal[1]
    definition: NetDefinitionV3
    view: PortableViewV1 | None = None

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


def _validate_unicode(value: object) -> None:
    if isinstance(value, str):
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise NetDocumentError("JSON strings must contain Unicode scalar values")
    elif isinstance(value, list | tuple):
        for item in value:
            _validate_unicode(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            _validate_unicode(key)
            _validate_unicode(item)


def _validate_document(document: NetDocumentV1) -> None:
    compile_net_definition(document.definition)
    if document.view is None:
        return
    body = document.definition.definition
    definition_nodes = {place.path for place in body.places} | {transition.path for transition in body.transitions}
    foreign = tuple(node.node for node in document.view.nodes if node.node not in definition_nodes)
    if foreign:
        raise NetDocumentError(f"view contains foreign definition node {foreign[0]!r}")


def parse_net_document(payload: bytes | str) -> NetDocumentV1:
    """Strictly parse and semantically admit one portable Net document."""
    try:
        text = payload.decode("utf-8", errors="strict") if isinstance(payload, bytes) else payload
        value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_no_constant)
        _validate_unicode(value)
        if isinstance(value, dict) and "view" in value and value["view"] is None:
            raise NetDocumentError("view must be absent or an object, not null")
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
        _validate_unicode(value)
        return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode()
    except NetDocumentError:
        raise
    except (UnicodeEncodeError, ValidationError, ValueError, RecursionError) as error:
        raise NetDocumentError(f"cannot serialize Petrus Net document v1: {error}") from None


def project_net_document(
    net: Net,
    positions: Mapping[str | NetPath, tuple[int | float, int | float]] | None = None,
) -> NetDocumentV1:
    """Project a runtime Net and optional node positions into a portable document."""
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
    "NetDocumentError",
    "NetDocumentV1",
    "NodePosition",
    "PortableViewV1",
    "definition_identity",
    "parse_net_document",
    "project_net_document",
    "serialize_net_document",
]
