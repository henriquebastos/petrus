"""Provider-neutral capability policy and immutable attachment-bound grants.

A grant is the only source of tool authority. Every grant is bound to one
exact attachment identity and epoch, carries an exact capability set, a finite
call budget, and a finite deadline, and can never be inherited after the
attachment it names is replaced.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from threading import RLock

from petrus.agenticus.hands.contract import (
    MAX_ARGV_PART_CHARS,
    MAX_ARGV_PARTS,
    MAX_PATH_CHARS,
    ToolMethod,
)

_MAX_IDENTITY_BYTES = 256


def _identity(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value.encode()) > _MAX_IDENTITY_BYTES
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError(f"{name} must be a bounded non-empty identity string")
    return value


def _positive_integer(value: object, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _finite_deadline(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def _writable_path(value: object) -> str:
    path = _identity(value, "grant writable path")
    parts = path.split("/")
    if (
        len(path) > MAX_PATH_CHARS
        or path.startswith("/")
        or "\\" in path
        or any(part in ("", ".", "..") for part in parts)
    ):
        raise ValueError("grant writable path must be a bounded normalized relative path")
    return path


def _writable_root(value: object) -> str:
    if value == ".":
        return "."
    return _writable_path(value)


def _argv_part(part: object) -> str:
    if (
        not isinstance(part, str)
        or not part
        or len(part) > MAX_ARGV_PART_CHARS
        or "\\" in part
        or any(ord(character) < 32 or ord(character) == 127 for character in part)
        or any(segment in (".", "..") for segment in part.split("/"))
    ):
        raise ValueError("grant argv command must be 1..4 bounded non-empty parts")
    return part


def _argv_allowlist(value: Iterable[object]) -> frozenset[tuple[str, ...]]:
    commands: list[tuple[str, ...]] = []
    for command in tuple(value):
        if isinstance(command, str) or not isinstance(command, Iterable):
            raise TypeError("grant argv allowlist must contain argv tuples")
        parts = tuple(_argv_part(part) for part in command)
        if not parts or len(parts) > MAX_ARGV_PARTS:
            raise ValueError("grant argv command must be 1..4 bounded non-empty parts")
        commands.append(parts)
    return frozenset(commands)


@dataclass(frozen=True)
class CapabilityGrant:
    """One immutable, finite, deadline-bounded authority for one attachment epoch."""

    attachment_id: str
    attachment_epoch: int
    grant_epoch: int
    capabilities: frozenset[ToolMethod]
    writable_paths: frozenset[str]
    allowed_argv: frozenset[tuple[str, ...]]
    deadline: float
    max_calls: int
    writable_roots: frozenset[str] = frozenset()
    denied_writable_roots: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(self, "attachment_id", _identity(self.attachment_id, "grant attachment_id"))
        _positive_integer(self.attachment_epoch, "grant attachment_epoch")
        _positive_integer(self.grant_epoch, "grant grant_epoch")
        capabilities = frozenset(self.capabilities)
        if any(not isinstance(capability, ToolMethod) for capability in capabilities):
            raise TypeError("grant capabilities must be exact ToolMethod values")
        object.__setattr__(self, "capabilities", capabilities)
        object.__setattr__(self, "writable_paths", frozenset(_writable_path(path) for path in self.writable_paths))
        object.__setattr__(self, "allowed_argv", _argv_allowlist(self.allowed_argv))
        object.__setattr__(self, "deadline", _finite_deadline(self.deadline, "grant deadline"))
        _positive_integer(self.max_calls, "grant max_calls")
        object.__setattr__(self, "writable_roots", frozenset(_writable_root(path) for path in self.writable_roots))
        object.__setattr__(
            self,
            "denied_writable_roots",
            frozenset(_writable_root(path) for path in self.denied_writable_roots),
        )

    def permits(self, method: ToolMethod) -> bool:
        return method in self.capabilities

    def permits_write_path(self, path: str) -> bool:
        """Whether one normalized path is inside this grant's exact write scope."""
        if any(root == "." or path == root or path.startswith(f"{root}/") for root in self.denied_writable_roots):
            return False
        return path in self.writable_paths or any(
            root == "." or path == root or path.startswith(f"{root}/") for root in self.writable_roots
        )


class GrantLedgerError(ValueError):
    """A grant operation named a stale attachment or violated ledger order."""


class GrantBudgetExhausted(GrantLedgerError):
    """The exact current grant has spent its finite call budget."""


class GrantLedger:
    """Attachment-scoped grant custody with strictly increasing grant epochs.

    The ledger holds at most one current grant. Opening a grant for a new
    attachment epoch permanently retires every grant of prior epochs, so no
    authority survives attachment replacement.
    """

    def __init__(self, attachment_id: str, attachment_epoch: int) -> None:
        self._attachment_id = _identity(attachment_id, "ledger attachment_id")
        self._attachment_epoch = _positive_integer(attachment_epoch, "ledger attachment_epoch")
        self._grant_epoch = 0
        self._current: CapabilityGrant | None = None
        self._consumed = 0
        self._lock = RLock()

    @property
    def attachment_id(self) -> str:
        return self._attachment_id

    @property
    def attachment_epoch(self) -> int:
        return self._attachment_epoch

    def current(self) -> CapabilityGrant | None:
        with self._lock:
            return self._current

    def open(
        self,
        capabilities: Iterable[ToolMethod],
        *,
        writable_paths: Iterable[str] = (),
        writable_roots: Iterable[str] = (),
        denied_writable_roots: Iterable[str] = (),
        allowed_argv: Iterable[tuple[str, ...]] = (),
        deadline: float,
        max_calls: int,
    ) -> CapabilityGrant:
        """Issue the next grant epoch, replacing any current grant."""

        with self._lock:
            grant_epoch = self._grant_epoch + 1
            grant = CapabilityGrant(
                attachment_id=self._attachment_id,
                attachment_epoch=self._attachment_epoch,
                grant_epoch=grant_epoch,
                capabilities=frozenset(capabilities),
                writable_paths=frozenset(writable_paths),
                allowed_argv=frozenset(allowed_argv),
                deadline=deadline,
                max_calls=max_calls,
                writable_roots=frozenset(writable_roots),
                denied_writable_roots=frozenset(denied_writable_roots),
            )
            self._grant_epoch = grant_epoch
            self._current = grant
            self._consumed = 0
            return grant

    def close(self) -> None:
        """Retire the current grant without opening a successor."""

        with self._lock:
            self._current = None
            self._consumed = 0

    def consume(self, grant_epoch: int) -> CapabilityGrant:
        """Spend one call of the exact current grant or refuse fail-closed.

        The gateway consumes only when a call is admitted past its prechecks,
        so rejected requests never spend grant budget.
        """

        with self._lock:
            grant = self._current
            if grant is None or grant.grant_epoch != grant_epoch:
                raise GrantLedgerError("grant epoch is not current for this attachment")
            if self._consumed >= grant.max_calls:
                raise GrantBudgetExhausted("grant call budget is exhausted")
            self._consumed += 1
            return grant


__all__ = ["CapabilityGrant", "GrantBudgetExhausted", "GrantLedger", "GrantLedgerError"]
