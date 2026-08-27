"""Exploration-local strict parser for the ES-061 portable-document spine."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from petrus.impetus.history import (
    InstanceCreated,
    replay_armed,
    replay_instance_identity,
    replay_marking,
    replay_watermark,
)
from petrus.impetus.history.codec import decode_record, encode_record
from petrus.impetus.net_definition import (
    JSON_SAFE_INTEGER_MAX,
    NetDefinitionV3,
    compile_net_definition,
    serialize_net_definition,
)
from petrus.impetus.observation import marking as project_marking
from petrus.impetus.petrinet import NetPath


class DocumentError(ValueError):
    """The portable document is malformed or contradicts its embedded evidence."""


class _WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def _tuple_from_json(value: object) -> object:
    return tuple(value) if isinstance(value, list) else value


class MarkingToken(_WireModel):
    color: str | None
    data: object


class PlaceMarking(_WireModel):
    place: str
    tokens: tuple[MarkingToken, ...]

    _tuple_tokens = field_validator("tokens", mode="before")(_tuple_from_json)


class NodePosition(_WireModel):
    node: str
    x: int
    y: int

    @field_validator("x", "y")
    @classmethod
    def portable_coordinate(cls, value: int) -> int:
        if not -JSON_SAFE_INTEGER_MAX <= value <= JSON_SAFE_INTEGER_MAX:
            raise ValueError("view coordinates must be interoperable JSON integers")
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


class EmbeddedArtifact(_WireModel):
    """One exact UTF-8 source artifact retained without JSON reserialization."""

    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    base64: str

    @classmethod
    def from_bytes(cls, payload: bytes) -> EmbeddedArtifact:
        return cls(sha256=sha256(payload).hexdigest(), base64=base64.b64encode(payload).decode("ascii"))


class ObservedStep(_WireModel):
    id: int = Field(ge=0, le=JSON_SAFE_INTEGER_MAX)
    parent: int | None = Field(ge=0, le=JSON_SAFE_INTEGER_MAX)
    provenance: Literal["observed"]
    capture: EmbeddedArtifact


class ManualStep(_WireModel):
    id: int = Field(ge=0, le=JSON_SAFE_INTEGER_MAX)
    parent: int = Field(ge=0, le=JSON_SAFE_INTEGER_MAX)
    provenance: Literal["manual"]
    operation: Literal["replace-marking"]
    marking: tuple[PlaceMarking, ...]

    _tuple_marking = field_validator("marking", mode="before")(_tuple_from_json)


class SimulatedStep(_WireModel):
    id: int = Field(ge=0, le=JSON_SAFE_INTEGER_MAX)
    parent: int | None = Field(ge=0, le=JSON_SAFE_INTEGER_MAX)
    provenance: Literal["simulated"]
    result: EmbeddedArtifact


LineageStep = Annotated[ObservedStep | ManualStep | SimulatedStep, Field(discriminator="provenance")]


class ExecutionLineage(_WireModel):
    head: int = Field(ge=0, le=JSON_SAFE_INTEGER_MAX)
    steps: tuple[LineageStep, ...]

    _tuple_steps = field_validator("steps", mode="before")(_tuple_from_json)


class NetDocument(_WireModel):
    format: Literal["petrus-net-document"]
    version: Literal[1]
    definition: NetDefinitionV3
    view: PortableView | None = None
    lineage: ExecutionLineage | None = None

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


@dataclass(frozen=True)
class Checkpoint:
    """The source-independent state one lineage step resolves for navigation."""

    id: int
    parent: int | None
    provenance: Literal["observed", "manual", "simulated"]
    marking: tuple[PlaceMarking, ...]


@dataclass(frozen=True)
class ParsedDocument:
    """One admitted wire document plus its derived identity and checkpoint list."""

    wire: NetDocument
    definition_identity: str
    checkpoints: tuple[Checkpoint, ...]


@dataclass(frozen=True)
class _SourceState:
    payload: bytes
    instance: str
    frontier: int
    records: tuple[dict[str, object], ...]
    marking: tuple[PlaceMarking, ...]


def _duplicate_free_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DocumentError(f"duplicate JSON member {key!r}")
        result[key] = value
    return result


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise DocumentError(f"non-finite JSON number {value}")
    return number


def _no_constant(value: str) -> None:
    raise DocumentError(f"non-finite JSON number {value}")


def _validate_unicode(value: object) -> None:
    if isinstance(value, str):
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise DocumentError("JSON strings must contain Unicode scalar values")
    elif isinstance(value, list | tuple):
        for item in value:
            _validate_unicode(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            _validate_unicode(key)
            _validate_unicode(item)


def _load_json(payload: bytes | str, subject: str) -> object:
    try:
        text = payload.decode("utf-8", errors="strict") if isinstance(payload, bytes) else payload
        value = json.loads(
            text,
            object_pairs_hook=_duplicate_free_object,
            parse_float=_finite_float,
            parse_constant=_no_constant,
        )
        _validate_unicode(value)
        return value
    except DocumentError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as error:
        raise DocumentError(f"invalid strict JSON in {subject}: {error}") from None


def _exact_object(value: object, keys: set[str], path: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise DocumentError(f"{path} must be an object")
    if set(value) != keys:
        raise DocumentError(f"{path} must have exactly fields {sorted(keys)}, found {sorted(value)}")
    return value


def _exact_list(value: object, path: str) -> list[object]:
    if not isinstance(value, list):
        raise DocumentError(f"{path} must be an array")
    return value


def _integer(value: object, path: str, *, minimum: int | None = None) -> int:
    if type(value) is not int:
        raise DocumentError(f"{path} must be an integer, not {value!r}")
    if minimum is not None and value < minimum:
        raise DocumentError(f"{path} must be at least {minimum}, found {value}")
    return value


def _string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise DocumentError(f"{path} must be a non-empty string")
    return value


def _canonical_path(value: object, path: str) -> str:
    text = _string(value, path)
    try:
        canonical = str(NetPath(text))
    except ValueError as error:
        raise DocumentError(f"{path} is not a NetPath: {error}") from None
    if canonical != text:
        raise DocumentError(f"{path} must use canonical dotted NetPath spelling")
    return text


def _artifact_bytes(artifact: EmbeddedArtifact, path: str) -> bytes:
    try:
        payload = base64.b64decode(artifact.base64.encode("ascii"), validate=True)
    except (UnicodeEncodeError, ValueError) as error:
        raise DocumentError(f"{path}.base64 must be canonical base64: {error}") from None
    if base64.b64encode(payload).decode("ascii") != artifact.base64:
        raise DocumentError(f"{path}.base64 must use canonical padded base64 spelling")
    digest = sha256(payload).hexdigest()
    if digest != artifact.sha256:
        raise DocumentError(f"{path}.sha256 does not match the retained source bytes")
    return payload


def _marking(
    value: object,
    definition: NetDefinitionV3,
    path: str,
) -> tuple[PlaceMarking, ...]:
    entries = _exact_list(value, path)
    parsed: list[PlaceMarking] = []
    place_definitions = {place.path: place for place in definition.definition.places}
    for index, entry in enumerate(entries):
        try:
            place = PlaceMarking.model_validate(entry, strict=True)
        except ValidationError as error:
            raise DocumentError(f"{path}[{index}] is malformed: {error}") from None
        _canonical_path(place.place, f"{path}[{index}].place")
        if place.place not in place_definitions:
            raise DocumentError(f"{path}[{index}].place names foreign place {place.place!r}")
        if not place.tokens:
            raise DocumentError(f"{path}[{index}].tokens must be nonempty in sparse marking form")
        expected_color = place_definitions[place.place].color
        for token_index, token in enumerate(place.tokens):
            if token.color is not None and not token.color:
                raise DocumentError(f"{path}[{index}].tokens[{token_index}].color must be nonempty or null")
            if expected_color is not None and token.color != expected_color:
                raise DocumentError(
                    f"{path}[{index}].tokens[{token_index}].color {token.color!r} does not match "
                    f"place {place.place!r} color {expected_color!r}"
                )
        parsed.append(place)
    names = tuple(entry.place for entry in parsed)
    if names != tuple(sorted(names, key=lambda item: tuple(ord(character) for character in item))):
        raise DocumentError(f"{path} places must be sorted by Unicode scalar value")
    if len(names) != len(set(names)):
        raise DocumentError(f"{path} places must be unique")
    return tuple(parsed)


def _tokens(value: object, path: str) -> None:
    tokens = _exact_list(value, path)
    for index, token in enumerate(tokens):
        try:
            MarkingToken.model_validate(token, strict=True)
        except ValidationError as error:
            raise DocumentError(f"{path}[{index}] is malformed: {error}") from None


def _selections(value: object, path: str) -> None:
    selections = _exact_list(value, path)
    for index, selection in enumerate(selections):
        item = _exact_object(selection, {"place", "tokens"}, f"{path}[{index}]")
        _canonical_path(item["place"], f"{path}[{index}].place")
        _tokens(item["tokens"], f"{path}[{index}].tokens")


def _validate_in_flight(value: object, path: str) -> None:
    entries = _exact_list(value, path)
    for index, entry in enumerate(entries):
        item_path = f"{path}[{index}]"
        item = _exact_object(
            entry,
            {"occurrence", "transition", "phase", "binding", "invocation", "result"},
            item_path,
        )
        _integer(item["occurrence"], f"{item_path}.occurrence", minimum=1)
        _canonical_path(item["transition"], f"{item_path}.transition")
        if item["phase"] not in {"pure_pending", "activity_pending", "projection_pending"}:
            raise DocumentError(f"{item_path}.phase is unsupported")
        binding = _exact_object(item["binding"], {"consumed", "read", "delivered"}, f"{item_path}.binding")
        _selections(binding["consumed"], f"{item_path}.binding.consumed")
        _selections(binding["read"], f"{item_path}.binding.read")
        _tokens(binding["delivered"], f"{item_path}.binding.delivered")
        invocation = item["invocation"]
        if invocation is not None:
            invocation = _exact_object(
                invocation,
                {"activity", "input", "policy", "correlation", "idempotency"},
                f"{item_path}.invocation",
            )
            _string(invocation["activity"], f"{item_path}.invocation.activity")
            policy = _exact_object(
                invocation["policy"],
                {"attempts", "heartbeat_timeout"},
                f"{item_path}.invocation.policy",
            )
            _integer(policy["attempts"], f"{item_path}.invocation.policy.attempts", minimum=1)
            _integer(
                policy["heartbeat_timeout"],
                f"{item_path}.invocation.policy.heartbeat_timeout",
                minimum=1,
            )
            if invocation["correlation"] is not None:
                _string(invocation["correlation"], f"{item_path}.invocation.correlation")
            if invocation["idempotency"] is not None:
                _string(invocation["idempotency"], f"{item_path}.invocation.idempotency")
        if item["phase"] == "pure_pending" and (invocation is not None or item["result"] is not None):
            raise DocumentError(f"{item_path} pure_pending cannot carry an invocation or result")
        if item["phase"] == "activity_pending" and (invocation is None or item["result"] is not None):
            raise DocumentError(f"{item_path} activity_pending requires an invocation and no result")
        if item["phase"] == "projection_pending" and invocation is None:
            raise DocumentError(f"{item_path} projection_pending requires an invocation")


def _decode_history_record(value: object, path: str):
    record = _exact_object(value, set(value) if isinstance(value, dict) else set(), path)
    _integer(record.get("schema"), f"{path}.schema")
    _integer(record.get("instant"), f"{path}.instant")
    if "occurrence" in record and record["occurrence"] is not None:
        _integer(record["occurrence"], f"{path}.occurrence", minimum=1)
    try:
        decoded = decode_record(record)
    except (TypeError, ValueError) as error:
        raise DocumentError(f"{path} is not a canonical History record: {error}") from None
    if encode_record(decoded) != record:
        raise DocumentError(f"{path} is not the record's exact canonical schema spelling")
    return decoded


def _history(value: object, path: str) -> tuple[str, int, tuple[dict[str, object], ...], tuple[object, ...]]:
    history = _exact_object(value, {"protocol", "instance", "after", "next", "frontier", "records"}, path)
    if _integer(history["protocol"], f"{path}.protocol") != 1:
        raise DocumentError(f"{path}.protocol must be 1")
    instance = _string(history["instance"], f"{path}.instance")
    if _integer(history["after"], f"{path}.after", minimum=0) != 0:
        raise DocumentError(f"{path}.after must be zero for complete evidence")
    frontier = _integer(history["frontier"], f"{path}.frontier", minimum=1)
    if _integer(history["next"], f"{path}.next", minimum=0) != frontier:
        raise DocumentError(f"{path}.next must equal frontier")
    entries = _exact_list(history["records"], f"{path}.records")
    if len(entries) != frontier:
        raise DocumentError(f"{path}.records must contain exactly frontier entries")
    raw_records: list[dict[str, object]] = []
    decoded_records = []
    for position, entry in enumerate(entries):
        item_path = f"{path}.records[{position}]"
        item = _exact_object(entry, {"position", "record"}, item_path)
        if _integer(item["position"], f"{item_path}.position", minimum=0) != position:
            raise DocumentError(f"{item_path}.position must equal its array index")
        record = _exact_object(
            item["record"], set(item["record"]) if isinstance(item["record"], dict) else set(), f"{item_path}.record"
        )
        decoded_records.append(_decode_history_record(record, f"{item_path}.record"))
        raw_records.append(item)
    identity = replay_instance_identity(decoded_records)
    if not isinstance(identity, InstanceCreated) or identity.instance != instance:
        raise DocumentError(f"{path} must start with the matching InstanceCreated record")
    return instance, frontier, tuple(raw_records), tuple(decoded_records)


def _snapshot(
    value: object,
    definition: NetDefinitionV3,
    path: str,
) -> tuple[str, int, tuple[PlaceMarking, ...], dict[str, object]]:
    snapshot = _exact_object(value, {"protocol", "instance", "definition", "frontier", "current"}, path)
    if _integer(snapshot["protocol"], f"{path}.protocol") != 1:
        raise DocumentError(f"{path}.protocol must be 1")
    instance = _string(snapshot["instance"], f"{path}.instance")
    frontier = _integer(snapshot["frontier"], f"{path}.frontier", minimum=1)
    expected_definition = definition.definition.model_dump(mode="json")
    if snapshot["definition"] != expected_definition:
        raise DocumentError(f"{path}.definition does not match the document's canonical definition")
    current = _exact_object(
        snapshot["current"],
        {"marking", "status", "watermark", "in_flight", "armed", "next_maturation"},
        f"{path}.current",
    )
    marking = _marking(current["marking"], definition, f"{path}.current.marking")
    if current["status"] not in {"running", "terminated", "completed", "stuck", "awaiting"}:
        raise DocumentError(f"{path}.current.status is unsupported")
    _integer(current["watermark"], f"{path}.current.watermark")
    _validate_in_flight(current["in_flight"], f"{path}.current.in_flight")
    armed = _exact_list(current["armed"], f"{path}.current.armed")
    prior: tuple[str, str] | None = None
    for index, entry in enumerate(armed):
        item_path = f"{path}.current.armed[{index}]"
        item = _exact_object(entry, {"source", "key"}, item_path)
        pair = (_canonical_path(item["source"], f"{item_path}.source"), _string(item["key"], f"{item_path}.key"))
        if prior is not None and pair <= prior:
            raise DocumentError(f"{path}.current.armed must be unique and source/key sorted")
        prior = pair
    if current["next_maturation"] is not None:
        _integer(current["next_maturation"], f"{path}.current.next_maturation")
    return instance, frontier, marking, current


def _source_state(
    payload: bytes,
    snapshot: object,
    history: object,
    definition: NetDefinitionV3,
    path: str,
) -> _SourceState:
    snapshot_instance, snapshot_frontier, marking, current = _snapshot(snapshot, definition, f"{path}.snapshot")
    history_instance, history_frontier, records, decoded = _history(history, f"{path}.history")
    if snapshot_instance != history_instance:
        raise DocumentError(f"{path} snapshot and History instance identities differ")
    if snapshot_frontier != history_frontier:
        raise DocumentError(f"{path} snapshot and History frontiers differ")
    try:
        replayed_marking = _marking(
            project_marking(replay_marking(decoded)),
            definition,
            f"{path}.history replay marking",
        )
        replayed_watermark = replay_watermark(decoded)
        replayed_armed = [
            {"source": str(source), "key": key}
            for source, keys in sorted(replay_armed(decoded).items(), key=lambda item: str(item[0]))
            for key in sorted(keys)
        ]
    except ValueError as error:
        raise DocumentError(f"{path}.history cannot be replayed: {error}") from None
    if replayed_marking != marking:
        raise DocumentError(f"{path}.snapshot marking disagrees with replayed History")
    if replayed_watermark != current["watermark"]:
        raise DocumentError(f"{path}.snapshot watermark disagrees with replayed History")
    if replayed_armed != current["armed"]:
        raise DocumentError(f"{path}.snapshot armed registrations disagree with replayed History")
    return _SourceState(payload, snapshot_instance, snapshot_frontier, records, marking)


def _capture(artifact: EmbeddedArtifact, definition: NetDefinitionV3, path: str) -> _SourceState:
    payload = _artifact_bytes(artifact, path)
    value = _exact_object(
        _load_json(payload, path),
        {"format", "version", "snapshot", "history"},
        path,
    )
    if value["format"] != "petrus-observation-capture" or _integer(value["version"], f"{path}.version") != 1:
        raise DocumentError(f"{path} must embed observation capture schema 1")
    return _source_state(payload, value["snapshot"], value["history"], definition, path)


def _simulation(
    artifact: EmbeddedArtifact, definition: NetDefinitionV3, path: str
) -> tuple[_SourceState, tuple[PlaceMarking, ...]]:
    payload = _artifact_bytes(artifact, path)
    value = _exact_object(
        _load_json(payload, path),
        {"format", "version", "profile", "scenario", "outcome", "snapshot", "history"},
        path,
    )
    if value["format"] != "petrus-simulation-result" or _integer(value["version"], f"{path}.version") != 1:
        raise DocumentError(f"{path} must embed simulation result schema 1")
    if value["profile"] != "implementation-free-v1":
        raise DocumentError(f"{path}.profile must be implementation-free-v1")
    scenario = _exact_object(value["scenario"], {"start_instant", "initial_marking", "max_actions"}, f"{path}.scenario")
    if _integer(scenario["start_instant"], f"{path}.scenario.start_instant") != 0:
        raise DocumentError(f"{path}.scenario.start_instant must be zero")
    max_actions = _integer(scenario["max_actions"], f"{path}.scenario.max_actions", minimum=1)
    if max_actions > 256:
        raise DocumentError(f"{path}.scenario.max_actions exceeds implementation-free-v1")
    initial = _marking(scenario["initial_marking"], definition, f"{path}.scenario.initial_marking")
    outcome = _exact_object(value["outcome"], {"actions_applied", "reason"}, f"{path}.outcome")
    actions = _integer(outcome["actions_applied"], f"{path}.outcome.actions_applied", minimum=0)
    if actions > max_actions:
        raise DocumentError(f"{path}.outcome.actions_applied exceeds max_actions")
    if outcome["reason"] not in {"rest", "action_limit"}:
        raise DocumentError(f"{path}.outcome.reason is unsupported")
    state = _source_state(payload, value["snapshot"], value["history"], definition, path)
    action_records = sum(
        entry["record"].get("record") in {"TimerMatured", "FiringCompleted"} for entry in state.records
    )
    if action_records != actions:
        raise DocumentError(f"{path}.outcome.actions_applied disagrees with its complete History")
    return state, initial


def _validate_view(view: PortableView | None, definition: NetDefinitionV3) -> None:
    if view is None:
        return
    allowed = {
        *(place.path for place in definition.definition.places),
        *(transition.path for transition in definition.definition.transitions),
    }
    nodes = tuple(position.node for position in view.nodes)
    if nodes != tuple(sorted(nodes)) or len(nodes) != len(set(nodes)):
        raise DocumentError("view.nodes must have unique canonical paths in lexical order")
    foreign = next((node for node in nodes if node not in allowed), None)
    if foreign is not None:
        raise DocumentError(f"view.nodes names foreign node {foreign!r}")


def _lineage(
    lineage: ExecutionLineage | None,
    definition: NetDefinitionV3,
) -> tuple[Checkpoint, ...]:
    if lineage is None:
        return ()
    if not lineage.steps:
        raise DocumentError("lineage.steps must be nonempty when lineage is present")
    if lineage.head >= len(lineage.steps):
        raise DocumentError("lineage.head must identify an existing step")
    checkpoints: list[Checkpoint] = []
    observed_sources: dict[int, _SourceState] = {}
    for index, step in enumerate(lineage.steps):
        if step.id != index:
            raise DocumentError(f"lineage.steps[{index}].id must equal its array index")
        if index == 0:
            if step.parent is not None:
                raise DocumentError("lineage root parent must be null")
        elif step.parent is None or step.parent >= index:
            raise DocumentError(f"lineage.steps[{index}].parent must identify a smaller existing step")

        if isinstance(step, ObservedStep):
            state = _capture(step.capture, definition, f"lineage.steps[{index}].capture")
            if step.parent is not None:
                parent = lineage.steps[step.parent]
                if not isinstance(parent, ObservedStep):
                    raise DocumentError("an observed step can extend only observed evidence, never a hypothesis")
                prior = observed_sources[step.parent]
                if state.instance != prior.instance:
                    raise DocumentError("an observed child must retain its parent's Instance identity")
                if state.frontier <= prior.frontier or state.records[: prior.frontier] != prior.records:
                    raise DocumentError("an observed child must be a strict exact extension of its parent's History")
            observed_sources[index] = state
            marking = state.marking
        elif isinstance(step, ManualStep):
            marking = _marking(
                [entry.model_dump(mode="json") for entry in step.marking],
                definition,
                f"lineage.steps[{index}].marking",
            )
        else:
            state, initial = _simulation(step.result, definition, f"lineage.steps[{index}].result")
            if step.parent is not None and initial != checkpoints[step.parent].marking:
                raise DocumentError("a simulated child's scenario initial marking must equal its parent checkpoint")
            marking = state.marking
        checkpoints.append(Checkpoint(step.id, step.parent, step.provenance, marking))
    return tuple(checkpoints)


def parse_document(payload: bytes | str) -> ParsedDocument:
    """Parse one strict ES-061 candidate document and verify every embedded authority."""
    try:
        value = _load_json(payload, "Petrus net document")
        wire = NetDocument.model_validate(value, strict=True)
        compile_net_definition(wire.definition)
        definition_identity = sha256(serialize_net_definition(wire.definition)).hexdigest()
        _validate_view(wire.view, wire.definition)
        checkpoints = _lineage(wire.lineage, wire.definition)
        return ParsedDocument(wire, definition_identity, checkpoints)
    except DocumentError:
        raise
    except (ValidationError, TypeError, ValueError, RecursionError) as error:
        raise DocumentError(f"invalid Petrus net document v1: {error}") from None


def serialize_document(document: NetDocument) -> bytes:
    """Serialize one parsed candidate document without rewriting embedded source bytes."""
    value = document.model_dump(mode="json")
    if document.view is None:
        value.pop("view")
    if document.lineage is None:
        value.pop("lineage")
    payload = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    parse_document(payload)
    return payload


def strict_json(payload: bytes | str, subject: str) -> object:
    """Parse strict JSON for another exploration-local candidate shape."""
    return _load_json(payload, subject)


def validate_capture(
    artifact: EmbeddedArtifact,
    definition: NetDefinitionV3,
    path: str,
) -> _SourceState:
    """Validate one exact capture used as exploration evidence."""
    return _capture(artifact, definition, path)


def validate_simulation(
    artifact: EmbeddedArtifact,
    definition: NetDefinitionV3,
    path: str,
) -> tuple[_SourceState, tuple[PlaceMarking, ...]]:
    """Validate one exact simulation result used as exploration evidence."""
    return _simulation(artifact, definition, path)


def validate_marking(
    value: object,
    definition: NetDefinitionV3,
    path: str,
) -> tuple[PlaceMarking, ...]:
    """Validate the shared sparse marking projection."""
    return _marking(value, definition, path)


__all__ = [
    "Checkpoint",
    "DocumentError",
    "EmbeddedArtifact",
    "ExecutionLineage",
    "ManualStep",
    "NetDocument",
    "NodePosition",
    "ObservedStep",
    "ParsedDocument",
    "PlaceMarking",
    "PortableView",
    "SimulatedStep",
    "parse_document",
    "serialize_document",
    "strict_json",
    "validate_capture",
    "validate_marking",
    "validate_simulation",
]
