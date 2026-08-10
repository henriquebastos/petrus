"""Petri-agnostic Activity custody and Dispatch implementations.

Absurd is an explicit optional implementation at :mod:`petrus.motus.dispatch.absurd`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Protocol, runtime_checkable

from petrus.motus.activity import (
    Activity,
    ActivityError,
    ActivityFailure,
    ActivityInvocation,
    _OMITTED,
    snapshot_heartbeat_details,
)


@dataclass(frozen=True)
class ActivityAttempt:
    """A detached, provider-neutral fenced claim on one Activity invocation."""

    attempt_id: str
    epoch: str
    claimant: str
    queue: str
    invocation: ActivityInvocation
    latest_details: object = None
    instance: str | None = None

    def __post_init__(self) -> None:
        if self.instance is not None and (not isinstance(self.instance, str) or not self.instance):
            raise ValueError("Activity Attempt instance must be a non-empty string or None")
        object.__setattr__(self, "latest_details", snapshot_heartbeat_details(self.latest_details))


@runtime_checkable
class WorkerDispatch(Protocol):
    """The provider-neutral synchronous custody surface consumed by ``Worker``."""

    def claim(self) -> ActivityAttempt | None: ...

    def heartbeat(self, attempt: ActivityAttempt, *, details: object = _OMITTED) -> object: ...

    def complete(self, attempt: ActivityAttempt, result: object) -> None: ...

    def fail(self, attempt: ActivityAttempt, error: str | Exception | ActivityFailure) -> None: ...

    def wait(self, timeout: float) -> bool: ...

    def close(self) -> None: ...


# ActivityAttempt must exist before the provider imports its neutral value.
from petrus.motus.dispatch.local import LocalDispatch, LocalWorkerDispatch  # noqa: E402


@dataclass(frozen=True)
class InlineDispatch:
    """Execute named Activities inline and buffer dispatched terminal outcomes."""

    activities: Mapping[str, Activity]
    _completed: list[tuple[int, object]] = field(default_factory=list, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "activities", MappingProxyType(dict(self.activities)))

    def __call__(self, invocation: ActivityInvocation) -> object:
        if invocation.activity not in self.activities:
            raise ValueError(
                f"no activity implementation for {invocation.activity!r}: this InlineDispatch implements "
                f"{sorted(self.activities)}"
            )
        implementation = self.activities[invocation.activity]
        started = __import__("time").monotonic()
        for attempt in range(1, invocation.policy.attempts + 1):
            context = _InlineActivityExecutionContext(
                attempt_id=f"inline-{attempt}",
                epoch=str(attempt),
                claimant="inline",
                latest_details=None,
                instance=None,
            )
            try:
                return implementation(invocation, context=context)
            except Exception as error:
                failure = _classify_inline_failure(error)
                elapsed = __import__("time").monotonic() - started
                expired = (
                    invocation.policy.schedule_to_close is not None and elapsed >= invocation.policy.schedule_to_close
                )
                if not failure.retryable or expired or attempt == invocation.policy.attempts:
                    raise

    def dispatch(self, occurrence: int, invocation: ActivityInvocation) -> None:
        try:
            self._completed.append((occurrence, self(invocation)))
        except Exception as error:
            self._completed.append((occurrence, _classify_inline_failure(error)))

    def collect(self) -> tuple[tuple[int, object], ...]:
        drained = tuple(self._completed)
        self._completed.clear()
        return drained


def _classify_inline_failure(error: Exception) -> ActivityFailure:
    if isinstance(error, ActivityError):
        return error.failure
    return ActivityFailure(str(error) or type(error).__name__, kind=type(error).__name__, retryable=True)


@dataclass
class _InlineActivityExecutionContext:
    attempt_id: str
    epoch: str
    claimant: str
    latest_details: object
    instance: str | None

    def heartbeat(self, *, details: object = _OMITTED) -> object:
        if details is not _OMITTED:
            self.latest_details = snapshot_heartbeat_details(details)
        return self.latest_details


@runtime_checkable
class Dispatch(Protocol):
    """Asynchronous activity custody and completion collection contract."""

    def dispatch(self, occurrence: int, invocation: ActivityInvocation) -> None: ...

    def collect(self) -> Sequence[tuple[int, object]]: ...


class InMemoryDispatch:
    """Deterministic in-memory Dispatch whose pending work is pumped explicitly."""

    def __init__(self) -> None:
        self._pending: dict[int, ActivityInvocation] = {}
        self._completed: list[tuple[int, object]] = []

    @property
    def pending(self) -> Mapping[int, ActivityInvocation]:
        return MappingProxyType(dict(self._pending))

    def dispatch(self, occurrence: int, invocation: ActivityInvocation) -> None:
        if occurrence in self._pending:
            raise ValueError(f"occurrence {occurrence} is already pending in this pool: one dispatch per occurrence")
        self._pending[occurrence] = invocation

    def collect(self) -> tuple[tuple[int, object], ...]:
        drained = tuple(self._completed)
        self._completed.clear()
        return drained

    def complete(self, occurrence: int, result: object) -> None:
        self._take(occurrence)
        self._completed.append((occurrence, result))

    def fail(self, occurrence: int, error: str) -> None:
        self._take(occurrence)
        self._completed.append((occurrence, ActivityFailure(error)))

    def _take(self, occurrence: int) -> None:
        if occurrence not in self._pending:
            raise ValueError(f"occurrence {occurrence} is not pending in this pool: dispatch it before completing it")
        del self._pending[occurrence]


__all__ = [
    "ActivityAttempt",
    "Dispatch",
    "InMemoryDispatch",
    "InlineDispatch",
    "LocalDispatch",
    "LocalWorkerDispatch",
    "WorkerDispatch",
]
