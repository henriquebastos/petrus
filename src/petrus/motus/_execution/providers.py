"""Private execution-territory provider implementations."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import queue
import re
import shlex
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import stat
from typing import Any

from .artifacts import extract_workspace_archive, workspace_archive
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
    MAX_PRIVATE_FILE_BYTES,
    MAX_PRIVATE_FILES_PER_ATTACHMENT,
    MAX_PRIVATE_FILE_TOTAL_BYTES,
    PrivateFile,
    PrivateFileCleanupResult,
    PrivateFileRef,
    ReconcileClass,
    ReconcileResult,
)

_LABEL = "run.petrus.operation"
_SPEC_LABEL = "run.petrus.spec"
_OPERATION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_E2B_WORKSPACE = "/home/user/workspace"
_PRIVATE_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


@dataclass
class _LocalPrivateRecord:
    reference: PrivateFileRef
    root: Path
    content_bytes: int
    present: bool = True
    verified_absent: bool = False


def _owned_private_directory(descriptor: int) -> bool:
    metadata = os.fstat(descriptor)
    return stat.S_ISDIR(metadata.st_mode) and stat.S_IMODE(metadata.st_mode) == 0o700 and metadata.st_uid == os.getuid()


def _owned_private_file(metadata: os.stat_result) -> bool:
    return (
        stat.S_ISREG(metadata.st_mode)
        and stat.S_IMODE(metadata.st_mode) == 0o600
        and metadata.st_uid == os.getuid()
        and metadata.st_nlink == 1
    )


def _fingerprint(spec: EnvironmentSpec) -> str:
    material = json.dumps({"image": spec.image}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(material.encode()).hexdigest()


def _operation_id(value: str) -> str:
    if not isinstance(value, str) or not _OPERATION_ID.fullmatch(value):
        raise ValueError("operation id must be a safe non-empty provider label")
    return value


def _checked_host_cwd(workspace: Path, relative: Path) -> Path:
    cwd = (workspace / relative).resolve()
    if not cwd.is_relative_to(workspace.resolve()):
        raise ValueError("command cwd escapes the workspace")
    return cwd


def _checked_guest_cwd(workspace: Path, relative: Path) -> PurePosixPath:
    root = PurePosixPath(workspace.as_posix())
    child = PurePosixPath(relative.as_posix())
    if root.anchor != "/" or ".." in root.parts or child.is_absolute() or "\x00" in str(root) or "\x00" in str(child):
        raise ValueError("command cwd escapes the workspace")
    parts = list(root.parts[1:])
    boundary = len(parts)
    for part in child.parts:
        if part == "..":
            if len(parts) == boundary:
                raise ValueError("command cwd escapes the workspace")
            parts.pop()
        else:
            parts.append(part)
    return PurePosixPath("/", *parts)


def _collect(
    process: subprocess.Popen[bytes], command: Command, terminate, kill
) -> tuple[bytes, bytes, bool, bool, bool]:
    deadline = None if command.timeout is None else time.monotonic() + command.timeout
    timed_out = superseded = output_truncated = False
    while True:
        wait = 0.05 if deadline is None else max(0.001, min(0.05, deadline - time.monotonic()))
        try:
            stdout, stderr = process.communicate(timeout=wait)
            return stdout, stderr, timed_out, superseded, output_truncated
        except subprocess.TimeoutExpired as pending:
            partial_stdout = pending.output or b""
            partial_stderr = pending.stderr or b""
            output_truncated = len(partial_stdout) + len(partial_stderr) > command.output_limit
            try:
                if command.is_current is not None and not command.is_current():
                    superseded = True
            except BaseException:
                kill()
                process.communicate()
                raise
            if deadline is not None and time.monotonic() >= deadline:
                timed_out = True
            if not (superseded or timed_out or output_truncated):
                continue
            terminate()
            try:
                stdout, stderr = process.communicate(timeout=0.5)
            except subprocess.TimeoutExpired:
                kill()
                stdout, stderr = process.communicate()
            return stdout, stderr, timed_out, superseded, output_truncated


def _result(
    attachment: ExecutionAttachment, process: subprocess.Popen[bytes], command: Command, terminate, kill
) -> CommandResult:
    stdout, stderr, timed_out, superseded, overflow = _collect(process, command, terminate, kill)
    limit = command.output_limit
    truncated = overflow or len(stdout) + len(stderr) > limit
    stdout = stdout[:limit]
    stderr = stderr[: max(0, limit - len(stdout))]
    lease = attachment.lease
    return CommandResult(
        process.returncode,
        stdout,
        stderr,
        timed_out,
        superseded,
        truncated,
        ExecutionProvenance(lease.operation_id, lease.provider, lease.lease_id),
    )


class LocalProcessEnvironment:
    provider = "local-process"
    capabilities = frozenset(
        {
            EnvironmentCapability.COMMAND_CANCELLATION.value,
            EnvironmentCapability.EXPLICIT_ENVIRONMENT.value,
            EnvironmentCapability.PRIVATE_FILE_TRANSFER.value,
            EnvironmentCapability.PROCESS_GROUP.value,
            EnvironmentCapability.WORKSPACE.value,
        }
    )

    def __init__(self) -> None:
        self._instance_id = str(uuid.uuid4())
        self._leases: dict[str, EnvironmentLease] = {}
        self._territories: dict[str, Path] = {}
        self._specs: dict[str, str] = {}
        self._processes: dict[str, subprocess.Popen[bytes]] = {}
        self._launching: set[str] = set()
        self._attachments: dict[str, ExecutionAttachment] = {}
        self._private_files: dict[str, dict[str, _LocalPrivateRecord]] = {}
        self._private_cleaned: set[tuple[str, str]] = set()
        self._lock = threading.RLock()

    def create(self, operation_id: str, spec: EnvironmentSpec) -> EnvironmentLease:
        with self._lock:
            _operation_id(operation_id)
            if spec.image is not None:
                raise ValueError("local process environments do not accept an image")
            missing = spec.required_capabilities - self.capabilities
            if missing:
                raise ValueError(f"unsupported capabilities: {sorted(missing)}")
            existing = self.lookup(operation_id)
            if existing is not None:
                if self._specs[operation_id] != _fingerprint(spec):
                    raise ValueError("operation id collides with a materially different environment spec")
                return existing
            territory = Path(tempfile.mkdtemp(prefix="impetus-execution-"))
            lease = EnvironmentLease(
                operation_id,
                self.provider,
                f"{self._instance_id}:{uuid.uuid4()}",
                self.capabilities,
                LeaseState.READY,
            )
            self._leases[operation_id] = lease
            self._territories[lease.lease_id] = territory
            self._specs[operation_id] = _fingerprint(spec)
            return lease

    def provision(self, operation_id: str, spec: EnvironmentSpec) -> EnvironmentLease:
        """Compatibility spelling for private CV10 consumers; use :meth:`create`."""

        return self.create(operation_id, spec)

    def lookup(self, operation_id: str) -> EnvironmentLease | None:
        with self._lock:
            return self._leases.get(operation_id)

    def attach(self, lease: EnvironmentLease, workspace_archive_bytes: bytes, input_digest: str) -> ExecutionAttachment:
        with self._lock:
            if lease.provider != "local-process" or self.lookup(lease.operation_id) != lease:
                raise ValueError("attachment lease is not a current local-process territory")
            if self._busy(lease.lease_id):
                raise RuntimeError("local-process territory still has an active command")
            prior = self._attachments.get(lease.lease_id)
            if prior is not None:
                cleaned = self._cleanup_private_files_locked(prior)
                if not cleaned.verified:
                    raise RuntimeError("prior attachment private-file cleanup could not be verified")
            territory = self._territories[lease.lease_id]
            workspace = territory / "workspace"
            if workspace.exists():
                shutil.rmtree(workspace)
            extract_workspace_archive(workspace_archive_bytes, workspace)
            attachment = ExecutionAttachment(str(uuid.uuid4()), lease, input_digest, workspace)
            self._attachments[lease.lease_id] = attachment
            return attachment

    def _busy(self, lease_id: str) -> bool:
        return lease_id in self._launching or lease_id in self._processes

    @staticmethod
    def _provenance(attachment: ExecutionAttachment) -> ExecutionProvenance:
        lease = attachment.lease
        return ExecutionProvenance(lease.operation_id, lease.provider, lease.lease_id)

    def _private_result(
        self,
        attachment: ExecutionAttachment,
        disposition: CleanupDisposition,
        *,
        removed: int = 0,
        detail: str = "",
    ) -> PrivateFileCleanupResult:
        return PrivateFileCleanupResult(
            attachment.attachment_id,
            self._provenance(attachment),
            disposition,
            removed,
            detail,
        )

    def _private_attachment_locked(self, attachment: ExecutionAttachment) -> None:
        lease = attachment.lease
        if (
            lease.provider != self.provider
            or self.lookup(lease.operation_id) != lease
            or EnvironmentCapability.PRIVATE_FILE_TRANSFER.value not in lease.capabilities
            or self._attachments.get(lease.lease_id) != attachment
        ):
            raise ValueError("private-file attachment is not current")
        if self._busy(lease.lease_id):
            raise RuntimeError("private-file operation requires an idle territory")

    @contextmanager
    def _private_tree(self, lease_id: str, file_id: str):
        descriptors: list[int] = []
        try:
            territory = os.open(self._territories[lease_id], _PRIVATE_DIRECTORY_FLAGS)
            descriptors.append(territory)
            private = os.open("private", _PRIVATE_DIRECTORY_FLAGS, dir_fd=territory)
            descriptors.append(private)
            root = os.open(file_id, _PRIVATE_DIRECTORY_FLAGS, dir_fd=private)
            descriptors.append(root)
            if not all(_owned_private_directory(descriptor) for descriptor in descriptors):
                raise RuntimeError("private-file directory invariant failed")
            yield private, root
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)

    def _create_private_file_locked(self, attachment: ExecutionAttachment, file_id: str, value: PrivateFile) -> Path:
        territory_path = self._territories[attachment.lease.lease_id]
        root_path = territory_path / "private" / file_id
        descriptors: list[int] = []
        try:
            territory = os.open(territory_path, _PRIVATE_DIRECTORY_FLAGS)
            descriptors.append(territory)
            if not _owned_private_directory(territory):
                raise RuntimeError("private-file territory invariant failed")
            try:
                os.mkdir("private", mode=0o700, dir_fd=territory)
            except FileExistsError:
                pass
            private = os.open("private", _PRIVATE_DIRECTORY_FLAGS, dir_fd=territory)
            descriptors.append(private)
            os.fchmod(private, 0o700)
            if not _owned_private_directory(private):
                raise RuntimeError("private-file directory invariant failed")
            os.mkdir(file_id, mode=0o700, dir_fd=private)
            root = os.open(file_id, _PRIVATE_DIRECTORY_FLAGS, dir_fd=private)
            descriptors.append(root)
            os.fchmod(root, 0o700)
            if not _owned_private_directory(root):
                raise RuntimeError("private-file root invariant failed")
            file_descriptor = os.open(
                value.name,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                0o600,
                dir_fd=root,
            )
            descriptors.append(file_descriptor)
            os.fchmod(file_descriptor, 0o600)
            self._write_private_content(file_descriptor, value.content)
            os.fsync(file_descriptor)
            if not _owned_private_file(os.fstat(file_descriptor)):
                raise RuntimeError("private-file leaf invariant failed")
            return root_path
        except BaseException:
            for descriptor in reversed(descriptors):
                os.close(descriptor)
            descriptors.clear()
            cleaned = self._discard_private_path(root_path)
            message = (
                "private file import failed"
                if cleaned
                else "private file import failed and cleanup could not be verified"
            )
            raise RuntimeError(message) from None
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)

    @staticmethod
    def _write_private_content(descriptor: int, content: bytes) -> None:
        pending = memoryview(content)
        while pending:
            written = os.write(descriptor, pending)
            if written <= 0:
                raise OSError("private file write made no progress")
            pending = pending[written:]

    @staticmethod
    def _discard_private_path(root: Path) -> bool:
        try:
            metadata = root.lstat()
        except FileNotFoundError:
            return True
        try:
            if stat.S_ISDIR(metadata.st_mode) and not root.is_symlink():
                shutil.rmtree(root)
            else:
                root.unlink()
        except OSError:
            return False
        return not os.path.lexists(root)

    def _record_locked(self, attachment: ExecutionAttachment, reference: PrivateFileRef) -> _LocalPrivateRecord | None:
        if (
            reference.attachment_id != attachment.attachment_id
            or reference.provenance.identity != attachment.lease.identity
        ):
            return None
        record = self._private_files.get(attachment.lease.lease_id, {}).get(reference.file_id)
        return record if record is not None and record.reference == reference else None

    def import_private_file(self, attachment: ExecutionAttachment, value: PrivateFile) -> PrivateFileRef:
        if not isinstance(value, PrivateFile):
            raise TypeError("private file import requires PrivateFile")
        with self._lock:
            self._private_attachment_locked(attachment)
            records = self._private_files.setdefault(attachment.lease.lease_id, {})
            active = [
                record
                for record in records.values()
                if record.present and record.reference.attachment_id == attachment.attachment_id
            ]
            if (
                len(active) >= MAX_PRIVATE_FILES_PER_ATTACHMENT
                or sum(record.content_bytes for record in active) + len(value.content) > MAX_PRIVATE_FILE_TOTAL_BYTES
            ):
                raise ValueError("private file attachment bounds would be exceeded")
            file_id = uuid.uuid4().hex
            root = self._create_private_file_locked(attachment, file_id, value)
            reference = PrivateFileRef(file_id, value.name, attachment.attachment_id, self._provenance(attachment))
            records[file_id] = _LocalPrivateRecord(reference, root, len(value.content))
            self._private_cleaned.discard((attachment.lease.lease_id, attachment.attachment_id))
            return reference

    def _read_private_file_locked(self, attachment: ExecutionAttachment, record: _LocalPrivateRecord) -> bytes:
        if not record.present:
            raise RuntimeError("private file is absent")
        try:
            with self._private_tree(attachment.lease.lease_id, record.reference.file_id) as (_, root):
                descriptor = os.open(record.reference.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=root)
                try:
                    before = os.fstat(descriptor)
                    if not _owned_private_file(before) or before.st_size > MAX_PRIVATE_FILE_BYTES:
                        raise RuntimeError("private-file leaf invariant failed")
                    chunks: list[bytes] = []
                    retained = 0
                    while retained <= MAX_PRIVATE_FILE_BYTES:
                        chunk = os.read(descriptor, min(65536, MAX_PRIVATE_FILE_BYTES + 1 - retained))
                        if not chunk:
                            break
                        chunks.append(chunk)
                        retained += len(chunk)
                    after = os.fstat(descriptor)
                finally:
                    os.close(descriptor)
            stable = (
                before.st_dev,
                before.st_ino,
                before.st_mode,
                before.st_uid,
                before.st_nlink,
                before.st_size,
                before.st_mtime_ns,
                before.st_ctime_ns,
            ) == (
                after.st_dev,
                after.st_ino,
                after.st_mode,
                after.st_uid,
                after.st_nlink,
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            )
            content = b"".join(chunks)
            if not stable or len(content) != after.st_size or len(content) > MAX_PRIVATE_FILE_BYTES:
                raise RuntimeError("private file changed during export")
            return content
        except OSError, RuntimeError:
            raise RuntimeError("private file export could not be verified") from None

    def export_private_file(self, attachment: ExecutionAttachment, reference: PrivateFileRef) -> PrivateFile:
        with self._lock:
            self._private_attachment_locked(attachment)
            record = self._record_locked(attachment, reference)
            if record is None:
                raise ValueError("private file reference is not registered to the current attachment")
            return PrivateFile(reference.name, self._read_private_file_locked(attachment, record))

    def _delete_record_locked(
        self, attachment: ExecutionAttachment, record: _LocalPrivateRecord
    ) -> tuple[CleanupDisposition, int]:
        if not record.present:
            return (
                CleanupDisposition.NOT_CREATED if record.verified_absent else CleanupDisposition.UNVERIFIED,
                0,
            )
        invariant = False
        removed = 0
        try:
            with self._private_tree(attachment.lease.lease_id, record.reference.file_id) as (private, root):
                metadata = os.stat(record.reference.name, dir_fd=root, follow_symlinks=False)
                invariant = _owned_private_file(metadata)
                os.unlink(record.reference.name, dir_fd=root)
                removed = 1
                if os.listdir(root):
                    invariant = False
                else:
                    os.rmdir(record.reference.file_id, dir_fd=private)
        except FileNotFoundError, NotADirectoryError, OSError, RuntimeError:
            invariant = False
        absent = not os.path.lexists(record.root)
        if not absent:
            absent = self._discard_private_path(record.root)
        record.present = not absent
        record.verified_absent = invariant and absent
        return (CleanupDisposition.CLEAN if record.verified_absent else CleanupDisposition.UNVERIFIED, removed)

    def delete_private_file(
        self, attachment: ExecutionAttachment, reference: PrivateFileRef
    ) -> PrivateFileCleanupResult:
        with self._lock:
            try:
                self._private_attachment_locked(attachment)
            except ValueError, RuntimeError:
                return self._private_result(
                    attachment,
                    CleanupDisposition.UNVERIFIED,
                    detail="private-file attachment is stale, foreign, or active",
                )
            record = self._record_locked(attachment, reference)
            if record is None:
                return self._private_result(
                    attachment,
                    CleanupDisposition.UNVERIFIED,
                    detail="private file reference is not registered",
                )
            disposition, removed = self._delete_record_locked(attachment, record)
            return self._private_result(attachment, disposition, removed=removed)

    def _remove_private_parent_locked(self, attachment: ExecutionAttachment) -> bool:
        territory_path = self._territories[attachment.lease.lease_id]
        private_path = territory_path / "private"
        try:
            territory = os.open(territory_path, _PRIVATE_DIRECTORY_FLAGS)
            try:
                try:
                    private = os.open("private", _PRIVATE_DIRECTORY_FLAGS, dir_fd=territory)
                except FileNotFoundError:
                    return True
                try:
                    if not _owned_private_directory(private) or os.listdir(private):
                        return False
                finally:
                    os.close(private)
                os.rmdir("private", dir_fd=territory)
            finally:
                os.close(territory)
            return not os.path.lexists(private_path)
        except NotADirectoryError, OSError:
            return False

    def _cleanup_private_files_locked(self, attachment: ExecutionAttachment) -> PrivateFileCleanupResult:
        try:
            self._private_attachment_locked(attachment)
        except ValueError, RuntimeError:
            return self._private_result(
                attachment,
                CleanupDisposition.UNVERIFIED,
                detail="private-file attachment is stale, foreign, or active",
            )
        key = (attachment.lease.lease_id, attachment.attachment_id)
        if key in self._private_cleaned:
            return self._private_result(attachment, CleanupDisposition.NOT_CREATED)
        records = [
            record
            for record in self._private_files.get(attachment.lease.lease_id, {}).values()
            if record.reference.attachment_id == attachment.attachment_id
        ]
        removed = 0
        verified = True
        for record in records:
            disposition, count = self._delete_record_locked(attachment, record)
            removed += count
            verified = verified and disposition in (CleanupDisposition.CLEAN, CleanupDisposition.NOT_CREATED)
        parent_absent = self._remove_private_parent_locked(attachment)
        if not parent_absent:
            parent = self._territories[attachment.lease.lease_id] / "private"
            discarded = self._discard_private_path(parent)
            verified = False
            parent_absent = discarded
        verified = verified and parent_absent
        if verified:
            self._private_cleaned.add(key)
        disposition = (
            CleanupDisposition.CLEAN
            if verified and removed
            else CleanupDisposition.NOT_CREATED
            if verified
            else CleanupDisposition.UNVERIFIED
        )
        return self._private_result(attachment, disposition, removed=removed)

    def cleanup_private_files(self, attachment: ExecutionAttachment) -> PrivateFileCleanupResult:
        with self._lock:
            return self._cleanup_private_files_locked(attachment)

    def _private_bindings_locked(self, attachment: ExecutionAttachment, command: Command) -> dict[str, str]:
        if not command.private_roots:
            return {}
        self._private_attachment_locked(attachment)
        bindings: dict[str, str] = {}
        for name, reference in command.private_roots.items():
            record = self._record_locked(attachment, reference)
            if record is None or not record.present:
                raise ValueError("command private root is not registered to the current attachment")
            self._read_private_file_locked(attachment, record)
            bindings[name] = str(record.root)
        return bindings

    @staticmethod
    def _redact_private_paths(value: bytes, roots: dict[str, str]) -> bytes:
        for root in roots.values():
            value = value.replace(os.fsencode(root), b"[PRIVATE_ROOT]")
        return value

    def _validate_execution_locked(self, attachment: ExecutionAttachment) -> None:
        lease = attachment.lease
        if lease.provider != self.provider or self.lookup(lease.operation_id) != lease:
            raise ValueError("execution attachment is not owned by this local-process provider")
        if self._busy(lease.lease_id):
            raise RuntimeError("local-process territory already has an active command")

    def _redacted_result(self, result: CommandResult, private_bindings: dict[str, str]) -> CommandResult:
        if not private_bindings:
            return result
        return CommandResult(
            result.returncode,
            self._redact_private_paths(result.stdout, private_bindings),
            self._redact_private_paths(result.stderr, private_bindings),
            result.timed_out,
            result.superseded,
            result.output_truncated,
            result.provenance,
        )

    def execute(self, attachment: ExecutionAttachment, command: Command) -> CommandResult:
        lease = attachment.lease
        with self._lock:
            self._validate_execution_locked(attachment)
        if command.is_current is not None and not command.is_current():
            return CommandResult(
                -signal.SIGTERM,
                b"",
                b"",
                False,
                True,
                False,
                ExecutionProvenance(lease.operation_id, lease.provider, lease.lease_id),
            )
        with self._lock:
            self._validate_execution_locked(attachment)
            private_bindings = self._private_bindings_locked(attachment, command)
            environment = dict(command.environment)
            environment.update(private_bindings)
            self._launching.add(lease.lease_id)
            try:
                process = subprocess.Popen(
                    command.argv,
                    cwd=_checked_host_cwd(attachment.workspace, command.cwd),
                    env=environment,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    start_new_session=True,
                )
                self._processes[lease.lease_id] = process
            finally:
                self._launching.discard(lease.lease_id)

        def terminate() -> None:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)

        def kill() -> None:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)

        try:
            result = _result(attachment, process, command, terminate, kill)
            return self._redacted_result(result, private_bindings)
        finally:
            with self._lock:
                self._processes.pop(lease.lease_id, None)

    def export(self, attachment: ExecutionAttachment) -> bytes:
        with self._lock:
            if self.lookup(attachment.lease.operation_id) != attachment.lease:
                raise ValueError("execution attachment is no longer current")
            return workspace_archive(attachment.workspace)

    def cancel(self, lease: EnvironmentLease, reason: str) -> None:
        del reason
        with self._lock:
            current = self.lookup(lease.operation_id)
            if current is None or current.identity != lease.identity:
                return
            process = self._processes.get(lease.lease_id)
            if process is not None and process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)

    def destroy(self, lease: EnvironmentLease) -> CleanupResult:
        """Remove provider territory only; Runner/attachment destruction never destroys a Thread."""
        with self._lock:
            if lease.provider != self.provider:
                return CleanupResult(
                    lease.identity,
                    CleanupDisposition.UNVERIFIED,
                    "lease belongs to a different provider",
                )
            current = self.lookup(lease.operation_id)
            if current is None:
                owned = lease.lease_id.startswith(f"{self._instance_id}:")
                disposition = (
                    CleanupDisposition.NOT_CREATED
                    if owned and lease.lease_id not in self._territories
                    else CleanupDisposition.UNVERIFIED
                )
                detail = (
                    "no lease exists in the owning local adapter"
                    if disposition is CleanupDisposition.NOT_CREATED
                    else "local lease is not observable"
                )
                return CleanupResult(lease.identity, disposition, detail)
            if current.identity != lease.identity:
                return CleanupResult(
                    lease.identity,
                    CleanupDisposition.UNVERIFIED,
                    "operation resolves to a different local lease",
                )
            process = self._processes.get(lease.lease_id)
            if process is not None and process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=0.5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=1)
                except OSError, subprocess.SubprocessError:
                    return CleanupResult(
                        lease.identity,
                        CleanupDisposition.UNVERIFIED,
                        "local command termination could not be verified",
                    )
            self._processes.pop(lease.lease_id, None)
            territory = self._territories.get(lease.lease_id)
            try:
                if territory is not None:
                    shutil.rmtree(territory)
            except OSError:
                return CleanupResult(
                    lease.identity,
                    CleanupDisposition.UNVERIFIED,
                    "local workspace removal could not be verified",
                )
            if territory is not None and territory.exists():
                return CleanupResult(
                    lease.identity,
                    CleanupDisposition.UNVERIFIED,
                    "local workspace remains after destroy",
                )
            self._territories.pop(lease.lease_id, None)
            self._attachments.pop(lease.lease_id, None)
            self._private_files.pop(lease.lease_id, None)
            self._private_cleaned = {key for key in self._private_cleaned if key[0] != lease.lease_id}
            self._leases.pop(lease.operation_id, None)
            self._specs.pop(lease.operation_id, None)
            return CleanupResult(lease.identity, CleanupDisposition.CLEAN)

    def reconcile(self, operation_id: str) -> ReconcileResult:
        lease = self.lookup(operation_id)
        return (
            ReconcileResult(ReconcileClass.RETRYABLE, detail="no local lease")
            if lease is None
            else ReconcileResult(ReconcileClass.UNCERTAIN, lease, "local process completion is not durably recorded")
        )


class DockerEnvironment:
    provider = "docker"
    capabilities = frozenset(
        {
            EnvironmentCapability.CONTAINER.value,
            EnvironmentCapability.EXPLICIT_ENVIRONMENT.value,
            EnvironmentCapability.RECREATABLE_LOOKUP.value,
            EnvironmentCapability.TERRITORY_CANCELLATION.value,
            EnvironmentCapability.WORKSPACE.value,
        }
    )

    def __init__(self) -> None:
        self._processes: dict[str, subprocess.Popen[bytes]] = {}

    @staticmethod
    def _docker(
        *args: str, check: bool = True, input: bytes | None = None, timeout: float = 120
    ) -> subprocess.CompletedProcess:
        return subprocess.run(
            ("docker", *args), capture_output=True, input=input, check=check, text=input is None, timeout=timeout
        )

    def lookup(self, operation_id: str) -> EnvironmentLease | None:
        _operation_id(operation_id)
        found = self._docker("ps", "--all", "--quiet", "--filter", f"label={_LABEL}={operation_id}").stdout.split()
        if len(found) > 1:
            raise RuntimeError(f"operation {operation_id!r} resolves to multiple containers")
        if not found:
            return None
        info = json.loads(self._docker("inspect", found[0]).stdout)[0]
        if any(mount["Type"] == "bind" for mount in info["Mounts"]):
            raise RuntimeError("execution container unexpectedly has a bind mount")
        state = LeaseState.READY if info["State"]["Running"] else LeaseState.TERMINAL
        return EnvironmentLease(operation_id, "docker", found[0], self.capabilities, state)

    def create(self, operation_id: str, spec: EnvironmentSpec) -> EnvironmentLease:
        _operation_id(operation_id)
        if spec.image is None:
            raise ValueError("Docker requires an image")
        missing = spec.required_capabilities - self.capabilities
        if missing:
            raise ValueError(f"unsupported capabilities: {sorted(missing)}")
        existing = self.lookup(operation_id)
        if existing is not None:
            info = json.loads(self._docker("inspect", existing.lease_id).stdout)[0]
            if info["Config"]["Labels"].get(_SPEC_LABEL) != _fingerprint(spec):
                raise ValueError("operation id collides with a materially different environment spec")
            if existing.state is LeaseState.TERMINAL:
                raise RuntimeError("operation has a terminal prior territory; reconcile before retrying")
            return existing
        created = self._docker(
            "run",
            "--detach",
            "--label",
            f"{_LABEL}={operation_id}",
            "--label",
            f"{_SPEC_LABEL}={_fingerprint(spec)}",
            "--workdir",
            "/workspace",
            "--entrypoint",
            "/bin/sh",
            spec.image,
            "-c",
            "mkdir -p /workspace; while :; do sleep 3600; done",
        )
        return self.lookup(operation_id) or self._remove_then_fail(created.stdout.strip())

    def provision(self, operation_id: str, spec: EnvironmentSpec) -> EnvironmentLease:
        """Compatibility spelling for private CV10 consumers; use :meth:`create`."""

        return self.create(operation_id, spec)

    def _remove_then_fail(self, container: str):
        self._docker("rm", "--force", container, check=False)
        raise RuntimeError("created Docker lease could not be looked up")

    def attach(self, lease: EnvironmentLease, workspace_archive_bytes: bytes, input_digest: str) -> ExecutionAttachment:
        if (
            lease.provider != "docker"
            or self.lookup(lease.operation_id) != lease
            or lease.state is not LeaseState.READY
        ):
            raise ValueError("attachment lease is not a current ready Docker territory")
        if lease.lease_id in self._processes:
            raise RuntimeError("Docker territory still has an active command")
        with tempfile.TemporaryDirectory() as temporary:
            extract_workspace_archive(workspace_archive_bytes, Path(temporary))
        self._docker(
            "exec",
            "-i",
            lease.lease_id,
            "sh",
            "-c",
            "rm -rf /workspace && mkdir /workspace && tar -xf - -C /workspace",
            input=workspace_archive_bytes,
        )
        return ExecutionAttachment(str(uuid.uuid4()), lease, input_digest, Path("/workspace"))

    def execute(self, attachment: ExecutionAttachment, command: Command) -> CommandResult:
        if command.private_roots:
            raise ValueError("Docker does not support the private-file-transfer capability")
        lease = attachment.lease
        if (
            lease.provider != "docker"
            or self.lookup(lease.operation_id) != lease
            or lease.state is not LeaseState.READY
        ):
            raise ValueError("execution attachment is not a current ready Docker territory")
        if lease.lease_id in self._processes:
            raise RuntimeError("Docker territory already has an active command")
        if command.is_current is not None and not command.is_current():
            return CommandResult(
                -signal.SIGTERM,
                b"",
                b"",
                False,
                True,
                False,
                ExecutionProvenance(lease.operation_id, lease.provider, lease.lease_id),
            )
        cwd = _checked_guest_cwd(attachment.workspace, command.cwd)
        environment_names = tuple(command.environment)
        assignments = " ".join(f'{name}="${{{name}}}"' for name in environment_names)
        wrapper = f'exec env -i {assignments} "$@"'
        docker_environment = {
            name: value for name, value in os.environ.items() if name in {"HOME", "PATH"} or name.startswith("DOCKER_")
        }
        docker_environment.update(command.environment)
        docker_args = ["docker", "exec", "--workdir", str(cwd)]
        for name in environment_names:
            docker_args.extend(("--env", name))
        docker_args.extend((lease.lease_id, "sh", "-c", wrapper, "petrus-command", *command.argv))
        process = subprocess.Popen(
            docker_args,
            env=docker_environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._processes[lease.lease_id] = process

        def terminate() -> None:
            self._docker("kill", "--signal", "TERM", lease.lease_id, check=False)

        def kill() -> None:
            self._docker("kill", lease.lease_id, check=False)

        try:
            return _result(attachment, process, command, terminate, kill)
        finally:
            if process.poll() is None:
                kill()
                process.wait()
            self._processes.pop(lease.lease_id, None)

    def export(self, attachment: ExecutionAttachment) -> bytes:
        if self.lookup(attachment.lease.operation_id) != attachment.lease:
            raise ValueError("execution attachment is no longer current")
        raw = subprocess.run(
            ("docker", "exec", attachment.lease.lease_id, "tar", "-cf", "-", "-C", "/workspace", "."),
            check=True,
            capture_output=True,
            timeout=60,
        ).stdout
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            extract_workspace_archive(raw, root)
            return workspace_archive(root)

    def cancel(self, lease: EnvironmentLease, reason: str) -> None:
        del reason
        try:
            current = self.lookup(lease.operation_id)
        except OSError, subprocess.SubprocessError, ValueError:
            return
        if current is None or current.identity != lease.identity:
            return
        self._docker("kill", lease.lease_id, check=False)

    def destroy(self, lease: EnvironmentLease) -> CleanupResult:
        """Remove provider territory only; Runner/attachment destruction never destroys a Thread."""
        if lease.provider != self.provider:
            return CleanupResult(
                lease.identity,
                CleanupDisposition.UNVERIFIED,
                "lease belongs to a different provider",
            )
        try:
            current = self.lookup(lease.operation_id)
        except OSError, subprocess.SubprocessError, ValueError:
            return CleanupResult(
                lease.identity,
                CleanupDisposition.UNVERIFIED,
                "Docker lookup failed before destroy",
            )
        if current is None:
            return CleanupResult(lease.identity, CleanupDisposition.NOT_CREATED, "no Docker container")
        if current.identity != lease.identity:
            return CleanupResult(
                lease.identity,
                CleanupDisposition.UNVERIFIED,
                "operation resolves to a different Docker lease",
            )
        try:
            self._docker("rm", "--force", lease.lease_id, check=False)
            remaining = self.lookup(lease.operation_id)
        except OSError, subprocess.SubprocessError, ValueError:
            return CleanupResult(
                lease.identity,
                CleanupDisposition.UNVERIFIED,
                "Docker cleanup could not be independently verified",
            )
        if remaining is None:
            return CleanupResult(lease.identity, CleanupDisposition.CLEAN)
        return CleanupResult(
            lease.identity,
            CleanupDisposition.UNVERIFIED,
            "Docker container remains after destroy",
        )

    def reconcile(self, operation_id: str) -> ReconcileResult:
        try:
            lease = self.lookup(operation_id)
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            return ReconcileResult(ReconcileClass.UNCERTAIN, detail=str(error))
        if lease is None:
            return ReconcileResult(ReconcileClass.RETRYABLE, detail="no container")
        if lease.state is LeaseState.TERMINAL:
            return ReconcileResult(ReconcileClass.TERMINAL, lease)
        return ReconcileResult(ReconcileClass.UNCERTAIN, lease, "container readiness does not prove operation outcome")


class E2bEnvironment:
    """Private E2B VM adapter; SDK objects and provider credentials stay host-side."""

    provider = "e2b"
    capabilities = frozenset(
        {
            EnvironmentCapability.COMMAND_CANCELLATION.value,
            EnvironmentCapability.EXPLICIT_ENVIRONMENT.value,
            EnvironmentCapability.RECREATABLE_LOOKUP.value,
            EnvironmentCapability.VM.value,
            EnvironmentCapability.WORKSPACE.value,
        }
    )

    def __init__(self, *, api_key: str | None = None, sdk_loader=None, lease_timeout: int = 900) -> None:
        if lease_timeout <= 0:
            raise ValueError("E2B lease timeout must be positive")
        self._api_key = api_key
        self._sdk_loader = sdk_loader or self._load_sdk
        self._lease_timeout = lease_timeout
        self._sandboxes: dict[str, Any] = {}
        self._commands: dict[str, Any] = {}

    @staticmethod
    def _load_sdk():
        return importlib.import_module("e2b")

    def _sdk(self):
        return self._sdk_loader()

    def _opts(self) -> dict[str, str]:
        key = self._api_key or os.getenv("E2B_API_KEY")
        return {} if key is None else {"api_key": key}

    def _sandbox(self, lease: EnvironmentLease):
        sandbox = self._sandboxes.get(lease.lease_id)
        if sandbox is None:
            sandbox = self._sdk().Sandbox.connect(lease.lease_id, timeout=self._lease_timeout, **self._opts())
            self._sandboxes[lease.lease_id] = sandbox
        return sandbox

    def lookup(self, operation_id: str) -> EnvironmentLease | None:
        _operation_id(operation_id)
        sdk = self._sdk()
        paginator = sdk.Sandbox.list(
            query=sdk.SandboxQuery(metadata={_LABEL: operation_id}),
            limit=2,
            **self._opts(),
        )
        found = []
        while paginator.has_next and len(found) < 2:
            found.extend(paginator.next_items(**self._opts()))
        if len(found) > 1:
            raise RuntimeError(f"operation {operation_id!r} resolves to multiple E2B sandboxes")
        if not found:
            return None
        info = found[0]
        state = str(getattr(info.state, "value", info.state)).lower()
        lease_state = LeaseState.READY if state in {"running", "paused"} else LeaseState.TERMINAL
        return EnvironmentLease(operation_id, "e2b", str(info.sandbox_id), self.capabilities, lease_state)

    def create(self, operation_id: str, spec: EnvironmentSpec) -> EnvironmentLease:
        _operation_id(operation_id)
        if spec.image is None:
            raise ValueError("E2B requires a template image")
        missing = spec.required_capabilities - self.capabilities
        if missing:
            raise ValueError(f"unsupported capabilities: {sorted(missing)}")
        existing = self.lookup(operation_id)
        if existing is not None:
            sdk = self._sdk()
            paginator = sdk.Sandbox.list(
                query=sdk.SandboxQuery(metadata={_LABEL: operation_id}),
                limit=1,
                **self._opts(),
            )
            info = paginator.next_items(**self._opts())[0]
            if info.metadata.get(_SPEC_LABEL) != _fingerprint(spec):
                raise ValueError("operation id collides with a materially different environment spec")
            if existing.state is LeaseState.TERMINAL:
                raise RuntimeError("operation has a terminal prior VM; reconcile before retrying")
            return existing
        sandbox = self._sdk().Sandbox.create(
            template=spec.image,
            timeout=self._lease_timeout,
            metadata={_LABEL: operation_id, _SPEC_LABEL: _fingerprint(spec)},
            envs={},
            secure=True,
            **self._opts(),
        )
        self._sandboxes[str(sandbox.sandbox_id)] = sandbox
        try:
            found = self.lookup(operation_id)
        except BaseException:
            try:
                sandbox.kill()
            except BaseException:
                pass
            self._sandboxes.pop(str(sandbox.sandbox_id), None)
            raise
        return found or self._kill_then_fail(sandbox)

    def provision(self, operation_id: str, spec: EnvironmentSpec) -> EnvironmentLease:
        """Compatibility spelling for private CV10 consumers; use :meth:`create`."""

        return self.create(operation_id, spec)

    def _kill_then_fail(self, sandbox):
        try:
            sandbox.kill()
        finally:
            self._sandboxes.pop(str(sandbox.sandbox_id), None)
        raise RuntimeError("created E2B lease could not be looked up")

    def attach(self, lease: EnvironmentLease, workspace_archive_bytes: bytes, input_digest: str) -> ExecutionAttachment:
        if lease.provider != "e2b" or self.lookup(lease.operation_id) != lease or lease.state is not LeaseState.READY:
            raise ValueError("attachment lease is not a current ready E2B VM")
        if lease.lease_id in self._commands:
            raise RuntimeError("E2B territory still has an active command")
        with tempfile.TemporaryDirectory() as temporary:
            extract_workspace_archive(workspace_archive_bytes, Path(temporary))
        sandbox = self._sandbox(lease)
        archive_path = f"/tmp/petrus-input-{uuid.uuid4()}.tar"
        sandbox.files.write(archive_path, workspace_archive_bytes)
        try:
            sandbox.commands.run(
                f"rm -rf {shlex.quote(_E2B_WORKSPACE)} && mkdir -p {shlex.quote(_E2B_WORKSPACE)} && "
                f"tar -xf {shlex.quote(archive_path)} -C {shlex.quote(_E2B_WORKSPACE)}",
                timeout=60,
            )
        finally:
            sandbox.files.remove(archive_path)
        return ExecutionAttachment(str(uuid.uuid4()), lease, input_digest, Path(_E2B_WORKSPACE))

    def execute(  # noqa: C901 - remote cancellation and bounded collection precedence is explicit
        self, attachment: ExecutionAttachment, command: Command
    ) -> CommandResult:
        if command.private_roots:
            raise ValueError("E2B does not support the private-file-transfer capability")
        lease = attachment.lease
        if lease.provider != "e2b" or self.lookup(lease.operation_id) != lease or lease.state is not LeaseState.READY:
            raise ValueError("execution attachment is not a current ready E2B VM")
        if lease.lease_id in self._commands:
            raise RuntimeError("E2B territory already has an active command")
        provenance = ExecutionProvenance(lease.operation_id, lease.provider, lease.lease_id)
        if command.is_current is not None and not command.is_current():
            return CommandResult(-signal.SIGTERM, b"", b"", False, True, False, provenance)
        cwd = str(_checked_guest_cwd(attachment.workspace, command.cwd))
        handle = self._sandbox(lease).commands.run(
            shlex.join(command.argv),
            background=True,
            envs=dict(command.environment),
            cwd=cwd,
            timeout=max(command.timeout or self._lease_timeout, 1),
        )
        self._commands[lease.lease_id] = handle
        completed: queue.Queue[object] = queue.Queue(maxsize=1)
        stdout_parts: list[str] = []
        stderr_parts: list[str] = []

        def wait() -> None:
            try:
                result = handle.wait(on_stdout=stdout_parts.append, on_stderr=stderr_parts.append)
            except BaseException as error:
                result = error
            completed.put(result)

        waiter = threading.Thread(target=wait, name=f"e2b-command-{lease.lease_id}", daemon=True)
        waiter.start()
        deadline = None if command.timeout is None else time.monotonic() + command.timeout
        timed_out = superseded = overflow = False
        try:
            while waiter.is_alive():
                size = sum(len(part.encode()) for part in (*stdout_parts, *stderr_parts))
                overflow = size > command.output_limit
                try:
                    superseded = command.is_current is not None and not command.is_current()
                except BaseException:
                    handle.kill()
                    waiter.join(timeout=5)
                    raise
                timed_out = deadline is not None and time.monotonic() >= deadline
                if overflow or superseded or timed_out:
                    handle.kill()
                    break
                waiter.join(timeout=0.05)
            waiter.join(timeout=5)
            if waiter.is_alive():
                raise RuntimeError("E2B command did not terminate after cancellation")
            value = completed.get_nowait()
            if (
                isinstance(value, BaseException)
                and not hasattr(value, "exit_code")
                and not (overflow or superseded or timed_out)
            ):
                raise value
            returncode = int(getattr(value, "exit_code", -signal.SIGKILL))
            result_stdout = getattr(value, "stdout", None)
            result_stderr = getattr(value, "stderr", None)
            if not stdout_parts and result_stdout:
                stdout_parts.append(str(result_stdout))
            if not stderr_parts and result_stderr:
                stderr_parts.append(str(result_stderr))
            stdout = "".join(stdout_parts).encode()
            stderr = "".join(stderr_parts).encode()
            overflow = overflow or len(stdout) + len(stderr) > command.output_limit
            stdout = stdout[: command.output_limit]
            stderr = stderr[: max(0, command.output_limit - len(stdout))]
            return CommandResult(returncode, stdout, stderr, timed_out, superseded, overflow, provenance)
        finally:
            self._commands.pop(lease.lease_id, None)

    def export(self, attachment: ExecutionAttachment) -> bytes:
        lease = attachment.lease
        if self.lookup(lease.operation_id) != lease:
            raise ValueError("execution attachment is no longer current")
        sandbox = self._sandbox(lease)
        archive_path = f"/tmp/petrus-output-{uuid.uuid4()}.tar"
        sandbox.commands.run(
            f"tar -cf {shlex.quote(archive_path)} -C {shlex.quote(_E2B_WORKSPACE)} .",
            timeout=60,
        )
        try:
            raw = bytes(sandbox.files.read(archive_path, format="bytes"))
        finally:
            sandbox.files.remove(archive_path)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            extract_workspace_archive(raw, root)
            return workspace_archive(root)

    def cancel(self, lease: EnvironmentLease, reason: str) -> None:
        del reason
        try:
            current = self.lookup(lease.operation_id)
        except Exception:
            return
        if current is None or current.identity != lease.identity:
            return
        handle = self._commands.get(lease.lease_id)
        if handle is not None:
            handle.kill()

    def destroy(self, lease: EnvironmentLease) -> CleanupResult:
        if lease.provider != self.provider:
            return CleanupResult(
                lease.identity,
                CleanupDisposition.UNVERIFIED,
                "lease belongs to a different provider",
            )
        try:
            current = self.lookup(lease.operation_id)
        except Exception:
            return CleanupResult(
                lease.identity,
                CleanupDisposition.UNVERIFIED,
                "E2B lookup failed before destroy",
            )
        if current is None:
            return CleanupResult(lease.identity, CleanupDisposition.NOT_CREATED, "no E2B VM")
        if current.identity != lease.identity:
            return CleanupResult(
                lease.identity,
                CleanupDisposition.UNVERIFIED,
                "operation resolves to a different E2B lease",
            )
        self.cancel(lease, "destroy")
        sandbox = self._sandboxes.get(lease.lease_id)
        if sandbox is None:
            try:
                sandbox = self._sdk().Sandbox.connect(lease.lease_id, **self._opts())
            except Exception:
                return CleanupResult(
                    lease.identity,
                    CleanupDisposition.UNVERIFIED,
                    "E2B VM could not be reached for destroy",
                )
        try:
            sandbox.kill()
            self._sandboxes.pop(lease.lease_id, None)
            remaining = self.lookup(lease.operation_id)
        except Exception:
            return CleanupResult(
                lease.identity,
                CleanupDisposition.UNVERIFIED,
                "E2B cleanup could not be independently verified",
            )
        if remaining is None:
            return CleanupResult(lease.identity, CleanupDisposition.CLEAN)
        return CleanupResult(
            lease.identity,
            CleanupDisposition.UNVERIFIED,
            "E2B VM remains after destroy",
        )

    def reconcile(self, operation_id: str) -> ReconcileResult:
        try:
            lease = self.lookup(operation_id)
        except Exception as error:
            return ReconcileResult(ReconcileClass.UNCERTAIN, detail=str(error))
        if lease is None:
            return ReconcileResult(ReconcileClass.RETRYABLE, detail="no E2B VM")
        if lease.state is LeaseState.TERMINAL:
            return ReconcileResult(ReconcileClass.TERMINAL, lease)
        return ReconcileResult(ReconcileClass.UNCERTAIN, lease, "VM readiness does not prove operation outcome")
