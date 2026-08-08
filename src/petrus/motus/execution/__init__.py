"""Supported provider-neutral execution-territory contract.

Motus owns temporary execution territories without assigning agent, Thread,
Episode, Activity, or canonical-History meaning to them. Concrete providers
live in explicit sibling modules and may offer different capability keys.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Protocol, runtime_checkable

_ENVIRONMENT_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_PRIVATE_FILE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*", re.ASCII)
MAX_COMMAND_OUTPUT_BYTES = 1_000_000
MAX_PRIVATE_FILE_BYTES = 1_000_000
MAX_PRIVATE_FILE_NAME_BYTES = 64
MAX_PRIVATE_FILES_PER_ATTACHMENT = 16
MAX_PRIVATE_FILE_TOTAL_BYTES = 4_000_000


class EnvironmentCapability(StrEnum):
    """Shared capability keys; providers may additionally advertise extensions."""

    COMMAND_CANCELLATION = "command-cancellation"
    CONTAINER = "container"
    EXPLICIT_ENVIRONMENT = "explicit-environment"
    MICROVM = "microvm"
    PRIVATE_FILE_TRANSFER = "private-file-transfer"
    PROCESS_GROUP = "process-group"
    RECREATABLE_LOOKUP = "recreatable-lookup"
    TERRITORY_CANCELLATION = "territory-cancellation"
    VM = "vm"
    WORKSPACE = "workspace"


class LeaseState(StrEnum):
    """Provider-observed state of one territory lease."""

    READY = "ready"
    TERMINAL = "terminal"
    UNCERTAIN = "uncertain"


class ReconcileClass(StrEnum):
    """Whether an operation is terminal, safe to retry, or still uncertain."""

    TERMINAL = "terminal"
    RETRYABLE = "retryable"
    UNCERTAIN = "uncertain"


class CleanupDisposition(StrEnum):
    """Independently consumable result of one identity-correlated destroy attempt."""

    CLEAN = "clean"
    NOT_CREATED = "not-created"
    UNVERIFIED = "unverified"


def _text(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError(f"{name} must be a non-empty trimmed string without control characters")
    return value


def _capabilities(value: object) -> frozenset[str]:
    if isinstance(value, str):
        raise TypeError("environment capabilities must be an iterable of keys, not one string")
    if not isinstance(value, Iterable):
        raise TypeError("environment capabilities must be an iterable of keys") from None
    items = tuple(value)
    return frozenset(_text(capability, "environment capability") for capability in items)


@dataclass(frozen=True)
class EnvironmentSpec:
    """Provider-neutral creation request and required capability constraints."""

    image: str | None = None
    required_capabilities: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if self.image is not None:
            object.__setattr__(self, "image", _text(self.image, "environment image"))
        object.__setattr__(self, "required_capabilities", _capabilities(self.required_capabilities))


@dataclass(frozen=True)
class LeaseIdentity:
    """Stable provider identity for one temporary territory lease."""

    operation_id: str
    provider: str
    lease_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "operation_id", _text(self.operation_id, "lease operation_id"))
        object.__setattr__(self, "provider", _text(self.provider, "lease provider"))
        object.__setattr__(self, "lease_id", _text(self.lease_id, "lease lease_id"))


@dataclass(frozen=True)
class EnvironmentLease:
    """Detached provider lease fact; state may change while identity remains stable."""

    operation_id: str
    provider: str
    lease_id: str
    capabilities: frozenset[str]
    state: LeaseState

    def __post_init__(self) -> None:
        identity = LeaseIdentity(self.operation_id, self.provider, self.lease_id)
        object.__setattr__(self, "operation_id", identity.operation_id)
        object.__setattr__(self, "provider", identity.provider)
        object.__setattr__(self, "lease_id", identity.lease_id)
        object.__setattr__(self, "capabilities", _capabilities(self.capabilities))
        if not isinstance(self.state, LeaseState):
            raise TypeError("environment lease state must be LeaseState")

    @property
    def identity(self) -> LeaseIdentity:
        return LeaseIdentity(self.operation_id, self.provider, self.lease_id)


@dataclass(frozen=True)
class ExecutionAttachment:
    """One workspace/archive binding to a current territory lease."""

    attachment_id: str
    lease: EnvironmentLease
    input_digest: str
    workspace: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "attachment_id", _text(self.attachment_id, "attachment_id"))
        if not isinstance(self.lease, EnvironmentLease):
            raise TypeError("execution attachment lease must be EnvironmentLease")
        object.__setattr__(self, "input_digest", _text(self.input_digest, "attachment input_digest"))
        if not isinstance(self.workspace, Path):
            raise TypeError("execution attachment workspace must be pathlib.Path")


@dataclass(frozen=True)
class Command:
    """One bounded command with an optional timeout and currency cancellation check."""

    argv: tuple[str, ...]
    cwd: Path = Path(".")
    environment: Mapping[str, str] = field(default_factory=dict)
    timeout: float | None = None
    output_limit: int = MAX_COMMAND_OUTPUT_BYTES
    is_current: Callable[[], bool] | None = field(default=None, compare=False, repr=False)
    private_roots: Mapping[str, PrivateFileRef] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if isinstance(self.argv, str):
            raise TypeError("command argv must be an iterable of arguments, not one string")
        argv = tuple(self.argv)
        cwd = Path(self.cwd)
        timeout_valid = self.timeout is None or (
            not isinstance(self.timeout, bool)
            and isinstance(self.timeout, int | float)
            and math.isfinite(self.timeout)
            and self.timeout > 0
        )
        output_valid = (
            not isinstance(self.output_limit, bool)
            and isinstance(self.output_limit, int)
            and 0 <= self.output_limit <= MAX_COMMAND_OUTPUT_BYTES
        )
        if not argv or cwd.is_absolute() or not timeout_valid or not output_valid:
            raise ValueError(
                "command requires argv, a relative cwd, a positive finite timeout, and an output limit "
                f"between 0 and {MAX_COMMAND_OUTPUT_BYTES} bytes"
            )
        environment = dict(self.environment)
        private_roots = dict(self.private_roots)
        if any(not isinstance(part, str) or "\x00" in part for part in argv) or any(
            not isinstance(key, str)
            or not isinstance(value, str)
            or _ENVIRONMENT_NAME.fullmatch(key) is None
            or "\x00" in key
            or "\x00" in value
            for key, value in environment.items()
        ):
            raise ValueError("invalid command or environment value")
        if len(private_roots) > MAX_PRIVATE_FILES_PER_ATTACHMENT or any(
            not isinstance(key, str)
            or _ENVIRONMENT_NAME.fullmatch(key) is None
            or key in environment
            or not isinstance(reference, PrivateFileRef)
            for key, reference in private_roots.items()
        ):
            raise ValueError("invalid command private root binding")
        if self.is_current is not None and not callable(self.is_current):
            raise TypeError("command is_current must be callable or None")
        object.__setattr__(self, "argv", argv)
        object.__setattr__(self, "cwd", cwd)
        object.__setattr__(self, "environment", MappingProxyType(environment))
        object.__setattr__(self, "private_roots", MappingProxyType(private_roots))


@dataclass(frozen=True)
class ExecutionProvenance:
    """Lease correlation attached to one command result."""

    operation_id: str
    provider: str
    lease_id: str

    def __post_init__(self) -> None:
        identity = LeaseIdentity(self.operation_id, self.provider, self.lease_id)
        object.__setattr__(self, "operation_id", identity.operation_id)
        object.__setattr__(self, "provider", identity.provider)
        object.__setattr__(self, "lease_id", identity.lease_id)

    @property
    def identity(self) -> LeaseIdentity:
        return LeaseIdentity(self.operation_id, self.provider, self.lease_id)


def _private_file_name(value: object) -> str:
    if (
        not isinstance(value, str)
        or value in (".", "..")
        or len(value.encode("ascii", errors="ignore")) != len(value)
        or len(value.encode()) > MAX_PRIVATE_FILE_NAME_BYTES
        or _PRIVATE_FILE_NAME.fullmatch(value) is None
    ):
        raise ValueError("private file name must be one bounded safe ASCII filename component")
    return value


@dataclass(frozen=True)
class PrivateFile:
    """One bounded opaque file entering or leaving provider-private custody."""

    name: str
    content: bytes = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _private_file_name(self.name))
        if not isinstance(self.content, bytes):
            raise TypeError("private file content must be bytes")
        if len(self.content) > MAX_PRIVATE_FILE_BYTES:
            raise ValueError(f"private file content exceeds the {MAX_PRIVATE_FILE_BYTES}-byte bound")


@dataclass(frozen=True)
class PrivateFileRef:
    """Path-free reference to one file under an exact territory attachment."""

    file_id: str
    name: str
    attachment_id: str
    provenance: ExecutionProvenance

    def __post_init__(self) -> None:
        object.__setattr__(self, "file_id", _text(self.file_id, "private file_id"))
        object.__setattr__(self, "name", _private_file_name(self.name))
        object.__setattr__(self, "attachment_id", _text(self.attachment_id, "private file attachment_id"))
        if not isinstance(self.provenance, ExecutionProvenance):
            raise TypeError("private file provenance must be ExecutionProvenance")


@dataclass(frozen=True)
class PrivateFileCleanupResult:
    """Path-free, independently consumable cleanup evidence for private files."""

    attachment_id: str
    provenance: ExecutionProvenance
    disposition: CleanupDisposition
    removed: int = 0
    detail: str = ""
    physical_erasure_guaranteed: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "attachment_id", _text(self.attachment_id, "private cleanup attachment_id"))
        if not isinstance(self.provenance, ExecutionProvenance):
            raise TypeError("private cleanup provenance must be ExecutionProvenance")
        if not isinstance(self.disposition, CleanupDisposition):
            raise TypeError("private cleanup disposition must be CleanupDisposition")
        if isinstance(self.removed, bool) or not isinstance(self.removed, int) or self.removed < 0:
            raise ValueError("private cleanup removed count must be a non-negative integer")
        if not isinstance(self.detail, str):
            raise TypeError("private cleanup detail must be a string")
        if type(self.physical_erasure_guaranteed) is not bool:
            raise TypeError("private cleanup physical erasure field must be a boolean")

    @property
    def verified(self) -> bool:
        """Whether cleanup may pass a fail-closed private-custody gate."""

        return self.disposition in (CleanupDisposition.CLEAN, CleanupDisposition.NOT_CREATED)


@dataclass(frozen=True)
class CommandResult:
    """Bounded process result correlated to the territory that produced it."""

    returncode: int
    stdout: bytes
    stderr: bytes
    timed_out: bool
    superseded: bool
    output_truncated: bool
    provenance: ExecutionProvenance

    def __post_init__(self) -> None:
        if isinstance(self.returncode, bool) or not isinstance(self.returncode, int):
            raise TypeError("command result returncode must be an integer")
        if not isinstance(self.stdout, bytes) or not isinstance(self.stderr, bytes):
            raise TypeError("command result stdout and stderr must be bytes")
        if any(type(value) is not bool for value in (self.timed_out, self.superseded, self.output_truncated)):
            raise TypeError("command result status fields must be booleans")
        if not isinstance(self.provenance, ExecutionProvenance):
            raise TypeError("command result provenance must be ExecutionProvenance")
        if len(self.stdout) + len(self.stderr) > MAX_COMMAND_OUTPUT_BYTES:
            raise ValueError("command result exceeds the supported output bound")


@dataclass(frozen=True)
class ReconcileResult:
    """Lookup-first recovery classification for one stable operation identity."""

    classification: ReconcileClass
    lease: EnvironmentLease | None = None
    detail: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.classification, ReconcileClass):
            raise TypeError("reconcile classification must be ReconcileClass")
        if self.lease is not None and not isinstance(self.lease, EnvironmentLease):
            raise TypeError("reconcile lease must be EnvironmentLease or None")
        if not isinstance(self.detail, str):
            raise TypeError("reconcile detail must be a string")
        if self.classification is ReconcileClass.TERMINAL and self.lease is None:
            raise ValueError("terminal reconciliation requires the observed lease")
        if self.classification is ReconcileClass.RETRYABLE and self.lease is not None:
            raise ValueError("retryable reconciliation cannot retain a provider lease")


@dataclass(frozen=True)
class CleanupResult:
    """Fail-closed destruction evidence for one exact lease identity."""

    identity: LeaseIdentity
    disposition: CleanupDisposition
    detail: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.identity, LeaseIdentity):
            raise TypeError("cleanup identity must be LeaseIdentity")
        if not isinstance(self.disposition, CleanupDisposition):
            raise TypeError("cleanup disposition must be CleanupDisposition")
        if not isinstance(self.detail, str):
            raise TypeError("cleanup detail must be a string")

    @property
    def verified(self) -> bool:
        """Whether cleanup may pass a fail-closed settlement gate."""

        return self.disposition in (CleanupDisposition.CLEAN, CleanupDisposition.NOT_CREATED)


@runtime_checkable
class EnvironmentProvider(Protocol):
    """Supported Motus territory lifecycle; creation and recovery are lookup-first."""

    provider: str
    capabilities: frozenset[str]

    def create(self, operation_id: str, spec: EnvironmentSpec) -> EnvironmentLease: ...

    def lookup(self, operation_id: str) -> EnvironmentLease | None: ...

    def attach(
        self, lease: EnvironmentLease, workspace_archive_bytes: bytes, input_digest: str
    ) -> ExecutionAttachment: ...

    def execute(self, attachment: ExecutionAttachment, command: Command) -> CommandResult: ...

    def export(self, attachment: ExecutionAttachment) -> bytes: ...

    def cancel(self, lease: EnvironmentLease, reason: str) -> None: ...

    def reconcile(self, operation_id: str) -> ReconcileResult: ...

    def destroy(self, lease: EnvironmentLease) -> CleanupResult: ...


@runtime_checkable
class PrivateFileTransfer(EnvironmentProvider, Protocol):
    """Optional complete private-file import, command binding, export, and cleanup contract."""

    def import_private_file(self, attachment: ExecutionAttachment, value: PrivateFile) -> PrivateFileRef: ...

    def export_private_file(self, attachment: ExecutionAttachment, reference: PrivateFileRef) -> PrivateFile: ...

    def delete_private_file(
        self, attachment: ExecutionAttachment, reference: PrivateFileRef
    ) -> PrivateFileCleanupResult: ...

    def cleanup_private_files(self, attachment: ExecutionAttachment) -> PrivateFileCleanupResult: ...


__all__ = [
    "MAX_COMMAND_OUTPUT_BYTES",
    "MAX_PRIVATE_FILE_BYTES",
    "MAX_PRIVATE_FILE_NAME_BYTES",
    "MAX_PRIVATE_FILES_PER_ATTACHMENT",
    "MAX_PRIVATE_FILE_TOTAL_BYTES",
    "CleanupDisposition",
    "CleanupResult",
    "Command",
    "CommandResult",
    "EnvironmentCapability",
    "EnvironmentLease",
    "EnvironmentProvider",
    "EnvironmentSpec",
    "ExecutionAttachment",
    "ExecutionProvenance",
    "LeaseIdentity",
    "LeaseState",
    "PrivateFile",
    "PrivateFileCleanupResult",
    "PrivateFileRef",
    "PrivateFileTransfer",
    "ReconcileClass",
    "ReconcileResult",
]
