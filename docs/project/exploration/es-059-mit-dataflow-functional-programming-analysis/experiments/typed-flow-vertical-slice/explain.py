"""Join immutable canonical History records to the source-map sidecar.

The explained History is a detached JSON projection regenerated from
canonical records plus the source map — never a second semantic log and never
execution authority. Every record must explain back to an authored source;
the only enumerated neutral record category is ``TimerMatured``, which has no
Net node and no authored owner.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import cast

from petrus.impetus.history import (
    ActivityCompleted,
    ActivityFailed,
    ActivityRequested,
    ActivityTerminalQuarantined,
    CandidateSelected,
    DeliveryRegistrationClosed,
    DeliveryRegistrationOpened,
    ExternalEventDelivered,
    FiringBegun,
    FiringCompleted,
    FiringFailed,
    InstanceCreated,
    Record,
    ScopeClosed,
    ScopeOpened,
    ScopeReset,
    ScopedDeliveryDropped,
    ScopedDeliveryQuarantined,
    TimerMatured,
    TokensConsumed,
    TokensInitialized,
    TokensProduced,
    TokensRead,
)
from petrus.impetus.scope import LifecycleScope

from source_map import SourceMapV1

FORMAT = "petrus-experiment-explained-history"
VERSION = 1

_NEUTRAL = (TimerMatured,)

_TRANSITION_RECORDS = (
    CandidateSelected,
    FiringBegun,
    ActivityRequested,
    ActivityCompleted,
    ActivityFailed,
    ActivityTerminalQuarantined,
    FiringCompleted,
    FiringFailed,
)
_PLACE_RECORDS = (TokensInitialized, TokensConsumed, TokensRead, TokensProduced)
_SOURCE_RECORDS = (
    ExternalEventDelivered,
    ScopedDeliveryDropped,
    ScopedDeliveryQuarantined,
    DeliveryRegistrationOpened,
    DeliveryRegistrationClosed,
)
_SCOPE_RECORDS = (ScopeOpened, ScopeClosed, ScopeReset)


def _scope_value(scope: LifecycleScope | str | None) -> object:
    if scope is None:
        return None
    if isinstance(scope, str):
        return {"name": scope, "generation": None}
    return {"name": scope.name, "generation": scope.generation}


def _tokens(tokens) -> list[dict[str, object]]:
    return [{"color": token.color, "data": token.data} for token in tokens]


def _source_entry(source_map: SourceMapV1, source_id: str) -> dict[str, object]:
    entry = source_map.source_for(source_id)
    if entry is None:
        raise ValueError(f"source id {source_id!r} is not in the source map")
    return {"id": entry.id, "file": entry.file, "line": entry.line, "symbol": entry.symbol}


def _node_attribution(source_map: SourceMapV1, path: str, record: Record, index: int) -> dict[str, object]:
    element = source_map.element_for(path)
    if element is None:
        raise ValueError(f"record {index} ({type(record).__name__}) names unmapped node {path}")
    return {
        "node": path,
        "role": element.role,
        "source": _source_entry(source_map, element.source),
    }


def _scope_attribution(source_map: SourceMapV1, name: str, record: Record, index: int) -> dict[str, object]:
    scope = source_map.scope_for(name)
    if scope is None:
        raise ValueError(f"record {index} ({type(record).__name__}) names unmapped scope {name!r}")
    return {"node": None, "role": "lifecycle scope", "source": _source_entry(source_map, scope.source)}


def _detail(record: Record) -> dict[str, object]:
    if isinstance(record, InstanceCreated):
        return {"instance": record.instance, "name": record.name}
    if isinstance(record, ExternalEventDelivered):
        return {"identity": record.identity, "tokens": _tokens(record.tokens)}
    if isinstance(record, (ScopedDeliveryDropped, ScopedDeliveryQuarantined)):
        return {"identity": record.identity, "tokens": _tokens(record.tokens)}
    if isinstance(record, _PLACE_RECORDS):
        return {"tokens": _tokens(record.tokens)}
    if isinstance(record, ActivityRequested):
        return {
            "activity": record.activity,
            "input": record.input,
            "correlation": record.correlation,
            "idempotency": record.idempotency,
        }
    if isinstance(record, ActivityCompleted):
        return {"result": record.result}
    if isinstance(record, (ActivityFailed, FiringFailed)):
        return {"error": record.error}
    if isinstance(record, ScopeReset):
        return {
            "closed": _scope_value(record.closed),
            "opened": _scope_value(record.opened),
            "discarded": list(record.discarded),
            "cancelled": list(record.cancelled),
        }
    if isinstance(record, ScopeClosed):
        return {"discarded": list(record.discarded), "cancelled": list(record.cancelled)}
    if isinstance(record, (DeliveryRegistrationOpened, DeliveryRegistrationClosed)):
        return {"key": record.key}
    return {}


def _attribution(source_map: SourceMapV1, record: Record, index: int) -> dict[str, object]:
    if isinstance(record, InstanceCreated):
        if record.name is None:
            raise ValueError(f"record {index}: InstanceCreated has no net name to attribute")
        return {"node": None, "role": "authored machine", "source": _source_entry(source_map, record.name)}
    if isinstance(record, _SCOPE_RECORDS):
        name = record.closed.name if isinstance(record, ScopeReset) else record.scope.name
        return _scope_attribution(source_map, name, record, index)
    if isinstance(record, _TRANSITION_RECORDS):
        return _node_attribution(source_map, str(record.transition), record, index)
    if isinstance(record, _PLACE_RECORDS):
        return _node_attribution(source_map, str(record.place), record, index)
    if isinstance(record, _SOURCE_RECORDS):
        return _node_attribution(source_map, str(record.source), record, index)
    if isinstance(record, _NEUTRAL):
        return {"node": None, "role": "neutral", "source": None}
    raise ValueError(f"record {index} ({type(record).__name__}) has no attribution rule")


def _entry(source_map: SourceMapV1, record: Record, index: int) -> dict[str, object]:
    entry: dict[str, object] = {
        "index": index,
        "record": type(record).__name__,
        "instant": record.instant,
    }
    occurrence = getattr(record, "occurrence", None)
    if occurrence is not None:
        entry["occurrence"] = occurrence
    scope = getattr(record, "scope", None)
    if scope is not None and not isinstance(record, _SCOPE_RECORDS):
        entry["scope"] = _scope_value(scope)
    entry.update(_attribution(source_map, record, index))
    entry["detail"] = _detail(record)
    return entry


def _occurrence_groups(entries: list[dict[str, object]], records: Sequence[Record]) -> list[dict[str, object]]:
    groups: dict[int, dict[str, object]] = {}
    for entry, record in zip(entries, records, strict=True):
        occurrence = entry.get("occurrence")
        if occurrence is None:
            continue
        group = groups.setdefault(
            cast(int, occurrence),
            {
                "occurrence": occurrence,
                "transition": None,
                "source": None,
                "accepted": [],
                "read": [],
                "produced": [],
                "activity": None,
                "ended": None,
            },
        )
        if isinstance(record, (CandidateSelected, FiringBegun)):
            group["transition"] = str(record.transition)
            group["source"] = entry["source"]
        elif isinstance(record, ExternalEventDelivered):
            group["transition"] = str(record.source)
            group["source"] = entry["source"]
            group["accepted"] = _tokens(record.tokens)
        elif isinstance(record, TokensConsumed):
            group["accepted"] = [*cast(list, group["accepted"]), *_tokens(record.tokens)]
        elif isinstance(record, TokensRead):
            group["read"] = [*cast(list, group["read"]), *_tokens(record.tokens)]
        elif isinstance(record, TokensProduced):
            group["produced"] = [
                *cast(list, group["produced"]),
                {"place": str(record.place), "tokens": _tokens(record.tokens)},
            ]
        elif isinstance(record, ActivityRequested):
            group["activity"] = {
                "activity": record.activity,
                "correlation": record.correlation,
                "idempotency": record.idempotency,
            }
        elif isinstance(record, ActivityCompleted) and group["activity"] is not None:
            group["activity"] = {**cast(dict, group["activity"]), "result": record.result}
        elif isinstance(record, (FiringCompleted, FiringFailed)):
            group["ended"] = type(record).__name__
    return [groups[occurrence] for occurrence in sorted(groups)]


def explain_history(records: Sequence[Record], source_map: SourceMapV1) -> dict[str, object]:
    """Project canonical records into the attributed explained History."""
    entries = [_entry(source_map, record, index) for index, record in enumerate(records)]
    return {
        "format": FORMAT,
        "version": VERSION,
        "definition_sha256": source_map.definition_sha256,
        "entries": entries,
        "occurrences": _occurrence_groups(entries, records),
    }


def unattributed_records(records: Sequence[Record], source_map: SourceMapV1) -> tuple[str, ...]:
    """Name every record the source map cannot attribute (empty when complete)."""
    failures = []
    for index, record in enumerate(records):
        try:
            _attribution(source_map, record, index)
        except ValueError as error:
            failures.append(str(error))
    return tuple(failures)


def serialize_explained(document: dict[str, object]) -> bytes:
    return (json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")
