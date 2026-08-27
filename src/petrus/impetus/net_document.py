"""Portable Petrus Net documents with optional view and execution lineage."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Annotated, Literal, Mapping, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from petrus.impetus._net_document_evidence import (
    AdmittedEvidence,
    EvidenceError,
    admit_evidence,
    replay_records,
    validate_json_value,
    validate_marking,
)
from petrus.impetus.net_definition import (
    JSON_SAFE_INTEGER_MAX,
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


class MarkingToken(_DocumentModel):
    """One token in a portable sparse marking."""

    color: str | None
    data: object

    _valid_data = field_validator("data", mode="before")(validate_json_value)


class PlaceMarking(_DocumentModel):
    """Tokens currently held by one place."""

    place: str
    tokens: tuple[MarkingToken, ...]

    _tuple_tokens = field_validator("tokens", mode="before")(_tuple)


class EmbeddedArtifact(_DocumentModel):
    """Exact source bytes retained with their integrity digest."""

    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    base64: str

    @classmethod
    def from_bytes(cls, payload: bytes) -> EmbeddedArtifact:
        """Retain exact bytes using canonical padded base64."""
        return cls(
            sha256=sha256(payload).hexdigest(),
            base64=base64.b64encode(payload).decode("ascii"),
        )


class ObservationEvidenceSource(_DocumentModel):
    """A retained capture contributing one observed History suffix."""

    id: int = Field(ge=0, le=JSON_SAFE_INTEGER_MAX)
    kind: Literal["observation-capture"]
    after: int = Field(ge=0, le=JSON_SAFE_INTEGER_MAX)
    artifact: EmbeddedArtifact


class SimulationEvidenceSource(_DocumentModel):
    """A retained simulation result contributing one hypothetical History."""

    id: int = Field(ge=0, le=JSON_SAFE_INTEGER_MAX)
    kind: Literal["simulation-result"]
    after: Literal[0]
    artifact: EmbeddedArtifact

    @field_validator("after", mode="before")
    @classmethod
    def exact_zero(cls, value: object) -> object:
        if type(value) is not int or value != 0:
            raise ValueError("simulation source after must be the integer 0")
        return value


EvidenceSource = Annotated[
    ObservationEvidenceSource | SimulationEvidenceSource,
    Field(discriminator="kind"),
]


class HistoryRecordFact(_DocumentModel):
    """An exact History record retained by one evidence source."""

    kind: Literal["history-record"]
    source: int = Field(ge=0, le=JSON_SAFE_INTEGER_MAX)
    position: int = Field(ge=0, le=JSON_SAFE_INTEGER_MAX)
    record: dict[str, object]

    _valid_record = field_validator("record", mode="before")(validate_json_value)


class ManualReplacementFact(_DocumentModel):
    """An explicit hypothetical replacement of the complete marking."""

    kind: Literal["manual-replace-marking"]
    marking: tuple[PlaceMarking, ...]

    _tuple_marking = field_validator("marking", mode="before")(_tuple)


LineageFact = Annotated[HistoryRecordFact | ManualReplacementFact, Field(discriminator="kind")]


class LineageEntry(_DocumentModel):
    """One dense node in a backward-linked execution lineage."""

    id: int = Field(ge=0, le=JSON_SAFE_INTEGER_MAX)
    parent: int | None = Field(ge=0, le=JSON_SAFE_INTEGER_MAX)
    provenance: Literal["observed", "simulated", "manual"]
    fact: LineageFact
    checkpoint: tuple[PlaceMarking, ...] | None = None

    _tuple_checkpoint = field_validator("checkpoint", mode="before")(_tuple)

    @model_validator(mode="before")
    @classmethod
    def checkpoint_is_absent_or_array(cls, value: object) -> object:
        if isinstance(value, dict):
            fields = cast(dict[str, object], value)
            if "checkpoint" in fields and fields["checkpoint"] is None:
                raise ValueError("checkpoint must be absent or an array, not null")
        return value


class ExecutionLineage(_DocumentModel):
    """Retained evidence and one flat, forkable navigation sequence."""

    sources: tuple[EvidenceSource, ...]
    head: int = Field(ge=0, le=JSON_SAFE_INTEGER_MAX)
    entries: tuple[LineageEntry, ...]

    _tuple_sources = field_validator("sources", mode="before")(_tuple)
    _tuple_entries = field_validator("entries", mode="before")(_tuple)


class NetDocumentV1(_DocumentModel):
    """One Net definition with optional view data and execution lineage."""

    format: Literal["petrus-net-document"]
    version: Literal[1]
    definition: NetDefinitionV3
    view: PortableViewV1 | None = None
    lineage: ExecutionLineage | None = None

    _valid_version = field_validator("version", mode="before")(_version_one)


@dataclass(frozen=True)
class NavigationEntry:
    """A source-independent lineage entry with its resolved marking."""

    id: int
    parent: int | None
    provenance: Literal["observed", "simulated", "manual"]
    event: str
    marking: tuple[PlaceMarking, ...]


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
    elif isinstance(value, float) and not math.isfinite(value):
        raise NetDocumentError("JSON numbers must be finite")
    elif isinstance(value, list | tuple):
        for item in value:
            _validate_unicode(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            _validate_unicode(key)
            _validate_unicode(item)


def _place_markings(
    value: object,
    definition: NetDefinitionV3,
    path: str,
) -> tuple[PlaceMarking, ...]:
    normalized = validate_marking(list(value) if isinstance(value, tuple) else value, definition, path)
    return tuple(PlaceMarking.model_validate(entry, strict=True) for entry in normalized)


def _entry_marking(
    value: tuple[PlaceMarking, ...],
    definition: NetDefinitionV3,
    path: str,
) -> tuple[PlaceMarking, ...]:
    return _place_markings([entry.model_dump(mode="json") for entry in value], definition, path)


def _lineage_structure(lineage: ExecutionLineage) -> None:
    if not lineage.entries:
        raise NetDocumentError("lineage.entries must be nonempty")
    if lineage.head >= len(lineage.entries):
        raise NetDocumentError("lineage.head must name an existing entry")
    for index, entry in enumerate(lineage.entries):
        if entry.id != index:
            raise NetDocumentError(f"lineage.entries[{index}].id must equal its array index")
        if index == 0:
            if entry.parent is not None:
                raise NetDocumentError("lineage.entries[0] must be the sole root with parent null")
        elif entry.parent is None or entry.parent >= index:
            raise NetDocumentError(f"lineage.entries[{index}].parent must be a smaller entry id")


def _admit_sources(
    lineage: ExecutionLineage,
    definition: NetDefinitionV3,
) -> tuple[AdmittedEvidence, ...]:
    if not lineage.sources:
        raise NetDocumentError("lineage.sources must be nonempty")
    admitted: list[AdmittedEvidence] = []
    for index, source in enumerate(lineage.sources):
        if source.id != index:
            raise NetDocumentError(f"lineage.sources[{index}].id must equal its array index")
        admitted.append(
            admit_evidence(
                kind=source.kind,
                after=source.after,
                digest=source.artifact.sha256,
                base64_value=source.artifact.base64,
                definition=definition,
                path=f"lineage.sources[{index}]",
            )
        )
    return tuple(admitted)


def _admitted_history_fact(
    entry: LineageEntry,
    fact: HistoryRecordFact,
    sources: tuple[AdmittedEvidence, ...],
    used: list[list[int]],
    path: str,
) -> AdmittedEvidence:
    if fact.source >= len(sources):
        raise NetDocumentError(f"{path}.fact.source must name an existing evidence source")
    source = sources[fact.source]
    expected_provenance = "observed" if source.kind == "observation-capture" else "simulated"
    if entry.provenance != expected_provenance:
        raise NetDocumentError(f"{path} provenance contradicts its evidence source kind")
    if fact.position < source.after or fact.position >= len(source.records):
        raise NetDocumentError(f"{path}.fact.position is outside its source's projected range")
    if fact.record != source.records[fact.position]["record"]:
        raise NetDocumentError(f"{path}.fact.record differs from the exact retained source position")
    used[fact.source].append(fact.position)
    return source


def _root_history_sequence(
    entry: LineageEntry,
    source: AdmittedEvidence,
    markings: list[tuple[PlaceMarking, ...]],
    definition: NetDefinitionV3,
    path: str,
) -> None:
    if entry.provenance == "observed" and entry.parent is not None:
        raise NetDocumentError(f"{path} observed source root cannot descend from another entry")
    if entry.provenance == "simulated" and entry.parent is not None:
        if source.initial is None:
            raise NetDocumentError(f"{path} simulated source must expose its initial marking")
        initial = _place_markings(source.initial, definition, f"{path} source initial marking")
        if initial != markings[entry.parent]:
            raise NetDocumentError(f"{path} simulated source initial marking must equal its parent state")


def _continued_history_sequence(
    entry: LineageEntry,
    fact: HistoryRecordFact,
    source: AdmittedEvidence,
    lineage: ExecutionLineage,
    sources: tuple[AdmittedEvidence, ...],
    sequences: list[tuple[dict[str, object], ...]],
    path: str,
) -> tuple[dict[str, object], ...]:
    if entry.parent is None:
        raise NetDocumentError(f"{path} non-root History record requires a History-record parent")
    parent = lineage.entries[entry.parent]
    parent_fact = parent.fact
    if not isinstance(parent_fact, HistoryRecordFact):
        raise NetDocumentError(f"{path} non-root History record requires a History-record parent")
    if parent.provenance != entry.provenance or parent_fact.position + 1 != fact.position:
        raise NetDocumentError(f"{path} must continue a same-provenance canonical record sequence")
    sequence = sequences[entry.parent] + (fact.record,)
    if entry.provenance == "simulated" and parent_fact.source != fact.source:
        raise NetDocumentError(f"{path} simulated History cannot switch evidence sources")
    if entry.provenance == "observed":
        parent_source = sources[parent_fact.source]
        if parent_source.kind != "observation-capture" or parent_source.instance != source.instance:
            raise NetDocumentError(f"{path} observed extension must preserve Instance identity")
        expected_prefix = tuple(record["record"] for record in source.records[: fact.position])
        if sequences[entry.parent] != expected_prefix:
            raise NetDocumentError(f"{path} observed source does not exactly extend its parent History")
    return sequence


def _resolved_history_entry(
    entry: LineageEntry,
    fact: HistoryRecordFact,
    lineage: ExecutionLineage,
    definition: NetDefinitionV3,
    sources: tuple[AdmittedEvidence, ...],
    sequences: list[tuple[dict[str, object], ...]],
    markings: list[tuple[PlaceMarking, ...]],
    used: list[list[int]],
    path: str,
) -> tuple[tuple[dict[str, object], ...], tuple[PlaceMarking, ...], str]:
    source = _admitted_history_fact(entry, fact, sources, used, path)
    if fact.position == 0:
        _root_history_sequence(entry, source, markings, definition, path)
        sequence = (fact.record,)
    else:
        sequence = _continued_history_sequence(entry, fact, source, lineage, sources, sequences, path)
    marking = _place_markings(
        replay_records(sequence, definition, f"{path}.fact canonical sequence"),
        definition,
        f"{path}.fact replay marking",
    )
    event = fact.record.get("record")
    if not isinstance(event, str):
        raise NetDocumentError(f"{path}.fact.record must expose its canonical record discriminator")
    return sequence, marking, event


def _resolved_entries(
    lineage: ExecutionLineage,
    definition: NetDefinitionV3,
    sources: tuple[AdmittedEvidence, ...],
) -> tuple[NavigationEntry, ...]:
    _lineage_structure(lineage)
    sequences: list[tuple[dict[str, object], ...]] = []
    markings: list[tuple[PlaceMarking, ...]] = []
    navigation: list[NavigationEntry] = []
    used: list[list[int]] = [[] for _ in sources]

    for index, entry in enumerate(lineage.entries):
        path = f"lineage.entries[{index}]"
        if isinstance(entry.fact, ManualReplacementFact):
            if entry.provenance != "manual":
                raise NetDocumentError(f"{path} manual fact requires manual provenance")
            if entry.parent is None:
                raise NetDocumentError(f"{path} manual replacement requires a parent")
            sequence: tuple[dict[str, object], ...] = ()
            marking = _entry_marking(entry.fact.marking, definition, f"{path}.fact.marking")
            event = "ManualMarkingReplaced"
        else:
            sequence, marking, event = _resolved_history_entry(
                entry,
                entry.fact,
                lineage,
                definition,
                sources,
                sequences,
                markings,
                used,
                path,
            )

        if entry.checkpoint is not None:
            checkpoint = _entry_marking(entry.checkpoint, definition, f"{path}.checkpoint")
            if checkpoint != marking:
                raise NetDocumentError(f"{path}.checkpoint disagrees with replay-derived state")
        sequences.append(sequence)
        markings.append(marking)
        navigation.append(NavigationEntry(entry.id, entry.parent, entry.provenance, event, marking))

    for index, source in enumerate(sources):
        expected = list(range(source.after, len(source.records)))
        if used[index] != expected:
            raise NetDocumentError(
                f"lineage source {index} must project each source position from after through frontier exactly once"
            )
        final_entry = next(
            entry
            for entry in reversed(lineage.entries)
            if isinstance(entry.fact, HistoryRecordFact) and entry.fact.source == index
        )
        final_marking = _place_markings(source.marking, definition, f"lineage source {index} snapshot marking")
        if markings[final_entry.id] != final_marking:
            raise NetDocumentError(f"lineage source {index} final projected marking disagrees with its source snapshot")
    return tuple(navigation)


def _resolve_lineage(document: NetDocumentV1) -> tuple[NavigationEntry, ...]:
    if document.lineage is None:
        return ()
    sources = _admit_sources(document.lineage, document.definition)
    return _resolved_entries(document.lineage, document.definition, sources)


def _validate_document(document: NetDocumentV1) -> None:
    compile_net_definition(document.definition)
    if document.view is not None:
        body = document.definition.definition
        definition_nodes = {place.path for place in body.places} | {transition.path for transition in body.transitions}
        foreign = tuple(node.node for node in document.view.nodes if node.node not in definition_nodes)
        if foreign:
            raise NetDocumentError(f"view contains foreign definition node {foreign[0]!r}")
    try:
        _resolve_lineage(document)
    except EvidenceError as error:
        raise NetDocumentError(str(error)) from None


def parse_net_document(payload: bytes | str) -> NetDocumentV1:
    """Strictly parse and semantically admit one portable Net document."""
    try:
        text = payload.decode("utf-8", errors="strict") if isinstance(payload, bytes) else payload
        value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_no_constant)
        _validate_unicode(value)
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
        model_value = document.model_dump(mode="python")
        if document.lineage is not None:
            for entry in model_value["lineage"]["entries"]:
                if entry["checkpoint"] is None:
                    del entry["checkpoint"]
        document = NetDocumentV1.model_validate(model_value, strict=True)
        _validate_document(document)
        value = document.model_dump(mode="json")
        if document.view is None:
            del value["view"]
        if document.lineage is None:
            del value["lineage"]
        else:
            for entry in value["lineage"]["entries"]:
                if entry["checkpoint"] is None:
                    del entry["checkpoint"]
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


def resolve_lineage(document: NetDocumentV1) -> tuple[NavigationEntry, ...]:
    """Validate retained evidence and resolve every lineage entry's marking."""
    try:
        compile_net_definition(document.definition)
        return _resolve_lineage(document)
    except NetDocumentError:
        raise
    except EvidenceError as error:
        raise NetDocumentError(str(error)) from None
    except (ValidationError, TypeError, ValueError, RecursionError) as error:
        raise NetDocumentError(f"cannot resolve Petrus Net document lineage: {error}") from None


__all__ = [
    "EmbeddedArtifact",
    "ExecutionLineage",
    "HistoryRecordFact",
    "LineageEntry",
    "ManualReplacementFact",
    "MarkingToken",
    "NavigationEntry",
    "NetDocumentError",
    "NetDocumentV1",
    "NodePosition",
    "ObservationEvidenceSource",
    "PlaceMarking",
    "PortableViewV1",
    "SimulationEvidenceSource",
    "definition_identity",
    "parse_net_document",
    "project_net_document",
    "resolve_lineage",
    "serialize_net_document",
]
