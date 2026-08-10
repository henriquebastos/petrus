"""Provider-neutral synchronous Activity Worker runtime."""

from __future__ import annotations

import asyncio
import concurrent.futures
import inspect
import json
import os
import queue
import sys
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

import petrus.telemetry as telemetry
from petrus.motus.activity import (
    Activity,
    ActivityError,
    ActivityFailure,
    AsyncActivity,
    AsyncActivityDefinition,
    _OMITTED,
)
from petrus.motus.activity import snapshot_heartbeat_details
from petrus.motus.dispatch import ActivityAttempt, WorkerDispatch

log = telemetry.get_logger("impetus")


def _is_async_activity(value: object) -> bool:
    """Classify every supported asynchronous Activity spelling in one place."""

    return (
        isinstance(value, AsyncActivityDefinition)
        or inspect.iscoroutinefunction(value)
        or inspect.iscoroutinefunction(getattr(value, "__call__", None))
    )


def _validate_registry(activities: Mapping[str, Any], *, asynchronous: bool) -> dict[str, Any]:
    registry = dict(activities)
    if not registry or any(
        not isinstance(name, str) or not name or not callable(value) for name, value in registry.items()
    ):
        raise ValueError("Worker activities must be a non-empty mapping of non-empty string names to callables")
    wrong = [name for name, value in registry.items() if _is_async_activity(value) is not asynchronous]
    if wrong:
        required = "asynchronous" if asynchronous else "synchronous"
        hint = " (AsyncActivityDefinitions or async callables)" if asynchronous else ""
        raise TypeError(f"Worker requires {required} Activities{hint}; wrong-mode registry entries: {sorted(wrong)}")
    return registry


@dataclass
class ActivityExecutionContext:
    """Provider-neutral context supplied to a synchronous Activity."""

    attempt_id: str
    epoch: str
    claimant: str
    latest_details: object
    _provider: WorkerDispatch = field(repr=False)
    _attempt: ActivityAttempt = field(repr=False)

    def heartbeat(self, *, details: object = _OMITTED) -> object:
        self.latest_details = self._provider.heartbeat(self._attempt, details=details)
        return self.latest_details


class Worker:
    """Run registered Activities one at a time over a Worker-facing Dispatch."""

    def __init__(self, provider: WorkerDispatch, activities: Mapping[str, Activity], *, worker_id: str | None = None):
        if not isinstance(provider, WorkerDispatch):
            raise TypeError("Worker provider must implement WorkerDispatch")
        self._provider = provider
        self._activities = _validate_registry(activities, asynchronous=False)
        self._worker_id = worker_id or f"worker-{os.getpid()}"
        self._stop = False

    def stop(self) -> None:
        """Stop new claims; an Activity already running is allowed to terminalize."""
        self._stop = True

    def run(self, *, poll_interval: float = 0.25) -> None:
        if poll_interval < 0:
            raise ValueError("Worker poll interval must be non-negative")
        log.emit("worker_started", worker=self._worker_id, concurrency=1)
        self._say(ready=True, worker=self._worker_id)
        try:
            while not self._stop:
                self._drain()
                if not self._stop:
                    self._provider.wait(poll_interval)
        finally:
            self._provider.close()
            log.emit("worker_stopped", worker=self._worker_id, concurrency=1)

    def _drain(self) -> None:
        while not self._stop:
            attempt = self._provider.claim()
            if attempt is None:
                return
            self._execute(attempt)

    def _execute(self, attempt: ActivityAttempt) -> None:
        invocation = attempt.invocation
        with log.span(
            "worker_activity",
            worker=self._worker_id,
            queue=attempt.queue,
            activity=invocation.activity,
            attempt=attempt.attempt_id,
            epoch=attempt.epoch,
            claimant=attempt.claimant,
        ) as span:
            error: Exception | None = None
            result: object = None
            try:
                implementation = self._activities.get(invocation.activity)
                if implementation is None:
                    raise LookupError(
                        f"no activity implementation for {invocation.activity!r}: "
                        f"this worker implements {sorted(self._activities)}"
                    )
                context = ActivityExecutionContext(
                    attempt.attempt_id,
                    attempt.epoch,
                    attempt.claimant,
                    attempt.latest_details,
                    self._provider,
                    attempt,
                )
                result = implementation(invocation, context=context)
                result = json.loads(json.dumps(result, allow_nan=False))
            except Exception as raised:
                error = raised
            try:
                if error is None:
                    self._provider.complete(attempt, result)
                else:
                    self._provider.fail(attempt, error.failure if isinstance(error, ActivityError) else error)
            except Exception as refused:
                self._say(worker=self._worker_id, refused=attempt.attempt_id, error=str(refused).strip())
                span.set(outcome="refused")
                return
            outcome = "completed" if error is None else "failed"
            span.set(outcome=outcome, max_rss_mb=telemetry.max_rss_mb())
            self._say(
                worker=self._worker_id, processed=attempt.attempt_id, activity=invocation.activity, outcome=outcome
            )

    @staticmethod
    def _say(**event: object) -> None:
        print(json.dumps(event), file=sys.stdout, flush=True)


@dataclass
class AsyncActivityExecutionContext:
    """Attempt context whose custody operations stay serialized until terminal."""

    attempt_id: str
    epoch: str
    claimant: str
    latest_details: object
    _access: _AsyncWorkerAccess = field(repr=False)
    _slot: int = field(repr=False)
    _attempt: ActivityAttempt = field(repr=False)
    _open: bool = field(default=True, init=False, repr=False)
    _closing: bool = field(default=False, init=False, repr=False)
    _heartbeat_lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    async def heartbeat(self, *, details: object = _OMITTED) -> object:
        # Snapshot caller-owned mutable data on the event-loop thread while
        # retaining omission as a distinct provider operation.
        detached = details if details is _OMITTED else snapshot_heartbeat_details(details)
        async with self._heartbeat_lock:
            if not self._open or self._closing:
                raise RuntimeError("Activity execution context is closed")
            accepted = await _owned(self._access.heartbeat(self._slot, self._attempt, details=detached))
            self.latest_details = accepted
            return accepted

    async def _close(self) -> None:
        self._closing = True
        async with self._heartbeat_lock:
            self._open = False


@dataclass(frozen=True)
class _LaneCall:
    method: str
    args: tuple[object, ...]
    kwargs: dict[str, object]
    future: concurrent.futures.Future[Any]


class _ProviderLane:
    """One stable thread and provider instance, addressed from one event loop."""

    def __init__(self, number: int, factory: Callable[[], WorkerDispatch]):
        self.number = number
        self._factory = factory
        self._calls: queue.Queue[_LaneCall | None] = queue.Queue()
        self._ready: concurrent.futures.Future[None] = concurrent.futures.Future()
        self._thread = threading.Thread(target=self._own, name=f"impetus-provider-{number}", daemon=False)

    def start(self) -> concurrent.futures.Future[None]:
        self._thread.start()
        return self._ready

    async def call(self, method: str, *args: object, **kwargs: object) -> Any:
        future: concurrent.futures.Future[Any] = concurrent.futures.Future()
        self._calls.put(_LaneCall(method, args, kwargs, future))
        return await asyncio.wrap_future(future)

    async def close(self) -> None:
        if not self._thread.is_alive():
            return
        try:
            await self.call("close")
        finally:
            self._calls.put(None)
            await asyncio.to_thread(self._thread.join)

    @staticmethod
    def _settle(
        future: concurrent.futures.Future[Any], *, value: Any = None, error: BaseException | None = None
    ) -> None:
        if future.cancelled() or future.done():
            return
        if error is None:
            future.set_result(value)
        else:
            future.set_exception(error)

    def _own(self) -> None:
        try:
            provider = self._factory()
            if not isinstance(provider, WorkerDispatch):
                raise TypeError("AsyncWorker provider factory must return a WorkerDispatch")
        except BaseException as error:
            self._settle(self._ready, error=error)
            return
        self._settle(self._ready)
        while (request := self._calls.get()) is not None:
            if not request.future.set_running_or_notify_cancel():
                continue
            try:
                value = getattr(provider, request.method)(*request.args, **request.kwargs)
                self._settle(request.future, value=value)
            except BaseException as error:
                self._settle(request.future, error=error)


class _AsyncWorkerAccess(Protocol):
    """Initially-private awaitable Worker custody used by ``AsyncWorker``."""

    async def ready(self) -> None: ...

    async def claim(self, slot: int) -> ActivityAttempt | None: ...

    async def heartbeat(self, slot: int, attempt: ActivityAttempt, *, details: object = _OMITTED) -> object: ...

    async def complete(self, slot: int, attempt: ActivityAttempt, result: object) -> None: ...

    async def fail(self, slot: int, attempt: ActivityAttempt, error: str | Exception | ActivityFailure) -> None: ...

    async def wait(self, slot: int, timeout: float) -> bool: ...

    async def close(self) -> None: ...


async def _owned(awaitable: Awaitable[Any]) -> Any:
    """Let a custody operation reach a definite result even if its caller leaves."""

    operation = asyncio.ensure_future(awaitable)
    cancelled: asyncio.CancelledError | None = None
    while not operation.done():
        try:
            await asyncio.shield(operation)
        except asyncio.CancelledError as error:
            cancelled = cancelled or error
    try:
        result = operation.result()
    except BaseException as error:
        if cancelled is not None:
            raise error from cancelled
        raise
    if cancelled is not None:
        raise cancelled
    return result


async def _settle_after_cancellation(operation: asyncio.Task[Any]) -> Any:
    """Return a task's result while ignoring further cancellation of its owner."""

    while not operation.done():
        try:
            await asyncio.shield(operation)
        except asyncio.CancelledError:
            continue
    return operation.result()


class _SynchronousWorkerAccess:
    """Private async adapter preserving N stable synchronous provider lanes."""

    def __init__(self, factory: Callable[[], WorkerDispatch], concurrency: int):
        self._lanes = [_ProviderLane(number, factory) for number in range(concurrency)]
        self._initialized: list[_ProviderLane] = []

    async def ready(self) -> None:
        self._initialized = await AsyncWorker._start_lanes(self._lanes)

    async def claim(self, slot: int) -> ActivityAttempt | None:
        return await self._lanes[slot].call("claim")

    async def heartbeat(self, slot: int, attempt: ActivityAttempt, *, details: object = _OMITTED) -> object:
        return await self._lanes[slot].call("heartbeat", attempt, details=details)

    async def complete(self, slot: int, attempt: ActivityAttempt, result: object) -> None:
        await self._lanes[slot].call("complete", attempt, result)

    async def fail(self, slot: int, attempt: ActivityAttempt, error: str | Exception | ActivityFailure) -> None:
        await self._lanes[slot].call("fail", attempt, error)

    async def wait(self, slot: int, timeout: float) -> bool:
        return await self._lanes[slot].call("wait", timeout)

    async def close(self) -> None:
        results = await asyncio.gather(*(lane.close() for lane in self._initialized), return_exceptions=True)
        error = next((result for result in results if isinstance(result, BaseException)), None)
        if error is not None:
            raise error


class AsyncWorker:
    """Run async Activities through one provider-neutral async custody path."""

    def __init__(
        self,
        provider_factory: Callable[[], WorkerDispatch],
        activities: Mapping[str, AsyncActivity],
        *,
        concurrency: int,
        worker_id: str | None = None,
    ):
        if not callable(provider_factory):
            raise TypeError("AsyncWorker provider_factory must be callable")
        if isinstance(concurrency, bool) or not isinstance(concurrency, int) or concurrency <= 0:
            raise ValueError("AsyncWorker concurrency must be a positive integer")
        self._activities = _validate_registry(activities, asynchronous=True)
        self._factory = provider_factory
        self._access_factory: Callable[[], Awaitable[_AsyncWorkerAccess]] | None = None
        self._concurrency = concurrency
        self._worker_id = worker_id or f"async-worker-{os.getpid()}"
        self._stop = threading.Event()

    @classmethod
    def _from_async_access(
        cls,
        access_factory: Callable[[], Awaitable[_AsyncWorkerAccess]],
        activities: Mapping[str, AsyncActivity],
        *,
        concurrency: int,
        worker_id: str | None = None,
    ) -> AsyncWorker:
        """Explicit internal native-async construction door; no shape guessing."""

        if not callable(access_factory):
            raise TypeError("AsyncWorker access_factory must be callable")

        def unused_sync_factory() -> WorkerDispatch:
            raise AssertionError("native async access does not construct a synchronous provider")

        worker = cls(unused_sync_factory, activities, concurrency=concurrency, worker_id=worker_id)
        worker._access_factory = access_factory
        return worker

    def stop(self) -> None:
        """Stop new admission while claims already in progress and admitted work drain."""
        self._stop.set()

    async def _acquire_access(
        self,
    ) -> tuple[_AsyncWorkerAccess | None, BaseException | None, asyncio.CancelledError | None]:
        if self._access_factory is None:
            return _SynchronousWorkerAccess(self._factory, self._concurrency), None, None
        acquisition = asyncio.ensure_future(self._access_factory())
        try:
            return await asyncio.shield(acquisition), None, None
        except asyncio.CancelledError as cancelled:
            try:
                return await _settle_after_cancellation(acquisition), None, cancelled
            except BaseException as error:
                return None, error, cancelled

    async def run(self, *, poll_interval: float = 0.25) -> None:  # noqa: C901 - custody cleanup precedence is explicit
        if poll_interval < 0:
            raise ValueError("AsyncWorker poll interval must be non-negative")
        access: _AsyncWorkerAccess | None = None
        coordinator: asyncio.Task[None] | None = None
        first_error: BaseException | None = None
        cancelled: asyncio.CancelledError | None = None
        log.emit("worker_started", worker=self._worker_id, concurrency=self._concurrency)
        try:
            access, first_error, cancelled = await self._acquire_access()
            if cancelled is None and first_error is None:
                assert access is not None
                await _owned(access.ready())
                self._say(ready=True, worker=self._worker_id, concurrency=self._concurrency)
                coordinator = asyncio.create_task(self._coordinate(access, poll_interval))
                await asyncio.shield(coordinator)
        except asyncio.CancelledError as error:
            cancelled = cancelled or error
            self.stop()
        except BaseException as error:
            first_error = error
            self.stop()
        finally:
            if coordinator is not None:
                try:
                    await _owned(coordinator)
                except asyncio.CancelledError as error:
                    cancelled = cancelled or error
                except BaseException as error:
                    first_error = first_error or error
            if access is not None:
                try:
                    await _owned(access.close())
                except asyncio.CancelledError as error:
                    cancelled = cancelled or error
                except BaseException as error:
                    first_error = first_error or error
            log.emit("worker_stopped", worker=self._worker_id, concurrency=self._concurrency)
        if first_error is not None:
            if cancelled is not None:
                raise first_error from cancelled
            raise first_error
        if cancelled is not None:
            raise cancelled

    @staticmethod
    async def _start_lanes(lanes: list[_ProviderLane]) -> list[_ProviderLane]:
        started: list[_ProviderLane] = []
        readiness: list[concurrent.futures.Future[None]] = []
        start_error: BaseException | None = None
        for lane in lanes:
            try:
                readiness.append(lane.start())
                started.append(lane)
            except BaseException as error:
                start_error = error
                break
        settling = asyncio.ensure_future(
            asyncio.gather(*(asyncio.wrap_future(future) for future in readiness), return_exceptions=True)
        )
        cancelled: asyncio.CancelledError | None = None
        try:
            results = await asyncio.shield(settling)
        except asyncio.CancelledError as error:
            cancelled = error
            results = await asyncio.shield(settling)
        initialized = [
            lane for lane, result in zip(started, results, strict=True) if not isinstance(result, BaseException)
        ]
        startup_error = next((result for result in results if isinstance(result, BaseException)), None)
        if start_error is not None or startup_error is not None or cancelled is not None:
            await asyncio.shield(asyncio.gather(*(lane.close() for lane in initialized), return_exceptions=True))
            if cancelled is not None:
                raise cancelled
            if start_error is not None:
                raise start_error
            assert startup_error is not None
            raise startup_error
        return initialized

    async def _coordinate(self, access: _AsyncWorkerAccess, poll_interval: float) -> None:
        active: dict[asyncio.Task[None], int] = {}
        free = list(range(self._concurrency))
        try:
            while not self._stop.is_set():
                done = [task for task in active if task.done()]
                self._settled_slots(done, active, free)
                if not free:
                    await asyncio.wait(active, return_when=asyncio.FIRST_COMPLETED)
                    self._settled_slots([task for task in active if task.done()], active, free)
                    continue
                slot = free.pop(0)
                attempt = await _owned(access.claim(slot))
                if attempt is not None:
                    task = asyncio.create_task(self._execute(access, slot, attempt))
                    active[task] = slot
                    done = [task for task in active if task.done()]
                    self._settled_slots(done, active, free)
                else:
                    free.insert(0, slot)
                    if active:
                        await asyncio.wait(active, timeout=0, return_when=asyncio.FIRST_COMPLETED)
                        self._settled_slots([task for task in active if task.done()], active, free)
                    if not self._stop.is_set():
                        await _owned(access.wait(slot, poll_interval))
            if active:
                results = await asyncio.gather(*active, return_exceptions=True)
                error = next((result for result in results if isinstance(result, BaseException)), None)
                if error is not None:
                    raise error
        except BaseException:
            self.stop()
            if active:
                await asyncio.shield(asyncio.gather(*active, return_exceptions=True))
            raise

    @staticmethod
    def _settled_slots(done: list[asyncio.Task[None]], active: dict[asyncio.Task[None], int], free: list[int]) -> None:
        for task in done:
            slot = active.pop(task)
            error = task.exception()
            if error is not None:
                raise error
            free.append(slot)
        free.sort()

    async def _execute(self, access: _AsyncWorkerAccess, slot: int, attempt: ActivityAttempt) -> None:
        invocation = attempt.invocation
        with log.span(
            "worker_activity",
            worker=self._worker_id,
            queue=attempt.queue,
            activity=invocation.activity,
            attempt=attempt.attempt_id,
            epoch=attempt.epoch,
            claimant=attempt.claimant,
        ) as span:
            error: Exception | None = None
            result: object = None
            context = AsyncActivityExecutionContext(
                attempt.attempt_id,
                attempt.epoch,
                attempt.claimant,
                attempt.latest_details,
                access,
                slot,
                attempt,
            )
            try:
                implementation = self._activities.get(invocation.activity)
                if implementation is None:
                    raise LookupError(
                        f"no activity implementation for {invocation.activity!r}: "
                        f"this worker implements {sorted(self._activities)}"
                    )
                result = await implementation(invocation, context=context)
                result = json.loads(json.dumps(result, allow_nan=False))
            except asyncio.CancelledError as raised:
                error = RuntimeError(f"Activity cancelled: {raised}")
            except Exception as raised:
                error = raised
            finally:
                await context._close()
            try:
                if error is None:
                    await _owned(access.complete(slot, attempt, result))
                else:
                    await _owned(
                        access.fail(slot, attempt, error.failure if isinstance(error, ActivityError) else error)
                    )
            except Exception as refused:
                self._say(worker=self._worker_id, refused=attempt.attempt_id, error=str(refused).strip())
                span.set(outcome="refused")
                raise
            outcome = "completed" if error is None else "failed"
            span.set(outcome=outcome, max_rss_mb=telemetry.max_rss_mb())
            self._say(
                worker=self._worker_id, processed=attempt.attempt_id, activity=invocation.activity, outcome=outcome
            )

    @staticmethod
    def _say(**event: object) -> None:
        Worker._say(**event)


__all__ = ["ActivityExecutionContext", "AsyncActivityExecutionContext", "AsyncWorker", "Worker"]
