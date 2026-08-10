"""SQLite-backed, single-host Activity custody.

The database is the clock and serialization authority.  Every operation opens
its own connection and finishes its short transaction before Activity code can
run; consequently a provider object is safe to construct before spawning, but
no SQLite connection is inherited by a child.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import time
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path

import petrus.telemetry as telemetry
from petrus.motus.activity import (
    ActivityFailure,
    ActivityInvocation,
    ExecutionPolicy,
    _OMITTED,
    snapshot_heartbeat_details,
)
from petrus.motus.dispatch import ActivityAttempt

log = telemetry.get_logger("impetus")

_VERSION = 2
_PREFIX = "impetus_local_dispatch_"


_DDL = (
    """CREATE TABLE impetus_local_dispatch_schema (
 component TEXT PRIMARY KEY CHECK(component='dispatch'), version INTEGER NOT NULL)""",
    "INSERT INTO impetus_local_dispatch_schema VALUES ('dispatch', 2)",
    """CREATE TABLE impetus_local_dispatch_tasks (
 sequence INTEGER PRIMARY KEY AUTOINCREMENT,
 instance TEXT NOT NULL, occurrence INTEGER NOT NULL CHECK(occurrence>0),
 queue TEXT NOT NULL, invocation TEXT NOT NULL CHECK(json_valid(invocation)),
 epoch INTEGER NOT NULL DEFAULT 0 CHECK(epoch>=0), claimant TEXT, deadline INTEGER,
 schedule_start INTEGER NOT NULL, attempt_start INTEGER, attempt_deadline INTEGER, available_at INTEGER NOT NULL,
 details TEXT CHECK(details IS NULL OR json_valid(details)),
 CHECK((epoch=0 AND claimant IS NULL AND deadline IS NULL) OR
       (epoch>0 AND claimant IS NOT NULL AND deadline IS NOT NULL)),
 UNIQUE(instance, occurrence))""",
    """CREATE INDEX impetus_local_dispatch_claimable
 ON impetus_local_dispatch_tasks(queue, sequence)""",
    """CREATE TABLE impetus_local_dispatch_terminals (
 sequence INTEGER PRIMARY KEY AUTOINCREMENT,
 instance TEXT NOT NULL, occurrence INTEGER NOT NULL, epoch INTEGER NOT NULL CHECK(epoch>=0),
 claimant TEXT, outcome TEXT NOT NULL CHECK(json_valid(outcome)),
 CHECK((epoch=0 AND claimant IS NULL) OR (epoch>0 AND claimant IS NOT NULL)),
 UNIQUE(instance, occurrence),
 FOREIGN KEY(instance, occurrence) REFERENCES impetus_local_dispatch_tasks(instance, occurrence))""",
)


class LocalDispatch:
    """Engine-facing session over one SQLite custody domain."""

    def __init__(
        self,
        path: Path | str,
        *,
        instance: str,
        default_queue: str = "default",
        activity_queues: Mapping[str, str] | None = None,
    ):
        self.path = Path(path)
        self.instance = _name(instance, "instance")
        self.default_queue = _name(default_queue, "queue")
        routes = dict(activity_queues or {})
        for activity, queue in routes.items():
            _name(activity, "activity")
            _name(queue, "queue")
        self.activity_queues = routes
        self._published: set[int] = set()
        self._collected: set[int] = set()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _initialize(self.path)

    def dispatch(self, occurrence: int, invocation: ActivityInvocation) -> None:
        _occurrence(occurrence)
        if not isinstance(invocation, ActivityInvocation):
            raise TypeError("LocalDispatch publishes ActivityInvocation values")
        queue = self.activity_queues.get(invocation.activity, self.default_queue)
        encoded = _encode_invocation(invocation)
        with _transaction(self.path) as connection:
            now = _now(connection)
            connection.execute(
                "INSERT INTO impetus_local_dispatch_tasks(instance,occurrence,queue,invocation,schedule_start,available_at) "
                "VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(instance,occurrence) DO NOTHING",
                (self.instance, occurrence, queue, encoded, now, now),
            )
            row = connection.execute(
                "SELECT queue,invocation,epoch,deadline FROM impetus_local_dispatch_tasks "
                "WHERE instance=? AND occurrence=?",
                (self.instance, occurrence),
            ).fetchone()
            if row is None or row[1] != encoded:
                raise ValueError(f"Local Dispatch publication conflict for occurrence {occurrence}")
            old_queue, _, epoch, deadline = row
            terminal = connection.execute(
                "SELECT 1 FROM impetus_local_dispatch_terminals WHERE instance=? AND occurrence=?",
                (self.instance, occurrence),
            ).fetchone()
            # Routing is operational. Pending/expired work moves; a live claim
            # and a terminal retain their established custody route.
            if terminal is None and old_queue != queue and (epoch == 0 or deadline <= now):
                connection.execute(
                    "UPDATE impetus_local_dispatch_tasks SET queue=? WHERE instance=? AND occurrence=?",
                    (queue, self.instance, occurrence),
                )
        self._published.add(occurrence)
        log.emit(
            "dispatch_published",
            instance=self.instance,
            occurrence=occurrence,
            queue=queue,
            activity=invocation.activity,
        )

    def collect(self) -> tuple[tuple[int, object], ...]:
        eligible = sorted(self._published - self._collected)
        if not eligible:
            return ()
        marks = ",".join("?" for _ in eligible)
        with _connect(self.path) as connection:
            rows = connection.execute(
                f"SELECT occurrence,outcome FROM impetus_local_dispatch_terminals WHERE instance=? "
                f"AND occurrence IN ({marks}) ORDER BY sequence",
                (self.instance, *eligible),
            ).fetchall()
        self._collected.update(row[0] for row in rows)
        for occurrence, outcome in rows:
            log.emit(
                "dispatch_collected",
                instance=self.instance,
                occurrence=occurrence,
                outcome=json.loads(outcome)["kind"],
            )
        return tuple((occurrence, _decode_outcome(outcome)) for occurrence, outcome in rows)

    def worker(self, queues: Sequence[str] = ("default",), *, worker_id: str | None = None) -> LocalWorkerDispatch:
        """Construct a Worker-side provider over this database (not this Instance)."""
        return LocalWorkerDispatch(self.path, queues=queues, worker_id=worker_id)

    def wait_for_results(self, timeout: float) -> bool:
        deadline = time.monotonic() + _timeout(timeout)
        while True:
            if self._terminal_ready():
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            time.sleep(min(0.05, remaining))

    def _terminal_ready(self) -> bool:
        eligible = sorted(self._published - self._collected)
        if not eligible:
            return False
        marks = ",".join("?" for _ in eligible)
        with _connect(self.path) as connection:
            return (
                connection.execute(
                    f"SELECT 1 FROM impetus_local_dispatch_terminals WHERE instance=? AND occurrence IN ({marks}) LIMIT 1",
                    (self.instance, *eligible),
                ).fetchone()
                is not None
            )


class LocalWorkerDispatch:
    """Concrete Worker-side claims and fenced reporting across all Instances."""

    def __init__(
        self,
        path: Path | str,
        *,
        queues: Sequence[str] = ("default",),
        worker_id: str | None = None,
        _claimant: str | None = None,
    ):
        self.path = Path(path)
        self.queues = tuple(dict.fromkeys(_name(queue, "queue") for queue in queues))
        if not self.queues:
            raise ValueError("Local Worker Dispatch requires at least one queue")
        label = _name(worker_id, "worker label") if worker_id is not None else "worker"
        self.claimant = _claimant or f"{label}:{uuid.uuid4()}"
        _initialize(self.path)

    def claim(self) -> ActivityAttempt | None:
        marks = ",".join("?" for _ in self.queues)
        with _transaction(self.path) as connection:
            now = _now(connection)
            expired = _terminalize_exhausted(connection, now, self.queues)
            row = connection.execute(
                f"SELECT t.instance,t.occurrence,t.queue,t.invocation,t.epoch,t.details "
                f"FROM impetus_local_dispatch_tasks t LEFT JOIN impetus_local_dispatch_terminals x "
                f"USING(instance,occurrence) WHERE x.occurrence IS NULL AND t.queue IN ({marks}) "
                "AND t.epoch < json_extract(t.invocation,'$.policy.attempts') "
                "AND t.available_at<=? AND (t.epoch=0 OR t.deadline<=?) ORDER BY t.sequence LIMIT 1",
                (*self.queues, now, now),
            ).fetchone()
            attempt = None
            if row is not None:
                instance, occurrence, queue, encoded, prior, details = row
                invocation = _decode_invocation(encoded)
                epoch = prior + 1
                hard_limits = []
                if invocation.policy.start_to_close is not None:
                    hard_limits.append(now + _milliseconds(invocation.policy.start_to_close))
                schedule_deadline = None
                if invocation.policy.schedule_to_close is not None:
                    schedule_deadline = connection.execute(
                        "SELECT schedule_start FROM impetus_local_dispatch_tasks WHERE instance=? AND occurrence=?",
                        (instance, occurrence),
                    ).fetchone()[0] + _milliseconds(invocation.policy.schedule_to_close)
                    hard_limits.append(schedule_deadline)
                attempt_deadline = min(hard_limits) if hard_limits else None
                deadline = min([now + invocation.policy.heartbeat_timeout * 1000, *hard_limits])
                connection.execute(
                    "UPDATE impetus_local_dispatch_tasks SET epoch=?,claimant=?,deadline=?,attempt_start=?,attempt_deadline=? "
                    "WHERE instance=? AND occurrence=?",
                    (epoch, self.claimant, deadline, now, attempt_deadline, instance, occurrence),
                )
                attempt = ActivityAttempt(
                    _attempt_id(instance, occurrence), str(epoch), self.claimant, queue, invocation, _json(details)
                )
        for instance, occurrence, epoch, claimant in expired:
            log.emit(
                "dispatch_lease_expired",
                instance=instance,
                occurrence=occurrence,
                attempt=_attempt_id(instance, occurrence),
                epoch=epoch,
                claimant=claimant,
                outcome="failed",
            )
        if attempt is not None:
            _emit_attempt("dispatch_claimed", attempt)
        return attempt

    def heartbeat(self, attempt: ActivityAttempt, *, details: object = _OMITTED) -> object:
        snapshot = None if details is _OMITTED else snapshot_heartbeat_details(details)
        encoded = None if details is _OMITTED else _encode_json(snapshot, "heartbeat details")
        with _transaction(self.path) as connection:
            now = _now(connection)
            row = _active(connection, attempt, now)
            timeout = _decode_invocation(row[1]).policy.heartbeat_timeout
            instance, occurrence = _attempt_key(attempt)
            deadline = now + timeout * 1000
            if row[6] is not None:
                deadline = min(deadline, row[6])
            if details is _OMITTED:
                connection.execute(
                    "UPDATE impetus_local_dispatch_tasks SET deadline=? WHERE instance=? AND occurrence=?",
                    (deadline, instance, occurrence),
                )
                latest = _json(row[5])
            else:
                assert encoded is not None
                connection.execute(
                    "UPDATE impetus_local_dispatch_tasks SET deadline=?,details=? WHERE instance=? AND occurrence=?",
                    (deadline, encoded, instance, occurrence),
                )
                latest = json.loads(encoded)
        _emit_attempt("dispatch_heartbeat", attempt)
        return latest

    def complete(self, attempt: ActivityAttempt, result: object) -> None:
        self._terminal(attempt, {"kind": "completed", "value": _faithful(result, "Activity result")})

    def fail(self, attempt: ActivityAttempt, error: str | Exception | ActivityFailure) -> None:
        legacy_retryable = isinstance(error, str)
        failure = (
            error
            if isinstance(error, ActivityFailure)
            else ActivityFailure(
                error if isinstance(error, str) else repr(error),
                kind=type(error).__name__ if isinstance(error, Exception) else "ActivityError",
                retryable=not isinstance(error, str),
            )
        )
        with _transaction(self.path) as connection:
            outcome = {"kind": "failed", "failure": _failure_wire(failure)}
            if _acknowledge_terminal_retry(connection, attempt, outcome):
                disposition = "terminal-retry"
            else:
                now = _now(connection)
                _active(connection, attempt, now)
                instance, occurrence = _attempt_key(attempt)
                attempts = connection.execute(
                    "SELECT json_extract(invocation,'$.policy.attempts') FROM impetus_local_dispatch_tasks "
                    "WHERE instance=? AND occurrence=?",
                    (instance, occurrence),
                ).fetchone()[0]
                task = connection.execute(
                    "SELECT schedule_start FROM impetus_local_dispatch_tasks WHERE instance=? AND occurrence=?",
                    (instance, occurrence),
                ).fetchone()
                schedule_deadline = (
                    None
                    if attempt.invocation.policy.schedule_to_close is None
                    else task[0] + _milliseconds(attempt.invocation.policy.schedule_to_close)
                )
                delay = max(attempt.invocation.policy.retry_policy.delay(int(attempt.epoch)), failure.retry_after or 0)
                available = now + _milliseconds(delay)
                if (
                    (failure.retryable or legacy_retryable)
                    and int(attempt.epoch) < attempts
                    and (schedule_deadline is None or available < schedule_deadline)
                ):
                    # Keep epoch as the fence and make the failed lease immediately
                    # claimable. The next claim increments it.
                    connection.execute(
                        "UPDATE impetus_local_dispatch_tasks SET deadline=?,available_at=? WHERE instance=? AND occurrence=?",
                        (now, available, instance, occurrence),
                    )
                    disposition = "retryable"
                else:
                    self._insert_terminal(connection, attempt, outcome)
                    disposition = "terminal"
        _emit_attempt("dispatch_failed", attempt, outcome=disposition)

    def _terminal(self, attempt: ActivityAttempt, outcome: object) -> None:
        with _transaction(self.path) as connection:
            if _acknowledge_terminal_retry(connection, attempt, outcome):
                disposition = "terminal-retry"
            else:
                _active(connection, attempt, _now(connection))
                self._insert_terminal(connection, attempt, outcome)
                disposition = "terminal"
        _emit_attempt("dispatch_completed", attempt, outcome=disposition)

    @staticmethod
    def _insert_terminal(connection: sqlite3.Connection, attempt: ActivityAttempt, outcome: object) -> None:
        instance, occurrence = _attempt_key(attempt)
        connection.execute(
            "INSERT INTO impetus_local_dispatch_terminals(instance,occurrence,epoch,claimant,outcome) VALUES(?,?,?,?,?)",
            (instance, occurrence, int(attempt.epoch), attempt.claimant, _encode_json(outcome, "outcome")),
        )

    def wait(self, timeout: float) -> bool:
        deadline = time.monotonic() + _timeout(timeout)
        marks = ",".join("?" for _ in self.queues)
        while True:
            with _transaction(self.path) as connection:
                now = _now(connection)
                expired = _terminalize_exhausted(connection, now, self.queues)
                row = connection.execute(
                    f"SELECT 1 FROM impetus_local_dispatch_tasks t LEFT JOIN impetus_local_dispatch_terminals x "
                    f"USING(instance,occurrence) WHERE x.occurrence IS NULL AND t.queue IN ({marks}) "
                    "AND t.epoch < json_extract(t.invocation,'$.policy.attempts') "
                    "AND t.available_at<=? AND (t.epoch=0 OR t.deadline<=?) LIMIT 1",
                    (*self.queues, now, now),
                ).fetchone()
            for instance, occurrence, epoch, claimant in expired:
                log.emit(
                    "dispatch_lease_expired",
                    instance=instance,
                    occurrence=occurrence,
                    attempt=_attempt_id(instance, occurrence),
                    epoch=epoch,
                    claimant=claimant,
                    outcome="failed",
                )
            if row:
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            time.sleep(min(0.05, remaining))

    def close(self) -> None:
        """Operation-scoped SQLite connections leave no persistent resource to close."""


def _active(connection: sqlite3.Connection, attempt: ActivityAttempt, now: int):
    if not isinstance(attempt, ActivityAttempt):
        raise TypeError("custody operation requires ActivityAttempt")
    instance, occurrence = _attempt_key(attempt)
    row = connection.execute(
        "SELECT queue,invocation,epoch,claimant,deadline,details,attempt_deadline FROM impetus_local_dispatch_tasks "
        "WHERE instance=? AND occurrence=?",
        (instance, occurrence),
    ).fetchone()
    terminal = connection.execute(
        "SELECT 1 FROM impetus_local_dispatch_terminals WHERE instance=? AND occurrence=?",
        (instance, occurrence),
    ).fetchone()
    if (
        row is None
        or terminal
        or row[0] != attempt.queue
        or row[1] != _encode_invocation(attempt.invocation)
        or str(row[2]) != attempt.epoch
        or row[3] != attempt.claimant
        or row[4] <= now
    ):
        raise ValueError(f"stale Activity attempt {attempt.attempt_id}")
    return row


def _attempt_id(instance: str, occurrence: int) -> str:
    return json.dumps([instance, occurrence], ensure_ascii=False, separators=(",", ":"))


def _attempt_key(attempt: ActivityAttempt) -> tuple[str, int]:
    try:
        value = json.loads(attempt.attempt_id)
        if not isinstance(value, list) or len(value) != 2:
            raise ValueError
        instance, occurrence = value
        _name(instance, "attempt instance")
        _occurrence(occurrence)
        return instance, occurrence
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid Local Activity attempt identity {attempt.attempt_id!r}") from error


def _emit_attempt(name: str, attempt: ActivityAttempt, **fields: object) -> None:
    instance, occurrence = _attempt_key(attempt)
    log.emit(
        name,
        instance=instance,
        occurrence=occurrence,
        attempt=attempt.attempt_id,
        epoch=attempt.epoch,
        claimant=attempt.claimant,
        queue=attempt.queue,
        activity=attempt.invocation.activity,
        **fields,
    )


def _acknowledge_terminal_retry(connection: sqlite3.Connection, attempt: ActivityAttempt, outcome: object) -> bool:
    if not isinstance(attempt, ActivityAttempt):
        raise TypeError("custody operation requires ActivityAttempt")
    instance, occurrence = _attempt_key(attempt)
    row = connection.execute(
        "SELECT epoch,claimant,outcome FROM impetus_local_dispatch_terminals WHERE instance=? AND occurrence=?",
        (instance, occurrence),
    ).fetchone()
    if row is None:
        return False
    encoded = _encode_json(outcome, "outcome")
    if row == (int(attempt.epoch), attempt.claimant, encoded):
        return True
    raise ValueError(f"conflicting terminal report for Activity attempt {attempt.attempt_id}")


def _terminalize_exhausted(
    connection: sqlite3.Connection, now: int, queues: Sequence[str]
) -> tuple[tuple[str, int, int, str], ...]:
    marks = ",".join("?" for _ in queues)
    # An expired retryable lease becomes delayed work before another claimant
    # can see it. Backoff is anchored at the durable lease expiry, not at the
    # later sweep time.
    retryable = connection.execute(
        f"SELECT t.instance,t.occurrence,t.epoch,t.deadline,t.invocation FROM impetus_local_dispatch_tasks t "
        f"LEFT JOIN impetus_local_dispatch_terminals x USING(instance,occurrence) WHERE x.occurrence IS NULL "
        f"AND t.queue IN ({marks}) AND t.epoch>0 AND t.deadline<=? "
        "AND t.epoch<json_extract(t.invocation,'$.policy.attempts')",
        (*queues, now),
    ).fetchall()
    for instance, occurrence, epoch, expiry, encoded in retryable:
        invocation = _decode_invocation(encoded)
        available = expiry + _milliseconds(invocation.policy.retry_policy.delay(epoch))
        connection.execute(
            "UPDATE impetus_local_dispatch_tasks SET available_at=? WHERE instance=? AND occurrence=?",
            (available, instance, occurrence),
        )
    rows = connection.execute(
        f"SELECT t.instance,t.occurrence,t.epoch,t.claimant FROM impetus_local_dispatch_tasks t "
        f"LEFT JOIN impetus_local_dispatch_terminals x USING(instance,occurrence) WHERE x.occurrence IS NULL "
        f"AND t.queue IN ({marks}) AND ((t.epoch>0 AND t.deadline<=? "
        "AND t.epoch>=json_extract(t.invocation,'$.policy.attempts')) OR "
        "(json_extract(t.invocation,'$.policy.schedule_to_close') IS NOT NULL AND "
        "t.schedule_start + CAST(json_extract(t.invocation,'$.policy.schedule_to_close')*1000 AS INTEGER) + "
        "(json_extract(t.invocation,'$.policy.schedule_to_close')*1000 > "
        "CAST(json_extract(t.invocation,'$.policy.schedule_to_close')*1000 AS INTEGER)) <= ?))",
        (*queues, now, now),
    ).fetchall()
    for instance, occurrence, epoch, claimant in rows:
        noun = "attempt" if epoch == 1 else "attempts"
        failure = ActivityFailure(f"Local Dispatch deadline exhausted after {epoch} {noun}", kind="DeadlineExceeded")
        outcome = {"kind": "failed", "failure": _failure_wire(failure)}
        connection.execute(
            "INSERT OR IGNORE INTO impetus_local_dispatch_terminals(instance,occurrence,epoch,claimant,outcome) "
            "VALUES(?,?,?,?,?)",
            (instance, occurrence, epoch, claimant, _encode_json(outcome, "outcome")),
        )
    return tuple(rows)


def _initialize(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _raw_connect(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            objects = dict(
                connection.execute("SELECT name,type FROM sqlite_master WHERE name LIKE ?", (_PREFIX + "%",)).fetchall()
            )
            if not objects:
                for statement in _DDL:
                    connection.execute(statement)
            else:
                expected = {
                    "impetus_local_dispatch_schema": "table",
                    "impetus_local_dispatch_tasks": "table",
                    "impetus_local_dispatch_claimable": "index",
                    "impetus_local_dispatch_terminals": "table",
                }
                if objects != expected:
                    raise ValueError(
                        f"{path}: foreign or unversioned Local Dispatch schema; migration is not supported"
                    )
                rows = connection.execute("SELECT component,version FROM impetus_local_dispatch_schema").fetchall()
                if rows == [("dispatch", 1)]:
                    _migrate_v1(connection)
                    connection.execute("UPDATE impetus_local_dispatch_schema SET version=2 WHERE component='dispatch'")
                    rows = [("dispatch", 2)]
                if rows != [("dispatch", _VERSION)]:
                    raise ValueError(f"{path}: unsupported Local Dispatch schema {rows!r}; migration is not supported")
                _validate_shape(connection, path)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
    with _connect(path):
        pass


def _validate_shape(connection: sqlite3.Connection, path: Path) -> None:
    expected_sql = {
        "impetus_local_dispatch_schema": _DDL[0],
        "impetus_local_dispatch_tasks": _DDL[2],
        "impetus_local_dispatch_claimable": _DDL[3],
        "impetus_local_dispatch_terminals": _DDL[4],
    }
    actual_sql = dict(
        connection.execute(
            "SELECT name,sql FROM sqlite_master WHERE name IN (?,?,?,?)",
            tuple(expected_sql),
        )
    )

    def normalize(statement: str) -> str:
        return re.sub(r"\s+", " ", statement.strip()).lower()

    if {name: normalize(sql) for name, sql in actual_sql.items()} != {
        name: normalize(sql) for name, sql in expected_sql.items()
    }:
        raise ValueError(f"{path}: foreign current-version Local Dispatch DDL shape")

    expected_columns = {
        "impetus_local_dispatch_schema": [("component", "TEXT", 0, None, 1), ("version", "INTEGER", 1, None, 0)],
        "impetus_local_dispatch_tasks": [
            ("sequence", "INTEGER", 0, None, 1),
            ("instance", "TEXT", 1, None, 0),
            ("occurrence", "INTEGER", 1, None, 0),
            ("queue", "TEXT", 1, None, 0),
            ("invocation", "TEXT", 1, None, 0),
            ("epoch", "INTEGER", 1, "0", 0),
            ("claimant", "TEXT", 0, None, 0),
            ("deadline", "INTEGER", 0, None, 0),
            ("schedule_start", "INTEGER", 1, None, 0),
            ("attempt_start", "INTEGER", 0, None, 0),
            ("attempt_deadline", "INTEGER", 0, None, 0),
            ("available_at", "INTEGER", 1, None, 0),
            ("details", "TEXT", 0, None, 0),
        ],
        "impetus_local_dispatch_terminals": [
            ("sequence", "INTEGER", 0, None, 1),
            ("instance", "TEXT", 1, None, 0),
            ("occurrence", "INTEGER", 1, None, 0),
            ("epoch", "INTEGER", 1, None, 0),
            ("claimant", "TEXT", 0, None, 0),
            ("outcome", "TEXT", 1, None, 0),
        ],
    }
    for table, expected in expected_columns.items():
        actual = [(row[1], row[2], row[3], row[4], row[5]) for row in connection.execute(f"PRAGMA table_info({table})")]
        if actual != expected:
            raise ValueError(f"{path}: foreign current-version Local Dispatch table shape for {table}")
    index = connection.execute("PRAGMA index_info(impetus_local_dispatch_claimable)").fetchall()
    foreign = [
        (row[2], row[3], row[4], row[5], row[6], row[7])
        for row in connection.execute("PRAGMA foreign_key_list(impetus_local_dispatch_terminals)")
    ]
    expected_foreign = [
        ("impetus_local_dispatch_tasks", "instance", "instance", "NO ACTION", "NO ACTION", "NONE"),
        ("impetus_local_dispatch_tasks", "occurrence", "occurrence", "NO ACTION", "NO ACTION", "NONE"),
    ]
    if [row[2] for row in index] != ["queue", "sequence"] or foreign != expected_foreign:
        raise ValueError(f"{path}: foreign current-version Local Dispatch constraint or index shape")


def _migrate_v1(connection: sqlite3.Connection) -> None:
    """Transactionally rebuild the real v1 column order into exact v2 DDL."""
    now = _now(connection)
    tasks = connection.execute(
        "SELECT sequence,instance,occurrence,queue,invocation,epoch,claimant,deadline,details "
        "FROM impetus_local_dispatch_tasks ORDER BY sequence"
    ).fetchall()
    terminals = connection.execute(
        "SELECT sequence,instance,occurrence,epoch,claimant,outcome FROM impetus_local_dispatch_terminals ORDER BY sequence"
    ).fetchall()
    terminals = [
        (
            sequence,
            instance,
            occurrence,
            epoch,
            claimant,
            _encode_json(
                {"kind": "failed", "failure": _failure_wire(ActivityFailure(error=outcome["error"]))}
                if (outcome := json.loads(encoded)).get("kind") == "failed" and "error" in outcome
                else outcome,
                "outcome",
            ),
        )
        for sequence, instance, occurrence, epoch, claimant, encoded in terminals
    ]
    connection.execute("DROP TABLE impetus_local_dispatch_terminals")
    connection.execute("DROP INDEX impetus_local_dispatch_claimable")
    connection.execute("DROP TABLE impetus_local_dispatch_tasks")
    connection.execute(_DDL[2])
    connection.execute(_DDL[3])
    connection.execute(_DDL[4])
    for sequence, instance, occurrence, queue, encoded, epoch, claimant, deadline, details in tasks:
        invocation = _decode_invocation(encoded)
        canonical = _encode_invocation(invocation)
        connection.execute(
            "INSERT INTO impetus_local_dispatch_tasks(sequence,instance,occurrence,queue,invocation,epoch,claimant,"
            "deadline,schedule_start,attempt_start,attempt_deadline,available_at,details) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                sequence,
                instance,
                occurrence,
                queue,
                canonical,
                epoch,
                claimant,
                deadline,
                now,
                now if epoch else None,
                None,
                now,
                details,
            ),
        )
    connection.executemany(
        "INSERT INTO impetus_local_dispatch_terminals(sequence,instance,occurrence,epoch,claimant,outcome) VALUES(?,?,?,?,?,?)",
        terminals,
    )


class _transaction:
    def __init__(self, path: Path):
        self.connection = _connect(path)

    def __enter__(self):
        self.connection.execute("BEGIN IMMEDIATE")
        return self.connection

    def __exit__(self, kind, value, traceback):
        try:
            self.connection.commit() if kind is None else self.connection.rollback()
        finally:
            self.connection.close()


def _connect(path: Path) -> sqlite3.Connection:
    connection = _raw_connect(path)
    deadline = time.monotonic() + 5
    while True:
        try:
            mode = connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            break
        except sqlite3.OperationalError as error:
            if "locked" not in str(error).lower() or time.monotonic() >= deadline:
                connection.close()
                raise
            time.sleep(0.01)
    if str(mode).lower() != "wal":
        connection.close()
        raise ValueError(f"{path}: SQLite refused WAL mode")
    return connection


def _raw_connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=5, isolation_level=None)
    connection.execute("PRAGMA busy_timeout=5000")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA synchronous=FULL")
    return connection


def _now(connection: sqlite3.Connection) -> int:
    return connection.execute(
        "SELECT CAST(strftime('%s','now') AS INTEGER) * 1000 + CAST(substr(strftime('%f','now'),4,3) AS INTEGER)"
    ).fetchone()[0]


def _name(value: object, noun: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError(f"Local Dispatch {noun} must be a non-empty string without NUL")
    return value


def _occurrence(value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("Local Dispatch occurrence must be a positive integer")


def _timeout(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError("wait timeout must be a non-negative number")
    return float(value)


def _faithful(value: object, noun: str) -> object:
    return json.loads(_encode_json(value, noun))


def _encode_json(value: object, noun: str) -> str:
    try:
        return json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{noun} must be JSON-faithful: {error}") from error


def _encode_invocation(value: ActivityInvocation) -> str:
    return _encode_json(
        {
            "activity": value.activity,
            "input": value.input,
            "policy": {
                "attempts": value.policy.attempts,
                "heartbeat_timeout": value.policy.heartbeat_timeout,
                "initial_interval": value.policy.initial_interval,
                "coefficient": value.policy.coefficient,
                "max_interval": value.policy.max_interval,
                "jitter": value.policy.jitter,
                "start_to_close": value.policy.start_to_close,
                "schedule_to_close": value.policy.schedule_to_close,
            },
            "correlation": value.correlation,
            "idempotency": value.idempotency,
        },
        "Activity invocation",
    )


def _decode_invocation(value: str) -> ActivityInvocation:
    try:
        data = json.loads(value)
        fields = {"activity", "input", "policy", "correlation", "idempotency"}
        if not isinstance(data, dict) or set(data) != fields:
            raise ValueError(f"expected exact fields {sorted(fields)}")
        policy = data["policy"]
        legacy = {"attempts", "heartbeat_timeout"}
        policy_fields = legacy | {
            "initial_interval",
            "coefficient",
            "max_interval",
            "jitter",
            "start_to_close",
            "schedule_to_close",
        }
        if not isinstance(policy, dict) or set(policy) not in (legacy, policy_fields):
            raise ValueError("policy expected exact legacy or current fields")
        if any(isinstance(policy[name], bool) or not isinstance(policy[name], int) for name in legacy):
            raise ValueError("policy fields must be integers")
        return ActivityInvocation(
            data["activity"],
            input=data["input"],
            policy=ExecutionPolicy(**policy),
            correlation=data["correlation"],
            idempotency=data["idempotency"],
        )
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        raise ValueError(f"corrupt durable Activity invocation: {error}") from error


def _json(value: str | None) -> object:
    return None if value is None else json.loads(value)


def _decode_outcome(value: str) -> object:
    data = json.loads(value)
    if data["kind"] == "completed":
        return data["value"]
    return ActivityFailure(**(data["failure"] if "failure" in data else {"error": data["error"]}))


def _failure_wire(failure: ActivityFailure) -> dict[str, object]:
    return {
        "error": failure.error,
        "kind": failure.kind,
        "details": failure.details,
        "retryable": failure.retryable,
        "retry_after": failure.retry_after,
    }


def _milliseconds(seconds: float) -> int:
    return math.ceil(seconds * 1000) if seconds > 0 else 0


__all__ = ["LocalDispatch", "LocalWorkerDispatch"]
