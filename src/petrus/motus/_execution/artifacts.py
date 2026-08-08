"""Host-custodied artifacts for private Motus execution evidence."""

from __future__ import annotations

import hashlib
import io
import json
import os
import tarfile
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 200_000
MAX_EXTRACTED_BYTES = 2 * 1024 * 1024 * 1024


@dataclass(frozen=True)
class ProducerCorrelation:
    operation_id: str
    provider: str
    lease_id: str


@dataclass(frozen=True)
class ArtifactRef:
    digest: str
    size: int
    media_type: str
    retention_class: str
    producer: ProducerCorrelation


class ArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def put(self, data: bytes, *, media_type: str, retention_class: str, producer: ProducerCorrelation) -> ArtifactRef:
        if not isinstance(data, bytes):
            raise TypeError("artifact content must be bytes")
        if not media_type or not retention_class:
            raise ValueError("artifact media type and retention class must be non-empty")
        detached = bytes(data)
        digest = hashlib.sha256(detached).hexdigest()
        reference = ArtifactRef(digest, len(detached), media_type, retention_class, producer)
        directory = self.root / digest[:2]
        directory.mkdir(exist_ok=True)
        self._atomic(directory / f"{digest}.data", detached)
        self._atomic(directory / f"{digest}.json", json.dumps(asdict(reference), sort_keys=True).encode())
        return reference

    def read(self, reference: ArtifactRef) -> bytes:
        data = (self.root / reference.digest[:2] / f"{reference.digest}.data").read_bytes()
        if len(data) != reference.size or hashlib.sha256(data).hexdigest() != reference.digest:
            raise ValueError("artifact integrity check failed")
        return data

    def delete(self, reference: ArtifactRef) -> None:
        directory = self.root / reference.digest[:2]
        (directory / f"{reference.digest}.data").unlink(missing_ok=True)
        (directory / f"{reference.digest}.json").unlink(missing_ok=True)

    def prune(self, retain: int, *, protected: frozenset[str] = frozenset()) -> tuple[str, ...]:
        """Bound host evidence by blob count without touching current-operation authority."""

        if isinstance(retain, bool) or not isinstance(retain, int) or retain <= 0:
            raise ValueError("artifact retention must be a positive integer")
        entries = sorted(
            self.root.glob("*/*.data"),
            key=lambda path: (path.stat().st_mtime_ns, path.name),
        )
        remove = max(0, len(entries) - retain)
        removed: list[str] = []
        for data_path in entries:
            digest = data_path.stem
            if remove == 0:
                break
            if digest in protected:
                continue
            data_path.unlink(missing_ok=True)
            data_path.with_suffix(".json").unlink(missing_ok=True)
            removed.append(digest)
            remove -= 1
        return tuple(removed)

    @staticmethod
    def _atomic(path: Path, data: bytes) -> None:
        fd, temporary = tempfile.mkstemp(dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)


def workspace_archive(root: Path) -> bytes:
    """Return a deterministic tar archive of a workspace."""
    if not root.is_dir():
        raise ValueError("workspace archive root must be a directory")
    paths = sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix())
    if len(paths) > MAX_ARCHIVE_MEMBERS:
        raise ValueError("workspace archive has too many members")
    total = 0
    for path in paths:
        if path.is_file() and not path.is_symlink():
            total += path.stat().st_size
        elif not (path.is_dir() or path.is_symlink()):
            raise ValueError("workspace archive contains an unsupported file")
    if total > MAX_EXTRACTED_BYTES:
        raise ValueError("workspace archive exceeds extracted size limit")
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for path in paths:
            relative = path.relative_to(root).as_posix()
            info = archive.gettarinfo(str(path), relative)
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mtime = 0
            if info.isfile():
                with path.open("rb") as stream:
                    archive.addfile(info, stream)
            else:
                archive.addfile(info)
    data = output.getvalue()
    if len(data) > MAX_ARCHIVE_BYTES:
        raise ValueError("workspace archive exceeds transfer size limit")
    return data


def _validated_workspace_members(  # noqa: C901 - one ordered archive-safety gate is easier to audit
    archive: tarfile.TarFile,
    *,
    allow_links: bool,
    forbidden_roots: frozenset[str],
) -> list[tarfile.TarInfo]:
    """Return members only after one ordered archive-safety gate passes."""
    members = archive.getmembers()
    if len(members) > MAX_ARCHIVE_MEMBERS:
        raise ValueError("workspace archive has too many members")
    seen: set[str] = set()
    extracted = 0
    for member in members:
        name = PurePosixPath(member.name)
        if name.is_absolute() or ".." in name.parts:
            raise ValueError(f"unsafe archive member: {member.name!r}")
        normalized = name.as_posix()
        if normalized in seen:
            raise ValueError(f"duplicate archive member: {member.name!r}")
        seen.add(normalized)
        if name.parts and name.parts[0] in forbidden_roots:
            raise ValueError(f"forbidden archive member: {member.name!r}")
        if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
            raise ValueError(f"unsupported archive member: {member.name!r}")
        if member.isfile():
            extracted += member.size
            if extracted > MAX_EXTRACTED_BYTES:
                raise ValueError("workspace archive exceeds extracted size limit")
        if member.issym() or member.islnk():
            if not allow_links:
                raise ValueError(f"archive links are not permitted: {member.name!r}")
            target = PurePosixPath(member.linkname)
            resolved = target if member.islnk() else name.parent / target
            if target.is_absolute() or ".." in resolved.parts:
                raise ValueError(f"unsafe archive link: {member.name!r}")
    return members


def validate_workspace_archive(
    data: bytes,
    *,
    allow_links: bool = True,
    forbidden_roots: frozenset[str] = frozenset(),
) -> None:
    """Validate one bounded archive without creating a destination or extracting it."""
    if type(data) is not bytes:
        raise TypeError("workspace archive must be exact bytes")
    if len(data) > MAX_ARCHIVE_BYTES:
        raise ValueError("workspace archive exceeds transfer size limit")
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
            _validated_workspace_members(
                archive,
                allow_links=allow_links,
                forbidden_roots=frozenset(forbidden_roots),
            )
    except tarfile.TarError:
        raise ValueError("workspace archive is malformed") from None


def extract_workspace_archive(data: bytes, destination: Path) -> None:
    """Securely extract a tar without permitting archive-root escape or special files."""
    if type(data) is not bytes:
        raise TypeError("workspace archive must be exact bytes")
    if len(data) > MAX_ARCHIVE_BYTES:
        raise ValueError("workspace archive exceeds transfer size limit")
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
        members = _validated_workspace_members(
            archive,
            allow_links=True,
            forbidden_roots=frozenset(),
        )
        archive.extractall(destination, members, filter="data")
