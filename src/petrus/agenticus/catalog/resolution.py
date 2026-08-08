"""Host-local registration and deterministic Agenticus compatibility resolution."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from threading import RLock

from petrus.agenticus.catalog.descriptor import (
    CapabilityDescriptor,
    CompatibilityRequirement,
    DescriptorIdentity,
    DescriptorKind,
    _exact_object,
)
from petrus.agenticus.catalog.result import CompatibilityIssue, CompatibilityResult

_SNAPSHOT_SCHEMA_VERSION = 1


class CompatibilityIssueCode(StrEnum):
    """The complete incompatibility vocabulary emitted by ``Catalog``."""

    NOT_REGISTERED = "not-registered"
    NOT_ENABLED = "not-enabled"
    MISSING_SELECTION = "missing-selection"
    SELECTION_NOT_REGISTERED = "selection-not-registered"
    SELECTION_NOT_ENABLED = "selection-not-enabled"
    NAME_MISMATCH = "name-mismatch"
    VERSION_MISMATCH = "version-mismatch"
    MISSING_CAPABILITY = "missing-capability"


class CatalogRegistrationError(ValueError):
    """Base class for registration identity conflicts."""


class DuplicateRegistrationError(CatalogRegistrationError):
    """The exact descriptor is already registered."""


class AmbiguousRegistrationError(CatalogRegistrationError):
    """A registration conflicts by identity or cannot fit one per-kind selection."""


class UnknownRegistrationError(LookupError):
    """An enablement operation named an unregistered exact identity."""


class SelectionError(ValueError):
    """Base class for non-canonical resolution selections."""


class DuplicateSelectionError(SelectionError):
    """One exact identity was selected more than once."""


class AmbiguousSelectionError(SelectionError):
    """More than one identity was selected for one component kind."""


@dataclass(frozen=True)
class CatalogEntry:
    """One immutable inspection view of a host registration."""

    descriptor: CapabilityDescriptor
    enabled: bool

    def __post_init__(self) -> None:
        if not isinstance(self.descriptor, CapabilityDescriptor):
            raise TypeError("catalog entry descriptor must be CapabilityDescriptor")
        if type(self.enabled) is not bool:
            raise TypeError("catalog entry enabled must be bool")


@dataclass(frozen=True)
class ResolutionRequest:
    """Exact component selections for one prospective Episode.

    A request selects at most one exact identity of each kind and always names
    its runtime. Catalog validates that plan; it never searches for a more
    convenient provider, account, runtime, territory, or Continuation.
    """

    selections: tuple[DescriptorIdentity, ...]

    def __post_init__(self) -> None:
        selections = tuple(self.selections)
        if any(not isinstance(selection, DescriptorIdentity) for selection in selections):
            raise TypeError("resolution selections must contain DescriptorIdentity values")
        if len(set(selections)) != len(selections):
            raise DuplicateSelectionError("resolution selections must not contain a duplicate exact identity")
        kinds = [selection.kind for selection in selections]
        if len(set(kinds)) != len(kinds):
            raise AmbiguousSelectionError("resolution selections must contain at most one identity of each kind")
        if DescriptorKind.RUNTIME not in kinds:
            raise SelectionError("resolution selections must contain one exact runtime identity")
        object.__setattr__(self, "selections", tuple(sorted(selections, key=_identity_key)))


@dataclass(frozen=True)
class ResolutionSnapshot:
    """The immutable, portable descriptor plan captured for one resolved Episode."""

    catalog_revision: int
    descriptors: tuple[CapabilityDescriptor, ...]

    def __post_init__(self) -> None:
        if type(self.catalog_revision) is not int or self.catalog_revision < 0:
            raise ValueError("resolution catalog_revision must be a non-negative integer")
        descriptors = tuple(self.descriptors)
        if any(not isinstance(descriptor, CapabilityDescriptor) for descriptor in descriptors):
            raise TypeError("resolution snapshot must contain CapabilityDescriptor values")
        identities = [descriptor.identity for descriptor in descriptors]
        if len(set(identities)) != len(identities):
            raise ValueError("resolution snapshot must not contain duplicate descriptor identities")
        kinds = [identity.kind for identity in identities]
        if len(set(kinds)) != len(kinds):
            raise ValueError("resolution snapshot must contain at most one descriptor of each kind")
        if DescriptorKind.RUNTIME not in kinds:
            raise ValueError("resolution snapshot must contain one runtime descriptor")
        object.__setattr__(
            self, "descriptors", tuple(sorted(descriptors, key=lambda item: _identity_key(item.identity)))
        )

    def descriptor(self, kind: DescriptorKind) -> CapabilityDescriptor | None:
        """Return the selected descriptor of ``kind``, if the Episode has one."""

        if not isinstance(kind, DescriptorKind):
            raise TypeError("snapshot descriptor kind must be DescriptorKind")
        return next((descriptor for descriptor in self.descriptors if descriptor.identity.kind is kind), None)

    def to_data(self) -> dict[str, object]:
        return {
            "schema_version": _SNAPSHOT_SCHEMA_VERSION,
            "catalog_revision": self.catalog_revision,
            "descriptors": [descriptor.to_data() for descriptor in self.descriptors],
        }

    @classmethod
    def from_data(cls, data: object) -> ResolutionSnapshot:
        data = _exact_object(
            data,
            {"schema_version", "catalog_revision", "descriptors"},
            "resolution snapshot requires exact schema_version, catalog_revision, and descriptors fields",
        )
        if type(data["schema_version"]) is not int or data["schema_version"] != _SNAPSHOT_SCHEMA_VERSION:
            raise ValueError(f"resolution snapshot schema_version must be integer {_SNAPSHOT_SCHEMA_VERSION}")
        revision, descriptors = data["catalog_revision"], data["descriptors"]
        if type(revision) is not int or revision < 0:
            raise ValueError("resolution snapshot catalog_revision must be a non-negative integer")
        if not isinstance(descriptors, list):
            raise TypeError("resolution snapshot descriptors must be a JSON array")
        return cls(
            catalog_revision=revision,
            descriptors=tuple(CapabilityDescriptor.from_data(descriptor) for descriptor in descriptors),
        )


@dataclass(frozen=True)
class Resolution:
    """One deterministic plan or its complete candidate-local incompatibilities."""

    request: ResolutionRequest
    results: tuple[CompatibilityResult, ...]
    snapshot: ResolutionSnapshot | None

    def __post_init__(self) -> None:
        if not isinstance(self.request, ResolutionRequest):
            raise TypeError("resolution request must be ResolutionRequest")
        results = tuple(self.results)
        if any(not isinstance(result, CompatibilityResult) for result in results):
            raise TypeError("resolution results must contain CompatibilityResult values")
        candidates = tuple(result.candidate for result in results)
        if candidates != self.request.selections:
            raise ValueError("resolution results must align exactly with the requested selections")
        blocked = any(result.issues for result in results)
        if blocked == (self.snapshot is not None):
            raise ValueError("resolution snapshot must exist exactly when every candidate is compatible")
        if self.snapshot is not None and not isinstance(self.snapshot, ResolutionSnapshot):
            raise TypeError("resolution snapshot must be ResolutionSnapshot or None")
        object.__setattr__(self, "results", results)

    @property
    def compatible(self) -> bool:
        return self.snapshot is not None

    @property
    def incompatibilities(self) -> tuple[CompatibilityResult, ...]:
        return tuple(result for result in self.results if result.issues)


class Catalog:
    """A mutable host-local registry whose successful resolutions are immutable.

    Registration never enables a descriptor. Hosts must enable each exact
    identity as a separate policy act before it can participate in a plan.
    """

    def __init__(self) -> None:
        self._entries: dict[DescriptorIdentity, CatalogEntry] = {}
        self._revision = 0
        self._lock = RLock()

    @property
    def revision(self) -> int:
        with self._lock:
            return self._revision

    def register(self, descriptor: CapabilityDescriptor) -> None:
        """Register one disabled descriptor, refusing duplicate or conflicting identity."""

        if not isinstance(descriptor, CapabilityDescriptor):
            raise TypeError("catalog registration must be a CapabilityDescriptor")
        _refuse_impossible_requirements(descriptor)
        with self._lock:
            existing = self._entries.get(descriptor.identity)
            if existing is not None:
                if existing.descriptor == descriptor:
                    raise DuplicateRegistrationError(f"descriptor is already registered: {descriptor.identity.name}")
                raise AmbiguousRegistrationError(
                    f"descriptor identity has conflicting registration envelopes: {descriptor.identity.name}"
                )
            self._entries[descriptor.identity] = CatalogEntry(descriptor, enabled=False)
            self._revision += 1

    def enable(self, identity: DescriptorIdentity) -> None:
        """Explicitly enable one exact registered identity."""

        with self._lock:
            entry = self._entry(identity)
            if not entry.enabled:
                self._entries[identity] = CatalogEntry(entry.descriptor, enabled=True)
                self._revision += 1

    def disable(self, identity: DescriptorIdentity) -> None:
        """Disable one exact registered identity without changing prior snapshots."""

        with self._lock:
            entry = self._entry(identity)
            if entry.enabled:
                self._entries[identity] = CatalogEntry(entry.descriptor, enabled=False)
                self._revision += 1

    def inspect(self) -> tuple[CatalogEntry, ...]:
        """Return a deterministic immutable view without importing adapters."""

        with self._lock:
            return tuple(self._entries[identity] for identity in sorted(self._entries, key=_identity_key))

    def resolve(self, request: ResolutionRequest) -> Resolution:
        """Validate exactly ``request`` and return every incompatibility found."""

        if not isinstance(request, ResolutionRequest):
            raise TypeError("catalog resolve requires ResolutionRequest")
        with self._lock:
            entries = dict(self._entries)
            revision = self._revision
        selections = {identity.kind: identity for identity in request.selections}
        results = tuple(_check_candidate(identity, selections, entries) for identity in request.selections)
        snapshot = None
        if all(result.compatible for result in results):
            snapshot = ResolutionSnapshot(
                catalog_revision=revision,
                descriptors=tuple(entries[identity].descriptor for identity in request.selections),
            )
        return Resolution(request=request, results=results, snapshot=snapshot)

    def _entry(self, identity: DescriptorIdentity) -> CatalogEntry:
        if not isinstance(identity, DescriptorIdentity):
            raise TypeError("catalog identity must be DescriptorIdentity")
        try:
            return self._entries[identity]
        except KeyError as error:
            raise UnknownRegistrationError(f"descriptor is not registered: {identity.name}") from error


def _identity_key(identity: DescriptorIdentity) -> tuple[str, str, int]:
    return identity.kind.value, identity.name, identity.contract_version


def _issue(code: CompatibilityIssueCode, subject: str) -> CompatibilityIssue:
    return CompatibilityIssue(code.value, subject)


def _refuse_impossible_requirements(descriptor: CapabilityDescriptor) -> None:
    """Reject constraints that one exact per-kind selection cannot satisfy."""

    for kind in DescriptorKind:
        requirements = tuple(requirement for requirement in descriptor.requires if requirement.kind is kind)
        if len({requirement.contract_version for requirement in requirements}) > 1:
            raise AmbiguousRegistrationError(
                f"descriptor has conflicting {kind.value} requirement contract versions: {descriptor.identity.name}"
            )
        names = {requirement.name for requirement in requirements if requirement.name is not None}
        if len(names) > 1:
            raise AmbiguousRegistrationError(
                f"descriptor has conflicting {kind.value} requirement names: {descriptor.identity.name}"
            )


def _check_candidate(
    identity: DescriptorIdentity,
    selections: dict[DescriptorKind, DescriptorIdentity],
    entries: dict[DescriptorIdentity, CatalogEntry],
) -> CompatibilityResult:
    entry = entries.get(identity)
    issues: set[CompatibilityIssue] = set()
    if entry is None:
        issues.add(_issue(CompatibilityIssueCode.NOT_REGISTERED, identity.name))
    else:
        if not entry.enabled:
            issues.add(_issue(CompatibilityIssueCode.NOT_ENABLED, identity.name))
        for requirement in entry.descriptor.requires:
            issues.update(_requirement_issues(requirement, selections, entries))
    return CompatibilityResult(candidate=identity, issues=tuple(issues))


def _requirement_issues(
    requirement: CompatibilityRequirement,
    selections: dict[DescriptorKind, DescriptorIdentity],
    entries: dict[DescriptorIdentity, CatalogEntry],
) -> set[CompatibilityIssue]:
    selected = selections.get(requirement.kind)
    if selected is None:
        return {_issue(CompatibilityIssueCode.MISSING_SELECTION, requirement.kind.value)}

    issues: set[CompatibilityIssue] = set()
    if requirement.name is not None and selected.name != requirement.name:
        issues.add(_issue(CompatibilityIssueCode.NAME_MISMATCH, requirement.name))
    if selected.contract_version != requirement.contract_version:
        issues.add(
            _issue(
                CompatibilityIssueCode.VERSION_MISMATCH,
                f"{requirement.kind.value}@{requirement.contract_version}",
            )
        )

    entry = entries.get(selected)
    if entry is None:
        issues.add(_issue(CompatibilityIssueCode.SELECTION_NOT_REGISTERED, selected.name))
        return issues
    if not entry.enabled:
        issues.add(_issue(CompatibilityIssueCode.SELECTION_NOT_ENABLED, selected.name))
    for capability in requirement.capabilities - entry.descriptor.offers:
        issues.add(_issue(CompatibilityIssueCode.MISSING_CAPABILITY, capability))
    return issues
