from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from conftest import POSTGRES_IMAGE
from petrus.agenticus.attachment.binding import MotusAttachmentBinding
from petrus.agenticus.hands.workspace import MAX_READ_BYTES, MAX_STREAM_BYTES, MotusWorkspaceAdapter
from petrus.motus.execution import EnvironmentCapability, EnvironmentSpec
from petrus.motus.execution.archive import workspace_archive
from petrus.motus.execution.providers import DockerEnvironment, LocalProcessEnvironment


def test_local_workspace_adapter_runs_complete_public_motus_route(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "input.txt").write_text("needle\n" + "x" * (MAX_READ_BYTES + 10))
    provider = LocalProcessEnvironment()
    lease = provider.create("ds6-workspace-local", EnvironmentSpec())
    attachment = provider.attach(lease, workspace_archive(source), "input")
    adapter = MotusWorkspaceAdapter(provider, attachment, test_command=("/bin/sh", "-c", "test -f output.txt"))
    try:
        assert len(adapter.read("input.txt")) <= MAX_READ_BYTES
        assert adapter.search("needle", ".")[0].endswith("needle")
        shell = adapter.shell(("/bin/sh", "-c", "printf ok"), ".")
        assert (shell.returncode, shell.stdout, shell.stderr) == (0, "ok", "")
        staged = adapter.stage_write("call", "output.txt", "written")
        assert adapter.outstanding_stages() == 1
        assert adapter.commit_write(staged) == staged.digest
        assert adapter.outstanding_stages() == 0
        assert adapter.run_test().passed
        staged = adapter.stage_write("discard", "unused.txt", "secret")
        adapter.discard_write(staged)
        assert adapter.outstanding_stages() == 0
        adapter.stage_write("cleanup", "unused.txt", "secret")
        assert adapter.discard_all_stages() == 1
    finally:
        assert provider.destroy(lease).verified


def test_binary_output_preserves_the_public_utf8_byte_bound(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "binary").write_bytes(b"\xff" * (MAX_READ_BYTES + 10))
    provider = LocalProcessEnvironment()
    lease = provider.create("ds6-workspace-binary", EnvironmentSpec())
    attachment = provider.attach(lease, workspace_archive(source), "input")
    adapter = MotusWorkspaceAdapter(provider, attachment, test_command=("/bin/true",))
    try:
        content = adapter.read("binary")
        assert len(content.encode()) <= MAX_READ_BYTES
        shell = adapter.shell(("/bin/sh", "-c", f"head -c {MAX_STREAM_BYTES} binary"), ".")
        assert len(shell.stdout.encode()) <= MAX_STREAM_BYTES and shell.truncated
    finally:
        assert provider.destroy(lease).verified


def test_docker_workspace_adapter_and_binding_run_the_same_public_hands_route(tmp_path: Path) -> None:
    subprocess.run(("docker", "info"), check=True, capture_output=True)
    source = tmp_path / "source"
    source.mkdir()
    (source / "input.txt").write_text("needle\n")
    provider = DockerEnvironment()
    operation_id = f"ds6-docker-{hashlib.sha256(str(tmp_path).encode()).hexdigest()[:16]}"
    binding = MotusAttachmentBinding.open(
        provider,
        operation_id,
        EnvironmentSpec(
            image=POSTGRES_IMAGE,
            required_capabilities=frozenset({EnvironmentCapability.CONTAINER, EnvironmentCapability.WORKSPACE}),
        ),
        workspace_archive_bytes=workspace_archive(source),
        input_digest="input",
    )
    adapter = MotusWorkspaceAdapter(
        provider,
        binding.execution,
        test_command=("/bin/sh", "-c", "test -f output.txt"),
    )
    try:
        assert adapter.read("input.txt") == "needle\n"
        assert adapter.search("needle", ".")
        assert adapter.shell(("/bin/sh", "-c", "printf docker"), ".").stdout == "docker"
        staged = adapter.stage_write("docker-call", "output.txt", "written")
        assert adapter.commit_write(staged) == staged.digest
        assert adapter.run_test().passed
        assert binding.export_archive()
    finally:
        settlement = binding.settle()
    assert settlement.verified
