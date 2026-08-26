"""Frozen, JSON-faithful domain values for the readiness vertical slice.

Every value that enters tokens, Activity payloads, or History encodes through
the explicit ``to_data``/``from_data`` pair below. The current top-level
``DataclassPayloadConverter`` does not recursively reconstruct nested
dataclasses, so the nested values (``Evidence`` inside ``CIObserved``/
``Ladder``/requests, ``Ladder`` inside ``ReadinessState``) get explicit
experiment-local decoders — known values only, never a generic serialization
framework.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, fields, is_dataclass
from typing import Literal, cast


@dataclass(frozen=True)
class Evidence:
    run_id: int
    attempt: int


@dataclass(frozen=True)
class HeadObserved:
    head: str
    relation: Literal["new", "confirmed", "superseded"]
    generation: int
    lineage: str


@dataclass(frozen=True)
class CIObserved:
    head: str
    evidence: Evidence
    conclusion: Literal["success", "failure"]
    fingerprint: str | None = None


@dataclass(frozen=True)
class Ladder:
    lineage: str
    fingerprint: str | None
    rerun_used: bool
    repair_used: bool
    watermark: Evidence | None


@dataclass(frozen=True)
class ReadinessState:
    head: str
    generation: int
    lineage: str
    ladder: Ladder
    publication_operation: str | None  # set when requested; prevents duplicate authorization


@dataclass(frozen=True)
class PublishRequested:
    operation: str
    head: str
    generation: int


@dataclass(frozen=True)
class RerunRequested:
    operation: str
    head: str
    lineage: str
    fingerprint: str
    evidence: Evidence


@dataclass(frozen=True)
class RepairRequested:
    operation: str
    head: str
    lineage: str
    fingerprint: str
    evidence: Evidence


@dataclass(frozen=True)
class HumanNeeded:
    head: str
    lineage: str
    fingerprint: str


@dataclass(frozen=True)
class Ignored:
    reason: str


@dataclass(frozen=True)
class RerunAccepted:
    operation: str
    head: str


@dataclass(frozen=True)
class RepairLanded:
    operation: str
    head: str
    repaired_head: str


@dataclass(frozen=True)
class PublishAcknowledged:
    operation: str
    head: str
    generation: int


@dataclass(frozen=True)
class Published:
    head: str
    generation: int
    operation: str


def to_data(value: object) -> dict[str, object]:
    """Encode one known frozen domain value as a JSON-faithful mapping."""
    if not is_dataclass(value) or isinstance(value, type):
        raise TypeError(f"to_data encodes known domain dataclass values, got {value!r}")
    return asdict(value)


def _mapping(data: object, noun: str) -> dict[str, object]:
    if not isinstance(data, dict):
        raise ValueError(f"{noun} data must be a mapping, got {data!r}")
    return cast("dict[str, object]", data)


def _evidence(data: object) -> Evidence:
    payload = _mapping(data, "Evidence")
    return Evidence(run_id=cast(int, payload["run_id"]), attempt=cast(int, payload["attempt"]))


def _optional_evidence(data: object) -> Evidence | None:
    return None if data is None else _evidence(data)


def _ladder(data: object) -> Ladder:
    payload = _mapping(data, "Ladder")
    return Ladder(
        lineage=cast(str, payload["lineage"]),
        fingerprint=cast("str | None", payload["fingerprint"]),
        rerun_used=cast(bool, payload["rerun_used"]),
        repair_used=cast(bool, payload["repair_used"]),
        watermark=_optional_evidence(payload["watermark"]),
    )


# The known values whose fields need explicit nested reconstruction.
_NESTED_FIELDS: dict[type, dict[str, Callable[[object], object]]] = {
    CIObserved: {"evidence": _evidence},
    Ladder: {"watermark": _optional_evidence},
    ReadinessState: {"ladder": _ladder},
    RerunRequested: {"evidence": _evidence},
    RepairRequested: {"evidence": _evidence},
}

DOMAIN_TYPES: tuple[type, ...] = (
    Evidence,
    HeadObserved,
    CIObserved,
    Ladder,
    ReadinessState,
    PublishRequested,
    RerunRequested,
    RepairRequested,
    HumanNeeded,
    Ignored,
    RerunAccepted,
    RepairLanded,
    PublishAcknowledged,
    Published,
)


def from_data[T](annotation: type[T], data: object) -> T:
    """Reconstruct one known frozen domain value from its JSON-faithful mapping."""
    if annotation not in DOMAIN_TYPES:
        raise TypeError(f"from_data reconstructs known domain values only, got {annotation!r}")
    payload = _mapping(data, annotation.__name__)
    nested = _NESTED_FIELDS.get(annotation, {})
    arguments: dict[str, object] = {}
    for field in fields(cast("type[Evidence]", annotation)):
        raw = payload[field.name]
        decode = nested.get(field.name)
        arguments[field.name] = decode(raw) if callable(decode) else raw
    return annotation(**arguments)


@dataclass(frozen=True)
class DomainConverter:
    """Payload converter over the known domain values for typed Activities."""

    def decode(self, value: object, annotation: object) -> object:
        if not isinstance(annotation, type):
            raise TypeError(f"DomainConverter requires a concrete domain type, got {annotation!r}")
        return from_data(annotation, value)

    def encode(self, value: object, annotation: object) -> object:
        if not isinstance(annotation, type) or not isinstance(value, annotation):
            raise ValueError(f"DomainConverter cannot encode {value!r} as {annotation!r}")
        return to_data(value)
