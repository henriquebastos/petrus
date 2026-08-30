"""One provider-neutral live composition around exactly one durable Instance."""

from __future__ import annotations

from copy import deepcopy
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace

from petrus.engine._coordination import (
    AcceptDelivery,
    AcceptResult,
    Action,
    AdvanceTime,
    BeginCandidate,
    Clock,
    Coordinator,
    Delivery,
    DriveOutcome,
    DrivingPolicy,
    InFlightView,
    Sensor,
    SimulatedClock,
    Snapshot,
    Stop,
    Wait,
    choose_conservative,
    choose_throughput,
)
from petrus.motus.activity import ActivityDeclaration
from petrus.impetus.binding import ActivityHandler
from petrus.motus.dispatch import Dispatch
from petrus.impetus.history import FiringFailed, Record, ScopeReset
from petrus.impetus.history_store import HistoryStore
from petrus.impetus.observation import history_page as _history_page
from petrus.impetus.observation import net_document as _net_document
from petrus.impetus.observation import snapshot as _snapshot
from petrus.impetus.instance import (
    AcceptedDelivery,
    FiringOccurrence,
    FiringOutcome,
    Instance,
    PriorAcknowledgement,
    ScopeClosure,
    ScopedDeliveryAcknowledgement,
    Status,
    _canonical_accepted_delivery,
    firing_failure_text,
)
from petrus.impetus.petrinet import Instant, Marking, Net, NetPath, Token
from petrus.impetus.selection import SelectionPipeline, SelectionPolicy
from petrus.impetus.scope import LifecycleScope

_ENGINE_CONSTRUCTION = object()


def _nothing() -> None:
    """The empty hosting-resource operation for backend-owned compositions."""


@dataclass(frozen=True)
class _EngineResources:
    """Private provider wiring for one Engine's transaction and hosting fate."""

    commit: Callable[[], None] | None = None
    rollback: Callable[[], None] = _nothing
    release: Callable[[], None] = _nothing
    close: Callable[[], None] = _nothing
    ensure: Callable[[], None] = _nothing
    wait: Callable[[float], bool] | None = None


@dataclass(frozen=True)
class _ResolvedActivityHandler:
    """Freeze Engine-composed Activity timeout policy before Dispatch."""

    handler: ActivityHandler
    default_timeout: int
    declarations: Mapping[str, ActivityDeclaration]

    def prepare(self, binding):
        invocation = self.handler.prepare(binding)
        declaration = self.declarations.get(invocation.activity)
        timeout = (
            declaration.heartbeat_timeout
            if declaration is not None and declaration.heartbeat_timeout is not None
            else self.default_timeout
        )
        return replace(invocation, policy=replace(invocation.policy, heartbeat_timeout=timeout))

    def project(self, binding, result):
        return self.handler.project(binding, result)

    def project_failure(self, binding, failure):
        projector = getattr(self.handler, "project_failure", None)
        if projector is None:
            raise AttributeError("this ActivityHandler does not project failures")
        return projector(binding, failure)


class Engine:
    """The live motion-producing composition around one durable Instance.

    The ordinary ``create`` and ``load`` doors accept backend-owned History
    Stores whose writes are final when their methods return. First-party
    provider constructors use the private resource seam when a History Store
    joins a caller-held transaction or hosting requires a writer fence.

    Every writing-door exception poisons the complete composition. A provider
    may roll back and release its writer fence first; the coherent continuation
    is always a fresh ``load`` over committed History.
    """

    def __init__(
        self,
        net: Net | None = None,
        instance: str | None = None,
        *,
        history: HistoryStore | None = None,
        dispatch: Dispatch | None = None,
        create: bool | None = None,
        marking: Marking | None = None,
        at: Instant = 0,
        handlers=None,
        guards=None,
        filters=None,
        completions=None,
        policy: DrivingPolicy = choose_conservative,
        selection: SelectionPolicy = SelectionPipeline(),
        clock: Clock | None = None,
        sensor: Sensor | None = None,
        activities: Sequence[ActivityDeclaration] = (),
        default_heartbeat_timeout: int = 30,
        resources: _EngineResources = _EngineResources(),
        _construction=None,
    ):
        if _construction is not _ENGINE_CONSTRUCTION:
            raise TypeError("Engine cannot be constructed directly; use Engine.create() or Engine.load()")
        assert net is not None and instance is not None and history is not None and dispatch is not None
        self._resources = resources
        self._monitor = threading.RLock()
        self._write_thread: int | None = None
        self._resources_closed = False
        self._broken: str | None = None
        self._closed = False
        try:
            if (
                isinstance(default_heartbeat_timeout, bool)
                or not isinstance(default_heartbeat_timeout, int)
                or default_heartbeat_timeout <= 0
            ):
                raise ValueError("Engine default_heartbeat_timeout must be a positive integer")
            declarations = {declaration.name: declaration for declaration in activities}
            if len(declarations) != len(activities):
                raise ValueError("Engine Activity declarations require unique names")
            if handlers is not None:
                handlers = {
                    name: _ResolvedActivityHandler(handler, default_heartbeat_timeout, declarations)
                    if hasattr(handler, "prepare") and hasattr(handler, "project")
                    else handler
                    for name, handler in handlers.items()
                }
            if create:
                if len(history) != 0:
                    raise ValueError(f"cannot create Instance {instance!r}: canonical history already exists")
                self._instance = Instance(
                    net,
                    marking,
                    guards=guards,
                    handlers=handlers,
                    filters=filters,
                    completions=completions,
                    history=history,
                    instance_id=instance,
                    at=at,
                )
            else:
                if len(history) == 0:
                    raise ValueError(f"cannot load Instance {instance!r}: canonical history does not exist")
                self._instance = Instance.resume(
                    net, history, guards=guards, handlers=handlers, filters=filters, completions=completions
                )
                if self._instance.instance_id != instance:
                    raise ValueError(
                        f"cannot load Instance {instance!r}: canonical InstanceCreated identity is "
                        f"{self._instance.instance_id!r}; storage key and recorded identity must match exactly"
                    )
            self._clock = clock if clock is not None else SimulatedClock(at=self._instance.watermark)
            self._coordinator = Coordinator(
                self._instance,
                dispatch,
                policy=policy,
                selection=selection,
                clock=self._clock,
                sensor=sensor,
                commit=resources.commit,
            )
            self._committed()
        except BaseException:
            try:
                resources.rollback()
            finally:
                try:
                    resources.release()
                finally:
                    resources.close()
            self._closed = True
            raise

    @classmethod
    def create(
        cls,
        net: Net,
        instance: str,
        *,
        history: HistoryStore,
        dispatch: Dispatch,
        marking: Marking | None = None,
        at: Instant = 0,
        handlers=None,
        guards=None,
        filters=None,
        completions=None,
        policy: DrivingPolicy = choose_conservative,
        selection: SelectionPolicy = SelectionPipeline(),
        clock: Clock | None = None,
        sensor: Sensor | None = None,
        activities: Sequence[ActivityDeclaration] = (),
        default_heartbeat_timeout: int = 30,
    ) -> Engine:
        """Create and host a previously absent Instance over backend-owned writes."""
        return cls._open(
            net,
            instance,
            history=history,
            dispatch=dispatch,
            create=True,
            marking=marking,
            at=at,
            handlers=handlers,
            guards=guards,
            filters=filters,
            completions=completions,
            policy=policy,
            selection=selection,
            clock=clock,
            sensor=sensor,
            activities=activities,
            default_heartbeat_timeout=default_heartbeat_timeout,
        )

    @classmethod
    def load(
        cls,
        net: Net,
        instance: str,
        *,
        history: HistoryStore,
        dispatch: Dispatch,
        handlers=None,
        guards=None,
        filters=None,
        completions=None,
        policy: DrivingPolicy = choose_conservative,
        selection: SelectionPolicy = SelectionPipeline(),
        clock: Clock | None = None,
        sensor: Sensor | None = None,
        activities: Sequence[ActivityDeclaration] = (),
        default_heartbeat_timeout: int = 30,
    ) -> Engine:
        """Load and host an existing Instance over backend-owned writes."""
        return cls._open(
            net,
            instance,
            history=history,
            dispatch=dispatch,
            create=False,
            handlers=handlers,
            guards=guards,
            filters=filters,
            completions=completions,
            policy=policy,
            selection=selection,
            clock=clock,
            sensor=sensor,
            activities=activities,
            default_heartbeat_timeout=default_heartbeat_timeout,
        )

    @classmethod
    def _open(
        cls,
        net: Net,
        instance: str,
        *,
        history: HistoryStore,
        dispatch: Dispatch,
        create: bool,
        marking: Marking | None = None,
        at: Instant = 0,
        handlers=None,
        guards=None,
        filters=None,
        completions=None,
        policy: DrivingPolicy = choose_conservative,
        selection: SelectionPolicy = SelectionPipeline(),
        clock: Clock | None = None,
        sensor: Sensor | None = None,
        activities: Sequence[ActivityDeclaration] = (),
        default_heartbeat_timeout: int = 30,
        resources: _EngineResources = _EngineResources(),
    ) -> Engine:
        """First-party provider entry carrying private transaction/resource fate."""
        return cls(
            net,
            instance,
            history=history,
            dispatch=dispatch,
            create=create,
            marking=marking,
            at=at,
            handlers=handlers,
            guards=guards,
            filters=filters,
            completions=completions,
            policy=policy,
            selection=selection,
            clock=clock,
            sensor=sensor,
            activities=activities,
            default_heartbeat_timeout=default_heartbeat_timeout,
            resources=resources,
            _construction=_ENGINE_CONSTRUCTION,
        )

    @property
    def marking(self) -> Marking:
        """A detached value of the current marking."""
        return self._read(lambda: deepcopy(self._instance.marking), allow_reentry=True)

    @property
    def status(self) -> Status:
        """The Instance's derived status."""
        return self._read(lambda: self._instance.status, allow_reentry=True)

    @property
    def in_flight(self) -> tuple[FiringOccurrence, ...]:
        """Detached in-flight occurrence values in begin order."""
        return self._read(lambda: deepcopy(self._instance.in_flight), allow_reentry=True)

    @property
    def active_scopes(self) -> Mapping[str, LifecycleScope]:
        """The exact active lifecycle generation per name."""
        return self._read(lambda: self._instance.active_scopes, allow_reentry=True)

    @property
    def records(self) -> tuple[Record, ...]:
        """Detached canonical History record values, never an append-capable handle."""
        return self._read(lambda: deepcopy(self._instance.history.records), allow_reentry=True)

    def snapshot(self) -> dict[str, object]:
        """Return a coherent detached protocol-v1 view of definition and current state."""
        return self._read(lambda: _snapshot(self._instance, self._instance.history.records))

    def net_document(self) -> dict[str, object]:
        """Return one coherent observed portable Net document."""
        return self._read(lambda: _net_document(self._instance, self._instance.history.records))

    def history_page(self, after: int, limit: int) -> dict[str, object]:
        """Return a detached protocol-v1 page after an exclusive confirmed prefix."""
        return self._read(
            lambda: _history_page(self._instance.instance_id, self._instance.history.records, after, limit)
        )

    def advance(self) -> DriveOutcome:
        """Reconcile if first loaded, then apply at most one whole action and return the host's next posture."""
        return self._guarded(self._coordinator.drive)

    def wait(self, timeout: float) -> bool:
        """Wait for a provider wake hint or the bounded neutral polling interval."""
        waiter = self._read(lambda: self._resources.wait, allow_reentry=True)
        if waiter is not None:
            return waiter(timeout)
        time.sleep(timeout)
        return False

    def deliver(
        self,
        source: NetPath | str,
        tokens: Token | Sequence[Token],
        *,
        identity: str,
        scope: LifecycleScope | str | None = None,
    ) -> FiringOutcome | PriorAcknowledgement | ScopedDeliveryAcknowledgement:
        """Accept and complete one identified external delivery across two durable boundaries."""

        def door() -> FiringOutcome | PriorAcknowledgement | ScopedDeliveryAcknowledgement:
            accepted = self._accept_identified_delivery(source, tokens, identity, scope)
            if not isinstance(accepted, AcceptedDelivery):
                return accepted
            completed = self._complete_accepted_delivery(accepted)
            self._committed()
            return completed

        return self._guarded(door)

    def accept_delivery(
        self,
        source: NetPath | str,
        tokens: Token | Sequence[Token],
        *,
        identity: str,
        scope: LifecycleScope | str | None = None,
    ) -> AcceptedDelivery | PriorAcknowledgement | ScopedDeliveryAcknowledgement:
        """Durably accept and begin one identified source delivery without completing it."""

        def door() -> AcceptedDelivery | PriorAcknowledgement | ScopedDeliveryAcknowledgement:
            return self._accept_identified_delivery(source, tokens, identity, scope)

        return self._guarded(door)

    def _accept_identified_delivery(
        self,
        source: NetPath | str,
        tokens: Token | Sequence[Token],
        identity: str,
        scope: LifecycleScope | str | None,
    ) -> AcceptedDelivery | PriorAcknowledgement | ScopedDeliveryAcknowledgement:
        """Commit the shared identified-acceptance phase of both public delivery doors."""
        if identity is None:
            raise ValueError("delivery requires a stable delivery identity")
        before = len(self._instance.history)
        accepted = self._instance.accept_delivery(source, tokens, at=self._clock.now(), identity=identity, scope=scope)
        if len(self._instance.history) != before:
            self._committed()
        return accepted

    def complete_delivery(self, accepted: AcceptedDelivery) -> FiringOutcome:
        """Complete only the accepted unfinished pure source occurrence named by ``accepted``."""

        def door() -> FiringOutcome:
            completed = self._complete_accepted_delivery(accepted)
            self._committed()
            return completed

        return self._guarded(door)

    def _complete_accepted_delivery(self, accepted: AcceptedDelivery) -> FiringOutcome:
        """Complete one carrier and settle any recorded terminal failure through the provider."""
        accepted = _canonical_accepted_delivery(accepted)
        before = len(self._instance.history)
        try:
            return self._instance.complete_delivery(accepted, at=self._clock.now())
        except Exception:
            records = self._instance.history.records
            if (
                len(records) == before + 1
                and isinstance(records[-1], FiringFailed)
                and records[-1].occurrence == accepted.occurrence
            ):
                self._committed()
            raise

    def open_scope(self, name: str) -> LifecycleScope:
        """Open and commit the next lifecycle generation for ``name``."""

        def door() -> LifecycleScope:
            scope = self._instance.open_scope(name, at=self._clock.now())
            self._committed()
            return scope

        return self._guarded(door)

    def close_scope(self, scope: LifecycleScope) -> ScopeClosure:
        """Commit exact cleanup, then install recoverable Dispatch cancellation fences."""

        def door() -> ScopeClosure:
            self._require_scope_cancellation(scope)
            closure = self._instance.close_scope(scope, at=self._clock.now())
            history_position = len(self._instance.history)
            self._committed()  # canonical close is visible before any cancellation instruction
            self._coordinator.cancel(closure, history_position)
            self._committed()  # joined providers durably publish their operational fences
            return closure

        return self._guarded(door)

    def reset_scope(self, scope: LifecycleScope) -> LifecycleScope:
        """Atomically close ``scope`` and open its successor, then fence cancelled custody."""

        def door() -> LifecycleScope:
            self._require_scope_cancellation(scope)
            opened = self._instance.reset_scope(scope, at=self._clock.now())
            history_position = len(self._instance.history)
            record = self._instance.history.records[-1]
            assert isinstance(record, ScopeReset)
            closure = ScopeClosure(record.closed, record.discarded, record.cancelled)
            self._committed()  # reset commits whole before operational cancellation
            self._coordinator.cancel(closure, history_position)
            self._committed()
            return opened

        return self._guarded(door)

    def _require_scope_cancellation(self, scope: LifecycleScope) -> None:
        needs_cancellation = any(
            occurrence.scope == scope and occurrence.invocation is not None for occurrence in self._instance.in_flight
        )
        if needs_cancellation and not self._coordinator.supports_cancellation:
            raise TypeError(
                "cannot close lifecycle scope with in-flight Activities: this Dispatch does not implement "
                "the recoverable cancellation extension"
            )

    def seal(self, source: NetPath | str) -> None:
        """Close a source's default delivery registration and commit it."""

        def door() -> None:
            self._instance.seal(source, at=self._clock.now())
            self._committed()

        self._guarded(door)

    def close(self) -> None:
        """Release hosting resources without changing semantic Instance status."""
        with self._monitor:
            self._refuse_reentry()
            if self._closed:
                return
            self._closed = True
            self._close_resources()

    def _close_resources(self) -> None:
        if self._resources_closed:
            return
        self._resources_closed = True
        try:
            self._resources.release()
        finally:
            self._resources.close()

    def _committed(self) -> None:
        if self._resources.commit is not None:
            self._resources.commit()

    def _guarded(self, door):
        with self._monitor:
            self._refuse_reentry()
            self._ensure_open()
            self._write_thread = threading.get_ident()
            try:
                return door()
            except BaseException as error:
                self._broken = firing_failure_text(error)
                try:
                    self._resources.rollback()
                finally:
                    self._close_resources()
                raise
            finally:
                self._write_thread = None

    def _read(self, operation, *, allow_reentry: bool = False):
        with self._monitor:
            if not allow_reentry:
                self._refuse_reentry()
            self._ensure_open()
            return operation()

    def _refuse_reentry(self) -> None:
        if self._write_thread == threading.get_ident():
            raise RuntimeError("public Engine operation cannot re-enter while a writing door is active")

    def _ensure_open(self) -> None:
        self._resources.ensure()
        if self._broken is not None:
            raise RuntimeError(
                f"this Engine is poisoned after a writing door failed ({self._broken}): History, Instance, "
                f"Dispatch, and the advancement lane may have advanced together — continue through a fresh "
                f"Engine.load or provider load function"
            )
        if self._closed:
            raise RuntimeError("this Engine is closed; create or load a new Engine before observing or driving")


__all__ = [
    "AcceptedDelivery",
    "AcceptDelivery",
    "AcceptResult",
    "Action",
    "AdvanceTime",
    "BeginCandidate",
    "Clock",
    "Delivery",
    "DriveOutcome",
    "DrivingPolicy",
    "Engine",
    "InFlightView",
    "Sensor",
    "SimulatedClock",
    "Snapshot",
    "Stop",
    "Wait",
    "choose_conservative",
    "choose_throughput",
]
