"""Production acceptance for installation-owned Agent Connection custody."""

from __future__ import annotations

import json
import logging
import stat
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from petrus.agenticus.connection.custody import (
    AgentConnectionCustody,
    ConnectionIdentity,
    ConnectionStatus,
    CustodyError,
    HostNotEnrolled,
    LeaseConflict,
    LeaseMode,
    OpaqueState,
    OperationConflict,
    ReauthorizationRequired,
    StaleAttachment,
    StaleCustody,
    StorageContention,
)
from petrus.agenticus.connection.key import KeyContext, KeyErasureEvidence, KeyOperationError, KeyOperations
from petrus.agenticus.connection.materialization import MaterializationSecurityError, PrivateFileMaterializer
from petrus.agenticus.connection.storage import (
    ConnectionStorage,
    SqliteConnectionStorage,
    StorageError,
    StorageSecurityError,
    StorageSnapshot,
    validate_snapshot,
)


ACCESS_CANARY = "synthetic-access-canary-never-render"
REFRESH_CANARY = "synthetic-refresh-canary-never-render"
KEY_CANARY = sha256(b"synthetic-installation-key-canary").digest()


@dataclass
class Clock:
    instant: float = 1_000.0

    def now(self) -> float:
        return self.instant

    def advance(self, seconds: float) -> None:
        self.instant += seconds


class SyntheticKeyOperations(KeyOperations):
    """Test-only AEAD key boundary; production receives host key operations."""

    def __init__(self, key: bytes = KEY_CANARY) -> None:
        self._key = bytes(key)
        self._nonce = 0
        self._erased: set[str] = set()
        self._lock = threading.Lock()
        self.fail_erasure = False

    def seal(self, context: KeyContext, plaintext: bytearray) -> bytes:
        with self._lock:
            self._erased.discard(context.connection_id)
            self._nonce += 1
            nonce = self._nonce.to_bytes(12, "big")
        return nonce + AESGCM(self._key).encrypt(nonce, bytes(plaintext), context.authenticated_data())

    def open(self, context: KeyContext, ciphertext: bytes) -> bytearray:
        if context.connection_id in self._erased:
            raise KeyOperationError("connection key is unavailable")
        try:
            return bytearray(AESGCM(self._key).decrypt(ciphertext[:12], ciphertext[12:], context.authenticated_data()))
        except (InvalidTag, ValueError) as error:
            raise KeyOperationError("encrypted connection state failed integrity verification") from error

    def erase(self, connection_id: str) -> KeyErasureEvidence:
        if self.fail_erasure:
            raise KeyOperationError("synthetic key erasure failed")
        self._erased.add(connection_id)
        return KeyErasureEvidence(connection_id=connection_id, erased=True)


class FakeRotatingProvider:
    """The only test component that parses the synthetic opaque state."""

    provider_id = "fake-rotating-oauth"

    def __init__(self) -> None:
        self.authorize_calls = 0
        self.refresh_calls = 0
        self._current: dict[str, str | int] | None = None

    def authorize(self, account: str) -> bytes:
        self.authorize_calls += 1
        state: dict[str, str | int] = {
            "account": account,
            "generation": 0,
            "access_token": ACCESS_CANARY,
            "refresh_token": REFRESH_CANARY,
        }
        self._current = state
        return self._encode(state)

    def refresh(self, opaque_state: bytes) -> bytes:
        state = self._parse(opaque_state)
        if self._current is None or state["refresh_token"] != self._current["refresh_token"]:
            raise RuntimeError("provider rejected stale refresh state")
        self.refresh_calls += 1
        generation = int(state["generation"]) + 1
        updated: dict[str, str | int] = {
            "account": state["account"],
            "generation": generation,
            "access_token": f"rotated-access-{self.refresh_calls}-{generation}",
            "refresh_token": f"rotated-refresh-{self.refresh_calls}-{generation}",
        }
        self._current = updated
        return self._encode(updated)

    def rotate_for_operator(self) -> bytes:
        if self._current is None:
            raise RuntimeError("provider is not authorized")
        return self.refresh(self._encode(self._current))

    def inspect(self, opaque_state: bytes) -> tuple[str, int]:
        state = self._parse(opaque_state)
        return str(state["account"]), int(state["generation"])

    @staticmethod
    def _encode(state: dict[str, str | int]) -> bytes:
        return json.dumps(state, sort_keys=True, separators=(",", ":")).encode()

    @staticmethod
    def _parse(opaque_state: bytes) -> dict[str, str | int]:
        value = json.loads(opaque_state)
        assert isinstance(value, dict)
        return value


@dataclass
class Rig:
    root: Path
    clock: Clock
    keys: SyntheticKeyOperations
    provider: FakeRotatingProvider
    storage: SqliteConnectionStorage
    materializer: PrivateFileMaterializer
    custody: AgentConnectionCustody


@pytest.fixture
def rig(tmp_path: Path) -> Rig:
    root = tmp_path / "installation"
    clock = Clock()
    keys = SyntheticKeyOperations()
    provider = FakeRotatingProvider()
    storage = SqliteConnectionStorage(root / "connections.sqlite3")
    materializer = PrivateFileMaterializer(root / "materialized")
    custody = AgentConnectionCustody(storage, keys, materializer, clock=clock.now)
    return Rig(root, clock, keys, provider, storage, materializer, custody)


def _identity(connection_id: str = "connection-main") -> ConnectionIdentity:
    return ConnectionIdentity(
        connection_id=connection_id,
        provider=FakeRotatingProvider.provider_id,
        account_fingerprint=sha256(b"fake-rotating-oauth\0account-1").hexdigest(),
        profile="subscription_oauth",
    )


def _authorize(rig: Rig, connection_id: str = "connection-main", *, operation_id: str = "authorize-main") -> bytes:
    opaque_state = rig.provider.authorize("account-1")
    rig.custody.authorize(
        _identity(connection_id),
        OpaqueState(opaque_state),
        operation_id=operation_id,
    )
    return opaque_state


def _reopen(rig: Rig) -> AgentConnectionCustody:
    storage = SqliteConnectionStorage(rig.root / "connections.sqlite3")
    materializer = PrivateFileMaterializer(rig.root / "materialized")
    return AgentConnectionCustody(storage, rig.keys, materializer, clock=rig.clock.now)


def test_ordinary_materialization_moves_one_logical_connection_between_hosts(rig: Rig) -> None:
    rig.custody.enroll_host("h1", operation_id="enroll-h1")
    rig.custody.enroll_host("h2", operation_id="enroll-h2")
    _authorize(rig)

    h1 = rig.custody.materialize("connection-main", "h1", mode=LeaseMode.REFRESH, ttl=60, operation_id="materialize-h1")
    assert stat.S_IMODE(rig.materializer.root.stat().st_mode) == 0o700
    assert stat.S_IMODE(h1.home.path.stat().st_mode) == 0o600
    rig.custody.activate(h1, operation_id="activate-h1")
    h1.home.replace(rig.provider.refresh(h1.home.read()))
    publication = rig.custody.checkpoint(h1, operation_id="checkpoint-h1")

    assert publication.connection.identity == _identity()
    assert publication.connection.status is ConnectionStatus.READY
    assert publication.connection.state_version == 2
    assert publication.cleanup.removed is True
    assert publication.cleanup.physical_erasure_guaranteed is False
    assert h1.home.erased is True

    h2 = rig.custody.materialize("connection-main", "h2", mode=LeaseMode.READ, ttl=30, operation_id="materialize-h2")
    assert rig.provider.inspect(h2.home.read()) == ("account-1", 1)
    assert rig.provider.authorize_calls == 1
    operation = rig.custody.lookup_operation("materialize-h2")
    assert operation is not None
    assert operation.event_kind == "materialization.acquired"
    assert operation.lease_id == h2.fence.lease_id
    with pytest.raises(StaleAttachment, match="result"):
        rig.custody.admit_result(replace(h2.fence, attachment_id="attachment-forged"), operation_id="admit-forged")
    release = rig.custody.release(h2, operation_id="release-h2")
    assert release.cleanup.removed is True
    assert h2.home.erased is True
    repeated = rig.custody.release(h2, operation_id="release-h2-again")
    assert repeated.cleanup.already_absent is True


class BarrierStorage(ConnectionStorage):
    """Align exactly one CAS attempt across two independent custody owners."""

    def __init__(self, storage: SqliteConnectionStorage, barrier: threading.Barrier, revision: int) -> None:
        self._storage = storage
        self._barrier = barrier
        self._revision = revision
        self._waited = False

    def load(self) -> StorageSnapshot:
        return self._storage.load()

    def compare_and_swap(self, expected_revision: int, replacement: StorageSnapshot) -> bool:
        if expected_revision == self._revision and not self._waited:
            self._waited = True
            self._barrier.wait(timeout=5)
        return self._storage.compare_and_swap(expected_revision, replacement)

    def close(self) -> None:
        self._storage.close()


class LostAcknowledgementStorage(ConnectionStorage):
    """Publish one CAS, then lose its acknowledgement like a process crash."""

    def __init__(self, storage: SqliteConnectionStorage) -> None:
        self._storage = storage
        self._lose_next = True

    def load(self) -> StorageSnapshot:
        return self._storage.load()

    def compare_and_swap(self, expected_revision: int, replacement: StorageSnapshot) -> bool:
        published = self._storage.compare_and_swap(expected_revision, replacement)
        if published and self._lose_next:
            self._lose_next = False
            raise RuntimeError("synthetic lost publication acknowledgement")
        return published

    def close(self) -> None:
        self._storage.close()


class RefusingStorage(ConnectionStorage):
    """Return CAS contention forever without changing the loaded state."""

    def __init__(self, storage: SqliteConnectionStorage) -> None:
        self._storage = storage
        self.attempts = 0

    def load(self) -> StorageSnapshot:
        return self._storage.load()

    def compare_and_swap(self, expected_revision: int, replacement: StorageSnapshot) -> bool:
        self.attempts += 1
        return False

    def close(self) -> None:
        self._storage.close()


def test_concurrent_refresh_has_one_cas_winner_and_waits_for_readers(rig: Rig) -> None:
    for host in ("h1", "h2"):
        rig.custody.enroll_host(host, operation_id=f"enroll-{host}")
    _authorize(rig)
    reader = rig.custody.materialize("connection-main", "h1", mode=LeaseMode.READ, ttl=60, operation_id="reader")
    with pytest.raises(LeaseConflict, match="refresh custody"):
        rig.custody.materialize("connection-main", "h2", mode=LeaseMode.REFRESH, ttl=60, operation_id="blocked-writer")
    rig.custody.release(reader, operation_id="release-reader")

    revision = rig.storage.load().revision
    barrier = threading.Barrier(2)
    contenders = tuple(
        AgentConnectionCustody(
            BarrierStorage(
                SqliteConnectionStorage(rig.root / "connections.sqlite3"),
                barrier,
                revision,
            ),
            rig.keys,
            PrivateFileMaterializer(rig.root / "materialized"),
            clock=rig.clock.now,
        )
        for _ in range(2)
    )

    def contend(index: int):
        return contenders[index].materialize(
            "connection-main",
            f"h{index + 1}",
            mode=LeaseMode.REFRESH,
            ttl=60,
            operation_id=f"contender-{index + 1}",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(contend, index) for index in range(2)]
        outcomes: list[object] = []
        for future in futures:
            try:
                outcomes.append(future.result())
            except LeaseConflict as error:
                outcomes.append(error)

    winners = [outcome for outcome in outcomes if not isinstance(outcome, LeaseConflict)]
    assert len(winners) == 1
    assert sum(isinstance(outcome, LeaseConflict) for outcome in outcomes) == 1
    winner = winners[0]
    owner = contenders[int(winner.fence.host_id.removeprefix("h")) - 1]
    owner.release(winner, operation_id="release-winner")
    for contender in contenders:
        contender.close()


def test_current_host_renews_bounded_read_and_current_attachments_are_admitted(rig: Rig) -> None:
    rig.custody.enroll_host("h1", operation_id="enroll-h1")
    _authorize(rig)
    reader = rig.custody.materialize(
        "connection-main", "h1", mode=LeaseMode.READ, ttl=10, operation_id="renewable-reader"
    )

    rig.clock.advance(9)
    renewal = rig.custody.renew(reader, ttl=10, operation_id="renew-reader")
    rig.clock.advance(2)
    admitted = rig.custody.admit_result(reader.fence, operation_id="admit-current-result")

    assert renewal.expires_at == 1_019
    assert admitted.purpose == "result"
    assert admitted.attachment_id == reader.fence.attachment_id
    assert rig.provider.inspect(reader.home.read()) == ("account-1", 0)
    rig.custody.release(reader, operation_id="release-renewed-reader")

    refresh = rig.custody.materialize(
        "connection-main", "h1", mode=LeaseMode.REFRESH, ttl=10, operation_id="current-refresh"
    )
    rig.custody.activate(refresh, operation_id="activate-current-refresh")
    effect = rig.custody.admit_effect(refresh.fence, operation_id="admit-current-effect")
    assert effect.purpose == "effect"
    refresh.home.replace(rig.provider.refresh(refresh.home.read()))
    rig.custody.checkpoint(refresh, operation_id="checkpoint-current-refresh")


@pytest.mark.parametrize("ttl", (float("nan"), float("inf")))
def test_materialization_and_renewal_refuse_nonfinite_lease_bounds(rig: Rig, ttl: float) -> None:
    rig.custody.enroll_host("h1", operation_id="enroll-h1")
    _authorize(rig)

    with pytest.raises(ValueError, match="finite"):
        rig.custody.materialize(
            "connection-main", "h1", mode=LeaseMode.READ, ttl=ttl, operation_id="nonfinite-materialization"
        )

    reader = rig.custody.materialize("connection-main", "h1", mode=LeaseMode.READ, ttl=10, operation_id="finite-reader")
    with pytest.raises(ValueError, match="finite"):
        rig.custody.renew(reader, ttl=ttl, operation_id="nonfinite-renewal")
    rig.custody.release(reader, operation_id="release-finite-reader")


def test_operation_lookup_reconciles_a_lost_publication_acknowledgement(rig: Rig) -> None:
    uncertain = AgentConnectionCustody(
        LostAcknowledgementStorage(SqliteConnectionStorage(rig.root / "uncertain.sqlite3")),
        rig.keys,
        PrivateFileMaterializer(rig.root / "uncertain-materialized"),
        clock=rig.clock.now,
    )

    with pytest.raises(RuntimeError, match="lost publication acknowledgement"):
        uncertain.enroll_host("h1", operation_id="uncertain-enrollment")

    operation = uncertain.lookup_operation("uncertain-enrollment")
    assert operation is not None
    assert operation.event_kind == "host.enrolled"
    assert operation.host_id == "h1"
    assert operation.details == (
        ("ambiguous_connections", 0),
        ("canceled_leases", 0),
        ("enrollment_epoch", 1),
        ("expired_leases", 0),
    )
    with pytest.raises(OperationConflict, match="lookup_operation"):
        uncertain.enroll_host("h1", operation_id="uncertain-enrollment")
    uncertain.close()


def test_cas_contention_is_bounded_and_publishes_no_operation(rig: Rig) -> None:
    storage = RefusingStorage(SqliteConnectionStorage(rig.root / "refusing.sqlite3"))
    custody = AgentConnectionCustody(
        storage,
        rig.keys,
        PrivateFileMaterializer(rig.root / "refusing-materialized"),
        clock=rig.clock.now,
    )

    with pytest.raises(StorageContention, match="bounded CAS retries"):
        custody.enroll_host("h1", operation_id="never-published")

    assert storage.attempts == 8
    assert custody.lookup_operation("never-published") is None
    custody.close()


def test_crash_before_provider_mutation_reconciles_to_last_accepted_state(rig: Rig) -> None:
    for host in ("h1", "h2"):
        rig.custody.enroll_host(host, operation_id=f"enroll-{host}")
    original = _authorize(rig)
    abandoned = rig.custody.materialize(
        "connection-main", "h1", mode=LeaseMode.REFRESH, ttl=5, operation_id="abandoned-before-activation"
    )
    rig.custody.close()
    rig.clock.advance(6)

    recovered = _reopen(rig)
    result = recovered.recover(operation_id="recover-before-activation")

    assert result.expired_leases == 1
    assert result.ambiguous_connections == ()
    assert recovered.connection("connection-main").status is ConnectionStatus.READY
    assert abandoned.home.erased is True
    h2 = recovered.materialize("connection-main", "h2", mode=LeaseMode.READ, ttl=10, operation_id="read-recovered")
    assert h2.home.read() == original
    recovered.release(h2, operation_id="release-recovered")
    recovered.close()


def test_crash_after_provider_rotation_fails_closed_to_reauthorization(rig: Rig) -> None:
    rig.custody.enroll_host("h1", operation_id="enroll-h1")
    _authorize(rig)
    abandoned = rig.custody.materialize(
        "connection-main", "h1", mode=LeaseMode.REFRESH, ttl=5, operation_id="rotating-runtime"
    )
    rig.custody.activate(abandoned, operation_id="activate-rotating-runtime")
    rotated = rig.provider.refresh(abandoned.home.read())
    abandoned.home.replace(rotated)
    rig.custody.close()
    rig.clock.advance(6)

    recovered = _reopen(rig)
    result = recovered.recover(operation_id="recover-ambiguous-refresh")

    assert result.expired_leases == 1
    assert result.ambiguous_connections == ("connection-main",)
    view = recovered.connection("connection-main")
    assert view.status is ConnectionStatus.REAUTHORIZATION_REQUIRED
    assert view.authority_epoch == 2
    assert view.state_digest is None
    assert abandoned.home.erased is True
    with pytest.raises(ReauthorizationRequired, match="connection-main"):
        recovered.materialize("connection-main", "h1", mode=LeaseMode.READ, ttl=10, operation_id="fail-closed-read")
    mismatched = OpaqueState(rotated)
    with pytest.raises(CustodyError, match="different provider authority"):
        recovered.authorize(
            replace(_identity(), account_fingerprint="different-account"),
            mismatched,
            operation_id="mismatched-reauthorization",
        )
    assert mismatched.erased is True
    recovered.authorize(_identity(), OpaqueState(rotated), operation_id="explicit-reauthorization")
    assert recovered.connection("connection-main").status is ConnectionStatus.READY
    recovered.close()


def test_recovery_sweeps_released_plaintext_left_after_publication_crash(rig: Rig) -> None:
    rig.custody.enroll_host("h1", operation_id="enroll-h1")
    _authorize(rig)
    reader = rig.custody.materialize(
        "connection-main", "h1", mode=LeaseMode.READ, ttl=10, operation_id="published-reader"
    )
    rig.custody.release(reader, operation_id="published-release")

    abandoned = bytearray(ACCESS_CANARY.encode())
    orphan = rig.materializer.materialize(reader.fence.attachment_id, abandoned)
    abandoned[:] = b"\0" * len(abandoned)
    abandoned.clear()
    assert orphan.erased is False

    recovered = _reopen(rig)
    result = recovered.recover(operation_id="sweep-published-orphan")

    assert result.expired_leases == 0
    assert result.cleanup.removed == 1
    assert result.cleanup.unresolved == 0
    assert orphan.erased is True
    recovered.close()


def test_stale_writer_never_replaces_a_newer_rotated_authority(rig: Rig) -> None:
    rig.custody.enroll_host("h1", operation_id="enroll-h1")
    _authorize(rig)
    stale = rig.custody.materialize(
        "connection-main", "h1", mode=LeaseMode.REFRESH, ttl=60, operation_id="stale-writer"
    )
    rig.custody.activate(stale, operation_id="activate-stale-writer")
    stale.home.replace(rig.provider.refresh(stale.home.read()))

    current_state = rig.provider.rotate_for_operator()
    rotated = rig.custody.rotate("connection-main", OpaqueState(current_state), operation_id="operator-rotation")

    assert rotated.authority_epoch == 2
    assert rotated.state_version == 2
    with pytest.raises(StaleCustody, match="no longer current"):
        rig.custody.checkpoint(stale, operation_id="late-stale-return")
    with pytest.raises(StaleAttachment, match="result"):
        rig.custody.admit_result(stale.fence, operation_id="late-stale-result")
    assert stale.home.erased is True
    assert rig.custody.connection("connection-main") == rotated


def test_rotation_supersedes_an_expired_unreconciled_refresh_lease(rig: Rig) -> None:
    rig.custody.enroll_host("h1", operation_id="enroll-h1")
    _authorize(rig)
    expired = rig.custody.materialize(
        "connection-main", "h1", mode=LeaseMode.REFRESH, ttl=5, operation_id="expired-writer"
    )
    rig.custody.activate(expired, operation_id="activate-expired-writer")
    rig.clock.advance(6)

    rotated = rig.custody.rotate(
        "connection-main",
        OpaqueState(rig.provider.rotate_for_operator()),
        operation_id="rotate-after-expiry",
    )

    assert rotated.status is ConnectionStatus.READY
    assert rotated.authority_epoch == 2
    assert rotated.state_version == 2
    assert expired.home.erased is True
    with pytest.raises(StaleCustody, match="no longer current"):
        rig.custody.checkpoint(expired, operation_id="expired-return")


def test_releasing_activated_refresh_fails_closed_and_is_idempotently_cleanable(rig: Rig) -> None:
    rig.custody.enroll_host("h1", operation_id="enroll-h1")
    _authorize(rig)
    refresh = rig.custody.materialize(
        "connection-main", "h1", mode=LeaseMode.REFRESH, ttl=10, operation_id="activated-release"
    )
    rig.custody.activate(refresh, operation_id="activate-release")

    released = rig.custody.release(refresh, operation_id="release-ambiguous")

    connection = rig.custody.connection("connection-main")
    assert connection.status is ConnectionStatus.REAUTHORIZATION_REQUIRED
    assert connection.authority_epoch == 2
    assert connection.state_digest is None
    assert released.cleanup.removed is True
    repeated = rig.custody.release(refresh, operation_id="release-ambiguous-again")
    assert repeated.cleanup.already_absent is True


def test_host_removal_and_reenrollment_fence_old_custody_and_clean_reachable_state(rig: Rig) -> None:
    for host in ("h1", "h2"):
        rig.custody.enroll_host(host, operation_id=f"enroll-{host}")
    _authorize(rig)
    old = rig.custody.materialize("connection-main", "h2", mode=LeaseMode.REFRESH, ttl=60, operation_id="old-host-view")

    removal = rig.custody.remove_host("h2", operation_id="remove-h2")

    assert removal.canceled_leases == 1
    assert removal.cleanup.removed == 1
    assert removal.cleanup.unresolved == 0
    assert removal.offline_erasure_limit is True
    assert old.home.erased is True
    with pytest.raises(HostNotEnrolled, match="h2"):
        rig.custody.renew(old, ttl=10, operation_id="removed-renew")
    with pytest.raises(StaleCustody, match="no longer current"):
        rig.custody.checkpoint(old, operation_id="removed-checkpoint")
    with pytest.raises(StaleAttachment, match="effect"):
        rig.custody.admit_effect(old.fence, operation_id="removed-effect")

    rig.custody.enroll_host("h2", operation_id="reenroll-h2")
    replacement = rig.custody.materialize(
        "connection-main", "h2", mode=LeaseMode.READ, ttl=10, operation_id="replacement-view"
    )
    assert replacement.fence.host_epoch == 3
    rig.custody.release(replacement, operation_id="release-replacement")


def test_revoke_fences_every_attachment_and_returns_secret_free_cleanup(rig: Rig) -> None:
    for host in ("h1", "h2"):
        rig.custody.enroll_host(host, operation_id=f"enroll-{host}")
    _authorize(rig)
    h1 = rig.custody.materialize("connection-main", "h1", mode=LeaseMode.READ, ttl=60, operation_id="read-h1")
    h2 = rig.custody.materialize("connection-main", "h2", mode=LeaseMode.READ, ttl=60, operation_id="read-h2")

    result = rig.custody.revoke("connection-main", operation_id="revoke-main")

    assert result.connection.status is ConnectionStatus.REVOKED
    assert result.connection.authority_epoch == 2
    assert result.provider_revocation == "not_claimed"
    assert result.cleanup.attempted == 2
    assert result.cleanup.removed == 2
    assert h1.home.erased is True
    assert h2.home.erased is True
    with pytest.raises(StaleAttachment, match="result"):
        rig.custody.admit_result(h1.fence, operation_id="late-result")
    with pytest.raises(StaleAttachment, match="effect"):
        rig.custody.admit_effect(h2.fence, operation_id="late-effect")
    with pytest.raises(ReauthorizationRequired, match="connection-main"):
        rig.custody.materialize("connection-main", "h1", mode=LeaseMode.READ, ttl=10, operation_id="revoked-read")


def test_erase_is_key_backed_retryable_and_requires_explicit_reauthorization(rig: Rig) -> None:
    rig.custody.enroll_host("h1", operation_id="enroll-h1")
    _authorize(rig)
    second_state = rig.provider.authorize("account-1")
    rig.custody.authorize(
        _identity("connection-fallback"),
        OpaqueState(second_state),
        operation_id="authorize-fallback",
    )
    rig.custody.revoke("connection-main", operation_id="revoke-main")

    rig.keys.fail_erasure = True
    with pytest.raises(KeyOperationError, match="erasure failed"):
        rig.custody.erase("connection-main", operation_id="erase-main")
    pending = rig.custody.connection("connection-main")
    assert pending.status is ConnectionStatus.ERASURE_PENDING
    assert pending.state_digest is not None

    rig.keys.fail_erasure = False
    result = rig.custody.erase("connection-main", operation_id="erase-main")

    assert result.connection.status is ConnectionStatus.REAUTHORIZATION_REQUIRED
    assert result.connection.state_digest is None
    assert result.key_erasure.erased is True
    assert rig.custody.connection("connection-fallback").status is ConnectionStatus.READY
    with pytest.raises(ReauthorizationRequired, match="connection-main"):
        rig.custody.materialize("connection-main", "h1", mode=LeaseMode.READ, ttl=10, operation_id="erased-read")

    new_state = rig.provider.authorize("account-1")
    reauthorized = rig.custody.authorize(_identity(), OpaqueState(new_state), operation_id="reauthorize-after-erase")
    assert reauthorized.status is ConnectionStatus.READY
    assert reauthorized.authority_epoch == 3
    assert reauthorized.state_version == 3


def test_secret_canaries_never_reach_durable_rendered_or_cleanup_evidence(
    rig: Rig, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="petrus.agenticus.connection.custody")
    rig.custody.enroll_host("h1", operation_id="enroll-h1")
    plaintext = _authorize(rig)
    materialized = rig.custody.materialize(
        "connection-main", "h1", mode=LeaseMode.REFRESH, ttl=10, operation_id="canary-view"
    )
    rig.custody.activate(materialized, operation_id="activate-canary-view")
    materialized.home.replace(rig.provider.refresh(materialized.home.read()))
    result = rig.custody.checkpoint(materialized, operation_id="checkpoint-canary-view")
    with pytest.raises(StaleCustody) as raised:
        rig.custody.checkpoint(materialized, operation_id="repeat-checkpoint")

    database_bytes = b"".join(path.read_bytes() for path in rig.root.glob("connections.sqlite3*"))
    materialized_bytes = b"".join(path.read_bytes() for path in rig.materializer.root.glob("**/*") if path.is_file())
    rendered = (
        repr(rig.custody.audit_records()) + repr(result) + repr(materialized) + repr(raised.value) + caplog.text
    ).encode()
    for marker in (plaintext, ACCESS_CANARY.encode(), REFRESH_CANARY.encode(), KEY_CANARY):
        assert marker not in database_bytes
        assert marker not in materialized_bytes
        assert marker not in rendered
    assert result.connection.state_digest != sha256(plaintext).hexdigest()
    assert materialized.home.erased is True
    assert "credential" not in caplog.text.lower()


def test_materialization_refuses_permissive_modes_and_symlink_substitution(rig: Rig, tmp_path: Path) -> None:
    rig.custody.enroll_host("h1", operation_id="enroll-h1")
    _authorize(rig)
    materialized = rig.custody.materialize(
        "connection-main", "h1", mode=LeaseMode.READ, ttl=10, operation_id="mode-check"
    )

    materialized.home.path.chmod(0o644)
    with pytest.raises(MaterializationSecurityError, match="mode"):
        materialized.home.read()
    materialized.home.path.chmod(0o600)
    outside = tmp_path / "outside"
    outside.write_bytes(ACCESS_CANARY.encode())
    materialized.home.path.unlink()
    materialized.home.path.symlink_to(outside)
    with pytest.raises(MaterializationSecurityError, match="symlink"):
        materialized.home.read()
    cleanup = rig.custody.release(materialized, operation_id="release-tampered")
    assert cleanup.cleanup.security_violation is True
    assert outside.read_bytes() == ACCESS_CANARY.encode()

    symlink_root = tmp_path / "materialized-link"
    symlink_root.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(MaterializationSecurityError, match="symlink"):
        PrivateFileMaterializer(symlink_root)


def test_sqlite_storage_enforces_private_modes_and_refuses_symlink_files(tmp_path: Path) -> None:
    root = tmp_path / "private-store"
    path = root / "connections.sqlite3"
    storage = SqliteConnectionStorage(path)
    assert stat.S_IMODE(root.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    storage.close()

    path.chmod(0o644)
    with pytest.raises(StorageSecurityError, match="mode"):
        SqliteConnectionStorage(path)
    path.unlink()
    outside = tmp_path / "outside.sqlite3"
    outside.touch(mode=0o600)
    path.symlink_to(outside)
    with pytest.raises(StorageSecurityError, match="symlink"):
        SqliteConnectionStorage(path)


def test_storage_validation_refuses_state_the_live_writer_cannot_publish(rig: Rig) -> None:
    rig.custody.enroll_host("h1", operation_id="enroll-h1")
    _authorize(rig)
    refresh = rig.custody.materialize(
        "connection-main", "h1", mode=LeaseMode.REFRESH, ttl=10, operation_id="refresh-state"
    )
    snapshot = rig.storage.load()
    connection = snapshot.connections[0]
    lease = snapshot.leases[0]

    with pytest.raises(StorageError, match="active refresh custody"):
        validate_snapshot(replace(snapshot, connections=(replace(connection, status="ready"),)))
    with pytest.raises(StorageError, match="stale connection authority"):
        validate_snapshot(replace(snapshot, leases=(replace(lease, authority_epoch=2),)))
    for expires_at in (float("nan"), float("inf")):
        with pytest.raises(StorageError, match="finite"):
            validate_snapshot(replace(snapshot, leases=(replace(lease, expires_at=expires_at),)))

    rig.custody.release(refresh, operation_id="release-refresh-state")


def test_empty_provider_return_is_not_published(rig: Rig) -> None:
    rig.custody.enroll_host("h1", operation_id="enroll-h1")
    _authorize(rig)
    refresh = rig.custody.materialize(
        "connection-main", "h1", mode=LeaseMode.REFRESH, ttl=10, operation_id="empty-return"
    )
    rig.custody.activate(refresh, operation_id="activate-empty-return")
    refresh.home.path.write_bytes(b"")

    with pytest.raises(CustodyError, match="empty opaque state"):
        rig.custody.checkpoint(refresh, operation_id="reject-empty-return")

    released = rig.custody.release(refresh, operation_id="release-empty-return")
    assert released.cleanup.already_absent is True
    assert rig.custody.connection("connection-main").status is ConnectionStatus.REAUTHORIZATION_REQUIRED


@pytest.mark.parametrize(
    ("terminal_status", "operation"),
    (
        (ConnectionStatus.REVOKED, "revoke"),
        (ConnectionStatus.ERASURE_PENDING, "erase-pending"),
        (ConnectionStatus.REAUTHORIZATION_REQUIRED, "erased"),
    ),
)
def test_terminal_and_fail_closed_states_never_materialize(
    rig: Rig, terminal_status: ConnectionStatus, operation: str
) -> None:
    rig.custody.enroll_host("h1", operation_id="enroll-h1")
    _authorize(rig)
    rig.custody.revoke("connection-main", operation_id="revoke-main")
    if terminal_status is not ConnectionStatus.REVOKED:
        rig.keys.fail_erasure = terminal_status is ConnectionStatus.ERASURE_PENDING
        try:
            rig.custody.erase("connection-main", operation_id="erase-main")
        except KeyOperationError:
            pass
    assert rig.custody.connection("connection-main").status is terminal_status
    with pytest.raises(ReauthorizationRequired, match="connection-main"):
        rig.custody.materialize(
            "connection-main", "h1", mode=LeaseMode.READ, ttl=10, operation_id=f"blocked-{operation}"
        )
