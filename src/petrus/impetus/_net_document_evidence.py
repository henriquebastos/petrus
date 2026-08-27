"""Private strict admission for sources retained by portable Net documents."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Literal, cast

from petrus.impetus.history import (
    InstanceCreated,
    replay_armed,
    replay_instance_identity,
    replay_marking,
    replay_watermark,
)
from petrus.impetus.history.codec import decode_record, encode_record
from petrus.impetus.net_definition import NetDefinitionV3
from petrus.impetus.observation import marking as project_marking
from petrus.impetus.petrinet import NetPath


class EvidenceError(ValueError):
    """Retained source evidence is malformed or internally contradictory."""


@dataclass(frozen=True)
class AdmittedEvidence:
    """Source facts needed to validate one uniform lineage."""

    kind: Literal["observation-capture", "simulation-result"]
    after: int
    instance: str
    records: tuple[dict[str, object], ...]
    marking: tuple[dict[str, object], ...]
    initial: tuple[dict[str, object], ...] | None


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError(f"duplicate JSON member {key!r}")
        result[key] = value
    return result


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise EvidenceError(f"non-finite JSON number {value}")
    return number


def _no_constant(value: str) -> None:
    raise EvidenceError(f"non-finite JSON number {value}")


def _json_array(value: list[object]) -> None:
    for item in value:
        _json_value(item)


def _json_object(value: dict[object, object]) -> None:
    for key, item in value.items():
        if not isinstance(key, str):
            raise EvidenceError("JSON object member names must be strings")
        _json_value(key)
        _json_value(item)


def _json_value(value: object) -> None:
    if value is None or type(value) in {bool, int}:
        return
    if isinstance(value, str):
        if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
            raise EvidenceError("JSON strings must contain Unicode scalar values")
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise EvidenceError("JSON numbers must be finite")
    elif isinstance(value, list):
        _json_array(cast(list[object], value))
    elif isinstance(value, dict):
        _json_object(cast(dict[object, object], value))
    else:
        raise EvidenceError(f"value of type {type(value).__name__} is not strict JSON")


def validate_json_value(value: object) -> object:
    """Require one detached, finite, Unicode-scalar JSON value."""
    _json_value(value)
    return value


def _load_json(payload: bytes, subject: str) -> object:
    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_float=_finite_float,
            parse_constant=_no_constant,
        )
        _json_value(value)
        return value
    except EvidenceError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as error:
        raise EvidenceError(f"invalid strict JSON in {subject}: {error}") from None


def _exact_object(value: object, keys: set[str], path: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise EvidenceError(f"{path} must be an object")
    result = cast(dict[str, object], value)
    if set(result) != keys:
        raise EvidenceError(f"{path} must have exactly fields {sorted(keys)}, found {sorted(result)}")
    return result


def _exact_list(value: object, path: str) -> list[object]:
    if not isinstance(value, list):
        raise EvidenceError(f"{path} must be an array")
    return cast(list[object], value)


def _integer(value: object, path: str, *, minimum: int | None = None) -> int:
    if type(value) is not int:
        raise EvidenceError(f"{path} must be an integer, not {value!r}")
    if minimum is not None and value < minimum:
        raise EvidenceError(f"{path} must be at least {minimum}, found {value}")
    return value


def _string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise EvidenceError(f"{path} must be a non-empty string")
    return value


def _canonical_path(value: object, path: str) -> str:
    text = _string(value, path)
    try:
        canonical = str(NetPath(text))
    except ValueError as error:
        raise EvidenceError(f"{path} is not a NetPath: {error}") from None
    if canonical != text:
        raise EvidenceError(f"{path} must use canonical dotted NetPath spelling")
    return text


def _artifact_bytes(digest: str, encoded: str, path: str) -> bytes:
    try:
        payload = base64.b64decode(encoded.encode("ascii"), validate=True)
    except (UnicodeEncodeError, ValueError) as error:
        raise EvidenceError(f"{path}.base64 must be canonical base64: {error}") from None
    if base64.b64encode(payload).decode("ascii") != encoded:
        raise EvidenceError(f"{path}.base64 must use canonical padded base64 spelling")
    if sha256(payload).hexdigest() != digest:
        raise EvidenceError(f"{path}.sha256 does not match the retained source bytes")
    return payload


def validate_marking(
    value: object,
    definition: NetDefinitionV3,
    path: str,
) -> tuple[dict[str, object], ...]:
    """Validate and normalize protocol-v1 sparse marking JSON."""
    entries = _exact_list(value, path)
    result: list[dict[str, object]] = []
    places = {place.path: place for place in definition.definition.places}
    for index, entry in enumerate(entries):
        item_path = f"{path}[{index}]"
        item = _exact_object(entry, {"place", "tokens"}, item_path)
        place = _canonical_path(item["place"], f"{item_path}.place")
        if place not in places:
            raise EvidenceError(f"{item_path}.place names foreign place {place!r}")
        tokens = _exact_list(item["tokens"], f"{item_path}.tokens")
        if not tokens:
            raise EvidenceError(f"{item_path}.tokens must be nonempty in sparse marking form")
        normalized_tokens: list[dict[str, object]] = []
        expected_color = places[place].color
        for token_index, token in enumerate(tokens):
            token_path = f"{item_path}.tokens[{token_index}]"
            token_value = _exact_object(token, {"color", "data"}, token_path)
            color = token_value["color"]
            if color is not None and (not isinstance(color, str) or not color):
                raise EvidenceError(f"{token_path}.color must be a nonempty string or null")
            if expected_color is not None and color != expected_color:
                raise EvidenceError(
                    f"{token_path}.color {color!r} does not match place {place!r} color {expected_color!r}"
                )
            _json_value(token_value["data"])
            normalized_tokens.append({"color": color, "data": token_value["data"]})
        result.append({"place": place, "tokens": normalized_tokens})
    names = tuple(_string(item["place"], f"{path}[{index}].place") for index, item in enumerate(result))
    expected = tuple(sorted(names, key=lambda item: tuple(ord(character) for character in item)))
    if names != expected:
        raise EvidenceError(f"{path} places must be sorted by Unicode scalar value")
    if len(names) != len(set(names)):
        raise EvidenceError(f"{path} places must be unique")
    return tuple(result)


def _tokens(value: object, path: str) -> None:
    for index, token in enumerate(_exact_list(value, path)):
        item = _exact_object(token, {"color", "data"}, f"{path}[{index}]")
        color = item["color"]
        if color is not None and (not isinstance(color, str) or not color):
            raise EvidenceError(f"{path}[{index}].color must be a nonempty string or null")
        _json_value(item["data"])


def _selections(value: object, path: str) -> None:
    for index, selection in enumerate(_exact_list(value, path)):
        item_path = f"{path}[{index}]"
        item = _exact_object(selection, {"place", "tokens"}, item_path)
        _canonical_path(item["place"], f"{item_path}.place")
        _tokens(item["tokens"], f"{item_path}.tokens")


def _in_flight(value: object, path: str) -> None:
    for index, entry in enumerate(_exact_list(value, path)):
        item_path = f"{path}[{index}]"
        item = _exact_object(
            entry,
            {"occurrence", "transition", "phase", "binding", "invocation", "result"},
            item_path,
        )
        _integer(item["occurrence"], f"{item_path}.occurrence", minimum=1)
        _canonical_path(item["transition"], f"{item_path}.transition")
        if item["phase"] not in {"pure_pending", "activity_pending", "projection_pending"}:
            raise EvidenceError(f"{item_path}.phase is unsupported")
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
            _json_value(invocation["input"])
            policy = _exact_object(
                invocation["policy"],
                {"attempts", "heartbeat_timeout"},
                f"{item_path}.invocation.policy",
            )
            _integer(policy["attempts"], f"{item_path}.invocation.policy.attempts", minimum=1)
            _integer(policy["heartbeat_timeout"], f"{item_path}.invocation.policy.heartbeat_timeout", minimum=1)
            if invocation["correlation"] is not None:
                _string(invocation["correlation"], f"{item_path}.invocation.correlation")
            if invocation["idempotency"] is not None:
                _string(invocation["idempotency"], f"{item_path}.invocation.idempotency")
        _json_value(item["result"])
        if item["phase"] == "pure_pending" and (invocation is not None or item["result"] is not None):
            raise EvidenceError(f"{item_path} pure_pending cannot carry an invocation or result")
        if item["phase"] == "activity_pending" and (invocation is None or item["result"] is not None):
            raise EvidenceError(f"{item_path} activity_pending requires an invocation and no result")
        if item["phase"] == "projection_pending" and invocation is None:
            raise EvidenceError(f"{item_path} projection_pending requires an invocation")


def canonical_record(value: object, path: str) -> dict[str, object]:
    """Decode and re-encode one exact current canonical History record."""
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise EvidenceError(f"{path} must be an object")
    record = cast(dict[str, object], value)
    _integer(record.get("schema"), f"{path}.schema")
    _integer(record.get("instant"), f"{path}.instant")
    if "occurrence" in record and record["occurrence"] is not None:
        _integer(record["occurrence"], f"{path}.occurrence", minimum=1)
    try:
        decoded = decode_record(record)
    except (TypeError, ValueError) as error:
        raise EvidenceError(f"{path} is not a canonical History record: {error}") from None
    encoded = encode_record(decoded)
    if encoded != record:
        raise EvidenceError(f"{path} is not the record's exact canonical schema spelling")
    return encoded


def replay_records(
    records: tuple[dict[str, object], ...],
    definition: NetDefinitionV3,
    path: str,
) -> tuple[dict[str, object], ...]:
    """Replay one source-local canonical sequence to a sparse marking."""
    decoded = tuple(canonical_record(record, f"{path}[{index}]") for index, record in enumerate(records))
    try:
        history = tuple(decode_record(record) for record in decoded)
        value = project_marking(replay_marking(history))
        replay_watermark(history)
    except ValueError as error:
        raise EvidenceError(f"{path} cannot be replayed: {error}") from None
    return validate_marking(value, definition, f"{path} replay marking")


def _history(value: object, path: str) -> tuple[str, tuple[dict[str, object], ...], tuple[object, ...]]:
    history = _exact_object(value, {"protocol", "instance", "after", "next", "frontier", "records"}, path)
    if _integer(history["protocol"], f"{path}.protocol") != 1:
        raise EvidenceError(f"{path}.protocol must be 1")
    instance = _string(history["instance"], f"{path}.instance")
    if _integer(history["after"], f"{path}.after", minimum=0) != 0:
        raise EvidenceError(f"{path}.after must be zero for complete evidence")
    frontier = _integer(history["frontier"], f"{path}.frontier", minimum=1)
    if _integer(history["next"], f"{path}.next", minimum=0) != frontier:
        raise EvidenceError(f"{path}.next must equal frontier")
    entries = _exact_list(history["records"], f"{path}.records")
    if len(entries) != frontier:
        raise EvidenceError(f"{path}.records must contain exactly frontier entries")
    raw: list[dict[str, object]] = []
    decoded = []
    for position, entry in enumerate(entries):
        item_path = f"{path}.records[{position}]"
        item = _exact_object(entry, {"position", "record"}, item_path)
        if _integer(item["position"], f"{item_path}.position", minimum=0) != position:
            raise EvidenceError(f"{item_path}.position must equal its array index")
        record = canonical_record(item["record"], f"{item_path}.record")
        decoded.append(decode_record(record))
        raw.append({"position": position, "record": record})
    identity = replay_instance_identity(decoded)
    if not isinstance(identity, InstanceCreated) or identity.instance != instance:
        raise EvidenceError(f"{path} must start with the matching InstanceCreated record")
    return instance, tuple(raw), tuple(decoded)


def _snapshot(
    value: object,
    definition: NetDefinitionV3,
    path: str,
) -> tuple[str, int, tuple[dict[str, object], ...], dict[str, object]]:
    snapshot = _exact_object(value, {"protocol", "instance", "definition", "frontier", "current"}, path)
    if _integer(snapshot["protocol"], f"{path}.protocol") != 1:
        raise EvidenceError(f"{path}.protocol must be 1")
    instance = _string(snapshot["instance"], f"{path}.instance")
    frontier = _integer(snapshot["frontier"], f"{path}.frontier", minimum=1)
    if snapshot["definition"] != definition.definition.model_dump(mode="json"):
        raise EvidenceError(f"{path}.definition does not match the document's canonical definition")
    current = _exact_object(
        snapshot["current"],
        {"marking", "status", "watermark", "in_flight", "armed", "next_maturation"},
        f"{path}.current",
    )
    marking = validate_marking(current["marking"], definition, f"{path}.current.marking")
    if current["status"] not in {"running", "terminated", "completed", "stuck", "awaiting"}:
        raise EvidenceError(f"{path}.current.status is unsupported")
    _integer(current["watermark"], f"{path}.current.watermark")
    _in_flight(current["in_flight"], f"{path}.current.in_flight")
    prior: tuple[str, str] | None = None
    for index, entry in enumerate(_exact_list(current["armed"], f"{path}.current.armed")):
        item_path = f"{path}.current.armed[{index}]"
        item = _exact_object(entry, {"source", "key"}, item_path)
        pair = (_canonical_path(item["source"], f"{item_path}.source"), _string(item["key"], f"{item_path}.key"))
        if prior is not None and pair <= prior:
            raise EvidenceError(f"{path}.current.armed must be unique and source/key sorted")
        prior = pair
    if current["next_maturation"] is not None:
        _integer(current["next_maturation"], f"{path}.current.next_maturation")
    return instance, frontier, marking, current


def _source_state(
    snapshot: object,
    history: object,
    definition: NetDefinitionV3,
    path: str,
) -> tuple[str, tuple[dict[str, object], ...], tuple[dict[str, object], ...]]:
    snapshot_instance, snapshot_frontier, marking, current = _snapshot(snapshot, definition, f"{path}.snapshot")
    history_instance, records, decoded = _history(history, f"{path}.history")
    if snapshot_instance != history_instance:
        raise EvidenceError(f"{path} snapshot and History instance identities differ")
    if snapshot_frontier != len(records):
        raise EvidenceError(f"{path} snapshot and History frontiers differ")
    try:
        replayed_marking = validate_marking(
            project_marking(replay_marking(decoded)), definition, f"{path}.history replay marking"
        )
        replayed_watermark = replay_watermark(decoded)
        replayed_armed = [
            {"source": str(source), "key": key}
            for source, keys in sorted(replay_armed(decoded).items(), key=lambda item: str(item[0]))
            for key in sorted(keys)
        ]
    except ValueError as error:
        raise EvidenceError(f"{path}.history cannot be replayed: {error}") from None
    if replayed_marking != marking:
        raise EvidenceError(f"{path}.snapshot marking disagrees with replayed History")
    if replayed_watermark != current["watermark"]:
        raise EvidenceError(f"{path}.snapshot watermark disagrees with replayed History")
    if replayed_armed != current["armed"]:
        raise EvidenceError(f"{path}.snapshot armed registrations disagree with replayed History")
    return snapshot_instance, records, marking


def _admit_capture(
    value: object,
    after: int,
    definition: NetDefinitionV3,
    path: str,
) -> AdmittedEvidence:
    source = _exact_object(value, {"format", "version", "snapshot", "history"}, f"{path}.artifact")
    if source["format"] != "petrus-observation-capture" or _integer(source["version"], f"{path}.artifact.version") != 1:
        raise EvidenceError(f"{path}.artifact must embed observation capture schema 1")
    instance, records, marking = _source_state(source["snapshot"], source["history"], definition, f"{path}.artifact")
    if after >= len(records):
        raise EvidenceError(f"{path}.after must be smaller than its capture frontier")
    return AdmittedEvidence("observation-capture", after, instance, records, marking, None)


def _admit_simulation(value: object, definition: NetDefinitionV3, path: str) -> AdmittedEvidence:
    source = _exact_object(
        value,
        {"format", "version", "profile", "scenario", "outcome", "snapshot", "history"},
        f"{path}.artifact",
    )
    if source["format"] != "petrus-simulation-result" or _integer(source["version"], f"{path}.artifact.version") != 1:
        raise EvidenceError(f"{path}.artifact must embed simulation result schema 1")
    if source["profile"] != "implementation-free-v1":
        raise EvidenceError(f"{path}.artifact.profile must be implementation-free-v1")
    scenario = _exact_object(
        source["scenario"], {"start_instant", "initial_marking", "max_actions"}, f"{path}.artifact.scenario"
    )
    if _integer(scenario["start_instant"], f"{path}.artifact.scenario.start_instant") != 0:
        raise EvidenceError(f"{path}.artifact.scenario.start_instant must be zero")
    max_actions = _integer(scenario["max_actions"], f"{path}.artifact.scenario.max_actions", minimum=1)
    if max_actions > 256:
        raise EvidenceError(f"{path}.artifact.scenario.max_actions exceeds implementation-free-v1")
    initial = validate_marking(scenario["initial_marking"], definition, f"{path}.artifact.scenario.initial_marking")
    outcome = _exact_object(source["outcome"], {"actions_applied", "reason"}, f"{path}.artifact.outcome")
    actions = _integer(outcome["actions_applied"], f"{path}.artifact.outcome.actions_applied", minimum=0)
    if actions > max_actions:
        raise EvidenceError(f"{path}.artifact.outcome.actions_applied exceeds max_actions")
    if outcome["reason"] not in {"rest", "action_limit"}:
        raise EvidenceError(f"{path}.artifact.outcome.reason is unsupported")
    instance, records, marking = _source_state(source["snapshot"], source["history"], definition, f"{path}.artifact")
    applied = sum(
        cast(dict[str, object], item["record"]).get("record") in {"TimerMatured", "FiringCompleted"} for item in records
    )
    if applied != actions:
        raise EvidenceError(f"{path}.artifact.outcome.actions_applied disagrees with its complete History")
    return AdmittedEvidence("simulation-result", 0, instance, records, marking, initial)


def admit_evidence(
    *,
    kind: Literal["observation-capture", "simulation-result"],
    after: int,
    digest: str,
    base64_value: str,
    definition: NetDefinitionV3,
    path: str,
) -> AdmittedEvidence:
    """Decode, strictly validate, and relate one retained source artifact."""
    payload = _artifact_bytes(digest, base64_value, f"{path}.artifact")
    value = _load_json(payload, f"{path}.artifact")
    if kind == "observation-capture":
        return _admit_capture(value, after, definition, path)
    return _admit_simulation(value, definition, path)


__all__ = [
    "AdmittedEvidence",
    "EvidenceError",
    "admit_evidence",
    "canonical_record",
    "replay_records",
    "validate_json_value",
    "validate_marking",
]
