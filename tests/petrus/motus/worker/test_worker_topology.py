"""
The topology at process grain: a real one-Instance ``Engine`` over PostgreSQL
History + Absurd Dispatch and real ``python -m petrus.motus.worker`` subprocesses,
against the purpose-built net in ``tests.absurd_support`` — source ingress ->
impure activity on a queue-subscribing worker -> human-gate delivery -> done.

The kill tests are the ES-009 arming pattern, simplified per the DS4
commission: the WORKER dies by real SIGKILL mid-activity (the lease machinery
needs a genuinely dead process), while AUTHORITY crashes are staged in
process — a post-commit crash is faithfully "abandon the session objects"
(nothing uncommitted existed), and a mid-transaction crash is "close the
connection without committing" (the server aborts the open transaction
exactly as it does when the client is killed; the matrix proved that shape
with real SIGKILLs, s02/s04).
"""

from __future__ import annotations

# Python imports
import json
import os
import selectors
import signal
import subprocess
import sys
import time
from uuid import uuid4

# Pip imports
import psycopg
import pytest
from psycopg.types.json import Jsonb

import petrus.motus.worker._cli as worker_cli

from petrus.motus.activity import ActivityDeclaration, ActivityInvocation, ExecutionPolicy
from petrus.motus.dispatch.absurd import AbsurdDispatch, AbsurdWorkerDispatch, encode_invocation
from petrus.engine import DriveOutcome, Engine
from petrus.engine.absurd import create_engine, load_engine
from petrus.impetus.history import ActivityCompleted, ActivityRequested, CandidateSelected, InstanceCreated, ScopeClosed
from petrus.impetus.history.codec import encode_record
from petrus.impetus.history_store.postgres import PostgresHistoryStore
from petrus.impetus.instance import Instance, Status
from petrus.impetus.petrinet import Token
from petrus.motus.worker import Worker
from petrus.motus.worker._cli import _load_registry
from tests.absurd_support import (
    APPROVAL,
    CAPABILITY,
    DONE,
    INGRESS,
    ISSUE,
    OPERATOR,
    WORKED,
    ensure_fixture_tables,
    topology_handlers,
    topology_net,
)
from tests import REPO_ROOT

_OPEN_ENGINES: set[Engine] = set()


@pytest.fixture
def fixture_db(absurd_dsn):
    """The fake-external target and the kill switch, reset per test (effects accumulate across tests but their keys are per-test unique)."""
    with psycopg.connect(absurd_dsn, autocommit=True) as connection:
        ensure_fixture_tables(connection)
        connection.execute("DELETE FROM impetus_test.kill_switch")
        connection.execute("INSERT INTO impetus_test.kill_switch (armed) VALUES (FALSE)")
    yield absurd_dsn
    for engine in tuple(_OPEN_ENGINES):
        engine.close()
        _OPEN_ENGINES.remove(engine)


@pytest.fixture
def worker_factory(fixture_db):
    """Start real worker subprocesses (``python -m petrus.motus.worker``), barrier on their ready line, and reap every survivor at teardown."""
    processes: list[subprocess.Popen] = []

    def start(*, queues=(CAPABILITY,), claim_timeout=30, poll_interval=0.1, worker_id=None):
        command = [
            sys.executable,
            "-m",
            "petrus.motus.worker",
            "--provider",
            "absurd",
            "--dsn",
            fixture_db,
            "--registry",
            "tests.absurd_support:activities",
            "--claim-timeout",
            str(claim_timeout),
            "--poll-interval",
            str(poll_interval),
        ]
        for queue in queues:
            command += ["--queue", queue]
        if worker_id:
            command += ["--worker-id", worker_id]
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=REPO_ROOT,
            env={**os.environ, "IMPETUS_TEST_DSN": fixture_db},
        )
        processes.append(process)
        await_event(process, lambda event: event.get("ready"))
        return process

    yield start
    for process in processes:
        if process.poll() is None:
            process.kill()
            process.wait()


def await_event(process: subprocess.Popen, predicate, timeout: float = 30.0) -> dict:
    """Barrier-driven, never sleep-driven: read the worker's machine-readable stdout lines until one satisfies ``predicate``."""
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    deadline = time.monotonic() + timeout
    seen: list[str] = []
    while True:
        if not selector.select(timeout=max(0.0, deadline - time.monotonic())):
            process.kill()
            raise AssertionError(f"worker barrier timeout; saw {seen!r}")
        line = process.stdout.readline()
        if not line:
            if process.poll() is not None:
                raise AssertionError(f"worker exited early (rc={process.returncode}); saw {seen!r}")
            continue
        seen.append(line.strip())
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if predicate(event):
            selector.unregister(process.stdout)
            return event


def open_session(
    dsn: str,
    instance: str,
    *,
    load: bool = False,
    attempts: int = 1,
    project_poisoned: bool = False,
    default_queue: str = CAPABILITY,
    activities=(),
    default_heartbeat_timeout: int = 30,
) -> Engine:
    door = load_engine if load else create_engine
    joined = psycopg.connect(dsn, autocommit=False)
    listener = psycopg.connect(dsn, autocommit=True)
    engine = door(
        joined,
        topology_net(),
        instance,
        listen=listener,
        handlers=topology_handlers(attempts, project_poisoned),
        poll_interval=0.1,
        default_queue=default_queue,
        activities=activities,
        default_heartbeat_timeout=default_heartbeat_timeout,
    )
    _OPEN_ENGINES.add(engine)
    return engine


def close_session(engine: Engine) -> None:
    """Close both dedicated connections through their owning Engine."""
    engine.close()
    _OPEN_ENGINES.discard(engine)


def advance_until_blocked(session: Engine) -> DriveOutcome:
    """Pump immediately ready one-action turns until wait, sleep, or stop."""
    firings = []
    while True:
        outcome = session.advance()
        firings.extend(outcome.firings)
        if not outcome.ready:
            return DriveOutcome(tuple(firings), outcome.waiting, next_maturation=outcome.next_maturation)


def drive_until_rest(session: Engine, deadline_seconds: float = 30.0):
    """Pump ready turns and provider waits until the Engine stops."""
    deadline = time.monotonic() + deadline_seconds
    firings = []
    while True:
        outcome = advance_until_blocked(session)
        firings.extend(outcome.firings)
        if not outcome.waiting:
            return firings
        assert time.monotonic() < deadline, "timed out waiting on worker results"
        session.wait(1.0)


def effects_for(dsn: str, issue_id: str) -> int:
    with psycopg.connect(dsn, autocommit=True) as connection:
        return connection.execute(
            "SELECT count(*) FROM impetus_test.effects WHERE idempotency = %s", (f"effect-{issue_id}",)
        ).fetchone()[0]


def arm_kill_switch(dsn: str) -> None:
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute("UPDATE impetus_test.kill_switch SET armed = TRUE")


class TestEndToEnd:
    def test_the_activity_executes_on_the_worker_and_completes_through_server_side_projection(
        self, fixture_db, worker_factory
    ):
        worker = worker_factory()
        instance = f"topo-{uuid4().hex[:10]}"
        issue = f"goose-{uuid4().hex[:6]}"
        session = open_session(fixture_db, instance)

        session.deliver(INGRESS, Token(ISSUE, {"id": issue}))
        drive_until_rest(session)
        session.deliver(OPERATOR, Token(APPROVAL, {"id": issue}))
        drive_until_rest(session)

        # Done, with the worker's result projected server-side onto the token.
        (done_token,) = session.marking.place(DONE)
        assert done_token.data == {"id": issue, "spark": f"sparked {issue}"}
        assert session.status is Status.COMPLETED
        # The worker really did it, out of process.
        await_event(worker, lambda event: event.get("activity") == "spark_work" and event.get("outcome") == "completed")
        assert effects_for(fixture_db, issue) == 1

        # The history is authority-authored only: every durable row is a
        # record the authority's writer appended — a fresh load equals the
        # live writer's history value-for-value, the worker's answer present
        # exactly as the authority's acceptance stamp.
        with psycopg.connect(fixture_db, autocommit=True) as fresh:
            records = PostgresHistoryStore(fresh, instance).records
        assert records == session.records
        requested = [record for record in records if isinstance(record, ActivityRequested)]
        completed = [record for record in records if isinstance(record, ActivityCompleted)]
        assert [record.activity for record in requested] == ["spark_work"]
        assert [(record.occurrence, record.result) for record in completed] == [
            (requested[0].occurrence, f"sparked {issue}")
        ]


class TestLifecycleScopeCancellation:
    def test_engine_close_commits_history_then_absurd_tombstone_and_restart_repairs(self, fixture_db):
        instance = f"scope-{uuid4().hex[:10]}"
        issue = f"goose-{uuid4().hex[:6]}"
        session = open_session(fixture_db, instance)
        scope = session.open_scope("pr-lifecycle")
        session.deliver(INGRESS, Token(ISSUE, {"id": issue}), identity=f"issue-{issue}", scope=scope)
        assert advance_until_blocked(session).waiting
        request = next(record for record in session.records if isinstance(record, ActivityRequested))

        closure = session.close_scope(scope)

        assert closure.cancelled == (request.occurrence,)
        assert isinstance(session.records[-1], ScopeClosed)
        key = f"{instance}:occurrence-{request.occurrence}"
        with psycopg.connect(fixture_db, autocommit=True) as probe:
            assert probe.execute(
                f"SELECT state FROM absurd.t_{CAPABILITY} WHERE idempotency_key = %s", (key,)
            ).fetchone() == ("cancelled",)
        close_session(session)

        resumed = open_session(fixture_db, instance, load=True)
        assert resumed.advance().waiting is False
        with psycopg.connect(fixture_db, autocommit=True) as probe:
            assert probe.execute(
                f"SELECT count(*) FROM absurd.t_{CAPABILITY} WHERE idempotency_key = %s", (key,)
            ).fetchone() == (1,)


class TestWorkerKill:
    def test_two_workers_do_not_replace_a_long_activity_that_heartbeats(self, fixture_db, worker_factory):
        first = worker_factory(claim_timeout=1, worker_id="heartbeat-a")
        second = worker_factory(claim_timeout=1, worker_id="heartbeat-b")
        instance = f"topo-{uuid4().hex[:10]}"
        issue = f"goose-{uuid4().hex[:6]}"
        session = open_session(
            fixture_db,
            instance,
            attempts=2,
            activities=[ActivityDeclaration("spark_work", heartbeat_timeout=1)],
        )
        session.deliver(INGRESS, Token(ISSUE, {"id": issue, "mode": "heartbeat-long"}))
        drive_until_rest(session)

        completed = []
        for worker in (first, second):
            if worker.poll() is None:
                try:
                    completed.append(
                        await_event(worker, lambda event: event.get("activity") == "spark_work", timeout=1)
                    )
                except AssertionError:
                    pass
        assert sum(event.get("outcome") == "completed" for event in completed) == 1
        assert effects_for(fixture_db, issue) == 1
        requested = next(record for record in session.records if isinstance(record, ActivityRequested))
        with psycopg.connect(fixture_db, autocommit=True) as probe:
            assert (
                probe.execute(
                    f"SELECT count(*) FROM absurd.r_{CAPABILITY} WHERE task_id = "
                    f"(SELECT task_id FROM absurd.t_{CAPABILITY} WHERE idempotency_key = %s)",
                    (f"{instance}:occurrence-{requested.occurrence}",),
                ).fetchone()[0]
                == 1
            )

        encoded = [encode_record(record) for record in session.records]
        assert [payload["record"] for payload in encoded] == [
            "InstanceCreated",
            "DeliveryRegistrationOpened",
            "DeliveryRegistrationOpened",
            "ExternalEventDelivered",
            "FiringBegun",
            "TokensProduced",
            "FiringCompleted",
            "CandidateSelected",
            "FiringBegun",
            "TokensConsumed",
            "ActivityRequested",
            "ActivityCompleted",
            "TokensProduced",
            "FiringCompleted",
        ]
        forbidden = {"attempt_id", "epoch", "claimant", "checkpoint", "heartbeat", "details"}
        assert all(not (forbidden & payload.keys()) for payload in encoded)
        [request_payload] = [payload for payload in encoded if payload["record"] == "ActivityRequested"]
        assert request_payload["policy"] == {
            "attempts": 2,
            "heartbeat_timeout": 1,
            "initial_interval": 0,
            "coefficient": 2,
            "max_interval": 60,
            "jitter": 0,
            "start_to_close": None,
            "schedule_to_close": None,
        }

    def test_replacement_process_receives_durable_details_and_resumes(self, fixture_db, worker_factory, tmp_path):
        barrier = tmp_path / "checkpoint.json"
        first = worker_factory(claim_timeout=1, worker_id="checkpoint-a")
        instance = f"topo-{uuid4().hex[:10]}"
        issue = f"goose-{uuid4().hex[:6]}"
        session = open_session(
            fixture_db,
            instance,
            attempts=2,
            activities=[ActivityDeclaration("spark_work", heartbeat_timeout=1)],
        )
        session.deliver(INGRESS, Token(ISSUE, {"id": issue, "mode": "checkpoint-crash", "barrier": str(barrier)}))
        assert advance_until_blocked(session).waiting
        deadline = time.monotonic() + 15
        while not barrier.exists():
            assert time.monotonic() < deadline, "first worker never persisted its checkpoint barrier"
            time.sleep(0.05)
        first_details = json.loads(barrier.read_text(encoding="utf-8"))
        first.kill()
        first.wait()

        worker_factory(claim_timeout=1, worker_id="checkpoint-b")
        drive_until_rest(session, deadline_seconds=30)
        resumed = json.loads(barrier.with_suffix(".resumed").read_text(encoding="utf-8"))
        assert resumed["details"] == {"cursor": 7, "first_claimant": first_details["claimant"]}
        assert resumed["claimant"] != first_details["claimant"]
        assert session.marking.place(WORKED)[0].data["spark"] == "resumed 7"

    def test_sigkill_mid_activity_redispatches_on_lease_expiry_with_exactly_one_effect(
        self, fixture_db, worker_factory
    ):
        # DEC-013's bounded release probe over K3: worker A commits the
        # concrete PostgreSQL-backed effect, takes the arm, and blocks before
        # reporting terminal. SIGKILL leaves a live lease on a dead process.
        # Worker B sweeps the expired lease and executes the redelivery; the
        # idempotent external target holds one row while the second run alone
        # supplies the one canonical terminal result.
        arm_kill_switch(fixture_db)
        worker_a = worker_factory(claim_timeout=1, worker_id="doomed")
        instance = f"topo-{uuid4().hex[:10]}"
        issue = f"goose-{uuid4().hex[:6]}"
        session = open_session(fixture_db, instance, attempts=2, default_heartbeat_timeout=1)

        session.deliver(INGRESS, Token(ISSUE, {"id": issue}))
        outcome = advance_until_blocked(session)
        assert outcome.waiting  # dispatched, out with the worker

        deadline = time.monotonic() + 15
        while effects_for(fixture_db, issue) == 0:  # the effect commit IS the in-the-window barrier
            assert time.monotonic() < deadline, "worker never reached the effect"
            time.sleep(0.05)
        (requested,) = [record for record in session.records if isinstance(record, ActivityRequested)]
        assert not any(isinstance(record, ActivityCompleted) for record in session.records)
        key = f"{instance}:occurrence-{requested.occurrence}"
        with psycopg.connect(fixture_db, autocommit=True) as probe:
            (task_id, task_state, attempts) = probe.execute(
                f"SELECT task_id, state, attempts FROM absurd.t_{CAPABILITY} WHERE idempotency_key = %s", (key,)
            ).fetchone()
            first_runs = probe.execute(
                f"SELECT attempt, state FROM absurd.r_{CAPABILITY} WHERE task_id = %s ORDER BY attempt", (task_id,)
            ).fetchall()
        assert (task_state, attempts) == ("running", 1)
        assert first_runs == [(1, "running")]
        worker_a.kill()
        worker_a.wait()

        worker_factory(claim_timeout=1, worker_id="successor")
        drive_until_rest(session, deadline_seconds=30)
        session.deliver(OPERATOR, Token(APPROVAL, {"id": issue}))
        drive_until_rest(session)

        assert session.status is Status.COMPLETED
        assert effects_for(fixture_db, issue) == 1  # redelivered, never doubled
        completed = [record for record in session.records if isinstance(record, ActivityCompleted)]
        assert [(record.occurrence, record.result) for record in completed] == [
            (requested.occurrence, f"sparked {issue}")
        ]
        with psycopg.connect(fixture_db, autocommit=True) as probe:
            (same_task_id, task_state, attempts) = probe.execute(
                f"SELECT task_id, state, attempts FROM absurd.t_{CAPABILITY} WHERE idempotency_key = %s", (key,)
            ).fetchone()
            final_runs = probe.execute(
                f"SELECT attempt, state FROM absurd.r_{CAPABILITY} WHERE task_id = %s ORDER BY attempt", (task_id,)
            ).fetchall()
        assert same_task_id == task_id  # one recovery identity and one task across redelivery
        assert (task_state, attempts) == ("completed", 2)
        assert final_runs == [(1, "failed"), (2, "completed")]
        (done_token,) = session.marking.place(DONE)
        assert done_token.data["spark"] == f"sparked {issue}"

    def test_sigterm_drains_gracefully_the_in_flight_activity_completes(self, fixture_db, worker_factory):
        worker = worker_factory(worker_id="drainer")
        instance = f"topo-{uuid4().hex[:10]}"
        issue = f"goose-{uuid4().hex[:6]}"
        session = open_session(fixture_db, instance)

        session.deliver(INGRESS, Token(ISSUE, {"id": issue, "nap": 1.0}))
        outcome = advance_until_blocked(session)
        assert outcome.waiting
        with psycopg.connect(fixture_db, autocommit=True) as probe:
            deadline = time.monotonic() + 15
            while not probe.execute(f"SELECT 1 FROM absurd.r_{CAPABILITY} WHERE state = 'running'").fetchone():
                assert time.monotonic() < deadline, "worker never claimed"
                time.sleep(0.05)

        worker.send_signal(signal.SIGTERM)  # mid-nap: drain, don't drop
        await_event(worker, lambda event: event.get("outcome") == "completed")
        assert worker.wait(timeout=10) == 0

        drive_until_rest(session)
        session.deliver(OPERATOR, Token(APPROVAL, {"id": issue}))
        drive_until_rest(session)
        assert session.status is Status.COMPLETED


class TestAuthorityKill:
    def test_killed_after_the_dispatch_commit_resumes_without_a_double_spawn(self, fixture_db, worker_factory):
        instance = f"topo-{uuid4().hex[:10]}"
        issue = f"goose-{uuid4().hex[:6]}"
        first = open_session(fixture_db, instance)
        first.deliver(INGRESS, Token(ISSUE, {"id": issue}))
        outcome = advance_until_blocked(first)
        assert outcome.waiting  # begin batch + spawn + doorbell committed as one
        close_session(first)  # the authority dies here; nothing uncommitted existed

        # The resumed authority reconciles from canonical facts: the recorded
        # outbox redispatches idempotently — the live task is left alone.
        second = open_session(fixture_db, instance, load=True)
        (outstanding,) = second.in_flight  # rebuilt from ActivityRequested
        advance_until_blocked(second)
        with psycopg.connect(fixture_db, autocommit=True) as probe:
            count = probe.execute(
                f"SELECT count(*) FROM absurd.t_{CAPABILITY} WHERE idempotency_key = %s",
                (f"{instance}:occurrence-{outstanding.id}",),
            ).fetchone()[0]
        assert count == 1  # one spawn across both authority lives

        worker_factory()
        drive_until_rest(second)
        second.deliver(OPERATOR, Token(APPROVAL, {"id": issue}))
        drive_until_rest(second)

        assert second.status is Status.COMPLETED
        completed = [record for record in second.records if isinstance(record, ActivityCompleted)]
        assert len(completed) == 1  # the result was accepted exactly once
        assert effects_for(fixture_db, issue) == 1

    def test_a_crash_before_the_begin_transaction_commits_leaves_nothing_anywhere(self, fixture_db, worker_factory):
        # The commit-or-vanish pin, at the seam the D11 shape closes: begin
        # batch + spawn + doorbell staged in ONE open transaction, then the
        # authority dies (the connection drops; the server aborts the
        # transaction — the matrix's s02/s04 shape). NOTHING lands: no begin
        # records, no task, no bell.
        instance = f"topo-{uuid4().hex[:10]}"
        issue = f"goose-{uuid4().hex[:6]}"
        bootstrap = open_session(fixture_db, instance)
        bootstrap.deliver(INGRESS, Token(ISSUE, {"id": issue}))  # a committed prior fact
        close_session(bootstrap)
        with psycopg.connect(fixture_db, autocommit=True) as provision:
            provision.execute("SELECT absurd.create_queue(%s)", (CAPABILITY,))

        crashing = psycopg.connect(fixture_db, autocommit=False)
        history = PostgresHistoryStore(crashing, instance)
        recorded_before = len(history)
        live = Instance.resume(topology_net(), history, handlers=topology_handlers())
        adapter = AbsurdDispatch(crashing, instance=instance, default_queue=CAPABILITY)
        occurrence = live.begin(live.candidates()[0])
        adapter.dispatch(occurrence.id, occurrence.invocation)
        crashing.close()  # died before commit: the server aborts the whole staging

        with psycopg.connect(fixture_db, autocommit=True) as probe:
            rows = probe.execute(
                "SELECT count(*) FROM impetus.semantic_events WHERE net_instance_id = %s", (instance,)
            ).fetchone()[0]
            tasks = probe.execute(
                f"SELECT count(*) FROM absurd.t_{CAPABILITY} WHERE idempotency_key = %s",
                (f"{instance}:occurrence-{occurrence.id}",),
            ).fetchone()[0]
        assert rows == recorded_before  # the begin batch vanished whole
        assert tasks == 0  # and the spawn with it

        # The same identities re-dispatch cleanly afterwards: a fresh
        # authority resumes, begins the SAME work, and the flow completes.
        worker_factory()
        session = open_session(fixture_db, instance, load=True)
        drive_until_rest(session)
        session.deliver(OPERATOR, Token(APPROVAL, {"id": issue}))
        drive_until_rest(session)
        assert session.status is Status.COMPLETED
        assert effects_for(fixture_db, issue) == 1


class TestAbsurdProviderEngineConstruction:
    def test_resolves_default_and_declared_timeout_into_history_and_dispatch_and_snapshots_inputs(self, fixture_db):
        declarations = [ActivityDeclaration("other", heartbeat_timeout=9)]
        instance = f"topo-{uuid4().hex[:10]}"
        session = open_session(fixture_db, instance, activities=declarations, default_heartbeat_timeout=4)
        declarations[:] = [ActivityDeclaration("spark_work", heartbeat_timeout=99)]
        session.deliver(INGRESS, Token(ISSUE, {"id": "default"}))
        assert advance_until_blocked(session).waiting
        requested = next(record for record in session.records if isinstance(record, ActivityRequested))
        assert requested.policy.heartbeat_timeout == 4
        with psycopg.connect(fixture_db, autocommit=True) as probe:
            params = probe.execute(
                f"SELECT params FROM absurd.t_{CAPABILITY} WHERE idempotency_key = %s",
                (f"{instance}:occurrence-{requested.occurrence}",),
            ).fetchone()[0]
        assert params["policy"]["heartbeat_timeout"] == 4
        close_session(session)

        declared = [ActivityDeclaration("spark_work", heartbeat_timeout=7)]
        override_instance = f"topo-{uuid4().hex[:10]}"
        overridden = open_session(fixture_db, override_instance, activities=declared, default_heartbeat_timeout=4)
        declared.clear()
        overridden.deliver(INGRESS, Token(ISSUE, {"id": "override"}))
        assert advance_until_blocked(overridden).waiting
        assert (
            next(
                record for record in overridden.records if isinstance(record, ActivityRequested)
            ).policy.heartbeat_timeout
            == 7
        )
        close_session(overridden)

    def test_load_under_changed_timeout_keeps_recorded_in_flight_invocation_without_reprepare(self, fixture_db):
        instance = f"topo-{uuid4().hex[:10]}"
        first = open_session(
            fixture_db,
            instance,
            activities=[ActivityDeclaration("spark_work", heartbeat_timeout=6)],
            default_heartbeat_timeout=3,
        )
        first.deliver(INGRESS, Token(ISSUE, {"id": "frozen"}))
        assert advance_until_blocked(first).waiting
        original = first.in_flight[0].invocation
        assert original.policy.heartbeat_timeout == 6
        close_session(first)

        loaded = open_session(
            fixture_db,
            instance,
            load=True,
            activities=[ActivityDeclaration("spark_work", heartbeat_timeout=60)],
            default_heartbeat_timeout=30,
        )
        assert loaded.in_flight[0].invocation == original
        assert loaded.in_flight[0].invocation.policy.heartbeat_timeout == 6
        close_session(loaded)

    def test_provider_returns_the_concrete_engine_with_only_universal_doors(self, fixture_db):
        assert {name for name in Engine.__dict__ if not name.startswith("_")} == {
            "active_scopes",
            "advance",
            "close",
            "close_scope",
            "create",
            "deliver",
            "history_page",
            "in_flight",
            "load",
            "marking",
            "net_document",
            "open_scope",
            "records",
            "reset_scope",
            "seal",
            "snapshot",
            "status",
            "wait",
        }
        assert not hasattr(Engine, "queue_for")
        engine = open_session(fixture_db, f"topo-{uuid4().hex[:10]}")
        assert type(engine) is Engine
        close_session(engine)

    def test_create_and_load_are_explicit_and_close_appends_no_semantic_fact(self, fixture_db):
        instance = f"topo-{uuid4().hex[:10]}"
        with pytest.raises(ValueError, match="does not exist"):
            open_session(fixture_db, instance, load=True)

        created = open_session(fixture_db, instance)
        records = created.records
        close_session(created)
        loaded = open_session(fixture_db, instance, load=True)
        assert loaded.records == records
        close_session(loaded)

        with pytest.raises(ValueError, match="already exists"):
            open_session(fixture_db, instance)

        joined = psycopg.connect(fixture_db, autocommit=False)
        listener = psycopg.connect(fixture_db, autocommit=True)
        with pytest.raises(ValueError, match="already exists"):
            create_engine(joined, topology_net(), instance, listen=listener, handlers=topology_handlers())
        assert joined.closed
        assert listener.closed

        retried = open_session(fixture_db, instance, load=True)
        assert retried.records == records
        close_session(retried)

    def test_invalid_provider_option_closes_both_connections(self, fixture_db):
        joined = psycopg.connect(fixture_db, autocommit=False)
        listener = psycopg.connect(fixture_db, autocommit=True)

        with pytest.raises(TypeError, match="unexpected keyword argument 'unknown_option'"):
            create_engine(
                joined,
                topology_net(),
                f"topo-{uuid4().hex[:10]}",
                listen=listener,
                handlers=topology_handlers(),
                unknown_option=True,
            )

        assert joined.closed
        assert listener.closed

    def test_wrong_autocommit_listener_leaves_create_empty_and_retriable(self, fixture_db):
        instance = f"topo-{uuid4().hex[:10]}"
        with (
            psycopg.connect(fixture_db, autocommit=False) as joined,
            psycopg.connect(fixture_db, autocommit=False) as wrong_listener,
        ):
            with pytest.raises(ValueError, match="autocommit=True"):
                create_engine(joined, topology_net(), instance, listen=wrong_listener)
        with psycopg.connect(fixture_db, autocommit=True) as probe:
            assert len(PostgresHistoryStore(probe, instance)) == 0
        retry = open_session(fixture_db, instance)
        assert retry.records[0] == InstanceCreated(instance)
        close_session(retry)

    def test_load_refuses_recorded_identity_that_differs_from_storage_key(self, fixture_db):
        instance = f"topo-{uuid4().hex[:10]}"
        encoded = encode_record(InstanceCreated("different-instance"))
        with psycopg.connect(fixture_db, autocommit=True) as connection:
            connection.execute(
                "INSERT INTO impetus.semantic_events "
                "(event_id, net_instance_id, record_type, payload) VALUES (%s, %s, %s, %s)",
                (f"{instance}:0", instance, "InstanceCreated", Jsonb(encoded)),
            )
        with pytest.raises(ValueError, match="storage key and recorded identity must match exactly"):
            open_session(fixture_db, instance, load=True)

    def test_two_engines_keep_independent_instance_views(self, fixture_db):
        left = open_session(fixture_db, f"left-{uuid4().hex[:10]}")
        right = open_session(fixture_db, f"right-{uuid4().hex[:10]}")
        left.deliver(INGRESS, Token(ISSUE, {"id": "left"}))
        assert left.marking != right.marking
        assert left.records != right.records
        close_session(left)
        close_session(right)

    def test_load_refuses_incompatible_canonical_data(self, fixture_db):
        instance = f"bad-{uuid4().hex[:10]}"
        with psycopg.connect(fixture_db, autocommit=True) as connection:
            connection.execute(
                "INSERT INTO impetus.semantic_events "
                "(event_id, net_instance_id, record_type, payload) VALUES (%s, %s, %s, %s)",
                (f"{instance}:0", instance, "FutureRecord", Jsonb({"schema": 999, "type": "FutureRecord"})),
            )
        with pytest.raises(ValueError, match="decode|schema|record"):
            open_session(fixture_db, instance, load=True)

    def test_the_session_requires_a_join_mode_connection(self, fixture_db):
        with psycopg.connect(fixture_db, autocommit=True) as autocommit:
            with pytest.raises(ValueError, match="autocommit=False"):
                create_engine(autocommit, topology_net(), f"topo-{uuid4().hex[:10]}", listen=autocommit)

    def test_the_session_requires_a_dedicated_listen_connection(self, fixture_db):
        with psycopg.connect(fixture_db, autocommit=False) as joined:
            with pytest.raises(ValueError, match="dedicated autocommit listen connection"):
                create_engine(joined, topology_net(), f"topo-{uuid4().hex[:10]}", listen=None)

    def test_close_is_idempotent_and_every_door_and_observation_refuses_after_close(self, fixture_db):
        session = open_session(fixture_db, f"topo-{uuid4().hex[:10]}")
        close_session(session)
        session.close()
        for door in (
            lambda: session.advance(),
            lambda: session.deliver(INGRESS, Token(ISSUE, {"id": "late"})),
            lambda: session.seal(INGRESS),
            lambda: session.wait(0),
            lambda: session.marking,
            lambda: session.status,
            lambda: session.in_flight,
            lambda: session.records,
        ):
            with pytest.raises(RuntimeError, match="Engine is closed"):
                door()

    def test_a_second_live_authority_for_one_instance_is_fenced_out(self, fixture_db):
        instance = f"topo-{uuid4().hex[:10]}"
        first = open_session(fixture_db, instance)
        second_connection = psycopg.connect(fixture_db, autocommit=False)
        second_listener = psycopg.connect(fixture_db, autocommit=True)
        try:
            with pytest.raises(RuntimeError, match="already held.*second canonical writer"):
                load_engine(
                    second_connection,
                    topology_net(),
                    instance,
                    listen=second_listener,
                    handlers=topology_handlers(),
                )
            assert second_connection.closed
            assert second_listener.closed
            close_session(first)
            resumed = open_session(fixture_db, instance, load=True)
            close_session(resumed)
        finally:
            if not second_connection.closed:
                second_connection.close()
            if not second_listener.closed:
                second_listener.close()

    def test_the_session_hands_out_no_writer_and_its_accessors_are_read_only(self, fixture_db):
        # The purity lens's empirical bypass, made impossible: nothing on the
        # session reaches the coordinator, adapter, or instance — the fate
        # rule cannot be walked around — and observation is read-only.
        session = open_session(fixture_db, f"topo-{uuid4().hex[:10]}")
        for handle in ("coordinator", "adapter", "instance"):
            assert not hasattr(session, handle)
        for accessor in ("marking", "status", "in_flight", "records"):
            with pytest.raises(AttributeError):
                setattr(session, accessor, None)

    def test_joined_dispatch_failure_rolls_back_selection_before_fresh_load(self, fixture_db, monkeypatch):
        instance = f"topo-{uuid4().hex[:10]}"
        issue = f"goose-{uuid4().hex[:6]}"
        joined = psycopg.connect(fixture_db, autocommit=False)
        listener = psycopg.connect(fixture_db, autocommit=True)
        session = create_engine(
            joined,
            topology_net(),
            instance,
            listen=listener,
            handlers=topology_handlers(),
            poll_interval=0.1,
            default_queue=CAPABILITY,
        )
        session.deliver(INGRESS, Token(ISSUE, {"id": issue}))

        def fail_dispatch(self, occurrence, invocation):
            raise RuntimeError("dispatch failed after joined begin")

        monkeypatch.setattr(AbsurdDispatch, "dispatch", fail_dispatch)
        with pytest.raises(RuntimeError, match="dispatch failed after joined begin"):
            advance_until_blocked(session)

        # Poison releases authority immediately, before the old host closes,
        # so a fresh load is the available coherent continuation.
        resumed = open_session(fixture_db, instance, load=True)
        assert not any(isinstance(record, CandidateSelected) for record in resumed.records)
        assert resumed.marking.place(INGRESS) == ()
        assert len(resumed.in_flight) == 0
        session.close()
        assert joined.closed
        assert listener.closed
        close_session(resumed)

    def test_real_recovery_lock_contention_poisons_preserves_old_creates_no_target_and_releases_fence(self, fixture_db):
        old, target = f"old_{uuid4().hex[:8]}", f"target_{uuid4().hex[:8]}"
        instance = f"contention-{uuid4().hex[:8]}"
        first = open_session(fixture_db, instance, default_queue=old)
        first.deliver(INGRESS, Token(ISSUE, {"id": f"goose-{uuid4().hex[:6]}"}))
        assert advance_until_blocked(first).waiting
        (outstanding,) = first.in_flight
        close_session(first)
        key = f"{instance}:occurrence-{outstanding.id}"

        with psycopg.connect(fixture_db, autocommit=False) as locker:
            locker.execute(f"SELECT 1 FROM absurd.r_{old} FOR UPDATE")
            recovering = open_session(fixture_db, instance, load=True, default_queue=target)
            with pytest.raises(RuntimeError, match="currently locked"):
                recovering.advance()
            with pytest.raises(RuntimeError, match=r"fresh Engine\.load"):
                recovering.advance()
            close_session(recovering)

        with psycopg.connect(fixture_db, autocommit=True) as probe:
            assert probe.execute(f"SELECT state FROM absurd.t_{old} WHERE idempotency_key = %s", (key,)).fetchone() == (
                "pending",
            )
            if probe.execute("SELECT 1 FROM absurd.list_queues() WHERE queue_name = %s", (target,)).fetchone():
                assert probe.execute(
                    f"SELECT count(*) FROM absurd.t_{target} WHERE idempotency_key = %s", (key,)
                ).fetchone() == (0,)

        fresh = open_session(fixture_db, instance, load=True, default_queue=target)
        assert advance_until_blocked(fresh).waiting
        assert fresh.in_flight == (outstanding,)
        with psycopg.connect(fixture_db, autocommit=True) as probe:
            assert probe.execute(f"SELECT state FROM absurd.t_{old} WHERE idempotency_key = %s", (key,)).fetchone() == (
                "cancelled",
            )
            assert probe.execute(
                f"SELECT state FROM absurd.t_{target} WHERE idempotency_key = %s", (key,)
            ).fetchone() == ("pending",)
        close_session(fresh)

    def test_a_projection_crash_never_rolls_back_the_frozen_result(self, fixture_db, worker_factory):
        # The ratified two-boundary completion [DR 2026-07-14: ActivityCompleted
        # commits BEFORE deterministic projection], on the joined backend: the
        # freeze is its own commit, so a projection crash leaves the frozen
        # result durable, the occurrence projection-pending, and the FIXED
        # code retries projection alone — the activity is never re-invoked.
        worker_factory()
        instance = f"topo-{uuid4().hex[:10]}"
        issue = f"goose-{uuid4().hex[:6]}"
        session = open_session(fixture_db, instance, project_poisoned=True)
        session.deliver(INGRESS, Token(ISSUE, {"id": issue}))

        with pytest.raises(ValueError, match="projection poisoned"):
            drive_until_rest(session)

        with psycopg.connect(fixture_db, autocommit=True) as fresh:
            records = PostgresHistoryStore(fresh, instance).records
        completed = [record for record in records if isinstance(record, ActivityCompleted)]
        assert len(completed) == 1  # the freeze survived the projection crash
        work = completed[0].occurrence
        ended = {
            type(record).__name__
            for record in records
            if type(record).__name__ in ("FiringCompleted", "FiringFailed", "ActivityFailed")
            and record.occurrence == work
        }
        assert ended == set()  # nothing projected, nothing converted into a failed firing

        # Fix the code, resume fresh: reconcile's projection-pending leg
        # completes by projection alone.
        second = open_session(fixture_db, instance, load=True)  # the fixed deployment
        (pending,) = second.in_flight
        drive_until_rest(second)
        second.deliver(OPERATOR, Token(APPROVAL, {"id": issue}))
        drive_until_rest(second)
        assert second.status is Status.COMPLETED
        assert effects_for(fixture_db, issue) == 1  # the activity ran exactly once
        with psycopg.connect(fixture_db, autocommit=True) as probe:
            (attempts,) = probe.execute(
                f"SELECT attempts FROM absurd.t_{CAPABILITY} WHERE idempotency_key = %s",
                (f"{instance}:occurrence-{pending.id}",),
            ).fetchone()
        assert attempts == 1  # never re-invoked at the substrate either

    def test_a_terminal_activity_failure_halts_loud_with_its_facts_durable(self, fixture_db, worker_factory):
        # Stop-on-terminal-failure through the joined transaction: the
        # ActivityFailed + FiringFailed batch COMMITS before the halt
        # propagates — the raise is driver policy, never a rollback.
        worker_factory()
        instance = f"topo-{uuid4().hex[:10]}"
        issue = f"goose-{uuid4().hex[:6]}"
        session = open_session(fixture_db, instance)
        session.deliver(INGRESS, Token(ISSUE, {"id": issue, "boom": True}))

        with pytest.raises(RuntimeError, match="failed terminally.*boom requested"):
            drive_until_rest(session)

        with psycopg.connect(fixture_db, autocommit=True) as fresh:
            types = [type(record).__name__ for record in PostgresHistoryStore(fresh, instance).records]
        assert types.count("ActivityFailed") == 1
        assert types.count("FiringFailed") == 1
        assert effects_for(fixture_db, issue) == 0  # the failure preceded the effect

    def test_a_failed_door_poisons_the_session_whole(self, fixture_db, worker_factory):
        # The enforcing wrapper: after ANY door exception the session's
        # connection rolled back, so history, instance, adapter, and
        # coordinator all spoke retracted (or halted) state — every later
        # door refuses, naming the fresh-session continuation [convention 71].
        worker_factory()
        instance = f"topo-{uuid4().hex[:10]}"
        session = open_session(fixture_db, instance)
        session.deliver(INGRESS, Token(ISSUE, {"id": f"goose-{uuid4().hex[:6]}", "boom": True}))
        with pytest.raises(RuntimeError, match="failed terminally"):
            drive_until_rest(session)

        for door in (
            lambda: session.advance(),
            lambda: session.deliver(INGRESS, Token(ISSUE, {"id": "late"})),
            lambda: session.seal(INGRESS),
            lambda: session.wait(0.1),
            lambda: session.marking,
            lambda: session.status,
            lambda: session.in_flight,
            lambda: session.records,
        ):
            with pytest.raises(RuntimeError, match=r"fresh Engine\.load"):
                door()


class TestActivityRegistry:
    def test_claimant_is_reused_by_one_process_definition_and_new_for_a_new_one(self, fixture_db):
        def activity(invocation, *, context):
            return invocation.input

        process_provider = AbsurdWorkerDispatch(fixture_db, queues=(CAPABILITY,))
        Worker(process_provider, {"spark_work": activity})
        same_process_reconnect_claimant = process_provider.claimant
        restarted_provider = AbsurdWorkerDispatch(fixture_db, queues=(CAPABILITY,))
        Worker(restarted_provider, {"spark_work": activity})

        assert process_provider.claimant == same_process_reconnect_claimant
        assert restarted_provider.claimant != process_provider.claimant
        process_provider.close()
        restarted_provider.close()

    def test_worker_and_loader_snapshot_mutable_registries(self, fixture_db, monkeypatch):
        registry = {"spark_work": lambda invocation, *, context: invocation.input}
        import tests.absurd_support as support

        monkeypatch.setattr(support, "mutable_registry", registry, raising=False)
        loaded = _load_registry("tests.absurd_support:mutable_registry")
        provider = AbsurdWorkerDispatch(fixture_db, queues=(CAPABILITY,))
        worker = Worker(provider, registry)
        registry.clear()

        assert "spark_work" in worker._activities
        assert "spark_work" in loaded
        provider.close()

    def test_worker_snapshots_mutable_queue_sequence(self, fixture_db):
        queues = [CAPABILITY]
        provider = AbsurdWorkerDispatch(fixture_db, queues=queues)
        Worker(provider, {"spark_work": lambda invocation, *, context: invocation.input})
        queues[:] = ["changed"]
        assert provider.queues == (CAPABILITY,)
        provider.close()

    @pytest.mark.parametrize(
        "registry",
        [{}, {"": lambda invocation, *, context: None}, {7: lambda invocation, *, context: None}, {"work": object()}],
    )
    def test_worker_refuses_invalid_activity_registries(self, fixture_db, registry):
        message = (
            "default Activities or a scoped resolver" if not registry else "map non-empty string names to callables"
        )
        with pytest.raises(ValueError, match=message):
            Worker(AbsurdWorkerDispatch(fixture_db, queues=(CAPABILITY,)), registry)

    def test_worker_refuses_an_empty_queue_subscription(self, fixture_db):
        with pytest.raises(ValueError, match="at least one queue"):
            AbsurdWorkerDispatch(fixture_db, queues=())

    @pytest.mark.parametrize(
        ("flags", "expected"),
        [([], ("default",)), (["--queue", "one", "--queue", "two", "--queue", "one"], ("one", "two"))],
    )
    def test_main_defaults_queue_and_preserves_deduplicated_flag_order(self, monkeypatch, flags, expected):
        observed = {}

        class FakeProvider:
            def __init__(self, dsn, **options):
                observed["queues"] = options["queues"]

        class FakeWorker:
            def __init__(self, provider, activities, **options):
                pass

            def stop(self):
                pass

            def run(self, **options):
                pass

        monkeypatch.setattr(worker_cli, "Worker", FakeWorker)
        monkeypatch.setattr("petrus.motus.dispatch.absurd.AbsurdWorkerDispatch", FakeProvider)
        monkeypatch.setattr(worker_cli, "_load_registry", lambda spec: {"work": lambda invocation, *, context: None})
        monkeypatch.setattr(worker_cli.signal, "signal", lambda *args: None)
        worker_cli.main(
            ["--provider", "absurd", "--dsn", "postgresql:///unused", "--registry", "fake:registry", *flags]
        )
        assert observed["queues"] == expected

    def test_the_worker_refuses_an_unregistered_activity(self, fixture_db, worker_factory):
        queue = f"capmix_{uuid4().hex[:8]}"
        worker = worker_factory(queues=(queue,), poll_interval=0.1)
        misrouted = ActivityInvocation(
            "not_registered",
            input={"id": f"mix-{uuid4().hex[:6]}"},
            policy=ExecutionPolicy(),
            idempotency=f"effect-mix-{uuid4().hex[:6]}",
        )
        with psycopg.connect(fixture_db, autocommit=True) as spawner:
            spawner.execute(
                "SELECT absurd.spawn_task(%s, %s, %s, %s)",
                (queue, "not_registered", Jsonb(encode_invocation(misrouted)), Jsonb({"max_attempts": 1})),
            )

        await_event(worker, lambda event: event.get("outcome") == "failed", timeout=10.0)
        with psycopg.connect(fixture_db, autocommit=True) as probe:
            state, reason = probe.execute(
                f"SELECT t.state, r.failure_reason FROM absurd.t_{queue} t"
                f" JOIN absurd.r_{queue} r ON r.run_id = t.last_attempt_run"
            ).fetchone()
        assert state == "failed"
        assert "no activity implementation" in reason["message"]


class TestDispatchDoorbell:
    def test_the_doorbell_wakes_a_worker_whose_poll_could_not_have(self, fixture_db, worker_factory):
        # The worker's poll floor is 30s; a task processed within seconds is
        # explicable ONLY by the dispatch doorbell — the latency claim as a
        # structural fact.
        bell_queue = f"bell_{uuid4().hex[:8]}"
        worker = worker_factory(queues=(bell_queue,), poll_interval=30.0)
        time.sleep(0.5)  # let the empty first drain settle onto the LISTEN wait
        instance = f"topo-{uuid4().hex[:10]}"
        with psycopg.connect(fixture_db, autocommit=False) as authority:
            adapter = AbsurdDispatch(authority, instance=instance, default_queue=bell_queue)
            adapter.dispatch(
                1,
                ActivityInvocation(
                    "spark_work",
                    input={"id": f"bell-{uuid4().hex[:6]}"},
                    policy=ExecutionPolicy(),
                    idempotency=f"effect-bell-{uuid4().hex[:6]}",
                ),
            )
            started = time.monotonic()
            authority.commit()  # the bell rings here
            await_event(worker, lambda event: event.get("outcome") == "completed", timeout=10.0)
            assert time.monotonic() - started < 8.0  # well under the 30s poll floor

    def test_with_the_doorbell_suppressed_the_poll_safety_net_still_dispatches(self, fixture_db, worker_factory):
        # No NOTIFY is ever sent (raw spawn_task, no adapter): the worker's
        # poll interval alone finds the work — measurably later than a bell
        # wake, bounded by the poll floor.
        poll_queue = f"poll_{uuid4().hex[:8]}"
        worker = worker_factory(queues=(poll_queue,), poll_interval=0.5)
        time.sleep(0.3)
        silent = ActivityInvocation(
            "spark_work",
            input={"id": f"poll-{uuid4().hex[:6]}"},
            policy=ExecutionPolicy(),
            idempotency=f"effect-poll-{uuid4().hex[:6]}",
        )
        with psycopg.connect(fixture_db, autocommit=True) as quiet:
            quiet.execute(
                "SELECT absurd.spawn_task(%s, %s, %s, %s)",
                (poll_queue, "spark_work", Jsonb(encode_invocation(silent)), Jsonb({})),
            )
        await_event(worker, lambda event: event.get("outcome") == "completed", timeout=10.0)
