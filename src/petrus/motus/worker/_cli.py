"""Provider and transport selection for the Worker process entry point."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import os
import signal
from collections.abc import Mapping, Sequence
from typing import Any, Callable

from petrus.motus.dispatch import WorkerDispatch
from petrus.motus.worker import AsyncWorker, Worker, _AsyncWorkerAccess, _validate_registry


def _load_registry(spec: str) -> Mapping[str, Any]:
    module_name, _, attribute = spec.partition(":")
    if not module_name or not attribute:
        raise SystemExit(f"--registry must be 'module:attribute', got {spec!r}")
    loaded = getattr(importlib.import_module(module_name), attribute)
    registry = loaded() if callable(loaded) else loaded
    if not isinstance(registry, Mapping) or not registry:
        raise SystemExit(f"--registry {spec!r} must yield a non-empty mapping of activity name -> Activity")
    if any(not isinstance(name, str) or not name or not callable(activity) for name, activity in registry.items()):
        raise SystemExit(f"--registry {spec!r} must yield non-empty string names mapped to callable Activities")
    return dict(registry)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m petrus.motus.worker", description=__doc__)
    parser.add_argument("--provider", choices=("local", "absurd", "zeromq"), required=True)
    parser.add_argument("--registry", required=True, help="module:attribute of the Activity registry")
    parser.add_argument("--queue", action="append", default=[], help="subscribed queue (repeatable)")
    parser.add_argument("--worker-id", default=None, help="optional operational Worker label")
    parser.add_argument("--execution-mode", choices=("sync", "async"), default="sync")
    parser.add_argument("--custody-access", choices=("sync-bridge", "native-zeromq"), default="sync-bridge")
    parser.add_argument("--concurrency", type=int, default=1, help="positive AsyncWorker Activity-slot concurrency")
    parser.add_argument("--max-operation-sockets", type=int, default=8, help="native ZeroMQ in-flight socket bound")
    parser.add_argument("--claim-timeout", type=int, default=30, help="Absurd initial claim lease in seconds")
    parser.add_argument("--poll-interval", type=float, default=0.25)
    parser.add_argument("--path", help="Local SQLite Dispatch path")
    parser.add_argument("--dsn", default=os.environ.get("IMPETUS_DSN"), help="Absurd PostgreSQL DSN")
    parser.add_argument("--endpoint", help="ZeroMQ Dispatch server endpoint")
    parser.add_argument("--client-secret-certificate", help="ZeroMQ CURVE client .key_secret file")
    parser.add_argument("--server-public-certificate", help="ZeroMQ CURVE server public .key file")
    return parser


def _provider_factory(arguments: argparse.Namespace, queues: tuple[str, ...]) -> Callable[[], WorkerDispatch]:
    def create() -> WorkerDispatch:
        if arguments.provider == "local":
            from petrus.motus.dispatch.local import LocalWorkerDispatch

            return LocalWorkerDispatch(arguments.path, queues=queues, worker_id=arguments.worker_id)
        if arguments.provider == "absurd":
            try:
                from petrus.motus.dispatch.absurd import AbsurdWorkerDispatch
            except ImportError as error:
                raise SystemExit(str(error)) from error
            return AbsurdWorkerDispatch(
                arguments.dsn,
                queues=queues,
                worker_id=arguments.worker_id,
                claim_timeout=arguments.claim_timeout,
            )
        try:
            from petrus.motus.transport.zeromq import ZeroMQWorkerDispatch
        except ImportError as error:
            raise SystemExit(str(error)) from error
        return ZeroMQWorkerDispatch(
            arguments.endpoint,
            queues=queues,
            worker_id=arguments.worker_id,
            client_secret_certificate=arguments.client_secret_certificate,
            server_public_certificate=arguments.server_public_certificate,
        )

    return create


def _validate_provider_arguments(arguments: argparse.Namespace) -> None:
    certificates = arguments.client_secret_certificate or arguments.server_public_certificate
    if arguments.provider == "local":
        if not arguments.path or arguments.dsn or arguments.endpoint:
            raise SystemExit("Local provider requires --path and rejects --dsn/$IMPETUS_DSN and --endpoint")
        if certificates:
            raise SystemExit("Local provider rejects ZeroMQ CURVE certificates")
    elif arguments.provider == "absurd":
        if not arguments.dsn or arguments.path or arguments.endpoint:
            raise SystemExit("Absurd provider requires --dsn (or $IMPETUS_DSN) and rejects --path and --endpoint")
        if certificates:
            raise SystemExit("Absurd provider rejects ZeroMQ CURVE certificates")
    elif not arguments.endpoint or arguments.path or arguments.dsn:
        raise SystemExit("ZeroMQ provider requires --endpoint and rejects --path and --dsn/$IMPETUS_DSN")
    if arguments.custody_access == "native-zeromq" and (
        arguments.execution_mode != "async" or arguments.provider != "zeromq"
    ):
        raise SystemExit("native-zeromq custody access requires async execution with the zeromq provider")
    if arguments.custody_access == "sync-bridge" and arguments.max_operation_sockets != 8:
        raise SystemExit("--max-operation-sockets applies only to native-zeromq custody access")


def main(argv: Sequence[str] | None = None) -> None:
    arguments = _parser().parse_args(argv)
    queues = tuple(dict.fromkeys(arguments.queue)) or ("default",)
    registry = _load_registry(arguments.registry)
    try:
        registry = _validate_registry(registry, asynchronous=arguments.execution_mode == "async")
    except (TypeError, ValueError) as error:
        raise SystemExit(str(error)) from error
    _validate_provider_arguments(arguments)
    provider_factory = _provider_factory(arguments, queues)
    if arguments.execution_mode == "async":
        if arguments.custody_access == "native-zeromq":
            from petrus.motus.transport.zeromq import AsyncZeroMQWorkerAccess

            async def access_factory() -> _AsyncWorkerAccess:
                return await AsyncZeroMQWorkerAccess.create(
                    arguments.endpoint,
                    queues=queues,
                    worker_id=arguments.worker_id,
                    client_secret_certificate=arguments.client_secret_certificate,
                    server_public_certificate=arguments.server_public_certificate,
                    max_in_flight_operations=arguments.max_operation_sockets,
                )

            worker = AsyncWorker._from_async_access(
                access_factory, registry, concurrency=arguments.concurrency, worker_id=arguments.worker_id
            )
        else:
            worker = AsyncWorker(
                provider_factory, registry, concurrency=arguments.concurrency, worker_id=arguments.worker_id
            )
    else:
        if arguments.concurrency != 1:
            raise SystemExit("--concurrency applies only to --execution-mode async")
        worker = Worker(provider_factory(), registry, worker_id=arguments.worker_id)
    signal.signal(signal.SIGTERM, lambda _signum, _frame: worker.stop())
    if isinstance(worker, AsyncWorker):
        asyncio.run(worker.run(poll_interval=arguments.poll_interval))
    else:
        worker.run(poll_interval=arguments.poll_interval)


__all__ = ["main"]
