"""Exploration-local uniform-entry alternatives for the ES-061 document spine."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from document_spine import (
    DocumentError,
    EmbeddedArtifact,
    PlaceMarking,
    strict_json,
    validate_capture,
    validate_marking,
    validate_simulation,
)
from petrus.impetus.history import replay_marking, replay_watermark
from petrus.impetus.history.codec import decode_record, encode_record
from petrus.impetus.net_definition import (
    JSON_SAFE_INTEGER_MAX,
    NetDefinitionV3,
    compile_net_definition,
    serialize_net_definition,
)
from petrus.impetus.observation import marking as project_marking
from petrus.impetus.petrinet import NetPath


Provenance = Literal["observed", "manual", "simulated"]


class _WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def _tuple_from_json(value: object) -> object:
    return tuple(value) if isinstance(value, list) else value


class NodePosition(_WireModel):
    """AX2 geometry evidence; the Candidate intentionally does not settle its number type."""

    node: str
    x: int | float
    y: int | float

    @field_validator("x", "y")
    @classmethod
    def finite_coordinate(cls, value: int | float) -> int | float:
        if type(value) not in {int, float} or (type(value) is float and not math.isfinite(value)):
            raise ValueError("view coordinates must be finite JSON numbers")
        return value


class PortableView(_WireModel):
    version: Literal[1]
    nodes: tuple[NodePosition, ...]

    _tuple_nodes = field_validator("nodes", mode="before")(_tuple_from_json)

    @model_validator(mode="before")
    @classmethod
    def exact_version_discriminator(cls, value: object) -> object:
        if isinstance(value, dict) and "version" in value and type(value["version"]) is not int:
            raise ValueError("view.version must be an integer discriminator")
        return value


class ObservationSource(_WireModel):
    id: int = Field(ge=0, le=JSON_SAFE_INTEGER_MAX)
    kind: Literal["observation-capture"]
    after: int = Field(ge=0, le=JSON_SAFE_INTEGER_MAX)
    artifact: EmbeddedArtifact


class SimulationSource(_WireModel):
    id: int = Field(ge=0, le=JSON_SAFE_INTEGER_MAX)
    kind: Literal["simulation-result"]
    after: Literal[0]
    artifact: EmbeddedArtifact


EvidenceSource = Annotated[ObservationSource | SimulationSource, Field(discriminator="kind")]


class HistoryRecordFact(_WireModel):
    kind: Literal["history-record"]
    source: int = Field(ge=0, le=JSON_SAFE_INTEGER_MAX)
    position: int = Field(ge=0, le=JSON_SAFE_INTEGER_MAX)
    record: dict[str, object]


class ManualReplacementFact(_WireModel):
    kind: Literal["manual-replace-marking"]
    marking: tuple[PlaceMarking, ...]

    _tuple_marking = field_validator("marking", mode="before")(_tuple_from_json)


EntryFact = Annotated[HistoryRecordFact | ManualReplacementFact, Field(discriminator="kind")]


class LineageEntry(_WireModel):
    id: int = Field(ge=0, le=JSON_SAFE_INTEGER_MAX)
    parent: int | None = Field(ge=0, le=JSON_SAFE_INTEGER_MAX)
    provenance: Provenance
    fact: EntryFact
    checkpoint: tuple[PlaceMarking, ...] | None = None

    _tuple_checkpoint = field_validator("checkpoint", mode="before")(_tuple_from_json)

    @model_validator(mode="before")
    @classmethod
    def checkpoint_is_absent_or_an_array(cls, value: object) -> object:
        if isinstance(value, dict) and "checkpoint" in value and value["checkpoint"] is None:
            raise ValueError("checkpoint must be absent or an array, not null")
        return value


class AnchoredLineage(_WireModel):
    sources: tuple[EvidenceSource, ...]
    head: int = Field(ge=0, le=JSON_SAFE_INTEGER_MAX)
    entries: tuple[LineageEntry, ...]

    _tuple_sources = field_validator("sources", mode="before")(_tuple_from_json)
    _tuple_entries = field_validator("entries", mode="before")(_tuple_from_json)


class UnanchoredLineage(_WireModel):
    head: int = Field(ge=0, le=JSON_SAFE_INTEGER_MAX)
    entries: tuple[LineageEntry, ...]

    _tuple_entries = field_validator("entries", mode="before")(_tuple_from_json)


class _DocumentEnvelope(_WireModel):
    format: Literal["petrus-net-document"]
    version: Literal[1]
    definition: NetDefinitionV3
    view: PortableView | None = None

    @model_validator(mode="before")
    @classmethod
    def components_are_absent_or_strict_objects(cls, value: object) -> object:
        if isinstance(value, dict):
            if "version" in value and type(value["version"]) is not int:
                raise ValueError("version must be an integer discriminator")
            definition = value.get("definition")
            if isinstance(definition, dict) and "version" in definition and type(definition["version"]) is not int:
                raise ValueError("definition.version must be an integer discriminator")
            for component in ("view", "lineage"):
                if component in value and value[component] is None:
                    raise ValueError(f"{component} must be absent or an object, not null")
        return value


class AnchoredDocument(_DocumentEnvelope):
    lineage: AnchoredLineage | None = None


class UnanchoredDocument(_DocumentEnvelope):
    lineage: UnanchoredLineage | None = None


@dataclass(frozen=True)
class NavigationEntry:
    """The source-independent surface consumed by one lineage-navigation loop."""

    id: int
    parent: int | None
    provenance: Provenance
    event: str
    marking: tuple[PlaceMarking, ...]


@dataclass(frozen=True)
class ParsedAnchoredDocument:
    wire: AnchoredDocument
    definition_identity: str
    entries: tuple[NavigationEntry, ...]


@dataclass(frozen=True)
class ParsedUnanchoredDocument:
    wire: UnanchoredDocument
    definition_identity: str
    entries: tuple[NavigationEntry, ...]


@dataclass(frozen=True)
class _AdmittedSource:
    kind: Literal["observation-capture", "simulation-result"]
    after: int
    instance: str
    records: tuple[dict[str, object], ...]
    marking: tuple[PlaceMarking, ...]
    initial: tuple[PlaceMarking, ...] | None


def _validate_view(view: PortableView | None, definition: NetDefinitionV3) -> None:
    if view is None:
        return
    node_paths = {place.path for place in definition.definition.places} | {
        transition.path for transition in definition.definition.transitions
    }
    prior: str | None = None
    for index, node in enumerate(view.nodes):
        try:
            canonical = str(NetPath(node.node))
        except ValueError as error:
            raise DocumentError(f"view.nodes[{index}].node is not a NetPath: {error}") from None
        if canonical != node.node:
            raise DocumentError(f"view.nodes[{index}].node must use canonical dotted NetPath spelling")
        if node.node not in node_paths:
            raise DocumentError(f"view.nodes[{index}].node names foreign node {node.node!r}")
        if prior is not None and node.node <= prior:
            raise DocumentError("view.nodes must be unique and sorted by canonical path")
        prior = node.node


def _definition_identity(definition: NetDefinitionV3) -> str:
    compile_net_definition(definition)
    return sha256(serialize_net_definition(definition)).hexdigest()


def _decoded_record(record: dict[str, object], path: str) -> object:
    try:
        decoded = decode_record(record)
    except (TypeError, ValueError) as error:
        raise DocumentError(f"{path} is not a canonical History record: {error}") from None
    if encode_record(decoded) != record:
        raise DocumentError(f"{path} is not the record's exact canonical schema spelling")
    return decoded


def _replayed_marking(
    records: tuple[dict[str, object], ...],
    definition: NetDefinitionV3,
    path: str,
) -> tuple[PlaceMarking, ...]:
    decoded = tuple(_decoded_record(record, f"{path}[{index}]") for index, record in enumerate(records))
    try:
        marking = project_marking(replay_marking(decoded))
        replay_watermark(decoded)
    except ValueError as error:
        raise DocumentError(f"{path} cannot be replayed: {error}") from None
    return validate_marking(marking, definition, f"{path} replay marking")


def _validated_manual_marking(
    fact: ManualReplacementFact,
    definition: NetDefinitionV3,
    path: str,
) -> tuple[PlaceMarking, ...]:
    value = [entry.model_dump(mode="json") for entry in fact.marking]
    return validate_marking(value, definition, path)


def _validated_checkpoint(
    checkpoint: tuple[PlaceMarking, ...] | None,
    definition: NetDefinitionV3,
    path: str,
) -> tuple[PlaceMarking, ...] | None:
    if checkpoint is None:
        return None
    value = [entry.model_dump(mode="json") for entry in checkpoint]
    return validate_marking(value, definition, path)


def _lineage_structure(entries: tuple[LineageEntry, ...], head: int) -> None:
    if not entries:
        raise DocumentError("lineage.entries must be nonempty")
    if head >= len(entries):
        raise DocumentError("lineage.head must name an existing entry")
    for index, entry in enumerate(entries):
        if entry.id != index:
            raise DocumentError(f"lineage.entries[{index}].id must equal its array index")
        if index == 0:
            if entry.parent is not None:
                raise DocumentError("lineage.entries[0] must be the sole root with parent null")
        elif entry.parent is None or entry.parent >= index:
            raise DocumentError(f"lineage.entries[{index}].parent must be a smaller entry id")


def _admit_sources(lineage: AnchoredLineage, definition: NetDefinitionV3) -> tuple[_AdmittedSource, ...]:
    admitted: list[_AdmittedSource] = []
    for index, source in enumerate(lineage.sources):
        if source.id != index:
            raise DocumentError(f"lineage.sources[{index}].id must equal its array index")
        path = f"lineage.sources[{index}].artifact"
        if isinstance(source, ObservationSource):
            state = validate_capture(source.artifact, definition, path)
            if source.after >= state.frontier:
                raise DocumentError(f"lineage.sources[{index}].after must be smaller than its capture frontier")
            admitted.append(
                _AdmittedSource(
                    "observation-capture",
                    source.after,
                    state.instance,
                    state.records,
                    state.marking,
                    None,
                )
            )
        else:
            state, initial = validate_simulation(source.artifact, definition, path)
            admitted.append(
                _AdmittedSource(
                    "simulation-result",
                    0,
                    state.instance,
                    state.records,
                    state.marking,
                    initial,
                )
            )
    return tuple(admitted)


def _anchored_entries(
    lineage: AnchoredLineage,
    definition: NetDefinitionV3,
    sources: tuple[_AdmittedSource, ...],
) -> tuple[NavigationEntry, ...]:
    _lineage_structure(lineage.entries, lineage.head)
    if not sources:
        raise DocumentError("an anchored lineage must retain at least one evidence source")
    sequences: list[tuple[dict[str, object], ...]] = []
    markings: list[tuple[PlaceMarking, ...]] = []
    navigation: list[NavigationEntry] = []
    used: list[list[int]] = [[] for _ in sources]

    for index, entry in enumerate(lineage.entries):
        path = f"lineage.entries[{index}]"
        if isinstance(entry.fact, ManualReplacementFact):
            if entry.provenance != "manual":
                raise DocumentError(f"{path} manual fact requires manual provenance")
            if entry.parent is None:
                raise DocumentError(f"{path} manual replacement requires a parent")
            sequence: tuple[dict[str, object], ...] = ()
            marking = _validated_manual_marking(entry.fact, definition, f"{path}.fact.marking")
            event = "ManualMarkingReplaced"
        else:
            fact = entry.fact
            if fact.source >= len(sources):
                raise DocumentError(f"{path}.fact.source must name an existing evidence source")
            source = sources[fact.source]
            expected_provenance = "observed" if source.kind == "observation-capture" else "simulated"
            if entry.provenance != expected_provenance:
                raise DocumentError(f"{path} provenance contradicts its evidence source kind")
            if fact.position < source.after or fact.position >= len(source.records):
                raise DocumentError(f"{path}.fact.position is outside its source's projected range")
            source_record = source.records[fact.position]["record"]
            if fact.record != source_record:
                raise DocumentError(f"{path}.fact.record differs from the exact retained source position")
            used[fact.source].append(fact.position)

            if fact.position == 0:
                sequence = (fact.record,)
                if entry.provenance == "observed" and entry.parent is not None:
                    raise DocumentError(f"{path} observed source root cannot descend from another entry")
                if (
                    entry.provenance == "simulated"
                    and entry.parent is not None
                    and source.initial != markings[entry.parent]
                ):
                    raise DocumentError(f"{path} simulated source initial marking must equal its parent state")
            else:
                if entry.parent is None or not isinstance(lineage.entries[entry.parent].fact, HistoryRecordFact):
                    raise DocumentError(f"{path} non-root History record requires a History-record parent")
                parent = lineage.entries[entry.parent]
                parent_fact = parent.fact
                assert isinstance(parent_fact, HistoryRecordFact)
                if parent.provenance != entry.provenance or parent_fact.position + 1 != fact.position:
                    raise DocumentError(f"{path} must continue a same-provenance canonical record sequence")
                sequence = sequences[entry.parent] + (fact.record,)
                if entry.provenance == "simulated" and parent_fact.source != fact.source:
                    raise DocumentError(f"{path} simulated History cannot switch evidence sources")
                if entry.provenance == "observed":
                    parent_source = sources[parent_fact.source]
                    if parent_source.kind != "observation-capture" or parent_source.instance != source.instance:
                        raise DocumentError(f"{path} observed extension must preserve Instance identity")
                    expected_prefix = tuple(record["record"] for record in source.records[: fact.position])
                    if sequences[entry.parent] != expected_prefix:
                        raise DocumentError(f"{path} observed source does not exactly extend its parent History")

            marking = _replayed_marking(sequence, definition, f"{path}.fact canonical sequence")
            event_value = fact.record.get("record")
            if not isinstance(event_value, str):
                raise DocumentError(f"{path}.fact.record must expose its canonical record discriminator")
            event = event_value

        checkpoint = _validated_checkpoint(entry.checkpoint, definition, f"{path}.checkpoint")
        if checkpoint is not None and checkpoint != marking:
            raise DocumentError(f"{path}.checkpoint disagrees with replay-derived state")
        sequences.append(sequence)
        markings.append(marking)
        navigation.append(NavigationEntry(entry.id, entry.parent, entry.provenance, event, marking))

    for index, source in enumerate(sources):
        expected = list(range(source.after, len(source.records)))
        if used[index] != expected:
            raise DocumentError(
                f"lineage source {index} must project each source position from after through frontier exactly once"
            )
        final_entry = next(
            entry
            for entry in reversed(lineage.entries)
            if isinstance(entry.fact, HistoryRecordFact) and entry.fact.source == index
        )
        if markings[final_entry.id] != source.marking:
            raise DocumentError(f"lineage source {index} final projected marking disagrees with its source snapshot")
    return tuple(navigation)


def _unanchored_entries(
    lineage: UnanchoredLineage,
    definition: NetDefinitionV3,
) -> tuple[NavigationEntry, ...]:
    """Admit list semantics without claiming evidence custody or source authority."""
    _lineage_structure(lineage.entries, lineage.head)
    sequences: list[tuple[dict[str, object], ...]] = []
    markings: list[tuple[PlaceMarking, ...]] = []
    navigation: list[NavigationEntry] = []
    for index, entry in enumerate(lineage.entries):
        path = f"lineage.entries[{index}]"
        if isinstance(entry.fact, ManualReplacementFact):
            if entry.provenance != "manual" or entry.parent is None:
                raise DocumentError(f"{path} manual fact requires manual provenance and a parent")
            sequence: tuple[dict[str, object], ...] = ()
            marking = _validated_manual_marking(entry.fact, definition, f"{path}.fact.marking")
            event = "ManualMarkingReplaced"
        else:
            fact = entry.fact
            if entry.provenance == "manual":
                raise DocumentError(f"{path} History record cannot claim manual provenance")
            _decoded_record(fact.record, f"{path}.fact.record")
            if fact.position == 0:
                sequence = (fact.record,)
                if entry.provenance == "observed" and entry.parent is not None:
                    raise DocumentError(f"{path} observed source root cannot descend from another entry")
            else:
                if entry.parent is None or not isinstance(lineage.entries[entry.parent].fact, HistoryRecordFact):
                    raise DocumentError(f"{path} non-root History record requires a History-record parent")
                parent = lineage.entries[entry.parent]
                parent_fact = parent.fact
                assert isinstance(parent_fact, HistoryRecordFact)
                if parent.provenance != entry.provenance or parent_fact.position + 1 != fact.position:
                    raise DocumentError(f"{path} must continue a same-provenance canonical record sequence")
                sequence = sequences[entry.parent] + (fact.record,)
            marking = _replayed_marking(sequence, definition, f"{path}.fact canonical sequence")
            event_value = fact.record.get("record")
            if not isinstance(event_value, str):
                raise DocumentError(f"{path}.fact.record must expose its canonical record discriminator")
            event = event_value
        checkpoint = _validated_checkpoint(entry.checkpoint, definition, f"{path}.checkpoint")
        if checkpoint is not None and checkpoint != marking:
            raise DocumentError(f"{path}.checkpoint disagrees with replay-derived state")
        sequences.append(sequence)
        markings.append(marking)
        navigation.append(NavigationEntry(entry.id, entry.parent, entry.provenance, event, marking))
    return tuple(navigation)


def parse_anchored_document(payload: bytes | str) -> ParsedAnchoredDocument:
    """Parse the leading uniform-entry shape and prove exact source custody."""
    try:
        value = strict_json(payload, "anchored Petrus net document")
        wire = AnchoredDocument.model_validate(value, strict=True)
        identity = _definition_identity(wire.definition)
        _validate_view(wire.view, wire.definition)
        if wire.lineage is None:
            entries: tuple[NavigationEntry, ...] = ()
        else:
            sources = _admit_sources(wire.lineage, wire.definition)
            entries = _anchored_entries(wire.lineage, wire.definition, sources)
        return ParsedAnchoredDocument(wire, identity, entries)
    except DocumentError:
        raise
    except (ValidationError, TypeError, ValueError, RecursionError) as error:
        raise DocumentError(f"invalid anchored uniform-entry document: {error}") from None


def parse_unanchored_document(payload: bytes | str) -> ParsedUnanchoredDocument:
    """Parse the entries-only comparison without making an evidence-custody claim."""
    try:
        value = strict_json(payload, "unanchored Petrus net document")
        wire = UnanchoredDocument.model_validate(value, strict=True)
        identity = _definition_identity(wire.definition)
        _validate_view(wire.view, wire.definition)
        entries = () if wire.lineage is None else _unanchored_entries(wire.lineage, wire.definition)
        return ParsedUnanchoredDocument(wire, identity, entries)
    except DocumentError:
        raise
    except (ValidationError, TypeError, ValueError, RecursionError) as error:
        raise DocumentError(f"invalid unanchored uniform-entry document: {error}") from None


def serialize_anchored_document(document: AnchoredDocument) -> bytes:
    value = document.model_dump(mode="json")
    if document.view is None:
        value.pop("view")
    if document.lineage is None:
        value.pop("lineage")
    else:
        lineage = value["lineage"]
        for entry in lineage["entries"]:
            if entry["checkpoint"] is None:
                entry.pop("checkpoint")
    payload = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    parse_anchored_document(payload)
    return payload


__all__ = [
    "AnchoredDocument",
    "AnchoredLineage",
    "HistoryRecordFact",
    "LineageEntry",
    "ManualReplacementFact",
    "NavigationEntry",
    "NodePosition",
    "ObservationSource",
    "ParsedAnchoredDocument",
    "ParsedUnanchoredDocument",
    "PortableView",
    "SimulationSource",
    "UnanchoredDocument",
    "UnanchoredLineage",
    "parse_anchored_document",
    "parse_unanchored_document",
    "serialize_anchored_document",
]
