"""Small process-local operation handle shared by Agent Runtime profiles."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from petrus.agenticus.runtime.result import RuntimeTurnSettlement, safe_termination_code
from petrus.agenticus.thread.lifecycle import CancellationDisposition

_MAX_OPERATION_ID_BYTES = 256


def _operation_id(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value.encode()) > _MAX_OPERATION_ID_BYTES
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError("runtime operation identity must be a bounded non-empty text value")
    return value


class RuntimeCleanupDisposition(StrEnum):
    CLEAN = "clean"
    NOT_CREATED = "not-created"
    UNVERIFIED = "unverified"


@dataclass(frozen=True)
class RuntimeOperationCleanup:
    """Secret-free local/runtime cleanup evidence for one operation handle."""

    operation_id: str
    disposition: RuntimeCleanupDisposition
    code: str
    physical_erasure_guaranteed: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "operation_id", _operation_id(self.operation_id))
        if not isinstance(self.disposition, RuntimeCleanupDisposition):
            raise TypeError("runtime cleanup disposition must be RuntimeCleanupDisposition")
        object.__setattr__(self, "code", safe_termination_code(self.code))
        if type(self.physical_erasure_guaranteed) is not bool:
            raise TypeError("runtime cleanup physical erasure field must be a boolean")

    @property
    def verified(self) -> bool:
        return self.disposition in (RuntimeCleanupDisposition.CLEAN, RuntimeCleanupDisposition.NOT_CREATED)


class RuntimeProtocolError(RuntimeError):
    """A safe machine-coded runtime protocol failure without raw provider output."""

    def __init__(self, code: str) -> None:
        self.code = safe_termination_code(code)
        super().__init__(f"runtime protocol error: {self.code}")


@runtime_checkable
class RuntimeOperation(Protocol):
    """Cancellation and cleanup for one already-started profile-specific operation.

    ``wait`` raises :class:`TimeoutError` without changing operation state when
    its bound expires. It may then be called again. After terminal settlement,
    every wait returns the same immutable result. After ``close``, waiting raises
    ``RuntimeProtocolError("operation-closed")``.

    ``cancel`` is idempotent through DS3's exact ``CancellationDisposition``.
    ``close`` does not imply cancellation: it is legal only after settlement or
    after cancellation was requested, and otherwise raises
    ``RuntimeProtocolError("operation-active")``. Repeated close returns the
    same immutable cleanup evidence. Cancellation cleanup that cannot prove
    absence returns ``UNVERIFIED`` rather than manufacturing settlement.
    """

    @property
    def operation_id(self) -> str: ...

    def wait(self, timeout: float | None = None) -> RuntimeTurnSettlement: ...

    def cancel(self, reason: str) -> CancellationDisposition: ...

    def close(self) -> RuntimeOperationCleanup: ...
