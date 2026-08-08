"""Provider-neutral, secret-free Agent Runtime installation probe facts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from petrus.agenticus.catalog.descriptor import DescriptorIdentity, DescriptorKind

_MAX_TEXT_BYTES = 256
_CAPABILITY = re.compile(r"[a-z][a-z0-9.-]{0,127}")


def _text(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value.encode()) > _MAX_TEXT_BYTES
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError(f"{name} must be a bounded non-empty text value")
    return value


def _runtime_identity(value: object) -> DescriptorIdentity:
    if not isinstance(value, DescriptorIdentity) or value.kind is not DescriptorKind.RUNTIME:
        raise TypeError("runtime installation identity must be a runtime DescriptorIdentity")
    return value


def _capability(value: object, name: str) -> str:
    if not isinstance(value, str) or _CAPABILITY.fullmatch(value) is None:
        raise ValueError(f"{name} must be a bounded lowercase capability token")
    return value


class ProbeDisposition(StrEnum):
    """The safe pre-materialization result of probing one exact runtime profile."""

    READY = "ready"
    NOT_INSTALLED = "not-installed"
    INCOMPATIBLE = "incompatible"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, order=True)
class InstalledComponent:
    """One observed package/client pin without an executable or home path."""

    name: str
    version: str
    source_identity: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _text(self.name, "installed component name"))
        object.__setattr__(self, "version", _text(self.version, "installed component version"))
        object.__setattr__(
            self,
            "source_identity",
            _text(self.source_identity, "installed component source identity"),
        )


@dataclass(frozen=True, order=True)
class ProbeIssue:
    """A machine-safe probe issue; raw command or provider diagnostics stay private."""

    code: str
    component: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _capability(self.code, "probe issue code"))
        if self.component is not None:
            object.__setattr__(self, "component", _text(self.component, "probe issue component"))


@dataclass(frozen=True)
class RuntimeInstallation:
    """Exact qualified installation facts, with no authority, content, or path fields."""

    runtime: DescriptorIdentity
    adapter_contract_version: int
    components: tuple[InstalledComponent, ...]
    platform: str
    architecture: str
    capabilities: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        _runtime_identity(self.runtime)
        if type(self.adapter_contract_version) is not int or self.adapter_contract_version <= 0:
            raise ValueError("runtime adapter contract version must be a positive integer")
        components = tuple(self.components)
        if not components or any(not isinstance(component, InstalledComponent) for component in components):
            raise TypeError("runtime installation components must contain InstalledComponent values")
        if len({component.name for component in components}) != len(components):
            raise ValueError("runtime installation component names must be unique")
        object.__setattr__(self, "components", tuple(sorted(components)))
        object.__setattr__(self, "platform", _text(self.platform, "runtime installation platform"))
        object.__setattr__(self, "architecture", _text(self.architecture, "runtime installation architecture"))
        capabilities = frozenset(
            _capability(capability, "runtime installation capability") for capability in self.capabilities
        )
        object.__setattr__(self, "capabilities", capabilities)


def _validate_probe_shape(
    disposition: ProbeDisposition,
    installation: RuntimeInstallation | None,
    issues: tuple[ProbeIssue, ...],
) -> None:
    if disposition is ProbeDisposition.READY and (installation is None or issues):
        raise ValueError("a ready runtime probe requires an installation and no issues")
    if disposition is ProbeDisposition.INCOMPATIBLE and (installation is None or not issues):
        raise ValueError("an incompatible runtime probe requires observed installation facts and issues")
    if disposition is ProbeDisposition.NOT_INSTALLED and (installation is not None or not issues):
        raise ValueError("a not-installed runtime probe requires issues and no installation")
    if disposition is ProbeDisposition.UNAVAILABLE and not issues:
        raise ValueError("an unavailable runtime probe requires issues")


@dataclass(frozen=True)
class RuntimeProbeResult:
    """One strict probe verdict produced before Agent Connection materialization."""

    runtime: DescriptorIdentity
    disposition: ProbeDisposition
    installation: RuntimeInstallation | None = None
    issues: tuple[ProbeIssue, ...] = ()

    def __post_init__(self) -> None:
        _runtime_identity(self.runtime)
        if not isinstance(self.disposition, ProbeDisposition):
            raise TypeError("runtime probe disposition must be ProbeDisposition")
        issues = tuple(self.issues)
        if any(not isinstance(issue, ProbeIssue) for issue in issues):
            raise TypeError("runtime probe issues must contain ProbeIssue values")
        if len(set(issues)) != len(issues):
            raise ValueError("runtime probe issues must be unique")
        object.__setattr__(self, "issues", tuple(sorted(issues)))
        _validate_probe_shape(self.disposition, self.installation, issues)
        if self.installation is not None and self.installation.runtime != self.runtime:
            raise ValueError("runtime probe and installation identities must match exactly")
