"""Detached canonical projections for runtime observation and static inspection."""

from __future__ import annotations

from dataclasses import fields
import json
from typing import Any

from petrus.impetus.net_document import (
    ExecutionLineage,
    LineageEntry,
    PlaceMarking,
    project_net_document,
    serialize_net_document,
)
from petrus.impetus.net_definition import project_net_definition
from petrus.impetus.history import Record, replay_markings
from petrus.impetus.history.codec import encode_record
from petrus.impetus.instance import Instance
from petrus.impetus.petrinet import Net, Token
from petrus.motus.activity import ActivityFailure

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]


def _strict(value: object) -> Any:
    """Return a detached JSON value, refusing extensions and non-finite numbers."""
    try:
        return json.loads(json.dumps(value, allow_nan=False))
    except (TypeError, ValueError) as error:
        raise ValueError(f"observation data must be strict JSON-faithful: {error}") from None


def _integer(value: object, subject: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"protocol 1 requires {subject} to be an integer, got {value!r}")
    return value


def definition(net: Net) -> dict[str, object]:
    """Project the v3-pinned canonical definition nested by protocol 1."""
    try:
        return project_net_definition(net).definition.model_dump(mode="json")
    except ValueError as error:
        raise ValueError(f"observation data must be strict JSON-faithful: {error}") from None


def net_inspection(net: Net) -> dict[str, object]:
    """Export one definition-only portable Net document."""
    return json.loads(serialize_net_document(project_net_document(net)))


def net_document(instance: Instance, records: tuple[Record, ...]) -> dict[str, object]:
    """Project one coherent observed Instance into a portable Net document."""
    if not records:
        raise ValueError("an observed Net document requires nonempty canonical History")
    current = snapshot(instance, records)["current"]
    assert isinstance(current, dict)
    observation = {key: value for key, value in current.items() if key != "marking"}
    history_markings = replay_markings(records)
    entries = tuple(
        LineageEntry(
            id=index,
            parent=None if index == 0 else index - 1,
            provenance="observed",
            marking=tuple(
                PlaceMarking.model_validate(entry, strict=True) for entry in marking(history_markings[index])
            ),
            metadata={
                **({"instance": instance.instance_id} if index == 0 else {}),
                **({"observation": observation} if index == len(records) - 1 else {}),
                "history_record": encode_record(record),
            },
        )
        for index, record in enumerate(records)
    )
    document = project_net_document(
        instance.net,
        lineage=ExecutionLineage(head=len(entries) - 1, entries=entries),
    )
    return json.loads(serialize_net_document(document))


def _tokens(tokens: tuple[Token, ...]) -> list[dict[str, object]]:
    return [{"color": token.color, "data": token.data} for token in tokens]


def marking(value) -> list[dict[str, object]]:
    """Project one Marking in protocol-v1 ordered place/token shape."""
    return _strict(
        [
            {"place": str(place), "tokens": _tokens(tokens)}
            for place, tokens in sorted(value, key=lambda item: str(item[0]))
        ]
    )


def _selections(selections) -> list[dict[str, object]]:
    return [{"place": str(place), "tokens": _tokens(tokens)} for place, tokens in selections]


def _activity_result(value: object) -> object:
    if isinstance(value, ActivityFailure):
        return {
            "error": value.error,
            "kind": value.kind,
            "details": value.details,
            "retryable": value.retryable,
            "retry_after": value.retry_after,
        }
    return value


def snapshot(instance: Instance, records: tuple[Record, ...]) -> dict[str, object]:
    """Capture one coherent current protocol-v1 snapshot."""
    watermark = _integer(instance.watermark, "current watermark")
    maturation = instance.next_maturation
    if maturation is not None:
        maturation = _integer(maturation, "next maturation")
    in_flight = []
    for occurrence in instance.in_flight:
        frozen = occurrence.id in instance._frozen_results  # noqa: SLF001 - observation is an Instance leaf
        phase = "projection_pending" if frozen else "activity_pending" if occurrence.invocation else "pure_pending"
        invocation = occurrence.invocation
        in_flight.append(
            {
                "occurrence": occurrence.id,
                "transition": str(occurrence.binding.transition),
                "phase": phase,
                "binding": {
                    "consumed": _selections(occurrence.binding.consumed),
                    "read": _selections(occurrence.binding.read),
                    "delivered": _tokens(occurrence.binding.delivered),
                },
                "invocation": None
                if invocation is None
                else {
                    "activity": invocation.activity,
                    "input": invocation.input,
                    "policy": {
                        field.name: getattr(invocation.policy, field.name) for field in fields(invocation.policy)
                    },
                    "correlation": invocation.correlation,
                    "idempotency": invocation.idempotency,
                },
                "result": _activity_result(instance._frozen_results[occurrence.id]) if frozen else None,  # noqa: SLF001
            }
        )
    payload = {
        "protocol": 1,
        "instance": instance.instance_id,
        "definition": definition(instance.net),
        "frontier": len(records),
        "current": {
            "marking": marking(instance.marking),
            "status": instance.status.value,
            "watermark": watermark,
            "in_flight": in_flight,
            "armed": [
                {"source": str(source), "key": key}
                for source, keys in sorted(instance.armed.items(), key=lambda item: str(item[0]))
                for key in sorted(keys)
            ],
            "next_maturation": maturation,
        },
    }
    return _strict(payload)


def history_page(instance_id: str, records: tuple[Record, ...], after: int, limit: int) -> dict[str, object]:
    """Encode one exclusive-prefix page from a captured canonical History."""
    if isinstance(after, bool) or not isinstance(after, int) or after < 0:
        raise ValueError(f"history after must be a non-negative integer, got {after!r}")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError(f"history limit must be a positive integer, got {limit!r}")
    frontier = len(records)
    if after > frontier:
        raise ValueError(f"history after {after} exceeds captured frontier {frontier}")
    end = min(after + limit, frontier)
    return _strict(
        {
            "protocol": 1,
            "instance": instance_id,
            "after": after,
            "next": end,
            "frontier": frontier,
            "records": [
                {"position": position, "record": encode_record(records[position])} for position in range(after, end)
            ],
        }
    )


__all__ = ["definition", "history_page", "marking", "net_document", "net_inspection", "snapshot"]
