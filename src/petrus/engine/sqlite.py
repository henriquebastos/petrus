"""SQLite History construction doors for the neutral Engine."""

from __future__ import annotations

from petrus.engine import Engine, _EngineResources
from petrus.impetus.history_store.sqlite import SqliteHistoryStore, _WriterFence


def _open_engine(path, net, instance: str, *, dispatch, create: bool, **options) -> Engine:
    """Fence before loading History, then transfer both resources to Engine."""
    fence = _WriterFence(path, instance)
    history = None
    transferred = False
    try:
        history = SqliteHistoryStore(path, instance)
        resources = _EngineResources(release=fence.close, close=history.close, ensure=fence.ensure)
        engine = Engine._open(
            net, instance, history=history, dispatch=dispatch, create=create, resources=resources, **options
        )
        transferred = True
        return engine
    finally:
        if not transferred:
            if history is not None:
                history.close()
            fence.close()


def create_engine(path, net, instance: str, *, dispatch, **options) -> Engine:
    """Create and host one Instance through the fenced local SQLite route."""
    return _open_engine(path, net, instance, dispatch=dispatch, create=True, **options)


def load_engine(path, net, instance: str, *, dispatch, **options) -> Engine:
    """Load and host one Instance through the fenced local SQLite route."""
    return _open_engine(path, net, instance, dispatch=dispatch, create=False, **options)


__all__ = ["create_engine", "load_engine"]
