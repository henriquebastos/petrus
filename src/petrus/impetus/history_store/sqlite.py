"""SQLite storage and local production hosting for canonical History.

Many Instance histories may share one local database.  The component owns only
the ``impetus_history_*`` namespace; schema version 1 is initialized on a new
database and is otherwise validated, never migrated.  Writes use short SQLite
transactions as the concurrency backstop. Direct ``SqliteHistoryStore``
construction is an unfenced low-level route for inspection, tests, or callers
that coordinate writers externally. Production local hosts use
``petrus.engine.sqlite.create_engine`` and ``load_engine``, which hold a POSIX
writer fence.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import sqlite3
import time
import weakref
from importlib import import_module
from pathlib import Path
from typing import Any

from petrus.impetus.history import Record
from petrus.impetus.history.codec import decode_record, encode_record
from petrus.impetus.history_store.memory import InMemoryHistoryStore


def _load_fcntl() -> Any:
    try:
        return import_module("fcntl")
    except ImportError:  # pragma: no cover - exercised only on non-POSIX Python
        return None


_fcntl: Any = _load_fcntl()

__all__ = ["SqliteHistoryStore"]

_SCHEMA_VERSION = 1
_FIRING_TERMINALS = ("FiringCompleted", "FiringFailed")
_ACTIVITY_TERMINALS = ("ActivityCompleted", "ActivityFailed")

_DDL = (
    """CREATE TABLE impetus_history_schema (
    component TEXT PRIMARY KEY CHECK (component = 'history'),
    version INTEGER NOT NULL
)""",
    "INSERT INTO impetus_history_schema (component, version) VALUES ('history', 1)",
    """CREATE TABLE impetus_history_events (
    instance TEXT NOT NULL,
    position INTEGER NOT NULL CHECK (position >= 0),
    event_id TEXT NOT NULL UNIQUE,
    record_type TEXT NOT NULL,
    occurrence INTEGER,
    payload TEXT NOT NULL,
    recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (instance, position)
)""",
    """CREATE UNIQUE INDEX impetus_history_one_firing_terminal
    ON impetus_history_events (instance, occurrence)
    WHERE record_type IN ('FiringCompleted', 'FiringFailed')""",
    """CREATE UNIQUE INDEX impetus_history_one_activity_terminal
    ON impetus_history_events (instance, occurrence)
    WHERE record_type IN ('ActivityCompleted', 'ActivityFailed')""",
)

_FENCES: weakref.WeakSet[_WriterFence] = weakref.WeakSet()


class _WriterFence:
    """One nonblocking POSIX writer fence, with fork-safe descriptor fate."""

    def __init__(self, path: Path | str, instance: str):
        if _fcntl is None:
            raise RuntimeError(
                "fenced SQLite Engine hosting requires POSIX advisory locks; "
                "use Linux or macOS, or coordinate a low-level SqliteHistoryStore writer externally"
            )
        if not isinstance(instance, str) or not instance:
            raise ValueError(f"SQLite Engine requires a non-empty string instance id, got {instance!r}")
        database = Path(path).expanduser().resolve()
        lock_dir = database.parent / ".impetus-sqlite-locks"
        lock_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        identity = hashlib.sha256(instance.encode("utf-8")).hexdigest()
        database_id = hashlib.sha256(str(database).encode("utf-8")).hexdigest()
        self.path = lock_dir / f"{database_id}.{identity}.lock"
        self._pid = os.getpid()
        self._fd: int | None = None
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            _fcntl.flock(fd, _fcntl.LOCK_EX | _fcntl.LOCK_NB)
        except OSError as error:
            os.close(fd)
            if error.errno in (errno.EACCES, errno.EAGAIN):
                raise RuntimeError(
                    f"refusing second canonical writer for Instance {instance!r} in SQLite database {database}"
                ) from error
            raise
        self._fd = fd
        _FENCES.add(self)

    def ensure(self) -> None:
        if os.getpid() != self._pid:
            raise RuntimeError("an Engine inherited across fork cannot be observed or driven; open a fresh Engine")

    def close(self) -> None:
        fd, self._fd = self._fd, None
        if fd is None:
            return
        _FENCES.discard(self)
        if os.getpid() == self._pid:
            try:
                _fcntl.flock(fd, _fcntl.LOCK_UN)
            finally:
                os.close(fd)
        else:
            os.close(fd)

    def _after_fork_child(self) -> None:
        # flock is tied to the inherited open-file description. Closing the
        # child's duplicate (without LOCK_UN) leaves only the parent's authority.
        fd, self._fd = self._fd, None
        if fd is not None:
            os.close(fd)


def _after_fork_child() -> None:
    for fence in tuple(_FENCES):
        fence._after_fork_child()
    _FENCES.clear()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_after_fork_child)


class SqliteHistoryStore:
    """Unfenced low-level History for one ``instance`` in a local SQLite file.

    Coordinate canonical writers externally, or use the construction doors in
    ``petrus.engine.sqlite`` for the production fenced hosting boundary.
    """

    def __init__(self, path: Path | str, instance: str):
        if not isinstance(instance, str) or not instance:
            raise ValueError(f"SqliteHistoryStore requires a non-empty string instance id, got {instance!r}")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._instance = instance
        self._history = InMemoryHistoryStore()
        self._connection = sqlite3.connect(self.path, timeout=5.0, isolation_level=None)
        try:
            # Inspect existing component metadata before WAL or any other
            # persistent pragma can touch the file. Foreign/unsupported known
            # shapes are refusal-only inputs, not databases to normalize.
            self._preflight_schema()
            self._configure()
            self._ensure_schema()
            self._load()
        except BaseException:
            self._connection.close()
            raise

    def _preflight_schema(self) -> None:
        objects = dict(
            self._connection.execute(
                "SELECT name, type FROM sqlite_master WHERE name LIKE 'impetus_history_%'"
            ).fetchall()
        )
        if not objects:
            return
        if objects.get("impetus_history_schema") != "table":
            raise ValueError(f"{self.path}: foreign or unversioned impetus_history schema; migration is not supported")
        columns = [row[1] for row in self._connection.execute("PRAGMA table_info(impetus_history_schema)")]
        if columns != ["component", "version"]:
            raise ValueError(f"{self.path}: foreign impetus_history schema metadata shape; migration is not supported")
        rows = self._connection.execute("SELECT component, version FROM impetus_history_schema").fetchall()
        if rows != [("history", _SCHEMA_VERSION)]:
            raise ValueError(
                f"{self.path}: unsupported impetus_history schema metadata {rows!r}; "
                f"this store reads version {_SCHEMA_VERSION} only and does not migrate"
            )

    def _configure(self) -> None:
        self._connection.execute("PRAGMA busy_timeout = 5000")
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA synchronous = FULL")
        deadline = time.monotonic() + 5.0
        while True:
            try:
                mode = self._connection.execute("PRAGMA journal_mode = WAL").fetchone()[0]
                break
            except sqlite3.OperationalError as error:
                # This pragma can bypass the busy handler while another first
                # constructor establishes WAL. Retry only that bootstrap lock;
                # all other operational failures retain their original fate.
                if "locked" not in str(error).lower() or time.monotonic() >= deadline:
                    raise
                time.sleep(0.01)
        if str(mode).lower() != "wal":
            raise ValueError(f"{self.path}: SQLite refused WAL journal mode (reported {mode!r})")

    def _ensure_schema(self) -> None:
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            self._ensure_schema_locked()
            self._connection.commit()
        except BaseException:
            self._connection.rollback()
            raise

    def _ensure_schema_locked(self) -> None:
        objects = {
            row[0]: row[1]
            for row in self._connection.execute(
                "SELECT name, type FROM sqlite_master WHERE name LIKE 'impetus_history_%'"
            )
        }
        if not objects:
            for statement in _DDL:
                self._connection.execute(statement)
            return
        if objects.get("impetus_history_schema") != "table":
            raise ValueError(f"{self.path}: foreign or unversioned impetus_history schema; migration is not supported")
        columns = [row[1] for row in self._connection.execute("PRAGMA table_info(impetus_history_schema)")]
        if columns != ["component", "version"]:
            raise ValueError(f"{self.path}: foreign impetus_history schema metadata shape; migration is not supported")
        rows = self._connection.execute("SELECT component, version FROM impetus_history_schema").fetchall()
        if rows != [("history", _SCHEMA_VERSION)]:
            raise ValueError(
                f"{self.path}: unsupported impetus_history schema metadata {rows!r}; "
                f"this store reads version {_SCHEMA_VERSION} only and does not migrate"
            )
        expected = {
            "impetus_history_schema": "table",
            "impetus_history_events": "table",
            "impetus_history_one_firing_terminal": "index",
            "impetus_history_one_activity_terminal": "index",
        }
        if objects != expected:
            raise ValueError(f"{self.path}: corrupt or foreign impetus_history version {_SCHEMA_VERSION} shape")
        expected_sql = {
            "impetus_history_schema": _DDL[0],
            "impetus_history_events": _DDL[2],
            "impetus_history_one_firing_terminal": _DDL[3],
            "impetus_history_one_activity_terminal": _DDL[4],
        }
        actual_sql = dict(
            self._connection.execute(
                "SELECT name, sql FROM sqlite_master WHERE name IN (?, ?, ?, ?)", tuple(expected_sql)
            )
        )

        def normalize(statement: str) -> str:
            return re.sub(r"\s+", " ", statement.strip()).lower()

        if {name: normalize(sql) for name, sql in actual_sql.items()} != {
            name: normalize(sql) for name, sql in expected_sql.items()
        }:
            raise ValueError(f"{self.path}: corrupt or foreign impetus_history version {_SCHEMA_VERSION} DDL shape")
        event_columns = [row[1] for row in self._connection.execute("PRAGMA table_info(impetus_history_events)")]
        if event_columns != [
            "instance",
            "position",
            "event_id",
            "record_type",
            "occurrence",
            "payload",
            "recorded_at",
        ]:
            raise ValueError(f"{self.path}: corrupt or foreign impetus_history version {_SCHEMA_VERSION} event shape")

    def _load(self) -> None:
        rows = self._connection.execute(
            "SELECT position, event_id, record_type, occurrence, payload FROM impetus_history_events "
            "WHERE instance = ? ORDER BY position",
            (self._instance,),
        ).fetchall()
        records: list[Record] = []
        for expected, (position, event_id, record_type, occurrence, payload) in enumerate(rows):
            expected_id = f"{self._instance}:{expected}"
            if position != expected or event_id != expected_id:
                raise ValueError(
                    f"{self.path}: history for {self._instance!r} is non-dense or has corrupt event identity "
                    f"at position {expected}"
                )
            try:
                encoded = json.loads(payload)
                record = decode_record(encoded)
            except (json.JSONDecodeError, TypeError, ValueError) as error:
                raise ValueError(f"event {event_id} does not decode as an event history record: {error}") from error
            if type(record).__name__ != record_type or encoded.get("occurrence") != occurrence:
                raise ValueError(f"event {event_id} has corrupt indexing metadata")
            records.append(record)
        self._history.extend(records)

    @property
    def records(self) -> tuple[Record, ...]:
        return self._history.records

    def __iter__(self):
        return iter(self._history)

    def __len__(self) -> int:
        return len(self._history)

    def append(self, record: Record) -> None:
        self._commit([record])

    def extend(self, records: list[Record]) -> None:
        self._commit(records)

    def _commit(self, records: list[Record]) -> None:
        batch = [self._encode(record) for record in records]
        entered: list[Record] = []
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            position = len(self)
            for record, record_type, occurrence, payload in batch:
                event_id = f"{self._instance}:{position}"
                cursor = self._connection.execute(
                    "INSERT INTO impetus_history_events "
                    "(instance, position, event_id, record_type, occurrence, payload) VALUES (?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT DO NOTHING",
                    (self._instance, position, event_id, record_type, occurrence, payload),
                )
                if cursor.rowcount == 0 and not self._verify_conflict(event_id, record_type, occurrence, payload):
                    continue
                entered.append(record)
                position += 1
            self._connection.commit()
        except BaseException:
            self._connection.rollback()
            raise
        self._history.extend(entered)

    @staticmethod
    def _encode(record: Record) -> tuple[Record, str, int | None, str]:
        encoded = encode_record(record)
        try:
            payload = json.dumps(encoded, allow_nan=False, separators=(",", ":"))
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"cannot durably encode {type(record).__name__}: {error} — durable instants, token data, "
                "and activity input/result must be JSON-faithful values"
            ) from error
        return record, type(record).__name__, encoded.get("occurrence"), payload

    def _verify_conflict(self, event_id: str, record_type: str, occurrence: int | None, payload: str) -> bool:
        stored = self._connection.execute(
            "SELECT record_type, payload FROM impetus_history_events WHERE event_id = ?", (event_id,)
        ).fetchone()
        if stored is not None:
            stored_type, stored_payload = stored
            if json.loads(stored_payload) == json.loads(payload):
                return True
            raise ValueError(
                f"event {event_id} is already recorded as a different fact "
                f"(stored {stored_type}, appending {record_type})"
            )
        family = next((family for family in (_FIRING_TERMINALS, _ACTIVITY_TERMINALS) if record_type in family), None)
        terminal = None
        if family is not None:
            placeholders = ", ".join("?" for _ in family)
            terminal = self._connection.execute(
                "SELECT event_id, record_type, payload FROM impetus_history_events "
                f"WHERE instance = ? AND occurrence = ? AND record_type IN ({placeholders})",
                (self._instance, occurrence, *family),
            ).fetchone()
        if terminal is None:
            raise RuntimeError(f"insert of event {event_id} conflicted but no stored row explains it")
        stored_event, stored_type, stored_payload = terminal
        if json.loads(stored_payload) == json.loads(payload):
            return False
        raise ValueError(
            f"occurrence {occurrence} of {self._instance} already holds its terminal fact "
            f"({stored_type}, event {stored_event}); refusing different {record_type} (event {event_id})"
        )

    def close(self) -> None:
        self._connection.close()
