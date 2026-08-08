"""Provider-neutral component identities and capability descriptors."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

_SCHEMA_VERSION = 1
_MAX_TEXT_BYTES = 256


def _text(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value.encode()) > _MAX_TEXT_BYTES
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError(f"{name} must be a non-empty, trimmed string of at most {_MAX_TEXT_BYTES} UTF-8 bytes")
    return value


def _positive_integer(value: object, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _exact_object(value: object, fields: set[str], message: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError(message)
    result: dict[str, object] = {key: item for key, item in value.items() if isinstance(key, str)}
    if set(result) != fields:
        raise ValueError(message)
    return result


def _capabilities(value: Iterable[object], name: str) -> frozenset[str]:
    if isinstance(value, str):
        raise TypeError(f"{name} must be an iterable of capability keys, not one string")
    items = tuple(value)
    capabilities = tuple(_text(item, f"{name} item") for item in items)
    if len(set(capabilities)) != len(capabilities):
        raise ValueError(f"{name} must not contain duplicate capability keys")
    return frozenset(capabilities)


class DescriptorKind(StrEnum):
    """The exact component kinds a host may register with Catalog."""

    CONNECTION = "connection"
    PROGRAM = "program"
    RUNTIME = "runtime"
    HANDS = "hands"
    TERRITORY = "territory"
    CONTINUATION = "continuation"
    EFFECT = "effect"


@dataclass(frozen=True, order=True)
class DescriptorIdentity:
    """Stable identity and contract version for one registered component."""

    kind: DescriptorKind
    name: str
    contract_version: int

    def __post_init__(self) -> None:
        if not isinstance(self.kind, DescriptorKind):
            raise TypeError("descriptor kind must be DescriptorKind")
        object.__setattr__(self, "name", _text(self.name, "descriptor name"))
        object.__setattr__(
            self,
            "contract_version",
            _positive_integer(self.contract_version, "descriptor contract_version"),
        )

    def to_data(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "name": self.name,
            "contract_version": self.contract_version,
        }

    @classmethod
    def from_data(cls, data: object) -> DescriptorIdentity:
        data = _exact_object(
            data,
            {"kind", "name", "contract_version"},
            "descriptor identity requires exact kind, name, and contract_version fields",
        )
        try:
            kind = DescriptorKind(data["kind"])
        except (TypeError, ValueError) as error:
            raise ValueError("descriptor identity kind is not supported") from error
        return cls(
            kind=kind,
            name=_text(data["name"], "descriptor name"),
            contract_version=_positive_integer(data["contract_version"], "descriptor contract_version"),
        )


@dataclass(frozen=True)
class CompatibilityRequirement:
    """One exact-kind requirement with opaque capability keys."""

    kind: DescriptorKind
    name: str | None
    contract_version: int
    capabilities: frozenset[str]

    def __post_init__(self) -> None:
        if not isinstance(self.kind, DescriptorKind):
            raise TypeError("requirement kind must be DescriptorKind")
        if self.name is not None:
            object.__setattr__(self, "name", _text(self.name, "requirement name"))
        object.__setattr__(
            self,
            "contract_version",
            _positive_integer(self.contract_version, "requirement contract_version"),
        )
        object.__setattr__(self, "capabilities", _capabilities(self.capabilities, "requirement capabilities"))

    def to_data(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "name": self.name,
            "contract_version": self.contract_version,
            "capabilities": sorted(self.capabilities),
        }

    @classmethod
    def from_data(cls, data: object) -> CompatibilityRequirement:
        data = _exact_object(
            data,
            {"kind", "name", "contract_version", "capabilities"},
            "compatibility requirement requires exact kind, name, contract_version, and capabilities fields",
        )
        name = data["name"]
        if name is not None:
            name = _text(name, "requirement name")
        capabilities = data["capabilities"]
        if not isinstance(capabilities, list):
            raise TypeError("requirement capabilities must be a JSON array")
        try:
            kind = DescriptorKind(data["kind"])
        except (TypeError, ValueError) as error:
            raise ValueError("requirement kind is not supported") from error
        return cls(
            kind=kind,
            name=name,
            contract_version=_positive_integer(data["contract_version"], "requirement contract_version"),
            capabilities=_capabilities(capabilities, "requirement capabilities"),
        )


@dataclass(frozen=True)
class CapabilityDescriptor:
    """One registration envelope with opaque offers and typed requirements."""

    identity: DescriptorIdentity
    offers: frozenset[str]
    requires: tuple[CompatibilityRequirement, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.identity, DescriptorIdentity):
            raise TypeError("descriptor identity must be DescriptorIdentity")
        object.__setattr__(self, "offers", _capabilities(self.offers, "descriptor offers"))
        requirements = tuple(self.requires)
        if any(not isinstance(requirement, CompatibilityRequirement) for requirement in requirements):
            raise TypeError("descriptor requires must contain CompatibilityRequirement values")
        if len(set(requirements)) != len(requirements):
            raise ValueError("descriptor requires must not contain duplicate requirements")
        object.__setattr__(self, "requires", tuple(sorted(requirements, key=_requirement_key)))

    def to_data(self) -> dict[str, object]:
        return {
            "schema_version": _SCHEMA_VERSION,
            "identity": self.identity.to_data(),
            "offers": sorted(self.offers),
            "requires": [requirement.to_data() for requirement in self.requires],
        }

    @classmethod
    def from_data(cls, data: object) -> CapabilityDescriptor:
        data = _exact_object(
            data,
            {"schema_version", "identity", "offers", "requires"},
            "capability descriptor requires exact schema_version, identity, offers, and requires fields",
        )
        if type(data["schema_version"]) is not int or data["schema_version"] != _SCHEMA_VERSION:
            raise ValueError(f"capability descriptor schema_version must be integer {_SCHEMA_VERSION}")
        offers, requires = data["offers"], data["requires"]
        if not isinstance(offers, list) or not isinstance(requires, list):
            raise TypeError("capability descriptor offers and requires must be JSON arrays")
        return cls(
            identity=DescriptorIdentity.from_data(data["identity"]),
            offers=_capabilities(offers, "descriptor offers"),
            requires=tuple(CompatibilityRequirement.from_data(requirement) for requirement in requires),
        )


def _requirement_key(requirement: CompatibilityRequirement) -> tuple[str, str, int, tuple[str, ...]]:
    return (
        requirement.kind.value,
        requirement.name or "",
        requirement.contract_version,
        tuple(sorted(requirement.capabilities)),
    )
