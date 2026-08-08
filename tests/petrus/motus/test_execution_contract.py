"""Public Motus execution-territory API and fail-closed lifecycle contract."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import cast

import pytest

from conftest import POSTGRES_IMAGE
from petrus.motus.execution import (
    MAX_COMMAND_OUTPUT_BYTES,
    MAX_PRIVATE_FILE_BYTES,
    MAX_PRIVATE_FILE_NAME_BYTES,
    MAX_PRIVATE_FILES_PER_ATTACHMENT,
    MAX_PRIVATE_FILE_TOTAL_BYTES,
    CleanupDisposition,
    CleanupResult,
    Command,
    EnvironmentCapability,
    EnvironmentLease,
    EnvironmentProvider,
    EnvironmentSpec,
    ExecutionProvenance,
    LeaseState,
    PrivateFile,
    PrivateFileCleanupResult,
    PrivateFileRef,
    PrivateFileTransfer,
    ReconcileClass,
)
from petrus.motus.execution.archive import extract_workspace_archive, workspace_archive
from petrus.motus.execution.gondolin import GondolinEnvironment
from petrus.motus.execution.providers import DockerEnvironment, E2bEnvironment, LocalProcessEnvironment


def test_public_surface_is_exact_optional_safe_and_owns_its_values() -> None:
    code = """
import sys
import petrus.motus.execution as execution
expected = {
    'MAX_COMMAND_OUTPUT_BYTES', 'MAX_PRIVATE_FILE_BYTES', 'MAX_PRIVATE_FILE_NAME_BYTES',
    'MAX_PRIVATE_FILES_PER_ATTACHMENT', 'MAX_PRIVATE_FILE_TOTAL_BYTES',
    'CleanupDisposition', 'CleanupResult', 'Command', 'CommandResult',
    'EnvironmentCapability', 'EnvironmentLease', 'EnvironmentProvider', 'EnvironmentSpec',
    'ExecutionAttachment', 'ExecutionProvenance', 'LeaseIdentity', 'LeaseState', 'ReconcileClass',
    'ReconcileResult', 'PrivateFile', 'PrivateFileCleanupResult', 'PrivateFileRef', 'PrivateFileTransfer',
}
assert set(execution.__all__) == expected
assert all(getattr(execution, name).__module__ == 'petrus.motus.execution' for name in expected if not name.startswith('MAX_'))
assert 'e2b' not in sys.modules
assert 'petrus.motus._execution.timeline' not in sys.modules
assert not any(name == 'petrus.agenticus' or name.startswith('petrus.agenticus.') for name in sys.modules)
"""
    subprocess.run([sys.executable, "-c", code], check=True)


def test_private_model_location_is_identity_compatible_without_owning_types() -> None:
    from petrus.motus._execution.model import EnvironmentSpec as CompatibilityEnvironmentSpec

    assert CompatibilityEnvironmentSpec is EnvironmentSpec
    assert CompatibilityEnvironmentSpec.__module__ == "petrus.motus.execution"


def test_provider_capability_discovery_is_semantic_and_provider_differences_are_explicit(tmp_path: Path) -> None:
    providers = (
        LocalProcessEnvironment(),
        DockerEnvironment(),
        E2bEnvironment(sdk_loader=lambda: None),
        GondolinEnvironment(tmp_path / "gondolin", sdk_module="unused.mjs"),
    )
    expected = {
        "local-process": {
            EnvironmentCapability.COMMAND_CANCELLATION,
            EnvironmentCapability.EXPLICIT_ENVIRONMENT,
            EnvironmentCapability.PRIVATE_FILE_TRANSFER,
            EnvironmentCapability.PROCESS_GROUP,
            EnvironmentCapability.WORKSPACE,
        },
        "docker": {
            EnvironmentCapability.CONTAINER,
            EnvironmentCapability.EXPLICIT_ENVIRONMENT,
            EnvironmentCapability.RECREATABLE_LOOKUP,
            EnvironmentCapability.TERRITORY_CANCELLATION,
            EnvironmentCapability.WORKSPACE,
        },
        "e2b": {
            EnvironmentCapability.COMMAND_CANCELLATION,
            EnvironmentCapability.EXPLICIT_ENVIRONMENT,
            EnvironmentCapability.RECREATABLE_LOOKUP,
            EnvironmentCapability.VM,
            EnvironmentCapability.WORKSPACE,
        },
        "gondolin": {
            EnvironmentCapability.EXPLICIT_ENVIRONMENT,
            EnvironmentCapability.MICROVM,
            EnvironmentCapability.PRIVATE_FILE_TRANSFER,
            EnvironmentCapability.RECREATABLE_LOOKUP,
            EnvironmentCapability.TERRITORY_CANCELLATION,
            EnvironmentCapability.VM,
            EnvironmentCapability.WORKSPACE,
        },
    }

    for provider in providers:
        assert isinstance(provider, EnvironmentProvider)
        assert provider.capabilities == {capability.value for capability in expected[provider.provider]}
    assert isinstance(providers[0], PrivateFileTransfer)
    assert not isinstance(providers[1], PrivateFileTransfer)
    assert not isinstance(providers[2], PrivateFileTransfer)
    assert isinstance(providers[3], PrivateFileTransfer)


def test_destroy_never_verifies_absence_for_a_foreign_provider(tmp_path: Path) -> None:
    providers = (
        LocalProcessEnvironment(),
        DockerEnvironment(),
        E2bEnvironment(sdk_loader=lambda: pytest.fail("foreign cleanup must not load the E2B SDK")),
        GondolinEnvironment(tmp_path / "gondolin", sdk_module="unused.mjs"),
    )
    foreign = EnvironmentLease(
        "foreign-cleanup",
        "foreign-provider",
        "foreign-lease",
        frozenset(),
        LeaseState.READY,
    )

    for provider in providers:
        result = provider.destroy(foreign)
        assert result.disposition is CleanupDisposition.UNVERIFIED
        assert not result.verified


def test_local_public_lifecycle_transfers_workspace_and_returns_verified_cleanup(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "input.txt").write_text("host")
    provider = LocalProcessEnvironment()
    operation_id = f"cv16-local-{os.getpid()}"
    spec = EnvironmentSpec(required_capabilities=frozenset({EnvironmentCapability.WORKSPACE}))

    lease = provider.create(operation_id, spec)
    assert provider.create(operation_id, spec) == lease
    attachment = provider.attach(lease, workspace_archive(source), "input-digest")
    result = provider.execute(
        attachment,
        Command(("/bin/sh", "-c", "cat input.txt; printf territory > output.txt")),
    )
    assert result.returncode == 0 and result.stdout == b"host"
    assert result.provenance.identity == lease.identity
    restored = tmp_path / "restored"
    extract_workspace_archive(provider.export(attachment), restored)
    assert (restored / "output.txt").read_text() == "territory"

    cleaned = provider.destroy(lease)
    assert cleaned == CleanupResult(lease.identity, CleanupDisposition.CLEAN)
    assert cleaned.verified and provider.lookup(operation_id) is None
    absent = provider.destroy(lease)
    assert absent.disposition is CleanupDisposition.NOT_CREATED and absent.verified
    unknown = LocalProcessEnvironment().destroy(lease)
    assert unknown.disposition is CleanupDisposition.UNVERIFIED and not unknown.verified


def test_local_destroy_refuses_stale_identity_and_retains_uncertain_custody(monkeypatch) -> None:
    provider = LocalProcessEnvironment()
    lease = provider.create("cv16-local-stale", EnvironmentSpec())
    stale = EnvironmentLease(
        lease.operation_id,
        lease.provider,
        "different-lease",
        lease.capabilities,
        LeaseState.READY,
    )
    assert provider.destroy(stale).disposition is CleanupDisposition.UNVERIFIED
    assert provider.lookup(lease.operation_id) == lease

    monkeypatch.setattr(shutil, "rmtree", lambda _path: (_ for _ in ()).throw(OSError("denied")))
    failed = provider.destroy(lease)
    assert failed.disposition is CleanupDisposition.UNVERIFIED and not failed.verified
    assert provider.lookup(lease.operation_id) == lease
    monkeypatch.undo()
    assert provider.destroy(lease).verified


def test_create_checks_capabilities_before_reusing_an_existing_operation() -> None:
    provider = LocalProcessEnvironment()
    lease = provider.create("cv16-capability-check", EnvironmentSpec())
    try:
        with pytest.raises(ValueError, match="unsupported capabilities"):
            provider.create(
                lease.operation_id,
                EnvironmentSpec(required_capabilities=frozenset({EnvironmentCapability.CONTAINER})),
            )
    finally:
        provider.destroy(lease)


def test_command_is_snapshotted_finite_and_uniformly_bounded() -> None:
    command = Command(("printf", "safe"), cwd=Path("subdirectory"))
    assert command.argv == ("printf", "safe") and command.cwd == Path("subdirectory")
    with pytest.raises(ValueError, match="environment capability"):
        EnvironmentSpec(required_capabilities=cast("frozenset[str]", frozenset({1})))
    with pytest.raises(ValueError, match="command requires"):
        Command(("true",), timeout=float("inf"))
    with pytest.raises(ValueError, match="command requires"):
        Command(("true",), timeout=True)
    with pytest.raises(ValueError, match="command requires"):
        Command(("true",), output_limit=MAX_COMMAND_OUTPUT_BYTES + 1)
    with pytest.raises(ValueError, match="command requires"):
        Command(("true",), output_limit=True)


def test_private_file_values_are_bounded_path_free_and_secret_safe() -> None:
    provenance = ExecutionProvenance("operation", "provider", "lease")
    value = PrivateFile("auth.json", b"canary-private-content")
    reference = PrivateFileRef("file", value.name, "attachment", provenance)
    cleaned = PrivateFileCleanupResult(
        "attachment",
        provenance,
        CleanupDisposition.CLEAN,
        removed=1,
    )
    roots = {"CODEX_HOME": reference}
    command = Command(("codex", "status"), private_roots=roots)
    roots.clear()

    assert command.private_roots == {"CODEX_HOME": reference}
    assert cleaned.verified and not cleaned.physical_erasure_guaranteed
    assert "canary-private-content" not in repr(value)
    assert "private_roots" not in repr(command)
    assert all(
        not hasattr(subject, attribute) for subject in (reference, cleaned) for attribute in ("path", "digest", "size")
    )

    for name in ("", ".", "..", "../auth.json", "auth/json", "auth\\json", " auth", "é", "a" * 65):
        with pytest.raises(ValueError, match="private file name"):
            PrivateFile(name, b"")
    with pytest.raises(TypeError, match="content must be bytes"):
        PrivateFile("auth.json", cast("bytes", "secret"))
    with pytest.raises(ValueError, match="exceeds"):
        PrivateFile("auth.json", b"x" * (MAX_PRIVATE_FILE_BYTES + 1))
    assert len("a" * MAX_PRIVATE_FILE_NAME_BYTES) == MAX_PRIVATE_FILE_NAME_BYTES
    assert PrivateFile("a" * MAX_PRIVATE_FILE_NAME_BYTES, b"").content == b""

    with pytest.raises(ValueError, match="private root"):
        Command(("true",), environment={"CODEX_HOME": "safe"}, private_roots={"CODEX_HOME": reference})
    with pytest.raises(ValueError, match="private root"):
        Command(("true",), private_roots={"BAD-NAME": reference})
    with pytest.raises(ValueError, match="private root"):
        Command(
            ("true",),
            private_roots={f"ROOT_{index}": reference for index in range(MAX_PRIVATE_FILES_PER_ATTACHMENT + 1)},
        )
    with pytest.raises(ValueError, match="private root"):
        Command(("true",), private_roots=cast("dict[str, PrivateFileRef]", {"ROOT": object()}))
    with pytest.raises(ValueError, match="non-negative"):
        PrivateFileCleanupResult("attachment", provenance, CleanupDisposition.CLEAN, removed=-1)
    assert MAX_PRIVATE_FILE_TOTAL_BYTES >= MAX_PRIVATE_FILE_BYTES


def test_docker_public_lifecycle_is_lookup_first_and_cleanup_is_identity_correlated(tmp_path: Path) -> None:
    subprocess.run(("docker", "info"), check=True, capture_output=True)
    provider = DockerEnvironment()
    operation_id = f"cv16-docker-{hashlib.sha256(str(tmp_path).encode()).hexdigest()[:16]}"
    spec = EnvironmentSpec(
        image=POSTGRES_IMAGE,
        required_capabilities=frozenset(
            {EnvironmentCapability.CONTAINER, EnvironmentCapability.TERRITORY_CANCELLATION}
        ),
    )
    lease = provider.create(operation_id, spec)
    try:
        assert DockerEnvironment().create(operation_id, spec).identity == lease.identity
        stale = EnvironmentLease(operation_id, lease.provider, "different-container", lease.capabilities, lease.state)
        assert provider.destroy(stale).disposition is CleanupDisposition.UNVERIFIED
        current = provider.lookup(operation_id)
        assert current is not None and current.identity == lease.identity
        attachment = provider.attach(lease, workspace_archive(tmp_path), "input-digest")
        result = provider.execute(attachment, Command(("/bin/sh", "-c", "printf docker > result")))
        assert result.returncode == 0 and result.provenance.identity == lease.identity
    finally:
        cleanup = provider.destroy(lease)
    assert cleanup.disposition is CleanupDisposition.CLEAN and cleanup.verified
    assert provider.lookup(operation_id) is None
    assert provider.reconcile(operation_id).classification is ReconcileClass.RETRYABLE
