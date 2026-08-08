from __future__ import annotations

import os
import json
import signal
import socket
import stat
import subprocess
import shutil
import tempfile
import textwrap
import threading
import time
from pathlib import Path

import pytest

from petrus.motus._execution import gondolin
from petrus.motus.execution import (
    CleanupDisposition,
    Command,
    EnvironmentLease,
    EnvironmentSpec,
    LeaseState,
    PrivateFileRef,
    ReconcileClass,
    EnvironmentCapability,
    PrivateFile,
)
from petrus.motus.execution.archive import extract_workspace_archive, workspace_archive
from petrus.motus.execution.gondolin import GondolinEnvironment


@pytest.fixture
def fake_sdk(tmp_path: Path) -> Path:
    module = tmp_path / "fake-gondolin.mjs"
    module.write_text(
        textwrap.dedent(
            """
            import childProcess from "node:child_process";
            import fs from "node:fs";
            import os from "node:os";
            import path from "node:path";
            export const VERSION = "0.12.0";
            export const PETRUS_FAKE = true;
            export class RealFSProvider { constructor(root) { this.root = root; } }
            export function createHttpHooks() { return { httpHooks: { fakeHooks: true }, env: {} }; }
            export function resolveImageSelector(selector) {
              if (!["fake-image", "fake-image-slow-probe", "fake-image-custom-store"].includes(selector)) {
                throw new Error(`unknown local image under ${process.env.GONDOLIN_IMAGE_STORE ?? process.env.XDG_CACHE_HOME}`);
              }
              if (selector === "fake-image-custom-store") {
                const store = process.env.GONDOLIN_IMAGE_STORE
                  ?? (process.env.XDG_CACHE_HOME ? path.join(process.env.XDG_CACHE_HOME, "gondolin", "images") : undefined);
                if (!store || !path.isAbsolute(store)) throw new Error("missing custom image store");
                return { assetDir: path.join(store, "objects", selector) };
              }
              return { assetDir: selector };
            }
            export function loadGuestAssets(assetDir) {
              return {
                kernelPath: path.join(assetDir, "kernel"),
                initrdPath: path.join(assetDir, "initrd"),
                rootfsPath: path.join(assetDir, "rootfs"),
              };
            }
            export class VM {
              static async create(options) {
                const assets = options.sandbox.imagePath;
                if (!assets || typeof assets !== "object") throw new Error("image was not resolved locally");
                const image = path.basename(path.dirname(assets.rootfsPath));
                if (!["fake-image", "fake-image-slow-probe", "fake-image-custom-store"].includes(image)) throw new Error("wrong VM options");
                const expected = JSON.stringify({ sandbox: { vmm: "qemu", imagePath: assets, netEnabled: true } });
                if (JSON.stringify({ sandbox: options.sandbox }) !== expected) throw new Error("wrong VM options");
                if (!options.httpHooks.fakeHooks || Object.keys(options).sort().join() !== "httpHooks,sandbox,vfs") throw new Error("wrong VM options");
                const vm = new VM(options.vfs.mounts["/petrus-transfer"].root, image);
                const sessions = process.env.GONDOLIN_SESSIONS_DIR;
                if (!sessions || !path.isAbsolute(sessions)) throw new Error("missing isolated session registry");
                fs.mkdirSync(sessions, { recursive: true });
                vm.registration = path.join(sessions, "fake-session.json");
                fs.writeFileSync(vm.registration, "registered");
                await vm.start();
                return vm;
              }
              constructor(root, image) {
                this.root = root; this.child = null; this.started = false;
                this.image = image;
                this.guest = fs.mkdtempSync(path.join(process.env.TMPDIR ?? os.tmpdir(), "fake-guest-"));
              }
              async start() { this.started = true; }
              exec(argv, options) {
                if (!this.started) throw new Error("sandbox is stopped");
                const privateRoot = path.join(this.guest, ".petrus-private");
                const mapped = value => value === "/workspace" || value.startsWith("/workspace/")
                  ? value.replace("/workspace", this.guest)
                  : value === "/tmp/.petrus-private" || value.startsWith("/tmp/.petrus-private/")
                  ? value.replace("/tmp/.petrus-private", privateRoot)
                  : value === "/petrus-transfer" || value.startsWith("/petrus-transfer/")
                  ? value.replace("/petrus-transfer", this.root) : value;
                const cwd = options.cwd ? mapped(options.cwd) : this.root;
                if (options.stdout !== "pipe" || options.stderr !== "pipe" || !Number.isFinite(options.windowBytes)) throw new Error("wrong exec options");
                const translated = argv.map(value => mapped(value).replace?.("R='/tmp/.petrus-private'", `R='${privateRoot}'`) ?? mapped(value));
                if (translated[0] === "/bin/tar" && !fs.existsSync(translated[0])) translated[0] = "/usr/bin/tar";
                const env = Object.fromEntries(Object.entries(options.env ?? {}).map(([key, value]) => [key, mapped(value)]));
                if (this.image === "fake-image-slow-probe" && translated.at(-1) === "probe") {
                  this.child = childProcess.spawn("/bin/sh", ["-c", 'sleep 0.2; exec "$@"', "slow-probe", ...translated], { cwd, env, detached: true });
                } else {
                  this.child = childProcess.spawn(translated[0], translated.slice(1), { cwd, env, detached: true });
                }
                if (Buffer.isBuffer(options.stdin)) this.child.stdin.end(options.stdin); else this.child.stdin.end();
                const child = this.child, queued = [], waiters = [];
                let finished = false;
                const emit = value => { const waiter = waiters.shift(); waiter ? waiter(value) : queued.push(value); };
                child.stdout.on("data", data => emit({ value: { stream: "stdout", data }, done: false }));
                child.stderr.on("data", data => emit({ value: { stream: "stderr", data }, done: false }));
                child.on("close", () => { finished = true; emit({ done: true }); });
                const result = new Promise((resolve, reject) => {
                  child.on("error", reject);
                  child.on("close", code => code === null ? reject(new Error("VM closed")) : resolve({ exitCode: code }));
                });
                return { result, output() { return { [Symbol.asyncIterator]() { return this; }, next() {
                  if (queued.length) return Promise.resolve(queued.shift());
                  if (finished) return Promise.resolve({ done: true });
                  return new Promise(resolve => waiters.push(resolve));
                } }; } };
              }
              async close() {
                if (this.child && this.child.exitCode === null) {
                  const child = this.child;
                  const closed = new Promise(resolve => child.once("close", resolve));
                  const rows = childProcess.execFileSync("/bin/ps", ["-axo", "pid=,ppid="], { encoding: "utf8" });
                  const children = new Map();
                  for (const line of rows.split("\\n")) {
                    const [pid, ppid] = line.trim().split(/\\s+/).map(Number);
                    if (Number.isInteger(pid) && Number.isInteger(ppid)) children.set(pid, ppid);
                  }
                  const descendants = [], pending = [child.pid];
                  while (pending.length) {
                    const parent = pending.pop();
                    for (const [pid, ppid] of children) if (ppid === parent) { descendants.push(pid); pending.push(pid); }
                  }
                  for (const pid of descendants.reverse()) try { process.kill(pid, "SIGKILL"); } catch {}
                  try { child.kill("SIGKILL"); } catch {}
                  await closed;
                }
                fs.rmSync(this.registration, { force: true });
                fs.rmSync(this.guest, { recursive: true, force: true });
              }
            }
            """
        )
    )
    return module


def test_sidecar_has_valid_node_syntax() -> None:
    sidecar = Path(__file__).parents[3] / "src/petrus/motus/_execution/gondolin_sidecar.mjs"
    subprocess.run(("node", "--check", sidecar), check=True, capture_output=True)


def test_gondolin_sidecar_lifecycle_recreation_vfs_and_bounds(tmp_path: Path, fake_sdk: Path, monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "host-secret")
    root = tmp_path / "short"
    provider = GondolinEnvironment(root, sdk_module=str(fake_sdk), lease_ttl=30)
    spec = EnvironmentSpec(image="fake-image", required_capabilities=frozenset({"vm", "microvm"}))
    lease = provider.provision("operation", spec)
    try:
        assert lease.state is LeaseState.READY
        record = provider._read(provider._directory("operation"))
        assert record is not None
        assert record["boot_token"] not in gondolin._identity(record["pid"]).get("command", "")
        assert stat.S_IMODE((provider._directory("operation") / "registry.json").stat().st_mode) == 0o600
        assert stat.S_IMODE(Path(record["socket"]).stat().st_mode) == 0o600
        assert Path(record["runtime"], "sessions", "fake-session.json").is_file()
        assert len(os.fsencode(record["socket"])) < 100
        with socket.socket(socket.AF_UNIX) as client:
            client.connect(record["socket"])
            client.sendall(b'{"action":"handshake","lease_id":"wrong","boot_token":"wrong"}\n')
            assert b'"authentication failed"' in client.recv(1024)
        assert GondolinEnvironment(root, sdk_module=str(fake_sdk)).lookup("operation") == lease
        with pytest.raises(ValueError, match="collides"):
            provider.provision("operation", EnvironmentSpec(image="other"))
        source = tmp_path / "source"
        source.mkdir()
        (source / "input").write_text("host")
        attachment = provider.attach(lease, workspace_archive(source), "digest")
        assert attachment.workspace == Path("/workspace")
        result = provider.execute(
            attachment,
            Command(
                (
                    "/bin/sh",
                    "-c",
                    'cat input; printf %s "${GITHUB_TOKEN-unset}" > output; printf "#!/bin/sh\\n" > mode.sh; chmod 755 mode.sh',
                ),
                environment={"ALLOWED": "yes"},
            ),
        )
        assert result.returncode == 0 and result.stdout == b"host"
        restored = tmp_path / "restored"
        extract_workspace_archive(provider.export(attachment), restored)
        assert (restored / "output").read_text() == "unset"
        assert stat.S_IMODE((restored / "mode.sh").stat().st_mode) == 0o755
        stale = EnvironmentLease("operation", "different-provider", lease.lease_id, lease.capabilities, lease.state)
        assert provider.destroy(stale).disposition is CleanupDisposition.UNVERIFIED
        assert provider.lookup("operation") == lease
    finally:
        cleanup = provider.destroy(lease)
    assert cleanup.disposition is CleanupDisposition.CLEAN and cleanup.identity == lease.identity
    assert provider.lookup("operation") is None
    assert provider.reconcile("operation").classification is ReconcileClass.RETRYABLE
    assert not any(root.iterdir())


@pytest.mark.parametrize("variable", ("GONDOLIN_IMAGE_STORE", "XDG_CACHE_HOME"))
def test_sidecar_resolves_a_custom_image_store_locally_before_vm_creation(
    tmp_path: Path,
    fake_sdk: Path,
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
) -> None:
    image_store = tmp_path / "image-store"
    image_store.mkdir()
    monkeypatch.setenv(variable, str(image_store))
    root = tmp_path / "g"
    provider = GondolinEnvironment(root, sdk_module=str(fake_sdk), lease_ttl=30)

    lease = provider.create("custom-store", EnvironmentSpec(image="fake-image-custom-store"))

    assert lease.state is LeaseState.READY
    assert provider.destroy(lease).verified
    assert not any(root.iterdir())


def test_sidecar_sanitizes_a_missing_local_image_store_path(
    tmp_path: Path,
    fake_sdk: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_store = tmp_path / "private-image-store"
    monkeypatch.setenv("GONDOLIN_IMAGE_STORE", str(image_store))
    root = tmp_path / "g"
    provider = GondolinEnvironment(root, sdk_module=str(fake_sdk), lease_ttl=30)

    with pytest.raises(RuntimeError, match="Gondolin local image is unavailable") as captured:
        provider.create("missing-image", EnvironmentSpec(image="missing-image"))

    assert str(image_store) not in str(captured.value)
    assert not any(root.iterdir())


def test_gondolin_private_file_route_and_persisted_grant(tmp_path: Path, fake_sdk: Path) -> None:
    root = tmp_path / "g"
    provider = GondolinEnvironment(root, sdk_module=str(fake_sdk), lease_ttl=30)
    required = frozenset({EnvironmentCapability.PRIVATE_FILE_TRANSFER.value})
    lease = provider.create("private", EnvironmentSpec(image="fake-image", required_capabilities=required))
    empty = tmp_path / "empty"
    empty.mkdir()
    try:
        assert required <= lease.capabilities
        assert GondolinEnvironment(root, sdk_module=str(fake_sdk)).lookup("private") == lease
        attachment = provider.attach(lease, workspace_archive(empty), "digest")
        canary = b"private-canary-never-promoted"
        reference = provider.import_private_file(attachment, PrivateFile("secret", canary))
        forged = PrivateFileRef(reference.file_id, "other", reference.attachment_id, reference.provenance)
        with pytest.raises(RuntimeError, match="private operation failed"):
            provider.export_private_file(attachment, forged)
        assert provider.delete_private_file(attachment, forged).disposition is CleanupDisposition.UNVERIFIED
        with pytest.raises(RuntimeError, match="private reference unavailable"):
            provider.execute(
                attachment,
                Command(("true",), private_roots={"PRIVATE": forged}),
            )
        result = provider.execute(
            attachment,
            Command(("/bin/sh", "-c", 'printf after > "$PRIVATE/secret"'), private_roots={"PRIVATE": reference}),
        )
        assert result.returncode == 0
        assert provider.export_private_file(attachment, reference) == PrivateFile("secret", b"after")
        assert canary not in result.stdout + result.stderr + provider.export(attachment)
        assert provider.delete_private_file(attachment, reference).removed == 1
        assert provider.delete_private_file(attachment, reference).disposition is CleanupDisposition.NOT_CREATED
        assert provider.cleanup_private_files(attachment).verified
        record = provider._read(provider._directory("private"))
        assert record is not None
        assert canary not in json.dumps(record).encode()
        assert canary not in Path(record["runtime"], "stderr").read_bytes()
        assert all(canary not in path.read_bytes() for path in Path(record["workspace"]).glob("*") if path.is_file())
        assert canary not in repr(reference).encode() + repr(result).encode()
    finally:
        assert provider.destroy(lease).verified


def test_gondolin_lease_without_requirement_does_not_gain_private_transfer(tmp_path: Path, fake_sdk: Path) -> None:
    provider = GondolinEnvironment(tmp_path / "g", sdk_module=str(fake_sdk), lease_ttl=30)
    lease = provider.create("ordinary", EnvironmentSpec(image="fake-image"))
    source = tmp_path / "source-ordinary"
    source.mkdir()
    try:
        assert EnvironmentCapability.PRIVATE_FILE_TRANSFER.value not in lease.capabilities
        first = provider.attach(lease, workspace_archive(source), "first")
        provider.attach(lease, workspace_archive(source), "second")
        assert provider.execute(first, Command(("true",))).returncode == 0
    finally:
        provider.destroy(lease)


def test_existing_noncapable_lease_cannot_satisfy_later_private_requirement(tmp_path: Path, fake_sdk: Path) -> None:
    provider = GondolinEnvironment(tmp_path / "g", sdk_module=str(fake_sdk), lease_ttl=30)
    lease = provider.create("fixed-grant", EnvironmentSpec(image="fake-image"))
    try:
        with pytest.raises(RuntimeError, match="lacks required capabilities"):
            provider.create(
                "fixed-grant",
                EnvironmentSpec(
                    image="fake-image",
                    required_capabilities=frozenset({EnvironmentCapability.PRIVATE_FILE_TRANSFER.value}),
                ),
            )
    finally:
        assert provider.destroy(lease).verified


def test_private_probe_failure_rolls_back_without_relocking_or_residue(
    tmp_path: Path, fake_sdk: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "g"
    provider = GondolinEnvironment(root, sdk_module=str(fake_sdk), lease_ttl=30)
    original = provider._request

    def reject_probe(record, request, *, timeout=2):
        if request.get("action") == "private_probe":
            raise RuntimeError("probe detail must not escape")
        return original(record, request, timeout=timeout)

    monkeypatch.setattr(provider, "_request", reject_probe)
    created: list[Path] = []
    original_mkdtemp = tempfile.mkdtemp

    def record_runtime(*args, **kwargs):
        runtime = Path(original_mkdtemp(*args, **kwargs))
        created.append(runtime)
        return str(runtime)

    monkeypatch.setattr(gondolin.tempfile, "mkdtemp", record_runtime)
    with pytest.raises(RuntimeError, match="security probe failed"):
        provider.create(
            "probe-failure",
            EnvironmentSpec(
                image="fake-image",
                required_capabilities=frozenset({EnvironmentCapability.PRIVATE_FILE_TRANSFER.value}),
            ),
        )
    assert provider.lookup("probe-failure") is None
    assert not any(root.iterdir())
    assert created and all(not runtime.exists() for runtime in created)


def test_private_symlink_replacement_is_unverified_and_never_touches_target(tmp_path: Path, fake_sdk: Path) -> None:
    provider = GondolinEnvironment(tmp_path / "g", sdk_module=str(fake_sdk), lease_ttl=30)
    required = frozenset({EnvironmentCapability.PRIVATE_FILE_TRANSFER.value})
    lease = provider.create("private-symlink", EnvironmentSpec(image="fake-image", required_capabilities=required))
    source = tmp_path / "source-symlink"
    source.mkdir()
    (source / "victim").write_bytes(b"victim")
    try:
        attachment = provider.attach(lease, workspace_archive(source), "digest")
        reference = provider.import_private_file(attachment, PrivateFile("secret", b"private"))
        result = provider.execute(
            attachment,
            Command(
                ("/bin/sh", "-c", 'rm "$PRIVATE/secret"; ln -s /workspace/victim "$PRIVATE/secret"'),
                private_roots={"PRIVATE": reference},
            ),
        )
        assert result.returncode == 0
        with pytest.raises(RuntimeError, match="private operation failed"):
            provider.export_private_file(attachment, reference)
        assert provider.delete_private_file(attachment, reference).disposition is CleanupDisposition.UNVERIFIED
        replacement = tmp_path / "replacement-symlink"
        replacement.mkdir()
        with pytest.raises(RuntimeError, match="private attachment cleanup failed"):
            provider.attach(lease, workspace_archive(replacement), "replacement")
        restored = tmp_path / "restored-symlink"
        extract_workspace_archive(provider.export(attachment), restored)
        assert (restored / "victim").read_bytes() == b"victim"
    finally:
        assert provider.destroy(lease).verified


def test_private_cleanup_is_unverified_while_command_is_active(tmp_path: Path, fake_sdk: Path) -> None:
    provider = GondolinEnvironment(tmp_path / "g", sdk_module=str(fake_sdk), lease_ttl=30)
    required = frozenset({EnvironmentCapability.PRIVATE_FILE_TRANSFER.value})
    lease = provider.create("private-active", EnvironmentSpec(image="fake-image", required_capabilities=required))
    source = tmp_path / "source-active"
    source.mkdir()
    attachment = provider.attach(lease, workspace_archive(source), "digest")
    reference = provider.import_private_file(attachment, PrivateFile("secret", b"private"))
    results = []

    thread = threading.Thread(
        target=lambda: results.append(
            provider.execute(
                attachment,
                Command(("/bin/sh", "-c", "sleep 0.4"), private_roots={"PRIVATE": reference}),
            )
        )
    )
    thread.start()
    record = provider._read(provider._directory(lease.operation_id))
    assert record is not None
    deadline = time.monotonic() + 1
    while not provider._request(record, {"action": "status"})["active"] and time.monotonic() < deadline:
        time.sleep(0.01)
    assert provider.cleanup_private_files(attachment).disposition is CleanupDisposition.UNVERIFIED
    thread.join(timeout=2)
    assert not thread.is_alive() and results[0].returncode == 0
    assert provider.cleanup_private_files(attachment).verified
    assert provider.destroy(lease).verified


def test_private_sidecar_death_requires_territory_destroy_for_verified_cleanup(tmp_path: Path, fake_sdk: Path) -> None:
    provider = GondolinEnvironment(tmp_path / "g", sdk_module=str(fake_sdk), lease_ttl=30)
    required = frozenset({EnvironmentCapability.PRIVATE_FILE_TRANSFER.value})
    lease = provider.create("private-death", EnvironmentSpec(image="fake-image", required_capabilities=required))
    source = tmp_path / "source-death"
    source.mkdir()
    attachment = provider.attach(lease, workspace_archive(source), "digest")
    provider.import_private_file(attachment, PrivateFile("secret", b"private"))
    record = provider._read(provider._directory(lease.operation_id))
    assert record is not None
    os.kill(record["pid"], signal.SIGKILL)
    os.waitpid(record["pid"], 0)

    cleanup = provider.cleanup_private_files(attachment)
    assert cleanup.disposition is CleanupDisposition.UNVERIFIED and not cleanup.verified
    assert provider.destroy(lease).verified
    assert not Path(record["runtime"]).exists()


def test_gondolin_timeout_destroys_lease(tmp_path: Path, fake_sdk: Path) -> None:
    provider = GondolinEnvironment(tmp_path / "g", sdk_module=str(fake_sdk), lease_ttl=30)
    lease = provider.provision(f"timeout-{os.getpid()}", EnvironmentSpec(image="fake-image"))
    empty = tmp_path / "empty"
    empty.mkdir()
    attachment = provider.attach(lease, workspace_archive(empty), "digest")
    result = provider.execute(attachment, Command(("/bin/sh", "-c", "sleep 10"), timeout=0.05))
    assert result.timed_out
    assert provider.lookup(lease.operation_id).state is LeaseState.UNCERTAIN
    provider.destroy(lease)


def test_gondolin_output_overflow_closes_and_destroy_is_idempotent(tmp_path: Path, fake_sdk: Path) -> None:
    provider = GondolinEnvironment(tmp_path / "g", sdk_module=str(fake_sdk), lease_ttl=30)
    lease = provider.provision("overflow", EnvironmentSpec(image="fake-image"))
    empty = tmp_path / "empty"
    empty.mkdir()
    result = provider.execute(
        provider.attach(lease, workspace_archive(empty), "digest"),
        Command(("/bin/sh", "-c", "printf 12345"), output_limit=3),
    )
    assert result.output_truncated and result.stdout == b"123"
    assert provider.destroy(lease).disposition is CleanupDisposition.CLEAN
    assert provider.destroy(lease).disposition is CleanupDisposition.NOT_CREATED
    assert not any(provider.root.iterdir())


def test_command_cwd_is_guest_lexical_and_cannot_escape_workspace(
    tmp_path: Path, fake_sdk: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = GondolinEnvironment(tmp_path / "g", sdk_module=str(fake_sdk), lease_ttl=30)
    lease = provider.provision("cwd", EnvironmentSpec(image="fake-image"))
    empty = tmp_path / "empty"
    empty.mkdir()
    attachment = provider.attach(lease, workspace_archive(empty), "digest")
    original_resolve = Path.resolve

    def remapped_resolve(path: Path, *args, **kwargs) -> Path:
        if path.is_relative_to(Path("/workspace")):
            return Path("/host-specific") / path.relative_to("/")
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", remapped_resolve)
    try:
        assert provider.execute(attachment, Command(("true",))).returncode == 0
        with pytest.raises(ValueError, match="escapes"):
            provider.execute(attachment, Command(("true",), cwd=Path("../escape")))
    finally:
        provider.destroy(lease)


def test_concurrent_provision_creates_one_lease_and_sidecar(tmp_path: Path, fake_sdk: Path) -> None:
    root = tmp_path / "g"
    providers = [GondolinEnvironment(root, sdk_module=str(fake_sdk), lease_ttl=30) for _ in range(2)]
    leases = []

    def provision(provider: GondolinEnvironment) -> None:
        leases.append(provider.provision("concurrent", EnvironmentSpec(image="fake-image")))

    threads = [threading.Thread(target=provision, args=(provider,)) for provider in providers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(leases) == 2 and leases[0] == leases[1]
    records = list(root.glob("*/registry.json"))
    assert len(records) == 1
    providers[0].destroy(leases[0])


def test_spawn_failure_removes_runtime_and_operation_directory(tmp_path: Path, fake_sdk: Path) -> None:
    root = tmp_path / "g"
    before = set(Path("/tmp").glob("petrus-g-*"))
    provider = GondolinEnvironment(root, sdk_module=str(fake_sdk), node="/missing/petrus-node")
    with pytest.raises(FileNotFoundError):
        provider.provision("spawn-failure", EnvironmentSpec(image="fake-image"))
    assert not any(root.iterdir())
    assert set(Path("/tmp").glob("petrus-g-*")) == before


def test_registry_write_failure_stops_unregistered_sidecar(tmp_path: Path, fake_sdk: Path, monkeypatch) -> None:
    root = tmp_path / "g"
    before = set(Path("/tmp").glob("petrus-g-*"))
    provider = GondolinEnvironment(root, sdk_module=str(fake_sdk), lease_ttl=30)
    monkeypatch.setattr(provider, "_write", lambda _directory, _record: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(OSError, match="disk"):
        provider.provision("registry-failure", EnvironmentSpec(image="fake-image"))
    assert not any(root.iterdir())
    assert set(Path("/tmp").glob("petrus-g-*")) == before


def test_unregistered_workspace_fails_closed_before_runtime_creation(tmp_path: Path, fake_sdk: Path) -> None:
    root = tmp_path / "g"
    provider = GondolinEnvironment(root, sdk_module=str(fake_sdk), lease_ttl=30)
    (provider._directory("orphan") / "workspace").mkdir(parents=True)
    before = set(Path("/tmp").glob("petrus-g-*"))
    orphan = EnvironmentLease("orphan", provider.provider, "unregistered", provider.capabilities, LeaseState.UNCERTAIN)
    cleanup = provider.destroy(orphan)
    assert cleanup.disposition is CleanupDisposition.UNVERIFIED and not cleanup.verified
    assert (provider._directory("orphan") / "workspace").is_dir()
    with pytest.raises(RuntimeError, match="uncertain custody"):
        provider.provision("orphan", EnvironmentSpec(image="fake-image"))
    assert set(Path("/tmp").glob("petrus-g-*")) == before


def test_lock_revalidates_after_destroy_unlinks_a_waiters_inode(tmp_path: Path, fake_sdk: Path, monkeypatch) -> None:
    provider = GondolinEnvironment(tmp_path / "g", sdk_module=str(fake_sdk), lease_ttl=30)
    opened = threading.Event()
    original_open = os.open

    def observed_open(path, flags, mode=0o777, *, dir_fd=None):
        descriptor = original_open(path, flags, mode, dir_fd=dir_fd)
        if threading.current_thread().name == "waiting-lock" and not opened.is_set():
            opened.set()
        return descriptor

    monkeypatch.setattr(os, "open", observed_open)
    observed = []

    def wait_for_lock() -> None:
        with provider._locked("race") as directory:
            observed.append(directory.exists() and (directory / "lock").exists())

    with provider._locked("race") as directory:
        thread = threading.Thread(target=wait_for_lock, name="waiting-lock")
        thread.start()
        assert opened.wait(timeout=1)
        shutil.rmtree(directory)
    thread.join(timeout=1)
    assert not thread.is_alive() and observed == [True]


def test_process_identity_uses_ps_when_proc_is_unavailable(monkeypatch) -> None:
    expected = {"state": "present", "marker": "start", "command": "node sidecar"}
    monkeypatch.setattr(os.path, "isdir", lambda path: path != "/proc")
    monkeypatch.setattr(gondolin, "_ps_identity", lambda _pid: expected)
    assert gondolin._identity(41) == expected


def test_group_identity_snapshot_ignores_member_that_exited_after_enumeration(monkeypatch) -> None:
    record = {
        "pid": 41,
        "pgid": 41,
        "start_identity": {"state": "present", "marker": "leader-start"},
    }
    monkeypatch.setattr(
        gondolin,
        "_group_members",
        lambda _pgid: [{"pid": 41, "command": "node sidecar"}, {"pid": 99, "command": "finished-helper"}],
    )
    monkeypatch.setattr(
        gondolin,
        "_identity",
        lambda pid: {"state": "present", "marker": "leader-start"} if pid == 41 else {"state": "missing"},
    )
    assert gondolin._group_identities(record) == {"41": "leader-start"}


def test_sidecar_enforces_single_flight_commands(tmp_path: Path, fake_sdk: Path) -> None:
    provider = GondolinEnvironment(tmp_path / "g", sdk_module=str(fake_sdk), lease_ttl=30)
    lease = provider.provision("single-flight", EnvironmentSpec(image="fake-image"))
    empty = tmp_path / "empty"
    empty.mkdir()
    attachment = provider.attach(lease, workspace_archive(empty), "digest")
    first = []

    def execute_first() -> None:
        first.append(provider.execute(attachment, Command(("/bin/sh", "-c", "sleep 10"), timeout=0.3)))

    thread = threading.Thread(target=execute_first)
    thread.start()
    record = provider._read(provider._directory("single-flight"))
    assert record is not None
    deadline = time.monotonic() + 1
    while not provider._request(record, {"action": "status"})["active"] and time.monotonic() < deadline:
        time.sleep(0.01)
    with pytest.raises(RuntimeError, match="command already active"):
        provider.execute(attachment, Command(("true",)))
    thread.join(timeout=2)
    assert not thread.is_alive() and first[0].timed_out
    provider.destroy(lease)


def test_currency_check_failure_closes_active_lease(tmp_path: Path, fake_sdk: Path) -> None:
    provider = GondolinEnvironment(tmp_path / "g", sdk_module=str(fake_sdk), lease_ttl=30)
    lease = provider.provision("currency-error", EnvironmentSpec(image="fake-image"))
    empty = tmp_path / "empty"
    empty.mkdir()
    checks = iter((True, RuntimeError("currency unavailable")))

    def current() -> bool:
        value = next(checks)
        if isinstance(value, BaseException):
            raise value
        return value

    with pytest.raises(RuntimeError, match="currency unavailable"):
        provider.execute(
            provider.attach(lease, workspace_archive(empty), "digest"),
            Command(("/bin/sh", "-c", "sleep 10"), is_current=current),
        )
    deadline = time.monotonic() + 1
    while provider.lookup(lease.operation_id).state is LeaseState.READY and time.monotonic() < deadline:
        time.sleep(0.01)
    assert provider.lookup(lease.operation_id).state is LeaseState.UNCERTAIN
    provider.destroy(lease)


def test_supersession_closes_fresh_lease(tmp_path: Path, fake_sdk: Path) -> None:
    provider = GondolinEnvironment(tmp_path / "g", sdk_module=str(fake_sdk), lease_ttl=30)
    lease = provider.provision("superseded", EnvironmentSpec(image="fake-image"))
    empty = tmp_path / "empty"
    empty.mkdir()
    checks = iter([True, True, False])
    result = provider.execute(
        provider.attach(lease, workspace_archive(empty), "digest"),
        Command(("/bin/sh", "-c", "sleep 10"), is_current=lambda: next(checks, False)),
    )
    assert result.superseded
    provider.destroy(lease)
    provider.destroy(lease)


def test_ttl_expires_and_can_be_destroyed_without_residue(tmp_path: Path, fake_sdk: Path) -> None:
    root = tmp_path / "g"
    provider = GondolinEnvironment(root, sdk_module=str(fake_sdk), lease_ttl=0.1)
    lease = provider.provision("ttl", EnvironmentSpec(image="fake-image"))
    deadline = time.monotonic() + 3
    while provider.lookup("ttl").state is LeaseState.READY and time.monotonic() < deadline:
        time.sleep(0.03)
    assert provider.lookup("ttl").state is LeaseState.UNCERTAIN
    provider.destroy(lease)
    assert not any(root.iterdir())


def test_private_security_probe_gets_startup_grace_before_short_ttl(tmp_path: Path, fake_sdk: Path) -> None:
    root = tmp_path / "g"
    provider = GondolinEnvironment(root, sdk_module=str(fake_sdk), lease_ttl=0.05)
    lease = provider.create(
        "private-ttl",
        EnvironmentSpec(
            image="fake-image-slow-probe",
            required_capabilities=frozenset({EnvironmentCapability.PRIVATE_FILE_TRANSFER.value}),
        ),
    )
    assert lease.state is LeaseState.READY
    deadline = time.monotonic() + 3
    while provider.lookup(lease.operation_id).state is LeaseState.READY and time.monotonic() < deadline:
        time.sleep(0.01)
    assert provider.lookup(lease.operation_id).state is LeaseState.UNCERTAIN
    assert provider.destroy(lease).verified
    assert not any(root.iterdir())


def test_hard_sidecar_death_has_verified_cleanup(tmp_path: Path, fake_sdk: Path) -> None:
    root = tmp_path / "g"
    provider = GondolinEnvironment(root, sdk_module=str(fake_sdk), lease_ttl=30)
    lease = provider.provision("hard-death", EnvironmentSpec(image="fake-image"))
    record = provider._read(provider._directory("hard-death"))
    assert record is not None
    session_registry = Path(record["runtime"], "sessions")
    assert session_registry.is_dir()
    os.kill(record["pid"], signal.SIGKILL)
    os.waitpid(record["pid"], 0)
    assert provider.destroy(lease).verified
    assert not session_registry.exists() and not Path(record["socket"]).exists() and not any(root.iterdir())


def test_foreign_reused_process_group_fails_closed_without_signal(monkeypatch) -> None:
    record = {"pid": 41, "pgid": 41, "runtime": "/private/token", "start_identity": {"state": "present"}}
    monkeypatch.setattr(gondolin, "_group_members", lambda _pgid: [{"pid": 99, "command": "unrelated"}])
    monkeypatch.setattr(gondolin, "_identity", lambda _pid: {"state": "missing"})
    signalled = []
    monkeypatch.setattr(os, "killpg", lambda pgid, sig: signalled.append((pgid, sig)))
    with pytest.raises(RuntimeError, match="uncertain"):
        GondolinEnvironment._cleanup_group(record)
    assert signalled == []


def test_same_process_marker_allows_zombie_leader_cleanup(monkeypatch) -> None:
    record = {
        "pid": 41,
        "pgid": 41,
        "runtime": "/tmp/petrus-g-token",
        "start_identity": {"state": "present", "marker": "boot:100", "command": "node sidecar"},
    }
    groups = iter(
        ([{"pid": 41, "command": "<defunct>"}], []),
    )
    monkeypatch.setattr(gondolin, "_group_members", lambda _pgid: next(groups, []))
    monkeypatch.setattr(
        gondolin,
        "_identity",
        lambda _pid: {"state": "present", "marker": "boot:100", "command": ""},
    )
    signalled = []
    monkeypatch.setattr(os, "killpg", lambda pgid, sig: signalled.append((pgid, sig)))
    GondolinEnvironment._cleanup_group(record)
    assert signalled == [(41, signal.SIGTERM)]


def test_recorded_member_identity_allows_orphan_process_group_cleanup(monkeypatch) -> None:
    record = {
        "pid": 41,
        "pgid": 41,
        "runtime": "/tmp/petrus-g-token",
        "start_identity": {"state": "present", "marker": "leader-start"},
        "group_identities": {"41": "leader-start", "99": "member-start"},
    }
    groups = iter(([{"pid": 99, "command": "qemu-system-aarch64"}], []))
    monkeypatch.setattr(gondolin, "_group_members", lambda _pgid: next(groups, []))
    monkeypatch.setattr(
        gondolin,
        "_identity",
        lambda pid: {"state": "present", "marker": "member-start"} if pid == 99 else {"state": "missing"},
    )
    signalled = []
    monkeypatch.setattr(os, "killpg", lambda pgid, sig: signalled.append((pgid, sig)))
    GondolinEnvironment._cleanup_group(record)
    assert signalled == [(41, signal.SIGTERM)]


def test_changed_recorded_member_identity_fails_closed_without_signal(monkeypatch) -> None:
    record = {
        "pid": 41,
        "pgid": 41,
        "runtime": "/tmp/petrus-g-token",
        "start_identity": {"state": "present", "marker": "leader-start"},
        "group_identities": {"41": "leader-start", "99": "original-member"},
    }
    monkeypatch.setattr(
        gondolin,
        "_group_members",
        lambda _pgid: [{"pid": 99, "command": "qemu-system-aarch64"}],
    )
    monkeypatch.setattr(
        gondolin,
        "_identity",
        lambda pid: {"state": "present", "marker": "reused-member"} if pid == 99 else {"state": "missing"},
    )
    signalled = []
    monkeypatch.setattr(os, "killpg", lambda pgid, sig: signalled.append((pgid, sig)))
    with pytest.raises(RuntimeError, match="uncertain"):
        GondolinEnvironment._cleanup_group(record)
    assert signalled == []


@pytest.mark.real_gondolin_acceptance
def test_real_gondolin_lifecycle_is_explicitly_opt_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sdk = os.getenv("PETRUS_REAL_GONDOLIN_SDK_MODULE")
    image = os.getenv("PETRUS_REAL_GONDOLIN_IMAGE")
    if not sdk or not image:
        pytest.skip("set PETRUS_REAL_GONDOLIN_SDK_MODULE and PETRUS_REAL_GONDOLIN_IMAGE")
    monkeypatch.setenv("GITHUB_TOKEN", "must-remain-on-host")
    root = tmp_path / "real"
    spec = EnvironmentSpec(
        image=image,
        required_capabilities=frozenset({"vm", "microvm", EnvironmentCapability.PRIVATE_FILE_TRANSFER.value}),
    )
    source = tmp_path / "source"
    source.mkdir()
    (source / "input.txt").write_text("host input\n")

    provider = GondolinEnvironment(root, sdk_module=sdk, lease_ttl=30)
    lease = provider.provision("real-lifecycle", spec)
    record = provider._read(provider._directory(lease.operation_id))
    assert record is not None
    runtime = Path(record["runtime"])
    transfer = Path(record["workspace"])
    try:
        recreated = GondolinEnvironment(root, sdk_module=sdk, lease_ttl=30)
        assert recreated.lookup(lease.operation_id) == lease
        attachment = recreated.attach(lease, workspace_archive(source), "input-digest")
        result = recreated.execute(
            attachment,
            Command(
                (
                    "/bin/sh",
                    "-c",
                    'cat input.txt; test "${GITHUB_TOKEN-unset}" = unset; printf guest > output.txt; '
                    'printf "#!/bin/sh\\nexit 0\\n" > mode.sh; chmod 755 mode.sh',
                ),
                environment={"PETRUS_ALLOWED": "yes"},
            ),
        )
        assert result.returncode == 0 and result.stdout == b"host input\n"
        restored = tmp_path / "restored"
        extract_workspace_archive(recreated.export(attachment), restored)
        assert (restored / "output.txt").read_text() == "guest"
        assert stat.S_IMODE((restored / "mode.sh").stat().st_mode) == 0o755
        reference = recreated.import_private_file(attachment, PrivateFile("secret", b"before"))
        private_result = recreated.execute(
            attachment,
            Command(("/bin/sh", "-c", 'printf after > "$PRIVATE/secret"'), private_roots={"PRIVATE": reference}),
        )
        assert private_result.returncode == 0
        assert recreated.export_private_file(attachment, reference) == PrivateFile("secret", b"after")
        assert recreated.delete_private_file(attachment, reference).verified
        assert recreated.cleanup_private_files(attachment).verified
        timed_out = recreated.execute(
            attachment,
            Command(("/bin/sh", "-c", "sleep 30; touch /petrus-transfer/should-not-exist"), timeout=0.2),
        )
        assert timed_out.timed_out and not timed_out.superseded
        assert not (transfer / "should-not-exist").exists()
    finally:
        provider.destroy(lease)
    assert not runtime.exists() and not any(root.iterdir())

    superseded_provider = GondolinEnvironment(root, sdk_module=sdk, lease_ttl=30)
    superseded_lease = superseded_provider.provision("real-superseded", spec)
    try:
        checks = iter((True, True, False))
        attachment = superseded_provider.attach(superseded_lease, workspace_archive(source), "input-digest")
        superseded = superseded_provider.execute(
            attachment,
            Command(("/bin/sh", "-c", "sleep 30; touch stale"), is_current=lambda: next(checks, False)),
        )
        assert superseded.superseded and not superseded.timed_out
    finally:
        superseded_provider.destroy(superseded_lease)

    overflow_provider = GondolinEnvironment(root, sdk_module=sdk, lease_ttl=30)
    overflow_lease = overflow_provider.provision("real-overflow", spec)
    try:
        attachment = overflow_provider.attach(overflow_lease, workspace_archive(source), "input-digest")
        overflow = overflow_provider.execute(
            attachment,
            Command(("/bin/sh", "-c", "yes x | head -c 100000"), output_limit=1024),
        )
        assert overflow.output_truncated and len(overflow.stdout) + len(overflow.stderr) == 1024
    finally:
        overflow_provider.destroy(overflow_lease)

    crash_provider = GondolinEnvironment(root, sdk_module=sdk, lease_ttl=30)
    crash_lease = crash_provider.provision("real-crash", spec)
    crash_record = crash_provider._read(crash_provider._directory(crash_lease.operation_id))
    assert crash_record is not None
    os.kill(crash_record["pid"], signal.SIGKILL)
    os.waitpid(crash_record["pid"], 0)
    assert crash_provider.lookup(crash_lease.operation_id).state is LeaseState.UNCERTAIN
    assert crash_provider.reconcile(crash_lease.operation_id).classification is ReconcileClass.UNCERTAIN
    crash_provider.destroy(crash_lease)
    assert not Path(crash_record["runtime"]).exists() and not any(root.iterdir())

    ttl_provider = GondolinEnvironment(root, sdk_module=sdk, lease_ttl=0.2)
    ttl_lease = ttl_provider.provision("real-ttl", spec)
    deadline = time.monotonic() + 5
    while ttl_provider.lookup(ttl_lease.operation_id).state is LeaseState.READY and time.monotonic() < deadline:
        time.sleep(0.05)
    assert ttl_provider.lookup(ttl_lease.operation_id).state is LeaseState.UNCERTAIN
    ttl_provider.destroy(ttl_lease)
    assert not any(root.iterdir())
