"""Production Agent Connection authority, custody, and stale-writer fencing."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from hashlib import sha256
from math import isfinite
from typing import Generic, TypeAlias, TypeVar

from petrus.agenticus.connection.key import KeyContext, KeyErasureEvidence, KeyOperations
from petrus.agenticus.connection.materialization import (
    CleanupEvidence,
    CleanupSummary,
    MaterializedState,
    PrivateFileMaterializer,
)
from petrus.agenticus.connection.storage import (
    AuditRecord,
    AuditValue,
    ConnectionStorage,
    StorageSnapshot,
    StoredConnection,
    StoredHost,
    StoredLease,
    validate_snapshot,
)


LOGGER = logging.getLogger("petrus.agenticus.connection.custody")
_MAX_TEXT_BYTES = 256
_CAS_ATTEMPTS = 8
T = TypeVar("T")


class LeaseMode(StrEnum):
    READ = "read"
    REFRESH = "refresh"


class ConnectionStatus(StrEnum):
    READY = "ready"
    REFRESHING = "refreshing"
    REVOKED = "revoked"
    ERASURE_PENDING = "erasure_pending"
    REAUTHORIZATION_REQUIRED = "reauthorization_required"


class CustodyError(RuntimeError):
    """Agent Connection custody refused an operation without exposing authority."""


class HostNotEnrolled(CustodyError):
    pass


class LeaseConflict(CustodyError):
    pass


class StaleCustody(CustodyError):
    pass


class StaleAttachment(CustodyError):
    pass


class ReauthorizationRequired(CustodyError):
    pass


class OperationConflict(CustodyError):
    pass


class StorageContention(CustodyError):
    pass


class OpaqueState:
    """An erasable provider-native state buffer whose representation is redacted."""

    def __init__(self, content: bytes | bytearray) -> None:
        if not isinstance(content, bytes | bytearray) or not content:
            raise ValueError("opaque Agent Connection state must be non-empty bytes")
        self._content = bytearray(content)
        self._erased = False

    @property
    def erased(self) -> bool:
        return self._erased

    def _borrow(self) -> bytearray:
        if self._erased:
            raise CustodyError("opaque Agent Connection state has been erased")
        return self._content

    def erase(self) -> None:
        _erase_buffer(self._content)
        self._erased = True

    def __repr__(self) -> str:
        state = "erased" if self._erased else "present"
        return f"OpaqueState(<{state}>)"


@dataclass(frozen=True, order=True)
class ConnectionIdentity:
    """Stable logical connection identity and nonsecret provider metadata."""

    connection_id: str
    provider: str
    account_fingerprint: str
    profile: str

    def __post_init__(self) -> None:
        for value, name in (
            (self.connection_id, "connection"),
            (self.provider, "provider"),
            (self.account_fingerprint, "account fingerprint"),
            (self.profile, "profile"),
        ):
            _text(value, name)


@dataclass(frozen=True)
class ConnectionView:
    identity: ConnectionIdentity
    status: ConnectionStatus
    authority_epoch: int
    state_version: int
    state_digest: str | None


@dataclass(frozen=True)
class AttachmentFence:
    attachment_id: str
    lease_id: str
    connection_id: str
    host_id: str
    host_epoch: int
    authority_epoch: int
    base_version: int


@dataclass(frozen=True)
class Materialization:
    fence: AttachmentFence
    mode: LeaseMode
    expires_at: float
    home: MaterializedState

    def __repr__(self) -> str:
        return (
            "Materialization("
            f"attachment_id={self.fence.attachment_id!r}, connection_id={self.fence.connection_id!r}, "
            f"host_id={self.fence.host_id!r}, mode={self.mode.value!r}, home={self.home!r})"
        )


@dataclass(frozen=True)
class OperationView:
    operation_id: str
    event_kind: str
    connection_id: str | None
    host_id: str | None
    lease_id: str | None
    details: tuple[tuple[str, AuditValue], ...]


@dataclass(frozen=True)
class PublicationResult:
    operation_id: str
    connection: ConnectionView
    cleanup: CleanupEvidence


@dataclass(frozen=True)
class ReleaseResult:
    operation_id: str
    cleanup: CleanupEvidence


@dataclass(frozen=True)
class RenewalResult:
    operation_id: str
    expires_at: float


@dataclass(frozen=True)
class HostRemoval:
    operation_id: str
    host_id: str
    canceled_leases: int
    cleanup: CleanupSummary
    offline_erasure_limit: bool = True


@dataclass(frozen=True)
class RevocationResult:
    operation_id: str
    connection: ConnectionView
    cleanup: CleanupSummary
    provider_revocation: str = "not_claimed"
    offline_erasure_limit: bool = True


@dataclass(frozen=True)
class ErasureResult:
    operation_id: str
    connection: ConnectionView
    key_erasure: KeyErasureEvidence
    cleanup: CleanupSummary
    physical_media_erasure_guaranteed: bool = False


@dataclass(frozen=True)
class RecoveryResult:
    operation_id: str
    expired_leases: int
    ambiguous_connections: tuple[str, ...]
    cleanup: CleanupSummary


@dataclass(frozen=True)
class AdmissionResult:
    operation_id: str
    purpose: str
    attachment_id: str


@dataclass(frozen=True)
class _Change(Generic[T]):
    snapshot: StorageSnapshot
    value: T
    details: Mapping[str, AuditValue]
    cleanup_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Commit(Generic[T]):
    value: T
    cleanup: CleanupSummary


Transform: TypeAlias = Callable[[StorageSnapshot], _Change[T]]


class AgentConnectionCustody:
    """Installation-neutral custody machinery over host storage, keys, and files."""

    def __init__(
        self,
        storage: ConnectionStorage,
        keys: KeyOperations,
        materializer: PrivateFileMaterializer,
        *,
        clock: Callable[[], float],
    ) -> None:
        self._storage = storage
        self._keys = keys
        self._materializer = materializer
        self._clock = clock

    def enroll_host(self, host_id: str, *, operation_id: str) -> None:
        _text(host_id, "host")

        def change(snapshot: StorageSnapshot) -> _Change[None]:
            now = self._now()
            reconciled, expired_ids, ambiguous = _reconcile_expired(snapshot, now)
            hosts = _hosts(reconciled)
            current = hosts.get(host_id)
            epoch = 1 if current is None else current.enrollment_epoch + 1
            hosts[host_id] = StoredHost(host_id, epoch, True)
            affected = _active_leases(reconciled, now, host_id=host_id)
            updated = _replace_hosts(reconciled, hosts)
            updated = _release_leases(updated, affected, "host_reenrolled")
            updated, newly_ambiguous = _settle_released_refreshes(updated, affected)
            details: dict[str, AuditValue] = {
                "enrollment_epoch": epoch,
                "canceled_leases": len(affected),
                "expired_leases": len(expired_ids),
                "ambiguous_connections": len(set(ambiguous) | set(newly_ambiguous)),
            }
            cleanup = expired_ids + tuple(lease.attachment_id for lease in affected)
            return _Change(updated, None, details, cleanup)

        self._commit(operation_id, "host.enrolled", change, host_id=host_id)

    def remove_host(self, host_id: str, *, operation_id: str) -> HostRemoval:
        _text(host_id, "host")

        def change(snapshot: StorageSnapshot) -> _Change[int]:
            now = self._now()
            reconciled, expired_ids, _ = _reconcile_expired(snapshot, now)
            host = _active_host(reconciled, host_id)
            hosts = _hosts(reconciled)
            hosts[host_id] = replace(host, enrollment_epoch=host.enrollment_epoch + 1, active=False)
            affected = _active_leases(reconciled, now, host_id=host_id)
            updated = _replace_hosts(reconciled, hosts)
            updated = _release_leases(updated, affected, "host_removed")
            updated, ambiguous = _settle_released_refreshes(updated, affected)
            details: dict[str, AuditValue] = {
                "canceled_leases": len(affected),
                "ambiguous_connections": len(ambiguous),
                "offline_erasure_limit": True,
            }
            cleanup = expired_ids + tuple(lease.attachment_id for lease in affected)
            return _Change(updated, len(affected), details, cleanup)

        committed = self._commit(operation_id, "host.removed", change, host_id=host_id)
        return HostRemoval(operation_id, host_id, committed.value, committed.cleanup)

    def authorize(
        self,
        identity: ConnectionIdentity,
        opaque_state: OpaqueState,
        *,
        operation_id: str,
    ) -> ConnectionView:
        if not isinstance(identity, ConnectionIdentity):
            raise TypeError("connection identity must be ConnectionIdentity")
        if not isinstance(opaque_state, OpaqueState):
            raise TypeError("opaque state must be OpaqueState")
        _operation_id(operation_id)
        initial = self._load()
        current = _connections(initial).get(identity.connection_id)
        if current is None:
            authority_epoch, state_version, event_kind = 1, 1, "connection.authorized"
        else:
            if current.status != ConnectionStatus.REAUTHORIZATION_REQUIRED.value:
                opaque_state.erase()
                raise CustodyError(f"connection {identity.connection_id!r} is already authorized")
            if not _identity_matches(current, identity):
                opaque_state.erase()
                raise CustodyError(
                    f"connection {identity.connection_id!r} cannot be rebound to different provider authority"
                )
            authority_epoch = current.authority_epoch + 1
            state_version = current.state_version + 1
            event_kind = "connection.reauthorized"
        encrypted = self._seal(identity.connection_id, authority_epoch, state_version, opaque_state)

        def change(snapshot: StorageSnapshot) -> _Change[ConnectionView]:
            existing = _connections(snapshot).get(identity.connection_id)
            if not _same_connection_generation(existing, current):
                raise StorageContention(f"connection {identity.connection_id!r} changed during authorization")
            stored = StoredConnection(
                identity.connection_id,
                identity.provider,
                identity.account_fingerprint,
                identity.profile,
                ConnectionStatus.READY.value,
                authority_epoch,
                state_version,
                encrypted,
                _digest(encrypted),
            )
            updated = _replace_connection(snapshot, stored)
            details: dict[str, AuditValue] = {
                "authority_epoch": authority_epoch,
                "state_version": state_version,
            }
            return _Change(updated, _view(stored), details)

        return self._commit(operation_id, event_kind, change, connection_id=identity.connection_id).value

    def materialize(
        self,
        connection_id: str,
        host_id: str,
        *,
        mode: LeaseMode,
        ttl: float,
        operation_id: str,
    ) -> Materialization:
        _text(connection_id, "connection")
        _text(host_id, "host")
        if not isinstance(mode, LeaseMode):
            raise TypeError("materialization mode must be LeaseMode")
        _positive_ttl(ttl)
        suffix = sha256(_operation_id(operation_id).encode()).hexdigest()[:32]
        lease_id = f"lease-{suffix}"
        attachment_id = f"attachment-{suffix}"
        now = self._now()
        expires_at = _finite_time(now + ttl, "materialization lease expiry")
        self._reconcile_expired_before(operation_id, now)

        def change(snapshot: StorageSnapshot) -> _Change[tuple[StoredConnection, StoredLease]]:
            reconciled, expired_ids, ambiguous = _reconcile_expired(snapshot, now)
            host = _active_host(reconciled, host_id)
            connection = _connection(reconciled, connection_id)
            _require_materializable(connection)
            active = _active_leases(reconciled, now, connection_id=connection_id)
            if mode is LeaseMode.REFRESH and active:
                raise LeaseConflict(
                    f"connection {connection_id!r} cannot grant refresh custody while materializations are active"
                )
            lease = StoredLease(
                lease_id,
                attachment_id,
                connection_id,
                host_id,
                host.enrollment_epoch,
                mode.value,
                connection.authority_epoch,
                connection.state_version,
                expires_at,
            )
            leases = _leases(reconciled)
            leases[lease_id] = lease
            updated = _replace_leases(reconciled, leases)
            if mode is LeaseMode.REFRESH:
                updated = _replace_connection(updated, replace(connection, status=ConnectionStatus.REFRESHING.value))
            details: dict[str, AuditValue] = {
                "mode": mode.value,
                "authority_epoch": connection.authority_epoch,
                "base_version": connection.state_version,
                "expired_leases": len(expired_ids),
                "ambiguous_connections": len(ambiguous),
            }
            return _Change(updated, (connection, lease), details, expired_ids)

        committed = self._commit(
            operation_id,
            "materialization.acquired",
            change,
            connection_id=connection_id,
            host_id=host_id,
            lease_id=lease_id,
        )
        connection, lease = committed.value
        if connection.encrypted_state is None:
            self._abort_materialization(lease, operation_id)
            raise ReauthorizationRequired(f"connection {connection_id!r} requires explicit reauthorization")
        try:
            plaintext = self._keys.open(
                KeyContext(connection_id, connection.authority_epoch, connection.state_version),
                connection.encrypted_state,
            )
            try:
                home = self._materializer.materialize(attachment_id, plaintext)
            finally:
                _erase_buffer(plaintext)
        except BaseException:
            self._abort_materialization(lease, operation_id)
            raise
        return Materialization(_fence(lease), mode, expires_at, home)

    def activate(self, materialization: Materialization, *, operation_id: str) -> None:
        _materialization(materialization)
        if materialization.mode is not LeaseMode.REFRESH:
            raise CustodyError("only refresh custody can enter provider-mutation state")
        fence = materialization.fence

        def change(snapshot: StorageSnapshot) -> _Change[None]:
            lease = _require_current_lease(snapshot, fence, self._now(), LeaseMode.REFRESH)
            leases = _leases(snapshot)
            leases[lease.lease_id] = replace(lease, activated=True)
            details: dict[str, AuditValue] = {"authority_epoch": fence.authority_epoch}
            return _Change(_replace_leases(snapshot, leases), None, details)

        self._commit(
            operation_id,
            "materialization.activated",
            change,
            connection_id=fence.connection_id,
            host_id=fence.host_id,
            lease_id=fence.lease_id,
        )

    def renew(self, materialization: Materialization, *, ttl: float, operation_id: str) -> RenewalResult:
        _materialization(materialization)
        _positive_ttl(ttl)
        fence = materialization.fence

        def change(snapshot: StorageSnapshot) -> _Change[float]:
            now = self._now()
            expires_at = _finite_time(now + ttl, "materialization lease expiry")
            _active_host(snapshot, fence.host_id)
            lease = _require_current_lease(snapshot, fence, now, materialization.mode)
            leases = _leases(snapshot)
            leases[lease.lease_id] = replace(lease, expires_at=expires_at)
            details: dict[str, AuditValue] = {"expires_at": expires_at}
            return _Change(_replace_leases(snapshot, leases), expires_at, details)

        committed = self._commit(
            operation_id,
            "materialization.renewed",
            change,
            connection_id=fence.connection_id,
            host_id=fence.host_id,
            lease_id=fence.lease_id,
        )
        return RenewalResult(operation_id, committed.value)

    def checkpoint(self, materialization: Materialization, *, operation_id: str) -> PublicationResult:
        _materialization(materialization)
        _operation_id(operation_id)
        fence = materialization.fence
        try:
            initial = self._load()
            initial_lease = _require_current_lease(initial, fence, self._now(), LeaseMode.REFRESH)
            if not initial_lease.activated:
                raise CustodyError("refresh custody must be activated before publishing provider state")
            returned = bytearray(materialization.home.read())
            if not returned:
                raise CustodyError("provider returned empty opaque state")
            next_version = fence.base_version + 1
            encrypted = self._seal_buffer(
                fence.connection_id,
                fence.authority_epoch,
                next_version,
                returned,
            )

            def change(snapshot: StorageSnapshot) -> _Change[ConnectionView]:
                lease = _require_current_lease(snapshot, fence, self._now(), LeaseMode.REFRESH)
                current = _connection(snapshot, fence.connection_id)
                if (
                    not lease.activated
                    or current.authority_epoch != fence.authority_epoch
                    or current.state_version != fence.base_version
                    or current.status != ConnectionStatus.REFRESHING.value
                ):
                    raise StaleCustody(f"lease is no longer current for connection {fence.connection_id!r}")
                accepted = replace(
                    current,
                    status=ConnectionStatus.READY.value,
                    state_version=next_version,
                    encrypted_state=encrypted,
                    state_digest=_digest(encrypted),
                )
                leases = _leases(snapshot)
                leases[lease.lease_id] = replace(lease, released=True, release_reason="checkpointed")
                updated = _replace_connection(_replace_leases(snapshot, leases), accepted)
                details: dict[str, AuditValue] = {
                    "base_version": fence.base_version,
                    "accepted_version": next_version,
                }
                return _Change(updated, _view(accepted), details)

            committed = self._commit(
                operation_id,
                "materialization.checkpointed",
                change,
                connection_id=fence.connection_id,
                host_id=fence.host_id,
                lease_id=fence.lease_id,
            )
            cleanup = self._materializer.cleanup(fence.attachment_id)
            return PublicationResult(operation_id, committed.value, cleanup)
        finally:
            self._materializer.cleanup(fence.attachment_id)

    def release(self, materialization: Materialization, *, operation_id: str) -> ReleaseResult:
        _materialization(materialization)
        fence = materialization.fence

        def change(snapshot: StorageSnapshot) -> _Change[None]:
            now = self._now()
            updated, expired_ids, ambiguous = _reconcile_expired(snapshot, now)
            lease = _leases(updated).get(fence.lease_id)
            if lease is None or not _lease_matches(lease, fence) or lease.mode != materialization.mode.value:
                raise StaleCustody(f"lease is no longer current for connection {fence.connection_id!r}")
            if lease.released:
                details: dict[str, AuditValue] = {"already_settled": True, "mode": materialization.mode.value}
                return _Change(updated, None, details, expired_ids)
            _require_current_lease(updated, fence, now, materialization.mode)
            updated = _release_leases(updated, (lease,), "released")
            updated, ambiguous = _settle_released_refreshes(updated, (lease,))
            details: dict[str, AuditValue] = {
                "mode": materialization.mode.value,
                "ambiguous_refresh": bool(ambiguous),
            }
            return _Change(updated, None, details, expired_ids)

        try:
            self._commit(
                operation_id,
                "materialization.released",
                change,
                connection_id=fence.connection_id,
                host_id=fence.host_id,
                lease_id=fence.lease_id,
            )
        finally:
            cleanup = self._materializer.cleanup(fence.attachment_id)
        return ReleaseResult(operation_id, cleanup)

    def rotate(self, connection_id: str, opaque_state: OpaqueState, *, operation_id: str) -> ConnectionView:
        return self._replace_authority(connection_id, opaque_state, operation_id, "connection.rotated")

    def revoke(self, connection_id: str, *, operation_id: str) -> RevocationResult:
        _text(connection_id, "connection")

        def change(snapshot: StorageSnapshot) -> _Change[ConnectionView]:
            connection = _connection(snapshot, connection_id)
            if connection.status in {
                ConnectionStatus.REVOKED.value,
                ConnectionStatus.ERASURE_PENDING.value,
            }:
                raise ReauthorizationRequired(f"connection {connection_id!r} requires explicit reauthorization")
            unsettled = tuple(
                lease for lease in snapshot.leases if lease.connection_id == connection_id and not lease.released
            )
            revoked = replace(
                connection,
                status=ConnectionStatus.REVOKED.value,
                authority_epoch=connection.authority_epoch + 1,
            )
            updated = _replace_connection(_release_leases(snapshot, unsettled, "connection_revoked"), revoked)
            details: dict[str, AuditValue] = {
                "authority_epoch": revoked.authority_epoch,
                "canceled_leases": len(unsettled),
                "provider_revocation": "not_claimed",
                "offline_erasure_limit": True,
            }
            cleanup = tuple(lease.attachment_id for lease in unsettled)
            return _Change(updated, _view(revoked), details, cleanup)

        committed = self._commit(operation_id, "connection.revoked", change, connection_id=connection_id)
        return RevocationResult(operation_id, committed.value, committed.cleanup)

    def erase(self, connection_id: str, *, operation_id: str) -> ErasureResult:
        _text(connection_id, "connection")
        _operation_id(operation_id)
        pending_operation = f"prepare-{sha256(operation_id.encode()).hexdigest()[:32]}"
        current = _connection(self._load(), connection_id)
        if current.status == ConnectionStatus.REVOKED.value:

            def prepare(snapshot: StorageSnapshot) -> _Change[None]:
                connection = _connection(snapshot, connection_id)
                if connection.status != ConnectionStatus.REVOKED.value:
                    raise CustodyError(f"connection {connection_id!r} is not revoked")
                pending = replace(connection, status=ConnectionStatus.ERASURE_PENDING.value)
                details: dict[str, AuditValue] = {"state_version": pending.state_version}
                return _Change(_replace_connection(snapshot, pending), None, details)

            self._commit(pending_operation, "connection.erasure_started", prepare, connection_id=connection_id)
        elif current.status != ConnectionStatus.ERASURE_PENDING.value:
            raise CustodyError(f"connection {connection_id!r} must be revoked before erasure")

        key_erasure = self._keys.erase(connection_id)

        def finish(snapshot: StorageSnapshot) -> _Change[ConnectionView]:
            connection = _connection(snapshot, connection_id)
            if connection.status != ConnectionStatus.ERASURE_PENDING.value:
                raise CustodyError(f"connection {connection_id!r} is not awaiting erasure")
            active = tuple(
                lease for lease in snapshot.leases if lease.connection_id == connection_id and not lease.released
            )
            erased = replace(
                connection,
                status=ConnectionStatus.REAUTHORIZATION_REQUIRED.value,
                state_version=connection.state_version + 1,
                encrypted_state=None,
                state_digest=None,
            )
            updated = _replace_connection(_release_leases(snapshot, active, "connection_erased"), erased)
            details: dict[str, AuditValue] = {
                "state_version": erased.state_version,
                "key_erased": key_erasure.erased,
                "physical_media_erasure_guaranteed": False,
            }
            cleanup = tuple(lease.attachment_id for lease in active)
            return _Change(updated, _view(erased), details, cleanup)

        committed = self._commit(operation_id, "connection.erased", finish, connection_id=connection_id)
        return ErasureResult(operation_id, committed.value, key_erasure, committed.cleanup)

    def admit_result(self, fence: AttachmentFence, *, operation_id: str) -> AdmissionResult:
        return self._admit(fence, operation_id, "result")

    def admit_effect(self, fence: AttachmentFence, *, operation_id: str) -> AdmissionResult:
        return self._admit(fence, operation_id, "effect")

    def connection(self, connection_id: str) -> ConnectionView:
        _text(connection_id, "connection")
        return _view(_connection(self._load(), connection_id))

    def recover(self, *, operation_id: str) -> RecoveryResult:
        def change(snapshot: StorageSnapshot) -> _Change[tuple[int, tuple[str, ...]]]:
            updated, expired_ids, ambiguous = _reconcile_expired(snapshot, self._now())
            details: dict[str, AuditValue] = {
                "expired_leases": len(expired_ids),
                "ambiguous_connections": len(ambiguous),
            }
            released_ids = tuple(lease.attachment_id for lease in updated.leases if lease.released)
            return _Change(updated, (len(expired_ids), ambiguous), details, released_ids)

        committed = self._commit(operation_id, "installation.recovered", change)
        expired, ambiguous = committed.value
        return RecoveryResult(operation_id, expired, ambiguous, committed.cleanup)

    def lookup_operation(self, operation_id: str) -> OperationView | None:
        _operation_id(operation_id)
        for record in self._load().audit:
            if record.operation_id == operation_id:
                return _operation_view(record)
        return None

    def audit_records(self) -> tuple[AuditRecord, ...]:
        return self._load().audit

    def close(self) -> None:
        """Close storage only; active views intentionally survive to model a process crash."""
        self._storage.close()

    def _admit(self, fence: AttachmentFence, operation_id: str, purpose: str) -> AdmissionResult:
        if not isinstance(fence, AttachmentFence):
            raise TypeError("attachment fence must be AttachmentFence")

        def change(snapshot: StorageSnapshot) -> _Change[AdmissionResult]:
            if not _attachment_is_current(snapshot, fence, self._now()):
                raise StaleAttachment(f"{purpose} rejected: attachment {fence.attachment_id!r} is stale")
            result = AdmissionResult(operation_id, purpose, fence.attachment_id)
            details: dict[str, AuditValue] = {"authority_epoch": fence.authority_epoch}
            return _Change(snapshot, result, details)

        return self._commit(
            operation_id,
            f"attachment.{purpose}.admitted",
            change,
            connection_id=fence.connection_id,
            host_id=fence.host_id,
            lease_id=fence.lease_id,
        ).value

    def _replace_authority(
        self,
        connection_id: str,
        opaque_state: OpaqueState,
        operation_id: str,
        event_kind: str,
    ) -> ConnectionView:
        _text(connection_id, "connection")
        if not isinstance(opaque_state, OpaqueState):
            raise TypeError("opaque state must be OpaqueState")
        initial = self._load()
        current = _connection(initial, connection_id)
        if current.status not in {ConnectionStatus.READY.value, ConnectionStatus.REFRESHING.value}:
            opaque_state.erase()
            raise ReauthorizationRequired(f"connection {connection_id!r} requires explicit reauthorization")
        authority_epoch = current.authority_epoch + 1
        state_version = current.state_version + 1
        encrypted = self._seal(connection_id, authority_epoch, state_version, opaque_state)

        def change(snapshot: StorageSnapshot) -> _Change[ConnectionView]:
            connection = _connection(snapshot, connection_id)
            if not _same_connection_generation(connection, current):
                raise StaleCustody(f"connection {connection_id!r} changed during rotation")
            unsettled = tuple(
                lease for lease in snapshot.leases if lease.connection_id == connection_id and not lease.released
            )
            rotated = replace(
                connection,
                status=ConnectionStatus.READY.value,
                authority_epoch=authority_epoch,
                state_version=state_version,
                encrypted_state=encrypted,
                state_digest=_digest(encrypted),
            )
            updated = _replace_connection(_release_leases(snapshot, unsettled, "authority_rotated"), rotated)
            details: dict[str, AuditValue] = {
                "authority_epoch": authority_epoch,
                "state_version": state_version,
                "canceled_leases": len(unsettled),
            }
            cleanup = tuple(lease.attachment_id for lease in unsettled)
            return _Change(updated, _view(rotated), details, cleanup)

        return self._commit(operation_id, event_kind, change, connection_id=connection_id).value

    def _reconcile_expired_before(self, parent_operation_id: str, now: float) -> None:
        if not any(not lease.released and lease.expires_at <= now for lease in self._load().leases):
            return
        operation_id = f"reconcile-{sha256(parent_operation_id.encode()).hexdigest()[:32]}"

        def change(snapshot: StorageSnapshot) -> _Change[None]:
            updated, expired_ids, ambiguous = _reconcile_expired(snapshot, now)
            details: dict[str, AuditValue] = {
                "expired_leases": len(expired_ids),
                "ambiguous_connections": len(ambiguous),
            }
            return _Change(updated, None, details, expired_ids)

        self._commit(operation_id, "materialization.reconciled", change)

    def _abort_materialization(self, lease: StoredLease, parent_operation_id: str) -> None:
        operation_id = f"abort-{sha256(parent_operation_id.encode()).hexdigest()[:32]}"

        def change(snapshot: StorageSnapshot) -> _Change[None]:
            current = _leases(snapshot).get(lease.lease_id)
            if current is None or current.released:
                return _Change(snapshot, None, {"already_settled": True})
            updated = _release_leases(snapshot, (current,), "materialization_failed")
            updated, ambiguous = _settle_released_refreshes(updated, (current,))
            details: dict[str, AuditValue] = {"ambiguous_refresh": bool(ambiguous)}
            return _Change(updated, None, details, (current.attachment_id,))

        self._commit(
            operation_id,
            "materialization.failed",
            change,
            connection_id=lease.connection_id,
            host_id=lease.host_id,
            lease_id=lease.lease_id,
        )

    def _seal(self, connection_id: str, authority_epoch: int, state_version: int, state: OpaqueState) -> bytes:
        try:
            return self._keys.seal(KeyContext(connection_id, authority_epoch, state_version), state._borrow())
        finally:
            state.erase()

    def _seal_buffer(
        self,
        connection_id: str,
        authority_epoch: int,
        state_version: int,
        state: bytearray,
    ) -> bytes:
        try:
            return self._keys.seal(KeyContext(connection_id, authority_epoch, state_version), state)
        finally:
            _erase_buffer(state)

    def _load(self) -> StorageSnapshot:
        return validate_snapshot(self._storage.load())

    def _now(self) -> float:
        return _finite_time(self._clock(), "custody clock")

    def _commit(
        self,
        operation_id: str,
        event_kind: str,
        transform: Transform[T],
        *,
        connection_id: str | None = None,
        host_id: str | None = None,
        lease_id: str | None = None,
    ) -> _Commit[T]:
        _operation_id(operation_id)
        for _ in range(_CAS_ATTEMPTS):
            snapshot = self._load()
            if any(record.operation_id == operation_id for record in snapshot.audit):
                raise OperationConflict(
                    f"operation {operation_id!r} is already published; reconcile it through lookup_operation"
                )
            change = transform(snapshot)
            details = _audit_details(change.details)
            record = AuditRecord(
                sequence=len(snapshot.audit) + 1,
                operation_id=operation_id,
                event_kind=event_kind,
                connection_id=connection_id,
                host_id=host_id,
                lease_id=lease_id,
                details=details,
            )
            replacement = replace(
                change.snapshot,
                revision=snapshot.revision + 1,
                audit=change.snapshot.audit + (record,),
            )
            if self._storage.compare_and_swap(snapshot.revision, replacement):
                cleanup = self._materializer.summarize(tuple(dict.fromkeys(change.cleanup_ids)))
                LOGGER.info(
                    "%s operation=%s connection=%s host=%s lease=%s",
                    event_kind,
                    operation_id,
                    connection_id or "-",
                    host_id or "-",
                    lease_id or "-",
                )
                return _Commit(change.value, cleanup)
        raise StorageContention(f"operation {operation_id!r} could not publish after bounded CAS retries")


def _text(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value.encode()) > _MAX_TEXT_BYTES
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError(f"{name} identity must be a trimmed string of at most {_MAX_TEXT_BYTES} UTF-8 bytes")
    return value


def _operation_id(value: object) -> str:
    return _text(value, "operation")


def _positive_ttl(ttl: float) -> None:
    if _finite_time(ttl, "materialization lease ttl") <= 0:
        raise ValueError("materialization lease ttl must be positive")


def _finite_time(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def _materialization(value: object) -> Materialization:
    if not isinstance(value, Materialization):
        raise TypeError("materialization must be Materialization")
    return value


def _erase_buffer(buffer: bytearray) -> None:
    for index in range(len(buffer)):
        buffer[index] = 0
    buffer.clear()


def _digest(value: bytes) -> str:
    return sha256(value).hexdigest()


def _hosts(snapshot: StorageSnapshot) -> dict[str, StoredHost]:
    return {host.host_id: host for host in snapshot.hosts}


def _connections(snapshot: StorageSnapshot) -> dict[str, StoredConnection]:
    return {connection.connection_id: connection for connection in snapshot.connections}


def _leases(snapshot: StorageSnapshot) -> dict[str, StoredLease]:
    return {lease.lease_id: lease for lease in snapshot.leases}


def _replace_hosts(snapshot: StorageSnapshot, hosts: Mapping[str, StoredHost]) -> StorageSnapshot:
    return replace(snapshot, hosts=tuple(sorted(hosts.values())))


def _replace_connection(snapshot: StorageSnapshot, connection: StoredConnection) -> StorageSnapshot:
    connections = _connections(snapshot)
    connections[connection.connection_id] = connection
    return replace(snapshot, connections=tuple(sorted(connections.values())))


def _replace_leases(snapshot: StorageSnapshot, leases: Mapping[str, StoredLease]) -> StorageSnapshot:
    return replace(snapshot, leases=tuple(sorted(leases.values())))


def _active_host(snapshot: StorageSnapshot, host_id: str) -> StoredHost:
    host = _hosts(snapshot).get(host_id)
    if host is None or not host.active:
        raise HostNotEnrolled(f"host {host_id!r} is not enrolled")
    return host


def _connection(snapshot: StorageSnapshot, connection_id: str) -> StoredConnection:
    connection = _connections(snapshot).get(connection_id)
    if connection is None:
        raise CustodyError(f"connection {connection_id!r} does not exist")
    return connection


def _active_leases(
    snapshot: StorageSnapshot,
    now: float,
    *,
    connection_id: str | None = None,
    host_id: str | None = None,
) -> tuple[StoredLease, ...]:
    return tuple(
        lease
        for lease in snapshot.leases
        if not lease.released
        and lease.expires_at > now
        and (connection_id is None or lease.connection_id == connection_id)
        and (host_id is None or lease.host_id == host_id)
    )


def _release_leases(snapshot: StorageSnapshot, selected: tuple[StoredLease, ...], reason: str) -> StorageSnapshot:
    if not selected:
        return snapshot
    leases = _leases(snapshot)
    for lease in selected:
        leases[lease.lease_id] = replace(lease, released=True, release_reason=reason)
    return _replace_leases(snapshot, leases)


def _settle_released_refreshes(
    snapshot: StorageSnapshot, released: tuple[StoredLease, ...]
) -> tuple[StorageSnapshot, tuple[str, ...]]:
    connection_ids = {lease.connection_id for lease in released if lease.mode == LeaseMode.REFRESH.value}
    ambiguous = tuple(sorted({lease.connection_id for lease in released if lease.activated}))
    updated = snapshot
    for connection_id in sorted(connection_ids):
        connection = _connection(updated, connection_id)
        if connection.status != ConnectionStatus.REFRESHING.value:
            continue
        status = (
            ConnectionStatus.REAUTHORIZATION_REQUIRED.value
            if connection_id in ambiguous
            else ConnectionStatus.READY.value
        )
        epoch = connection.authority_epoch + (connection_id in ambiguous)
        replacement = replace(connection, status=status, authority_epoch=epoch)
        if connection_id in ambiguous:
            replacement = replace(replacement, encrypted_state=None, state_digest=None)
        updated = _replace_connection(updated, replacement)
    return updated, ambiguous


def _reconcile_expired(
    snapshot: StorageSnapshot, now: float
) -> tuple[StorageSnapshot, tuple[str, ...], tuple[str, ...]]:
    expired = tuple(lease for lease in snapshot.leases if not lease.released and lease.expires_at <= now)
    updated = _release_leases(snapshot, expired, "expired")
    updated, ambiguous = _settle_released_refreshes(updated, expired)
    return updated, tuple(lease.attachment_id for lease in expired), ambiguous


def _require_materializable(connection: StoredConnection) -> None:
    status = ConnectionStatus(connection.status)
    if status in {
        ConnectionStatus.REVOKED,
        ConnectionStatus.ERASURE_PENDING,
        ConnectionStatus.REAUTHORIZATION_REQUIRED,
    }:
        raise ReauthorizationRequired(f"connection {connection.connection_id!r} requires explicit reauthorization")
    if status is ConnectionStatus.REFRESHING:
        raise LeaseConflict(f"connection {connection.connection_id!r} already has refresh custody")
    if connection.encrypted_state is None:
        raise ReauthorizationRequired(f"connection {connection.connection_id!r} requires explicit reauthorization")


def _require_current_lease(
    snapshot: StorageSnapshot,
    fence: AttachmentFence,
    now: float,
    mode: LeaseMode,
) -> StoredLease:
    lease = _leases(snapshot).get(fence.lease_id)
    host = _hosts(snapshot).get(fence.host_id)
    if (
        lease is None
        or host is None
        or not host.active
        or host.enrollment_epoch != fence.host_epoch
        or lease.released
        or lease.expires_at <= now
        or lease.mode != mode.value
        or not _lease_matches(lease, fence)
    ):
        raise StaleCustody(f"lease is no longer current for connection {fence.connection_id!r}")
    return lease


def _lease_matches(lease: StoredLease, fence: AttachmentFence) -> bool:
    return bool(
        lease.attachment_id == fence.attachment_id
        and lease.connection_id == fence.connection_id
        and lease.host_id == fence.host_id
        and lease.host_epoch == fence.host_epoch
        and lease.authority_epoch == fence.authority_epoch
        and lease.base_version == fence.base_version
    )


def _attachment_is_current(snapshot: StorageSnapshot, fence: AttachmentFence, now: float) -> bool:
    try:
        lease = _require_current_lease(snapshot, fence, now, LeaseMode(_leases(snapshot)[fence.lease_id].mode))
        connection = _connection(snapshot, fence.connection_id)
    except CustodyError, KeyError, ValueError:
        return False
    return bool(
        _lease_matches(lease, fence)
        and connection.status in {ConnectionStatus.READY.value, ConnectionStatus.REFRESHING.value}
        and connection.authority_epoch == fence.authority_epoch
        and connection.state_version == fence.base_version
    )


def _fence(lease: StoredLease) -> AttachmentFence:
    return AttachmentFence(
        lease.attachment_id,
        lease.lease_id,
        lease.connection_id,
        lease.host_id,
        lease.host_epoch,
        lease.authority_epoch,
        lease.base_version,
    )


def _view(connection: StoredConnection) -> ConnectionView:
    return ConnectionView(
        ConnectionIdentity(
            connection.connection_id,
            connection.provider,
            connection.account_fingerprint,
            connection.profile,
        ),
        ConnectionStatus(connection.status),
        connection.authority_epoch,
        connection.state_version,
        connection.state_digest,
    )


def _same_connection_generation(left: StoredConnection | None, right: StoredConnection | None) -> bool:
    if left is None or right is None:
        return left is right
    return bool(
        left.connection_id == right.connection_id
        and left.status == right.status
        and left.authority_epoch == right.authority_epoch
        and left.state_version == right.state_version
        and left.state_digest == right.state_digest
    )


def _identity_matches(connection: StoredConnection, identity: ConnectionIdentity) -> bool:
    return bool(
        connection.connection_id == identity.connection_id
        and connection.provider == identity.provider
        and connection.account_fingerprint == identity.account_fingerprint
        and connection.profile == identity.profile
    )


def _audit_details(details: Mapping[str, AuditValue]) -> tuple[tuple[str, AuditValue], ...]:
    safe: list[tuple[str, AuditValue]] = []
    for name, value in details.items():
        if any(part in name.lower() for part in ("token", "secret", "password", "home", "key_material")):
            raise ValueError(f"audit detail {name!r} is not safe metadata")
        if value is not None and type(value) not in {str, int, float, bool}:
            raise TypeError(f"audit detail {name!r} must be a safe scalar")
        safe.append((name, value))
    return tuple(sorted(safe))


def _operation_view(record: AuditRecord) -> OperationView:
    return OperationView(
        record.operation_id,
        record.event_kind,
        record.connection_id,
        record.host_id,
        record.lease_id,
        record.details,
    )
