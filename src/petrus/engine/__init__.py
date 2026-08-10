"""One provider-neutral live composition around exactly one durable Instance."""

from __future__ import annotations

import time
import threading
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
from petrus.impetus.history import Record
from petrus.impetus.history_store import HistoryStore
from petrus.impetus.observation import history_page as _history_page
from petrus.impetus.observation import snapshot as _snapshot
from petrus.impetus.instance import FiringOccurrence, FiringOutcome, Instance, PriorAcknowledgement, Status
from petrus.impetus.petrinet import Instant, Marking, Net, NetPath, Token
from petrus.impetus.selection import SelectionPipeline, SelectionPolicy

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
        """The current marking, exposed read-only through the Engine lifecycle."""
        return self._read(lambda: self._instance.marking, allow_reentry=True)

    @property
    def status(self) -> Status:
        """The Instance's derived status."""
        return self._read(lambda: self._instance.status, allow_reentry=True)

    @property
    def in_flight(self) -> tuple[FiringOccurrence, ...]:
        """The in-flight occurrences in begin order."""
        return self._read(lambda: self._instance.in_flight, allow_reentry=True)

    @property
    def records(self) -> tuple[Record, ...]:
        """The canonical History records, never an append-capable handle."""
        return self._read(lambda: self._instance.history.records, allow_reentry=True)

    def snapshot(self) -> dict[str, object]:
        """Return a coherent detached protocol-v1 view of definition and current state."""
        return self._read(lambda: _snapshot(self._instance, self._instance.history.records))

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
        self, source: NetPath | str, tokens: Token | Sequence[Token], *, identity: str | None = None
    ) -> FiringOutcome | PriorAcknowledgement:
        """Land one external delivery and commit its complete fact set."""

        def door() -> FiringOutcome | PriorAcknowledgement:
            landed = self._instance.deliver(source, tokens, at=self._clock.now(), identity=identity)
            self._committed()
            return landed

        return self._guarded(door)

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
                self._broken = repr(error)
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
