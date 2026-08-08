"""PostgreSQL History plus Absurd Dispatch construction doors."""

from __future__ import annotations

from collections.abc import Mapping

import psycopg

from petrus.motus.dispatch.absurd import AbsurdDispatch
from petrus.engine import Engine, _EngineResources
from petrus.engine._postgres import PostgresAuthorityFence as _PostgresAuthorityFence
from petrus.impetus.history_store.postgres import PostgresHistoryStore
from petrus.impetus.petrinet import Net


def _validate_connections(connection, listen) -> None:
    if connection.autocommit:
        raise ValueError(
            "Absurd Engine construction requires an autocommit=False connection: the Engine owns the joined "
            "transaction that makes begin+dispatch commit-or-vanish — an autocommit connection would commit "
            "each statement alone"
        )
    if listen is None:
        raise ValueError(
            "Absurd Engine construction requires a dedicated autocommit listen connection: the results "
            "doorbell and every wait-time probe ride it, so the joined connection never idles in transaction "
            "while the driver blocks"
        )
    if listen is connection:
        raise ValueError(
            "Absurd Engine construction requires the listen connection to be dedicated, not the joined connection"
        )
    if not listen.autocommit:
        raise ValueError("Absurd Engine construction requires the dedicated listen connection to use autocommit=True")


def _rollback(connection) -> None:
    try:
        connection.rollback()
    except psycopg.Error:
        pass


def _release_fence(fence: _PostgresAuthorityFence, connection) -> None:
    try:
        fence.close()
    finally:
        _rollback(connection)


def _close_connections(connection, listen) -> None:
    if listen is None or listen is connection:
        connection.close()
        return
    try:
        listen.close()
    finally:
        connection.close()


def _open_engine(
    connection,
    net: Net,
    instance: str,
    *,
    listen,
    create: bool,
    poll_interval: float = 0.25,
    default_queue: str = "default",
    activity_queues: Mapping[str, str] | None = None,
    **options,
) -> Engine:
    fence = None
    transferred = False
    try:
        _validate_connections(connection, listen)
        fence = _PostgresAuthorityFence(connection, instance)
        history = PostgresHistoryStore(connection, instance)
        dispatch = AbsurdDispatch(
            connection,
            instance=instance,
            listen=listen,
            poll_interval=poll_interval,
            default_queue=default_queue,
            activity_queues=activity_queues,
        )
        resources = _EngineResources(
            commit=connection.commit,
            rollback=lambda: _rollback(connection),
            release=lambda: _release_fence(fence, connection),
            close=lambda: _close_connections(connection, listen),
            wait=dispatch.wait_for_results,
        )
        engine = Engine._open(
            net, instance, history=history, dispatch=dispatch, create=create, resources=resources, **options
        )
        transferred = True
        return engine
    except BaseException:
        if not transferred:
            _rollback(connection)
            if fence is not None:
                _release_fence(fence, connection)
            _close_connections(connection, listen)
        raise


def create_engine(connection, net: Net, instance: str, *, listen, **options) -> Engine:
    """Create and host one new Instance with PostgreSQL History and Absurd Dispatch."""
    return _open_engine(connection, net, instance, listen=listen, create=True, **options)


def load_engine(connection, net: Net, instance: str, *, listen, **options) -> Engine:
    """Load and host one existing Instance with PostgreSQL History and Absurd Dispatch."""
    return _open_engine(connection, net, instance, listen=listen, create=False, **options)


__all__ = ["create_engine", "load_engine"]
