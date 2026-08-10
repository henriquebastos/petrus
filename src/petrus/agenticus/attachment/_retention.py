"""Private single-host custody for intentionally retained Motus territories.

Activity and Worker never receive this surface. One host state root durably
owns release, exact-lease reclaim, and eventual destruction obligations.
"""

from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import math
import os
import sqlite3
import stat
import threading
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import cast

from petrus.agenticus.attachment.binding import AttachmentCoordinates, MotusAttachmentBinding
from petrus.agenticus.attachment.episode import AttachmentRelease, EpisodeAttachment
from petrus.agenticus.catalog.descriptor import DescriptorKind
from petrus.agenticus.catalog.resolution import ResolutionSnapshot
from petrus.agenticus.connection.storage import StorageError, StorageSecurityError
from petrus.agenticus.hands.gateway import ResultAdmission, TargetCurrency
from petrus.agenticus.thread.identity import EpisodeId
from petrus.motus.execution import (
    CleanupDisposition,
    EnvironmentLease,
    EnvironmentProvider,
    LeaseIdentity,
    LeaseState,
)
from petrus.motus.execution.archive import MAX_WORKSPACE_ARCHIVE_BYTES


class TerritoryCustodyPhase(StrEnum):
    RELEASING = "releasing"
    RETAINED = "retained"
    CLAIMING = "claiming"
    ATTACHED = "attached"
    RETIRING = "retiring"
    RETIRED = "retired"
    QUARANTINED = "quarantined"


def _text(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value.encode()) > 256
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError(f"{name} must be bounded non-empty text")
    return value


def _exact_int(value: object, name: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")
    return value


def _exact_number(value: object, name: str) -> int | float:
    if type(value) not in (int, float):
        raise TypeError(f"{name} must be numeric")
    return cast(int | float, value)


def _optional_text(value: object, name: str) -> str | None:
    return None if value is None else _text(value, name)


def _optional_int(value: object, name: str) -> int | None:
    return None if value is None else _exact_int(value, name)


def _optional_bytes(value: object, name: str) -> bytes | None:
    if value is not None and not isinstance(value, bytes):
        raise TypeError(f"{name} must be bytes")
    return value


@dataclass(frozen=True)
class TerritoryCustodyRecord:
    custody_id: str
    owner_id: str
    generation: int
    phase: TerritoryCustodyPhase
    source: AttachmentCoordinates
    lease: EnvironmentLease
    retain_until: float
    archive: bytes | None = None
    archive_digest: str | None = None
    target_episode_id: str | None = None
    target_attachment_id: str | None = None
    target_epoch: int | None = None
    cleanup: CleanupDisposition | None = None

    def __post_init__(self) -> None:  # noqa: C901 - one durable closed-state validation boundary
        _text(self.custody_id, "territory custody id")
        _text(self.owner_id, "territory custody owner")
        if type(self.generation) is not int or self.generation <= 0:
            raise ValueError("territory custody generation must be positive")
        if not isinstance(self.phase, TerritoryCustodyPhase):
            raise TypeError("territory custody phase must be TerritoryCustodyPhase")
        if not isinstance(self.source, AttachmentCoordinates) or not isinstance(self.lease, EnvironmentLease):
            raise TypeError("territory custody requires exact source coordinates and lease")
        if not math.isfinite(self.retain_until):
            raise ValueError("territory custody expiry must be finite")
        if self.archive is not None:
            if len(self.archive) > MAX_WORKSPACE_ARCHIVE_BYTES:
                raise ValueError("retained territory archive exceeds the public workspace bound")
            if self.archive_digest != hashlib.sha256(self.archive).hexdigest():
                raise StorageError("retained territory archive digest does not match its bytes")
        elif self.archive_digest is not None:
            raise StorageError("retained territory archive digest has no bytes")
        target = (self.target_episode_id, self.target_attachment_id, self.target_epoch)
        if any(value is not None for value in target) and not all(value is not None for value in target):
            raise StorageError("retained territory target coordinates are partial")
        if self.target_episode_id is not None:
            _text(self.target_episode_id, "territory target episode")
            _text(self.target_attachment_id, "territory target attachment")
            if type(self.target_epoch) is not int or self.target_epoch <= self.source.attachment_epoch:
                raise StorageError("territory target epoch must advance the source epoch")
        if self.phase in (TerritoryCustodyPhase.RETAINED, TerritoryCustodyPhase.CLAIMING) and self.archive is None:
            raise StorageError("retained territory phase requires a durable archive")
        if self.cleanup is not None and not isinstance(self.cleanup, CleanupDisposition):
            raise TypeError("territory cleanup must be CleanupDisposition")


class _ReleaseTicket:
    def __init__(self, ledger: SqliteTerritoryCustody, expected: TerritoryCustodyRecord) -> None:
        self._ledger = ledger
        self._expected = expected
        self._used = False

    def _accept_release(
        self,
        binding: MotusAttachmentBinding,
        coordinates: AttachmentCoordinates,
        stages_discarded: int,
        archive: bytes,
    ) -> LeaseIdentity:
        del stages_discarded
        if self._used:
            raise StorageError("territory release ticket was already consumed")
        if coordinates != self._expected.source or binding.lease_identity != self._expected.lease.identity:
            raise StorageError("territory release does not match durable transfer intent")
        self._used = True
        return binding._release(
            lambda lease: self._ledger._accept_release(self._expected, lease, archive)  # noqa: SLF001
        )


class SqliteTerritoryCustody:
    """Mode-0600, single-writer custody ledger for one local host state root."""

    def __init__(self, path: Path, *, clock=time.time) -> None:
        self.path = Path(path)
        self._clock = clock
        self._prepare_path()
        self._fence = _WriterFence(self.path)
        self._lock = threading.RLock()
        try:
            self._database = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False, timeout=5)
            os.chmod(self.path, 0o600)
            self._database.execute("PRAGMA journal_mode = DELETE")
            self._database.execute("PRAGMA synchronous = FULL")
            self._database.execute("PRAGMA secure_delete = ON")
            self._database.execute(
                """CREATE TABLE IF NOT EXISTS territory_custody (
                    custody_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL,
                    generation INTEGER NOT NULL, phase TEXT NOT NULL,
                    source_episode TEXT NOT NULL, source_attachment TEXT NOT NULL,
                    source_epoch INTEGER NOT NULL, operation_id TEXT NOT NULL,
                    provider TEXT NOT NULL, lease_id TEXT NOT NULL,
                    capabilities TEXT NOT NULL, retain_until REAL NOT NULL,
                    archive BLOB, archive_digest TEXT,
                    target_episode TEXT, target_attachment TEXT, target_epoch INTEGER,
                    cleanup TEXT)"""
            )
            self._database.execute(
                """CREATE UNIQUE INDEX IF NOT EXISTS one_live_territory_operation
                   ON territory_custody(provider, operation_id) WHERE phase <> 'retired'"""
            )
        except BaseException:
            self._fence.close()
            raise

    def begin_release(
        self,
        custody_id: str,
        owner_id: str,
        attachment: EpisodeAttachment,
        *,
        retain_until: float,
    ) -> _ReleaseTicket:
        """Write transfer intent before the host closes an Episode Attachment."""

        self._fence.ensure()
        _text(custody_id, "territory custody id")
        _text(owner_id, "territory custody owner")
        if not isinstance(attachment, EpisodeAttachment):
            raise TypeError("territory release requires an EpisodeAttachment")
        if not math.isfinite(retain_until) or retain_until <= self._clock():
            raise ValueError("territory retention expiry must be finite and in the future")
        binding = attachment.binding
        if not isinstance(binding, MotusAttachmentBinding):
            raise TypeError("territory retention requires an exact Motus binding")
        lease = binding.execution.lease
        source = attachment.coordinates()
        with self._lock:
            current = self.lookup(custody_id)
            if current is None:
                generation = 1
            elif (
                current.phase is TerritoryCustodyPhase.ATTACHED
                and current.owner_id == owner_id
                and current.target_episode_id == source.episode_id
                and current.target_attachment_id == source.attachment_id
                and current.target_epoch == source.attachment_epoch
                and current.lease.identity == lease.identity
            ):
                generation = current.generation + 1
            else:
                raise StorageError("territory custody id is not releasable by this Attachment")
            try:
                self._write(
                    """INSERT INTO territory_custody
                       (custody_id, owner_id, generation, phase, source_episode, source_attachment,
                        source_epoch, operation_id, provider, lease_id, capabilities, retain_until)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(custody_id) DO UPDATE SET owner_id=excluded.owner_id,
                        generation=excluded.generation, phase=excluded.phase,
                        source_episode=excluded.source_episode, source_attachment=excluded.source_attachment,
                        source_epoch=excluded.source_epoch, operation_id=excluded.operation_id,
                        provider=excluded.provider, lease_id=excluded.lease_id,
                        capabilities=excluded.capabilities, retain_until=excluded.retain_until,
                        archive=NULL, archive_digest=NULL, target_episode=NULL,
                        target_attachment=NULL, target_epoch=NULL, cleanup=NULL""",
                    (
                        custody_id,
                        owner_id,
                        generation,
                        TerritoryCustodyPhase.RELEASING.value,
                        source.episode_id,
                        source.attachment_id,
                        source.attachment_epoch,
                        lease.operation_id,
                        lease.provider,
                        lease.lease_id,
                        json.dumps(sorted(lease.capabilities), separators=(",", ":")),
                        retain_until,
                    ),
                )
            except sqlite3.IntegrityError:
                raise StorageError("territory operation already has a live custody obligation") from None
            return _ReleaseTicket(self, self._required(custody_id))

    def release(
        self,
        custody_id: str,
        owner_id: str,
        attachment: EpisodeAttachment,
        *,
        retain_until: float,
        drain_timeout: float = 30.0,
    ) -> AttachmentRelease:
        ticket = self.begin_release(custody_id, owner_id, attachment, retain_until=retain_until)
        return attachment._release_to(ticket, drain_timeout=drain_timeout)  # noqa: SLF001

    def reclaim(  # noqa: C901 - exact lookup, durable claim, and fail-closed rollback are one custody transition
        self,
        custody_id: str,
        owner_id: str,
        provider: EnvironmentProvider,
        *,
        episode_id: EpisodeId,
        snapshot: ResolutionSnapshot,
        attachment_id: str,
        deadline: float,
        admission: ResultAdmission | None = None,
        target: TargetCurrency | None = None,
    ) -> EpisodeAttachment:
        """Reclaim only the exact retained lease into a distinct Attachment."""

        self._fence.ensure()
        if not isinstance(episode_id, EpisodeId):
            raise TypeError("territory reclaim requires an exact EpisodeId")
        _text(attachment_id, "territory target attachment")
        if not isinstance(snapshot, ResolutionSnapshot):
            raise TypeError("territory reclaim requires an immutable ResolutionSnapshot")
        if snapshot.descriptor(DescriptorKind.HANDS) is None or snapshot.descriptor(DescriptorKind.TERRITORY) is None:
            raise ValueError("territory reclaim snapshot must select Hands and Territory descriptors")
        if isinstance(deadline, bool) or not isinstance(deadline, int | float) or not math.isfinite(deadline):
            raise ValueError("territory reclaim deadline must be finite")
        with self._lock:
            row = self._database.execute("SELECT * FROM territory_custody WHERE custody_id=?", (custody_id,)).fetchone()
            if row is None:
                raise StorageError("territory custody record is absent")
            try:
                current = self._decode(row)
            except StorageError:
                self._salvage_corrupt(row)
                raise
            if current.owner_id != owner_id or current.phase is not TerritoryCustodyPhase.RETAINED:
                raise StorageError("territory custody is not retained by this owner")
            if episode_id.value == current.source.episode_id or attachment_id == current.source.attachment_id:
                raise ValueError("territory reclaim requires a distinct Episode and attachment identity")
            if current.retain_until <= self._clock():
                self._set_phase(custody_id, TerritoryCustodyPhase.RETAINED, TerritoryCustodyPhase.RETIRING)
                raise StorageError("territory custody expired before reclaim")
            assert current.archive is not None and current.archive_digest is not None
            observed = provider.lookup(current.lease.operation_id)
            if observed is None or observed.state is not LeaseState.READY:
                self._set_phase(custody_id, TerritoryCustodyPhase.RETAINED, TerritoryCustodyPhase.RETIRING)
                raise StorageError("retained territory is absent or not ready")
            if observed.identity != current.lease.identity:
                self._set_phase(custody_id, TerritoryCustodyPhase.RETAINED, TerritoryCustodyPhase.RETIRING)
                raise StorageError("retained territory identity conflicts with provider lookup")
            target_epoch = current.source.attachment_epoch + 1
            self._write(
                """UPDATE territory_custody SET phase=?, target_episode=?,
                   target_attachment=?, target_epoch=? WHERE custody_id=? AND phase=?""",
                (
                    TerritoryCustodyPhase.CLAIMING.value,
                    episode_id.value,
                    attachment_id,
                    target_epoch,
                    custody_id,
                    TerritoryCustodyPhase.RETAINED.value,
                ),
                expected_rows=1,
            )
        try:
            binding = MotusAttachmentBinding._reclaim_exact(
                provider,
                current.lease.identity,
                workspace_archive_bytes=current.archive,
                input_digest=current.archive_digest,
            )
            attachment = EpisodeAttachment(
                episode_id=episode_id,
                snapshot=snapshot,
                binding=binding,
                attachment_id=attachment_id,
                attachment_epoch=target_epoch,
                deadline=deadline,
                admission=admission,
                target=target,
            )
        except Exception:
            with self._lock:
                self._set_phase(custody_id, TerritoryCustodyPhase.CLAIMING, TerritoryCustodyPhase.RETIRING)
            raise
        with self._lock:
            self._set_phase(custody_id, TerritoryCustodyPhase.CLAIMING, TerritoryCustodyPhase.ATTACHED)
        return attachment

    def recover(self) -> tuple[TerritoryCustodyRecord, ...]:
        """Fence ambiguous active/releasing custody and expire retained records."""

        self._fence.ensure()
        with self._lock:
            self._write(
                """UPDATE territory_custody SET phase=? WHERE phase IN (?, ?, ?)
                   OR (phase=? AND retain_until<=?)""",
                (
                    TerritoryCustodyPhase.RETIRING.value,
                    TerritoryCustodyPhase.RELEASING.value,
                    TerritoryCustodyPhase.CLAIMING.value,
                    TerritoryCustodyPhase.ATTACHED.value,
                    TerritoryCustodyPhase.RETAINED.value,
                    self._clock(),
                ),
            )
            rows = self._database.execute("SELECT * FROM territory_custody ORDER BY custody_id").fetchall()
            records = []
            for row in rows:
                try:
                    records.append(self._decode(row))
                except StorageError:
                    phase = self._salvage_corrupt(row)
                    if phase is TerritoryCustodyPhase.QUARANTINED:
                        raise StorageError("malformed territory identity was quarantined") from None
                    updated = self._database.execute(
                        "SELECT * FROM territory_custody WHERE custody_id=?", (str(row[0]),)
                    ).fetchone()
                    assert updated is not None
                    records.append(self._decode(updated))
            return tuple(records)

    def retire(self, custody_id: str, owner_id: str, provider: EnvironmentProvider) -> TerritoryCustodyRecord:
        """Destroy only the exact recorded lease and retain a bounded tombstone."""

        self._fence.ensure()
        with self._lock:
            current = self._required(custody_id)
            if current.owner_id != owner_id:
                raise StorageError("territory custody belongs to a different owner")
            if current.phase is TerritoryCustodyPhase.RETIRED:
                return current
            if current.phase is TerritoryCustodyPhase.RETAINED:
                self._set_phase(custody_id, TerritoryCustodyPhase.RETAINED, TerritoryCustodyPhase.RETIRING)
                current = self._required(custody_id)
            if current.phase is not TerritoryCustodyPhase.RETIRING:
                raise StorageError("territory custody is not safe to retire")
            observed = provider.lookup(current.lease.operation_id)
            if observed is not None and observed.identity != current.lease.identity:
                raise StorageError("territory retirement refuses a foreign current lease")
            lease = observed or current.lease
        cleanup = provider.destroy(lease)
        if cleanup.identity != current.lease.identity or not cleanup.verified:
            return self._required(custody_id)
        with self._lock:
            self._write(
                """UPDATE territory_custody SET phase=?, archive=NULL,
                   archive_digest=NULL, cleanup=? WHERE custody_id=? AND phase=?""",
                (
                    TerritoryCustodyPhase.RETIRED.value,
                    cleanup.disposition.value,
                    custody_id,
                    TerritoryCustodyPhase.RETIRING.value,
                ),
                expected_rows=1,
            )
            return self._required(custody_id)

    def lookup(self, custody_id: str) -> TerritoryCustodyRecord | None:
        self._fence.ensure()
        _text(custody_id, "territory custody id")
        with self._lock:
            row = self._database.execute("SELECT * FROM territory_custody WHERE custody_id=?", (custody_id,)).fetchone()
        return None if row is None else self._decode(row)

    def records(self) -> tuple[TerritoryCustodyRecord, ...]:
        self._fence.ensure()
        with self._lock:
            rows = self._database.execute("SELECT * FROM territory_custody ORDER BY custody_id").fetchall()
        return tuple(self._decode(row) for row in rows)

    def close(self) -> None:
        with self._lock:
            self._database.close()
        self._fence.close()

    def _accept_release(self, expected: TerritoryCustodyRecord, lease: EnvironmentLease, archive: bytes) -> None:
        if lease != expected.lease or len(archive) > MAX_WORKSPACE_ARCHIVE_BYTES:
            raise StorageError("territory release differs from durable transfer intent")
        digest = hashlib.sha256(archive).hexdigest()
        with self._lock:
            if expected.retain_until <= self._clock():
                self._set_phase(
                    expected.custody_id,
                    TerritoryCustodyPhase.RELEASING,
                    TerritoryCustodyPhase.RETIRING,
                )
                raise StorageError("territory retention expired during release")
            self._write(
                """UPDATE territory_custody SET phase=?, archive=?, archive_digest=?
                   WHERE custody_id=? AND generation=? AND phase=?""",
                (
                    TerritoryCustodyPhase.RETAINED.value,
                    archive,
                    digest,
                    expected.custody_id,
                    expected.generation,
                    TerritoryCustodyPhase.RELEASING.value,
                ),
                expected_rows=1,
            )

    def _required(self, custody_id: str) -> TerritoryCustodyRecord:
        record = self.lookup(custody_id)
        if record is None:
            raise StorageError("territory custody record is absent")
        return record

    def _set_phase(self, custody_id: str, expected: TerritoryCustodyPhase, phase: TerritoryCustodyPhase) -> None:
        self._write(
            "UPDATE territory_custody SET phase=? WHERE custody_id=? AND phase=?",
            (phase.value, custody_id, expected.value),
            expected_rows=1,
        )

    def _set_phase_raw(self, custody_id: str, phase: TerritoryCustodyPhase) -> None:
        self._write(
            """UPDATE territory_custody SET phase=?, capabilities='[]', retain_until=0,
               archive=NULL, archive_digest=NULL, target_episode=NULL,
               target_attachment=NULL, target_epoch=NULL, cleanup=NULL WHERE custody_id=?""",
            (phase.value, custody_id),
            expected_rows=1,
        )

    def _salvage_corrupt(self, row: tuple[object, ...]) -> TerritoryCustodyPhase:
        try:
            custody_id = _text(row[0], "territory custody id")
            _text(row[1], "territory custody owner")
            generation = _exact_int(row[2], "territory custody generation")
            if generation <= 0:
                raise ValueError
            AttachmentCoordinates(
                _text(row[4], "source episode"),
                _text(row[5], "source attachment"),
                _exact_int(row[6], "source epoch"),
            )
            LeaseIdentity(
                _text(row[7], "territory operation"),
                _text(row[8], "territory provider"),
                _text(row[9], "territory lease"),
            )
        except TypeError, ValueError:
            self._write(
                "UPDATE territory_custody SET phase=? WHERE custody_id=?",
                (TerritoryCustodyPhase.QUARANTINED.value, row[0]),
                expected_rows=1,
            )
            return TerritoryCustodyPhase.QUARANTINED
        self._set_phase_raw(custody_id, TerritoryCustodyPhase.RETIRING)
        return TerritoryCustodyPhase.RETIRING

    def _write(self, sql: str, parameters: tuple[object, ...], *, expected_rows: int | None = None) -> None:
        self._database.execute("BEGIN IMMEDIATE")
        try:
            cursor = self._database.execute(sql, parameters)
            if expected_rows is not None and cursor.rowcount != expected_rows:
                raise StorageError("territory custody write lost its expected state")
            self._database.commit()
        except BaseException:
            self._database.rollback()
            raise

    @classmethod
    def _decode(cls, row: tuple[object, ...]) -> TerritoryCustodyRecord:
        try:
            return cls._decode_validated(row)
        except StorageError:
            raise
        except json.JSONDecodeError, TypeError, ValueError:
            raise StorageError("territory custody record is malformed") from None

    @staticmethod
    def _decode_validated(row: tuple[object, ...]) -> TerritoryCustodyRecord:
        capabilities = json.loads(_text(row[10], "territory capabilities"))
        if not isinstance(capabilities, list) or any(not isinstance(value, str) for value in capabilities):
            raise StorageError("territory custody capabilities are malformed")
        capability_values = cast(list[str], capabilities)
        return TerritoryCustodyRecord(
            custody_id=_text(row[0], "territory custody id"),
            owner_id=_text(row[1], "territory custody owner"),
            generation=_exact_int(row[2], "territory custody generation"),
            phase=TerritoryCustodyPhase(_text(row[3], "territory custody phase")),
            source=AttachmentCoordinates(
                _text(row[4], "source episode"),
                _text(row[5], "source attachment"),
                _exact_int(row[6], "source epoch"),
            ),
            lease=EnvironmentLease(
                _text(row[7], "territory operation"),
                _text(row[8], "territory provider"),
                _text(row[9], "territory lease"),
                frozenset(capability_values),
                LeaseState.READY,
            ),
            retain_until=_exact_number(row[11], "territory retention expiry"),
            archive=_optional_bytes(row[12], "territory archive"),
            archive_digest=_optional_text(row[13], "territory archive digest"),
            target_episode_id=_optional_text(row[14], "territory target episode"),
            target_attachment_id=_optional_text(row[15], "territory target attachment"),
            target_epoch=_optional_int(row[16], "territory target epoch"),
            cleanup=None if row[17] is None else CleanupDisposition(_text(row[17], "territory cleanup disposition")),
        )

    def _prepare_path(self) -> None:
        parent = self.path.parent
        if parent.is_symlink():
            raise StorageSecurityError("territory custody parent must not be a symlink")
        if not parent.exists():
            parent.mkdir(mode=0o700, parents=True)
            parent.chmod(0o700)
        metadata = parent.lstat()
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o700
            or metadata.st_uid != os.geteuid()
        ):
            raise StorageSecurityError("territory custody parent must be an owned mode-0700 directory")
        if self.path.is_symlink():
            raise StorageSecurityError("territory custody file must not be a symlink")
        if not self.path.exists():
            descriptor = os.open(
                self.path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                0o600,
            )
            os.close(descriptor)
        metadata = self.path.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_uid != os.geteuid()
        ):
            raise StorageSecurityError("territory custody file must be owned regular mode-0600")


class _WriterFence:
    def __init__(self, database: Path) -> None:
        self.path = database.with_name(f".{database.name}.writer.lock")
        self._pid = os.getpid()
        descriptor = os.open(self.path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_uid != os.geteuid()
            ):
                raise StorageSecurityError("territory custody writer fence must be owned regular mode-0600")
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            os.close(descriptor)
            if error.errno in (errno.EACCES, errno.EAGAIN):
                raise StorageError("territory custody already has a live writer") from error
            raise
        except BaseException:
            os.close(descriptor)
            raise
        self._descriptor: int | None = descriptor

    def ensure(self) -> None:
        if self._descriptor is None:
            raise StorageError("territory custody writer is closed")
        if os.getpid() != self._pid:
            raise StorageError("territory custody cannot be used across fork")

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


__all__: list[str] = []
