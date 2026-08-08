"""Concrete Hands workspace adapter over the public Motus execution contract.

The adapter is the only place a version-1 Hands call crosses into a territory.
It uses exactly the supported ``EnvironmentProvider``/``ExecutionAttachment``
surface, fences every command result to the exact lease provenance it was
created for, stages writes outside every final target, and returns only
bounded digests and truncated text — never raw provider state, sessions,
credentials, or unbounded output.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from threading import RLock

from petrus.agenticus.hands.gateway import ShellOutcome, StagedWrite, TestOutcome
from petrus.motus.execution import Command, CommandResult, EnvironmentProvider, ExecutionAttachment

STAGE_DIRECTORY = ".petrus-hands-stage"
MAX_READ_BYTES = 4096
MAX_SEARCH_MATCHES = 16
MAX_SEARCH_MATCH_CHARS = 256
MAX_STREAM_BYTES = 2048
_COMMAND_OUTPUT_LIMIT = 65536


class WorkspaceAdapterError(RuntimeError):
    """A territory operation failed; the gateway renders it as ``provider``."""


def _bounded_text(data: bytes, limit: int) -> tuple[str, bool]:
    truncated = len(data) > limit
    text = data[:limit].decode(errors="replace")
    # Replacement characters may occupy more UTF-8 bytes than the invalid or
    # partial input they replace. Preserve the public encoded-byte bound.
    while len(text.encode()) > limit:
        text = text[:-1]
        truncated = True
    return text, truncated


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class MotusWorkspaceAdapter:
    """The gateway's Hands adapter for one exact Motus execution attachment.

    Writes stage under :data:`STAGE_DIRECTORY`, outside every final target,
    and reach a target only through :meth:`commit_write`. The adapter keeps
    the authoritative registry of outstanding stage tokens, so settlement can
    prove every stage was removed. Commands run with the empty default
    environment; no credential-shaped value ever enters the territory.
    """

    def __init__(
        self,
        provider: EnvironmentProvider,
        attachment: ExecutionAttachment,
        *,
        test_command: tuple[str, ...],
        command_timeout: float = 60.0,
    ) -> None:
        if not isinstance(attachment, ExecutionAttachment):
            raise TypeError("workspace adapter attachment must be ExecutionAttachment")
        command = tuple(test_command)
        if not command or any(not isinstance(part, str) or not part for part in command):
            raise ValueError("workspace adapter test_command must be a non-empty tuple of non-empty strings")
        if (
            isinstance(command_timeout, bool)
            or not isinstance(command_timeout, int | float)
            or not math.isfinite(command_timeout)
            or command_timeout <= 0
        ):
            raise ValueError("workspace adapter command_timeout must be a positive finite number")
        self._provider = provider
        self._attachment = attachment
        self._lease_identity = attachment.lease.identity
        self._test_command = command
        self._timeout = float(command_timeout)
        self._stages: dict[str, str] = {}
        self._lock = RLock()

    def read(self, path: str) -> str:
        result = self._run(("/bin/sh", "-c", 'cat -- "$0"', path))
        if result.returncode != 0:
            raise WorkspaceAdapterError("workspace read failed")
        content, _ = _bounded_text(result.stdout, MAX_READ_BYTES)
        return content

    def search(self, query: str, path: str) -> tuple[str, ...]:
        result = self._run(("/bin/sh", "-c", 'grep -r -n -e "$0" -- "$1"', query, path))
        if result.returncode == 1:
            return ()
        if result.returncode != 0:
            raise WorkspaceAdapterError("workspace search failed")
        text, _ = _bounded_text(result.stdout, _COMMAND_OUTPUT_LIMIT)
        lines = [line[:MAX_SEARCH_MATCH_CHARS] for line in text.splitlines() if line]
        return tuple(lines[:MAX_SEARCH_MATCHES])

    def shell(self, argv: tuple[str, ...], cwd: str) -> ShellOutcome:
        result = self._run(tuple(argv), cwd=cwd)
        stdout, stdout_truncated = _bounded_text(result.stdout, MAX_STREAM_BYTES)
        stderr, stderr_truncated = _bounded_text(result.stderr, MAX_STREAM_BYTES)
        return ShellOutcome(
            returncode=result.returncode,
            stdout=stdout,
            stderr=stderr,
            truncated=result.output_truncated or stdout_truncated or stderr_truncated,
        )

    def stage_write(self, call_id: str, path: str, content: str) -> StagedWrite:
        name = _digest(call_id.encode())[:32]
        result = self._run(
            (
                "/bin/sh",
                "-c",
                'mkdir -p -- "$0" && printf %s "$2" > "$0/$1"',
                STAGE_DIRECTORY,
                name,
                content,
            )
        )
        if result.returncode != 0:
            raise WorkspaceAdapterError("workspace stage failed")
        staged = StagedWrite(call_id=call_id, path=path, digest=_digest(content.encode()))
        with self._lock:
            self._stages[name] = staged.path
        return staged

    def commit_write(self, staged: StagedWrite) -> str:
        name = self._stage_name(staged)
        result = self._run(
            (
                "/bin/sh",
                "-c",
                'parent=$(dirname -- "$2") && mkdir -p -- "$parent" && mv -f -- "$0/$1" "$2"',
                STAGE_DIRECTORY,
                name,
                staged.path,
            )
        )
        if result.returncode != 0:
            raise WorkspaceAdapterError("workspace commit failed")
        with self._lock:
            self._stages.pop(name, None)
        return staged.digest

    def discard_write(self, staged: StagedWrite) -> None:
        name = self._stage_name(staged)
        result = self._run(("/bin/sh", "-c", 'rm -f -- "$0/$1"', STAGE_DIRECTORY, name))
        with self._lock:
            self._stages.pop(name, None)
        if result.returncode != 0:
            raise WorkspaceAdapterError("workspace stage discard failed")

    def run_test(self) -> TestOutcome:
        result = self._run(self._test_command)
        return TestOutcome(
            passed=result.returncode == 0,
            evidence_digest=_digest(result.stdout + result.stderr),
        )

    def discard_all_stages(self) -> int:
        result = self._run(("/bin/sh", "-c", 'rm -rf -- "$0"', STAGE_DIRECTORY))
        if result.returncode != 0:
            raise WorkspaceAdapterError("workspace stage cleanup failed")
        with self._lock:
            removed = len(self._stages)
            self._stages.clear()
        return removed

    def outstanding_stages(self) -> int:
        """The authoritative count of stage tokens not yet committed or discarded."""

        with self._lock:
            return len(self._stages)

    def _stage_name(self, staged: StagedWrite) -> str:
        name = _digest(staged.call_id.encode())[:32]
        with self._lock:
            if self._stages.get(name) != staged.path:
                raise WorkspaceAdapterError("stage token is not registered with this adapter")
        return name

    def _run(self, argv: tuple[str, ...], cwd: str = ".") -> CommandResult:
        try:
            command = Command(argv, cwd=Path(cwd), timeout=self._timeout, output_limit=_COMMAND_OUTPUT_LIMIT)
            result = self._provider.execute(self._attachment, command)
        except WorkspaceAdapterError:
            raise
        except Exception as error:
            raise WorkspaceAdapterError("territory command failed") from error
        if result.provenance.identity != self._lease_identity:
            raise WorkspaceAdapterError("command result provenance does not match the bound lease")
        if result.timed_out or result.superseded:
            raise WorkspaceAdapterError("territory command did not complete currently")
        return result


__all__ = [
    "MAX_READ_BYTES",
    "MAX_SEARCH_MATCHES",
    "MAX_SEARCH_MATCH_CHARS",
    "MAX_STREAM_BYTES",
    "STAGE_DIRECTORY",
    "MotusWorkspaceAdapter",
    "WorkspaceAdapterError",
]
