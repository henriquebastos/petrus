from __future__ import annotations

from pathlib import Path
import threading
import time

import pytest

from petrus.motus.execution import (
    CleanupDisposition,
    Command,
    EnvironmentCapability,
    EnvironmentLease,
    EnvironmentSpec,
    ExecutionAttachment,
    ExecutionProvenance,
    LeaseState,
    PrivateFile,
    PrivateFileRef,
    PrivateFileTransfer,
)
from petrus.motus.execution.archive import extract_workspace_archive, workspace_archive
from petrus.motus.execution.providers import DockerEnvironment, E2bEnvironment, LocalProcessEnvironment


def _local(tmp_path: Path, operation: str = "private-file"):
    provider = LocalProcessEnvironment()
    lease = provider.create(
        operation,
        EnvironmentSpec(required_capabilities=frozenset({EnvironmentCapability.PRIVATE_FILE_TRANSFER})),
    )
    source = tmp_path / f"source-{operation}"
    source.mkdir()
    attachment = provider.attach(lease, workspace_archive(source), "input-digest")
    return provider, lease, attachment


def test_local_private_file_full_custody_route_is_bounded_and_workspace_free(tmp_path: Path) -> None:
    provider, lease, attachment = _local(tmp_path)
    assert isinstance(provider, PrivateFileTransfer)
    canary = b"private-canary-never-in-workspace"
    reference = provider.import_private_file(attachment, PrivateFile("auth.json", canary))
    assert reference.attachment_id == attachment.attachment_id
    assert reference.provenance.identity == lease.identity
    assert all(not hasattr(reference, attribute) for attribute in ("path", "digest", "size", "content"))

    result = provider.execute(
        attachment,
        Command(
            (
                "/bin/sh",
                "-c",
                'printf -- "-updated" >> "$CODEX_HOME/auth.json"; printf "%s" "$CODEX_HOME"',
            ),
            private_roots={"CODEX_HOME": reference},
        ),
    )
    assert result.returncode == 0 and result.stdout == b"[PRIVATE_ROOT]"
    assert canary not in result.stdout + result.stderr
    exported = provider.export_private_file(attachment, reference)
    assert exported == PrivateFile("auth.json", canary + b"-updated")

    archive = provider.export(attachment)
    assert canary not in archive
    restored = tmp_path / "restored"
    extract_workspace_archive(archive, restored)
    assert not any(restored.rglob("auth.json"))

    deleted = provider.delete_private_file(attachment, reference)
    assert deleted.disposition is CleanupDisposition.CLEAN and deleted.removed == 1 and deleted.verified
    repeated = provider.delete_private_file(attachment, reference)
    assert repeated.disposition is CleanupDisposition.NOT_CREATED and repeated.removed == 0 and repeated.verified
    assert not repeated.physical_erasure_guaranteed
    assert provider.cleanup_private_files(attachment).verified

    territory = provider._territories[lease.lease_id]
    assert provider.destroy(lease).verified
    assert not territory.exists()


def test_local_private_refs_are_exactly_attachment_and_lease_fenced(tmp_path: Path) -> None:
    provider, lease, first = _local(tmp_path, "private-fences")
    reference = provider.import_private_file(first, PrivateFile("auth.json", b"secret"))
    forged = PrivateFileRef("missing", "auth.json", first.attachment_id, reference.provenance)
    assert provider.delete_private_file(first, forged).disposition is CleanupDisposition.UNVERIFIED

    stale_lease = EnvironmentLease(lease.operation_id, lease.provider, "stale", lease.capabilities, LeaseState.READY)
    stale_attachment = ExecutionAttachment("stale", stale_lease, "digest", first.workspace)
    stale_ref = PrivateFileRef(
        "missing",
        "auth.json",
        "stale",
        ExecutionProvenance(stale_lease.operation_id, stale_lease.provider, stale_lease.lease_id),
    )
    assert provider.delete_private_file(stale_attachment, stale_ref).disposition is CleanupDisposition.UNVERIFIED

    second_source = tmp_path / "second"
    second_source.mkdir()
    second = provider.attach(lease, workspace_archive(second_source), "second-digest")
    assert second.attachment_id != first.attachment_id
    with pytest.raises(ValueError, match="not current"):
        provider.export_private_file(first, reference)
    assert provider.delete_private_file(first, reference).disposition is CleanupDisposition.UNVERIFIED
    assert provider.destroy(lease).verified


def test_local_private_symlink_replacement_never_reads_or_unlinks_target(tmp_path: Path) -> None:
    provider, lease, attachment = _local(tmp_path, "private-symlink")
    reference = provider.import_private_file(attachment, PrivateFile("auth.json", b"private"))
    record = provider._private_files[lease.lease_id][reference.file_id]
    victim = tmp_path / "victim"
    victim.write_bytes(b"victim")
    (record.root / reference.name).unlink()
    (record.root / reference.name).symlink_to(victim)

    with pytest.raises(RuntimeError, match="could not be verified"):
        provider.export_private_file(attachment, reference)
    cleanup = provider.delete_private_file(attachment, reference)
    assert cleanup.disposition is CleanupDisposition.UNVERIFIED and not cleanup.verified
    assert victim.read_bytes() == b"victim"
    replacement = tmp_path / "replacement"
    replacement.mkdir()
    with pytest.raises(RuntimeError, match="cleanup could not be verified"):
        provider.attach(lease, workspace_archive(replacement), "replacement")
    assert provider.destroy(lease).verified


def test_local_private_operations_are_excluded_while_command_is_active(tmp_path: Path) -> None:
    provider, lease, attachment = _local(tmp_path, "private-active")
    reference = provider.import_private_file(attachment, PrivateFile("auth.json", b"private"))
    results = []

    thread = threading.Thread(
        target=lambda: results.append(
            provider.execute(
                attachment,
                Command(("/bin/sh", "-c", "sleep 0.4"), private_roots={"CODEX_HOME": reference}),
            )
        )
    )
    thread.start()
    deadline = time.monotonic() + 1
    while lease.lease_id not in provider._processes and time.monotonic() < deadline:
        time.sleep(0.01)
    with pytest.raises(RuntimeError, match="idle territory"):
        provider.import_private_file(attachment, PrivateFile("other", b"private"))
    with pytest.raises(RuntimeError, match="idle territory"):
        provider.export_private_file(attachment, reference)
    assert provider.delete_private_file(attachment, reference).disposition is CleanupDisposition.UNVERIFIED
    thread.join(timeout=2)
    assert not thread.is_alive() and results[0].returncode == 0
    assert provider.cleanup_private_files(attachment).verified
    assert provider.destroy(lease).verified


def test_local_private_file_count_and_total_bounds_are_attachment_scoped(tmp_path: Path, monkeypatch) -> None:
    from petrus.motus._execution import providers

    provider, lease, attachment = _local(tmp_path, "private-bounds")
    monkeypatch.setattr(providers, "MAX_PRIVATE_FILES_PER_ATTACHMENT", 2)
    monkeypatch.setattr(providers, "MAX_PRIVATE_FILE_TOTAL_BYTES", 5)
    provider.import_private_file(attachment, PrivateFile("one", b"12"))
    provider.import_private_file(attachment, PrivateFile("two", b"345"))
    with pytest.raises(ValueError, match="bounds"):
        provider.import_private_file(attachment, PrivateFile("three", b""))
    assert provider.cleanup_private_files(attachment).removed == 2
    assert provider.destroy(lease).verified


def test_noncapable_providers_reject_private_roots_before_lookup_or_allocation() -> None:
    provenance = ExecutionProvenance("operation", "docker", "lease")
    reference = PrivateFileRef("file", "auth.json", "attachment", provenance)
    lease = EnvironmentLease("operation", "docker", "lease", frozenset(), LeaseState.READY)
    attachment = ExecutionAttachment("attachment", lease, "digest", Path("/workspace"))
    command = Command(("true",), private_roots={"CODEX_HOME": reference})

    with pytest.raises(ValueError, match="private-file-transfer"):
        DockerEnvironment().execute(attachment, command)
    with pytest.raises(ValueError, match="private-file-transfer"):
        E2bEnvironment(sdk_loader=lambda: pytest.fail("private roots must reject before SDK lookup")).execute(
            attachment,
            command,
        )
