"""Private filesystem materialization and cleanup evidence."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path


class MaterializationError(RuntimeError):
    """A private opaque-state materialization operation failed."""


class MaterializationSecurityError(MaterializationError):
    """A filesystem shape could redirect or expose opaque state."""


@dataclass(frozen=True)
class CleanupEvidence:
    """Secret-free evidence for one cooperative local cleanup attempt."""

    attachment_id: str
    removed: bool
    already_absent: bool
    bytes_overwritten: int
    physical_erasure_guaranteed: bool = False
    security_violation: bool = False


@dataclass(frozen=True)
class CleanupSummary:
    """Aggregate cleanup evidence without materialization paths or contents."""

    attempted: int
    removed: int
    already_absent: int
    unresolved: int
    security_violations: int
    physical_erasure_guaranteed: bool = False


class MaterializedState:
    """One private opaque-state file whose representation omits its path and bytes."""

    def __init__(self, materializer: PrivateFileMaterializer, attachment_id: str) -> None:
        self._materializer = materializer
        self._attachment_id = attachment_id

    @property
    def path(self) -> Path:
        """Return the private path for the selected provider runtime only."""
        return self._materializer._path(self._attachment_id)

    @property
    def erased(self) -> bool:
        try:
            self.path.lstat()
        except FileNotFoundError:
            return True
        return False

    def read(self) -> bytes:
        return self._materializer.read(self._attachment_id)

    def replace(self, opaque_state: bytes) -> None:
        self._materializer.replace(self._attachment_id, opaque_state)

    def __repr__(self) -> str:
        state = "erased" if self.erased else "materialized"
        return f"MaterializedState(<{state}>)"


class PrivateFileMaterializer:
    """Materialize one opaque state blob under a private, non-symlink root."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self._prepare_root()

    def materialize(self, attachment_id: str, plaintext: bytearray) -> MaterializedState:
        self._validate_attachment_id(attachment_id)
        self._assert_root()
        path = self._path(attachment_id)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags, 0o600)
        except FileExistsError as error:
            raise MaterializationSecurityError(
                f"materialization target for attachment {attachment_id!r} already exists or is a symlink"
            ) from error
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(plaintext)
                stream.flush()
                os.fsync(stream.fileno())
        finally:
            os.close(descriptor)
        return MaterializedState(self, attachment_id)

    def read(self, attachment_id: str) -> bytes:
        descriptor = self._open_private_file(attachment_id, os.O_RDONLY)
        try:
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                return stream.read()
        finally:
            os.close(descriptor)

    def replace(self, attachment_id: str, opaque_state: bytes) -> None:
        if not isinstance(opaque_state, bytes) or not opaque_state:
            raise ValueError("returned opaque state must be non-empty bytes")
        descriptor = self._open_private_file(attachment_id, os.O_WRONLY | os.O_TRUNC)
        try:
            with os.fdopen(descriptor, "wb", closefd=False) as stream:
                stream.write(opaque_state)
                stream.flush()
                os.fsync(stream.fileno())
        finally:
            os.close(descriptor)

    def cleanup(self, attachment_id: str) -> CleanupEvidence:
        self._validate_attachment_id(attachment_id)
        path = self._path(attachment_id)
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            return CleanupEvidence(attachment_id, False, True, 0)
        if stat.S_ISLNK(metadata.st_mode):
            path.unlink()
            return CleanupEvidence(attachment_id, True, False, 0, security_violation=True)
        if not stat.S_ISREG(metadata.st_mode):
            return CleanupEvidence(attachment_id, False, False, 0, security_violation=True)

        overwritten = metadata.st_size
        flags = os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(path, flags)
            try:
                remaining = overwritten
                block = b"\0" * min(max(remaining, 1), 65_536)
                while remaining:
                    written = os.write(descriptor, block[:remaining])
                    remaining -= written
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            path.unlink()
        except OSError:
            return CleanupEvidence(attachment_id, False, False, 0, security_violation=True)
        return CleanupEvidence(attachment_id, True, False, overwritten)

    def summarize(self, attachment_ids: tuple[str, ...]) -> CleanupSummary:
        evidence = tuple(self.cleanup(attachment_id) for attachment_id in attachment_ids)
        return CleanupSummary(
            attempted=len(evidence),
            removed=sum(item.removed for item in evidence),
            already_absent=sum(item.already_absent for item in evidence),
            unresolved=sum(not item.removed and not item.already_absent for item in evidence),
            security_violations=sum(item.security_violation for item in evidence),
        )

    def _open_private_file(self, attachment_id: str, flags: int) -> int:
        self._validate_attachment_id(attachment_id)
        self._assert_root()
        path = self._path(attachment_id)
        try:
            metadata = path.lstat()
        except FileNotFoundError as error:
            raise MaterializationError(f"materialization for attachment {attachment_id!r} is absent") from error
        if stat.S_ISLNK(metadata.st_mode):
            raise MaterializationSecurityError(f"materialization for attachment {attachment_id!r} is a symlink")
        if not stat.S_ISREG(metadata.st_mode):
            raise MaterializationSecurityError(f"materialization for attachment {attachment_id!r} is not a file")
        if stat.S_IMODE(metadata.st_mode) != 0o600:
            raise MaterializationSecurityError(f"materialization for attachment {attachment_id!r} has unsafe mode")
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
            os.close(descriptor)
            raise MaterializationSecurityError(f"materialization for attachment {attachment_id!r} changed during open")
        return descriptor

    def _prepare_root(self) -> None:
        if self.root.is_symlink():
            raise MaterializationSecurityError("materialization root must not be a symlink")
        if not self.root.exists():
            self.root.mkdir(mode=0o700, parents=True)
            self.root.chmod(0o700)
        self._assert_root()

    def _assert_root(self) -> None:
        try:
            metadata = self.root.lstat()
        except FileNotFoundError as error:
            raise MaterializationSecurityError("materialization root is absent") from error
        if stat.S_ISLNK(metadata.st_mode):
            raise MaterializationSecurityError("materialization root must not be a symlink")
        if not stat.S_ISDIR(metadata.st_mode):
            raise MaterializationSecurityError("materialization root must be a directory")
        if stat.S_IMODE(metadata.st_mode) != 0o700:
            raise MaterializationSecurityError("materialization root must have mode 0700")

    def _path(self, attachment_id: str) -> Path:
        return self.root / f"{attachment_id}.state"

    @staticmethod
    def _validate_attachment_id(attachment_id: str) -> None:
        if (
            not isinstance(attachment_id, str)
            or not attachment_id
            or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in attachment_id)
        ):
            raise ValueError("attachment identity must contain only lowercase letters, digits, and hyphens")
