"""Single-writer durable recovery boundary for native Pi operations.

This boundary prevents blind redispatch after a crash; it cannot make an
external provider call exactly once. One process must exclusively own a ledger.
"""

from __future__ import annotations

import errno
import fcntl
import os
import sqlite3
import stat
import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol, cast, runtime_checkable

from petrus.agenticus.connection.storage import StorageError, StorageSecurityError
from petrus.agenticus.runtime.operation import (
    RuntimeCleanupDisposition,
    RuntimeOperation,
    RuntimeOperationCleanup,
    RuntimeProtocolError,
)
from petrus.agenticus.runtime.pi import PiRuntimeAdapter, PiRuntimeInvocation, pi_durable_fingerprint
from petrus.agenticus.runtime.result import RuntimeTurnSettlement, safe_termination_code
from petrus.agenticus.thread.identity import EpisodeId, TurnId
from petrus.agenticus.thread.lifecycle import CancellationDisposition, TurnOutcome


class PiOperationPhase(StrEnum):
    EXECUTING = "executing"
    SETTLED = "settled"


def _text(value: object, name: str, maximum: int = 512) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value.encode()) > maximum
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError(f"{name} must be bounded non-empty text")
    return value


@dataclass(frozen=True)
class PiOperationRecord:
    """Secret-free durable operation identity, terminal refs, and cleanup state."""

    operation_id: str
    fingerprint: str
    episode_id: EpisodeId
    turn_id: TurnId
    sequence: int
    phase: PiOperationPhase
    outcome: TurnOutcome | None = None
    accepted_appends: int | None = None
    termination_code: str | None = None
    output_reference: str | None = None
    continuation_reference: str | None = None
    cleanup: RuntimeCleanupDisposition = RuntimeCleanupDisposition.UNVERIFIED
    cleanup_code: str = "cleanup-uncertain"
    acknowledged: bool = False

    def __post_init__(self) -> None:
        _text(self.operation_id, "Pi operation", 256)
        if not isinstance(self.fingerprint, str) or len(self.fingerprint) != 64:
            raise ValueError("Pi operation fingerprint must be SHA-256")
        try:
            int(self.fingerprint, 16)
        except ValueError:
            raise ValueError("Pi operation fingerprint must be SHA-256") from None
        if not isinstance(self.episode_id, EpisodeId) or not isinstance(self.turn_id, TurnId):
            raise TypeError("Pi operation record requires exact identities")
        if type(self.sequence) is not int or self.sequence <= 0:
            raise ValueError("Pi operation sequence must be positive")
        if not isinstance(self.phase, PiOperationPhase):
            raise TypeError("Pi operation phase must be PiOperationPhase")
        if not isinstance(self.cleanup, RuntimeCleanupDisposition):
            raise TypeError("Pi operation cleanup must be RuntimeCleanupDisposition")
        safe_termination_code(self.cleanup_code)
        if type(self.acknowledged) is not bool:
            raise TypeError("Pi operation acknowledgement must be boolean")
        if self.phase is PiOperationPhase.EXECUTING:
            if (
                any(
                    value is not None
                    for value in (
                        self.outcome,
                        self.accepted_appends,
                        self.termination_code,
                        self.output_reference,
                        self.continuation_reference,
                    )
                )
                or self.cleanup is not RuntimeCleanupDisposition.UNVERIFIED
                or self.cleanup_code != "cleanup-uncertain"
                or self.acknowledged
            ):
                raise ValueError("executing Pi operation cannot contain terminal state")
            return
        self.settlement()

    def settlement(self) -> RuntimeTurnSettlement:
        if self.phase is not PiOperationPhase.SETTLED:
            raise RuntimeProtocolError("operation-active")
        if not isinstance(self.outcome, TurnOutcome) or self.accepted_appends is None or self.termination_code is None:
            raise ValueError("settled Pi operation requires complete terminal state")
        return RuntimeTurnSettlement(
            self.episode_id,
            self.turn_id,
            self.outcome,
            self.accepted_appends,
            self.termination_code,
            self.output_reference,
            self.continuation_reference,
        )

    def cleanup_evidence(self) -> RuntimeOperationCleanup:
        return RuntimeOperationCleanup(self.operation_id, self.cleanup, self.cleanup_code)


@runtime_checkable
class PiOperationLedger(Protocol):
    def recover(self) -> tuple[PiOperationRecord, ...]: ...
    def admit(
        self, operation_id: str, fingerprint: str, episode_id: EpisodeId, turn_id: TurnId
    ) -> PiOperationRecord: ...
    def lookup(self, operation_id: str) -> PiOperationRecord | None: ...
    def records(self) -> tuple[PiOperationRecord, ...]: ...
    def settle(self, operation_id: str, settlement: RuntimeTurnSettlement) -> PiOperationRecord: ...
    def upgrade_cleanup(self, operation_id: str, cleanup: RuntimeOperationCleanup) -> PiOperationRecord: ...
    def acknowledge(self, operation_id: str) -> PiOperationRecord: ...
    def watermark(self) -> int: ...
    def close(self) -> None: ...


class SqlitePiOperationLedger:
    """Private SQLite ledger with one fail-loud, process-fenced writer."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._prepare_path()
        self._fence = _WriterFence(self.path)
        self._lock = threading.RLock()
        try:
            self._database = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False, timeout=5)
            os.chmod(self.path, 0o600)
            self._database.execute("PRAGMA journal_mode = DELETE")
            self._database.execute("PRAGMA synchronous = FULL")
            self._database.execute(
                """CREATE TABLE IF NOT EXISTS pi_operations (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    operation_id TEXT NOT NULL UNIQUE, fingerprint TEXT NOT NULL,
                    episode_id TEXT NOT NULL, turn_id TEXT NOT NULL, phase TEXT NOT NULL,
                    outcome TEXT, accepted_appends INTEGER, termination_code TEXT,
                    output_reference TEXT, continuation_reference TEXT,
                    cleanup TEXT NOT NULL, cleanup_code TEXT NOT NULL,
                    acknowledged INTEGER NOT NULL CHECK (acknowledged IN (0, 1)))"""
            )
        except BaseException:
            self._fence.close()
            raise

    def recover(self) -> tuple[PiOperationRecord, ...]:
        """Fence every operation whose prior process may have crossed the provider."""
        self._fence.ensure()
        with self._lock:
            operation_ids = tuple(
                str(row[0])
                for row in self._database.execute(
                    "SELECT operation_id FROM pi_operations WHERE phase = ? ORDER BY sequence",
                    (PiOperationPhase.EXECUTING.value,),
                ).fetchall()
            )
            if operation_ids:
                self._write(
                    """UPDATE pi_operations SET phase = ?, outcome = ?, accepted_appends = 0,
                       termination_code = ?, output_reference = NULL, continuation_reference = NULL,
                       cleanup = ?, cleanup_code = ?, acknowledged = 0 WHERE phase = ?""",
                    (
                        PiOperationPhase.SETTLED.value,
                        TurnOutcome.INDETERMINATE.value,
                        "restart-indeterminate",
                        RuntimeCleanupDisposition.UNVERIFIED.value,
                        "cleanup-uncertain",
                        PiOperationPhase.EXECUTING.value,
                    ),
                    expected_rows=len(operation_ids),
                )
            return tuple(self._required(operation_id) for operation_id in operation_ids)

    def admit(self, operation_id: str, fingerprint: str, episode_id: EpisodeId, turn_id: TurnId) -> PiOperationRecord:
        self._fence.ensure()
        candidate = PiOperationRecord(operation_id, fingerprint, episode_id, turn_id, 1, PiOperationPhase.EXECUTING)
        with self._lock:
            existing = self.lookup(operation_id)
            if existing is not None:
                return existing
            self._write(
                """INSERT INTO pi_operations
                   (operation_id, fingerprint, episode_id, turn_id, phase, cleanup, cleanup_code, acknowledged)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 0)""",
                (
                    candidate.operation_id,
                    candidate.fingerprint,
                    episode_id.value,
                    turn_id.value,
                    PiOperationPhase.EXECUTING.value,
                    RuntimeCleanupDisposition.UNVERIFIED.value,
                    "cleanup-uncertain",
                ),
                expected_rows=1,
            )
            result = self.lookup(operation_id)
            assert result is not None
            return result

    def lookup(self, operation_id: str) -> PiOperationRecord | None:
        self._fence.ensure()
        _text(operation_id, "Pi operation", 256)
        with self._lock:
            row = self._database.execute(
                "SELECT * FROM pi_operations WHERE operation_id = ?", (operation_id,)
            ).fetchone()
        return None if row is None else self._decode(row)

    def records(self) -> tuple[PiOperationRecord, ...]:
        self._fence.ensure()
        with self._lock:
            rows = self._database.execute("SELECT * FROM pi_operations ORDER BY sequence").fetchall()
        records = tuple(self._decode(row) for row in rows)
        if tuple(record.sequence for record in records) != tuple(range(1, len(records) + 1)):
            raise StorageError("Pi operation ledger sequence is not dense")
        return records

    def settle(self, operation_id: str, settlement: RuntimeTurnSettlement) -> PiOperationRecord:
        self._fence.ensure()
        if not isinstance(settlement, RuntimeTurnSettlement):
            raise TypeError("Pi ledger settlement must be RuntimeTurnSettlement")
        with self._lock:
            current = self._required(operation_id)
            if (current.episode_id, current.turn_id) != (settlement.episode_id, settlement.turn_id):
                raise RuntimeProtocolError("operation-conflict")
            if current.phase is PiOperationPhase.SETTLED:
                if current.settlement() != settlement:
                    raise RuntimeProtocolError("operation-conflict")
                return current
            self._write(
                """UPDATE pi_operations SET phase = ?, outcome = ?, accepted_appends = ?, termination_code = ?,
                   output_reference = ?, continuation_reference = ? WHERE operation_id = ? AND phase = ?""",
                (
                    PiOperationPhase.SETTLED.value,
                    settlement.outcome.value,
                    settlement.accepted_appends,
                    settlement.termination_code,
                    settlement.output_reference,
                    settlement.continuation_reference,
                    operation_id,
                    PiOperationPhase.EXECUTING.value,
                ),
                expected_rows=1,
            )
            return self._required(operation_id)

    def upgrade_cleanup(self, operation_id: str, cleanup: RuntimeOperationCleanup) -> PiOperationRecord:
        self._fence.ensure()
        if not isinstance(cleanup, RuntimeOperationCleanup) or cleanup.operation_id != operation_id:
            raise RuntimeProtocolError("operation-conflict")
        with self._lock:
            current = self._required(operation_id)
            if current.phase is not PiOperationPhase.SETTLED:
                raise RuntimeProtocolError("operation-active")
            if current.cleanup is not RuntimeCleanupDisposition.UNVERIFIED:
                if current.cleanup_evidence() != cleanup:
                    raise RuntimeProtocolError("operation-conflict")
                return current
            if cleanup.disposition not in (RuntimeCleanupDisposition.CLEAN, RuntimeCleanupDisposition.NOT_CREATED):
                if current.cleanup_evidence() != cleanup:
                    raise RuntimeProtocolError("operation-conflict")
                return current
            self._write(
                "UPDATE pi_operations SET cleanup = ?, cleanup_code = ? WHERE operation_id = ?",
                (cleanup.disposition.value, cleanup.code, operation_id),
                expected_rows=1,
            )
            return self._required(operation_id)

    def acknowledge(self, operation_id: str) -> PiOperationRecord:
        self._fence.ensure()
        with self._lock:
            current = self._required(operation_id)
            if current.phase is not PiOperationPhase.SETTLED:
                raise RuntimeProtocolError("operation-active")
            if not current.acknowledged:
                self._write(
                    "UPDATE pi_operations SET acknowledged = 1 WHERE operation_id = ? AND acknowledged = 0",
                    (operation_id,),
                    expected_rows=1,
                )
            return self._required(operation_id)

    def watermark(self) -> int:
        self._fence.ensure()
        watermark = 0
        for record in self.records():
            if record.phase is not PiOperationPhase.SETTLED or not record.acknowledged:
                break
            watermark = record.sequence
        return watermark

    def close(self) -> None:
        with self._lock:
            self._database.close()
        self._fence.close()

    def _required(self, operation_id: str) -> PiOperationRecord:
        record = self.lookup(operation_id)
        if record is None:
            raise RuntimeProtocolError("operation-absent")
        return record

    def _write(self, sql: str, parameters: tuple[object, ...], *, expected_rows: int | None = None) -> None:
        with self._lock:
            self._database.execute("BEGIN IMMEDIATE")
            try:
                cursor = self._database.execute(sql, parameters)
                if expected_rows is not None and cursor.rowcount != expected_rows:
                    raise StorageError("Pi operation ledger write lost its expected state")
                self._database.commit()
            except BaseException:
                self._database.rollback()
                raise

    @staticmethod
    def _decode(row: tuple[object, ...]) -> PiOperationRecord:
        sequence = cast(int, row[0])
        accepted_appends = cast(int | None, row[7])
        return PiOperationRecord(
            operation_id=str(row[1]),
            fingerprint=str(row[2]),
            episode_id=EpisodeId(str(row[3])),
            turn_id=TurnId(str(row[4])),
            sequence=sequence,
            phase=PiOperationPhase(str(row[5])),
            outcome=None if row[6] is None else TurnOutcome(str(row[6])),
            accepted_appends=accepted_appends,
            termination_code=None if row[8] is None else str(row[8]),
            output_reference=None if row[9] is None else str(row[9]),
            continuation_reference=None if row[10] is None else str(row[10]),
            cleanup=RuntimeCleanupDisposition(str(row[11])),
            cleanup_code=str(row[12]),
            acknowledged=bool(row[13]),
        )

    def _prepare_path(self) -> None:
        parent = self.path.parent
        if parent.is_symlink():
            raise StorageSecurityError("Pi ledger parent must not be a symlink")
        if not parent.exists():
            parent.mkdir(mode=0o700, parents=True)
            parent.chmod(0o700)
        metadata = parent.lstat()
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o700
            or metadata.st_uid != os.geteuid()
        ):
            raise StorageSecurityError("Pi ledger parent must be an owned mode-0700 directory")
        if self.path.is_symlink():
            raise StorageSecurityError("Pi ledger file must not be a symlink")
        if not self.path.exists():
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(self.path, flags, 0o600)
            os.close(descriptor)
        metadata = self.path.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_uid != os.geteuid()
        ):
            raise StorageSecurityError("Pi ledger file must be owned regular mode-0600")


class _WriterFence:
    """Nonblocking POSIX ownership fence for one operation ledger."""

    def __init__(self, database: Path) -> None:
        self.path = database.with_name(f".{database.name}.writer.lock")
        self._pid = os.getpid()
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(self.path, flags, 0o600)
        except OSError as error:
            raise StorageSecurityError("Pi ledger writer fence is unavailable") from error
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_uid != os.geteuid()
            ):
                raise StorageSecurityError("Pi ledger writer fence must be owned regular mode-0600")
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            os.close(descriptor)
            if error.errno in (errno.EACCES, errno.EAGAIN):
                raise StorageError("Pi operation ledger already has a live writer") from error
            raise
        except BaseException:
            os.close(descriptor)
            raise
        self._descriptor: int | None = descriptor

    def ensure(self) -> None:
        if self._descriptor is None:
            raise StorageError("Pi operation ledger writer is closed")
        if os.getpid() != self._pid:
            raise StorageError("Pi operation ledger cannot be used across fork")

    def close(self) -> None:
        descriptor, self._descriptor = self._descriptor, None
        if descriptor is None:
            return
        if os.getpid() == self._pid:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)
        else:
            os.close(descriptor)


class _ReplayOperation:
    def __init__(self, record: PiOperationRecord) -> None:
        self._record = record
        self._lock = threading.RLock()
        self._cleanup: RuntimeOperationCleanup | None = None

    @property
    def operation_id(self) -> str:
        return self._record.operation_id

    def wait(self, timeout: float | None = None) -> RuntimeTurnSettlement:
        if timeout is not None and (
            isinstance(timeout, bool) or not isinstance(timeout, int | float) or not 0 < timeout < float("inf")
        ):
            raise ValueError("Pi wait timeout must be positive and finite")
        with self._lock:
            if self._cleanup is not None:
                raise RuntimeProtocolError("operation-closed")
            return self._record.settlement()

    def cancel(self, reason: str) -> CancellationDisposition:
        _text(reason, "Pi cancellation reason")
        with self._lock:
            return CancellationDisposition.TOO_LATE

    def close(self) -> RuntimeOperationCleanup:
        with self._lock:
            if self._cleanup is None:
                self._cleanup = self._record.cleanup_evidence()
            return self._cleanup


class _DurableOperation:
    def __init__(
        self,
        inner: RuntimeOperation,
        ledger: PiOperationLedger,
        receipt: Callable[[str], RuntimeTurnSettlement | None],
    ) -> None:
        self._inner, self._ledger, self._receipt = inner, ledger, receipt
        self._lock = threading.RLock()
        self._cleanup: RuntimeOperationCleanup | None = None

    @property
    def operation_id(self) -> str:
        return self._inner.operation_id

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._cleanup is not None

    def wait(self, timeout: float | None = None) -> RuntimeTurnSettlement:
        with self._lock:
            if self._cleanup is not None:
                raise RuntimeProtocolError("operation-closed")
            result = self._inner.wait(timeout)
            self._ledger.settle(self.operation_id, result)
            return result

    def cancel(self, reason: str) -> CancellationDisposition:
        return self._inner.cancel(reason)

    def close(self) -> RuntimeOperationCleanup:
        with self._lock:
            if self._cleanup is not None:
                return self._cleanup
            result = self._receipt(self.operation_id)
            if result is not None:
                self._ledger.settle(self.operation_id, result)
            cleanup = self._inner.close()
            result = self._receipt(self.operation_id)
            if result is None:
                record = self._ledger.lookup(self.operation_id)
                if record is None:
                    raise RuntimeProtocolError("operation-absent")
                result = RuntimeTurnSettlement(
                    record.episode_id,
                    record.turn_id,
                    TurnOutcome.INDETERMINATE,
                    0,
                    "close-indeterminate",
                )
            self._ledger.settle(self.operation_id, result)
            self._ledger.upgrade_cleanup(self.operation_id, cleanup)
            self._cleanup = cleanup
            return cleanup


class PiRecoveredRuntime:
    """Single-process Pi adapter facade with durable ambiguous-work recovery."""

    def __init__(self, adapter: PiRuntimeAdapter, ledger: PiOperationLedger) -> None:
        if type(adapter) is not PiRuntimeAdapter or not isinstance(ledger, PiOperationLedger):
            raise TypeError("Pi recovered runtime requires exact adapter and operation ledger")
        self._adapter, self._ledger = adapter, ledger
        self._lock = threading.RLock()
        self._live: dict[str, _DurableOperation] = {}
        recovered = ledger.recover()
        records = ledger.records()
        if any(record.phase is PiOperationPhase.EXECUTING for record in records):
            raise RuntimeProtocolError("recovery-state-invalid")
        self.recovered_settlements = tuple(record.settlement() for record in recovered)

    @property
    def descriptor(self):
        return self._adapter.descriptor

    @property
    def hands(self):
        return self._adapter.hands

    @property
    def territory(self):
        return self._adapter.territory

    @property
    def program(self):
        return self._adapter.program

    def probe(self, **kwargs):
        return self._adapter.probe(**kwargs)

    def start(self, inv: PiRuntimeInvocation) -> RuntimeOperation:
        fingerprint = pi_durable_fingerprint(self._adapter.config, inv)
        with self._lock:
            record = self._ledger.admit(inv.operation_id, fingerprint, inv.episode_id, inv.turn_id)
            if record.fingerprint != fingerprint:
                raise RuntimeProtocolError("operation-conflict")
            live = self._live.get(inv.operation_id)
            if live is not None:
                return live
            if record.phase is PiOperationPhase.SETTLED:
                return _ReplayOperation(record)
            try:
                inner = self._adapter.start(inv)
            except RuntimeProtocolError as error:
                failed = RuntimeTurnSettlement(inv.episode_id, inv.turn_id, TurnOutcome.FAILED, 0, error.code)
                self._ledger.settle(inv.operation_id, failed)
                self._ledger.upgrade_cleanup(
                    inv.operation_id,
                    RuntimeOperationCleanup(
                        inv.operation_id, RuntimeCleanupDisposition.NOT_CREATED, "client-not-created"
                    ),
                )
                raise
            except Exception:
                failed = RuntimeTurnSettlement(
                    inv.episode_id, inv.turn_id, TurnOutcome.FAILED, 0, "runtime-start-failed"
                )
                self._ledger.settle(inv.operation_id, failed)
                self._ledger.upgrade_cleanup(
                    inv.operation_id,
                    RuntimeOperationCleanup(
                        inv.operation_id, RuntimeCleanupDisposition.NOT_CREATED, "client-not-created"
                    ),
                )
                raise RuntimeProtocolError("runtime-start-failed") from None
            operation = _DurableOperation(inner, self._ledger, self._adapter.receipt)
            self._live[inv.operation_id] = operation
            return operation

    def acknowledge(self, operation_id: str) -> PiOperationRecord:
        return self._ledger.acknowledge(operation_id)

    def evict(self) -> tuple[str, ...]:
        watermark = self._ledger.watermark()
        evicted: list[str] = []
        with self._lock:
            for operation_id, operation in tuple(self._live.items()):
                record = self._ledger.lookup(operation_id)
                if record is not None and record.acknowledged and record.sequence <= watermark and operation.closed:
                    if self._adapter.evict(operation_id):
                        del self._live[operation_id]
                        evicted.append(operation_id)
        return tuple(evicted)


__all__ = [
    "PiOperationLedger",
    "PiOperationPhase",
    "PiOperationRecord",
    "PiRecoveredRuntime",
    "SqlitePiOperationLedger",
]
