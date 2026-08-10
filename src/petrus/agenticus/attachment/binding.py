"""Provider-neutral Episode Attachment binding and settlement evidence.

An :class:`AttachmentBinding` is the narrow lifecycle one Episode Attachment
epoch holds over its execution territory. The outer coordinates and
settlement evidence are provider-neutral so distinct binding implementations
can exist without optional-field impossible states: a Motus-backed binding
carries an exact lease, while an honestly provider-managed binding (for
example a host whose provider owns loop, tools, and placement) may implement
the same narrow protocol without any Motus lease at all. Only the external
capability-scoped Hands path requires Motus.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from threading import Condition, local
from typing import Protocol

from petrus.motus.execution import (
    CleanupResult,
    Command,
    CommandResult,
    EnvironmentLease,
    EnvironmentProvider,
    EnvironmentSpec,
    ExecutionAttachment,
    LeaseIdentity,
    LeaseState,
)

_KIND_PATTERN = re.compile(r"[a-z][a-z0-9-]{0,63}")
_MAX_IDENTITY_BYTES = 256
_MAX_DETAIL_BYTES = 256

MOTUS_BINDING_KIND = "motus-territory"


def _identity(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value.encode()) > _MAX_IDENTITY_BYTES
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError(f"{name} must be a bounded non-empty identity string")
    return value


def _positive_integer(value: object, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _kind(value: object) -> str:
    if not isinstance(value, str) or _KIND_PATTERN.fullmatch(value) is None:
        raise ValueError("binding kind must be a bounded lowercase token")
    return value


def _detail(value: object) -> str:
    if not isinstance(value, str) or len(value.encode()) > _MAX_DETAIL_BYTES or any(ord(c) < 32 for c in value):
        raise ValueError("settlement detail must be a bounded string without control characters")
    return value


@dataclass(frozen=True)
class AttachmentCoordinates:
    """The exact current coordinates a DS7 ``EffectFence`` construction needs.

    This carries identity only; DS7 owns effect types and target/authority
    head policy, and the host supplies those from its own seams.
    """

    episode_id: str
    attachment_id: str
    attachment_epoch: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "episode_id", _identity(self.episode_id, "coordinates episode_id"))
        object.__setattr__(self, "attachment_id", _identity(self.attachment_id, "coordinates attachment_id"))
        _positive_integer(self.attachment_epoch, "coordinates attachment_epoch")


@dataclass(frozen=True)
class BindingSettlement:
    """Independently consumable, fail-closed settlement evidence of one binding.

    ``verified`` is the only gate an Episode Attachment trusts; ``disposition``
    and ``detail`` are bounded secret-safe tokens for the host's records.
    """

    binding_kind: str
    disposition: str
    verified: bool
    detail: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "binding_kind", _kind(self.binding_kind))
        object.__setattr__(self, "disposition", _kind(self.disposition))
        if type(self.verified) is not bool:
            raise TypeError("settlement verified must be a boolean")
        object.__setattr__(self, "detail", _detail(self.detail))


class AttachmentBinding(Protocol):
    """The narrow lifecycle one Episode Attachment epoch holds over territory.

    Implementations own their provider lifecycle; the Episode Attachment only
    cancels, exports one bounded archive, and consumes settlement evidence.
    """

    @property
    def binding_kind(self) -> str: ...

    def cancel(self, reason: str) -> None: ...

    def export_archive(self) -> bytes: ...

    def settle(self) -> BindingSettlement: ...


class MotusBindingError(RuntimeError):
    """A Motus binding operation violated its lease or provenance contract."""


class MotusAttachmentBinding:
    """Concrete binding over one exact public Motus territory lease.

    Creation is lookup-first through the supported provider ``lookup``/
    ``create``/``attach`` path. Settlement destroys the exact lease and
    consumes its ``CleanupResult``; only an independently ``verified``
    disposition (``clean`` or ``not-created``) settles, and every command
    result is provenance-fenced to the exact lease.
    """

    binding_kind = MOTUS_BINDING_KIND

    def __init__(
        self,
        provider: EnvironmentProvider,
        lease: EnvironmentLease,
        execution: ExecutionAttachment,
        base_archive: bytes,
    ) -> None:
        if not isinstance(lease, EnvironmentLease):
            raise TypeError("motus binding lease must be EnvironmentLease")
        if not isinstance(execution, ExecutionAttachment):
            raise TypeError("motus binding execution must be ExecutionAttachment")
        if execution.lease.identity != lease.identity:
            raise MotusBindingError("execution attachment does not belong to the bound lease")
        if not isinstance(base_archive, bytes):
            raise TypeError("motus binding base archive must be bytes")
        self._provider = provider
        self._lease = lease
        self._execution = execution
        self._base_archive = base_archive
        self._discard_output = False
        self._cleanup: CleanupResult | None = None
        self._released = False
        self._operations = Condition()
        self._operation_state = local()
        self._operation_admission_open = True
        self._active_operations = 0

    @classmethod
    def open(
        cls,
        provider: EnvironmentProvider,
        operation_id: str,
        spec: EnvironmentSpec,
        *,
        workspace_archive_bytes: bytes,
        input_digest: str,
    ) -> MotusAttachmentBinding:
        """Bind lookup-first: reuse the operation's lease or create it, then attach."""

        lease = provider.lookup(operation_id)
        if lease is None:
            lease = provider.create(operation_id, spec)
        try:
            execution = provider.attach(lease, workspace_archive_bytes, input_digest)
        except Exception:
            try:
                cleanup = provider.destroy(lease)
            except Exception:
                raise MotusBindingError("Motus attachment failed and cleanup could not be verified") from None
            if not isinstance(cleanup, CleanupResult) or cleanup.identity != lease.identity or not cleanup.verified:
                raise MotusBindingError("Motus attachment failed and cleanup could not be verified") from None
            raise MotusBindingError("Motus attachment failed after verified cleanup") from None
        return cls(provider, lease, execution, workspace_archive_bytes)

    @classmethod
    def _reclaim_exact(
        cls,
        provider: EnvironmentProvider,
        expected: LeaseIdentity,
        *,
        workspace_archive_bytes: bytes,
        input_digest: str,
    ) -> MotusAttachmentBinding:
        """Attach only to one exact retained lease; never create a replacement."""

        if not isinstance(expected, LeaseIdentity):
            raise TypeError("retained Motus reclaim requires an exact LeaseIdentity")
        lease = provider.lookup(expected.operation_id)
        if lease is None:
            raise MotusBindingError("retained Motus lease is absent")
        if lease.identity != expected:
            raise MotusBindingError("retained Motus lease identity conflicts with provider lookup")
        if lease.state is not LeaseState.READY:
            raise MotusBindingError("retained Motus lease is not ready")
        try:
            execution = provider.attach(lease, workspace_archive_bytes, input_digest)
        except Exception:
            raise MotusBindingError("retained Motus lease attachment failed") from None
        return cls(provider, lease, execution, workspace_archive_bytes)

    @property
    def provider(self) -> EnvironmentProvider:
        self._ensure_owned()
        return self._provider

    @property
    def lease_identity(self) -> LeaseIdentity:
        return self._lease.identity

    @property
    def execution(self) -> ExecutionAttachment:
        self._ensure_owned()
        return self._execution

    @property
    def cleanup_result(self) -> CleanupResult | None:
        """The consumed Motus cleanup evidence, for host inspection only."""

        return self._cleanup

    def execute(self, command: Command) -> CommandResult:
        """Run one bounded command, provenance-fenced to the exact lease."""

        with self._operation():
            result = self._provider.execute(self._execution, command)
        if result.provenance.identity != self._lease.identity:
            raise MotusBindingError("command result provenance does not match the bound lease")
        if result.timed_out or result.superseded or result.output_truncated:
            self._discard_output = True
        return result

    def cancel(self, reason: str) -> None:
        self._ensure_owned()
        self._discard_output = True
        self._provider.cancel(self._lease, reason)

    def export_archive(self) -> bytes:
        self._ensure_owned()
        if self._discard_output:
            return self._base_archive
        return self._provider.export(self._execution)

    def settle(self) -> BindingSettlement:
        """Destroy the exact lease and consume its fail-closed cleanup evidence."""

        self._ensure_owned()
        cleanup = self._provider.destroy(self._lease)
        if not isinstance(cleanup, CleanupResult):
            raise MotusBindingError("provider destroy must return CleanupResult")
        if cleanup.identity != self._lease.identity:
            return BindingSettlement(
                binding_kind=self.binding_kind,
                disposition="unverified",
                verified=False,
                detail="cleanup evidence names a different lease identity",
            )
        self._cleanup = cleanup
        return BindingSettlement(
            binding_kind=self.binding_kind,
            disposition=cleanup.disposition.value,
            verified=cleanup.verified,
            detail="provider cleanup evidence consumed",
        )

    def _release(self, accept: Callable[[EnvironmentLease], None]) -> LeaseIdentity:
        """Irrevocably close this binding before host custody accepts its lease."""

        if not callable(accept):
            raise TypeError("Motus binding release requires a custody acceptance callback")
        with self._operations:
            self._ensure_owned()
            if self._operation_admission_open or self._active_operations:
                raise MotusBindingError("Motus binding release requires quiesced operation admission")
            self._released = True
        accept(self._lease)
        return self._lease.identity

    def _quiesce(self, timeout: float) -> bool:
        """Close operation admission and wait for every borrowed provider operation."""

        if isinstance(timeout, bool) or not isinstance(timeout, int | float) or timeout < 0:
            raise ValueError("Motus binding quiescence timeout must be non-negative")
        with self._operations:
            self._ensure_owned()
            self._operation_admission_open = False
            return self._operations.wait_for(lambda: self._active_operations == 0, timeout)

    @contextmanager
    def _operation(self):
        """Borrow this binding's provider authority until one operation is complete."""

        depth = getattr(self._operation_state, "depth", 0)
        if depth:
            self._operation_state.depth = depth + 1
            try:
                yield
            finally:
                self._operation_state.depth -= 1
            return
        with self._operations:
            self._ensure_owned()
            if not self._operation_admission_open:
                raise MotusBindingError("Motus binding operation admission is closed")
            self._active_operations += 1
            self._operation_state.depth = 1
        try:
            yield
        finally:
            with self._operations:
                self._operation_state.depth = 0
                self._active_operations -= 1
                self._operations.notify_all()

    def _ensure_owned(self) -> None:
        if self._released:
            raise MotusBindingError("Motus binding authority was released to host custody")


__all__ = [
    "MOTUS_BINDING_KIND",
    "AttachmentBinding",
    "AttachmentCoordinates",
    "BindingSettlement",
    "MotusAttachmentBinding",
    "MotusBindingError",
]
