from __future__ import annotations

import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Event

import pytest

from petrus.agenticus.attachment._retention import SqliteTerritoryCustody, TerritoryCustodyPhase
from petrus.agenticus.attachment.binding import MotusAttachmentBinding, MotusBindingError
from petrus.agenticus.attachment.episode import EpisodeAttachment, EpisodeAttachmentError
from petrus.agenticus.catalog.descriptor import CapabilityDescriptor, DescriptorIdentity, DescriptorKind
from petrus.agenticus.catalog.resolution import ResolutionSnapshot
from petrus.agenticus.connection.storage import StorageError
from petrus.agenticus.thread.identity import EpisodeId
from petrus.motus.execution import CleanupDisposition, CleanupResult, EnvironmentSpec
from petrus.motus.execution.archive import workspace_archive
from petrus.motus.execution.providers import LocalProcessEnvironment


def _snapshot(suffix: str) -> ResolutionSnapshot:
    return ResolutionSnapshot(
        1,
        tuple(
            CapabilityDescriptor(DescriptorIdentity(kind, f"{kind.value}-{suffix}", 1), frozenset(), ())
            for kind in (DescriptorKind.RUNTIME, DescriptorKind.HANDS, DescriptorKind.TERRITORY)
        ),
    )


def _attachment(tmp_path: Path, provider: LocalProcessEnvironment) -> tuple[EpisodeAttachment, MotusAttachmentBinding]:
    source = tmp_path / "source"
    source.mkdir()
    (source / "canary.txt").write_text("retained")
    binding = MotusAttachmentBinding.open(
        provider,
        "territory-operation",
        EnvironmentSpec(),
        workspace_archive_bytes=workspace_archive(source),
        input_digest="initial",
    )
    return (
        EpisodeAttachment(
            episode_id=EpisodeId("episode-one"),
            snapshot=_snapshot("one"),
            binding=binding,
            attachment_id="attachment-one",
            attachment_epoch=3,
            deadline=100,
        ),
        binding,
    )


def test_retained_lease_reclaims_into_a_distinct_episode_and_retires_exactly(tmp_path: Path) -> None:
    provider = LocalProcessEnvironment()
    attachment, old_binding = _attachment(tmp_path, provider)
    path = tmp_path / "custody" / "territories.db"
    custody = SqliteTerritoryCustody(path, clock=lambda: 10)

    released = custody.release("custody-one", "host-one", attachment, retain_until=50)
    retained = custody.lookup("custody-one")
    assert retained is not None and retained.phase is TerritoryCustodyPhase.RETAINED
    assert retained.archive == released.archive
    assert provider.lookup(released.territory.operation_id) is not None
    with pytest.raises(MotusBindingError, match="released"):
        old_binding.export_archive()
    custody.close()

    reconstructed = SqliteTerritoryCustody(path, clock=lambda: 20)
    successor = reconstructed.reclaim(
        "custody-one",
        "host-one",
        provider,
        episode_id=EpisodeId("episode-two"),
        snapshot=_snapshot("two"),
        attachment_id="attachment-two",
        deadline=100,
    )
    current = reconstructed.lookup("custody-one")
    assert current is not None and current.phase is TerritoryCustodyPhase.ATTACHED
    assert successor.episode_id == EpisodeId("episode-two") and successor.epoch == 4
    assert successor.binding.lease_identity == released.territory

    reconstructed.release("custody-one", "host-one", successor, retain_until=60)
    retired = reconstructed.retire("custody-one", "host-one", provider)
    assert retired.phase is TerritoryCustodyPhase.RETIRED
    assert retired.cleanup is not None and retired.archive is None
    assert provider.lookup(released.territory.operation_id) is None
    reconstructed.close()
    assert b"retained" not in path.read_bytes()


def test_recovery_retires_incomplete_release_instead_of_reusing_it(tmp_path: Path) -> None:
    provider = LocalProcessEnvironment()
    attachment, _binding = _attachment(tmp_path, provider)
    path = tmp_path / "custody" / "territories.db"
    custody = SqliteTerritoryCustody(path, clock=lambda: 10)
    custody.begin_release("custody-crash", "host-one", attachment, retain_until=50)
    custody.close()

    recovered = SqliteTerritoryCustody(path, clock=lambda: 20)
    [record] = recovered.recover()
    assert record.phase is TerritoryCustodyPhase.RETIRING and record.archive is None
    assert recovered.retire("custody-crash", "host-one", provider).phase is TerritoryCustodyPhase.RETIRED
    assert provider.lookup(record.lease.operation_id) is None
    recovered.close()


def test_corrupt_archive_never_reclaims_and_preserves_exact_cleanup_obligation(tmp_path: Path) -> None:
    provider = LocalProcessEnvironment()
    attachment, _binding = _attachment(tmp_path, provider)
    path = tmp_path / "custody" / "territories.db"
    custody = SqliteTerritoryCustody(path, clock=lambda: 10)
    release = custody.release("custody-corrupt", "host-one", attachment, retain_until=50)
    custody.close()
    with sqlite3.connect(path) as database:
        database.execute("UPDATE territory_custody SET archive=? WHERE custody_id=?", (b"corrupt", "custody-corrupt"))

    recovered = SqliteTerritoryCustody(path, clock=lambda: 20)
    with pytest.raises(StorageError, match="digest"):
        recovered.reclaim(
            "custody-corrupt",
            "host-one",
            provider,
            episode_id=EpisodeId("episode-two"),
            snapshot=_snapshot("two"),
            attachment_id="attachment-two",
            deadline=100,
        )
    retiring = recovered.lookup("custody-corrupt")
    assert retiring is not None and retiring.phase is TerritoryCustodyPhase.RETIRING
    assert recovered.retire("custody-corrupt", "host-one", provider).phase is TerritoryCustodyPhase.RETIRED
    assert provider.lookup(release.territory.operation_id) is None
    recovered.close()


def test_missing_retained_lease_never_falls_through_to_creation(tmp_path: Path) -> None:
    provider = LocalProcessEnvironment()
    attachment, _binding = _attachment(tmp_path, provider)
    custody = SqliteTerritoryCustody(tmp_path / "custody" / "territories.db", clock=lambda: 10)
    custody.release("custody-missing", "host-one", attachment, retain_until=50)
    retained = custody.lookup("custody-missing")
    assert retained is not None and provider.destroy(retained.lease).verified
    provider.create = lambda *args: (_ for _ in ()).throw(AssertionError("create must not run"))  # type: ignore[method-assign]

    with pytest.raises(StorageError, match="absent or not ready"):
        custody.reclaim(
            "custody-missing",
            "host-one",
            provider,
            episode_id=EpisodeId("episode-two"),
            snapshot=_snapshot("two"),
            attachment_id="attachment-two",
            deadline=100,
        )
    assert custody.lookup("custody-missing").phase is TerritoryCustodyPhase.RETIRING  # type: ignore[union-attr]
    assert custody.retire("custody-missing", "host-one", provider).phase is TerritoryCustodyPhase.RETIRED
    custody.close()


def test_foreign_lookup_remains_retryable_until_exact_retirement_is_verified(tmp_path: Path) -> None:
    provider = LocalProcessEnvironment()
    attachment, _binding = _attachment(tmp_path, provider)
    custody = SqliteTerritoryCustody(tmp_path / "custody" / "territories.db", clock=lambda: 10)
    custody.release("custody-foreign", "host-one", attachment, retain_until=50)
    retained = custody.lookup("custody-foreign")
    assert retained is not None
    original_lookup = provider.lookup
    provider.lookup = lambda operation_id: replace(retained.lease, lease_id="foreign-lease")  # type: ignore[method-assign]
    try:
        with pytest.raises(StorageError, match="conflicts"):
            custody.reclaim(
                "custody-foreign",
                "host-one",
                provider,
                episode_id=EpisodeId("episode-two"),
                snapshot=_snapshot("two"),
                attachment_id="attachment-two",
                deadline=100,
            )
        assert custody.lookup("custody-foreign").phase is TerritoryCustodyPhase.RETIRING  # type: ignore[union-attr]
        with pytest.raises(StorageError, match="foreign current lease"):
            custody.retire("custody-foreign", "host-one", provider)
    finally:
        provider.lookup = original_lookup  # type: ignore[method-assign]
    assert custody.retire("custody-foreign", "host-one", provider).phase is TerritoryCustodyPhase.RETIRED
    assert provider.lookup(retained.lease.operation_id) is None
    custody.close()


def test_expired_custody_moves_to_exact_retirement_instead_of_reclaim(tmp_path: Path) -> None:
    now = [10.0]
    provider = LocalProcessEnvironment()
    attachment, _binding = _attachment(tmp_path, provider)
    custody = SqliteTerritoryCustody(tmp_path / "custody" / "territories.db", clock=lambda: now[0])
    custody.release("custody-expired", "host-one", attachment, retain_until=15)
    now[0] = 20

    with pytest.raises(StorageError, match="expired"):
        custody.reclaim(
            "custody-expired",
            "host-one",
            provider,
            episode_id=EpisodeId("episode-two"),
            snapshot=_snapshot("two"),
            attachment_id="attachment-two",
            deadline=100,
        )
    assert custody.retire("custody-expired", "host-one", provider).phase is TerritoryCustodyPhase.RETIRED
    custody.close()


def test_expiry_during_export_never_acknowledges_retention(tmp_path: Path) -> None:
    now = [10.0]
    provider = LocalProcessEnvironment()
    attachment, _binding = _attachment(tmp_path, provider)
    custody = SqliteTerritoryCustody(tmp_path / "custody" / "territories.db", clock=lambda: now[0])
    original_export = provider.export

    def expiring_export(execution):
        archive = original_export(execution)
        now[0] = 20
        return archive

    provider.export = expiring_export  # type: ignore[method-assign]
    with pytest.raises(EpisodeAttachmentError, match="release to host custody failed"):
        custody.release("custody-export-expired", "host-one", attachment, retain_until=15)
    record = custody.lookup("custody-export-expired")
    assert record is not None and record.phase is TerritoryCustodyPhase.RETIRING
    assert custody.retire("custody-export-expired", "host-one", provider).phase is TerritoryCustodyPhase.RETIRED
    custody.close()


def test_custody_database_has_one_live_writer(tmp_path: Path) -> None:
    path = tmp_path / "custody" / "territories.db"
    first = SqliteTerritoryCustody(path)
    with pytest.raises(StorageError, match="live writer"):
        SqliteTerritoryCustody(path)
    first.close()


def test_release_closes_operation_admission_and_waits_before_export(tmp_path: Path) -> None:
    provider = LocalProcessEnvironment()
    attachment, binding = _attachment(tmp_path, provider)
    custody = SqliteTerritoryCustody(tmp_path / "custody" / "territories.db", clock=lambda: 10)
    entered, finish, exported = Event(), Event(), Event()
    original_export = provider.export

    def recording_export(execution):
        exported.set()
        return original_export(execution)

    provider.export = recording_export  # type: ignore[method-assign]

    def active_operation() -> None:
        with binding._operation():  # noqa: SLF001 - pins the private host-operation barrier
            entered.set()
            assert finish.wait(2)

    with ThreadPoolExecutor(max_workers=2) as pool:
        running = pool.submit(active_operation)
        assert entered.wait(1)
        releasing = pool.submit(custody.release, "custody-drain", "host-one", attachment, retain_until=50)
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            try:
                with binding._operation():  # noqa: SLF001 - observe admission closing
                    pass
            except MotusBindingError:
                break
            time.sleep(0.01)
        else:
            pytest.fail("release did not close operation admission")
        assert not releasing.done() and not exported.is_set()
        finish.set()
        running.result(1)
        release = releasing.result(2)
    assert exported.is_set() and custody.lookup("custody-drain").phase is TerritoryCustodyPhase.RETAINED  # type: ignore[union-attr]
    custody.retire("custody-drain", "host-one", provider)
    custody.close()
    assert release.territory.operation_id == "territory-operation"


def test_one_provider_operation_cannot_have_two_live_custody_ids(tmp_path: Path) -> None:
    provider = LocalProcessEnvironment()
    attachment, _binding = _attachment(tmp_path, provider)
    custody = SqliteTerritoryCustody(tmp_path / "custody" / "territories.db", clock=lambda: 10)
    custody.begin_release("custody-a", "host-one", attachment, retain_until=50)
    with pytest.raises(StorageError, match="live custody obligation"):
        custody.begin_release("custody-b", "host-one", attachment, retain_until=50)
    [record] = custody.recover()
    assert record.custody_id == "custody-a" and record.phase is TerritoryCustodyPhase.RETIRING
    custody.retire("custody-a", "host-one", provider)
    custody.close()


@pytest.mark.parametrize("reuse", ("episode", "attachment"))
def test_reclaim_refuses_source_identities_without_changing_retained_custody(tmp_path: Path, reuse: str) -> None:
    provider = LocalProcessEnvironment()
    attachment, _binding = _attachment(tmp_path, provider)
    custody = SqliteTerritoryCustody(tmp_path / "custody" / "territories.db", clock=lambda: 10)
    custody.release("custody-distinct", "host-one", attachment, retain_until=50)

    with pytest.raises(ValueError, match="distinct"):
        custody.reclaim(
            "custody-distinct",
            "host-one",
            provider,
            episode_id=attachment.episode_id if reuse == "episode" else EpisodeId("episode-two"),
            snapshot=_snapshot("two"),
            attachment_id=attachment.attachment_id if reuse == "attachment" else "attachment-two",
            deadline=100,
        )
    assert custody.lookup("custody-distinct").phase is TerritoryCustodyPhase.RETAINED  # type: ignore[union-attr]
    custody.retire("custody-distinct", "host-one", provider)
    custody.close()


def test_malformed_nonidentity_state_becomes_retirable_but_malformed_identity_quarantines(tmp_path: Path) -> None:
    provider = LocalProcessEnvironment()
    attachment, _binding = _attachment(tmp_path, provider)
    path = tmp_path / "custody" / "territories.db"
    custody = SqliteTerritoryCustody(path, clock=lambda: 10)
    custody.release("custody-malformed", "host-one", attachment, retain_until=50)
    custody.close()
    with sqlite3.connect(path) as database:
        database.execute("UPDATE territory_custody SET capabilities='not-json' WHERE custody_id='custody-malformed'")
    recovered = SqliteTerritoryCustody(path, clock=lambda: 20)
    [retiring] = recovered.recover()
    assert retiring.phase is TerritoryCustodyPhase.RETIRING
    recovered.retire("custody-malformed", "host-one", provider)
    recovered.close()

    second_root = tmp_path / "second"
    second_root.mkdir()
    second, _binding = _attachment(second_root, provider)
    second_path = tmp_path / "other-custody" / "territories.db"
    custody = SqliteTerritoryCustody(second_path, clock=lambda: 10)
    custody.release("custody-bad-identity", "host-one", second, retain_until=50)
    custody.close()
    with sqlite3.connect(second_path) as database:
        database.execute("UPDATE territory_custody SET lease_id='' WHERE custody_id='custody-bad-identity'")
    quarantined = SqliteTerritoryCustody(second_path, clock=lambda: 20)
    with pytest.raises(StorageError, match="quarantined"):
        quarantined.recover()
    with sqlite3.connect(second_path) as database:
        assert database.execute(
            "SELECT phase FROM territory_custody WHERE custody_id='custody-bad-identity'"
        ).fetchone() == (TerritoryCustodyPhase.QUARANTINED.value,)
    quarantined.close()


@pytest.mark.parametrize("column", ("operation_id", "provider", "lease_id"))
def test_nontext_destruction_identity_quarantines_without_provider_cleanup(tmp_path: Path, column: str) -> None:
    provider = LocalProcessEnvironment()
    attachment, _binding = _attachment(tmp_path, provider)
    path = tmp_path / "custody" / "territories.db"
    custody = SqliteTerritoryCustody(path, clock=lambda: 10)
    custody.release("custody-binary-identity", "host-one", attachment, retain_until=50)
    custody.close()
    with sqlite3.connect(path) as database:
        database.execute(
            f"UPDATE territory_custody SET {column}=? WHERE custody_id=?",  # noqa: S608 - fixed parametrized column
            (sqlite3.Binary(b"territory-identity"), "custody-binary-identity"),
        )

    cleanup_called = False

    def forbidden_destroy(_lease):
        nonlocal cleanup_called
        cleanup_called = True
        raise AssertionError("malformed identity must never reach provider cleanup")

    provider.destroy = forbidden_destroy  # type: ignore[method-assign]
    recovered = SqliteTerritoryCustody(path, clock=lambda: 20)
    with pytest.raises(StorageError, match="quarantined"):
        recovered.recover()
    with pytest.raises(StorageError, match="malformed"):
        recovered.retire("custody-binary-identity", "host-one", provider)
    assert not cleanup_called
    with sqlite3.connect(path) as database:
        assert database.execute(
            "SELECT phase FROM territory_custody WHERE custody_id='custody-binary-identity'"
        ).fetchone() == (TerritoryCustodyPhase.QUARANTINED.value,)
    recovered.close()


def test_recovery_fences_an_attached_lease_instead_of_reconstructing_active_work(tmp_path: Path) -> None:
    provider = LocalProcessEnvironment()
    attachment, _binding = _attachment(tmp_path, provider)
    path = tmp_path / "custody" / "territories.db"
    custody = SqliteTerritoryCustody(path, clock=lambda: 10)
    custody.release("custody-attached-crash", "host-one", attachment, retain_until=50)
    reclaimed = custody.reclaim(
        "custody-attached-crash",
        "host-one",
        provider,
        episode_id=EpisodeId("episode-two"),
        snapshot=_snapshot("two"),
        attachment_id="attachment-two",
        deadline=100,
    )
    assert reclaimed.binding.lease_identity == attachment.binding.lease_identity
    custody.close()

    recovered = SqliteTerritoryCustody(path, clock=lambda: 20)
    [record] = recovered.recover()
    assert record.phase is TerritoryCustodyPhase.RETIRING
    assert recovered.retire("custody-attached-crash", "host-one", provider).phase is TerritoryCustodyPhase.RETIRED
    recovered.close()


def test_retirement_retries_unverified_cleanup_and_destroy_before_commit(tmp_path: Path) -> None:
    provider = LocalProcessEnvironment()
    attachment, _binding = _attachment(tmp_path, provider)
    custody = SqliteTerritoryCustody(tmp_path / "custody" / "territories.db", clock=lambda: 10)
    custody.release("custody-retire-retry", "host-one", attachment, retain_until=50)
    retained = custody.lookup("custody-retire-retry")
    assert retained is not None
    original_destroy = provider.destroy
    provider.destroy = lambda lease: CleanupResult(  # type: ignore[method-assign]
        lease.identity, CleanupDisposition.UNVERIFIED, "uncertain"
    )
    first = custody.retire("custody-retire-retry", "host-one", provider)
    assert first.phase is TerritoryCustodyPhase.RETIRING and provider.lookup(retained.lease.operation_id) is not None

    original_write = custody._write  # noqa: SLF001 - inject crash after provider destroy

    def destroy_then_break_commit(lease):
        result = original_destroy(lease)
        custody._write = lambda *args, **kwargs: (_ for _ in ()).throw(OSError("crash"))  # type: ignore[method-assign]  # noqa: SLF001
        return result

    provider.destroy = destroy_then_break_commit  # type: ignore[method-assign]
    with pytest.raises(OSError, match="crash"):
        custody.retire("custody-retire-retry", "host-one", provider)
    custody._write = original_write  # type: ignore[method-assign]  # noqa: SLF001
    provider.destroy = original_destroy  # type: ignore[method-assign]
    assert provider.lookup(retained.lease.operation_id) is None
    assert custody.retire("custody-retire-retry", "host-one", provider).phase is TerritoryCustodyPhase.RETIRED
    custody.close()
