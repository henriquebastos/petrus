"""Transport-neutral Fabric model and wire values."""

from __future__ import annotations

# Python imports
import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType

MAX_INLINE_PAYLOAD_BYTES = 64 * 1024
_VERSION = 1
_MAX_TEXT = 1024
_FIELDS = frozenset(
    {"version", "delivery_id", "sender", "recipient", "source", "correlation", "payload", "reply_route"}
)


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value or len(value.encode()) > _MAX_TEXT:
        raise ValueError(f"{name} must be a non-empty string of at most {_MAX_TEXT} UTF-8 bytes")
    return value


def _exact_object(value: object, fields: frozenset[str] | set[str], message: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(message)
    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError(message)
        result[key] = item
    return result


def _json_object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError(f"{name} must be a JSON object")
    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError(f"{name} object keys must be strings")
        result[key] = item
    return result


def _json_copy(value: object, name: str = "payload") -> object:
    def validate(item: object, path: str) -> None:
        if item is None or isinstance(item, (str, bool, int)):
            return
        if isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError(f"{path} must be strict JSON (NaN and Infinity are forbidden)")
            return
        if isinstance(item, list):
            for index, child in enumerate(item):
                validate(child, f"{path}[{index}]")
            return
        if isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str):
                    raise TypeError(f"{path} object keys must be strings")
                validate(child, f"{path}.{key}")
            return
        raise TypeError(f"{path} contains {type(item).__name__}, which is not a JSON value")

    validate(value, name)
    return json.loads(json.dumps(value, allow_nan=False, ensure_ascii=False, separators=(",", ":")))


def _freeze_json(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


@dataclass(frozen=True)
class ReplyRoute:
    instance_id: str
    source: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "instance_id", _text(self.instance_id, "reply_route.instance_id"))
        object.__setattr__(self, "source", _text(self.source, "reply_route.source"))

    def to_data(self) -> dict[str, str]:
        return {"instance_id": self.instance_id, "source": self.source}

    @classmethod
    def from_data(cls, data: object) -> ReplyRoute:
        data = _exact_object(
            data,
            {"instance_id", "source"},
            "reply_route must be an exact object with instance_id and source",
        )
        return cls(
            instance_id=_text(data["instance_id"], "reply_route.instance_id"),
            source=_text(data["source"], "reply_route.source"),
        )


@dataclass(frozen=True)
class Envelope:
    delivery_id: str
    sender: str
    recipient: str
    source: str
    correlation: str
    payload: Mapping[str, object]
    reply_route: ReplyRoute | None = None

    def __post_init__(self) -> None:
        for name in ("delivery_id", "sender", "recipient", "source", "correlation"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not isinstance(self.payload, dict):
            raise TypeError("payload must be a JSON object")
        payload = _json_copy(self.payload)
        size = len(_canonical(payload))
        if size > MAX_INLINE_PAYLOAD_BYTES:
            raise ValueError(
                f"payload is {size} canonical JSON bytes; inline fabric payloads are limited to "
                f"{MAX_INLINE_PAYLOAD_BYTES} bytes — use the artifact protocol and send a verified artifact reference"
            )
        object.__setattr__(self, "payload", _freeze_json(payload))
        if self.reply_route is not None and not isinstance(self.reply_route, ReplyRoute):
            raise TypeError("reply_route must be ReplyRoute or None")

    @classmethod
    def from_data(cls, data: object) -> Envelope:
        if not isinstance(data, dict) or set(data) != _FIELDS:
            missing = sorted(_FIELDS - set(data)) if isinstance(data, dict) else sorted(_FIELDS)
            unknown = sorted(set(data) - _FIELDS, key=repr) if isinstance(data, dict) else []
            raise ValueError(f"envelope requires exact version-1 fields (missing={missing}, unknown={unknown})")
        data = _exact_object(data, _FIELDS, "envelope requires exact version-1 fields")
        if type(data["version"]) is not int or data["version"] != _VERSION:
            raise ValueError("envelope version must be integer 1")
        route = data["reply_route"]
        payload = _json_object(data["payload"], "payload")
        return cls(
            delivery_id=_text(data["delivery_id"], "delivery_id"),
            sender=_text(data["sender"], "sender"),
            recipient=_text(data["recipient"], "recipient"),
            source=_text(data["source"], "source"),
            correlation=_text(data["correlation"], "correlation"),
            payload=payload,
            reply_route=None if route is None else ReplyRoute.from_data(route),
        )

    def to_data(self) -> dict[str, object]:
        return {
            "version": _VERSION,
            "delivery_id": self.delivery_id,
            "sender": self.sender,
            "recipient": self.recipient,
            "source": self.source,
            "correlation": self.correlation,
            "payload": _thaw_json(self.payload),
            "reply_route": None if self.reply_route is None else self.reply_route.to_data(),
        }

    @property
    def digest(self) -> str:
        return hashlib.sha256(_canonical(self.to_data())).hexdigest()

    @property
    def ingress_identity(self) -> str:
        # Length-prefixing makes the pair injective even when either caller-
        # supplied component contains the separator.
        return f"fabric:{len(self.sender)}:{self.sender}:{self.delivery_id}"


@dataclass(frozen=True)
class Endpoint:
    recipient: str
    source: str
    capabilities: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "recipient", _text(self.recipient, "recipient"))
        object.__setattr__(self, "source", _text(self.source, "source"))
        if not isinstance(self.capabilities, dict):
            raise TypeError("capabilities must be a JSON object")
        object.__setattr__(self, "capabilities", _freeze_json(_json_copy(self.capabilities, "capabilities")))

    def to_data(self) -> dict[str, object]:
        return {
            "recipient": self.recipient,
            "source": self.source,
            "capabilities": _thaw_json(self.capabilities),
        }

    @classmethod
    def from_data(cls, data: object) -> Endpoint:
        data = _thaw_json(data)
        data = _exact_object(
            data,
            {"recipient", "source", "capabilities"},
            "endpoint must be an exact object with recipient, source, and capabilities",
        )
        capabilities = _json_object(data["capabilities"], "capabilities")
        return cls(_text(data["recipient"], "recipient"), _text(data["source"], "source"), capabilities)


@dataclass(frozen=True)
class Submission:
    sender: str
    delivery_id: str
    state: str
    duplicate: bool
    occurrence: int | None = None
    accepted_at: datetime | None = None


@dataclass(frozen=True)
class Receipt:
    sender: str
    delivery_id: str
    recipient: str
    source: str
    digest: str
    state: str
    occurrence: int | None
    accepted_at: datetime | None
    payload_retained: bool
