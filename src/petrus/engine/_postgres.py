"""Private PostgreSQL fencing for one canonical writer per Instance.

The event history remains the authority; this session-level advisory lock is
the trusted-workspace coordination fence that prevents two writer
processes from operating the same history concurrently. It is deliberately
not a lease service or a hostile-tenant security boundary. The lock follows
the PostgreSQL connection: losing or closing that connection releases the
fence, and a live coordinator must treat the connection's failure as terminal.

The ``PostgresAuthorityFence`` name remains private while maintained
CV5 compositions still use it; its eventual owner and spelling remain deferred.
"""

from __future__ import annotations

# Python imports
import hashlib

# Pip imports — the optional extra, refused loud by name when absent.
try:
    import psycopg
except ImportError as _psycopg_missing:
    raise ImportError(
        "PostgresAuthorityFence needs psycopg, which ships in the optional 'postgres' extra: "
        "install petrus-runtime[postgres] (e.g. `uv add 'petrus-runtime[postgres]'` or `pip install 'petrus-runtime[postgres]'`)"
    ) from _psycopg_missing


def _fence_key(instance: str) -> int:
    if not isinstance(instance, str) or not instance:
        raise ValueError(f"authority fence requires a non-empty string instance id, got {instance!r}")
    digest = hashlib.sha256(b"impetus-authority\0" + instance.encode()).digest()[:8]
    return int.from_bytes(digest, byteorder="big", signed=True)


class PostgresAuthorityFence:
    """One session-level PostgreSQL advisory lock for a net-instance identity."""

    def __init__(self, connection, instance: str):
        self._connection = connection
        self.instance = instance
        self._key = _fence_key(instance)
        self._held = bool(connection.execute("SELECT pg_try_advisory_lock(%s)", (self._key,)).fetchone()[0])
        if not self._held:
            raise RuntimeError(
                f"authority fence for instance {instance!r} is already held: refusing a second canonical writer"
            )

    def close(self) -> None:
        if not self._held:
            return
        try:
            self._connection.execute("SELECT pg_advisory_unlock(%s)", (self._key,))
        except psycopg.Error:
            pass  # a dead connection already released every session lock
        self._held = False

    def __enter__(self) -> PostgresAuthorityFence:
        return self

    def __exit__(self, _type, _value, _traceback) -> None:
        self.close()
