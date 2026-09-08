"""Production acceptance for optional ZeroMQ Worker Dispatch mediation."""

from __future__ import annotations

import asyncio
import json
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest
import zmq
import zmq.auth

import petrus.motus.transport.zeromq as zeromq
from petrus.motus.activity import ActivityFailure, ActivityInvocation, ExecutionPolicy, _OMITTED
from petrus.motus.dispatch import CancellationDisposition, CancellationInstruction
from petrus.motus.dispatch.local import LocalDispatch, LocalWorkerDispatch
from petrus.motus.transport.zeromq import (
    AsyncZeroMQWorkerAccess,
    OperationUncertain,
    ZeroMQDispatchServer,
    ZeroMQWorkerDispatch,
)
from petrus.motus.worker import AsyncWorker


def test_zap_domain_preserves_the_operational_protocol_identity() -> None:
    assert zeromq._ZAP_DOMAIN == "impetus.dispatch.worker.v2"


class RunningServer:
    def __init__(self, server: ZeroMQDispatchServer):
        self.server = server
        self.error: BaseException | None = None

        def run() -> None:
            try:
                server.serve_forever()
            except BaseException as error:
                self.error = error

        self.thread = threading.Thread(target=run)
        self.thread.start()
        self.endpoint = server.wait_ready()

    def close(self) -> None:
        self.server.stop()
        self.thread.join(5)
        assert not self.thread.is_alive()
        if self.error is not None:
            raise self.error


@pytest.fixture
def curve_certificates(tmp_path: Path):
    certificates = tmp_path / "certificates"
    allowed = tmp_path / "allowed"
    certificates.mkdir()
    allowed.mkdir()
    server_public, server_secret = zmq.auth.create_certificates(certificates, "server")
    client_public, client_secret = zmq.auth.create_certificates(certificates, "client")
    _, stranger_secret = zmq.auth.create_certificates(certificates, "stranger")
    other_server_public, _ = zmq.auth.create_certificates(certificates, "other-server")
    shutil.copy(client_public, allowed / "client.key")
    return {
        "server_public": Path(server_public),
        "server_secret": Path(server_secret),
        "client_secret": Path(client_secret),
        "stranger_secret": Path(stranger_secret),
        "other_server_public": Path(other_server_public),
        "allowed": allowed,
    }


def invocation(*, attempts: int = 2, heartbeat_timeout: int = 2) -> ActivityInvocation:
    return ActivityInvocation(
        "work",
        input={"nested": [1, {"faithful": True}]},
        policy=ExecutionPolicy(attempts, heartbeat_timeout),
        correlation="correlation",
        idempotency="idempotency",
    )


def test_ipc_round_trips_attempt_heartbeat_null_and_terminal_fencing(tmp_path: Path) -> None:
    path = tmp_path / "dispatch.sqlite3"
    endpoint = f"ipc://{tmp_path}/dispatch.sock"
    dispatch = LocalDispatch(path, instance="instance", activity_queues={"work": "cpu"})
    dispatch.dispatch(1, invocation())
    running = RunningServer(ZeroMQDispatchServer.local(endpoint, path, allowed_queues=("cpu", "io")))
    client = ZeroMQWorkerDispatch(running.endpoint, queues=("cpu",), worker_id="remote-cpu")
    try:
        attempt = client.claim()
        assert attempt is not None
        assert attempt.queue == "cpu"
        assert attempt.invocation == invocation()
        assert client.heartbeat(attempt, details={"progress": [1, 2]}) == {"progress": [1, 2]}
        assert client.heartbeat(attempt) == {"progress": [1, 2]}
        assert client.heartbeat(attempt, details=None) is None
        client.complete(attempt, {"completed": [True]})
        client.complete(attempt, {"completed": [True]})
        assert dispatch.collect() == ((1, {"completed": [True]}),)
        with pytest.raises(ValueError, match="stale Activity attempt"):
            client.heartbeat(attempt)
        with pytest.raises(ValueError, match="conflicting terminal report"):
            client.complete(attempt, {"completed": [False]})
    finally:
        client.close()
        running.close()


def test_ipc_round_trips_v2_policy_and_classified_failure_for_sync_and_async_clients(tmp_path: Path) -> None:
    path = tmp_path / "dispatch.sqlite3"
    endpoint = f"ipc://{tmp_path}/v2-dispatch.sock"
    policy = ExecutionPolicy(
        attempts=3,
        heartbeat_timeout=4,
        initial_interval=5,
        coefficient=3,
        max_interval=20,
        start_to_close=40,
        schedule_to_close=90,
    )
    call = ActivityInvocation(
        "work",
        input={"operation": "stable"},
        policy=policy,
        correlation="correlation",
        idempotency="idempotency",
    )
    failure = ActivityFailure(
        "invalid",
        kind="InvalidRequest",
        details={"field": "name"},
        retryable=False,
        retry_after=7,
    )
    dispatch = LocalDispatch(path, instance="v2")
    dispatch.dispatch(1, call)
    dispatch.dispatch(2, call)
    running = RunningServer(ZeroMQDispatchServer.local(endpoint, path, allowed_queues=("default",)))
    client = ZeroMQWorkerDispatch(running.endpoint)

    async def fail_second() -> None:
        access = await AsyncZeroMQWorkerAccess.create(running.endpoint)
        try:
            attempt = await access.claim(0)
            assert attempt is not None and attempt.invocation == call
            await access.fail(0, attempt, failure)
        finally:
            await access.close()

    try:
        first = client.claim()
        assert first is not None and first.invocation == call
        client.fail(first, failure)
        asyncio.run(fail_second())
        assert dispatch.collect() == ((1, failure), (2, failure))
    finally:
        client.close()
        running.close()


def test_async_ipc_direct_claim_heartbeat_completion_fencing_and_idempotent_close(tmp_path: Path) -> None:
    path = tmp_path / "dispatch.sqlite3"
    endpoint = f"ipc://{tmp_path}/async-dispatch.sock"
    dispatch = LocalDispatch(path, instance="async-direct", activity_queues={"work": "cpu"})
    dispatch.dispatch(1, invocation())
    running = RunningServer(ZeroMQDispatchServer.local(endpoint, path, allowed_queues=("cpu",)))

    async def exercise():
        access = await AsyncZeroMQWorkerAccess.create(running.endpoint, queues=("cpu",), worker_id="direct")
        attempt = await access.claim(0)
        assert attempt is not None
        assert await access.heartbeat(0, attempt, details={"cursor": 1}) == {"cursor": 1}
        assert await access.heartbeat(0, attempt) == {"cursor": 1}
        assert await access.heartbeat(0, attempt, details=None) is None
        await access.complete(0, attempt, {"done": True})
        with pytest.raises(ValueError, match="stale Activity attempt"):
            await access.heartbeat(0, attempt)
        await access.close()
        await access.close()

    try:
        asyncio.run(exercise())
        assert dispatch.collect() == ((1, {"done": True}),)
    finally:
        running.close()


def test_sync_and_async_transport_clients_observe_lifecycle_cancellation_fences(tmp_path: Path) -> None:
    path = tmp_path / "dispatch.sqlite3"
    endpoint = f"ipc://{tmp_path}/cancel-dispatch.sock"
    call = invocation()
    dispatch = LocalDispatch(path, instance="cancelled")
    dispatch.dispatch(1, call)
    dispatch.dispatch(2, call)
    running = RunningServer(ZeroMQDispatchServer.local(endpoint, path, allowed_queues=("default",)))
    client = ZeroMQWorkerDispatch(running.endpoint, worker_id="sync")

    async def exercise_async() -> None:
        access = await AsyncZeroMQWorkerAccess.create(running.endpoint, worker_id="async")
        try:
            attempt = await access.claim(0)
            assert attempt is not None
            occurrence = json.loads(attempt.attempt_id)[1]
            assert dispatch.cancel(CancellationInstruction(occurrence, call, 12)) is CancellationDisposition.FENCED
            with pytest.raises(ValueError, match="stale Activity attempt"):
                await access.heartbeat(0, attempt)
            await access.complete(0, attempt, {"client": "async", "effect": "ambiguous"})
        finally:
            await access.close()

    try:
        attempt = client.claim()
        assert attempt is not None
        occurrence = json.loads(attempt.attempt_id)[1]
        assert dispatch.cancel(CancellationInstruction(occurrence, call, 11)) is CancellationDisposition.FENCED
        with pytest.raises(ValueError, match="stale Activity attempt"):
            client.heartbeat(attempt)
        client.complete(attempt, {"client": "sync", "effect": "ambiguous"})
        asyncio.run(exercise_async())
        assert {outcome["client"] for _, outcome in dispatch.collect()} == {"sync", "async"}
    finally:
        client.close()
        running.close()


def test_async_access_refuses_wrong_loop_and_owner_close_remains_idempotent(tmp_path: Path) -> None:
    async def exercise():
        access = await AsyncZeroMQWorkerAccess.create(f"ipc://{tmp_path}/unused.sock")
        errors = await asyncio.to_thread(_use_async_access_from_new_loop, access)
        assert len(errors) == 1
        assert "owning event loop" in str(errors[0])
        await access.close()
        await access.close()

    asyncio.run(exercise())


def _use_async_access_from_new_loop(access):
    errors = []

    async def use():
        try:
            await access.ready()
        except BaseException as error:
            errors.append(error)

    asyncio.run(use())
    return errors


@pytest.mark.parametrize("asynchronous", [False, True])
def test_worker_socket_setup_failure_closes_new_socket(monkeypatch, tmp_path: Path, asynchronous: bool) -> None:
    class Socket:
        closed = 0

        def __setattr__(self, name, value):
            if name == "sndhwm":
                raise RuntimeError("option refused")
            object.__setattr__(self, name, value)

        def close(self, *, linger):
            assert linger == 0
            self.closed += 1

    class Context:
        def __init__(self):
            self.socket_value = Socket()

        def socket(self, kind):
            assert kind == zmq.DEALER
            return self.socket_value

        def term(self):
            pass

    context = Context()

    if asynchronous:

        async def exercise():
            access = await AsyncZeroMQWorkerAccess.create(f"ipc://{tmp_path}/unused.sock")
            access._context.term()
            access._context = context
            with pytest.raises(RuntimeError, match="option refused"):
                access._open_socket()
            assert context.socket_value.closed == 1
            await access.close()

        asyncio.run(exercise())
    else:
        access = ZeroMQWorkerDispatch(f"ipc://{tmp_path}/unused.sock")
        access._context.term()
        access._context = context
        with pytest.raises(RuntimeError, match="option refused"):
            access._open_socket()
        assert context.socket_value.closed == 1
        access.close()


def test_async_send_cancellation_boundary_and_permit_wait_are_distinct(tmp_path: Path) -> None:
    class Socket:
        def __init__(self):
            self.send_entered = asyncio.Event()
            self.release = asyncio.Event()
            self.closed = 0

        async def send(self, payload):
            self.send_entered.set()
            await self.release.wait()

        async def recv_multipart(self):
            raise AssertionError("send did not finish")

        def close(self, *, linger):
            self.closed += 1

    async def exercise():
        access = await AsyncZeroMQWorkerAccess.create(f"ipc://{tmp_path}/unused.sock", max_in_flight_operations=1)
        socket = Socket()
        access._open_socket = lambda: socket
        sending = asyncio.create_task(access.claim(0))
        await socket.send_entered.wait()
        waiting = asyncio.create_task(access.claim(1))
        await asyncio.sleep(0)
        waiting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiting
        sending.cancel()
        with pytest.raises(OperationUncertain, match="outcome is uncertain"):
            await sending
        assert socket.closed == 1
        await access.close()

    asyncio.run(exercise())


def test_async_completion_retries_identical_payload_with_fresh_bounded_sockets(tmp_path: Path) -> None:
    payloads = []
    sockets = []
    live = 0
    peak = 0

    class Socket:
        def __init__(self):
            nonlocal live, peak
            live += 1
            peak = max(peak, live)
            self.closed = False

        async def send(self, payload):
            payloads.append(payload)

        async def recv_multipart(self):
            raise TimeoutError

        def close(self, *, linger):
            nonlocal live
            assert not self.closed
            self.closed = True
            live -= 1

    async def exercise():
        access = await AsyncZeroMQWorkerAccess.create(
            f"ipc://{tmp_path}/unused.sock", request_timeout=0.001, terminal_timeout=0.02, max_in_flight_operations=1
        )

        def open_socket():
            socket = Socket()
            sockets.append(socket)
            return socket

        access._open_socket = open_socket
        with pytest.raises(OperationUncertain, match="sent but not acknowledged"):
            await access.complete(0, _attempt_for_transport(), {"same": [1]})
        assert len(payloads) >= 2
        assert len(set(payloads)) == 1
        assert all(socket.closed for socket in sockets)
        assert peak == 1 and live == 0
        await access.close()

    asyncio.run(exercise())


def _attempt_for_transport():
    from petrus.motus.dispatch import ActivityAttempt

    return ActivityAttempt("attempt", "epoch", "claimant", "default", invocation(), instance="instance")


def test_v2_attempt_wire_requires_and_preserves_nullable_instance():
    encoded = zeromq._encode_attempt(_attempt_for_transport())
    assert set(encoded) == {
        "attempt_id",
        "epoch",
        "claimant",
        "queue",
        "invocation",
        "latest_details",
        "instance",
    }
    assert zeromq._decode_attempt(encoded).instance == "instance"
    encoded["instance"] = None
    assert zeromq._decode_attempt(encoded).instance is None
    del encoded["instance"]
    with pytest.raises(ValueError, match="requires exactly"):
        zeromq._decode_attempt(encoded)


def test_ipc_async_worker_uses_concurrent_zeromq_owner_lanes_and_heartbeats(tmp_path: Path) -> None:
    path = tmp_path / "dispatch.sqlite3"
    endpoint = f"ipc://{tmp_path}/dispatch.sock"
    dispatch = LocalDispatch(path, instance="async-zmq", activity_queues={"work": "io"})
    for number in range(3):
        dispatch.dispatch(number + 1, ActivityInvocation("work", input={"number": number}))
    running = RunningServer(ZeroMQDispatchServer.local(endpoint, path, allowed_queues=("io",)))
    entered = 0
    peak = 0

    async def work(activity_invocation, *, context):
        nonlocal entered, peak
        entered += 1
        peak = max(peak, entered)
        details = await context.heartbeat(details={"number": activity_invocation.input["number"]})
        await asyncio.sleep(0.02)
        entered -= 1
        if activity_invocation.input["number"] == 2:
            worker.stop()
        return details

    worker = AsyncWorker._from_async_access(
        lambda: AsyncZeroMQWorkerAccess.create(running.endpoint, queues=("io",), worker_id="async-zmq"),
        {"work": work},
        concurrency=3,
    )
    try:
        asyncio.run(asyncio.wait_for(worker.run(poll_interval=0.01), 5))
        assert peak == 3
        assert sorted(dispatch.collect()) == [(number + 1, {"number": number}) for number in range(3)]
    finally:
        running.close()


def test_queue_allowlist_drain_and_thread_ownership_are_explicit(tmp_path: Path) -> None:
    path = tmp_path / "dispatch.sqlite3"
    endpoint = f"ipc://{tmp_path}/dispatch.sock"
    dispatch = LocalDispatch(path, instance="instance")
    dispatch.dispatch(1, invocation())
    server = ZeroMQDispatchServer.local(endpoint, path, allowed_queues=("default",))
    running = RunningServer(server)
    refused = ZeroMQWorkerDispatch(endpoint, queues=("admin",), request_timeout=0.5)
    client = ZeroMQWorkerDispatch(endpoint, request_timeout=0.5)
    try:
        with pytest.raises(ValueError, match="outside the server allowlist"):
            refused.claim()
        errors: list[BaseException] = []

        def cross_thread() -> None:
            try:
                client.claim()
            except BaseException as error:
                errors.append(error)

        thread = threading.Thread(target=cross_thread)
        thread.start()
        thread.join()
        assert len(errors) == 1 and "owning thread" in str(errors[0])
        attempt = client.claim()
        assert attempt is not None
        assert attempt.instance == "instance"
        server.request_drain(2)
        client.complete(attempt, "drained")
        assert dispatch.collect() == ((1, "drained"),)
        assert client.claim() is None
    finally:
        refused.close()
        client.close()
        running.close()


def test_ipc_second_server_is_refused_before_zeromq_can_steal_the_binding(tmp_path: Path) -> None:
    path = tmp_path / "dispatch.sqlite3"
    endpoint = f"ipc://{tmp_path}/dispatch.sock"
    first = RunningServer(ZeroMQDispatchServer.local(endpoint, path, allowed_queues=("default",)))
    second = ZeroMQDispatchServer.local(endpoint, path, allowed_queues=("default",))
    try:
        with pytest.raises(RuntimeError, match="endpoint is already owned"):
            second.serve_forever()
    finally:
        first.close()


def test_curve_tcp_allows_approved_key_and_times_out_unapproved_key(tmp_path: Path, curve_certificates) -> None:
    path = tmp_path / "dispatch.sqlite3"
    dispatch = LocalDispatch(path, instance="instance")
    dispatch.dispatch(1, invocation())
    dispatch.dispatch(2, invocation())
    server = ZeroMQDispatchServer.local(
        "tcp://127.0.0.1:*",
        path,
        allowed_queues=("default",),
        server_secret_certificate=curve_certificates["server_secret"],
        allowed_client_keys=curve_certificates["allowed"],
    )
    running = RunningServer(server)
    approved = ZeroMQWorkerDispatch(
        running.endpoint,
        client_secret_certificate=curve_certificates["client_secret"],
        server_public_certificate=curve_certificates["server_public"],
        request_timeout=1,
    )
    stranger = ZeroMQWorkerDispatch(
        running.endpoint,
        client_secret_certificate=curve_certificates["stranger_secret"],
        server_public_certificate=curve_certificates["server_public"],
        request_timeout=0.2,
    )
    wrong_server = ZeroMQWorkerDispatch(
        running.endpoint,
        client_secret_certificate=curve_certificates["client_secret"],
        server_public_certificate=curve_certificates["other_server_public"],
        request_timeout=0.2,
    )
    try:
        with pytest.raises(ConnectionError, match="was not acknowledged"):
            stranger.claim()
        with pytest.raises(ConnectionError, match="was not acknowledged"):
            wrong_server.claim()
        attempt = approved.claim()
        assert attempt is not None
        approved.complete(attempt, "accepted")

        async def native_flow():
            native = await AsyncZeroMQWorkerAccess.create(
                running.endpoint,
                client_secret_certificate=curve_certificates["client_secret"],
                server_public_certificate=curve_certificates["server_public"],
                request_timeout=1,
            )
            native_attempt = await native.claim(0)
            assert native_attempt is not None
            await native.complete(0, native_attempt, "native accepted")
            await native.close()

        asyncio.run(native_flow())
        assert dispatch.collect() == ((1, "accepted"), (2, "native accepted"))
    finally:
        wrong_server.close()
        stranger.close()
        approved.close()
        running.close()


def test_public_only_server_certificate_fails_before_starting_authenticator(tmp_path: Path, curve_certificates) -> None:
    with pytest.raises(ValueError, match="server certificate must contain a public and secret key"):
        ZeroMQDispatchServer.local(
            "tcp://127.0.0.1:*",
            tmp_path / "dispatch.sqlite3",
            allowed_queues=("default",),
            server_secret_certificate=curve_certificates["server_public"],
            allowed_client_keys=curve_certificates["allowed"],
        )


@pytest.mark.parametrize("endpoint", ["tcp://127.0.0.1:5000", "ipc:///tmp/impetus-test"])
def test_tcp_requires_curve_and_ipc_rejects_curve_configuration(tmp_path: Path, endpoint: str) -> None:
    if endpoint.startswith("tcp"):
        with pytest.raises(ValueError, match="requires client secret and server public"):
            ZeroMQWorkerDispatch(endpoint)
        with pytest.raises(ValueError, match="requires a server secret certificate"):
            ZeroMQDispatchServer.local(endpoint, tmp_path / "db", allowed_queues=("default",))
    else:
        with pytest.raises(ValueError, match="rejects TCP CURVE"):
            ZeroMQWorkerDispatch(endpoint, client_secret_certificate="client", server_public_certificate="server")
        with pytest.raises(ValueError, match="rejects TCP CURVE"):
            ZeroMQDispatchServer.local(
                endpoint,
                tmp_path / "db",
                allowed_queues=("default",),
                server_secret_certificate="server",
                allowed_client_keys="clients",
            )


@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_request_terminal_and_drain_timeouts_are_refused(tmp_path: Path, timeout: float) -> None:
    endpoint = f"ipc://{tmp_path}/dispatch.sock"
    with pytest.raises(ValueError, match="finite non-negative"):
        ZeroMQWorkerDispatch(endpoint, request_timeout=timeout)
    with pytest.raises(ValueError, match="finite non-negative"):
        ZeroMQWorkerDispatch(endpoint, terminal_timeout=timeout)
    server = ZeroMQDispatchServer.local(endpoint, tmp_path / "dispatch.sqlite3", allowed_queues=("default",))
    with pytest.raises(ValueError, match="finite non-negative"):
        server.request_drain(timeout)


class DelayedProvider:
    """Inject reply-loss windows after custody has already committed."""

    def __init__(self, provider: LocalWorkerDispatch, delays: dict[str, float]):
        self.provider = provider
        self.delays = delays

    def claim(self):
        attempt = self.provider.claim()
        time.sleep(self.delays.pop("claim", 0))
        return attempt

    def heartbeat(self, attempt, *, details=_OMITTED):
        latest = (
            self.provider.heartbeat(attempt)
            if details is _OMITTED
            else self.provider.heartbeat(attempt, details=details)
        )
        time.sleep(self.delays.pop("heartbeat", 0))
        return latest

    def complete(self, attempt, result):
        self.provider.complete(attempt, result)
        time.sleep(self.delays.pop("complete", 0))

    def fail(self, attempt, error):
        self.provider.fail(attempt, error)
        time.sleep(self.delays.pop("fail", 0))

    def wait(self, timeout):
        return self.provider.wait(timeout)

    def close(self):
        self.provider.close()


def test_async_lost_claim_reply_is_uncertain_and_not_replayed(tmp_path: Path) -> None:
    path = tmp_path / "dispatch.sqlite3"
    endpoint = f"ipc://{tmp_path}/async-lost-claim.sock"
    dispatch = LocalDispatch(path, instance="async-lost-claim")
    dispatch.dispatch(1, invocation(heartbeat_timeout=1))
    calls = Counter()

    class CountingDelayed(DelayedProvider):
        def claim(self):
            calls["claim"] += 1
            return super().claim()

    def factory(queues, worker_id):
        return CountingDelayed(LocalWorkerDispatch(path, queues=queues, worker_id=worker_id), {"claim": 0.2})

    running = RunningServer(ZeroMQDispatchServer._from_factory(endpoint, factory))

    async def exercise():
        access = await AsyncZeroMQWorkerAccess.create(endpoint, request_timeout=0.05)
        try:
            with pytest.raises(OperationUncertain, match="claim.*not acknowledged"):
                await access.claim(0)
        finally:
            await access.close()

    try:
        asyncio.run(exercise())
        assert calls == {"claim": 1}
        _assert_task(path, epoch=1)
    finally:
        running.close()


def test_async_lost_heartbeat_and_failure_replies_are_not_replayed(tmp_path: Path) -> None:
    path = tmp_path / "dispatch.sqlite3"
    endpoint = f"ipc://{tmp_path}/async-lost-nonterminal.sock"
    dispatch = LocalDispatch(path, instance="async-lost-nonterminal")
    dispatch.dispatch(1, invocation(attempts=1))
    calls = Counter()

    class CountingDelayed(DelayedProvider):
        def heartbeat(self, attempt, *, details=_OMITTED):
            calls["heartbeat"] += 1
            return super().heartbeat(attempt, details=details)

        def fail(self, attempt, error):
            calls["fail"] += 1
            return super().fail(attempt, error)

    def factory(queues, worker_id):
        return CountingDelayed(
            LocalWorkerDispatch(path, queues=queues, worker_id=worker_id),
            {"heartbeat": 0.2, "fail": 0.2},
        )

    running = RunningServer(ZeroMQDispatchServer._from_factory(endpoint, factory))

    async def exercise():
        access = await AsyncZeroMQWorkerAccess.create(endpoint, request_timeout=0.05)
        try:
            attempt = await access.claim(0)
            assert attempt is not None
            with pytest.raises(OperationUncertain, match="heartbeat.*not acknowledged"):
                await access.heartbeat(0, attempt, details={"persisted": True})
            await asyncio.sleep(0.2)
            with pytest.raises(OperationUncertain, match="fail.*not acknowledged"):
                await access.fail(0, attempt, "final")
        finally:
            await access.close()

    try:
        asyncio.run(exercise())
        assert calls == {"heartbeat": 1, "fail": 1}
        assert dispatch.collect() == ((1, ActivityFailure("final", retryable=True)),)
    finally:
        running.close()


def test_lost_claim_reply_is_not_blindly_replayed_and_recovers_by_lease_expiry(tmp_path: Path) -> None:
    path = tmp_path / "dispatch.sqlite3"
    endpoint = f"ipc://{tmp_path}/dispatch.sock"
    dispatch = LocalDispatch(path, instance="instance")
    dispatch.dispatch(1, invocation(heartbeat_timeout=1))

    def factory(queues, worker_id):
        return DelayedProvider(LocalWorkerDispatch(path, queues=queues, worker_id=worker_id), {"claim": 0.2})

    running = RunningServer(ZeroMQDispatchServer._from_factory(endpoint, factory))
    client = ZeroMQWorkerDispatch(endpoint, request_timeout=0.05)
    try:
        with pytest.raises(ConnectionError, match="claim.*not acknowledged"):
            client.claim()
        # One claim reached custody. A blind RPC retry would have incremented
        # another task or epoch; instead the only task remains leased at epoch 1.
        with pytest.raises(AssertionError, match="unexpected task row"):
            _assert_task(path, epoch=2)
        _assert_task(path, epoch=1)
        time.sleep(1.05)
        replacement = LocalWorkerDispatch(path, _claimant="replacement").claim()
        assert replacement is not None and replacement.epoch == "2"
    finally:
        client.close()
        running.close()


def _assert_task(path: Path, *, epoch: int) -> None:
    with sqlite3.connect(path) as connection:
        row = connection.execute("SELECT epoch FROM impetus_local_dispatch_tasks").fetchone()
    assert row == (epoch,), f"unexpected task row {row!r}"


def test_lost_terminal_reply_is_redelivered_exactly_until_acknowledged(tmp_path: Path) -> None:
    path = tmp_path / "dispatch.sqlite3"
    endpoint = f"ipc://{tmp_path}/dispatch.sock"
    dispatch = LocalDispatch(path, instance="instance")
    dispatch.dispatch(1, invocation())
    delays = {"complete": 0.2}

    def factory(queues, worker_id):
        return DelayedProvider(LocalWorkerDispatch(path, queues=queues, worker_id=worker_id), delays)

    running = RunningServer(ZeroMQDispatchServer._from_factory(endpoint, factory))
    client = ZeroMQWorkerDispatch(endpoint, terminal_timeout=1)
    try:
        attempt = client.claim()
        assert attempt is not None
        # Only completion needs the short deadline that forces reply loss.
        client.request_timeout = 0.05
        client.complete(attempt, {"durable": True})
        assert dispatch.collect() == ((1, {"durable": True}),)
    finally:
        client.close()
        running.close()


def _start_delayed_completion_server_process(path: Path, endpoint: str, committed: Path) -> subprocess.Popen[str]:
    code = f"""
import json
import threading
import time
from pathlib import Path
from petrus.motus.dispatch.local import LocalWorkerDispatch
from petrus.motus.transport.zeromq import ZeroMQDispatchServer

class Delayed:
    def __init__(self, provider): self.provider = provider
    def claim(self): return self.provider.claim()
    def heartbeat(self, attempt, *, details): return self.provider.heartbeat(attempt, details=details)
    def complete(self, attempt, result):
        self.provider.complete(attempt, result)
        Path({str(committed)!r}).write_text('committed')
        time.sleep(10)
    def fail(self, attempt, error): return self.provider.fail(attempt, error)
    def wait(self, timeout): return self.provider.wait(timeout)
    def close(self): return self.provider.close()

def factory(queues, worker_id):
    return Delayed(LocalWorkerDispatch({str(path)!r}, queues=queues, worker_id=worker_id))

server = ZeroMQDispatchServer._from_factory({endpoint!r}, factory)
def announce():
    print(json.dumps({{'ready': True, 'endpoint': server.wait_ready()}}), flush=True)
threading.Thread(target=announce, daemon=True).start()
server.serve_forever()
"""
    process = subprocess.Popen(
        [sys.executable, "-c", code],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdout is not None
    event = json.loads(process.stdout.readline())
    assert event == {"ready": True, "endpoint": endpoint}
    return process


def test_uncertain_completion_redelivers_exactly_across_dispatch_process_death(tmp_path: Path) -> None:
    path = tmp_path / "dispatch.sqlite3"
    endpoint = f"ipc://{tmp_path}/dispatch.sock"
    committed = tmp_path / "completion-committed"
    dispatch = LocalDispatch(path, instance="instance")
    dispatch.dispatch(1, invocation())
    first = _start_delayed_completion_server_process(path, endpoint, committed)
    client = ZeroMQWorkerDispatch(endpoint, request_timeout=0.1, terminal_timeout=3)
    replacement: list[subprocess.Popen[str]] = []
    killer_errors: list[BaseException] = []
    try:
        attempt = client.claim()
        assert attempt is not None

        def replace_server() -> None:
            try:
                deadline = time.monotonic() + 5
                while not committed.exists():
                    if time.monotonic() >= deadline:
                        raise TimeoutError("delayed server did not commit completion")
                    time.sleep(0.01)
                first.kill()
                first.communicate(timeout=5)
                replacement.append(_start_server_process(path, endpoint))
            except BaseException as error:
                killer_errors.append(error)

        killer = threading.Thread(target=replace_server)
        killer.start()
        client.complete(attempt, {"survived": "process death"})
        killer.join(5)
        assert not killer.is_alive() and not killer_errors
        assert dispatch.collect() == ((1, {"survived": "process death"}),)
    finally:
        client.close()
        if first.poll() is None:
            first.kill()
            first.communicate(timeout=5)
        for process in replacement:
            if process.poll() is None:
                process.terminate()
                process.communicate(timeout=5)


def test_lost_heartbeat_and_failure_replies_are_not_replayed(tmp_path: Path) -> None:
    path = tmp_path / "dispatch.sqlite3"
    endpoint = f"ipc://{tmp_path}/dispatch.sock"
    dispatch = LocalDispatch(path, instance="instance")
    delays = {"heartbeat": 0.2, "fail": 0.2}

    def factory(queues, worker_id):
        return DelayedProvider(LocalWorkerDispatch(path, queues=queues, worker_id=worker_id), delays)

    running = RunningServer(ZeroMQDispatchServer._from_factory(endpoint, factory))
    readiness = ZeroMQWorkerDispatch(endpoint)
    try:
        assert readiness.claim() is None
    finally:
        readiness.close()
    dispatch.dispatch(1, invocation(attempts=2))
    dispatch.dispatch(2, invocation(attempts=1))
    client = ZeroMQWorkerDispatch(endpoint, request_timeout=0.05)
    try:
        first = client.claim()
        assert first is not None
        with pytest.raises(ConnectionError, match="heartbeat.*not acknowledged"):
            client.heartbeat(first, details={"persisted": True})
        with sqlite3.connect(path) as connection:
            details = connection.execute(
                "SELECT details FROM impetus_local_dispatch_tasks WHERE occurrence=1"
            ).fetchone()[0]
        assert json.loads(details) == {"persisted": True}
        time.sleep(0.2)
        with pytest.raises(ConnectionError, match="fail.*not acknowledged"):
            client.fail(first, "retry")
        time.sleep(0.25)
        replacement = client.claim()
        assert replacement is not None and replacement.epoch == "2"
        client.complete(replacement, "recovered")

        final = client.claim()
        assert final is not None
        delays["fail"] = 0.2
        with pytest.raises(ConnectionError, match="fail.*not acknowledged"):
            client.fail(final, "final")
        assert dispatch.collect() == ((1, "recovered"), (2, ActivityFailure("final", retryable=True)))
    finally:
        client.close()
        running.close()


def test_protocol_refuses_widened_unknown_version_and_oversized_requests(tmp_path: Path) -> None:
    endpoint = f"ipc://{tmp_path}/dispatch.sock"
    server = ZeroMQDispatchServer(
        endpoint,
        tmp_path / "dispatch.sqlite3",
        allowed_queues=("default",),
        max_message_bytes=1_000,
    )
    running = RunningServer(server)
    context = zmq.Context()
    socket = context.socket(zmq.DEALER)
    socket.linger = 0
    socket.connect(endpoint)
    base = {
        "version": 2,
        "request_id": "request",
        "client_id": "client",
        "worker_id": "worker",
        "queues": ["default"],
        "operation": "claim",
    }
    try:
        for request, message in (
            ({**base, "extra": True}, "requires exactly"),
            ({**base, "version": 1}, "unsupported"),
            ({**base, "version": True}, "unsupported"),
            ({**base, "operation": "x" * 300}, "protocol limit"),
            ({**base, "padding": "x" * 1_500}, "maximum message size"),
        ):
            socket.send_json(request)
            response = socket.recv_json()
            assert response["ok"] is False
            assert response["error"]["kind"] == "protocol"
            assert message in response["error"]["message"]
        socket.send_multipart([json.dumps(base).encode(), b"extra"])
        response = socket.recv_json()
        assert response["error"]["kind"] == "protocol"
        assert "exactly one application frame" in response["error"]["message"]
        socket.send_json(base)
        assert socket.recv_json()["ok"] is True
    finally:
        socket.close()
        context.term()
        running.close()


def test_stale_attempt_payload_cannot_change_claimant_or_epoch(tmp_path: Path) -> None:
    path = tmp_path / "dispatch.sqlite3"
    endpoint = f"ipc://{tmp_path}/dispatch.sock"
    LocalDispatch(path, instance="instance").dispatch(1, invocation())
    running = RunningServer(ZeroMQDispatchServer.local(endpoint, path, allowed_queues=("default",)))
    client = ZeroMQWorkerDispatch(endpoint)
    try:
        attempt = client.claim()
        assert attempt is not None
        for stale in (
            replace(attempt, epoch="2"),
            replace(attempt, claimant="other"),
            replace(attempt, queue="other"),
            replace(
                attempt,
                invocation=replace(
                    attempt.invocation,
                    policy=ExecutionPolicy(attempts=2, heartbeat_timeout=3_600),
                ),
            ),
        ):
            with pytest.raises(ValueError, match="stale Activity attempt"):
                client.heartbeat(stale)
        client.complete(attempt, "done")
    finally:
        client.close()
        running.close()


def _start_server_process(path: Path, endpoint: str) -> subprocess.Popen[str]:
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "petrus.motus.transport.zeromq",
            "--path",
            str(path),
            "--bind",
            endpoint,
            "--queue",
            "default",
            "--drain-timeout",
            "0.1",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdout is not None
    event = json.loads(process.stdout.readline())
    assert event["ready"] is True and event["endpoint"] == endpoint
    return process


def test_dispatch_service_process_death_preserves_lease_details_and_restart_recovery(tmp_path: Path) -> None:
    path = tmp_path / "dispatch.sqlite3"
    endpoint = f"ipc://{tmp_path}/dispatch.sock"
    dispatch = LocalDispatch(path, instance="instance")
    dispatch.dispatch(1, invocation(heartbeat_timeout=1))
    first = _start_server_process(path, endpoint)
    first_client = ZeroMQWorkerDispatch(endpoint, request_timeout=0.5)
    second: subprocess.Popen[str] | None = None
    replacement: ZeroMQWorkerDispatch | None = None
    try:
        attempt = first_client.claim()
        assert attempt is not None
        assert first_client.heartbeat(attempt, details={"checkpoint": 4}) == {"checkpoint": 4}
        first.kill()
        first.communicate(timeout=5)
        with pytest.raises(ConnectionError, match="heartbeat.*not acknowledged"):
            first_client.heartbeat(attempt)

        second = _start_server_process(path, endpoint)
        assert first_client.heartbeat(attempt, details={"checkpoint": 5}) == {"checkpoint": 5}
        replacement = ZeroMQWorkerDispatch(endpoint, request_timeout=0.5)
        assert replacement.claim() is None
        time.sleep(1.05)
        reclaimed = replacement.claim()
        assert reclaimed is not None
        assert reclaimed.instance == "instance"
        assert reclaimed.epoch == "2" and reclaimed.latest_details == {"checkpoint": 5}
        replacement.complete(reclaimed, "recovered")
        assert dispatch.collect() == ((1, "recovered"),)
    finally:
        first_client.close()
        if replacement is not None:
            replacement.close()
        if first.poll() is None:
            first.kill()
            first.communicate(timeout=5)
        if second is not None and second.poll() is None:
            second.terminate()
            second.communicate(timeout=5)
            assert second.returncode == 0
