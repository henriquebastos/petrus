"""Focused production Local Dispatch custody contract."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import replace
from multiprocessing import get_context
from pathlib import Path
from typing import cast

import pytest

from petrus.motus.activity import ActivityFailure, ActivityInvocation, ExecutionPolicy
from petrus.motus.dispatch import (
    ActivityAttempt,
    CancellationDisposition,
    CancellationInstruction,
    Dispatch,
    LocalDispatch,
    LocalWorkerDispatch,
)
from petrus.engine import Engine
from petrus.impetus.history import (
    ActivityCompleted,
    ActivityRequested,
    ActivityTerminalQuarantined,
    FiringCompleted,
    TokensInitialized,
)
from petrus.impetus.history_store import JsonlHistoryStore, SqliteHistoryStore
from petrus.impetus.petrinet import Arc, Marking, Net, NetPath, Place, Token, Transition
from petrus.motus.worker import Worker


def invocation(
    activity: str = "work",
    *,
    attempts: int = 2,
    timeout: int = 30,
    value=1,
    **policy,
):
    return ActivityInvocation(
        activity,
        input={"value": value},
        policy=ExecutionPolicy(attempts=attempts, heartbeat_timeout=timeout, **policy),
        correlation="correlation",
        idempotency="idempotency",
    )


def _start_dispatch(path: str, instance: str, results) -> None:
    try:
        LocalDispatch(path, instance=instance)
        results.put(None)
    except BaseException as error:
        results.put(repr(error))


def _claim_all(path: str, claimant: str, results) -> None:
    custody = LocalWorkerDispatch(path, _claimant=claimant)
    claimed = []
    while (attempt := custody.claim()) is not None:
        claimed.append(json.loads(attempt.attempt_id)[1])
        custody.complete(attempt, claimant)
    results.put((claimant, claimed))


def require_claim(custody) -> ActivityAttempt:
    attempt = custody.claim()
    assert attempt is not None, f"expected {custody.claimant!r} to claim work from {custody.queues!r}"
    return attempt


class _ManualProviderClock:
    def __init__(self, at: int = 0):
        self.at = at

    def now_ms(self) -> int:
        return self.at

    def advance_to(self, instant: int) -> None:
        if instant < self.at:
            raise ValueError("provider clock cannot rewind")
        self.at = instant


class _ProviderClockValue:
    def __init__(self, value: object):
        self.value = value

    def now_ms(self) -> int:
        return cast(int, self.value)


class _CountingActivity:
    def __init__(self, *, poison_prepare: bool = False):
        self.poison_prepare = poison_prepare
        self.prepared = 0
        self.projected = 0

    def prepare(self, binding):
        if self.poison_prepare:
            raise AssertionError("reconciliation reran Activity prepare")
        self.prepared += 1
        return invocation(value=binding.tokens[0].data)

    def project(self, binding, result):
        self.projected += 1
        return {NetPath("done"): (Token("Done", result),)}


class _RefuseActivityCompleted:
    """One-shot History seam for the post-collect, pre-accept crash window."""

    def __init__(self, history):
        self.history = history
        self.refused = False

    @property
    def records(self):
        return self.history.records

    def __iter__(self):
        return iter(self.history)

    def __len__(self):
        return len(self.history)

    def append(self, record):
        if isinstance(record, ActivityCompleted) and not self.refused:
            self.refused = True
            raise OSError("injected ActivityCompleted append refusal")
        self.history.append(record)

    def extend(self, records):
        if any(isinstance(record, ActivityCompleted) for record in records) and not self.refused:
            self.refused = True
            raise OSError("injected ActivityCompleted append refusal")
        self.history.extend(records)


def _activity_engine(tmp_path: Path, handler, *, load: bool = False, history=None):
    net = Net(
        places=[Place(NetPath("ready")), Place(NetPath("done"))],
        transitions=[Transition(NetPath("activity"), handler="activity")],
        arcs=[Arc(NetPath("ready"), NetPath("activity")), Arc(NetPath("activity"), NetPath("done"))],
    )
    history = JsonlHistoryStore(tmp_path / "history.jsonl") if history is None else history
    dispatch = LocalDispatch(tmp_path / "dispatch.db", instance="split-store")
    door = Engine.load if load else Engine.create
    options = {} if load else {"marking": Marking({NetPath("ready"): (Token("Input", 7),)})}
    return door(
        net,
        "split-store",
        history=history,
        dispatch=dispatch,
        handlers={"activity": handler},
        **options,
    )


def test_schema_reopens_and_refuses_unsupported_or_unversioned_shape(tmp_path: Path) -> None:
    path = tmp_path / "dispatch.db"
    assert isinstance(LocalDispatch(path, instance="one"), Dispatch)
    LocalDispatch(path, instance="two")
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE impetus_local_dispatch_schema SET version=99")
    with pytest.raises(ValueError, match="unsupported Local Dispatch schema"):
        LocalDispatch(path, instance="one")

    unversioned = tmp_path / "old.db"
    with sqlite3.connect(unversioned) as connection:
        connection.execute("CREATE TABLE impetus_local_dispatch_tasks(value)")
    with pytest.raises(ValueError, match="unversioned"):
        LocalDispatch(unversioned, instance="one")


def test_schema_initialization_is_atomic_under_spawned_process_startup(tmp_path: Path) -> None:
    path = tmp_path / "dispatch.db"
    context = get_context("spawn")
    results = context.Queue()
    processes = [
        context.Process(target=_start_dispatch, args=(str(path), f"instance-{number}", results)) for number in range(8)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(15)
        assert process.exitcode == 0
    assert [results.get(timeout=2) for _ in processes] == [None] * len(processes)
    LocalDispatch(path, instance="reopened")


def test_v1_schema_migrates_pending_active_and_terminal_custody_without_losing_fences(tmp_path: Path) -> None:
    path = tmp_path / "dispatch.db"
    legacy = json.dumps(
        {
            "activity": "work",
            "input": {"value": 1},
            "policy": {"attempts": 2, "heartbeat_timeout": 30},
            "correlation": "correlation",
            "idempotency": "idempotency",
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE impetus_local_dispatch_schema (
              component TEXT PRIMARY KEY CHECK(component='dispatch'), version INTEGER NOT NULL);
            INSERT INTO impetus_local_dispatch_schema VALUES ('dispatch', 1);
            CREATE TABLE impetus_local_dispatch_tasks (
              sequence INTEGER PRIMARY KEY AUTOINCREMENT,
              instance TEXT NOT NULL, occurrence INTEGER NOT NULL CHECK(occurrence>0),
              queue TEXT NOT NULL, invocation TEXT NOT NULL CHECK(json_valid(invocation)),
              epoch INTEGER NOT NULL DEFAULT 0 CHECK(epoch>=0), claimant TEXT, deadline INTEGER,
              details TEXT CHECK(details IS NULL OR json_valid(details)),
              CHECK((epoch=0 AND claimant IS NULL AND deadline IS NULL) OR
                    (epoch>0 AND claimant IS NOT NULL AND deadline IS NOT NULL)),
              UNIQUE(instance, occurrence));
            CREATE INDEX impetus_local_dispatch_claimable
              ON impetus_local_dispatch_tasks(queue, sequence);
            CREATE TABLE impetus_local_dispatch_terminals (
              sequence INTEGER PRIMARY KEY AUTOINCREMENT,
              instance TEXT NOT NULL, occurrence INTEGER NOT NULL, epoch INTEGER NOT NULL CHECK(epoch>0),
              claimant TEXT NOT NULL, outcome TEXT NOT NULL CHECK(json_valid(outcome)),
              UNIQUE(instance, occurrence),
              FOREIGN KEY(instance, occurrence)
                REFERENCES impetus_local_dispatch_tasks(instance, occurrence));
            """
        )
        connection.execute(
            "INSERT INTO impetus_local_dispatch_tasks(instance,occurrence,queue,invocation) VALUES('one',1,'default',?)",
            (legacy,),
        )
        connection.execute(
            "INSERT INTO impetus_local_dispatch_tasks(instance,occurrence,queue,invocation,epoch,claimant,deadline,details) "
            "VALUES('one',2,'default',?,1,'active',unixepoch('now')*1000+30000,'{\"progress\":1}')",
            (legacy,),
        )
        connection.execute(
            "INSERT INTO impetus_local_dispatch_tasks(instance,occurrence,queue,invocation,epoch,claimant,deadline) "
            "VALUES('one',3,'default',?,1,'done',unixepoch('now')*1000+30000)",
            (legacy,),
        )
        connection.execute(
            "INSERT INTO impetus_local_dispatch_terminals(instance,occurrence,epoch,claimant,outcome) "
            'VALUES(\'one\',3,1,\'done\',\'{"kind":"failed","error":"broken"}\')'
        )

    dispatch = LocalDispatch(path, instance="one")
    call = invocation()
    dispatch.dispatch(1, call)
    dispatch.dispatch(2, call)
    dispatch.dispatch(3, call)
    active = ActivityAttempt('["one",2]', "1", "active", "default", call, {"progress": 1}, "one")

    assert LocalWorkerDispatch(path, _claimant="active").heartbeat(active) == {"progress": 1}
    assert dispatch.collect() == ((3, ActivityFailure("broken")),)
    done = ActivityAttempt('["one",3]', "1", "done", "default", call, None, "one")
    LocalWorkerDispatch(path, _claimant="done").fail(done, "broken")
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT version FROM impetus_local_dispatch_schema").fetchone() == (3,)
        policy = json.loads(
            connection.execute("SELECT invocation FROM impetus_local_dispatch_tasks WHERE occurrence=1").fetchone()[0]
        )["policy"]
    assert set(policy) == {
        "attempts",
        "heartbeat_timeout",
        "initial_interval",
        "coefficient",
        "max_interval",
        "jitter",
        "start_to_close",
        "schedule_to_close",
    }


def test_v2_schema_migrates_to_durable_cancellation_tombstones(tmp_path: Path) -> None:
    path = tmp_path / "dispatch.db"
    dispatch = LocalDispatch(path, instance="one")
    dispatch.dispatch(1, invocation())
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE impetus_local_dispatch_cancellations")
        connection.execute("UPDATE impetus_local_dispatch_schema SET version=2")

    resumed = LocalDispatch(path, instance="one")

    assert resumed.cancel(CancellationInstruction(1, invocation(), 17)) is CancellationDisposition.RETIRED
    assert LocalWorkerDispatch(path, _claimant="worker").claim() is None
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT version FROM impetus_local_dispatch_schema").fetchone() == (3,)
        assert connection.execute(
            "SELECT occurrence,history_position FROM impetus_local_dispatch_cancellations"
        ).fetchall() == [(1, 17)]


def test_pending_and_absent_cancellation_are_durable_idempotent_tombstones(tmp_path: Path) -> None:
    path = tmp_path / "dispatch.db"
    dispatch = LocalDispatch(path, instance="one")
    call = invocation()
    dispatch.dispatch(1, call)

    pending = CancellationInstruction(1, call, 11)
    absent = CancellationInstruction(2, call, 12)
    assert dispatch.cancel(pending) is CancellationDisposition.RETIRED
    assert dispatch.cancel(absent) is CancellationDisposition.TOMBSTONED
    assert dispatch.cancel(pending) is CancellationDisposition.ACKNOWLEDGED

    # Recovery publication cannot resurrect either exact logical invocation.
    LocalDispatch(path, instance="one").dispatch(1, call)
    LocalDispatch(path, instance="one").dispatch(2, call)
    assert LocalWorkerDispatch(path, _claimant="worker").claim() is None
    with pytest.raises(ValueError, match="cancellation conflict"):
        dispatch.cancel(CancellationInstruction(1, call, 99))


def test_claimed_cancellation_fences_heartbeat_and_transports_exact_late_terminal(tmp_path: Path) -> None:
    path = tmp_path / "dispatch.db"
    dispatch = LocalDispatch(path, instance="one")
    call = invocation()
    dispatch.dispatch(1, call)
    custody = LocalWorkerDispatch(path, _claimant="worker")
    attempt = require_claim(custody)

    assert dispatch.cancel(CancellationInstruction(1, call, 11)) is CancellationDisposition.FENCED
    with pytest.raises(ValueError, match="stale"):
        custody.heartbeat(attempt)

    late = {"effect": "may-have-happened"}
    custody.complete(attempt, late)
    custody.complete(attempt, late)
    with pytest.raises(ValueError, match="conflicting terminal report"):
        custody.complete(attempt, {"effect": "different"})
    assert dispatch.collect() == ((1, late),)
    assert LocalWorkerDispatch(path, _claimant="other").claim() is None


def test_running_cancellation_fences_future_custody_and_reports_ambiguous_effect_for_quarantine(tmp_path: Path) -> None:
    path = tmp_path / "dispatch.db"
    dispatch = LocalDispatch(path, instance="one")
    call = invocation()
    dispatch.dispatch(1, call)
    entered = threading.Event()
    release = threading.Event()

    def work(invocation, *, context):
        entered.set()
        assert release.wait(5)
        return {"effect": "may-have-happened"}

    worker = Worker(dispatch.worker(worker_id="worker"), {"work": work})
    driving = threading.Thread(target=lambda: worker.run_available(limit=1))
    driving.start()
    assert entered.wait(5)

    assert dispatch.cancel(CancellationInstruction(1, call, 11)) is CancellationDisposition.FENCED
    release.set()
    driving.join(5)

    assert not driving.is_alive()
    assert dispatch.collect() == ((1, {"effect": "may-have-happened"}),)
    assert LocalWorkerDispatch(path, _claimant="other").claim() is None


def test_terminal_before_cancellation_is_reported_as_terminal_not_erased(tmp_path: Path) -> None:
    path = tmp_path / "dispatch.db"
    dispatch = LocalDispatch(path, instance="one")
    call = invocation()
    dispatch.dispatch(1, call)
    custody = LocalWorkerDispatch(path, _claimant="worker")
    custody.complete(require_claim(custody), {"done": True})

    assert dispatch.cancel(CancellationInstruction(1, call, 11)) is CancellationDisposition.TERMINAL
    assert dispatch.collect() == ((1, {"done": True}),)


def test_current_version_foreign_shape_and_invalid_custody_states_are_refused(tmp_path: Path) -> None:
    path = tmp_path / "dispatch.db"
    LocalDispatch(path, instance="one")
    with sqlite3.connect(path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO impetus_local_dispatch_tasks(instance,occurrence,queue,invocation,epoch) "
                "VALUES('x',1,'q','{}',1)"
            )
        connection.execute("DROP INDEX impetus_local_dispatch_claimable")
        connection.execute("CREATE INDEX impetus_local_dispatch_claimable ON impetus_local_dispatch_tasks(sequence)")
    with pytest.raises(ValueError, match="foreign current-version Local Dispatch .*shape"):
        LocalDispatch(path, instance="one")


def test_routes_and_instances_share_domain_but_claim_by_queue(tmp_path: Path) -> None:
    path = tmp_path / "dispatch.db"
    one = LocalDispatch(path, instance="one", default_queue="general", activity_queues={"work": "cpu"})
    two = LocalDispatch(path, instance="two", default_queue="general")
    one.dispatch(1, invocation())
    two.dispatch(1, invocation("other"))
    cpu = LocalWorkerDispatch(path, queues=["cpu"], _claimant="worker-cpu")
    general = LocalWorkerDispatch(path, queues=["general"], _claimant="worker-general")
    assert require_claim(cpu).instance == "one"
    assert require_claim(general).instance == "two"
    assert cpu.claim() is None


def test_exact_publication_route_recovery_and_live_route_preservation(tmp_path: Path) -> None:
    path = tmp_path / "dispatch.db"
    first = LocalDispatch(path, instance="one", default_queue="a")
    first.dispatch(1, invocation(value=True))
    moved = LocalDispatch(path, instance="one", default_queue="b")
    moved.dispatch(1, invocation(value=True))
    attempt = require_claim(LocalWorkerDispatch(path, queues=["b"], _claimant="worker"))
    assert attempt.queue == "b"
    LocalDispatch(path, instance="one", default_queue="c").dispatch(1, invocation(value=True))
    assert LocalWorkerDispatch(path, queues=["c"], _claimant="other").claim() is None
    with pytest.raises(ValueError, match="publication conflict"):
        moved.dispatch(1, invocation(value=1))  # JSON true and 1 are exact conflicts


def test_expired_retryable_route_moves_and_terminal_collection_ignores_current_route(tmp_path: Path) -> None:
    path = tmp_path / "dispatch.db"
    original = LocalDispatch(path, instance="one", default_queue="a")
    call = invocation()
    original.dispatch(1, call)
    first = require_claim(LocalWorkerDispatch(path, queues=["a"], _claimant="old"))
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE impetus_local_dispatch_tasks SET deadline=unixepoch('now') * 1000 WHERE instance='one'"
        )
    moved = LocalDispatch(path, instance="one", default_queue="b")
    moved.dispatch(1, call)
    new_custody = LocalWorkerDispatch(path, queues=["b"], _claimant="new")
    second = require_claim(new_custody)
    assert int(second.epoch) == int(first.epoch) + 1
    new_custody.complete(second, "done")
    LocalDispatch(path, instance="one", default_queue="c").dispatch(1, call)
    assert moved.collect() == ((1, "done"),)


def test_heartbeat_details_are_detached_and_omitted_preserves_but_none_replaces(tmp_path: Path) -> None:
    dispatch = LocalDispatch(tmp_path / "dispatch.db", instance="one")
    dispatch.dispatch(1, invocation())
    custody = LocalWorkerDispatch(dispatch.path, _claimant="worker")
    attempt = require_claim(custody)
    details = {"at": [1]}
    replaced = custody.heartbeat(attempt, details=details)
    details["at"].append(2)
    preserved = custody.heartbeat(attempt)
    assert replaced == preserved == {"at": [1]}
    assert custody.heartbeat(attempt, details=None) is None


def test_heartbeat_refuses_detached_queue_or_policy_tampering_without_renewing_lease(tmp_path: Path) -> None:
    dispatch = LocalDispatch(tmp_path / "dispatch.db", instance="one")
    dispatch.dispatch(1, invocation(timeout=1))
    custody = LocalWorkerDispatch(dispatch.path, _claimant="worker")
    attempt = require_claim(custody)
    with sqlite3.connect(dispatch.path) as connection:
        original_deadline = connection.execute("SELECT deadline FROM impetus_local_dispatch_tasks").fetchone()[0]

    for tampered in (
        replace(attempt, queue="other"),
        replace(
            attempt,
            invocation=replace(attempt.invocation, policy=ExecutionPolicy(attempts=2, heartbeat_timeout=3_600)),
        ),
    ):
        with pytest.raises(ValueError, match="stale Activity attempt"):
            custody.heartbeat(tampered)

    with sqlite3.connect(dispatch.path) as connection:
        assert (
            connection.execute("SELECT deadline FROM impetus_local_dispatch_tasks").fetchone()[0] == original_deadline
        )


def test_one_second_lease_survives_the_next_wall_clock_second_boundary(tmp_path: Path) -> None:
    while time.time() % 1 < 0.85:
        time.sleep(0.01)
    dispatch = LocalDispatch(tmp_path / "dispatch.db", instance="one")
    dispatch.dispatch(1, invocation(timeout=1))
    custody = LocalWorkerDispatch(dispatch.path, _claimant="worker")
    attempt = require_claim(custody)
    time.sleep(0.2)
    assert custody.heartbeat(attempt) is None


def test_heartbeat_renews_without_a_hard_attempt_deadline(tmp_path: Path) -> None:
    dispatch = LocalDispatch(tmp_path / "dispatch.db", instance="one")
    dispatch.dispatch(1, invocation(timeout=1))
    custody = LocalWorkerDispatch(dispatch.path, _claimant="worker")
    attempt = require_claim(custody)
    with sqlite3.connect(dispatch.path) as connection:
        original, hard = connection.execute(
            "SELECT deadline,attempt_deadline FROM impetus_local_dispatch_tasks"
        ).fetchone()
    time.sleep(0.02)
    custody.heartbeat(attempt)
    with sqlite3.connect(dispatch.path) as connection:
        renewed = connection.execute("SELECT deadline FROM impetus_local_dispatch_tasks").fetchone()[0]
    assert hard is None
    assert renewed > original


def test_subsecond_deadlines_and_retry_delays_round_up_from_millisecond_clock(tmp_path: Path) -> None:
    dispatch = LocalDispatch(tmp_path / "dispatch.db", instance="one")
    dispatch.dispatch(1, invocation(attempts=2, start_to_close=0.0001, schedule_to_close=1.0001))
    custody = LocalWorkerDispatch(dispatch.path, _claimant="worker")
    require_claim(custody)
    with sqlite3.connect(dispatch.path) as connection:
        schedule_start, available_at, attempt_start, attempt_deadline = connection.execute(
            "SELECT schedule_start,available_at,attempt_start,attempt_deadline FROM impetus_local_dispatch_tasks"
        ).fetchone()
    assert schedule_start == available_at
    assert attempt_deadline == attempt_start + 1

    retry_dispatch = LocalDispatch(tmp_path / "retry.db", instance="one")
    retry_dispatch.dispatch(2, invocation(attempts=2, initial_interval=0.0001))
    retry_custody = LocalWorkerDispatch(retry_dispatch.path, _claimant="worker")
    retry = require_claim(retry_custody)
    retry_custody.fail(retry, ActivityFailure("later", retryable=True))
    with sqlite3.connect(retry_dispatch.path) as connection:
        deadline, available = connection.execute(
            "SELECT deadline,available_at FROM impetus_local_dispatch_tasks WHERE occurrence=2"
        ).fetchone()
    assert available == deadline + 1


def test_oversized_heartbeat_details_are_rejected_before_persistence(tmp_path: Path) -> None:
    dispatch = LocalDispatch(tmp_path / "dispatch.db", instance="one")
    dispatch.dispatch(1, invocation())
    custody = LocalWorkerDispatch(dispatch.path, _claimant="worker")
    attempt = require_claim(custody)
    with pytest.raises(ValueError, match="limit"):
        custody.heartbeat(attempt, details="x" * 65_536)
    assert custody.heartbeat(attempt, details={"still": "usable"}) == {"still": "usable"}


def test_failure_retries_then_terminal_success_is_exact_and_session_redelivers(tmp_path: Path) -> None:
    path = tmp_path / "dispatch.db"
    dispatch = LocalDispatch(path, instance="one")
    call = invocation()
    dispatch.dispatch(1, call)
    custody = LocalWorkerDispatch(path, _claimant="worker")
    first = require_claim(custody)
    custody.fail(first, "transient")
    second = require_claim(custody)
    assert second.epoch == "2"
    result = {"tuple canonicalizes": [1, True, None]}
    custody.complete(second, result)
    assert dispatch.collect() == ((1, result),)
    assert dispatch.collect() == ()
    restarted = LocalDispatch(path, instance="one")
    assert restarted.collect() == ()
    restarted.dispatch(1, call)
    assert restarted.collect() == ((1, result),)


def test_two_retryable_failures_then_success_keep_one_logical_invocation(tmp_path: Path) -> None:
    dispatch = LocalDispatch(tmp_path / "dispatch.db", instance="one")
    call = invocation(attempts=3)
    dispatch.dispatch(1, call)
    custody = LocalWorkerDispatch(dispatch.path, _claimant="worker")
    attempts = []
    for number in (1, 2):
        attempt = require_claim(custody)
        attempts.append(attempt)
        custody.fail(
            attempt,
            ActivityFailure(
                f"transient-{number}",
                kind="Unavailable",
                details={"attempt": number},
                retryable=True,
            ),
        )
    final = require_claim(custody)
    attempts.append(final)
    custody.complete(final, "done")

    assert [attempt.epoch for attempt in attempts] == ["1", "2", "3"]
    assert all(attempt.invocation == call for attempt in attempts)
    assert {(attempt.invocation.correlation, attempt.invocation.idempotency) for attempt in attempts} == {
        ("correlation", "idempotency")
    }
    assert dispatch.collect() == ((1, "done"),)


def test_delayed_retry_schedule_survives_restart_under_the_provider_clock(tmp_path: Path) -> None:
    path = tmp_path / "dispatch.db"
    clock = _ManualProviderClock(1_000)
    dispatch = LocalDispatch(path, instance="one", clock=clock)
    call = invocation(attempts=2, initial_interval=60)
    dispatch.dispatch(1, call)
    worker = LocalWorkerDispatch(path, _claimant="first", clock=clock)
    worker.fail(
        require_claim(worker),
        ActivityFailure("later", kind="Unavailable", retryable=True, retry_after=30),
    )

    restarted = LocalDispatch(path, instance="one", clock=clock)
    restarted.dispatch(1, call)
    replacement = LocalWorkerDispatch(path, _claimant="replacement", clock=clock)
    assert replacement.claim() is None
    clock.advance_to(60_999)
    assert replacement.claim() is None
    clock.advance_to(61_000)
    assert require_claim(replacement).epoch == "2"


@pytest.mark.parametrize("value", [True, -1, 1.5, "1", 2**63])
def test_provider_clock_refuses_non_integer_negative_and_out_of_range_values(tmp_path: Path, value: object) -> None:
    dispatch = LocalDispatch(tmp_path / "dispatch.db", instance="one", clock=_ProviderClockValue(value))

    with pytest.raises(ValueError, match="nonnegative signed-64-bit millisecond integer"):
        dispatch.dispatch(1, invocation())


def test_dispatch_worker_shares_provider_clock_monotonicity_guard(tmp_path: Path) -> None:
    clock = _ManualProviderClock(1_000)
    dispatch = LocalDispatch(tmp_path / "dispatch.db", instance="one", clock=clock)
    dispatch.dispatch(1, invocation())
    worker = dispatch.worker(worker_id="worker")
    attempt = require_claim(worker)

    clock.at = 999
    with pytest.raises(ValueError, match="must not rewind"):
        worker.heartbeat(attempt)


def test_nonretryable_failure_terminalizes_without_spending_remaining_attempts(tmp_path: Path) -> None:
    dispatch = LocalDispatch(tmp_path / "dispatch.db", instance="one")
    dispatch.dispatch(1, invocation(attempts=5))
    custody = LocalWorkerDispatch(dispatch.path, _claimant="worker")
    custody.fail(
        require_claim(custody),
        ActivityFailure("invalid", kind="InvalidRequest", details={"field": "name"}, retryable=False),
    )

    assert custody.claim() is None
    assert dispatch.collect() == ((1, ActivityFailure("invalid", "InvalidRequest", {"field": "name"}, False)),)


def test_schedule_to_close_can_expire_before_first_claim(tmp_path: Path) -> None:
    dispatch = LocalDispatch(tmp_path / "dispatch.db", instance="one")
    dispatch.dispatch(1, invocation(attempts=3, schedule_to_close=10))
    with sqlite3.connect(dispatch.path) as connection:
        connection.execute("UPDATE impetus_local_dispatch_tasks SET schedule_start=0")

    assert LocalWorkerDispatch(dispatch.path, _claimant="worker").claim() is None
    [(occurrence, failure)] = dispatch.collect()
    assert occurrence == 1
    assert isinstance(failure, ActivityFailure)
    assert failure.kind == "DeadlineExceeded"


def test_start_to_close_deadline_fences_the_attempt_and_terminalizes_when_exhausted(tmp_path: Path) -> None:
    dispatch = LocalDispatch(tmp_path / "dispatch.db", instance="one")
    dispatch.dispatch(1, invocation(attempts=1, start_to_close=10))
    custody = LocalWorkerDispatch(dispatch.path, _claimant="worker")
    attempt = require_claim(custody)
    with sqlite3.connect(dispatch.path) as connection:
        connection.execute("UPDATE impetus_local_dispatch_tasks SET deadline=0,attempt_deadline=0 WHERE instance='one'")

    with pytest.raises(ValueError, match="stale"):
        custody.heartbeat(attempt)
    assert custody.claim() is None
    [(occurrence, failure)] = dispatch.collect()
    assert occurrence == 1
    assert isinstance(failure, ActivityFailure)
    assert failure.kind == "DeadlineExceeded"


@pytest.mark.parametrize(
    "operation,outcome,conflict", [("complete", {"ok": True}, {"ok": False}), ("fail", "broken", "other")]
)
def test_exact_terminal_report_retry_acknowledges_and_conflict_is_refused(
    tmp_path: Path, operation: str, outcome: object, conflict: object
) -> None:
    dispatch = LocalDispatch(tmp_path / "dispatch.db", instance="one")
    dispatch.dispatch(1, invocation(attempts=1))
    custody = LocalWorkerDispatch(dispatch.path, _claimant="worker")
    attempt = require_claim(custody)
    report = getattr(custody, operation)
    report(attempt, outcome)
    report(attempt, outcome)
    with pytest.raises(ValueError, match="conflicting terminal report"):
        report(attempt, conflict)
    with pytest.raises(ValueError, match="conflicting terminal report"):
        report(replace(attempt, claimant="other"), outcome)
    with pytest.raises(ValueError, match="conflicting terminal report"):
        report(replace(attempt, epoch=str(int(attempt.epoch) + 1)), outcome)


def test_final_activity_failure_and_expired_final_attempt_are_durable(tmp_path: Path) -> None:
    path = tmp_path / "dispatch.db"
    dispatch = LocalDispatch(path, instance="one")
    dispatch.dispatch(1, invocation(attempts=1))
    custody = LocalWorkerDispatch(path, _claimant="worker")
    custody.fail(require_claim(custody), "broken")
    assert dispatch.collect() == ((1, ActivityFailure("broken")),)

    other = LocalDispatch(path, instance="two")
    other.dispatch(1, invocation(attempts=1))
    expired = require_claim(LocalWorkerDispatch(path, _claimant="old"))
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE impetus_local_dispatch_tasks SET deadline=unixepoch('now') * 1000 WHERE instance='two'"
        )
    assert LocalWorkerDispatch(path, _claimant="poller").claim() is None
    [(occurrence, failure)] = other.collect()
    assert occurrence == 1
    assert isinstance(failure, ActivityFailure)
    with pytest.raises(ValueError, match="conflicting terminal report"):
        custody.complete(expired, "late")


def test_corrupt_durable_invocation_is_refused_contextually(tmp_path: Path) -> None:
    path = tmp_path / "dispatch.db"
    dispatch = LocalDispatch(path, instance="one")
    dispatch.dispatch(1, invocation())
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE impetus_local_dispatch_tasks SET invocation=?",
            (
                '{"activity":"work","input":null,"policy":{"attempts":true,"heartbeat_timeout":30},"correlation":null,"idempotency":null}',
            ),
        )
    with pytest.raises(ValueError, match="corrupt durable Activity invocation.*policy fields must be integers"):
        LocalWorkerDispatch(path, _claimant="worker").claim()


def test_spawned_claim_contention_distributes_distinct_work_once(tmp_path: Path) -> None:
    path = tmp_path / "dispatch.db"
    dispatch = LocalDispatch(path, instance="one")
    for occurrence in range(1, 25):
        dispatch.dispatch(occurrence, invocation(value=occurrence))
    context = get_context("spawn")
    results = context.Queue()
    processes = [
        context.Process(target=_claim_all, args=(str(path), f"worker-{number}", results)) for number in range(4)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(20)
        assert process.exitcode == 0
    distributions = [results.get(timeout=2) for _ in processes]
    occurrences = [occurrence for _, claimed in distributions for occurrence in claimed]
    assert sorted(occurrences) == list(range(1, 25)), distributions
    assert len(occurrences) == len(set(occurrences)), distributions


def test_stale_operations_are_fenced_after_reassignment_and_heartbeat_preserves_details(tmp_path: Path) -> None:
    path = tmp_path / "dispatch.db"
    dispatch = LocalDispatch(path, instance="one")
    dispatch.dispatch(1, invocation(timeout=1))
    old_custody = LocalWorkerDispatch(path, _claimant="old")
    old = require_claim(old_custody)
    assert old_custody.heartbeat(old, details={"progress": 3}) == {"progress": 3}
    assert LocalWorkerDispatch(path, _claimant="early").claim() is None
    with sqlite3.connect(path) as connection:
        connection.execute(
            "UPDATE impetus_local_dispatch_tasks SET deadline=unixepoch('now') * 1000 WHERE instance='one'"
        )
    replacement_custody = LocalWorkerDispatch(path, _claimant="replacement")
    replacement = require_claim(replacement_custody)
    assert replacement.latest_details == {"progress": 3}
    for operation in (
        lambda: old_custody.heartbeat(old),
        lambda: old_custody.complete(old, "late"),
        lambda: old_custody.fail(old, "late"),
    ):
        with pytest.raises(ValueError, match="stale"):
            operation()


def test_wait_terminalizes_exhausted_row_then_settles(tmp_path: Path) -> None:
    dispatch = LocalDispatch(tmp_path / "dispatch.db", instance="one")
    dispatch.dispatch(1, invocation(attempts=1))
    require_claim(LocalWorkerDispatch(dispatch.path, _claimant="old"))
    with sqlite3.connect(dispatch.path) as connection:
        connection.execute("UPDATE impetus_local_dispatch_tasks SET deadline=unixepoch('now') * 1000")
    custody = LocalWorkerDispatch(dispatch.path, _claimant="waiter")
    assert custody.wait(0) is False
    assert custody.wait(0) is False
    assert isinstance(dispatch.collect()[0][1], ActivityFailure)


def test_engine_reconciles_canonical_request_missing_from_local_custody(tmp_path: Path) -> None:
    original_handler = _CountingActivity()
    original = _activity_engine(tmp_path, original_handler)
    assert original.advance().ready is True
    [request] = [record for record in original.records if isinstance(record, ActivityRequested)]
    original.close()

    # Reproduce the split-store crash state: canonical outbox fact committed,
    # while the independently durable Local custody publication is absent.
    with sqlite3.connect(tmp_path / "dispatch.db") as connection:
        connection.execute("DELETE FROM impetus_local_dispatch_tasks WHERE instance='split-store'")

    poison = _CountingActivity(poison_prepare=True)
    resumed = _activity_engine(tmp_path, poison, load=True)
    assert resumed.advance().waiting is True
    attempt = require_claim(LocalWorkerDispatch(tmp_path / "dispatch.db", _claimant="worker"))

    assert attempt.invocation == ActivityInvocation(
        request.activity,
        input=request.input,
        policy=request.policy,
        correlation=request.correlation,
        idempotency=request.idempotency,
    )
    assert poison.prepared == 0
    assert LocalWorkerDispatch(tmp_path / "dispatch.db", _claimant="other").claim() is None


def test_engine_close_fences_claimed_local_attempt_and_canonically_quarantines_its_late_result(
    tmp_path: Path,
) -> None:
    source, ready, work, done = map(NetPath, ("source", "ready", "work", "done"))
    net = Net(
        places=[Place(ready), Place(done)],
        transitions=[Transition(source), Transition(work, handler="activity")],
        arcs=[Arc(source, ready), Arc(ready, work), Arc(work, done)],
    )
    history = JsonlHistoryStore(tmp_path / "history.jsonl")
    dispatch = LocalDispatch(tmp_path / "dispatch.db", instance="scoped-local")
    engine = Engine.create(
        net,
        "scoped-local",
        history=history,
        dispatch=dispatch,
        handlers={"activity": _CountingActivity()},
    )
    scope = engine.open_scope("draft")
    engine.deliver(source, Token("Input", 7), identity="draft-7", scope=scope)
    engine.advance()
    custody = LocalWorkerDispatch(dispatch.path, _claimant="worker")
    attempt = require_claim(custody)

    engine.close_scope(scope)
    custody.complete(attempt, {"effect": "ambiguous"})
    engine.advance()

    quarantined = [record for record in engine.records if isinstance(record, ActivityTerminalQuarantined)]
    assert len(quarantined) == 1
    assert quarantined[0].occurrence == json.loads(attempt.attempt_id)[1]
    assert not engine.marking


def test_engine_recollects_terminal_result_after_canonical_acceptance_refusal(tmp_path: Path) -> None:
    handler = _CountingActivity()
    durable = JsonlHistoryStore(tmp_path / "history.jsonl")
    refusing = _RefuseActivityCompleted(durable)
    original = _activity_engine(tmp_path, handler, history=refusing)
    assert original.advance().ready is True
    custody = LocalWorkerDispatch(tmp_path / "dispatch.db", _claimant="worker")
    attempt = require_claim(custody)
    occurrence = json.loads(attempt.attempt_id)[1]
    terminal = {"status": "durably-complete"}
    custody.complete(attempt, terminal)

    with pytest.raises(OSError, match="injected ActivityCompleted append refusal"):
        original.advance()
    with pytest.raises(RuntimeError, match="Engine is poisoned"):
        original.advance()
    assert handler.prepared == 1

    recovered_handler = _CountingActivity(poison_prepare=True)
    recovered = _activity_engine(tmp_path, recovered_handler, load=True)
    outcome = recovered.advance()
    records = JsonlHistoryStore(tmp_path / "history.jsonl").records

    assert [firing.occurrence for firing in outcome.firings] == [occurrence]
    assert recovered_handler.prepared == 0
    assert recovered_handler.projected == 1
    assert [record.result for record in records if isinstance(record, ActivityCompleted)] == [terminal]
    assert len([record for record in records if isinstance(record, FiringCompleted)]) == 1
    assert recovered.in_flight == ()


def test_sqlite_history_tables_coexist_untouched(tmp_path: Path) -> None:
    path = tmp_path / "application.db"
    history = SqliteHistoryStore(path, "one")
    record = TokensInitialized(NetPath("ready"), (Token.black(),), instant=0)
    history.append(record)
    dispatch = LocalDispatch(path, instance="one")
    dispatch.dispatch(1, invocation())
    assert SqliteHistoryStore(path, "one").records == (record,)
    with sqlite3.connect(path) as connection:
        names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master")}
    assert {"impetus_history_events", "impetus_local_dispatch_tasks"} <= names
