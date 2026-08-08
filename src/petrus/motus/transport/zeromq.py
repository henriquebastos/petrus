"""Optional ZeroMQ transport for the synchronous Worker Dispatch contract."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import signal
import threading
import time
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path
from types import ModuleType
from typing import cast

from petrus.motus.activity import ActivityInvocation, ExecutionPolicy, _OMITTED, snapshot_heartbeat_details
from petrus.motus.dispatch import ActivityAttempt, WorkerDispatch

fcntl: ModuleType | None
try:
    import fcntl as _fcntl
except ModuleNotFoundError:  # pragma: no cover - Windows has TCP but no POSIX IPC ownership fence
    fcntl = None
else:
    fcntl = _fcntl

try:
    import zmq
    import zmq.asyncio
    import zmq.auth
    from zmq.auth.thread import ThreadAuthenticator
except ModuleNotFoundError as error:  # pragma: no cover - exercised in a blocked-import subprocess
    raise ImportError(
        "ZeroMQ Dispatch Transport requires the optional 'zeromq' extra; install petrus[zeromq]"
    ) from error

_VERSION = 1
_MAX_MESSAGE_BYTES = 1024 * 1024
_HWM = 4
_MAX_CLIENTS = 1_000
_MAX_IDENTITY_BYTES = 256
_MAX_QUEUE_COUNT = 32
_MAX_ERROR_BYTES = 1_024
_ZAP_DOMAIN = "impetus.dispatch.worker.v1"

_WorkerProviderFactory = Callable[[Sequence[str], str], WorkerDispatch]


class _ProtocolError(ValueError):
    pass


class OperationUncertain(ConnectionError):
    """A sent custody operation lost its definitive response."""


class AsyncZeroMQWorkerAccess:
    """Event-loop-owned native async Worker access over the v1 wire protocol."""

    def __init__(
        self,
        endpoint: str,
        *,
        queues: Sequence[str] = ("default",),
        worker_id: str | None = None,
        client_secret_certificate: Path | str | None = None,
        server_public_certificate: Path | str | None = None,
        request_timeout: float = 5.0,
        terminal_timeout: float = 30.0,
        max_in_flight_operations: int = 8,
    ):
        if isinstance(max_in_flight_operations, bool) or not isinstance(max_in_flight_operations, int):
            raise ValueError("ZeroMQ maximum in-flight operations must be a positive integer")
        if max_in_flight_operations <= 0:
            raise ValueError("ZeroMQ maximum in-flight operations must be a positive integer")
        self.endpoint = _endpoint(endpoint)
        self.queues = tuple(dict.fromkeys(_wire_name(queue, "queue") for queue in queues))
        if not 1 <= len(self.queues) <= _MAX_QUEUE_COUNT:
            raise ValueError(f"ZeroMQ Worker access requires from 1 to {_MAX_QUEUE_COUNT} queues")
        self.worker_id = _wire_name(worker_id or f"worker-{os.getpid()}", "worker id")
        self.client_id = str(uuid.uuid4())
        self.request_timeout = _timeout(request_timeout, "request timeout")
        self.terminal_timeout = _timeout(terminal_timeout, "terminal timeout")
        if self.request_timeout < 0.001 or self.terminal_timeout < 0.001:
            raise ValueError("ZeroMQ request and terminal timeouts must be at least one millisecond")
        client = Path(client_secret_certificate) if client_secret_certificate else None
        server = Path(server_public_certificate) if server_public_certificate else None
        self._curve_keys = _client_security(self.endpoint, client, server)
        self.max_in_flight_operations = max_in_flight_operations
        self.high_water_mark = _HWM
        self.max_message_bytes = _MAX_MESSAGE_BYTES
        self._loop = asyncio.get_running_loop()
        self._context = zmq.asyncio.Context()
        self._permits = asyncio.Semaphore(max_in_flight_operations)
        self._sockets: set[object] = set()
        self._closed = False

    @classmethod
    async def create(
        cls,
        endpoint: str,
        *,
        queues: Sequence[str] = ("default",),
        worker_id: str | None = None,
        client_secret_certificate: Path | str | None = None,
        server_public_certificate: Path | str | None = None,
        request_timeout: float = 5.0,
        terminal_timeout: float = 30.0,
        max_in_flight_operations: int = 8,
    ) -> AsyncZeroMQWorkerAccess:
        """Construct explicitly on the event loop that will own all sockets."""
        return cls(
            endpoint,
            queues=queues,
            worker_id=worker_id,
            client_secret_certificate=client_secret_certificate,
            server_public_certificate=server_public_certificate,
            request_timeout=request_timeout,
            terminal_timeout=terminal_timeout,
            max_in_flight_operations=max_in_flight_operations,
        )

    async def ready(self) -> None:
        self._check_owner()
        if self._closed:
            raise RuntimeError("ZeroMQ Worker access is closed")

    async def claim(self, slot: int) -> ActivityAttempt | None:
        del slot
        value = await self._rpc("claim", {})
        mapping = _exact(value, {"attempt"}, "claim result")
        return None if mapping["attempt"] is None else _decode_attempt(mapping["attempt"])

    async def heartbeat(self, slot: int, attempt: ActivityAttempt, *, details: object = _OMITTED) -> object:
        del slot
        fields = {"attempt": _encode_attempt(attempt)}
        if details is not _OMITTED:
            fields["details"] = snapshot_heartbeat_details(details)
        return _exact(await self._rpc("heartbeat", fields), {"details"}, "heartbeat result")["details"]

    async def complete(self, slot: int, attempt: ActivityAttempt, result: object) -> None:
        del slot
        value = await self._rpc(
            "complete",
            {"attempt": _encode_attempt(attempt), "result": _faithful(result, "Activity result")},
            retry_until=self._loop.time() + self.terminal_timeout,
        )
        if _exact(value, {"completed"}, "complete result") != {"completed": True}:
            raise RuntimeError("ZeroMQ Dispatch returned an invalid complete acknowledgement")

    async def fail(self, slot: int, attempt: ActivityAttempt, error: str | Exception) -> None:
        del slot
        spelling = error if isinstance(error, str) else repr(error)
        value = await self._rpc("fail", {"attempt": _encode_attempt(attempt), "error": spelling})
        if _exact(value, {"failed"}, "fail result") != {"failed": True}:
            raise RuntimeError("ZeroMQ Dispatch returned an invalid fail acknowledgement")

    async def wait(self, slot: int, timeout: float) -> bool:
        del slot
        await asyncio.sleep(_timeout(timeout, "wait timeout"))
        return False

    async def close(self) -> None:
        self._check_owner()
        if self._closed:
            return
        self._closed = True
        while self._sockets:
            await asyncio.sleep(0)
        self._context.term()

    async def _rpc(self, operation: str, fields: dict[str, object], *, retry_until: float | None = None) -> object:
        self._check_owner()
        if self._closed:
            raise RuntimeError("ZeroMQ Worker access is closed")
        request_id = str(uuid.uuid4())
        payload = _encode_message(
            {
                "version": _VERSION,
                "request_id": request_id,
                "client_id": self.client_id,
                "worker_id": self.worker_id,
                "queues": list(self.queues),
                "operation": operation,
                **fields,
            }
        )
        while True:
            potentially_applied = False
            async with self._permits:
                socket = self._open_socket()
                self._sockets.add(socket)
                try:
                    potentially_applied = True
                    await socket.send(payload)
                    frames = await asyncio.wait_for(socket.recv_multipart(), self.request_timeout)
                    if len(frames) != 1:
                        raise RuntimeError("ZeroMQ Dispatch server returned a multipart protocol violation")
                    return _decode_response(frames[0], request_id)
                except asyncio.CancelledError as error:
                    if potentially_applied:
                        raise OperationUncertain(
                            f"ZeroMQ Dispatch request {operation!r} outcome is uncertain"
                        ) from error
                    raise
                except (TimeoutError, zmq.Again, zmq.ZMQError) as error:
                    if retry_until is None or self._loop.time() >= retry_until:
                        raise OperationUncertain(
                            f"ZeroMQ Dispatch request {operation!r} was sent but not acknowledged"
                        ) from error
                finally:
                    socket.close(linger=0)
                    self._sockets.remove(socket)

    def _open_socket(self):
        socket = self._context.socket(zmq.DEALER)
        try:
            socket.linger = 0
            socket.sndhwm = _HWM
            socket.rcvhwm = _HWM
            socket.maxmsgsize = _MAX_MESSAGE_BYTES
            socket.immediate = True
            socket.sndtimeo = max(1, round(self.request_timeout * 1000))
            if self.endpoint.startswith("tcp://"):
                assert self._curve_keys is not None
                public, secret, server = self._curve_keys
                socket.curve_publickey = public
                socket.curve_secretkey = secret
                socket.curve_serverkey = server
            socket.connect(self.endpoint)
            return socket
        except BaseException:
            socket.close(linger=0)
            raise

    def _check_owner(self) -> None:
        if asyncio.get_running_loop() is not self._loop:
            raise RuntimeError("ZeroMQ Worker access may only be used by its owning event loop")


class ZeroMQWorkerDispatch:
    """Worker-facing Dispatch client over IPC or authenticated CURVE TCP."""

    def __init__(
        self,
        endpoint: str,
        *,
        queues: Sequence[str] = ("default",),
        worker_id: str | None = None,
        client_secret_certificate: Path | str | None = None,
        server_public_certificate: Path | str | None = None,
        request_timeout: float = 5.0,
        terminal_timeout: float = 30.0,
    ):
        self.endpoint = _endpoint(endpoint)
        self.queues = tuple(dict.fromkeys(_wire_name(queue, "queue") for queue in queues))
        if not 1 <= len(self.queues) <= _MAX_QUEUE_COUNT:
            raise ValueError(f"ZeroMQ Worker Dispatch requires from 1 to {_MAX_QUEUE_COUNT} queues")
        self.worker_id = _wire_name(worker_id or f"worker-{os.getpid()}", "worker id")
        self.client_id = str(uuid.uuid4())
        self.request_timeout = _timeout(request_timeout, "request timeout")
        self.terminal_timeout = _timeout(terminal_timeout, "terminal timeout")
        if self.request_timeout < 0.001 or self.terminal_timeout < 0.001:
            raise ValueError("ZeroMQ request and terminal timeouts must be at least one millisecond")
        self._client_certificate = Path(client_secret_certificate) if client_secret_certificate else None
        self._server_certificate = Path(server_public_certificate) if server_public_certificate else None
        self._curve_keys = _client_security(self.endpoint, self._client_certificate, self._server_certificate)
        self._owner = threading.get_ident()
        self._context = zmq.Context()
        self._socket = None
        self._closed = False

    def claim(self) -> ActivityAttempt | None:
        value = self._rpc("claim", {})
        mapping = _exact(value, {"attempt"}, "claim result")
        return None if mapping["attempt"] is None else _decode_attempt(mapping["attempt"])

    def heartbeat(self, attempt: ActivityAttempt, *, details: object = _OMITTED) -> object:
        fields = {"attempt": _encode_attempt(attempt)}
        if details is not _OMITTED:
            fields["details"] = snapshot_heartbeat_details(details)
        value = self._rpc("heartbeat", fields)
        return _exact(value, {"details"}, "heartbeat result")["details"]

    def complete(self, attempt: ActivityAttempt, result: object) -> None:
        # Exact terminal reports are custody-idempotent and are the sole RPC
        # automatically redelivered after an uncertain response.
        value = self._rpc(
            "complete",
            {"attempt": _encode_attempt(attempt), "result": _faithful(result, "Activity result")},
            retry_until=time.monotonic() + self.terminal_timeout,
        )
        if _exact(value, {"completed"}, "complete result") != {"completed": True}:
            raise RuntimeError("ZeroMQ Dispatch returned an invalid complete acknowledgement")

    def fail(self, attempt: ActivityAttempt, error: str | Exception) -> None:
        spelling = error if isinstance(error, str) else repr(error)
        if not isinstance(spelling, str):
            raise TypeError("Activity failure must be a string or exception")
        value = self._rpc("fail", {"attempt": _encode_attempt(attempt), "error": spelling})
        if _exact(value, {"failed"}, "fail result") != {"failed": True}:
            raise RuntimeError("ZeroMQ Dispatch returned an invalid fail acknowledgement")

    def wait(self, timeout: float) -> bool:
        time.sleep(_timeout(timeout, "wait timeout"))
        return False

    def close(self) -> None:
        self._check_owner()
        if self._closed:
            return
        self._closed = True
        if self._socket is not None:
            self._socket.close(linger=0)
        self._context.term()

    def _rpc(self, operation: str, fields: dict[str, object], *, retry_until: float | None = None) -> object:
        self._check_owner()
        if self._closed:
            raise RuntimeError("ZeroMQ Worker Dispatch is closed")
        request_id = str(uuid.uuid4())
        request = {
            "version": _VERSION,
            "request_id": request_id,
            "client_id": self.client_id,
            "worker_id": self.worker_id,
            "queues": list(self.queues),
            "operation": operation,
            **fields,
        }
        payload = _encode_message(request)
        while True:
            try:
                socket = self._ensure_socket()
                socket.send(payload)
                if socket.poll(max(1, round(self.request_timeout * 1000)), zmq.POLLIN):
                    response_frames = socket.recv_multipart()
                    self._discard_socket()
                    if len(response_frames) != 1:
                        raise RuntimeError("ZeroMQ Dispatch server returned a multipart protocol violation")
                    return _decode_response(response_frames[0], request_id)
                raise TimeoutError(f"ZeroMQ Dispatch request {operation!r} timed out")
            except (TimeoutError, zmq.Again, zmq.ZMQError) as error:
                self._discard_socket()
                if retry_until is None or time.monotonic() >= retry_until:
                    raise ConnectionError(f"ZeroMQ Dispatch request {operation!r} was not acknowledged") from error

    def _open_socket(self):
        socket = self._context.socket(zmq.DEALER)
        try:
            socket.linger = 0
            socket.sndhwm = _HWM
            socket.rcvhwm = _HWM
            socket.maxmsgsize = _MAX_MESSAGE_BYTES
            socket.immediate = True
            socket.sndtimeo = max(1, round(self.request_timeout * 1000))
            if self.endpoint.startswith("tcp://"):
                assert self._curve_keys is not None
                client_public, client_secret, server_public = self._curve_keys
                socket.curve_publickey = client_public
                socket.curve_secretkey = client_secret
                socket.curve_serverkey = server_public
            socket.connect(self.endpoint)
            return socket
        except BaseException:
            socket.close(linger=0)
            raise

    def _ensure_socket(self):
        if self._socket is None:
            self._socket = self._open_socket()
        return self._socket

    def _discard_socket(self) -> None:
        if self._socket is not None:
            self._socket.close(linger=0)
            self._socket = None

    def _check_owner(self) -> None:
        if threading.get_ident() != self._owner:
            raise RuntimeError("ZeroMQ Worker Dispatch sockets may only be used by their owning thread")


class ZeroMQDispatchServer:
    """ROUTER service exposing a WorkerDispatch factory without owning custody."""

    def __init__(
        self,
        endpoint: str,
        path: Path | str,
        *,
        allowed_queues: Sequence[str],
        server_secret_certificate: Path | str | None = None,
        allowed_client_keys: Path | str | None = None,
        max_message_bytes: int = _MAX_MESSAGE_BYTES,
    ):
        self._initialize(
            endpoint,
            self._local_factory(path, allowed_queues),
            server_secret_certificate=server_secret_certificate,
            allowed_client_keys=allowed_client_keys,
            max_message_bytes=max_message_bytes,
        )

    def _initialize(
        self,
        endpoint: str,
        provider_factory: _WorkerProviderFactory,
        *,
        server_secret_certificate: Path | str | None,
        allowed_client_keys: Path | str | None,
        max_message_bytes: int,
    ) -> None:
        self.endpoint = _endpoint(endpoint, bind=True)
        self.provider_factory = provider_factory
        self.server_certificate = Path(server_secret_certificate) if server_secret_certificate else None
        self.allowed_client_keys = Path(allowed_client_keys) if allowed_client_keys else None
        self._curve_keys = _server_security(self.endpoint, self.server_certificate, self.allowed_client_keys)
        if (
            isinstance(max_message_bytes, bool)
            or not isinstance(max_message_bytes, int)
            or not 1 <= max_message_bytes <= _MAX_MESSAGE_BYTES
        ):
            raise ValueError(f"ZeroMQ maximum message bytes must be an integer from 1 to {_MAX_MESSAGE_BYTES}")
        self.max_message_bytes = max_message_bytes
        self.bound_endpoint: str | None = None
        self._ready = threading.Event()
        self._stop = threading.Event()
        self._draining = threading.Event()
        self._drain_deadline: float | None = None
        self._startup_error: BaseException | None = None

    @staticmethod
    def _local_factory(path: Path | str, allowed_queues: Sequence[str]) -> _WorkerProviderFactory:
        from petrus.motus.dispatch.local import LocalWorkerDispatch

        permitted = frozenset(_name(queue, "allowed queue") for queue in allowed_queues)
        if not permitted:
            raise ValueError("ZeroMQ Local Dispatch server requires at least one allowed queue")

        def factory(queues: Sequence[str], worker_id: str) -> WorkerDispatch:
            requested = tuple(dict.fromkeys(queues))
            if not requested or not set(requested) <= permitted:
                raise ValueError(f"Worker requested queues outside the server allowlist: {requested!r}")
            return LocalWorkerDispatch(path, queues=requested, worker_id=worker_id)

        return factory

    @classmethod
    def local(
        cls,
        endpoint: str,
        path: Path | str,
        *,
        allowed_queues: Sequence[str],
        server_secret_certificate: Path | str | None = None,
        allowed_client_keys: Path | str | None = None,
    ) -> ZeroMQDispatchServer:
        return cls(
            endpoint,
            path,
            allowed_queues=allowed_queues,
            server_secret_certificate=server_secret_certificate,
            allowed_client_keys=allowed_client_keys,
        )

    @classmethod
    def _from_factory(
        cls,
        endpoint: str,
        provider_factory: _WorkerProviderFactory,
        *,
        max_message_bytes: int = _MAX_MESSAGE_BYTES,
    ) -> ZeroMQDispatchServer:
        """Private fault-injection door; production v1 is Local-backed only."""
        server = cls.__new__(cls)
        server._initialize(
            endpoint,
            provider_factory,
            server_secret_certificate=None,
            allowed_client_keys=None,
            max_message_bytes=max_message_bytes,
        )
        return server

    def serve_forever(self) -> None:
        context = zmq.Context()
        socket = None
        authenticator = None
        lock = None
        providers: dict[str, tuple[tuple[str, ...], str, WorkerDispatch]] = {}
        try:
            socket, authenticator, lock = self._open_server(context)
            socket.bind(self.endpoint)
            self.bound_endpoint = socket.getsockopt_string(zmq.LAST_ENDPOINT)
            self._ready.set()
            self._serve_requests(socket, providers)
        except BaseException as error:
            self._startup_error = error
            self._ready.set()
            raise
        finally:
            for _, _, provider in providers.values():
                try:
                    provider.close()
                except Exception:
                    pass
            if socket is not None:
                socket.close(linger=0)
            if authenticator is not None:
                authenticator.stop()
            context.term()
            if lock is not None:
                lock.close()

    def _open_server(self, context):
        lock = _endpoint_lock(self.endpoint)
        authenticator = None
        socket = None
        try:
            if self.endpoint.startswith("tcp://"):
                assert self.server_certificate is not None and self.allowed_client_keys is not None
                authenticator = ThreadAuthenticator(context)
                authenticator.start()
                authenticator.configure_curve(domain=_ZAP_DOMAIN, location=str(self.allowed_client_keys))
            socket = context.socket(zmq.ROUTER)
            socket.linger = 0
            socket.sndhwm = _HWM
            socket.rcvhwm = _HWM
            socket.maxmsgsize = _MAX_MESSAGE_BYTES
            socket.sndtimeo = 1_000
            socket.router_mandatory = True
            if self.endpoint.startswith("tcp://"):
                assert self._curve_keys is not None
                public, secret = self._curve_keys
                socket.zap_domain = _ZAP_DOMAIN.encode()
                socket.curve_publickey = public
                socket.curve_secretkey = secret
                socket.curve_server = True
            return socket, authenticator, lock
        except BaseException:
            if socket is not None:
                socket.close(linger=0)
            if authenticator is not None:
                authenticator.stop()
            if lock is not None:
                lock.close()
            raise

    def _serve_requests(
        self,
        socket,
        providers: dict[str, tuple[tuple[str, ...], str, WorkerDispatch]],
    ) -> None:
        while not self._stop.is_set():
            if self._draining.is_set() and self._drain_deadline is not None:
                if time.monotonic() >= self._drain_deadline:
                    return
            if not socket.poll(100, zmq.POLLIN):
                continue
            route, body, protocol_error = self._receive_request(socket)
            response = self._handle(body, providers, protocol_error=protocol_error)
            try:
                socket.send_multipart([route, response])
            except zmq.Again, zmq.ZMQError:
                # Custody, not reply delivery, determines whether the
                # operation happened. The client applies operation-specific
                # uncertainty handling.
                continue

    def _receive_request(self, socket) -> tuple[bytes, tuple[bytes, ...], str | None]:
        route = socket.recv()
        body: list[bytes] = []
        total = 0
        frame_count = 0
        while socket.getsockopt(zmq.RCVMORE):
            frame = socket.recv()
            frame_count += 1
            total += len(frame)
            if frame_count == 1 and total <= self.max_message_bytes:
                body.append(frame)
        if frame_count != 1:
            return route, tuple(body), "request must contain exactly one application frame"
        if total > self.max_message_bytes:
            return route, (), "request exceeds the maximum message size"
        return route, tuple(body), None

    def wait_ready(self, timeout: float = 5.0) -> str:
        if not self._ready.wait(_timeout(timeout, "readiness timeout")):
            raise TimeoutError("ZeroMQ Dispatch server did not become ready")
        if self._startup_error is not None:
            raise RuntimeError(
                f"ZeroMQ Dispatch server failed to start: {self._startup_error}"
            ) from self._startup_error
        assert self.bound_endpoint is not None
        return self.bound_endpoint

    def request_drain(self, timeout: float = 30.0) -> None:
        self._drain_deadline = time.monotonic() + _timeout(timeout, "drain timeout")
        self._draining.set()

    def stop(self) -> None:
        self._stop.set()

    def _handle(
        self,
        frames: Sequence[bytes],
        providers: dict[str, tuple[tuple[str, ...], str, WorkerDispatch]],
        *,
        protocol_error: str | None = None,
    ) -> bytes:
        request_id = "unknown"
        try:
            if protocol_error is not None:
                raise _ProtocolError(protocol_error)
            request, base = self._parse_request(frames)
            request_id = request["request_id"]
            assert isinstance(request_id, str)
            operation, arguments = self._decode_operation(request, base)
            provider = self._provider(request, providers)
            value = self._operate(operation, arguments, provider)
            return _encode_message({"version": _VERSION, "request_id": request_id, "ok": True, "value": value})
        except _ProtocolError as error:
            kind = "protocol"
            message = _error_message(error)
        except ValueError as error:
            kind = "refused"
            message = _error_message(error)
        except Exception as error:
            kind = "service"
            message = _error_message(error)
        response = {
            "version": _VERSION,
            "request_id": request_id,
            "ok": False,
            "error": {"kind": kind, "message": message},
        }
        return _encode_message(response)

    def _parse_request(self, frames: Sequence[bytes]) -> tuple[dict[str, object], set[str]]:
        try:
            if len(frames) != 1:
                raise ValueError("request must contain exactly one application frame")
            if len(frames[0]) > self.max_message_bytes:
                raise ValueError("request exceeds the maximum message size")
            request = _decode_message(frames[0])
            base = {"version", "request_id", "client_id", "worker_id", "queues", "operation"}
            if not base <= set(request):
                raise ValueError(f"request requires base fields {sorted(base)}")
            request["request_id"] = _wire_name(request["request_id"], "request id")
            _wire_name(request["client_id"], "client id")
            _wire_name(request["worker_id"], "worker id")
            queues = request["queues"]
            if not isinstance(queues, list) or not 1 <= len(queues) <= _MAX_QUEUE_COUNT:
                raise ValueError(f"request queues must contain from 1 to {_MAX_QUEUE_COUNT} names")
            for queue in queues:
                _wire_name(queue, "queue")
            version = request["version"]
            if isinstance(version, bool) or not isinstance(version, int) or version != _VERSION:
                raise ValueError(f"unsupported ZeroMQ Dispatch protocol version {request['version']!r}")
            return request, base
        except ValueError as error:
            raise _ProtocolError(str(error)) from error

    @staticmethod
    def _decode_operation(request: dict[str, object], base: set[str]) -> tuple[str, tuple[object, ...]]:
        try:
            operation = _wire_name(request["operation"], "operation")
            if operation == "claim":
                _require_fields(request, base, "claim")
                return operation, ()
            if operation == "heartbeat":
                allowed = base | {"attempt"}
                details = _OMITTED
                if "details" in request:
                    allowed.add("details")
                    details = request["details"]
                _require_fields(request, allowed, "heartbeat")
                return operation, (_decode_attempt(request["attempt"]), details)
            if operation == "complete":
                _require_fields(request, base | {"attempt", "result"}, "complete")
                return operation, (_decode_attempt(request["attempt"]), request["result"])
            if operation == "fail":
                _require_fields(request, base | {"attempt", "error"}, "fail")
                if not isinstance(request["error"], str):
                    raise ValueError("failure error must be a string")
                return operation, (_decode_attempt(request["attempt"]), request["error"])
            raise ValueError(f"unknown Worker Dispatch operation {operation!r}")
        except ValueError as error:
            raise _ProtocolError(str(error)) from error

    def _provider(
        self,
        request: dict[str, object],
        providers: dict[str, tuple[tuple[str, ...], str, WorkerDispatch]],
    ) -> WorkerDispatch:
        client_id = request["client_id"]
        worker_id = request["worker_id"]
        queues_value = request["queues"]
        assert isinstance(queues_value, list)
        queues = tuple(dict.fromkeys(cast(str, queue) for queue in queues_value))
        assert isinstance(client_id, str) and isinstance(worker_id, str)
        cached = providers.get(client_id)
        if cached is not None:
            old_queues, old_worker, provider = cached
            if (queues, worker_id) != (old_queues, old_worker):
                raise ValueError("client identity cannot change Worker queues or identity")
            return provider
        if len(providers) >= _MAX_CLIENTS:
            _, (_, _, evicted) = providers.popitem()
            evicted.close()
        provider = self.provider_factory(queues, worker_id)
        if not isinstance(provider, WorkerDispatch):
            raise TypeError("ZeroMQ server factory must return WorkerDispatch")
        providers[client_id] = (queues, worker_id, provider)
        return provider

    def _operate(self, operation: str, arguments: tuple[object, ...], provider: WorkerDispatch) -> object:
        if operation == "claim":
            if self._draining.is_set():
                return {"attempt": None}
            attempt = provider.claim()
            return {"attempt": None if attempt is None else _encode_attempt(attempt)}
        if operation == "heartbeat":
            attempt, supplied_details = arguments
            assert isinstance(attempt, ActivityAttempt)
            details = (
                provider.heartbeat(attempt)
                if supplied_details is _OMITTED
                else provider.heartbeat(attempt, details=supplied_details)
            )
            return {"details": details}
        if operation == "complete":
            attempt, result = arguments
            assert isinstance(attempt, ActivityAttempt)
            provider.complete(attempt, result)
            return {"completed": True}
        if operation == "fail":
            attempt, error = arguments
            assert isinstance(attempt, ActivityAttempt) and isinstance(error, str)
            provider.fail(attempt, error)
            return {"failed": True}
        raise AssertionError(f"decoded unknown Worker Dispatch operation {operation!r}")


def _endpoint(value: object, *, bind: bool = False) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("ZeroMQ endpoint must be a non-empty string without NUL")
    if not value.startswith(("ipc://", "tcp://")):
        raise ValueError("ZeroMQ Dispatch Transport supports only ipc:// and tcp:// endpoints")
    if not bind and value.startswith("tcp://") and value.rsplit(":", 1)[-1] in {"*", "0"}:
        raise ValueError("ZeroMQ Worker requires a connectable TCP endpoint, not a wildcard bind endpoint")
    return value


def _client_security(endpoint: str, client: Path | None, server: Path | None) -> tuple[bytes, bytes, bytes] | None:
    if endpoint.startswith("tcp://") and (client is None or server is None):
        raise ValueError("ZeroMQ TCP Worker requires client secret and server public certificates")
    if endpoint.startswith("ipc://") and (client is not None or server is not None):
        raise ValueError("ZeroMQ IPC Worker rejects TCP CURVE certificates")
    if endpoint.startswith("tcp://"):
        assert client is not None and server is not None
        client_public, client_secret = zmq.auth.load_certificate(client)
        server_public, server_secret = zmq.auth.load_certificate(server)
        if not client_public or client_secret is None:
            raise ValueError("ZeroMQ client certificate must contain a public and secret key")
        if not server_public or server_secret is not None:
            raise ValueError("ZeroMQ trusted server certificate must be public-only")
        return client_public, client_secret, server_public
    return None


def _server_security(endpoint: str, server: Path | None, clients: Path | None) -> tuple[bytes, bytes] | None:
    if endpoint.startswith("tcp://"):
        if server is None or clients is None:
            raise ValueError("ZeroMQ TCP server requires a server secret certificate and allowed-client key directory")
        if not clients.is_dir() or not list(clients.glob("*.key")):
            raise ValueError("ZeroMQ TCP server allowed-client directory must contain at least one public .key")
        server_public, server_secret = zmq.auth.load_certificate(server)
        if not server_public or server_secret is None:
            raise ValueError("ZeroMQ server certificate must contain a public and secret key")
        for certificate in clients.glob("*.key"):
            public, secret = zmq.auth.load_certificate(certificate)
            if not public or secret is not None:
                raise ValueError(f"allowed-client certificate must be public-only: {certificate}")
        return server_public, server_secret
    elif server is not None or clients is not None:
        raise ValueError("ZeroMQ IPC server rejects TCP CURVE configuration")
    return None


def _endpoint_lock(endpoint: str):
    if not endpoint.startswith("ipc://"):
        return None
    if fcntl is None:
        raise RuntimeError("ZeroMQ IPC endpoint ownership requires POSIX fcntl; use authenticated TCP on this platform")
    path = Path(endpoint.removeprefix("ipc://"))
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = (path.parent / f".{path.name}.impetus.lock").open("a+b")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        lock.close()
        raise RuntimeError(f"ZeroMQ IPC endpoint is already owned: {endpoint}") from error
    return lock


def _encode_attempt(attempt: ActivityAttempt) -> dict[str, object]:
    if not isinstance(attempt, ActivityAttempt):
        raise TypeError("Worker Dispatch operation requires ActivityAttempt")
    return {
        "attempt_id": attempt.attempt_id,
        "epoch": attempt.epoch,
        "claimant": attempt.claimant,
        "queue": attempt.queue,
        "invocation": _encode_invocation(attempt.invocation),
        "latest_details": attempt.latest_details,
    }


def _decode_attempt(value: object) -> ActivityAttempt:
    data = _exact(
        value,
        {"attempt_id", "epoch", "claimant", "queue", "invocation", "latest_details"},
        "Activity Attempt",
    )
    return ActivityAttempt(
        _name(data["attempt_id"], "attempt id"),
        _name(data["epoch"], "attempt epoch"),
        _name(data["claimant"], "attempt claimant"),
        _name(data["queue"], "attempt queue"),
        _decode_invocation(data["invocation"]),
        data["latest_details"],
    )


def _encode_invocation(value: ActivityInvocation) -> dict[str, object]:
    if not isinstance(value, ActivityInvocation):
        raise TypeError("Activity Attempt requires ActivityInvocation")
    return {
        "activity": value.activity,
        "input": value.input,
        "policy": {"attempts": value.policy.attempts, "heartbeat_timeout": value.policy.heartbeat_timeout},
        "correlation": value.correlation,
        "idempotency": value.idempotency,
    }


def _decode_invocation(value: object) -> ActivityInvocation:
    data = _exact(value, {"activity", "input", "policy", "correlation", "idempotency"}, "Activity invocation")
    policy = _exact(data["policy"], {"attempts", "heartbeat_timeout"}, "execution policy")
    for field in ("attempts", "heartbeat_timeout"):
        if isinstance(policy[field], bool) or not isinstance(policy[field], int):
            raise ValueError(f"execution policy {field} must be an integer")
    activity = _name(data["activity"], "Activity name")
    attempts = cast(int, policy["attempts"])
    heartbeat_timeout = cast(int, policy["heartbeat_timeout"])
    correlation = data["correlation"]
    idempotency = data["idempotency"]
    if correlation is not None:
        correlation = _name(correlation, "Activity correlation")
    if idempotency is not None:
        idempotency = _name(idempotency, "Activity idempotency")
    return ActivityInvocation(
        activity,
        input=data["input"],
        policy=ExecutionPolicy(attempts, heartbeat_timeout),
        correlation=correlation,
        idempotency=idempotency,
    )


def _decode_response(payload: bytes, request_id: str) -> object:
    response = _decode_message(payload)
    if response.get("ok") is True:
        data = _exact(response, {"version", "request_id", "ok", "value"}, "successful response")
        if data["version"] != _VERSION or isinstance(data["version"], bool) or data["request_id"] != request_id:
            raise RuntimeError("ZeroMQ Dispatch response version or request identity mismatch")
        return data["value"]
    data = _exact(response, {"version", "request_id", "ok", "error"}, "refused response")
    error = _exact(data["error"], {"kind", "message"}, "refused response error")
    if data["version"] != _VERSION or isinstance(data["version"], bool) or data["request_id"] != request_id:
        raise RuntimeError("ZeroMQ Dispatch refusal version or request identity mismatch")
    if (
        data["ok"] is not False
        or error["kind"] not in {"protocol", "refused", "service"}
        or not isinstance(error["message"], str)
    ):
        raise RuntimeError("ZeroMQ Dispatch returned an invalid refusal")
    if error["kind"] == "refused":
        raise ValueError(f"ZeroMQ Dispatch refused request: {error['message']}")
    raise RuntimeError(f"ZeroMQ Dispatch {error['kind']} error: {error['message']}")


def _encode_message(value: object) -> bytes:
    encoded = json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    if len(encoded) > _MAX_MESSAGE_BYTES:
        raise ValueError("ZeroMQ Dispatch message exceeds the maximum size")
    return encoded


def _decode_message(payload: bytes) -> dict[str, object]:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid ZeroMQ Dispatch JSON message: {error}") from error
    if not isinstance(value, dict):
        raise ValueError("ZeroMQ Dispatch message must be a JSON object")
    return value


def _exact(value: object, fields: set[str], noun: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{noun} requires exactly {sorted(fields)}")
    return cast(dict[str, object], value)


def _require_fields(value: dict[str, object], fields: set[str], operation: str) -> None:
    if set(value) != fields:
        raise ValueError(f"{operation} request requires exactly {sorted(fields)}")


def _faithful(value: object, noun: str) -> object:
    try:
        return json.loads(json.dumps(value, allow_nan=False, ensure_ascii=False))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{noun} must be JSON-faithful: {error}") from error


def _name(value: object, noun: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError(f"ZeroMQ Dispatch {noun} must be a non-empty string without NUL")
    return value


def _wire_name(value: object, noun: str) -> str:
    spelling = _name(value, noun)
    if len(spelling.encode()) > _MAX_IDENTITY_BYTES:
        raise ValueError(f"ZeroMQ Dispatch {noun} exceeds the {_MAX_IDENTITY_BYTES}-byte protocol limit")
    return spelling


def _error_message(error: Exception) -> str:
    message = str(error).strip() or type(error).__name__
    encoded = message.encode()[:_MAX_ERROR_BYTES]
    return encoded.decode(errors="replace")


def _timeout(value: object, noun: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"ZeroMQ {noun} must be a finite non-negative number")
    return float(value)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m petrus.motus.transport.zeromq", description=__doc__)
    parser.add_argument("--path", required=True, help="Local SQLite Dispatch path owned by this execution host")
    parser.add_argument("--bind", required=True, help="ipc:// or tcp:// bind endpoint")
    parser.add_argument("--queue", action="append", default=[], help="allowed Worker queue (repeatable)")
    parser.add_argument("--server-secret-certificate", help="CURVE server .key_secret file (TCP)")
    parser.add_argument("--allowed-client-keys", help="directory of allowed client public .key files (TCP)")
    parser.add_argument("--drain-timeout", type=float, default=30.0)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    arguments = _parser().parse_args(argv)
    server = ZeroMQDispatchServer.local(
        arguments.bind,
        arguments.path,
        allowed_queues=tuple(dict.fromkeys(arguments.queue)) or ("default",),
        server_secret_certificate=arguments.server_secret_certificate,
        allowed_client_keys=arguments.allowed_client_keys,
    )

    def drain(_signum, _frame) -> None:
        server.request_drain(arguments.drain_timeout)

    signal.signal(signal.SIGTERM, drain)
    readiness = threading.Thread(target=lambda: _announce(server), daemon=True)
    readiness.start()
    server.serve_forever()


def _announce(server: ZeroMQDispatchServer) -> None:
    try:
        endpoint = server.wait_ready()
    except Exception:
        return
    print(json.dumps({"ready": True, "endpoint": endpoint, "pid": os.getpid()}), flush=True)


__all__ = [
    "ZeroMQDispatchServer",
    "ZeroMQWorkerDispatch",
    "main",
]


if __name__ == "__main__":
    main()
