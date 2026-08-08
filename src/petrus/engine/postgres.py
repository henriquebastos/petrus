"""PostgreSQL History construction doors for the neutral Engine."""

from __future__ import annotations

import psycopg

from petrus.engine import Engine, _EngineResources
from petrus.engine._postgres import PostgresAuthorityFence as _PostgresAuthorityFence
from petrus.impetus.history_store.postgres import PostgresHistoryStore


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


def _open_engine(connection, net, instance: str, *, dispatch, create: bool, **options) -> Engine:
    fence = None
    transferred = False
    try:
        if connection.autocommit:
            raise ValueError(
                "PostgreSQL Engine construction requires an autocommit=False connection: the Engine owns "
                "the joined transaction, writer fence, rollback, and poison fate"
            )
        fence = _PostgresAuthorityFence(connection, instance)
        history = PostgresHistoryStore(connection, instance)
        resources = _EngineResources(
            commit=connection.commit,
            rollback=lambda: _rollback(connection),
            release=lambda: _release_fence(fence, connection),
            close=connection.close,
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
            connection.close()
        raise


def create_engine(connection, net, instance: str, *, dispatch, **options) -> Engine:
    """Create and host one Instance with PostgreSQL History and neutral Dispatch."""
    return _open_engine(connection, net, instance, dispatch=dispatch, create=True, **options)


def load_engine(connection, net, instance: str, *, dispatch, **options) -> Engine:
    """Load and host one Instance with PostgreSQL History and neutral Dispatch."""
    return _open_engine(connection, net, instance, dispatch=dispatch, create=False, **options)


__all__ = ["create_engine", "load_engine"]
