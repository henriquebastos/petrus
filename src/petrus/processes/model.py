"""Strict, transport-neutral process lifecycle values."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from petrus.fabric.model import (
    Endpoint,
    ReplyRoute,
    _canonical,
    _exact_object,
    _freeze_json,
    _json_copy,
    _json_object,
    _text,
    _thaw_json,
)

_CHILD_VERSION = 1
_SPAWN_FIELDS = frozenset(
    {"version", "parent", "spawn_id", "process_kind", "source", "capabilities", "config", "reply_route"}
)
_OUTCOME_FIELDS = frozenset({"version", "parent", "spawn_id", "child", "endpoint", "prior_claim"})


def child_identity(parent: str, spawn_id: str) -> str:
    """Derive the stable v1 child identity from a parent-scoped spawn identity."""
    parent, spawn_id = _text(parent, "parent"), _text(spawn_id, "spawn_id")
    identity = _canonical({"version": _CHILD_VERSION, "parent": parent, "spawn_id": spawn_id})
    return f"process-v1-{hashlib.sha256(b'impetus-process-child\0' + identity).hexdigest()}"


def _mapping(value: object, name: str) -> Mapping[str, object]:
    value = _json_object(value, name)
    snapshot = _json_object(_json_copy(value, name), name)
    return MappingProxyType({key: _freeze_json(item) for key, item in snapshot.items()})


@dataclass(frozen=True)
class SpawnSpec:
    parent: str
    spawn_id: str
    process_kind: str
    source: str
    capabilities: Mapping[str, object]
    config: Mapping[str, object]
    reply_route: ReplyRoute | None = None

    def __post_init__(self) -> None:
        for name in ("parent", "spawn_id", "process_kind", "source"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        for name in ("capabilities", "config"):
            object.__setattr__(self, name, _mapping(getattr(self, name), name))
        if self.reply_route is not None and not isinstance(self.reply_route, ReplyRoute):
            raise TypeError("reply_route must be ReplyRoute or None")
        if self.reply_route is not None and self.reply_route.instance_id != self.parent:
            raise ValueError("spawn reply_route must belong to the parent process")

    @property
    def child(self) -> str:
        return child_identity(self.parent, self.spawn_id)

    def to_data(self) -> dict[str, object]:
        return {
            "version": _CHILD_VERSION,
            "parent": self.parent,
            "spawn_id": self.spawn_id,
            "process_kind": self.process_kind,
            "source": self.source,
            "capabilities": _thaw_json(self.capabilities),
            "config": _thaw_json(self.config),
            "reply_route": None if self.reply_route is None else self.reply_route.to_data(),
        }

    @classmethod
    def from_data(cls, data: object) -> SpawnSpec:
        data = _exact_object(data, _SPAWN_FIELDS, "spawn spec requires exact version-1 fields")
        if type(data.get("version")) is not int or data["version"] != _CHILD_VERSION:
            raise ValueError("spawn spec requires exact version-1 fields")
        route = data["reply_route"]
        capabilities = _json_object(data["capabilities"], "capabilities")
        config = _json_object(data["config"], "config")
        return cls(
            _text(data["parent"], "parent"),
            _text(data["spawn_id"], "spawn_id"),
            _text(data["process_kind"], "process_kind"),
            _text(data["source"], "source"),
            capabilities,
            config,
            reply_route=None if route is None else ReplyRoute.from_data(route),
        )

    @property
    def digest(self) -> str:
        return hashlib.sha256(_canonical(self.to_data())).hexdigest()


@dataclass(frozen=True)
class Provisioning:
    parent: str
    spawn_id: str
    child: str
    process_kind: str
    endpoint: Endpoint
    config: Mapping[str, object]
    reply_route: ReplyRoute | None = None

    def __post_init__(self) -> None:
        for name in ("parent", "spawn_id", "child", "process_kind"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.child != child_identity(self.parent, self.spawn_id):
            raise ValueError("provisioning child must match its parent-scoped spawn identity")
        if not isinstance(self.endpoint, Endpoint):
            raise TypeError("endpoint must be Endpoint")
        if self.endpoint.recipient != self.child:
            raise ValueError("provisioning endpoint recipient must be the child process")
        if not isinstance(self.config, Mapping):
            raise TypeError("config must be a JSON object")
        object.__setattr__(self, "config", _mapping(_thaw_json(self.config), "config"))
        if self.reply_route is not None and not isinstance(self.reply_route, ReplyRoute):
            raise TypeError("reply_route must be ReplyRoute or None")
        if self.reply_route is not None and self.reply_route.instance_id != self.parent:
            raise ValueError("provisioning reply_route must belong to the parent process")


@dataclass(frozen=True)
class SpawnClaim:
    parent: str
    spawn_id: str
    child: str
    prior_claim: bool

    def __post_init__(self) -> None:
        for name in ("parent", "spawn_id", "child"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.child != child_identity(self.parent, self.spawn_id):
            raise ValueError("spawn claim child must match its parent-scoped spawn identity")
        if type(self.prior_claim) is not bool:
            raise TypeError("prior_claim must be bool")

    @property
    def lineage(self) -> Lineage:
        return Lineage(self.parent, self.spawn_id, self.child)


@dataclass(frozen=True)
class SpawnOutcome:
    parent: str
    spawn_id: str
    child: str
    endpoint: Endpoint
    prior_claim: bool

    def __post_init__(self) -> None:
        for name in ("parent", "spawn_id", "child"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.child != child_identity(self.parent, self.spawn_id):
            raise ValueError("spawn outcome child must match its parent-scoped spawn identity")
        if not isinstance(self.endpoint, Endpoint) or self.endpoint.recipient != self.child:
            raise ValueError("spawn outcome endpoint must address the child process")
        if type(self.prior_claim) is not bool:
            raise TypeError("prior_claim must be bool")

    def to_data(self) -> dict[str, object]:
        return {
            "version": 1,
            "parent": self.parent,
            "spawn_id": self.spawn_id,
            "child": self.child,
            "endpoint": self.endpoint.to_data(),
            "prior_claim": self.prior_claim,
        }

    @classmethod
    def from_data(cls, data: object) -> SpawnOutcome:
        data = _exact_object(data, _OUTCOME_FIELDS, "spawn outcome requires exact version-1 fields")
        if type(data.get("version")) is not int or data["version"] != 1:
            raise ValueError("spawn outcome requires exact version-1 fields")
        prior_claim = data["prior_claim"]
        if type(prior_claim) is not bool:
            raise TypeError("prior_claim must be bool")
        return cls(
            _text(data["parent"], "parent"),
            _text(data["spawn_id"], "spawn_id"),
            _text(data["child"], "child"),
            Endpoint.from_data(data["endpoint"]),
            prior_claim,
        )


@dataclass(frozen=True)
class Lineage:
    parent: str
    spawn_id: str
    child: str

    def __post_init__(self) -> None:
        for name in ("parent", "spawn_id", "child"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.child != child_identity(self.parent, self.spawn_id):
            raise ValueError("lineage child must match its parent-scoped spawn identity")
