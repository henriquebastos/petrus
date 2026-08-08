"""Private Gondolin sidecar-backed execution provider."""

from __future__ import annotations

import base64
import fcntl
import hashlib
import importlib.resources
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .artifacts import MAX_ARCHIVE_BYTES, extract_workspace_archive, workspace_archive
from .model import (
    CleanupDisposition,
    CleanupResult,
    Command,
    CommandResult,
    EnvironmentCapability,
    EnvironmentLease,
    EnvironmentSpec,
    ExecutionAttachment,
    ExecutionProvenance,
    LeaseState,
    ReconcileClass,
    ReconcileResult,
    PrivateFile,
    PrivateFileCleanupResult,
    PrivateFileRef,
    MAX_PRIVATE_FILE_BYTES,
)
from .providers import _checked_guest_cwd

_VERSION = "0.12.0"
_MAX_FRAME = 8 * 1024 * 1024
_CAPABILITIES = frozenset(
    {
        EnvironmentCapability.EXPLICIT_ENVIRONMENT.value,
        EnvironmentCapability.MICROVM.value,
        EnvironmentCapability.PRIVATE_FILE_TRANSFER.value,
        EnvironmentCapability.RECREATABLE_LOOKUP.value,
        EnvironmentCapability.TERRITORY_CANCELLATION.value,
        EnvironmentCapability.VM.value,
        EnvironmentCapability.WORKSPACE.value,
    }
)


def _operation(value: str) -> str:
    if (
        not value
        or len(value) > 128
        or any(
            character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-" for character in value
        )
    ):
        raise ValueError("operation id must be a safe non-empty provider label")
    return value


def _fingerprint(spec: EnvironmentSpec) -> str:
    material = json.dumps({"image": spec.image}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(material.encode()).hexdigest()


def _ps_identity(pid: int) -> dict[str, str]:
    result = subprocess.run(
        ("ps", "-o", "lstart=", "-o", "command=", "-p", str(pid)), capture_output=True, text=True, check=False
    )
    if result.returncode != 0 or not result.stdout.strip():
        return {"state": "missing"}
    line = result.stdout.strip()
    return {"state": "present", "marker": line[:24].strip(), "command": line[24:].strip()}


def _identity(pid: int) -> dict[str, str]:
    if not os.path.isdir("/proc"):
        try:
            return _ps_identity(pid)
        except OSError:
            return {"state": "uninspectable"}
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().split()
        boot_id = ""
        try:
            boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        except OSError:
            pass
        command = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace").strip()
        return {"state": "present", "marker": f"{boot_id}:{fields[21]}", "command": command}
    except FileNotFoundError:
        return {"state": "missing"}
    except OSError, IndexError:
        try:
            return _ps_identity(pid)
        except OSError:
            return {"state": "uninspectable"}


def _group_members(pgid: int) -> list[dict[str, str | int]]:
    result = subprocess.run(("ps", "-axo", "pid=,pgid=,command="), capture_output=True, text=True, check=True)
    members = []
    for line in result.stdout.splitlines():
        fields = line.strip().split(maxsplit=2)
        if len(fields) >= 2 and fields[0].isdigit() and fields[1].isdigit() and int(fields[1]) == pgid:
            members.append({"pid": int(fields[0]), "command": fields[2] if len(fields) == 3 else ""})
    return members


def _group_identities(record: dict) -> dict[str, str]:
    identities: dict[str, str] = {}
    for member in _group_members(record["pgid"]):
        pid = int(member["pid"])
        identity = _identity(pid)
        if identity.get("state") == "missing":
            continue
        marker = identity.get("marker")
        if identity.get("state") != "present" or not marker:
            raise RuntimeError("Gondolin process group identity could not be recorded")
        identities[str(pid)] = marker
    if identities.get(str(record["pid"])) != record["start_identity"].get("marker"):
        raise RuntimeError("Gondolin sidecar identity changed during startup")
    return identities


def _safe_chmod(path: Path, mode: int) -> None:
    try:
        path.chmod(mode)
    except NotImplementedError, OSError:
        if os.name == "posix":
            raise


class GondolinEnvironment:
    """Private, durable adapter owning one authenticated sidecar per lease."""

    provider = "gondolin"
    capabilities = _CAPABILITIES

    def __init__(
        self,
        state_root: Path,
        *,
        sdk_module: str,
        node: str = "node",
        lease_ttl: float = 900,
        startup_timeout: float = 120,
        sidecar: Path | None = None,
    ) -> None:
        if lease_ttl <= 0:
            raise ValueError("Gondolin lease TTL must be positive")
        if startup_timeout <= 0:
            raise ValueError("Gondolin startup timeout must be positive")
        if not sdk_module:
            raise ValueError("Gondolin requires an explicit SDK module URL or path")
        self.root = state_root
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        _safe_chmod(self.root, 0o700)
        self.sdk_module, self.node, self.ttl, self.startup_timeout = sdk_module, node, lease_ttl, startup_timeout
        self.sidecar = sidecar or Path(str(importlib.resources.files(__package__).joinpath("gondolin_sidecar.mjs")))

    def _directory(self, operation_id: str) -> Path:
        return self.root / hashlib.sha256(operation_id.encode()).hexdigest()[:24]

    @contextmanager
    def _locked(self, operation_id: str):
        directory = self._directory(operation_id)
        fd = None
        while fd is None:
            directory.mkdir(mode=0o700, exist_ok=True)
            candidate = os.open(directory / "lock", os.O_CREAT | os.O_RDWR, 0o600)
            fcntl.flock(candidate, fcntl.LOCK_EX)
            try:
                held, current = os.fstat(candidate), os.stat(directory / "lock")
                if (held.st_dev, held.st_ino) == (current.st_dev, current.st_ino):
                    fd = candidate
                    continue
            except FileNotFoundError:
                pass
            except BaseException:
                os.close(candidate)
                raise
            os.close(candidate)
        try:
            yield directory
        finally:
            assert fd is not None
            os.close(fd)

    @staticmethod
    def _read(directory: Path) -> dict | None:
        try:
            return json.loads((directory / "registry.json").read_text())
        except FileNotFoundError:
            return None

    @staticmethod
    def _write(directory: Path, record: dict) -> None:
        temporary = directory / f"registry.{uuid.uuid4().hex}.tmp"
        descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(descriptor, "w") as stream:
                stream.write(json.dumps(record, sort_keys=True))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, directory / "registry.json")
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _remove_runtime(record: dict) -> None:
        runtime = Path(record["runtime"])
        try:
            metadata = runtime.lstat()
        except FileNotFoundError:
            return
        if (
            runtime.parent != Path("/tmp")
            or not runtime.name.startswith("petrus-g-")
            or runtime.is_symlink()
            or not runtime.is_dir()
            or metadata.st_uid != os.getuid()
        ):
            raise RuntimeError("Gondolin runtime custody is uncertain; registry retained")
        shutil.rmtree(runtime)

    @staticmethod
    def _request(record: dict, request: dict, *, timeout: float = 2) -> dict:
        request = {**request, "lease_id": record["lease_id"], "boot_token": record["boot_token"]}
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(timeout)
            client.connect(record["socket"])
            client.sendall(json.dumps(request, separators=(",", ":")).encode() + b"\n")
            received = bytearray()
            while b"\n" not in received:
                chunk = client.recv(min(65536, _MAX_FRAME + 1 - len(received)))
                if not chunk:
                    raise ConnectionError("Gondolin sidecar closed without a response")
                received.extend(chunk)
                if len(received) > _MAX_FRAME:
                    raise RuntimeError("Gondolin sidecar response is too large")
            response = json.loads(received.split(b"\n", 1)[0])
        if not response.get("ok"):
            raise RuntimeError(response.get("error", "Gondolin sidecar request failed"))
        return response

    def _handshake(self, record: dict) -> dict:
        response = self._request(record, {"action": "handshake"})
        if (
            response.get("version") != _VERSION
            or response.get("lease_id") != record["lease_id"]
            or response.get("closing")
        ):
            raise RuntimeError("Gondolin sidecar identity or SDK version mismatch")
        return response

    def _lease(self, record: dict, state: LeaseState = LeaseState.READY) -> EnvironmentLease:
        capabilities = self.capabilities
        if not record.get("private_file_transfer"):
            capabilities = capabilities - {EnvironmentCapability.PRIVATE_FILE_TRANSFER.value}
        return EnvironmentLease(record["operation_id"], "gondolin", record["lease_id"], capabilities, state)

    def _rollback_locked(self, directory: Path, record: dict) -> bool:
        """Remove a newly registered territory without reacquiring its operation lock."""
        try:
            try:
                self._request(record, {"action": "close"})
            except OSError, TimeoutError, RuntimeError, ConnectionError:
                pass
            deadline = time.monotonic() + 5
            while _group_members(record["pgid"]) and time.monotonic() < deadline:
                try:
                    os.waitpid(record["pid"], os.WNOHANG)
                except ChildProcessError:
                    pass
                time.sleep(0.03)
            if _group_members(record["pgid"]):
                self._cleanup_group(record)
            if _group_members(record["pgid"]):
                return False
            self._remove_runtime(record)
            shutil.rmtree(directory)
            return (
                not Path(record["runtime"]).exists() and not directory.exists() and not _group_members(record["pgid"])
            )
        except KeyError, OSError, RuntimeError, TypeError, ValueError, subprocess.SubprocessError:
            return False

    def _await_start(self, directory: Path, record: dict, process: subprocess.Popen[bytes], stderr_path: Path) -> None:
        deadline = time.monotonic() + self.startup_timeout
        try:
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    detail = stderr_path.read_bytes()[-1000:].decode(errors="replace")
                    raise RuntimeError(f"Gondolin sidecar failed to start: {detail}")
                try:
                    self._handshake(record)
                    return
                except OSError, TimeoutError, ConnectionError:
                    time.sleep(0.03)
            raise RuntimeError("Gondolin sidecar readiness timed out")
        except BaseException:
            self._cleanup_group(record)
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
            if _group_members(record["pgid"]):
                raise RuntimeError("Gondolin startup failed and cleanup is uncertain; registry retained")
            self._remove_runtime(record)
            shutil.rmtree(directory)
            raise

    def lookup(self, operation_id: str) -> EnvironmentLease | None:
        _operation(operation_id)
        record = self._read(self._directory(operation_id))
        if record is None:
            return None
        try:
            self._handshake(record)
        except OSError, TimeoutError, RuntimeError:
            return self._lease(record, LeaseState.UNCERTAIN)
        return self._lease(record)

    def create(  # noqa: C901 - exclusive lookup, spawn, registration, and rollback are one custody transition
        self, operation_id: str, spec: EnvironmentSpec
    ) -> EnvironmentLease:
        _operation(operation_id)
        missing = spec.required_capabilities - self.capabilities
        if missing:
            raise ValueError(f"unsupported capabilities: {sorted(missing)}")
        if spec.image is None:
            raise ValueError("Gondolin requires an image")
        with self._locked(operation_id) as directory:
            record = self._read(directory)
            if record is not None:
                if record["spec_fingerprint"] != _fingerprint(spec):
                    raise ValueError("operation id collides with a materially different environment spec")
                try:
                    self._handshake(record)
                except Exception as error:
                    raise RuntimeError("registered Gondolin lease is uncertain; destroy it before retrying") from error
                lease = self._lease(record)
                if not spec.required_capabilities <= lease.capabilities:
                    raise RuntimeError(
                        "registered Gondolin lease lacks required capabilities; destroy it before retrying"
                    )
                return lease
            workspace = directory / "workspace"
            if workspace.exists():
                raise RuntimeError("unregistered Gondolin workspace has uncertain custody")
            workspace.mkdir(mode=0o700)
            try:
                runtime = Path(tempfile.mkdtemp(prefix="petrus-g-", dir="/tmp"))
                _safe_chmod(runtime, 0o700)
            except BaseException:
                shutil.rmtree(workspace)
                raise
            token = secrets.token_urlsafe(32)
            socket_path = runtime / "s"
            lease_id = str(uuid.uuid4())
            env = {
                key: os.environ[key]
                for key in ("GONDOLIN_IMAGE_STORE", "HOME", "PATH", "XDG_CACHE_HOME")
                if key in os.environ
            }
            env.update(
                TMPDIR=str(runtime),
                GONDOLIN_SESSIONS_DIR=str(runtime / "sessions"),
                PETRUS_GONDOLIN_BOOT_TOKEN=token,
                PETRUS_GONDOLIN_SDK=self.sdk_module,
            )
            stderr_path = runtime / "stderr"
            try:
                with stderr_path.open("wb") as stderr_stream:
                    _safe_chmod(stderr_path, 0o600)
                    process = subprocess.Popen(
                        (
                            self.node,
                            str(self.sidecar),
                            str(socket_path),
                            lease_id,
                            str(workspace),
                            spec.image,
                            str(self.ttl),
                            (
                                "private"
                                if EnvironmentCapability.PRIVATE_FILE_TRANSFER.value in spec.required_capabilities
                                else "standard"
                            ),
                        ),
                        env=env,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=stderr_stream,
                        start_new_session=True,
                    )
            except BaseException:
                shutil.rmtree(runtime)
                shutil.rmtree(workspace)
                (directory / "lock").unlink()
                directory.rmdir()
                raise
            record = {
                "operation_id": operation_id,
                "lease_id": lease_id,
                "spec_fingerprint": _fingerprint(spec),
                "boot_token": token,
                "pid": process.pid,
                "pgid": process.pid,
                "start_identity": _identity(process.pid),
                "socket": str(socket_path),
                "runtime": str(runtime),
                "workspace": str(workspace),
                "sdk_module": self.sdk_module,
                "sdk_version": _VERSION,
                "image": spec.image,
            }
            try:
                self._write(directory, record)
            except BaseException:
                try:
                    process.terminate()
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    self._cleanup_group(record)
                    try:
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        pass
                if _group_members(record["pgid"]):
                    raise RuntimeError("Gondolin registry write failed and process cleanup is uncertain")
                self._remove_runtime(record)
                shutil.rmtree(directory)
                raise
            self._await_start(directory, record, process, stderr_path)
            try:
                record["group_identities"] = _group_identities(record)
                self._write(directory, record)
            except BaseException as error:
                if not self._rollback_locked(directory, record):
                    raise RuntimeError(
                        "Gondolin process identity registration failed; rollback is unverified and registry custody is retained"
                    ) from error
                raise RuntimeError("Gondolin process identity registration failed") from error
            if EnvironmentCapability.PRIVATE_FILE_TRANSFER.value in spec.required_capabilities:
                try:
                    self._request(record, {"action": "private_probe"}, timeout=60)
                    record["group_identities"].update(_group_identities(record))
                    record["private_file_transfer"] = True
                    self._write(directory, record)
                except BaseException as error:
                    if not self._rollback_locked(directory, record):
                        raise RuntimeError(
                            "Gondolin private-file probe failed; rollback is unverified and registry custody is retained"
                        ) from error
                    raise RuntimeError("Gondolin private-file security probe failed") from error
            return self._lease(record)

    def provision(self, operation_id: str, spec: EnvironmentSpec) -> EnvironmentLease:
        """Compatibility spelling for private CV10 consumers; use :meth:`create`."""

        return self.create(operation_id, spec)

    def _current(self, lease: EnvironmentLease) -> dict:
        record = self._read(self._directory(lease.operation_id))
        if record is None or lease.provider != "gondolin" or self._lease(record) != lease:
            raise ValueError("lease is not a current Gondolin territory")
        self._handshake(record)
        return record

    def attach(self, lease: EnvironmentLease, workspace_archive_bytes: bytes, input_digest: str) -> ExecutionAttachment:
        record = self._current(lease)
        attachment_id = str(uuid.uuid4())
        transfer = Path(record["workspace"])
        for child in transfer.iterdir():
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
        with tempfile.TemporaryDirectory() as temporary:
            normalized = Path(temporary)
            extract_workspace_archive(workspace_archive_bytes, normalized)
            archive = workspace_archive(normalized)
        input_path = transfer / "input.tar"
        input_path.write_bytes(archive)
        _safe_chmod(input_path, 0o600)
        try:
            self._request(record, {"action": "attach", "attachment_id": attachment_id}, timeout=60)
        finally:
            input_path.unlink(missing_ok=True)
        return ExecutionAttachment(attachment_id, lease, input_digest, Path("/workspace"))

    @staticmethod
    def _provenance(attachment: ExecutionAttachment) -> ExecutionProvenance:
        lease = attachment.lease
        return ExecutionProvenance(lease.operation_id, lease.provider, lease.lease_id)

    def _private_record(self, attachment: ExecutionAttachment) -> dict:
        record = self._current(attachment.lease)
        if EnvironmentCapability.PRIVATE_FILE_TRANSFER.value not in attachment.lease.capabilities:
            raise ValueError("lease does not grant private-file transfer")
        return record

    def _private_reference(self, attachment: ExecutionAttachment, reference: PrivateFileRef) -> None:
        if reference.attachment_id != attachment.attachment_id or reference.provenance != self._provenance(attachment):
            raise ValueError("private file reference is not from this attachment")

    def _unverified_private_cleanup(self, attachment: ExecutionAttachment) -> PrivateFileCleanupResult:
        return PrivateFileCleanupResult(
            attachment.attachment_id,
            self._provenance(attachment),
            CleanupDisposition.UNVERIFIED,
            detail="private cleanup unavailable",
        )

    def _private_cleanup_response(self, attachment: ExecutionAttachment, response: dict) -> PrivateFileCleanupResult:
        try:
            disposition = CleanupDisposition(response["disposition"])
            removed = response.get("removed", 0)
            detail = response.get("detail", "")
            return PrivateFileCleanupResult(
                attachment.attachment_id,
                self._provenance(attachment),
                disposition,
                removed,
                detail,
            )
        except KeyError, TypeError, ValueError:
            return self._unverified_private_cleanup(attachment)

    def import_private_file(self, attachment: ExecutionAttachment, value: PrivateFile) -> PrivateFileRef:
        if not isinstance(value, PrivateFile):
            raise TypeError("private file import requires PrivateFile")
        record = self._private_record(attachment)
        file_id = uuid.uuid4().hex
        self._request(
            record,
            {
                "action": "private_import",
                "attachment_id": attachment.attachment_id,
                "file_id": file_id,
                "name": value.name,
                "content": base64.b64encode(value.content).decode(),
            },
            timeout=60,
        )
        return PrivateFileRef(file_id, value.name, attachment.attachment_id, self._provenance(attachment))

    def export_private_file(self, attachment: ExecutionAttachment, reference: PrivateFileRef) -> PrivateFile:
        self._private_reference(attachment, reference)
        response = self._request(
            self._private_record(attachment),
            {
                "action": "private_export",
                "attachment_id": attachment.attachment_id,
                "file_id": reference.file_id,
                "name": reference.name,
            },
            timeout=60,
        )
        try:
            content = base64.b64decode(response["content"], validate=True)
        except KeyError, TypeError, ValueError:
            raise RuntimeError("Gondolin private export returned invalid content") from None
        if len(content) > MAX_PRIVATE_FILE_BYTES:
            raise RuntimeError("Gondolin private export violated its bound")
        return PrivateFile(reference.name, content)

    def delete_private_file(
        self, attachment: ExecutionAttachment, reference: PrivateFileRef
    ) -> PrivateFileCleanupResult:
        try:
            self._private_reference(attachment, reference)
            response = self._request(
                self._private_record(attachment),
                {
                    "action": "private_delete",
                    "attachment_id": attachment.attachment_id,
                    "file_id": reference.file_id,
                    "name": reference.name,
                },
                timeout=60,
            )
        except OSError, TimeoutError, ConnectionError, RuntimeError, ValueError:
            return self._unverified_private_cleanup(attachment)
        return self._private_cleanup_response(attachment, response)

    def cleanup_private_files(self, attachment: ExecutionAttachment) -> PrivateFileCleanupResult:
        try:
            response = self._request(
                self._private_record(attachment),
                {"action": "private_cleanup", "attachment_id": attachment.attachment_id},
                timeout=60,
            )
            return self._private_cleanup_response(attachment, response)
        except KeyError, TypeError, ValueError, OSError, TimeoutError, ConnectionError, RuntimeError:
            return self._unverified_private_cleanup(attachment)

    def execute(  # noqa: C901 - polling, cancellation precedence, and bounded framing form one protocol fold
        self, attachment: ExecutionAttachment, command: Command
    ) -> CommandResult:
        if (
            command.private_roots
            and EnvironmentCapability.PRIVATE_FILE_TRANSFER.value not in attachment.lease.capabilities
        ):
            raise ValueError("lease does not grant private-file transfer")
        record = self._current(attachment.lease)
        provenance = ExecutionProvenance(attachment.lease.operation_id, "gondolin", attachment.lease.lease_id)
        if command.is_current is not None and not command.is_current():
            self.cancel(attachment.lease, "superseded")
            return CommandResult(-signal.SIGTERM, b"", b"", False, True, False, provenance)
        relative = _checked_guest_cwd(Path("/workspace"), command.cwd)
        request = {
            "action": "execute",
            "argv": command.argv,
            "cwd": relative.as_posix(),
            "environment": dict(command.environment),
            "attachment_id": attachment.attachment_id,
            "private_roots": {
                name: {"file_id": reference.file_id, "name": reference.name}
                for name, reference in command.private_roots.items()
            },
            "timeout": command.timeout,
            "output_limit": command.output_limit,
        }
        for reference in command.private_roots.values():
            self._private_reference(attachment, reference)
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(0.05)
            client.connect(record["socket"])
            client.sendall(
                json.dumps({**request, "lease_id": record["lease_id"], "boot_token": record["boot_token"]}).encode()
                + b"\n"
            )
            received = bytearray()
            while True:
                try:
                    chunk = client.recv(min(65536, _MAX_FRAME + 1 - len(received)))
                    if not chunk:
                        raise ConnectionError("Gondolin sidecar closed without a response")
                    received.extend(chunk)
                    if len(received) > _MAX_FRAME:
                        raise RuntimeError("Gondolin sidecar response is too large")
                    if b"\n" in received:
                        break
                except TimeoutError:
                    if command.is_current is not None:
                        try:
                            current = command.is_current()
                        except BaseException:
                            self.cancel(attachment.lease, "currency check failed")
                            raise
                        if not current:
                            self.cancel(attachment.lease, "superseded")
                            return CommandResult(-signal.SIGTERM, b"", b"", False, True, False, provenance)
        response = json.loads(received.split(b"\n", 1)[0])
        if not response.get("ok"):
            raise RuntimeError(response.get("error", "Gondolin command failed"))
        stdout, stderr = base64.b64decode(response["stdout"]), base64.b64decode(response["stderr"])
        for reference in command.private_roots.values():
            private_root = f"/tmp/.petrus-private/{reference.file_id}".encode()
            stdout = stdout.replace(private_root, b"[private-root]")
            stderr = stderr.replace(private_root, b"[private-root]")
        if len(stdout) + len(stderr) > command.output_limit:
            raise RuntimeError("Gondolin sidecar violated the command output bound")
        return CommandResult(
            response["returncode"],
            stdout,
            stderr,
            response["timed_out"],
            False,
            response["output_truncated"],
            provenance,
        )

    def export(self, attachment: ExecutionAttachment) -> bytes:
        record = self._current(attachment.lease)
        transfer = Path(record["workspace"])
        output_path = transfer / "output.tar"
        output_path.unlink(missing_ok=True)
        try:
            self._request(record, {"action": "export"}, timeout=60)
            if output_path.is_symlink() or not output_path.is_file() or output_path.stat().st_size > MAX_ARCHIVE_BYTES:
                raise RuntimeError("Gondolin returned an invalid workspace archive")
            raw = output_path.read_bytes()
        finally:
            output_path.unlink(missing_ok=True)
        with tempfile.TemporaryDirectory() as temporary:
            normalized = Path(temporary)
            extract_workspace_archive(raw, normalized)
            return workspace_archive(normalized)

    def cancel(self, lease: EnvironmentLease, reason: str) -> None:
        del reason
        record = self._read(self._directory(lease.operation_id))
        if lease.provider == self.provider and record is not None and record["lease_id"] == lease.lease_id:
            self._request(record, {"action": "close"})

    def destroy(  # noqa: C901 - identity gate and fail-closed cleanup stay in one custody transition
        self, lease: EnvironmentLease
    ) -> CleanupResult:
        if lease.provider != self.provider:
            return CleanupResult(
                lease.identity,
                CleanupDisposition.UNVERIFIED,
                "lease belongs to a different provider",
            )
        try:
            with self._locked(lease.operation_id) as directory:
                record = self._read(directory)
                if record is None:
                    try:
                        (directory / "lock").unlink()
                        directory.rmdir()
                    except FileNotFoundError:
                        pass
                    return CleanupResult(
                        lease.identity,
                        CleanupDisposition.NOT_CREATED,
                        "no registered Gondolin territory",
                    )
                if lease.provider != self.provider or record["lease_id"] != lease.lease_id:
                    return CleanupResult(
                        lease.identity,
                        CleanupDisposition.UNVERIFIED,
                        "operation resolves to a different Gondolin lease",
                    )
                try:
                    self._request(record, {"action": "close"})
                except OSError, TimeoutError, RuntimeError:
                    pass
                deadline = time.monotonic() + 5
                while _group_members(record["pgid"]) and time.monotonic() < deadline:
                    try:
                        os.waitpid(record["pid"], os.WNOHANG)
                    except ChildProcessError:
                        pass
                    time.sleep(0.03)
                if _group_members(record["pgid"]):
                    self._cleanup_group(record)
                if _group_members(record["pgid"]):
                    return CleanupResult(
                        lease.identity,
                        CleanupDisposition.UNVERIFIED,
                        "Gondolin process cleanup could not be verified; registry retained",
                    )
                self._remove_runtime(record)
                shutil.rmtree(directory)
        except KeyError, OSError, RuntimeError, TypeError, ValueError, subprocess.SubprocessError:
            return CleanupResult(
                lease.identity,
                CleanupDisposition.UNVERIFIED,
                "Gondolin cleanup could not be independently verified",
            )
        return CleanupResult(lease.identity, CleanupDisposition.CLEAN)

    @staticmethod
    def _cleanup_group(record: dict) -> None:
        members = _group_members(record["pgid"])
        if not members:
            return
        identity = _identity(record["pid"])
        runtime = record["runtime"]
        live_leader_owned = (
            identity.get("state") == "present"
            and record["start_identity"].get("state") == "present"
            and identity.get("marker") == record["start_identity"].get("marker")
        )
        recorded_identities = record.get("group_identities", {})
        for member in members:
            member_identity = _identity(int(member["pid"]))
            recorded_member = (
                isinstance(recorded_identities, dict)
                and member_identity.get("state") == "present"
                and recorded_identities.get(str(member["pid"])) == member_identity.get("marker")
            )
            attributed = runtime in str(member["command"])
            if not (live_leader_owned or recorded_member or attributed):
                raise RuntimeError("Gondolin process group identity is uncertain; registry retained")
        for sig, delay in ((signal.SIGTERM, 0.5), (signal.SIGKILL, 0.2)):
            try:
                os.killpg(record["pgid"], sig)
            except ProcessLookupError:
                return
            deadline = time.monotonic() + delay
            while _group_members(record["pgid"]) and time.monotonic() < deadline:
                time.sleep(0.02)
            if not _group_members(record["pgid"]):
                return

    def reconcile(self, operation_id: str) -> ReconcileResult:
        lease = self.lookup(operation_id)
        if lease is None:
            return ReconcileResult(ReconcileClass.RETRYABLE, detail="no Gondolin lease")
        if lease.state is LeaseState.UNCERTAIN:
            return ReconcileResult(ReconcileClass.UNCERTAIN, lease, "registered sidecar is unreachable")
        return ReconcileResult(ReconcileClass.UNCERTAIN, lease, "VM readiness does not prove operation outcome")
