"""Canonical codec for schema-4 histories and schema-5 lifecycle scopes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields
from typing import Any, get_args

from petrus.motus.activity import ExecutionPolicy
from petrus.impetus.history import (
    ActivityTerminalQuarantined,
    DeliveryRegistration,
    Record,
    ScopeClosed,
    ScopeOpened,
    ScopeReset,
    ScopedDeliveryDropped,
    ScopedDeliveryQuarantined,
)
from petrus.impetus.petrinet import Token
from petrus.impetus.petrinet import NetPath
from petrus.impetus.scope import LifecycleScope

# Preserve the established public unscoped wire constant: ordinary records
# still encode byte-for-byte as schema 4. Lifecycle records and provenance
# opt into the additive schema-5 record envelope within the same History.
SCHEMA_VERSION = 4
LIFECYCLE_SCHEMA_VERSION = 5
READABLE_SCHEMA_VERSIONS = frozenset({SCHEMA_VERSION, LIFECYCLE_SCHEMA_VERSION})

_RECORD_TYPES: Mapping[str, type] = {record_type.__name__: record_type for record_type in get_args(Record)}
_V1_SUCCESSORS: Mapping[str, str] = {
    "RegistrationOpened": "DeliveryRegistrationOpened",
    "RegistrationClosed": "DeliveryRegistrationClosed",
    "ExternalEventRecorded": "ExternalEventDelivered",
}
_NODE_FIELDS = frozenset({"place", "transition", "source"})
_SCHEMA_5_RECORDS = (
    ScopeOpened,
    ScopeClosed,
    ScopeReset,
    ScopedDeliveryDropped,
    ScopedDeliveryQuarantined,
    ActivityTerminalQuarantined,
)
_SCHEMA_5_FIELDS = frozenset({"entries", "scope"})


def encode_record(record: Record) -> dict[str, Any]:
    """
    Encode one canonical record.

    Existing unscoped records deliberately retain their exact schema-4 wire;
    opting into lifecycle scope provenance moves that record (and only that
    record) to schema 5. This keeps old unscoped histories byte-compatible
    while allowing one history to acquire scoped records additively.
    """
    schema = LIFECYCLE_SCHEMA_VERSION if _uses_schema_5(record) else SCHEMA_VERSION
    encoded = {
        field.name: _encoded(getattr(record, field.name))
        for field in fields(record)
        if schema == LIFECYCLE_SCHEMA_VERSION or field.name not in _SCHEMA_5_FIELDS
    }
    return {"record": type(record).__name__, "schema": schema} | encoded


def decode_record(payload: Mapping[str, Any]) -> Record:
    """Decode canonical schema 5 or the accepted schema-4 predecessor."""
    data = dict(payload)
    if "record" not in data:
        raise ValueError("cannot decode event history record: payload has no 'record' discriminator")
    name = data.pop("record")
    if "schema" not in data:
        raise ValueError(
            f"cannot decode event history record {name!r}: payload has no 'schema' version — this kernel "
            f"writes schemas {sorted(READABLE_SCHEMA_VERSIONS)}, reads those same schemas, and has no converter "
            f"for older durable data"
        )
    schema = data.pop("schema")
    if type(schema) is not int or schema not in READABLE_SCHEMA_VERSIONS:
        raise ValueError(
            f"cannot decode event history record {name!r}: 'schema' is {schema!r}, and this kernel "
            f"reads schemas {sorted(READABLE_SCHEMA_VERSIONS)} only — no migration or converter exists"
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
    if schema == SCHEMA_VERSION and (
        _RECORD_TYPES[name] in _SCHEMA_5_RECORDS or any(field in data for field in _SCHEMA_5_FIELDS)
    ):
        raise ValueError(
            f"cannot decode event history record {name!r}: lifecycle scope records and provenance require schema 5"
        )
    decoded = _RECORD_TYPES[name](**{field: _decoded(field, value) for field, value in data.items()})
    expected = LIFECYCLE_SCHEMA_VERSION if _uses_schema_5(decoded) else SCHEMA_VERSION
    if schema != expected:
        raise ValueError(
            f"cannot decode event history record {name!r}: schema {schema} is not its canonical "
            f"record spelling (expected schema {expected})"
        )
    return decoded


def _uses_schema_5(record: Record) -> bool:
    """Whether this record uses the lifecycle-scope extension."""
    if isinstance(record, _SCHEMA_5_RECORDS):
        return True
    return any(
        field.name in _SCHEMA_5_FIELDS and getattr(record, field.name) not in (None, ()) for field in fields(record)
    )


def _encoded(value: Any) -> Any:
    if isinstance(value, NetPath):
        return str(value)
    if isinstance(value, Token):
        return {"color": value.color, "data": value.data}
    if isinstance(value, DeliveryRegistration):
        return {"source": str(value.source), "key": value.key}
    if isinstance(value, LifecycleScope):
        return {"name": value.name, "generation": value.generation}
    if isinstance(value, ExecutionPolicy):
        encoded = {field.name: getattr(value, field.name) for field in fields(value)}
        defaults = ExecutionPolicy()
        if all(
            encoded[name] == getattr(defaults, name)
            for name in encoded
            if name not in {"attempts", "heartbeat_timeout"}
        ):
            return {name: encoded[name] for name in ("attempts", "heartbeat_timeout")}
        return encoded
    if isinstance(value, tuple):
        return [_encoded(item) for item in value]
    return value


def _decoded(field: str, value: Any) -> Any:
    if field in _NODE_FIELDS:
        return NetPath(value)
    if field == "tokens":
        return tuple(Token(**token) for token in value)
    if field in {"entries", "discarded", "cancelled"}:
        return tuple(value)
    if field == "scope":
        return value if value is None or isinstance(value, str) else LifecycleScope(**value)
    if field in {"closed", "opened"}:
        return LifecycleScope(**value)
    if field == "policy":
        old_fields = {"attempts", "heartbeat_timeout"}
        current_fields = {item.name for item in fields(ExecutionPolicy)}
        if (
            not isinstance(value, Mapping)
            or set(value) not in (old_fields, current_fields)
            or isinstance(value["attempts"], bool)
            or not isinstance(value["attempts"], int)
            or isinstance(value["heartbeat_timeout"], bool)
            or not isinstance(value["heartbeat_timeout"], int)
        ):
            raise ValueError(
                "cannot decode ExecutionPolicy: policy must be exactly "
                f"the legacy or current exact policy fields, got {value!r}"
            )
        return ExecutionPolicy(**value)
    return value


__all__ = [
    "LIFECYCLE_SCHEMA_VERSION",
    "READABLE_SCHEMA_VERSIONS",
    "SCHEMA_VERSION",
    "decode_record",
    "encode_record",
]
