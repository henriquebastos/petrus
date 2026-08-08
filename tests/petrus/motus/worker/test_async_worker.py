"""Production asynchronous Activity execution contract."""

from __future__ import annotations

import asyncio
import threading
from collections import deque
from dataclasses import dataclass

import pytest

import petrus.motus.worker as worker_module
import petrus.motus.worker._cli as worker_cli
from petrus.motus.activity import (
    ActivityInvocation,
    AsyncActivityDefinition,
    DataclassPayloadConverter,
    activity,
    async_activity,
)
from petrus.motus.dispatch import ActivityAttempt
from petrus.motus.dispatch.local import LocalDispatch, LocalWorkerDispatch
from petrus.motus.worker import AsyncWorker, Worker


@dataclass(frozen=True)
class Input:
    value: int


@dataclass(frozen=True)
class Output:
    value: int


def _attempt(number: int) -> ActivityAttempt:
    return ActivityAttempt(
        f"attempt-{number}",
        f"epoch-{number}",
        "claimant",
        "io",
        ActivityInvocation("io", input={"item": {"value": number}}),
    )


class SharedProviders:
    def __init__(self, attempts: list[ActivityAttempt]):
        self.attempts = deque(attempts)
        self.lock = threading.Lock()
        self.owners: dict[int, set[int]] = {}
        self.completed: list[tuple[ActivityAttempt, object]] = []
        self.closed = 0

    def factory(self):
        lane = len(self.owners)
        owner = threading.get_ident()
        self.owners[lane] = {owner}
        shared = self

        class Provider:
            def _owner(self):
                shared.owners[lane].add(threading.get_ident())

            def claim(self):
                self._owner()
                with shared.lock:
                    return shared.attempts.popleft() if shared.attempts else None

            def heartbeat(self, attempt, *, details):
                self._owner()
                return details

            def complete(self, attempt, result):
                self._owner()
                with shared.lock:
                    shared.completed.append((attempt, result))

            def fail(self, attempt, error):
                raise AssertionError(error)

            def wait(self, timeout):
                self._owner()
                return False

            def close(self):
                self._owner()
                with shared.lock:
                    shared.closed += 1

        return Provider()


def test_async_decorator_converts_typed_payload_and_json_result():
    @async_activity(name="io", converter=DataclassPayloadConverter())
    async def io(item: Input) -> Output:
        await asyncio.sleep(0)
        return Output(item.value + 1)

    @activity(name="io", converter=DataclassPayloadConverter())
    def sync_io(item: Input) -> Output:
        return Output(item.value + 1)

    assert isinstance(io, AsyncActivityDefinition)
    assert io.declaration == sync_io.declaration

    async def execute():
        class Context:
            pass

        return await io(ActivityInvocation("io", input={"item": {"value": 2}}), context=Context())

    assert asyncio.run(execute()) == {"value": 3}


def test_async_decorator_rejects_sync_and_untyped_signatures():
    with pytest.raises(TypeError, match="async coroutine"):
        async_activity(lambda value: value)

    with pytest.raises(TypeError, match="requires a type annotation"):

        @async_activity
        async def untyped(value) -> int:
            return value

    with pytest.raises(TypeError, match="use async_activity"):

        @activity
        async def wrongly_sync(value: int) -> int:
            return value


def test_raw_coroutine_function_and_async_callable_are_context_aware_async_activities():
    seen = []

    async def raw(invocation, *, context):
        seen.append((invocation.activity, context.attempt_id))
        return "raw"

    class Callable:
        async def __call__(self, invocation, *, context):
            seen.append((invocation.activity, context.attempt_id))
            return "callable"

    AsyncWorker(lambda: SharedProviders([]).factory(), {"raw": raw}, concurrency=1)
    AsyncWorker(lambda: SharedProviders([]).factory(), {"callable": Callable()}, concurrency=1)
    with pytest.raises(TypeError, match="requires synchronous"):
        Worker(SharedProviders([]).factory(), {"raw": raw})
    with pytest.raises(TypeError, match="requires synchronous"):
        Worker(SharedProviders([]).factory(), {"callable": Callable()})


def test_cli_rejects_wrong_mode_registry_before_provider_factory(monkeypatch, tmp_path):
    monkeypatch.setattr(worker_cli, "_load_registry", lambda _spec: {"sync": lambda invocation, *, context: None})
    touched = False

    def provider_factory(*_args):
        nonlocal touched
        touched = True
        raise AssertionError("provider factory must remain untouched")

    monkeypatch.setattr(worker_cli, "_provider_factory", provider_factory)
    with pytest.raises(SystemExit, match="requires asynchronous"):
        worker_cli.main(
            [
                "--provider",
                "local",
                "--path",
                str(tmp_path / "dispatch.sqlite3"),
                "--registry",
                "fake:registry",
                "--execution-mode",
                "async",
            ]
        )
    assert not touched


def test_cli_defaults_to_sync_bridge_and_validates_explicit_native_access():
    defaults = worker_cli._parser().parse_args(
        ["--provider", "local", "--path", "dispatch.db", "--registry", "fake:registry"]
    )
    assert defaults.custody_access == "sync-bridge"
    assert defaults.max_operation_sockets == 8

    invalid = worker_cli._parser().parse_args(
        [
            "--provider",
            "local",
            "--path",
            "dispatch.db",
            "--registry",
            "fake:registry",
            "--custody-access",
            "native-zeromq",
        ]
    )
    with pytest.raises(SystemExit, match="requires async execution with the zeromq provider"):
        worker_cli._validate_provider_arguments(invalid)


def test_sync_and_async_workers_cross_reject_before_custody():
    @async_activity
    async def async_work(value: int) -> int:
        return value

    @activity
    def sync_work(value: int) -> int:
        return value

    provider = SharedProviders([]).factory()
    with pytest.raises(TypeError, match="requires synchronous"):
        Worker(provider, {"async_work": async_work})
    constructed = False

    def factory():
        nonlocal constructed
        constructed = True
        return provider

    with pytest.raises(TypeError, match="AsyncActivityDefinitions"):
        AsyncWorker(factory, {"sync_work": sync_work}, concurrency=1)
    assert not constructed


def test_async_worker_runs_exact_concurrency_on_event_loop_and_owns_providers_by_lane():
    concurrency = 3
    providers = SharedProviders([_attempt(number) for number in range(concurrency)])
    entered = 0
    peak = 0
    loop_thread = 0
    release = asyncio.Event()
    all_entered = asyncio.Event()

    @async_activity(name="io", converter=DataclassPayloadConverter())
    async def io(item: Input) -> Output:
        nonlocal entered, peak
        assert threading.get_ident() == loop_thread
        entered += 1
        peak = max(peak, entered)
        if entered == concurrency:
            all_entered.set()
        await release.wait()
        entered -= 1
        return Output(item.value)

    worker = AsyncWorker(providers.factory, {"io": io}, concurrency=concurrency)

    async def exercise():
        nonlocal loop_thread
        loop_thread = threading.get_ident()
        running = asyncio.create_task(worker.run(poll_interval=0))
        await asyncio.wait_for(all_entered.wait(), 2)
        worker.stop()
        release.set()
        await running

    asyncio.run(exercise())
    assert peak == concurrency
    assert len(providers.completed) == concurrency
    assert providers.closed == concurrency
    assert len(providers.owners) == concurrency
    assert all(len(owner_threads) == 1 for owner_threads in providers.owners.values())
    assert all(next(iter(owner_threads)) != loop_thread for owner_threads in providers.owners.values())


@pytest.mark.parametrize("concurrency", [0, -1, True, 1.5])
def test_async_worker_requires_positive_integer_concurrency(concurrency):
    @async_activity
    async def work(value: int) -> int:
        return value

    with pytest.raises(ValueError, match="positive integer"):
        AsyncWorker(lambda: SharedProviders([]).factory(), {"work": work}, concurrency=concurrency)


def test_async_worker_closes_initialized_lanes_after_partial_startup_failure():
    providers = SharedProviders([])
    constructions = 0

    def factory():
        nonlocal constructions
        constructions += 1
        if constructions == 2:
            raise RuntimeError("startup failed")
        return providers.factory()

    @async_activity
    async def work(value: int) -> int:
        return value

    worker = AsyncWorker(factory, {"work": work}, concurrency=3)
    with pytest.raises(RuntimeError, match="startup failed"):
        asyncio.run(worker.run())
    assert constructions == 3
    assert providers.closed == 2


def test_caller_cancellation_drains_claim_acquired_before_return_and_then_closes():
    attempt = _attempt(1)
    claim_acquired = threading.Event()
    release_claim = threading.Event()
    activity_ran = asyncio.Event()
    owner = None
    completed = []
    closed = threading.Event()

    class Provider:
        def claim(self):
            nonlocal owner
            owner = threading.get_ident()
            claim_acquired.set()
            assert release_claim.wait(2)
            return attempt

        def heartbeat(self, attempt, *, details):
            return details

        def complete(self, claimed, result):
            assert threading.get_ident() == owner
            completed.append((claimed, result))

        def fail(self, attempt, error):
            raise AssertionError(error)

        def wait(self, timeout):
            return False

        def close(self):
            assert threading.get_ident() == owner
            closed.set()

    async def work(invocation, *, context):
        activity_ran.set()
        return "done"

    async def exercise():
        running = asyncio.create_task(AsyncWorker(Provider, {"io": work}, concurrency=1).run(poll_interval=0))
        assert await asyncio.wait_for(asyncio.to_thread(claim_acquired.wait, 2), 3)
        running.cancel()
        cancellation_delivered = asyncio.get_running_loop().create_future()
        asyncio.get_running_loop().call_soon(cancellation_delivered.set_result, None)
        await cancellation_delivered
        assert not running.done()
        release_claim.set()
        await asyncio.wait_for(activity_ran.wait(), 2)
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(running, 2)
        assert closed.is_set()

    asyncio.run(exercise())
    assert completed == [(attempt, "done")]


def test_caller_cancellation_during_blocked_factory_closes_after_startup_settles():
    factory_entered = threading.Event()
    release_factory = threading.Event()
    closed = threading.Event()
    owner = None

    class Provider:
        def claim(self):
            return None

        def heartbeat(self, attempt, *, details):
            return details

        def complete(self, attempt, result):
            raise AssertionError("no Attempt")

        def fail(self, attempt, error):
            raise AssertionError("no Attempt")

        def wait(self, timeout):
            return False

        def close(self):
            assert threading.get_ident() == owner
            closed.set()

    def factory():
        nonlocal owner
        owner = threading.get_ident()
        factory_entered.set()
        assert release_factory.wait(2)
        return Provider()

    async def work(invocation, *, context):
        return None

    async def exercise():
        running = asyncio.create_task(AsyncWorker(factory, {"io": work}, concurrency=1).run())
        assert await asyncio.wait_for(asyncio.to_thread(factory_entered.wait, 2), 3)
        running.cancel()
        cancellation_delivered = asyncio.get_running_loop().create_future()
        asyncio.get_running_loop().call_soon(cancellation_delivered.set_result, None)
        await cancellation_delivered
        assert not running.done()
        release_factory.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(running, 2)
        assert closed.is_set()

    asyncio.run(exercise())


def test_partial_thread_start_failure_closes_provider_from_every_started_lane(monkeypatch):
    initialized = threading.Event()
    closed = threading.Event()
    owner = None
    original_start = worker_module._ProviderLane.start

    class Provider:
        def claim(self):
            return None

        def heartbeat(self, attempt, *, details):
            return details

        def complete(self, attempt, result):
            raise AssertionError("no Attempt")

        def fail(self, attempt, error):
            raise AssertionError("no Attempt")

        def wait(self, timeout):
            return False

        def close(self):
            assert threading.get_ident() == owner
            closed.set()

    def factory():
        nonlocal owner
        owner = threading.get_ident()
        initialized.set()
        return Provider()

    def start(lane):
        if lane.number == 1:
            raise RuntimeError("thread start failed")
        return original_start(lane)

    monkeypatch.setattr(worker_module._ProviderLane, "start", start)

    async def work(invocation, *, context):
        return None

    worker = AsyncWorker(factory, {"io": work}, concurrency=2)
    with pytest.raises(RuntimeError, match="thread start failed"):
        asyncio.run(worker.run())
    assert initialized.is_set()
    assert closed.is_set()


def test_user_activity_cancelled_error_is_reported_as_failure_and_provider_closes():
    attempt = _attempt(1)
    failed = []
    completed = []
    closed = threading.Event()
    claims = 0

    class Provider:
        def claim(self):
            nonlocal claims
            claims += 1
            return attempt if claims == 1 else None

        def heartbeat(self, attempt, *, details):
            return details

        def complete(self, attempt, result):
            completed.append((attempt, result))

        def fail(self, claimed, error):
            failed.append((claimed, error))

        def wait(self, timeout):
            return False

        def close(self):
            closed.set()

    async def work(invocation, *, context):
        worker.stop()
        raise asyncio.CancelledError("user cancellation")

    worker = AsyncWorker(Provider, {"io": work}, concurrency=1)
    asyncio.run(asyncio.wait_for(worker.run(poll_interval=0), 2))
    assert completed == []
    assert len(failed) == 1
    assert failed[0][0] is attempt
    assert isinstance(failed[0][1], RuntimeError)
    assert str(failed[0][1]) == "Activity cancelled: user cancellation"
    assert closed.is_set()


def test_cancelled_running_heartbeat_failure_keeps_lane_alive_to_fail_attempt_and_close():
    attempt = _attempt(1)
    heartbeat_entered = threading.Event()
    release_heartbeat = threading.Event()
    failed = []
    closed = threading.Event()
    heartbeat_task = None

    class Provider:
        claimed = False

        def claim(self):
            if self.claimed:
                return None
            self.claimed = True
            return attempt

        def heartbeat(self, claimed, *, details):
            heartbeat_entered.set()
            assert release_heartbeat.wait(2)
            raise RuntimeError("heartbeat unavailable")

        def complete(self, attempt, result):
            raise AssertionError("cancelled Activity must fail")

        def fail(self, claimed, error):
            failed.append((claimed, error))

        def wait(self, timeout):
            return False

        def close(self):
            closed.set()

    async def work(invocation, *, context):
        nonlocal heartbeat_task
        heartbeat_task = asyncio.create_task(context.heartbeat(details={"cursor": 1}))
        assert await asyncio.wait_for(asyncio.to_thread(heartbeat_entered.wait, 2), 3)
        worker.stop()
        heartbeat_task.cancel()
        release_heartbeat.set()
        await heartbeat_task

    worker = AsyncWorker(Provider, {"io": work}, concurrency=1)
    asyncio.run(asyncio.wait_for(worker.run(poll_interval=0), 3))
    assert len(failed) == 1
    assert failed[0][0] is attempt
    assert isinstance(failed[0][1], RuntimeError)
    assert str(failed[0][1]) == "heartbeat unavailable"
    assert closed.is_set()


def test_context_close_orders_queued_heartbeats_before_terminal_without_detached_errors():
    attempt = _attempt(1)
    heartbeat_entered = threading.Event()
    release_heartbeat = threading.Event()
    provider_heartbeats = []
    terminal = []
    heartbeat_tasks = []
    contexts = []
    loop_errors = []

    class Provider:
        claimed = False

        def claim(self):
            if self.claimed:
                return None
            self.claimed = True
            return attempt

        def heartbeat(self, claimed, *, details):
            provider_heartbeats.append((claimed, details))
            heartbeat_entered.set()
            assert release_heartbeat.wait(2)
            return {"accepted": details}

        def complete(self, claimed, result):
            terminal.append((claimed, result))

        def fail(self, attempt, error):
            raise AssertionError(error)

        def wait(self, timeout):
            return False

        def close(self):
            pass

    async def work(invocation, *, context):
        contexts.append(context)
        first = asyncio.create_task(context.heartbeat(details="first"))
        heartbeat_tasks.append(first)
        assert await asyncio.wait_for(asyncio.to_thread(heartbeat_entered.wait, 2), 3)
        second_started = asyncio.Event()

        async def queued_heartbeat():
            second_started.set()
            return await context.heartbeat(details="second")

        second = asyncio.create_task(queued_heartbeat())
        heartbeat_tasks.append(second)
        await second_started.wait()
        worker.stop()
        return "done"

    async def exercise():
        loop = asyncio.get_running_loop()
        loop.set_exception_handler(lambda _loop, context: loop_errors.append(context))
        running = asyncio.create_task(worker.run(poll_interval=0))
        assert await asyncio.wait_for(asyncio.to_thread(heartbeat_entered.wait, 2), 3)
        release_heartbeat.set()
        await asyncio.wait_for(running, 2)
        assert await heartbeat_tasks[0] == {"accepted": "first"}
        with pytest.raises(RuntimeError, match="context is closed"):
            await heartbeat_tasks[1]

    worker = AsyncWorker(Provider, {"io": work}, concurrency=1)
    asyncio.run(exercise())
    assert provider_heartbeats == [(attempt, "first")]
    assert terminal == [(attempt, "done")]
    assert contexts[0].latest_details == {"accepted": "first"}
    assert loop_errors == []


def test_terminal_failure_stops_all_lanes_drains_sibling_and_closes_every_provider():
    attempts = [_attempt(1), _attempt(2)]
    factory_lock = threading.Lock()
    created = 0
    claim_counts = [0, 0]
    entered = 0
    both_entered = asyncio.Event()
    release_sibling = asyncio.Event()
    terminal_failed = threading.Event()
    terminals = []
    closes = []

    def factory():
        nonlocal created
        with factory_lock:
            lane = created
            created += 1
        owner = threading.get_ident()

        class Provider:
            def claim(self):
                claim_counts[lane] += 1
                return attempts[lane] if claim_counts[lane] == 1 else None

            def heartbeat(self, attempt, *, details):
                return details

            def complete(self, claimed, result):
                terminals.append((claimed, result))
                if lane == 0:
                    terminal_failed.set()
                    raise RuntimeError("terminal failed")

            def fail(self, attempt, error):
                raise AssertionError(error)

            def wait(self, timeout):
                return False

            def close(self):
                assert threading.get_ident() == owner
                closes.append(lane)
                if lane == 1:
                    raise RuntimeError("close failed")

        return Provider()

    async def work(invocation, *, context):
        nonlocal entered
        entered += 1
        if entered == 2:
            both_entered.set()
        await both_entered.wait()
        if context.attempt_id == attempts[1].attempt_id:
            await release_sibling.wait()
        return context.attempt_id

    async def exercise():
        running = asyncio.create_task(AsyncWorker(factory, {"io": work}, concurrency=2).run(poll_interval=0))
        await asyncio.wait_for(both_entered.wait(), 2)
        assert await asyncio.wait_for(asyncio.to_thread(terminal_failed.wait, 2), 3)
        release_sibling.set()
        with pytest.raises(RuntimeError, match="terminal failed"):
            await asyncio.wait_for(running, 2)

    asyncio.run(exercise())
    assert claim_counts == [1, 1]
    assert terminals == [(attempts[0], "attempt-1"), (attempts[1], "attempt-2")]
    assert sorted(closes) == [0, 1]


def test_real_local_async_worker_concurrently_completes_and_preserves_heartbeat_details(tmp_path):
    path = tmp_path / "dispatch.sqlite3"
    dispatch = LocalDispatch(path, instance="async-local", default_queue="io")
    for number in range(3):
        dispatch.dispatch(number + 1, ActivityInvocation("io", input={"number": number}))
    entered = 0
    peak = 0

    async def io(invocation, *, context):
        nonlocal entered, peak
        entered += 1
        peak = max(peak, entered)
        source = {"number": [invocation.input["number"]]}
        accepted = await context.heartbeat(details=source)
        source["number"].append("mutated")
        await asyncio.sleep(0.02)
        entered -= 1
        if invocation.input["number"] == 2:
            worker.stop()
        return {"heartbeat": accepted, "latest": context.latest_details}

    worker = AsyncWorker(
        lambda: LocalWorkerDispatch(path, queues=("io",)), {"io": io}, concurrency=3, worker_id="local-async"
    )
    asyncio.run(asyncio.wait_for(worker.run(poll_interval=0.01), 5))

    assert peak == 3
    assert sorted(dispatch.collect()) == [
        (number + 1, {"heartbeat": {"number": [number]}, "latest": {"number": [number]}}) for number in range(3)
    ]


def test_native_access_factory_repeated_cancellation_transfers_ownership_and_closes_once():
    factory_entered = asyncio.Event()
    release_factory = asyncio.Event()
    closed = 0

    class Access:
        async def close(self):
            nonlocal closed
            closed += 1

    async def factory():
        factory_entered.set()
        await release_factory.wait()
        return Access()

    async def work(invocation, *, context):
        raise AssertionError("no Attempt")

    async def exercise():
        worker = AsyncWorker._from_async_access(factory, {"io": work}, concurrency=1)
        running = asyncio.create_task(worker.run())
        await factory_entered.wait()
        running.cancel("first")
        await asyncio.sleep(0)
        running.cancel("second")
        release_factory.set()
        with pytest.raises(asyncio.CancelledError):
            await running

    asyncio.run(exercise())
    assert closed == 1


def test_owned_provider_failure_that_settles_after_cancellation_wins():
    entered = asyncio.Event()
    release = asyncio.Event()

    async def operation():
        entered.set()
        await release.wait()
        raise RuntimeError("custody uncertain")

    async def exercise():
        task = asyncio.create_task(worker_module._owned(operation()))
        await entered.wait()
        task.cancel()
        await asyncio.sleep(0)
        release.set()
        with pytest.raises(RuntimeError, match="custody uncertain"):
            await task

    asyncio.run(exercise())


def test_terminal_failure_reaps_blocked_claim_result_without_another_claim():
    attempts = [_attempt(1), _attempt(2)]
    second_claim_entered = asyncio.Event()
    release_second_claim = asyncio.Event()
    release_terminal = asyncio.Event()
    claims = 0
    completed = []
    closed = 0

    class Access:
        async def ready(self):
            pass

        async def claim(self, slot):
            nonlocal claims
            claims += 1
            if claims == 1:
                return attempts[0]
            if claims == 2:
                second_claim_entered.set()
                await release_second_claim.wait()
                return attempts[1]
            raise AssertionError("a third claim must not be admitted")

        async def heartbeat(self, slot, attempt, *, details):
            return details

        async def complete(self, slot, attempt, result):
            completed.append(attempt)
            if attempt is attempts[0]:
                await release_terminal.wait()
                raise RuntimeError("terminal uncertain")

        async def fail(self, slot, attempt, error):
            raise AssertionError(error)

        async def wait(self, slot, timeout):
            return False

        async def close(self):
            nonlocal closed
            closed += 1

    async def work(invocation, *, context):
        return context.attempt_id

    async def exercise():
        worker = AsyncWorker._from_async_access(lambda: asyncio.sleep(0, result=Access()), {"io": work}, concurrency=3)
        running = asyncio.create_task(worker.run(poll_interval=0))
        await second_claim_entered.wait()
        release_terminal.set()
        await asyncio.sleep(0)
        release_second_claim.set()
        with pytest.raises(RuntimeError, match="terminal uncertain"):
            await running

    asyncio.run(exercise())
    assert claims == 2
    assert completed == attempts
    assert closed == 1


def test_repeated_cancellation_drains_known_claim_activity_terminal_and_blocked_close_once():
    attempt = _attempt(1)
    claim_entered = asyncio.Event()
    release_claim = asyncio.Event()
    activity_entered = asyncio.Event()
    release_activity = asyncio.Event()
    close_entered = asyncio.Event()
    release_close = asyncio.Event()
    events = []
    claims = 0
    closes = 0

    class Access:
        async def ready(self):
            pass

        async def claim(self, slot):
            nonlocal claims
            claims += 1
            claim_entered.set()
            await release_claim.wait()
            return attempt

        async def heartbeat(self, slot, attempt, *, details):
            return details

        async def complete(self, slot, claimed, result):
            events.append(("terminal", claimed, result))

        async def fail(self, slot, attempt, error):
            raise AssertionError(error)

        async def wait(self, slot, timeout):
            return False

        async def close(self):
            nonlocal closes
            closes += 1
            close_entered.set()
            await release_close.wait()
            events.append(("close",))

    async def work(invocation, *, context):
        activity_entered.set()
        await release_activity.wait()
        return "done"

    async def exercise():
        worker = AsyncWorker._from_async_access(lambda: asyncio.sleep(0, result=Access()), {"io": work}, concurrency=1)
        running = asyncio.create_task(worker.run(poll_interval=0))
        await claim_entered.wait()
        running.cancel("claim-1")
        running.cancel("claim-2")
        release_claim.set()
        await activity_entered.wait()
        running.cancel("activity-1")
        running.cancel("activity-2")
        release_activity.set()
        await close_entered.wait()
        running.cancel("close-1")
        running.cancel("close-2")
        release_close.set()
        with pytest.raises(asyncio.CancelledError):
            await running

    asyncio.run(exercise())
    assert claims == 1
    assert closes == 1
    assert events == [("terminal", attempt, "done"), ("close",)]


def test_repeated_cancellation_keeps_terminal_failure_primary_and_retrieves_factory_failure():
    async def work(invocation, *, context):
        return "done"

    async def terminal_case():
        entered = asyncio.Event()
        release = asyncio.Event()

        class Access:
            claimed = False

            async def ready(self):
                pass

            async def claim(self, slot):
                if self.claimed:
                    return None
                self.claimed = True
                return _attempt(1)

            async def complete(self, slot, attempt, result):
                entered.set()
                await release.wait()
                raise RuntimeError("terminal failed")

            async def fail(self, slot, attempt, error):
                raise AssertionError(error)

            async def heartbeat(self, slot, attempt, *, details):
                return details

            async def wait(self, slot, timeout):
                return False

            async def close(self):
                pass

        running = asyncio.create_task(
            AsyncWorker._from_async_access(lambda: asyncio.sleep(0, result=Access()), {"io": work}, concurrency=1).run(  # noqa: E501
                poll_interval=0
            )
        )
        await entered.wait()
        running.cancel()
        running.cancel()
        release.set()
        with pytest.raises(RuntimeError, match="terminal failed"):
            await running

    async def factory_case():
        entered = asyncio.Event()
        release = asyncio.Event()

        async def factory():
            entered.set()
            await release.wait()
            raise RuntimeError("factory failed")

        running = asyncio.create_task(AsyncWorker._from_async_access(factory, {"io": work}, concurrency=1).run())
        await entered.wait()
        running.cancel()
        running.cancel()
        release.set()
        with pytest.raises(RuntimeError, match="factory failed"):
            await running

    asyncio.run(terminal_case())
    asyncio.run(factory_case())


def test_same_turn_terminal_failures_surface_first_created_slot_error():
    attempts = [_attempt(1), _attempt(2)]
    both_terminal = asyncio.Event()
    terminal_count = 0

    class Access:
        claims = 0

        async def ready(self):
            pass

        async def claim(self, slot):
            if self.claims == 2:
                return None
            attempt = attempts[self.claims]
            self.claims += 1
            return attempt

        async def complete(self, slot, attempt, result):
            nonlocal terminal_count
            terminal_count += 1
            if terminal_count == 2:
                both_terminal.set()
            await both_terminal.wait()
            raise RuntimeError(f"slot {slot} failed")

        async def fail(self, slot, attempt, error):
            raise AssertionError(error)

        async def heartbeat(self, slot, attempt, *, details):
            return details

        async def wait(self, slot, timeout):
            return False

        async def close(self):
            pass

    async def work(invocation, *, context):
        return None

    with pytest.raises(RuntimeError, match="slot 0 failed"):
        asyncio.run(
            AsyncWorker._from_async_access(lambda: asyncio.sleep(0, result=Access()), {"io": work}, concurrency=2).run(
                poll_interval=0
            )
        )


def test_uncertain_native_claim_stops_admission_and_closes():
    claims = 0
    closed = 0

    class Access:
        async def ready(self):
            pass

        async def claim(self, slot):
            nonlocal claims
            claims += 1
            raise RuntimeError("claim outcome uncertain")

        async def heartbeat(self, slot, attempt, *, details):
            raise AssertionError("no known Attempt")

        async def complete(self, slot, attempt, result):
            raise AssertionError("no known Attempt")

        async def fail(self, slot, attempt, error):
            raise AssertionError("no known Attempt")

        async def wait(self, slot, timeout):
            raise AssertionError("uncertain claim must stop before wait")

        async def close(self):
            nonlocal closed
            closed += 1

    async def work(invocation, *, context):
        raise AssertionError("an uncertain claim has no executable Attempt")

    with pytest.raises(RuntimeError, match="claim outcome uncertain"):
        asyncio.run(
            AsyncWorker._from_async_access(lambda: asyncio.sleep(0, result=Access()), {"io": work}, concurrency=4).run()
        )
    assert claims == 1
    assert closed == 1
