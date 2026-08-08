"""Versioned, language-neutral flat Net-definition models and compiler."""

from __future__ import annotations

import json
from typing import Annotated, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from petrus.impetus.petrinet import (
    ANONYMOUS,
    AnonymousDeclaration,
    Arc,
    ArcMode,
    Cel,
    Delay,
    Net,
    NetPath,
    NetUri,
    Place,
    Transition,
    Until,
)

JSON_SAFE_INTEGER_MIN = -(2**53 - 1)
JSON_SAFE_INTEGER_MAX = 2**53 - 1

_SafeInteger = Annotated[int, Field(ge=JSON_SAFE_INTEGER_MIN, le=JSON_SAFE_INTEGER_MAX)]
_ArcPosition = Annotated[int, Field(ge=0, le=JSON_SAFE_INTEGER_MAX)]
_ArcWeight = Annotated[int, Field(ge=1, le=JSON_SAFE_INTEGER_MAX)]


class NetDefinitionError(ValueError):
    """A Net-definition document is malformed, noncanonical, or semantically invalid."""


class _DefinitionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SymbolExpression(_DefinitionModel):
    kind: Literal["symbol"]
    name: str

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        if not value or value.startswith("$"):
            raise ValueError("symbol name must be non-empty and cannot start with '$'")
        return value


class CelExpression(_DefinitionModel):
    kind: Literal["cel"]
    expression: str

    @field_validator("expression")
    @classmethod
    def valid_expression(cls, value: str) -> str:
        if not value:
            raise ValueError("CEL expression must be non-empty")
        return value


class SymbolBehavior(SymbolExpression):
    uri: str


class CelBehavior(CelExpression):
    uri: str


class AnonymousBehavior(_DefinitionModel):
    kind: Literal["anonymous"]
    uri: str


PureExpression = Annotated[SymbolExpression | CelExpression, Field(discriminator="kind")]
HandlerDefinition = Annotated[SymbolBehavior | AnonymousBehavior, Field(discriminator="kind")]
GuardDefinition = Annotated[SymbolBehavior | CelBehavior | AnonymousBehavior, Field(discriminator="kind")]


class DelayDefinition(_DefinitionModel):
    kind: Literal["delay"]
    duration: _SafeInteger


class UntilDefinition(_DefinitionModel):
    kind: Literal["until"]
    instant: _SafeInteger


TimerDefinition = Annotated[DelayDefinition | UntilDefinition, Field(discriminator="kind")]


def _path(value: str) -> str:
    path = NetPath(value)
    if str(path) != value:
        raise ValueError("path must use canonical dotted NetPath spelling")
    return value


def _tuple(value: object) -> object:
    """JSON arrays are the one wire spelling for immutable model tuples."""
    return tuple(value) if isinstance(value, list) else value


class PlaceDefinition(_DefinitionModel):
    path: str
    color: str | None

    _valid_path = field_validator("path")(_path)

    @field_validator("color")
    @classmethod
    def valid_color(cls, value: str | None) -> str | None:
        if value is not None and not value:
            raise ValueError("place color must be non-empty or null")
        return value


class TransitionDefinition(_DefinitionModel):
    path: str
    handler: HandlerDefinition | None
    guards: tuple[GuardDefinition, ...]
    timers: tuple[TimerDefinition, ...]

    _valid_path = field_validator("path")(_path)
    _tuple_fields = field_validator("guards", "timers", mode="before")(_tuple)


class ArcDefinition(_DefinitionModel):
    position: _ArcPosition
    source: str
    target: str
    mode: Literal["consume", "read", "inhibit"]
    weight: _ArcWeight
    color: str | None
    filter: PureExpression | None

    _valid_source = field_validator("source")(_path)
    _valid_target = field_validator("target")(_path)

    @field_validator("color")
    @classmethod
    def valid_color(cls, value: str | None) -> str | None:
        if value is not None and not value:
            raise ValueError("arc color must be non-empty or null")
        return value


class NetDefinitionBody(_DefinitionModel):
    name: str | None
    time_domain: Literal["integer"]
    places: tuple[PlaceDefinition, ...]
    transitions: tuple[TransitionDefinition, ...]
    arcs: tuple[ArcDefinition, ...]
    completion: PureExpression | None

    _tuple_fields = field_validator("places", "transitions", "arcs", mode="before")(_tuple)

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str | None) -> str | None:
        if value is not None and not value:
            raise ValueError("Net name must be non-empty or null")
        return value

    @model_validator(mode="after")
    def canonical_collections(self) -> NetDefinitionBody:
        place_paths = tuple(place.path for place in self.places)
        transition_paths = tuple(transition.path for transition in self.transitions)
        if place_paths != tuple(sorted(place_paths, key=_unicode_scalar_key)) or len(place_paths) != len(
            set(place_paths)
        ):
            raise ValueError("places must have unique paths sorted by Unicode scalar value")
        if transition_paths != tuple(sorted(transition_paths, key=_unicode_scalar_key)) or len(transition_paths) != len(
            set(transition_paths)
        ):
            raise ValueError("transitions must have unique paths sorted by Unicode scalar value")
        if tuple(arc.position for arc in self.arcs) != tuple(range(len(self.arcs))):
            raise ValueError("arc positions must be the dense ordered range [0, len(arcs))")
        return self


class NetDefinitionV3(_DefinitionModel):
    """One canonical flat, complete, implementation-free Net definition."""

    format: Literal["petrus-net-definition"]
    version: Literal[3]
    definition: NetDefinitionBody


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise NetDefinitionError(f"duplicate JSON member {key!r}")
        result[key] = value
    return result


def _no_constant(value: str) -> None:
    raise NetDefinitionError(f"non-finite JSON number {value}")


def _parse_integer(value: str) -> int:
    integer = int(value)
    if not JSON_SAFE_INTEGER_MIN <= integer <= JSON_SAFE_INTEGER_MAX:
        raise NetDefinitionError(
            f"JSON integer {value} is outside the inclusive interoperable range "
            f"[{JSON_SAFE_INTEGER_MIN}, {JSON_SAFE_INTEGER_MAX}]"
        )
    return integer


def _no_float(value: str) -> None:
    raise NetDefinitionError(f"v3 JSON numbers must use integer token spelling, got {value}")


def _validate_unicode(value: object) -> None:
    if isinstance(value, str):
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise NetDefinitionError("JSON strings must contain Unicode scalar values")
    elif isinstance(value, list | tuple):
        for item in value:
            _validate_unicode(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            _validate_unicode(key)
            _validate_unicode(item)


def _unicode_scalar_key(value: str) -> tuple[int, ...]:
    """Return the protocol-owned lexicographic Unicode scalar-value key."""
    return tuple(ord(character) for character in value)


def parse_net_definition(payload: bytes | str) -> NetDefinitionV3:
    """Strictly parse and semantically admit one canonical v3 document."""
    try:
        text = payload.decode("utf-8", errors="strict") if isinstance(payload, bytes) else payload
        value = json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_int=_parse_integer,
            parse_float=_no_float,
            parse_constant=_no_constant,
        )
        _validate_unicode(value)
        document = NetDefinitionV3.model_validate(value, strict=True)
        compile_net_definition(document)
        return document
    except NetDefinitionError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError, ValueError, RecursionError) as error:
        raise NetDefinitionError(f"invalid Petrus Net-definition v3: {error}") from None


def serialize_net_definition(document: NetDefinitionV3) -> bytes:
    """Validate and deterministically serialize one canonical v3 document."""
    try:
        compile_net_definition(document)
        value = document.model_dump(mode="json")
        _validate_unicode(value)
        return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode()
    except NetDefinitionError:
        raise
    except (UnicodeEncodeError, ValueError, RecursionError) as error:
        raise NetDefinitionError(f"cannot serialize Petrus Net-definition v3: {error}") from None


def _pure(value: PureExpression | None):
    if value is None:
        return None
    return value.name if isinstance(value, SymbolExpression) else Cel(value.expression)


def _behavior(value: HandlerDefinition | GuardDefinition | None):
    if value is None:
        return None
    if isinstance(value, SymbolBehavior):
        return value.name
    if isinstance(value, CelBehavior):
        return Cel(value.expression)
    return ANONYMOUS


def compile_net_definition(document: NetDefinitionV3) -> Net:
    """Compile one admitted v3 document through the canonical Net semantic boundary."""
    body = document.definition
    try:
        net = Net(
            places=(Place(NetPath(place.path), place.color) for place in body.places),
            transitions=(
                Transition(
                    NetPath(transition.path),
                    handler=_behavior(transition.handler),
                    guards=tuple(_behavior(guard) for guard in transition.guards),
                    timers=tuple(
                        Delay(timer.duration) if isinstance(timer, DelayDefinition) else Until(timer.instant)
                        for timer in transition.timers
                    ),
                )
                for transition in body.transitions
            ),
            arcs=(
                Arc(
                    NetPath(arc.source),
                    NetPath(arc.target),
                    ArcMode(arc.mode),
                    arc.weight,
                    arc.color,
                    _pure(arc.filter),
                )
                for arc in body.arcs
            ),
            completion=_pure(body.completion),
            name=body.name,
        )
    except ValueError as error:
        raise NetDefinitionError(f"invalid Petrus Net-definition v3 semantics: {error}") from None
    projected = project_net_definition(net)
    if projected != document:
        raise NetDefinitionError("Petrus Net-definition v3 must already be canonical and exactly projectable")
    return net


def _project_pure(value: object) -> PureExpression | None:
    if value is None:
        return None
    if isinstance(value, str):
        return SymbolExpression(kind="symbol", name=value)
    if isinstance(value, Cel):
        return CelExpression(kind="cel", expression=value.expression)
    raise NetDefinitionError(f"Net has no v3 pure-expression projection for {value!r}")


def _project_behavior(value: object, uri: NetUri) -> HandlerDefinition | GuardDefinition:
    if isinstance(value, str):
        return SymbolBehavior(kind="symbol", name=value, uri=str(uri))
    if isinstance(value, Cel):
        return CelBehavior(kind="cel", expression=value.expression, uri=str(uri))
    if isinstance(value, AnonymousDeclaration):
        return AnonymousBehavior(kind="anonymous", uri=str(uri))
    raise NetDefinitionError(f"Net has no v3 behavior projection for {value!r}")


def _integer(value: object, subject: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise NetDefinitionError(f"v3 integer time domain requires {subject} to be an integer, got {value!r}")
    if not JSON_SAFE_INTEGER_MIN <= value <= JSON_SAFE_INTEGER_MAX:
        raise NetDefinitionError(
            f"v3 {subject} {value!r} is outside the inclusive interoperable range "
            f"[{JSON_SAFE_INTEGER_MIN}, {JSON_SAFE_INTEGER_MAX}]"
        )
    return value


def project_net_definition(net: Net) -> NetDefinitionV3:
    """Project one canonical runtime Net into its exact v3 cross-system definition."""
    places = tuple(
        PlaceDefinition(path=str(path), color=place.color)
        for path, place in sorted(net.places.items(), key=lambda item: _unicode_scalar_key(str(item[0])))
    )
    transitions = []
    for path, transition in sorted(net.transitions.items(), key=lambda item: _unicode_scalar_key(str(item[0]))):
        handler_uri = net.handler_uri(path)
        handler = None
        if transition.handler is not None:
            if handler_uri is None:  # pragma: no cover - Net owns this invariant
                raise AssertionError("declared handler has no URI")
            handler = cast(HandlerDefinition, _project_behavior(transition.handler, handler_uri))
        guards = tuple(
            _project_behavior(guard, uri) for guard, uri in zip(transition.guards, net.guard_uris(path), strict=True)
        )
        timers = tuple(
            DelayDefinition(kind="delay", duration=_integer(timer.duration, "Delay duration"))
            if isinstance(timer, Delay)
            else UntilDefinition(kind="until", instant=_integer(timer.instant, "Until instant"))
            for timer in transition.timers
        )
        transitions.append(TransitionDefinition(path=str(path), handler=handler, guards=guards, timers=timers))
    arcs = tuple(
        ArcDefinition(
            position=_integer(position, "arc position"),
            source=str(arc.source),
            target=str(arc.target),
            mode=arc.mode.value,
            weight=_integer(arc.weight, "arc weight"),
            color=arc.color,
            filter=_project_pure(arc.filter),
        )
        for position, arc in enumerate(net.arcs)
    )
    document = NetDefinitionV3(
        format="petrus-net-definition",
        version=3,
        definition=NetDefinitionBody(
            name=net.name,
            time_domain="integer",
            places=places,
            transitions=tuple(transitions),
            arcs=arcs,
            completion=_project_pure(net.completion),
        ),
    )
    _validate_unicode(document.model_dump(mode="python"))
    return document


__all__ = [
    "AnonymousBehavior",
    "ArcDefinition",
    "CelBehavior",
    "CelExpression",
    "DelayDefinition",
    "JSON_SAFE_INTEGER_MAX",
    "JSON_SAFE_INTEGER_MIN",
    "NetDefinitionBody",
    "NetDefinitionError",
    "NetDefinitionV3",
    "PlaceDefinition",
    "SymbolBehavior",
    "SymbolExpression",
    "TransitionDefinition",
    "UntilDefinition",
    "compile_net_definition",
    "parse_net_definition",
    "project_net_definition",
    "serialize_net_definition",
]
