"""Canonical schema-4 codec for the unified semantic event history."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields
from typing import Any, get_args

from petrus.motus.activity import ExecutionPolicy
from petrus.impetus.history import DeliveryRegistration, Record
from petrus.impetus.petrinet import Token
from petrus.impetus.petrinet import NetPath

SCHEMA_VERSION = 4

_RECORD_TYPES: Mapping[str, type] = {record_type.__name__: record_type for record_type in get_args(Record)}
_V1_SUCCESSORS: Mapping[str, str] = {
    "RegistrationOpened": "DeliveryRegistrationOpened",
    "RegistrationClosed": "DeliveryRegistrationClosed",
    "ExternalEventRecorded": "ExternalEventDelivered",
}
_NODE_FIELDS = frozenset({"place", "transition", "source"})


def encode_record(record: Record) -> dict[str, Any]:
    """Encode a record under the canonical schema-4 envelope."""
    return {"record": type(record).__name__, "schema": SCHEMA_VERSION} | {
        field.name: _encoded(getattr(record, field.name)) for field in fields(record)
    }


def decode_record(payload: Mapping[str, Any]) -> Record:
    """Decode the canonical schema-4 envelope, refusing unknown or old forms."""
    data = dict(payload)
    if "record" not in data:
        raise ValueError("cannot decode event history record: payload has no 'record' discriminator")
    name = data.pop("record")
    if "schema" not in data:
        raise ValueError(
            f"cannot decode event history record {name!r}: payload has no 'schema' version — this kernel "
            f"writes and reads schema 4, and has no converter for older durable data"
        )
    schema = data.pop("schema")
    if schema != SCHEMA_VERSION:
        raise ValueError(
            f"cannot decode event history record {name!r}: 'schema' is {schema!r}, and this kernel "
            f"reads schema 4 only — no migration or converter exists"
        )
    if name not in _RECORD_TYPES:
        if name in _V1_SUCCESSORS:
            raise ValueError(
                f"cannot decode event history record: {name!r} is a schema-1 discriminator — the CV3 "
                f"schema-2 migration renamed it to {_V1_SUCCESSORS[name]!r}, and no v1 converter exists "
                f"(no production histories predate the migration)"
            )
        raise ValueError(
            f"cannot decode event history record: unknown 'record' discriminator {name!r} — "
            f"not a record type the kernel emits"
        )
    return _RECORD_TYPES[name](**{field: _decoded(field, value) for field, value in data.items()})


def _encoded(value: Any) -> Any:
    if isinstance(value, NetPath):
        return str(value)
    if isinstance(value, Token):
        return {"color": value.color, "data": value.data}
    if isinstance(value, DeliveryRegistration):
        return {"source": str(value.source), "key": value.key}
    if isinstance(value, ExecutionPolicy):
        return {"attempts": value.attempts, "heartbeat_timeout": value.heartbeat_timeout}
    if isinstance(value, tuple):
        return [_encoded(item) for item in value]
    return value


def _decoded(field: str, value: Any) -> Any:
    if field in _NODE_FIELDS:
        return NetPath(value)
    if field == "tokens":
        return tuple(Token(**token) for token in value)
    if field == "policy":
        if (
            not isinstance(value, Mapping)
            or set(value) != {"attempts", "heartbeat_timeout"}
            or isinstance(value["attempts"], bool)
            or not isinstance(value["attempts"], int)
            or isinstance(value["heartbeat_timeout"], bool)
            or not isinstance(value["heartbeat_timeout"], int)
        ):
            raise ValueError(
                "cannot decode ExecutionPolicy: policy must be exactly "
                f"{{'attempts': int, 'heartbeat_timeout': int}}, got {value!r}"
            )
        return ExecutionPolicy(attempts=value["attempts"], heartbeat_timeout=value["heartbeat_timeout"])
    return value


__all__ = ["SCHEMA_VERSION", "decode_record", "encode_record"]
