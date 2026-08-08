from __future__ import annotations

import json
import io
import os
import signal
import subprocess
import tarfile
import threading
import hashlib
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import POSTGRES_IMAGE
from petrus.motus._execution.artifacts import (
    ArtifactStore,
    ProducerCorrelation,
)
from petrus.motus._execution.timeline import TelemetryTimelineHandler, Timeline, TimelineEvent
from petrus.motus.execution import (
    CleanupDisposition,
    Command,
    EnvironmentLease,
    EnvironmentSpec,
    ExecutionAttachment,
    LeaseState,
    ReconcileClass,
)
from petrus.motus.execution.archive import extract_workspace_archive, workspace_archive
from petrus.motus.execution.providers import DockerEnvironment, E2bEnvironment, LocalProcessEnvironment


@pytest.fixture(params=("local", "docker"))
def environment(request, tmp_path):
    if request.param == "local":
        provider = LocalProcessEnvironment()
        spec = EnvironmentSpec(required_capabilities=frozenset({"explicit-environment"}))
    else:
        subprocess.run(("docker", "info"), check=True, capture_output=True)
        provider = DockerEnvironment()
        spec = EnvironmentSpec(
            image=POSTGRES_IMAGE,
            required_capabilities=frozenset({"container", "explicit-environment"}),
        )
    identity = hashlib.sha256(request.node.name.encode()).hexdigest()[:16]
    lease = provider.provision(f"cv10-{identity}-{os.getpid()}", spec)
    source = tmp_path / "source"
    source.mkdir()
    attachment = provider.attach(lease, workspace_archive(source), "input-digest")
    yield provider, lease, attachment
    provider.destroy(lease)


def test_provider_neutral_lifecycle_and_environment_custody(environment, monkeypatch):
    provider, lease, attachment = environment
    monkeypatch.setenv("GITHUB_TOKEN", "should-never-cross-the-door")
    assert lease.state is LeaseState.READY
    assert provider.lookup(lease.operation_id) == lease

    result = provider.execute(
        attachment,
        Command(
            ("/bin/sh", "-c", 'printf \'%s|%s\' "$ALLOWED" "${GITHUB_TOKEN-unset}" > result; cat result'),
            environment={"ALLOWED": "yes"},
        ),
    )
    assert result.returncode == 0
    assert result.stdout == b"yes|unset"
    restored = attachment.workspace.parent / "restored" if lease.provider == "local-process" else None
    if restored is not None:
        extract_workspace_archive(provider.export(attachment), restored)
        assert (restored / "result").read_text() == "yes|unset"
    assert result.provenance.operation_id == lease.operation_id

    superseded = provider.execute(attachment, Command(("/bin/sh", "-c", "exit 99"), is_current=lambda: False))
    assert superseded.superseded
    timed_out = provider.execute(attachment, Command(("/bin/sh", "-c", "sleep 10"), timeout=0.1))
    assert timed_out.timed_out
    provider.destroy(lease)
    provider.destroy(lease)
    assert provider.lookup(lease.operation_id) is None


def test_docker_lookup_first_survives_adapter_recreation_and_is_unique(tmp_path):
    operation_id = f"cv10-recreate-{os.getpid()}"
    first = DockerEnvironment()
    lease = first.provision(operation_id, EnvironmentSpec(image=POSTGRES_IMAGE))
    try:
        recreated = DockerEnvironment()
        assert recreated.provision(operation_id, EnvironmentSpec(image=POSTGRES_IMAGE)) == lease
        attachment = recreated.attach(lease, workspace_archive(tmp_path), "digest")
        assert recreated.execute(attachment, Command(("/bin/sh", "-c", "printf recreated > state"))).returncode == 0
        with pytest.raises(ValueError, match="collides"):
            recreated.provision(operation_id, EnvironmentSpec(image="materially-different"))
        found = subprocess.run(
            ("docker", "ps", "-aq", "--filter", f"label=run.petrus.operation={operation_id}"),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.split()
        assert found == [lease.lease_id]
        info = json.loads(
            subprocess.run(("docker", "inspect", lease.lease_id), check=True, capture_output=True).stdout
        )[0]
        assert not [mount for mount in info["Mounts"] if mount["Type"] == "bind"]
        subprocess.run(("docker", "stop", lease.lease_id), check=True, capture_output=True)
        assert recreated.reconcile(operation_id).classification is ReconcileClass.TERMINAL
        with pytest.raises(RuntimeError, match="terminal prior territory"):
            recreated.provision(operation_id, EnvironmentSpec(image=POSTGRES_IMAGE))
    finally:
        first.destroy(lease)


def test_artifacts_are_host_custodied_integrity_checked_and_provider_neutral(tmp_path):
    root = tmp_path / "artifacts"
    producer = ProducerCorrelation("operation", "local-process", "opaque")
    reference = ArtifactStore(root).put(
        b"portable result", media_type="text/plain", retention_class="evidence", producer=producer
    )
    assert ArtifactStore(root).read(reference) == b"portable result"
    assert reference.producer == producer
    data_path = root / reference.digest[:2] / f"{reference.digest}.data"
    data_path.write_bytes(b"tampered result")
    with pytest.raises(ValueError, match="integrity"):
        ArtifactStore(root).read(reference)


def test_artifact_retention_prunes_oldest_without_removing_current_authority(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    producer = ProducerCorrelation("operation", "provider", "lease")
    references = [
        store.put(
            f"artifact-{index}".encode(),
            media_type="text/plain",
            retention_class="operational",
            producer=producer,
        )
        for index in range(4)
    ]
    removed = store.prune(2, protected=frozenset({references[-1].digest}))
    assert len(removed) == 2
    assert store.read(references[-1]) == b"artifact-3"
    assert len(list(store.root.glob("*/*.data"))) == 2


def test_timeline_redacts_recursively_correlates_and_has_no_authority(tmp_path):
    artifact_store = ArtifactStore(tmp_path / "artifacts")
    reference = artifact_store.put(
        b"result", media_type="text/plain", retention_class="result", producer=ProducerCorrelation("op", "docker", "id")
    )
    path = tmp_path / "timeline.jsonl"
    timeline = Timeline(path)
    timeline.append(
        TimelineEvent(
            "event",
            "execution.finished",
            1,
            "worker",
            1,
            datetime.now(UTC),
            "execute",
            "succeeded",
            {"operation_id": "op", "artifact_digest": reference.digest},
            ("cause",),
            {"nested": {"password": "raw", "safe": "visible"}, "auth_headers": {"Authorization": "Bearer raw"}},
            "short-lived",
        )
    )
    record = json.loads(path.read_text())
    assert record["correlation"]["artifact_digest"] == reference.digest
    assert record["metadata"] == {
        "auth_headers": "[REDACTED]",
        "nested": {"password": "[REDACTED]", "safe": "visible"},
    }
    timeline.delete()
    assert not path.exists()
    assert artifact_store.read(reference) == b"result"


def test_timeline_mints_sequences_across_restart_and_retention_is_sink_policy(tmp_path):
    path = tmp_path / "timeline.jsonl"
    timeline = Timeline(path, retain=2)
    first = timeline.observe(
        "environment.provisioned",
        producer="motus.worker-1",
        phase="provision",
        outcome="ready",
        correlation={"operation_id": "operation"},
    )
    second = timeline.observe(
        "agent.turn.completed",
        producer="application.agent-1",
        phase="turn",
        outcome="completed",
        correlation={"operation_id": "operation", "thread_id": "thread"},
    )
    third = Timeline(path, retain=2).observe(
        "environment.destroyed",
        producer="motus.worker-1",
        phase="destroy",
        outcome="completed",
        correlation={"operation_id": "operation"},
        causal_refs=(first.event_id, second.event_id),
    )
    records = [json.loads(line) for line in path.read_text().splitlines()]
    assert [record["event_kind"] for record in records] == ["agent.turn.completed", "environment.destroyed"]
    assert third.producer_sequence == 2
    assert records[-1]["causal_refs"] == [first.event_id, second.event_id]


def test_telemetry_handler_builds_one_redacted_correlated_noncanonical_stream(tmp_path):
    import logging

    path = tmp_path / "timeline.jsonl"
    timeline = Timeline(path)
    handler = TelemetryTimelineHandler(timeline)
    handler.emit(
        logging.LogRecord(
            "impetus.telemetry",
            logging.INFO,
            __file__,
            1,
            json.dumps(
                {
                    "event": "impetus_worker_activity_finished",
                    "instance": "instance-1",
                    "occurrence": 9,
                    "attempt": "attempt-1",
                    "epoch": 2,
                    "worker": "worker-1",
                    "outcome": "completed",
                    "authorization": "Bearer secret-value",
                    "note": "credential sk-or-secretvalue must not survive",
                    "ts": 1,
                }
            ),
            (),
            None,
        )
    )
    record = json.loads(path.read_text())
    assert record["event_kind"] == "impetus_worker_activity_finished"
    assert record["phase"] == "finish" and record["outcome"] == "completed"
    assert record["correlation"] == {
        "attempt": "attempt-1",
        "epoch": "2",
        "instance": "instance-1",
        "occurrence": "9",
        "worker": "worker-1",
    }
    assert record["metadata"]["authorization"] == "[REDACTED]"
    assert "secretvalue" not in record["metadata"]["note"]


def test_telemetry_handler_failure_is_non_blocking(tmp_path):
    handler = TelemetryTimelineHandler(Timeline(tmp_path / "timeline.jsonl"))
    handler.timeline.observe = lambda *args, **kwargs: (_ for _ in ()).throw(OSError("full"))
    handler.emit(__import__("logging").LogRecord("x", 20, __file__, 1, '{"event":"safe"}', (), None))


def test_capabilities_and_reconciliation_are_truthful(tmp_path):
    provider = LocalProcessEnvironment()
    assert provider.reconcile("absent").classification is ReconcileClass.RETRYABLE
    with pytest.raises(ValueError, match="unsupported"):
        provider.provision("unsupported", EnvironmentSpec(required_capabilities=frozenset({"container"})))
    lease = provider.provision("known", EnvironmentSpec())
    assert provider.reconcile("known").classification is ReconcileClass.UNCERTAIN
    provider.destroy(lease)


def test_local_cwd_still_resolves_symlinks_before_containment(tmp_path):
    provider = LocalProcessEnvironment()
    lease = provider.provision("local-cwd-symlink", EnvironmentSpec())
    attachment = provider.attach(lease, workspace_archive(tmp_path), "digest")
    outside = tmp_path / "outside"
    outside.mkdir()
    (attachment.workspace / "escape").symlink_to(outside, target_is_directory=True)
    try:
        with pytest.raises(ValueError, match="escapes"):
            provider.execute(attachment, Command(("true",), cwd=Path("escape")))
    finally:
        provider.destroy(lease)


def test_cross_provider_workspace_handoff_has_no_shared_path(tmp_path):
    subprocess.run(("docker", "info"), check=True, capture_output=True)
    source = tmp_path / "source"
    source.mkdir()
    (source / "history").write_text("source")
    initial = workspace_archive(source)
    local = LocalProcessEnvironment()
    local_lease = local.provision(f"handoff-local-{os.getpid()}", EnvironmentSpec())
    local_attachment = local.attach(local_lease, initial, "source")
    local.execute(local_attachment, Command(("/bin/sh", "-c", "printf -- '-local' >> history")))
    local_workspace = local_attachment.workspace
    store = ArtifactStore(tmp_path / "store")
    ref = store.put(
        local.export(local_attachment),
        media_type="application/x-tar",
        retention_class="handoff",
        producer=ProducerCorrelation(local_lease.operation_id, local_lease.provider, local_lease.lease_id),
    )
    local.destroy(local_lease)
    assert not local_workspace.exists()

    docker = DockerEnvironment()
    docker_lease = docker.provision(f"handoff-docker-{os.getpid()}", EnvironmentSpec(image=POSTGRES_IMAGE))
    try:
        docker_attachment = docker.attach(docker_lease, store.read(ref), ref.digest)
        assert docker_attachment.workspace != local_workspace
        result = docker.execute(
            docker_attachment, Command(("/bin/sh", "-c", "cat history; printf -- '-docker' >> history"))
        )
        assert result.stdout == b"source-local"
        final = docker.export(docker_attachment)
        mounts = json.loads(
            subprocess.run(("docker", "inspect", docker_lease.lease_id), check=True, capture_output=True).stdout
        )[0]["Mounts"]
        assert not [mount for mount in mounts if mount["Type"] == "bind"]
    finally:
        docker.destroy(docker_lease)
    assert docker.lookup(docker_lease.operation_id) is None
    restored = tmp_path / "restored"
    extract_workspace_archive(final, restored)
    assert (restored / "history").read_text() == "source-local-docker"


def test_tar_rejects_escape_links_and_special_files(tmp_path):
    for configure in (
        lambda item: setattr(item, "name", "../escape"),
        lambda item: (setattr(item, "type", tarfile.SYMTYPE), setattr(item, "linkname", "../../escape")),
        lambda item: setattr(item, "type", tarfile.FIFOTYPE),
    ):
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w") as archive:
            item = tarfile.TarInfo("member")
            configure(item)
            archive.addfile(item)
        with pytest.raises(ValueError, match="unsafe|unsupported"):
            extract_workspace_archive(output.getvalue(), tmp_path / str(len(output.getvalue())))

    duplicate = io.BytesIO()
    with tarfile.open(fileobj=duplicate, mode="w") as archive:
        archive.addfile(tarfile.TarInfo("same"))
        archive.addfile(tarfile.TarInfo("same"))
    with pytest.raises(ValueError, match="duplicate"):
        extract_workspace_archive(duplicate.getvalue(), tmp_path / "duplicate")


def test_workspace_archive_member_and_size_limits_are_enforced(tmp_path, monkeypatch):
    from petrus.motus._execution import artifacts

    (tmp_path / "one").write_text("1")
    (tmp_path / "two").write_text("2")
    monkeypatch.setattr(artifacts, "MAX_ARCHIVE_MEMBERS", 1)
    with pytest.raises(ValueError, match="too many"):
        workspace_archive(tmp_path)
    monkeypatch.setattr(artifacts, "MAX_ARCHIVE_MEMBERS", 10)
    monkeypatch.setattr(artifacts, "MAX_EXTRACTED_BYTES", 1)
    with pytest.raises(ValueError, match="extracted size"):
        workspace_archive(tmp_path)


def test_local_collection_drains_large_output_and_kills_sigterm_ignoring_process(tmp_path):
    provider = LocalProcessEnvironment()
    lease = provider.provision("collection", EnvironmentSpec())
    attachment = provider.attach(lease, workspace_archive(tmp_path), "digest")
    try:
        large = provider.execute(
            attachment, Command(("/bin/sh", "-c", "head -c 2000000 /dev/zero"), output_limit=1000, timeout=5)
        )
        assert large.returncode == 0 and large.output_truncated and len(large.stdout) == 1000
        timeout = provider.execute(
            attachment, Command(("/bin/sh", "-c", "trap '' TERM; while :; do sleep 1; done"), timeout=0.1)
        )
        assert timeout.timed_out and timeout.returncode == -signal.SIGKILL
    finally:
        provider.destroy(lease)


def test_command_snapshots_and_validates_environment():
    environment = {"SAFE": "value"}
    command = Command(("true",), environment=environment)
    environment["SAFE"] = "changed"
    assert command.environment == {"SAFE": "value"}
    for invalid in (
        {"": "value"},
        {"BAD=KEY": "value"},
        {"BAD-KEY": "value"},
        {"BAD": "nul\x00value"},
        {"BAD": 1},
    ):
        with pytest.raises(ValueError, match="invalid"):
            Command(("true",), environment=invalid)


def test_docker_command_credentials_are_not_exposed_in_host_argv(monkeypatch):
    provider = DockerEnvironment()
    lease = EnvironmentLease("operation", "docker", "container", provider.capabilities, LeaseState.READY)
    attachment = ExecutionAttachment("attachment", lease, "digest", Path("/workspace"))
    captured = {}

    class Process:
        returncode = 0

        def communicate(self, timeout=None):
            del timeout
            return b"", b""

        def poll(self):
            return 0

    def popen(argv, **kwargs):
        captured.update(argv=tuple(argv), **kwargs)
        return Process()

    monkeypatch.setenv("GITHUB_TOKEN", "host-authority")
    monkeypatch.setattr(provider, "lookup", lambda operation_id: lease)
    monkeypatch.setattr(subprocess, "Popen", popen)

    result = provider.execute(
        attachment,
        Command(("agent", "run"), environment={"OPENROUTER_API_KEY": "agent-secret", "SAFE": "value"}),
    )

    assert result.returncode == 0
    assert "agent-secret" not in "\0".join(captured["argv"])
    assert captured["env"]["OPENROUTER_API_KEY"] == "agent-secret"
    assert "GITHUB_TOKEN" not in captured["env"]
    assert captured["argv"].count("OPENROUTER_API_KEY") == 1


class _FakeE2bHandle:
    def __init__(self, command: str, *, blocking: bool = False):
        self.command = command
        self.blocking = blocking
        self.killed = threading.Event()

    def wait(self, *, on_stdout, on_stderr):
        del on_stderr
        if self.blocking:
            self.killed.wait(2)
            return SimpleNamespace(exit_code=-signal.SIGKILL, stdout="", stderr="")
        if self.command == "transport failure":
            raise RuntimeError("E2B command transport failed")
        if self.command == "large output":
            on_stdout("x" * 100)
            return SimpleNamespace(exit_code=0, stdout="x" * 100, stderr="")
        on_stdout("vm-output")
        return SimpleNamespace(exit_code=0, stdout="vm-output", stderr="")

    def kill(self):
        self.killed.set()
        return True


class _FakeE2bFiles:
    def __init__(self, sandbox):
        self.sandbox = sandbox
        self.entries = {}

    def write(self, path, data):
        self.entries[path] = bytes(data)

    def read(self, path, *, format):
        assert format == "bytes"
        return self.entries[path]

    def remove(self, path):
        self.entries.pop(path, None)


class _FakeE2bCommands:
    def __init__(self, sandbox):
        self.sandbox = sandbox
        self.executions = []

    def run(self, command, **kwargs):
        import shlex

        self.executions.append((command, kwargs))
        if kwargs.get("background"):
            handle = _FakeE2bHandle(command, blocking=command == "sleep forever")
            self.sandbox.handles.append(handle)
            return handle
        parts = shlex.split(command)
        if command.startswith("rm -rf /home/user/workspace"):
            self.sandbox.workspace = self.sandbox.files.entries[parts[parts.index("-xf") + 1]]
        elif command.startswith("tar -cf"):
            self.sandbox.files.entries[parts[2]] = self.sandbox.workspace
        return SimpleNamespace(exit_code=0, stdout="", stderr="")


class _FakeE2bSandbox:
    entries = {}
    counter = 0

    def __init__(self, sandbox_id, metadata, template):
        self.sandbox_id = sandbox_id
        self.metadata = dict(metadata)
        self.template = template
        self.state = "running"
        self.workspace = b""
        self.handles = []
        self.files = _FakeE2bFiles(self)
        self.commands = _FakeE2bCommands(self)

    @classmethod
    def create(cls, *, template, metadata, **kwargs):
        assert kwargs["envs"] == {} and kwargs["secure"] is True
        assert "api_key" not in kwargs
        cls.counter += 1
        sandbox = cls(f"sandbox-{cls.counter}", metadata, template)
        cls.entries[sandbox.sandbox_id] = sandbox
        return sandbox

    @classmethod
    def connect(cls, sandbox_id, **kwargs):
        del kwargs
        return cls.entries[sandbox_id]

    @classmethod
    def list(cls, *, query, limit, **kwargs):
        del kwargs
        matching = [
            SimpleNamespace(
                sandbox_id=sandbox.sandbox_id,
                metadata=sandbox.metadata,
                state=SimpleNamespace(value=sandbox.state),
            )
            for sandbox in cls.entries.values()
            if sandbox.state != "killed"
            and all(sandbox.metadata.get(key) == value for key, value in query.metadata.items())
        ][:limit]
        return _FakeE2bPaginator(matching)

    def kill(self):
        self.state = "killed"
        for handle in self.handles:
            handle.kill()


class _FakeE2bPaginator:
    def __init__(self, entries):
        self.entries = entries
        self.has_next = bool(entries)

    def next_items(self, **kwargs):
        del kwargs
        self.has_next = False
        return self.entries


class _FakeE2bQuery:
    def __init__(self, *, metadata):
        self.metadata = metadata


@pytest.fixture
def fake_e2b_sdk(monkeypatch):
    monkeypatch.delenv("E2B_API_KEY", raising=False)
    _FakeE2bSandbox.entries = {}
    _FakeE2bSandbox.counter = 0
    return SimpleNamespace(Sandbox=_FakeE2bSandbox, SandboxQuery=_FakeE2bQuery)


def test_e2b_vm_lifecycle_is_lookup_first_artifact_based_and_recoverable(tmp_path, fake_e2b_sdk):
    operation_id = "cv10-e2b-recovery"
    source = tmp_path / "source"
    source.mkdir()
    (source / "evidence").write_text("portable")
    spec = EnvironmentSpec(image="petrus-agent-template", required_capabilities=frozenset({"vm"}))
    first = E2bEnvironment(sdk_loader=lambda: fake_e2b_sdk)
    lease = first.provision(operation_id, spec)
    attachment = first.attach(lease, workspace_archive(source), "digest")

    recreated = E2bEnvironment(sdk_loader=lambda: fake_e2b_sdk)
    assert recreated.provision(operation_id, spec) == lease
    with pytest.raises(ValueError, match="collides"):
        recreated.provision(operation_id, EnvironmentSpec(image="other-template"))
    recovered_attachment = recreated.attach(lease, recreated.export(attachment), "recovered")
    result = recreated.execute(
        recovered_attachment,
        Command(("tool", "argument with spaces; $(unsafe)"), environment={"ALLOWED": "yes"}),
    )
    assert result.stdout == b"vm-output"
    assert result.provenance.provider == "e2b"
    command, options = _FakeE2bSandbox.entries[lease.lease_id].commands.executions[-1]
    assert command == "tool 'argument with spaces; $(unsafe)'"
    assert options["envs"] == {"ALLOWED": "yes"}
    assert options["cwd"] == "/home/user/workspace"
    assert all(
        " /workspace" not in command for command, _ in _FakeE2bSandbox.entries[lease.lease_id].commands.executions
    )
    assert recreated.reconcile(operation_id).classification is ReconcileClass.UNCERTAIN
    stale = EnvironmentLease(operation_id, lease.provider, "different-vm", lease.capabilities, lease.state)
    assert recreated.destroy(stale).disposition is CleanupDisposition.UNVERIFIED
    assert recreated.lookup(operation_id) == lease
    cleanup = recreated.destroy(lease)
    assert cleanup.disposition is CleanupDisposition.CLEAN and cleanup.identity == lease.identity
    assert recreated.lookup(operation_id) is None
    assert recreated.reconcile(operation_id).classification is ReconcileClass.RETRYABLE


def test_e2b_vm_cwd_remains_a_guest_path_when_the_host_remaps_home(tmp_path, fake_e2b_sdk, monkeypatch):
    provider = E2bEnvironment(sdk_loader=lambda: fake_e2b_sdk)
    lease = provider.provision("e2b-guest-cwd", EnvironmentSpec(image="petrus-agent-template"))
    attachment = provider.attach(lease, workspace_archive(tmp_path), "digest")
    original_resolve = Path.resolve

    def remapped_resolve(path: Path, *args, **kwargs) -> Path:
        if path.is_relative_to(Path("/home")):
            return Path("/System/Volumes/Data") / path.relative_to("/")
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", remapped_resolve)
    try:
        provider.execute(attachment, Command(("tool",), cwd=Path(".")))
        _, options = _FakeE2bSandbox.entries[lease.lease_id].commands.executions[-1]
        assert options["cwd"] == "/home/user/workspace"
        provider.execute(attachment, Command(("tool",), cwd=Path("nested/..")))
        _, normalized = _FakeE2bSandbox.entries[lease.lease_id].commands.executions[-1]
        assert normalized["cwd"] == "/home/user/workspace"
        with pytest.raises(ValueError, match="escapes"):
            provider.execute(attachment, Command(("tool",), cwd=Path("../escape")))
    finally:
        provider.destroy(lease)


def test_e2b_vm_creation_lookup_failure_kills_uncertain_sandbox(fake_e2b_sdk, monkeypatch):
    original = _FakeE2bSandbox.list.__func__
    calls = 0

    def flaky_list(cls, *, query, limit, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("lookup failed after creation")
        return original(cls, query=query, limit=limit, **kwargs)

    monkeypatch.setattr(_FakeE2bSandbox, "list", classmethod(flaky_list))
    provider = E2bEnvironment(sdk_loader=lambda: fake_e2b_sdk)
    with pytest.raises(RuntimeError, match="lookup failed after creation"):
        provider.provision("e2b-uncertain-create", EnvironmentSpec(image="petrus-agent-template"))
    assert len(_FakeE2bSandbox.entries) == 1
    assert next(iter(_FakeE2bSandbox.entries.values())).state == "killed"


def test_e2b_vm_transport_failure_is_not_mislabeled_as_command_failure(tmp_path, fake_e2b_sdk):
    provider = E2bEnvironment(sdk_loader=lambda: fake_e2b_sdk)
    lease = provider.provision("e2b-transport-failure", EnvironmentSpec(image="petrus-agent-template"))
    try:
        attachment = provider.attach(lease, workspace_archive(tmp_path), "digest")
        with pytest.raises(RuntimeError, match="transport failed"):
            provider.execute(attachment, Command(("transport", "failure")))
    finally:
        provider.destroy(lease)


def test_e2b_vm_output_is_bounded(tmp_path, fake_e2b_sdk):
    provider = E2bEnvironment(sdk_loader=lambda: fake_e2b_sdk)
    lease = provider.provision("e2b-output-bound", EnvironmentSpec(image="petrus-agent-template"))
    try:
        attachment = provider.attach(lease, workspace_archive(tmp_path), "digest")
        result = provider.execute(attachment, Command(("large", "output"), output_limit=10))
        assert result.output_truncated
        assert result.stdout == b"x" * 10
        assert result.stderr == b""
    finally:
        provider.destroy(lease)


@pytest.mark.parametrize(("timeout", "field"), [(0.02, "timed_out"), (2, "superseded")])
def test_e2b_vm_command_timeout_and_supersession_kill_remote_command(tmp_path, fake_e2b_sdk, timeout, field):
    provider = E2bEnvironment(sdk_loader=lambda: fake_e2b_sdk)
    lease = provider.provision(f"e2b-{field}", EnvironmentSpec(image="petrus-agent-template"))
    attachment = provider.attach(lease, workspace_archive(tmp_path), "digest")
    observations = iter((True, False)) if field == "superseded" else None
    current = None if observations is None else lambda: next(observations, False)
    try:
        result = provider.execute(
            attachment,
            Command(("sleep", "forever"), timeout=timeout, is_current=current),
        )
        assert getattr(result, field)
        assert _FakeE2bSandbox.entries[lease.lease_id].handles[-1].killed.is_set()
    finally:
        provider.destroy(lease)


@pytest.mark.real_provider_acceptance
def test_live_e2b_vm_provider_is_explicitly_opt_in(tmp_path, monkeypatch):
    if os.getenv("PETRUS_RUN_CV10_E2B") != "1":
        pytest.skip("set PETRUS_RUN_CV10_E2B=1 to run live E2B lifecycle acceptance")
    if not os.getenv("E2B_API_KEY"):
        pytest.skip("live E2B lifecycle acceptance requires E2B_API_KEY")
    template = os.getenv("PETRUS_CV10_E2B_TEMPLATE")
    if not template:
        pytest.skip("set PETRUS_CV10_E2B_TEMPLATE to a template with sh and tar")
    source = tmp_path / "source"
    source.mkdir()
    (source / "probe.txt").write_text("host-to-vm")
    operation_id = f"cv10-live-e2b-{uuid.uuid4().hex[:16]}"
    provider = E2bEnvironment(lease_timeout=900)
    recreated = E2bEnvironment(lease_timeout=900)
    lease = provider.provision(
        operation_id,
        EnvironmentSpec(image=template, required_capabilities=frozenset({"vm", "explicit-environment"})),
    )
    try:
        attachment = provider.attach(lease, workspace_archive(source), "live-input")
        assert recreated.lookup(operation_id) == lease
        assert recreated.provision(operation_id, EnvironmentSpec(image=template)) == lease
        monkeypatch.setenv("GITHUB_TOKEN", "must-remain-on-host")
        result = recreated.execute(
            attachment,
            Command(
                (
                    "/bin/sh",
                    "-c",
                    'test "$(cat probe.txt)" = host-to-vm && printf vm-to-host > result.txt && '
                    'printf \'%s|%s\' "$ALLOWED" "${GITHUB_TOKEN-unset}"',
                ),
                environment={"ALLOWED": "yes"},
                timeout=30,
            ),
        )
        assert result.returncode == 0 and result.stdout == b"yes|unset"
        restored = tmp_path / "restored"
        extract_workspace_archive(recreated.export(attachment), restored)
        assert (restored / "probe.txt").read_text() == "host-to-vm"
        assert (restored / "result.txt").read_text() == "vm-to-host"
        assert recreated.reconcile(operation_id).classification is ReconcileClass.UNCERTAIN
        timed_out = recreated.execute(attachment, Command(("/bin/sh", "-c", "sleep 30"), timeout=0.5))
        assert timed_out.timed_out and not timed_out.superseded
        observations = iter((True, False))
        superseded = recreated.execute(
            attachment,
            Command(
                ("/bin/sh", "-c", "sleep 30"),
                timeout=30,
                is_current=lambda: next(observations, False),
            ),
        )
        assert superseded.superseded and not superseded.timed_out
    finally:
        try:
            cleanup = recreated.destroy(lease)
        finally:
            absent = provider.destroy(lease)
    assert cleanup.disposition is CleanupDisposition.CLEAN and cleanup.identity == lease.identity
    assert absent.disposition is CleanupDisposition.NOT_CREATED and absent.verified
    assert recreated.lookup(operation_id) is None
    assert recreated.reconcile(operation_id).classification is ReconcileClass.RETRYABLE
