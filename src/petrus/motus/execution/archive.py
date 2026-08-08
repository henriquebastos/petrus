"""Supported bounded workspace-archive transfer helpers."""

from __future__ import annotations

from pathlib import Path

from petrus.motus._execution.artifacts import (
    MAX_ARCHIVE_BYTES as MAX_WORKSPACE_ARCHIVE_BYTES,
)
from petrus.motus._execution.artifacts import extract_workspace_archive as _extract_workspace_archive
from petrus.motus._execution.artifacts import validate_workspace_archive as _validate_workspace_archive
from petrus.motus._execution.artifacts import workspace_archive as _workspace_archive


def workspace_archive(root: Path) -> bytes:
    """Return a deterministic bounded tar archive of one workspace."""

    return _workspace_archive(root)


def validate_workspace_archive(
    data: bytes,
    *,
    allow_links: bool = True,
    forbidden_roots: frozenset[str] = frozenset(),
) -> None:
    """Validate a bounded workspace archive without extracting it."""

    _validate_workspace_archive(data, allow_links=allow_links, forbidden_roots=forbidden_roots)


def extract_workspace_archive(data: bytes, destination: Path) -> None:
    """Extract a bounded workspace archive after traversal and file-type checks."""

    _extract_workspace_archive(data, destination)


__all__ = [
    "MAX_WORKSPACE_ARCHIVE_BYTES",
    "extract_workspace_archive",
    "validate_workspace_archive",
    "workspace_archive",
]
