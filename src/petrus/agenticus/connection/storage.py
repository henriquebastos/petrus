"""Pluggable CAS storage and a private SQLite Agent Connection store."""

from __future__ import annotations

import base64
import json
import os
import sqlite3
import stat
import threading
from collections.abc import Iterable
from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
from pathlib import Path
from typing import Protocol, TypeAlias, cast


AuditValue: TypeAlias = str | int | float | bool | None
AuditDetails: TypeAlias = tuple[tuple[str, AuditValue], ...]
_CONNECTION_STATUSES = {
    "ready",
    "refreshing",
    "revoked",
    "erasure_pending",
    "reauthorization_required",
}
_LEASE_MODES = {"read", "refresh"}


class StorageError(RuntimeError):
    """The host custody store could not preserve its contract."""


class StorageSecurityError(StorageError):
    """The store path has a filesystem shape unsafe for encrypted authority."""


@dataclass(frozen=True, order=True)
class StoredHost:
    host_id: str
    enrollment_epoch: int
    active: bool


@dataclass(frozen=True, order=True)
class StoredConnection:
    connection_id: str
    provider: str
    account_fingerprint: str
    profile: str
    status: str
    authority_epoch: int
    state_version: int
    encrypted_state: bytes | None
    state_digest: str | None


@dataclass(frozen=True, order=True)
class StoredLease:
    lease_id: str
    attachment_id: str
    connection_id: str
    host_id: str
    host_epoch: int
    mode: str
    authority_epoch: int
    base_version: int
    expires_at: float
    activated: bool = False
    released: bool = False
    release_reason: str | None = None


@dataclass(frozen=True)
class AuditRecord:
    """One secret-free custody operation record outside canonical History."""

    sequence: int
    operation_id: str
    event_kind: str
    connection_id: str | None
    host_id: str | None
    lease_id: str | None
    details: AuditDetails = ()

    def detail(self, name: str) -> AuditValue:
        return dict(self.details)[name]


@dataclass(frozen=True)
class StorageSnapshot:
    """One immutable complete custody state at a host-store CAS revision."""

    revision: int = 0
    hosts: tuple[StoredHost, ...] = ()
    connections: tuple[StoredConnection, ...] = ()
    leases: tuple[StoredLease, ...] = ()
    audit: tuple[AuditRecord, ...] = ()


class ConnectionStorage(Protocol):
    """Host storage operations needed by the provider-neutral custody state machine."""

    def load(self) -> StorageSnapshot:
        """Load one coherent immutable snapshot."""
        ...

    def compare_and_swap(self, expected_revision: int, replacement: StorageSnapshot) -> bool:
        """Publish replacement only if expected_revision remains current."""
        ...

    def close(self) -> None:
        """Release host storage resources without changing custody state."""
        ...


class SqliteConnectionStorage:
    """SQLite CAS storage containing only encrypted state and safe metadata."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._prepare_path()
        self._lock = threading.Lock()
        self._database = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False, timeout=5)
        os.chmod(self.path, 0o600)
        self._database.execute("PRAGMA journal_mode = DELETE")
        self._database.execute("PRAGMA synchronous = FULL")
        self._database.execute(
            """
            CREATE TABLE IF NOT EXISTS connection_custody (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                revision INTEGER NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        self._database.execute(
            "INSERT OR IGNORE INTO connection_custody (singleton, revision, payload) VALUES (1, 0, ?)",
            (_encode(StorageSnapshot()),),
        )

    def load(self) -> StorageSnapshot:
        with self._lock:
            row = self._database.execute(
                "SELECT revision, payload FROM connection_custody WHERE singleton = 1"
            ).fetchone()
        if row is None:
            raise StorageError("connection custody state is absent")
        snapshot = _decode(str(row[1]))
        revision = int(row[0])
        if snapshot.revision != revision:
            raise StorageError("connection custody revision diverges from its payload")
        return snapshot

    def compare_and_swap(self, expected_revision: int, replacement: StorageSnapshot) -> bool:
        if replacement.revision != expected_revision + 1:
            raise ValueError("replacement revision must advance expected revision exactly once")
        validate_snapshot(replacement)
        payload = _encode(replacement)
        with self._lock:
            self._database.execute("BEGIN IMMEDIATE")
            try:
                updated = self._database.execute(
                    """
                    UPDATE connection_custody SET revision = ?, payload = ?
                    WHERE singleton = 1 AND revision = ?
                    """,
                    (replacement.revision, payload, expected_revision),
                )
                if updated.rowcount != 1:
                    self._database.rollback()
                    return False
                self._database.commit()
            except BaseException:
                self._database.rollback()
                raise
        return True

    def close(self) -> None:
        with self._lock:
            self._database.close()

    def _prepare_path(self) -> None:
        parent = self.path.parent
        self._prepare_parent(parent)
        if self.path.is_symlink():
            raise StorageSecurityError("connection storage file must not be a symlink")
        if not self.path.exists():
            self._create_private_file()
        self._assert_private_file()

    @staticmethod
    def _prepare_parent(parent: Path) -> None:
        if parent.is_symlink():
            raise StorageSecurityError("connection storage parent must not be a symlink")
        if not parent.exists():
            parent.mkdir(mode=0o700, parents=True)
            parent.chmod(0o700)
        parent_metadata = parent.lstat()
        if stat.S_ISLNK(parent_metadata.st_mode):
            raise StorageSecurityError("connection storage parent must not be a symlink")
        if not stat.S_ISDIR(parent_metadata.st_mode):
            raise StorageSecurityError("connection storage parent must be a directory")
        if stat.S_IMODE(parent_metadata.st_mode) != 0o700:
            raise StorageSecurityError("connection storage parent must have mode 0700")

    def _create_private_file(self) -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(self.path, flags, 0o600)
        except FileExistsError:
            return
        try:
            os.fchmod(descriptor, 0o600)
        finally:
            os.close(descriptor)

    def _assert_private_file(self) -> None:
        metadata = self.path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise StorageSecurityError("connection storage file must not be a symlink")
        if not stat.S_ISREG(metadata.st_mode):
            raise StorageSecurityError("connection storage path must be a regular file")
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            raise StorageSecurityError("connection storage file must have mode 0600")


def validate_snapshot(snapshot: StorageSnapshot) -> StorageSnapshot:
    """Refuse host state that the custody writer could not have published."""
    if not isinstance(snapshot, StorageSnapshot):
        raise StorageError("connection storage must return StorageSnapshot")
    if type(snapshot.revision) is not int or snapshot.revision < 0:
        raise StorageError("connection custody revision must be a nonnegative integer")
    if snapshot.revision != len(snapshot.audit):
        raise StorageError("connection custody revision must equal its operation count")
    _validate_hosts(snapshot.hosts)
    _validate_connections(snapshot.connections)
    _validate_leases(snapshot)
    _validate_audit(snapshot.audit)
    return snapshot


def _validate_hosts(hosts: tuple[StoredHost, ...]) -> None:
    _unique((host.host_id for host in hosts), "host identities")
    if hosts != tuple(sorted(hosts)):
        raise StorageError("connection custody hosts must be canonically ordered")
    for host in hosts:
        if not isinstance(host, StoredHost):
            raise StorageError("connection custody hosts must contain StoredHost values")
        _stored_text(host.host_id, "host identity")
        _positive_integer(host.enrollment_epoch, "host enrollment epoch")
        if type(host.active) is not bool:
            raise StorageError("host active state must be boolean")


def _validate_connections(connections: tuple[StoredConnection, ...]) -> None:
    _unique((connection.connection_id for connection in connections), "connection identities")
    if connections != tuple(sorted(connections)):
        raise StorageError("connections must be canonically ordered")
    for connection in connections:
        if not isinstance(connection, StoredConnection):
            raise StorageError("connections must contain StoredConnection values")
        for value, name in (
            (connection.connection_id, "connection identity"),
            (connection.provider, "provider identity"),
            (connection.account_fingerprint, "account fingerprint"),
            (connection.profile, "connection profile"),
        ):
            _stored_text(value, name)
        if connection.status not in _CONNECTION_STATUSES:
            raise StorageError("connection status is not supported")
        _positive_integer(connection.authority_epoch, "connection authority epoch")
        _positive_integer(connection.state_version, "connection state version")
        _validate_ciphertext(connection)


def _validate_ciphertext(connection: StoredConnection) -> None:
    if (connection.encrypted_state is None) != (connection.state_digest is None):
        raise StorageError("encrypted connection state and digest must be present or absent together")
    if connection.encrypted_state is None:
        if connection.status not in {"reauthorization_required", "revoked", "erasure_pending"}:
            raise StorageError("materializable connection state may not omit encrypted state")
        return
    if not isinstance(connection.encrypted_state, bytes) or not connection.encrypted_state:
        raise StorageError("encrypted connection state must be non-empty bytes")
    if connection.state_digest != sha256(connection.encrypted_state).hexdigest():
        raise StorageError("encrypted connection state digest does not match its bytes")


def _validate_leases(snapshot: StorageSnapshot) -> None:
    leases = snapshot.leases
    _unique((lease.lease_id for lease in leases), "lease identities")
    _unique((lease.attachment_id for lease in leases), "attachment identities")
    if leases != tuple(sorted(leases)):
        raise StorageError("materialization leases must be canonically ordered")
    hosts = {host.host_id: host for host in snapshot.hosts}
    connections = {connection.connection_id: connection for connection in snapshot.connections}
    for lease in leases:
        _validate_lease(lease, hosts, connections)
    _validate_active_lease_sets(leases, connections)


def _validate_lease(
    lease: StoredLease,
    hosts: dict[str, StoredHost],
    connections: dict[str, StoredConnection],
) -> None:
    _validate_lease_value(lease)
    if lease.host_id not in hosts or lease.connection_id not in connections:
        raise StorageError("materialization lease references unknown authority")
    if not lease.released:
        _validate_live_lease_authority(lease, hosts[lease.host_id], connections[lease.connection_id])


def _validate_lease_value(lease: StoredLease) -> None:
    if not isinstance(lease, StoredLease):
        raise StorageError("materialization leases must contain StoredLease values")
    for value, name in (
        (lease.lease_id, "lease identity"),
        (lease.attachment_id, "attachment identity"),
        (lease.connection_id, "lease connection identity"),
        (lease.host_id, "lease host identity"),
    ):
        _stored_text(value, name)
    if lease.mode not in _LEASE_MODES:
        raise StorageError("materialization lease mode is not supported")
    for value, name in (
        (lease.host_epoch, "lease host epoch"),
        (lease.authority_epoch, "lease authority epoch"),
        (lease.base_version, "lease base version"),
    ):
        _positive_integer(value, name)
    if (
        isinstance(lease.expires_at, bool)
        or not isinstance(lease.expires_at, int | float)
        or not isfinite(lease.expires_at)
    ):
        raise StorageError("materialization lease expiry must be a finite number")
    if type(lease.activated) is not bool or type(lease.released) is not bool:
        raise StorageError("materialization lease flags must be boolean")
    if lease.activated and lease.mode != "refresh":
        raise StorageError("only refresh custody may be activated")
    if lease.released != (lease.release_reason is not None):
        raise StorageError("released materialization lease must carry exactly one release reason")


def _validate_live_lease_authority(
    lease: StoredLease,
    host: StoredHost,
    connection: StoredConnection,
) -> None:
    if not host.active or host.enrollment_epoch != lease.host_epoch:
        raise StorageError("active materialization lease references stale host authority")
    if connection.authority_epoch != lease.authority_epoch or connection.state_version != lease.base_version:
        raise StorageError("active materialization lease references stale connection authority")


def _validate_active_lease_sets(leases: tuple[StoredLease, ...], connections: dict[str, StoredConnection]) -> None:
    for connection_id, connection in connections.items():
        active = tuple(lease for lease in leases if lease.connection_id == connection_id and not lease.released)
        refresh = tuple(lease for lease in active if lease.mode == "refresh")
        if refresh and (len(refresh) != 1 or len(active) != 1):
            raise StorageError("refresh custody must be the only active materialization")
        if refresh and connection.status != "refreshing":
            raise StorageError("active refresh custody requires refreshing connection state")
        if not refresh and connection.status == "refreshing":
            raise StorageError("refreshing connection state requires active refresh custody")
        if active and connection.status not in {"ready", "refreshing"}:
            raise StorageError("fail-closed connection state cannot retain active materializations")


def _validate_audit(audit: tuple[AuditRecord, ...]) -> None:
    _unique((record.operation_id for record in audit), "operation identities")
    for expected, record in enumerate(audit, 1):
        if not isinstance(record, AuditRecord) or record.sequence != expected:
            raise StorageError("custody operation records must have dense canonical sequences")
        _stored_text(record.operation_id, "operation identity")
        _stored_text(record.event_kind, "operation event kind")
        for identity in (record.connection_id, record.host_id, record.lease_id):
            if identity is not None:
                _stored_text(identity, "operation subject identity")
        if record.details != tuple(sorted(record.details)):
            raise StorageError("operation details must be canonically ordered")
        if any(not _audit_value(value) for _, value in record.details):
            raise StorageError("operation details must contain safe scalar values")


def _unique(values: Iterable[object], name: str) -> None:
    items = tuple(values)
    if len(set(items)) != len(items):
        raise StorageError(f"{name} must be unique")


def _stored_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or any(ord(item) < 32 for item in value):
        raise StorageError(f"{name} must be a non-empty trimmed string")
    return value


def _positive_integer(value: object, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise StorageError(f"{name} must be a positive integer")
    return value


def _encode(snapshot: StorageSnapshot) -> str:
    validate_snapshot(snapshot)
    data = {
        "schema_version": 1,
        "revision": snapshot.revision,
        "hosts": [
            {
                "host_id": host.host_id,
                "enrollment_epoch": host.enrollment_epoch,
                "active": host.active,
            }
            for host in snapshot.hosts
        ],
        "connections": [
            {
                "connection_id": connection.connection_id,
                "provider": connection.provider,
                "account_fingerprint": connection.account_fingerprint,
                "profile": connection.profile,
                "status": connection.status,
                "authority_epoch": connection.authority_epoch,
                "state_version": connection.state_version,
                "encrypted_state": (
                    None
                    if connection.encrypted_state is None
                    else base64.b64encode(connection.encrypted_state).decode("ascii")
                ),
                "state_digest": connection.state_digest,
            }
            for connection in snapshot.connections
        ],
        "leases": [
            {
                "lease_id": lease.lease_id,
                "attachment_id": lease.attachment_id,
                "connection_id": lease.connection_id,
                "host_id": lease.host_id,
                "host_epoch": lease.host_epoch,
                "mode": lease.mode,
                "authority_epoch": lease.authority_epoch,
                "base_version": lease.base_version,
                "expires_at": lease.expires_at,
                "activated": lease.activated,
                "released": lease.released,
                "release_reason": lease.release_reason,
            }
            for lease in snapshot.leases
        ],
        "audit": [
            {
                "sequence": record.sequence,
                "operation_id": record.operation_id,
                "event_kind": record.event_kind,
                "connection_id": record.connection_id,
                "host_id": record.host_id,
                "lease_id": record.lease_id,
                "details": dict(record.details),
            }
            for record in snapshot.audit
        ],
    }
    return json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _decode(payload: str) -> StorageSnapshot:
    try:
        data = _object(json.loads(payload))
        if _integer(data["schema_version"]) != 1:
            raise ValueError
        return validate_snapshot(
            StorageSnapshot(
                revision=_integer(data["revision"]),
                hosts=tuple(_decode_host(item) for item in _array(data["hosts"])),
                connections=tuple(_decode_connection(item) for item in _array(data["connections"])),
                leases=tuple(_decode_lease(item) for item in _array(data["leases"])),
                audit=tuple(_decode_audit(item) for item in _array(data["audit"])),
            )
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise StorageError("connection custody payload is invalid") from error


def _decode_host(item: object) -> StoredHost:
    data = _object(item)
    return StoredHost(
        host_id=_string(data["host_id"]),
        enrollment_epoch=_integer(data["enrollment_epoch"]),
        active=_boolean(data["active"]),
    )


def _decode_connection(item: object) -> StoredConnection:
    data = _object(item)
    encrypted = data["encrypted_state"]
    return StoredConnection(
        connection_id=_string(data["connection_id"]),
        provider=_string(data["provider"]),
        account_fingerprint=_string(data["account_fingerprint"]),
        profile=_string(data["profile"]),
        status=_string(data["status"]),
        authority_epoch=_integer(data["authority_epoch"]),
        state_version=_integer(data["state_version"]),
        encrypted_state=None if encrypted is None else base64.b64decode(_string(encrypted), validate=True),
        state_digest=_optional_string(data["state_digest"]),
    )


def _decode_lease(item: object) -> StoredLease:
    data = _object(item)
    return StoredLease(
        lease_id=_string(data["lease_id"]),
        attachment_id=_string(data["attachment_id"]),
        connection_id=_string(data["connection_id"]),
        host_id=_string(data["host_id"]),
        host_epoch=_integer(data["host_epoch"]),
        mode=_string(data["mode"]),
        authority_epoch=_integer(data["authority_epoch"]),
        base_version=_integer(data["base_version"]),
        expires_at=_number(data["expires_at"]),
        activated=_boolean(data["activated"]),
        released=_boolean(data["released"]),
        release_reason=_optional_string(data["release_reason"]),
    )


def _decode_audit(item: object) -> AuditRecord:
    data = _object(item)
    details = _object(data["details"])
    safe_details: list[tuple[str, AuditValue]] = []
    for key, value in details.items():
        if not _audit_value(value):
            raise ValueError
        safe_details.append((key, cast(AuditValue, value)))
    return AuditRecord(
        sequence=_integer(data["sequence"]),
        operation_id=_string(data["operation_id"]),
        event_kind=_string(data["event_kind"]),
        connection_id=_optional_string(data["connection_id"]),
        host_id=_optional_string(data["host_id"]),
        lease_id=_optional_string(data["lease_id"]),
        details=tuple(sorted(safe_details)),
    )


def _audit_value(value: object) -> bool:
    return value is None or type(value) in {str, int, bool} or (type(value) is float and isfinite(value))


def _object(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError
    return cast(dict[str, object], value)


def _array(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError
    return cast(list[object], value)


def _string(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError
    return value


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    return _string(value)


def _integer(value: object) -> int:
    if type(value) is not int:
        raise ValueError
    return value


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not isfinite(value):
        raise ValueError
    return float(value)


def _boolean(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError
    return value
