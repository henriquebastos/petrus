"""Disposable event-sourced prototype for generation-scoped Activity work."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType


@dataclass(frozen=True, order=True)
class ActivityScope:
    """One generation of a named replaceable-work scope."""

    name: str
    generation: int

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("an Activity scope requires a name")
        if self.generation < 1:
            raise ValueError("an Activity scope generation must be positive")


class ActivityPhase(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class ScopedToken:
    identity: str
    scope: ActivityScope
    value: object


@dataclass(frozen=True)
class ActivityView:
    identity: str
    scope: ActivityScope
    phase: ActivityPhase
    result: object = None


@dataclass(frozen=True)
class ActivityCancellation:
    activity: str
    prior: ActivityPhase


@dataclass(frozen=True)
class ScopeOpened:
    scope: ActivityScope
    instant: int = 0


@dataclass(frozen=True)
class ScopedTokenQueued:
    token: ScopedToken
    instant: int = 0


@dataclass(frozen=True)
class ScopedActivityRequested:
    activity: str
    scope: ActivityScope
    instant: int = 0


@dataclass(frozen=True)
class ScopedActivityStarted:
    activity: str
    instant: int = 0


@dataclass(frozen=True)
class ScopedActivityCompleted:
    activity: str
    scope: ActivityScope
    result: object
    outputs: tuple[ScopedToken, ...] = ()
    instant: int = 0


@dataclass(frozen=True)
class ScopeClosed:
    scope: ActivityScope
    dropped_tokens: tuple[str, ...] = ()
    cancelled_activities: tuple[str, ...] = ()
    instant: int = 0


@dataclass(frozen=True)
class ScopeReset:
    closed: ActivityScope
    opened: ActivityScope
    dropped_tokens: tuple[str, ...] = ()
    cancelled_activities: tuple[str, ...] = ()
    instant: int = 0


@dataclass(frozen=True)
class ActivityCompletionQuarantined:
    activity: str
    scope: ActivityScope
    result: object
    instant: int = 0


type ScopeEvent = (
    ScopeOpened
    | ScopedTokenQueued
    | ScopedActivityRequested
    | ScopedActivityStarted
    | ScopedActivityCompleted
    | ScopeClosed
    | ScopeReset
    | ActivityCompletionQuarantined
)


@dataclass(frozen=True)
class CloseOutcome:
    scope: ActivityScope
    dropped_tokens: tuple[str, ...]
    cancelled: tuple[ActivityCancellation, ...]


@dataclass(frozen=True)
class ResetOutcome:
    closed: ActivityScope
    opened: ActivityScope
    dropped_tokens: tuple[str, ...]
    cancelled: tuple[ActivityCancellation, ...]


class ActivityScopeRuntime:
    """A single-writer semantic spike; append order is the race arbiter."""

    def __init__(self) -> None:
        self._history: list[ScopeEvent] = []
        self._active: dict[str, ActivityScope] = {}
        self._generations: dict[str, int] = {}
        self._queued: list[ScopedToken] = []
        self._activities: dict[str, ActivityView] = {}
        self._quarantined: dict[str, object] = {}

    @classmethod
    def resume(cls, records: tuple[ScopeEvent, ...]) -> ActivityScopeRuntime:
        runtime = cls()
        for event in records:
            runtime._apply(event)
            runtime._history.append(event)
        return runtime

    @property
    def records(self) -> tuple[ScopeEvent, ...]:
        return tuple(self._history)

    @property
    def queued(self) -> tuple[ScopedToken, ...]:
        return tuple(self._queued)

    @property
    def quarantined(self):
        return MappingProxyType(dict(self._quarantined))

    def active(self, name: str) -> ActivityScope | None:
        return self._active.get(name)

    def activity(self, identity: str) -> ActivityView:
        return self._activities[identity]

    def open(self, name: str, *, instant: int = 0) -> ActivityScope:
        if name in self._active:
            raise ValueError(f"Activity scope {name!r} is already open")
        scope = ActivityScope(name, self._generations.get(name, 0) + 1)
        self._commit(ScopeOpened(scope, instant))
        return scope

    def queue(self, scope: ActivityScope, identity: str, value: object, *, instant: int = 0) -> ScopedToken:
        self._require_active(scope)
        if not identity or any(token.identity == identity for token in self._queued):
            raise ValueError(f"queued scoped-token identity {identity!r} is empty or already queued")
        token = ScopedToken(identity, scope, value)
        self._commit(ScopedTokenQueued(token, instant))
        return token

    def request(self, scope: ActivityScope, activity: str, *, instant: int = 0) -> None:
        self._require_active(scope)
        if not activity or activity in self._activities:
            raise ValueError(f"scoped Activity identity {activity!r} is empty or already used")
        self._commit(ScopedActivityRequested(activity, scope, instant))

    def start(self, activity: str, *, instant: int = 0) -> None:
        current = self.activity(activity)
        if current.phase is not ActivityPhase.PENDING:
            raise ValueError(f"Activity {activity!r} is {current.phase}, not pending")
        self._commit(ScopedActivityStarted(activity, instant))

    def close(self, scope: ActivityScope, *, instant: int = 0) -> CloseOutcome:
        self._require_active(scope)
        dropped, cancellations = self._closure_effects(scope)
        event = ScopeClosed(
            scope,
            dropped_tokens=dropped,
            cancelled_activities=tuple(item.activity for item in cancellations),
            instant=instant,
        )
        self._commit(event)
        return CloseOutcome(scope, dropped, cancellations)

    def reset(self, scope: ActivityScope, *, instant: int = 0) -> ResetOutcome:
        self._require_active(scope)
        dropped, cancellations = self._closure_effects(scope)
        opened = ActivityScope(scope.name, scope.generation + 1)
        event = ScopeReset(
            closed=scope,
            opened=opened,
            dropped_tokens=dropped,
            cancelled_activities=tuple(item.activity for item in cancellations),
            instant=instant,
        )
        self._commit(event)
        return ResetOutcome(scope, opened, dropped, cancellations)

    def complete(
        self,
        activity: str,
        result: object,
        *,
        outputs: tuple[tuple[str, object], ...] = (),
        instant: int = 0,
    ) -> str:
        current = self.activity(activity)
        if current.phase is ActivityPhase.COMPLETED:
            if current.result == result:
                return "acknowledged"
            raise ValueError(f"Activity {activity!r} already completed with a different result")
        if current.phase is ActivityPhase.CANCELLED:
            if activity in self._quarantined:
                if self._quarantined[activity] == result:
                    return "acknowledged-quarantine"
                raise ValueError(f"Activity {activity!r} has a different quarantined late result")
            self._commit(ActivityCompletionQuarantined(activity, current.scope, result, instant))
            return "quarantined"
        self._require_active(current.scope)
        known = {token.identity for token in self._queued}
        produced = tuple(ScopedToken(identity, current.scope, value) for identity, value in outputs)
        if any(not token.identity or token.identity in known for token in produced) or len(
            {token.identity for token in produced}
        ) != len(produced):
            raise ValueError("Activity output token identities must be non-empty and unique in the queue")
        self._commit(ScopedActivityCompleted(activity, current.scope, result, produced, instant))
        return "accepted"

    def _closure_effects(self, scope: ActivityScope) -> tuple[tuple[str, ...], tuple[ActivityCancellation, ...]]:
        dropped = tuple(token.identity for token in self._queued if token.scope == scope)
        cancelled = tuple(
            ActivityCancellation(activity.identity, activity.phase)
            for activity in self._activities.values()
            if activity.scope == scope and activity.phase in (ActivityPhase.PENDING, ActivityPhase.RUNNING)
        )
        return dropped, cancelled

    def _require_active(self, scope: ActivityScope) -> None:
        if self._active.get(scope.name) != scope:
            raise ValueError(f"Activity scope {scope.name!r} generation {scope.generation} is not active")

    def _commit(self, event: ScopeEvent) -> None:
        self._history.append(event)
        self._apply(event)

    def _apply(self, event: ScopeEvent) -> None:  # noqa: C901 - closed experimental event fold
        match event:
            case ScopeOpened(scope=scope):
                if scope.name in self._active or scope.generation != self._generations.get(scope.name, 0) + 1:
                    raise ValueError(f"replay divergence opening Activity scope {scope}")
                self._active[scope.name] = scope
                self._generations[scope.name] = scope.generation
            case ScopedTokenQueued(token=token):
                self._require_active(token.scope)
                if any(queued.identity == token.identity for queued in self._queued):
                    raise ValueError(f"replay divergence queuing duplicate scoped-token {token.identity!r}")
                self._queued.append(token)
            case ScopedActivityRequested(activity=activity, scope=scope):
                self._require_active(scope)
                if activity in self._activities:
                    raise ValueError(f"replay divergence requesting duplicate Activity {activity!r}")
                self._activities[activity] = ActivityView(activity, scope, ActivityPhase.PENDING)
            case ScopedActivityStarted(activity=activity):
                current = self.activity(activity)
                if current.phase is not ActivityPhase.PENDING:
                    raise ValueError(f"replay divergence starting {current.phase} Activity {activity!r}")
                self._activities[activity] = ActivityView(activity, current.scope, ActivityPhase.RUNNING)
            case ScopedActivityCompleted(activity=activity, scope=scope, result=result, outputs=outputs):
                current = self.activity(activity)
                if current.scope != scope or current.phase not in (ActivityPhase.PENDING, ActivityPhase.RUNNING):
                    raise ValueError(f"replay divergence completing Activity {activity!r}")
                self._require_active(scope)
                self._activities[activity] = ActivityView(activity, scope, ActivityPhase.COMPLETED, result)
                self._queued.extend(outputs)
            case ScopeClosed(scope=scope, dropped_tokens=dropped, cancelled_activities=cancelled):
                self._apply_closure(scope, dropped, cancelled)
                del self._active[scope.name]
            case ScopeReset(
                closed=closed,
                opened=opened,
                dropped_tokens=dropped,
                cancelled_activities=cancelled,
            ):
                if opened != ActivityScope(closed.name, closed.generation + 1):
                    raise ValueError(f"replay divergence resetting {closed} to {opened}")
                self._apply_closure(closed, dropped, cancelled)
                self._active[closed.name] = opened
                self._generations[closed.name] = opened.generation
            case ActivityCompletionQuarantined(activity=activity, scope=scope, result=result):
                current = self.activity(activity)
                if (
                    current.scope != scope
                    or current.phase is not ActivityPhase.CANCELLED
                    or activity in self._quarantined
                ):
                    raise ValueError(f"replay divergence quarantining Activity {activity!r}")
                self._quarantined[activity] = result

    def _apply_closure(self, scope: ActivityScope, dropped: tuple[str, ...], cancelled: tuple[str, ...]) -> None:
        self._require_active(scope)
        expected_dropped, expected_cancellations = self._closure_effects(scope)
        expected_cancelled = tuple(item.activity for item in expected_cancellations)
        if dropped != expected_dropped or cancelled != expected_cancelled:
            raise ValueError(f"replay divergence closing Activity scope {scope}: recorded effects do not match state")
        dropped_set = set(dropped)
        self._queued = [token for token in self._queued if not (token.scope == scope and token.identity in dropped_set)]
        for identity in cancelled:
            self._activities[identity] = ActivityView(identity, scope, ActivityPhase.CANCELLED)


__all__ = [
    "ActivityCompletionQuarantined",
    "ActivityPhase",
    "ActivityScope",
    "ActivityScopeRuntime",
    "CloseOutcome",
    "ResetOutcome",
    "ScopeClosed",
    "ScopeReset",
    "ScopedToken",
]
