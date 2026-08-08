"""
Behavioral tests for the Absurd execution adapter — the D11 obligations at
unit grain, against the real pinned engine in the session container:

- **Schema pinning, never forked:** the vendored release script matches the
  ES-009 triple pin; ``ensure_absurd_schema`` verifies the hash before any
  apply, is idempotent by version, and refuses a tampered copy, a foreign
  ``absurd`` schema, and a drifted version — a re-pin is a deliberate act.
- **Idempotent dispatch on the recovery identity:** a second dispatch of one
  occurrence never double-enqueues (``spawn_task``'s idempotency key IS the
  occurrence key).
- **The doorbell rides the spawning transaction:** in join mode nothing —
  task or NOTIFY — is observable until the caller commits, and a rollback
  vanishes both (the K1/K2 dissolve at this seam).
- **Collect speaks completion order** and maps a policy-exhausted task to an
  ``ActivityFailure`` (Absurd's ``max_attempts``/``retry_strategy`` mapped
  honestly from ``invocation.policy.attempts``).
- **K4 lookup-first reconcile:** live -> left alone, completed -> collected,
  absent -> respawned under the same identity (operational state is
  reconstructible machinery).
"""

from __future__ import annotations

# Python imports
import asyncio
import hashlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

# Pip imports
import psycopg
import pytest
from psycopg import sql
from psycopg.types.json import Jsonb

# Internal imports
import petrus.motus.dispatch.absurd
from petrus.motus.dispatch import Dispatch
from petrus.motus.dispatch.absurd import (
    ABSURD_SQL_SHA256,
    ABSURD_VERSION,
    DISPATCH_CHANNEL,
    RESULTS_CHANNEL,
    AbsurdDispatch,
    AbsurdWorkerDispatch,
    GuardedDispatch,
    decode_invocation,
    encode_invocation,
    ensure_absurd_schema,
    validate_queue,
)
from petrus.motus.activity import ActivityFailure, ActivityInvocation, ExecutionPolicy
from petrus.motus.dispatch.absurd import _ReconnectableGuardedDispatch
from petrus.motus.worker import AsyncWorker
from tests import REPO_ROOT


@pytest.fixture
def observer(absurd_dsn):
    """An autocommit connection — each engine call is its own committed transaction (the owned posture the unit tests drive the adapter in unless join mode is the subject)."""
    with psycopg.connect(absurd_dsn, autocommit=True) as connection:
        yield connection


@pytest.fixture
def authority(absurd_dsn):
    """A join-mode connection: the adapter's statements ride the open transaction until the test commits or rolls back."""
    with psycopg.connect(absurd_dsn, autocommit=False) as connection:
        yield connection


@pytest.fixture
def listener(absurd_dsn):
    with psycopg.connect(absurd_dsn, autocommit=True) as connection:
        yield connection


@pytest.fixture
def queue():
    """A fresh capability (= queue) per test, so task tables never cross-talk."""
    return f"q_{uuid4().hex[:10]}"


def invocation_for(queue: str, *, attempts: int = 1, payload: object = None) -> ActivityInvocation:
    return ActivityInvocation(
        "probe_activity",
        input={"payload": payload},
        policy=ExecutionPolicy(attempts=attempts),
        idempotency=f"effect-{uuid4().hex[:8]}",
    )


def adapter_over(
    connection, *, listen=None, poll_interval: float = 0.25, default_queue: str = "default"
) -> AbsurdDispatch:
    return AbsurdDispatch(
        connection,
        instance=f"adapter-{uuid4().hex[:8]}",
        listen=listen,
        poll_interval=poll_interval,
        default_queue=default_queue,
    )


def claim_one(connection, queue: str, worker_id: str = "test-claimer", claim_timeout: int = 30):
    row = connection.execute(
        "SELECT run_id, task_id, attempt FROM absurd.claim_task(%s, %s, %s, 1)",
        (queue, worker_id, claim_timeout),
    ).fetchone()
    assert row is not None, f"nothing claimable on {queue}"
    return row


def complete(connection, queue: str, run_id, result: object) -> None:
    connection.execute("SELECT absurd.complete_run(%s, %s, %s)", (queue, run_id, Jsonb(result)))


def fail(connection, queue: str, run_id, name: str, message: str) -> None:
    connection.execute(
        "SELECT absurd.fail_run(%s, %s, %s, NULL)", (queue, run_id, Jsonb({"name": name, "message": message}))
    )


def task_rows(connection, queue: str, adapter: AbsurdDispatch, occurrence: int):
    key = f"{adapter._instance}:occurrence-{occurrence}"
    return connection.execute(
        f"SELECT task_id, state, attempts FROM absurd.t_{queue} WHERE idempotency_key = %s", (key,)
    ).fetchall()


def publish(adapter: AbsurdDispatch, connection, occurrence: int, invocation: ActivityInvocation) -> None:
    """Publish through the required joined transaction and make it visible to independent probes."""
    adapter.dispatch(occurrence, invocation)
    connection.commit()


def test_async_worker_integrates_distinct_absurd_lane_claimants_and_terminals(absurd_dsn, authority, queue):
    adapter = adapter_over(authority, default_queue=queue)
    for occurrence in range(1, 4):
        adapter.dispatch(occurrence, invocation_for(queue, payload=occurrence))
    authority.commit()
    entered = 0
    peak = 0
    release = asyncio.Event()
    all_entered = asyncio.Event()

    async def probe(invocation, *, context):
        nonlocal entered, peak
        entered += 1
        peak = max(peak, entered)
        if entered == 3:
            all_entered.set()
        details = await context.heartbeat(details={"payload": invocation.input["payload"]})
        await release.wait()
        entered -= 1
        return details

    worker = AsyncWorker(
        lambda: AbsurdWorkerDispatch(absurd_dsn, queues=(queue,), worker_id="async-absurd"),
        {"probe_activity": probe},
        concurrency=3,
    )

    async def exercise():
        running = asyncio.create_task(worker.run(poll_interval=0.01))
        await asyncio.wait_for(all_entered.wait(), 5)
        worker.stop()
        release.set()
        await running

    asyncio.run(asyncio.wait_for(exercise(), 10))

    assert peak == 3
    assert sorted(adapter.collect()) == [(number, {"payload": number}) for number in range(1, 4)]


def queue_state(connection, queue: str, key: str):
    return connection.execute(
        sql.SQL(
            "SELECT state, first_started_at, last_attempt_run::text FROM absurd.{} WHERE idempotency_key = %s"
        ).format(sql.Identifier(f"t_{queue}")),
        (key,),
    ).fetchone()


def assert_no_target_task(connection, queue: str, key: str) -> None:
    """Every refused reroute leaves no live task (only a prior tombstone is admissible) at its target."""
    if connection.execute("SELECT 1 FROM absurd.list_queues() WHERE queue_name = %s", (queue,)).fetchone():
        assert connection.execute(
            sql.SQL("SELECT count(*) FROM absurd.{} WHERE idempotency_key = %s AND state != 'cancelled'").format(
                sql.Identifier(f"t_{queue}")
            ),
            (key,),
        ).fetchone() == (0,)


class TestSchemaPin:
    def test_the_vendored_schema_matches_the_triple_pin(self):
        vendored = (
            REPO_ROOT / "src" / "petrus" / "motus" / "dispatch" / "absurd_schema" / f"absurd-{ABSURD_VERSION}.sql"
        )
        assert hashlib.sha256(vendored.read_bytes()).hexdigest() == ABSURD_SQL_SHA256

    def test_ensure_is_idempotent_by_version_on_a_provisioned_database(self, observer):
        ensure_absurd_schema(observer)  # the session fixture already applied it once
        assert observer.execute("SELECT absurd.get_schema_version()").fetchone()[0] == ABSURD_VERSION

    def test_a_tampered_vendored_copy_is_refused_before_any_apply(self, scratch_database, monkeypatch):
        monkeypatch.setattr(petrus.motus.dispatch.absurd, "ABSURD_SQL_SHA256", "0" * 64)
        with psycopg.connect(scratch_database, autocommit=True) as scratch:
            with pytest.raises(RuntimeError, match="hash mismatch"):
                ensure_absurd_schema(scratch)
            # Nothing was applied: the refusal precedes the sink.
            assert scratch.execute("SELECT 1 FROM pg_namespace WHERE nspname = 'absurd'").fetchone() is None

    def test_a_foreign_absurd_schema_with_no_version_answer_is_refused(self, scratch_database):
        with psycopg.connect(scratch_database, autocommit=True) as scratch:
            scratch.execute("CREATE SCHEMA absurd")
            with pytest.raises(RuntimeError, match="get_schema_version"):
                ensure_absurd_schema(scratch)

    def test_a_drifted_version_is_refused_as_a_deliberate_repin(self, scratch_database):
        with psycopg.connect(scratch_database, autocommit=True) as scratch:
            scratch.execute("CREATE SCHEMA absurd")
            scratch.execute(
                "CREATE FUNCTION absurd.get_schema_version() RETURNS text LANGUAGE sql AS $$ SELECT '9.9.9' $$"
            )
            with pytest.raises(RuntimeError, match="deliberate act"):
                ensure_absurd_schema(scratch)

    def test_a_tampered_copy_is_refused_even_when_already_provisioned(self, observer, monkeypatch):
        # The hash is re-verified on EVERY call, the version-check path
        # included: ensure never vouches for an installation while the
        # vendored copy beside it is edited.
        monkeypatch.setattr(petrus.motus.dispatch.absurd, "ABSURD_SQL_SHA256", "0" * 64)
        with pytest.raises(RuntimeError, match="hash mismatch"):
            ensure_absurd_schema(observer)

    def test_ensure_provisions_an_empty_database_to_the_pinned_version(self, scratch_database):
        with psycopg.connect(scratch_database, autocommit=True) as scratch:
            ensure_absurd_schema(scratch)
            assert scratch.execute("SELECT absurd.get_schema_version()").fetchone()[0] == ABSURD_VERSION


@pytest.fixture
def scratch_database(postgres_dsn):
    """A disposable database in the session container — for the provisioning refusals that must never touch the shared schemas."""
    name = f"scratch_{uuid4().hex[:10]}"
    with psycopg.connect(postgres_dsn, autocommit=True) as admin:
        admin.execute(f"CREATE DATABASE {name}")
        yield postgres_dsn.rsplit("/", 1)[0] + f"/{name}"
        admin.execute(f"DROP DATABASE {name} WITH (FORCE)")


class TestQueueMapping:
    def test_default_and_exact_activity_override(self, observer):
        adapter = AbsurdDispatch(
            observer, instance="routing", default_queue="private", activity_queues={"transcribe": "gpu"}
        )
        assert adapter.queue_for("ordinary") == "private"
        assert adapter.queue_for("transcribe") == "gpu"

    def test_activity_queue_overrides_are_snapshotted_at_adapter_construction(self, observer):
        routes = {"transcribe": "gpu"}
        adapter = AbsurdDispatch(observer, instance="routing", activity_queues=routes)
        routes["transcribe"] = "changed"
        routes["new"] = "new_queue"
        assert adapter.queue_for("transcribe") == "gpu"
        assert adapter.queue_for("new") == "default"

    def test_a_capability_that_cannot_be_a_queue_name_is_refused_loud(self):
        for bad in ("Agentic", "0day", "a-b", "", 7, "x" * 58):
            with pytest.raises(ValueError, match="queue.*invalid"):
                validate_queue(bad)


class TestInvocationWire:
    def test_the_invocation_crosses_the_queue_whole_and_round_trips_value_equal(self):
        original = ActivityInvocation(
            "implement_issue",
            input={"id": "goose", "n": 3},
            policy=ExecutionPolicy(attempts=4),
            correlation="corr-1",
            idempotency="effect-goose",
        )
        assert decode_invocation(encode_invocation(original)) == original

    def test_the_derived_none_identities_survive_the_wire(self):
        original = ActivityInvocation("check_issue", input="goose")
        assert decode_invocation(encode_invocation(original)) == original

    def test_a_foreign_payload_is_refused_loud(self):
        with pytest.raises(ValueError, match="does not decode as an activity invocation"):
            decode_invocation({"task": "nope"})

    def test_the_decode_is_strict_field_by_field(self):
        # A worker never guesses at an instruction: the exact wire shape or
        # nothing — missing fields, extra fields, a widened policy this pin
        # does not know, malformed capabilities, and a non-string identity
        # are each their own loud refusal.
        wire = encode_invocation(ActivityInvocation("check_issue", input="goose"))
        rejections = (
            {**wire, "extra": 1},  # extra field
            {key: value for key, value in wire.items() if key != "idempotency"},  # missing field
            {**wire, "policy": {"attempts": "3"}},  # non-int attempts
            {**wire, "policy": {"attempts": True}},  # bool is not an attempt count
            {**wire, "policy": {"attempts": 1, "backoff": 2}},  # widened policy: not this pin's vocabulary
            {**wire, "policy": [1]},  # policy not a mapping
            {**wire, "correlation": 7},  # non-string identity
            "not-a-mapping",
        )
        for payload in rejections:
            with pytest.raises(ValueError, match="does not decode as an activity invocation"):
                decode_invocation(payload)


class TestDispatch:
    def test_a_second_dispatch_of_one_occurrence_never_double_enqueues(self, authority, observer, queue):
        adapter = adapter_over(authority, default_queue=queue)
        invocation = invocation_for(queue)

        publish(adapter, authority, 7, invocation)
        publish(adapter, authority, 7, invocation)

        assert len(task_rows(observer, queue, adapter, 7)) == 1

    def test_the_doorbell_and_the_spawn_ride_the_open_transaction(self, authority, listener, observer, queue):
        # Join mode: BEFORE the commit, another connection sees neither the
        # task nor the NOTIFY; the commit delivers both together [D11]. The
        # queue pre-exists (committed) so invisibility is the TASK's, not the
        # table's — the rollback test below covers the virgin-queue shape.
        observer.execute("SELECT absurd.create_queue(%s)", (queue,))
        listener.execute(f"LISTEN {DISPATCH_CHANNEL}")
        adapter = adapter_over(authority, default_queue=queue)
        adapter.dispatch(1, invocation_for(queue))

        assert list(listener.notifies(timeout=0.2)) == []
        assert observer.execute(f"SELECT count(*) FROM absurd.t_{queue}").fetchone()[0] == 0

        authority.commit()

        notes = list(listener.notifies(timeout=5.0, stop_after=1))
        assert [(note.channel, note.payload) for note in notes] == [(DISPATCH_CHANNEL, queue)]
        assert observer.execute(f"SELECT count(*) FROM absurd.t_{queue} WHERE state = 'pending'").fetchone()[0] == 1

    def test_a_rollback_vanishes_the_spawn_and_the_doorbell_together(self, authority, listener, observer, queue):
        listener.execute(f"LISTEN {DISPATCH_CHANNEL}")
        adapter = adapter_over(authority, default_queue=queue)
        adapter.dispatch(1, invocation_for(queue))

        authority.rollback()

        assert list(listener.notifies(timeout=0.3)) == []
        # The queue's tables may not even exist (create_queue vanished too) —
        # either way, no task landed anywhere under this adapter's identity.
        tables = observer.execute(
            "SELECT count(*) FROM pg_tables WHERE schemaname = 'absurd' AND tablename = %s", (f"t_{queue}",)
        ).fetchone()[0]
        if tables:
            assert observer.execute(f"SELECT count(*) FROM absurd.t_{queue}").fetchone()[0] == 0

    def test_the_task_payload_is_the_serialized_invocation(self, authority, observer, queue):
        adapter = adapter_over(authority, default_queue=queue)
        invocation = invocation_for(queue, payload={"k": [1, 2]})
        publish(adapter, authority, 3, invocation)

        task_name, params = observer.execute(f"SELECT task_name, params FROM absurd.t_{queue}").fetchone()
        assert task_name == invocation.activity
        assert decode_invocation(params) == invocation

    def test_the_policy_maps_to_max_attempts_with_immediate_retry(self, authority, observer, queue):
        adapter = adapter_over(authority, default_queue=queue)
        publish(adapter, authority, 4, invocation_for(queue, attempts=3))

        max_attempts, strategy = observer.execute(
            f"SELECT max_attempts, retry_strategy FROM absurd.t_{queue}"
        ).fetchone()
        assert max_attempts == 3
        assert strategy == {"kind": "none"}


class TestCollect:
    def test_collect_returns_results_in_completion_order_and_drains(self, authority, observer, queue):
        adapter = adapter_over(authority, default_queue=queue)
        publish(adapter, authority, 1, invocation_for(queue, payload="first-dispatched"))
        publish(adapter, authority, 2, invocation_for(queue, payload="second-dispatched"))
        run_1, _, _ = claim_one(observer, queue)
        run_2, _, _ = claim_one(observer, queue)
        complete(observer, queue, run_2, {"answer": 2})
        complete(observer, queue, run_1, {"answer": 1})

        # Completion order, not dispatch order: 2 finished first.
        assert adapter.collect() == ((2, {"answer": 2}), (1, {"answer": 1}))
        assert adapter.collect() == ()

    def test_policy_exhaustion_surfaces_as_an_activity_failure(self, authority, observer, queue):
        adapter = adapter_over(authority, default_queue=queue)
        publish(adapter, authority, 1, invocation_for(queue, attempts=2))
        run_1, _, attempt_1 = claim_one(observer, queue)
        fail(observer, queue, run_1, "SparkError", "no fuel")
        run_2, _, attempt_2 = claim_one(observer, queue)  # kind "none": the retry is immediately claimable
        fail(observer, queue, run_2, "SparkError", "still no fuel")

        assert (attempt_1, attempt_2) == (1, 2)
        assert adapter.collect() == ((1, ActivityFailure("SparkError: still no fuel")),)

    def test_a_surviving_failure_is_not_a_terminal_outcome(self, authority, observer, queue):
        adapter = adapter_over(authority, default_queue=queue)
        publish(adapter, authority, 1, invocation_for(queue, attempts=2))
        run_1, _, _ = claim_one(observer, queue)
        fail(observer, queue, run_1, "SparkError", "first spark fizzled")

        # One attempt spent, one left: nothing terminal to collect yet.
        assert adapter.collect() == ()

    def test_a_cancelled_task_is_refused_loud_never_folded(self, authority, observer, queue):
        adapter = adapter_over(authority, default_queue=queue)
        publish(adapter, authority, 1, invocation_for(queue))
        (task_id,) = observer.execute(f"SELECT task_id FROM absurd.t_{queue}").fetchone()
        observer.execute("SELECT absurd.cancel_task(%s, %s)", (queue, task_id))

        with pytest.raises(RuntimeError, match="cancelled"):
            adapter.collect()


class TestLookupFirstRedispatch:
    # K4 lookup-first is dispatch's own shape: the spawn-by-recovery-identity
    # IS the substrate lookup, so a resumed authority reconciles by simply
    # redispatching the recorded outbox through the one door.

    def test_provider_valid_unconfigured_queue_does_not_break_normal_dispatch(self, authority, observer, queue):
        observer.execute("SELECT absurd.create_queue(%s)", ("GPU-jobs",))
        adapter = adapter_over(authority, default_queue=queue)
        publish(adapter, authority, 1, invocation_for(queue))
        assert task_rows(observer, queue, adapter, 1)[0][1] == "pending"

    def test_matching_pending_custody_on_provider_valid_unconfigured_queue_transfers(self, authority, observer):
        old, target = "GPU-jobs", f"target_{uuid4().hex[:8]}"
        instance = f"quoted-{uuid4().hex[:8]}"
        invocation = ActivityInvocation("probe_activity")
        key = f"{instance}:occurrence-1"
        observer.execute("SELECT absurd.create_queue(%s)", (old,))
        observer.execute(
            "SELECT absurd.spawn_task(%s, %s, %s, %s)",
            (old, invocation.activity, Jsonb(encode_invocation(invocation)), Jsonb({"idempotency_key": key})),
        )
        resumed = AbsurdDispatch(authority, instance=instance, default_queue=target)
        publish(resumed, authority, 1, invocation)
        assert queue_state(observer, old, key)[0] == "cancelled"
        assert queue_state(observer, target, key)[0] == "pending"

    def test_matching_completed_custody_on_provider_valid_unconfigured_queue_dispatch_collects_and_waits(
        self, authority, observer
    ):
        old, target = "GPU-done", f"target_{uuid4().hex[:8]}"
        instance = f"quoted-done-{uuid4().hex[:8]}"
        invocation = ActivityInvocation("probe_activity")
        key = f"{instance}:occurrence-1"
        observer.execute("SELECT absurd.create_queue(%s)", (old,))
        observer.execute(
            "SELECT absurd.spawn_task(%s, %s, %s, %s)",
            (
                old,
                invocation.activity,
                Jsonb(encode_invocation(invocation)),
                Jsonb({"idempotency_key": key, "max_attempts": 1}),
            ),
        )
        run, _, _ = claim_one(observer, old)
        complete(observer, old, run, "quoted done")
        resumed = AbsurdDispatch(authority, instance=instance, default_queue=target)
        publish(resumed, authority, 1, invocation)
        assert resumed.wait_for_results(0) is True
        assert resumed.collect() == ((1, "quoted done"),)

    def test_matching_failed_custody_on_provider_valid_unconfigured_queue_dispatch_collects_and_waits(
        self, authority, observer
    ):
        old, target = "GPU-failed", f"target_{uuid4().hex[:8]}"
        instance = f"quoted-fail-{uuid4().hex[:8]}"
        invocation = ActivityInvocation("probe_activity")
        key = f"{instance}:occurrence-1"
        observer.execute("SELECT absurd.create_queue(%s)", (old,))
        observer.execute(
            "SELECT absurd.spawn_task(%s, %s, %s, %s)",
            (
                old,
                invocation.activity,
                Jsonb(encode_invocation(invocation)),
                Jsonb({"idempotency_key": key, "max_attempts": 1}),
            ),
        )
        run, _, _ = claim_one(observer, old)
        fail(observer, old, run, "Quoted", "failed")
        resumed = AbsurdDispatch(authority, instance=instance, default_queue=target)
        publish(resumed, authority, 1, invocation)
        assert resumed.wait_for_results(0) is True
        assert resumed.collect() == ((1, ActivityFailure("Quoted: failed")),)

    def test_a_live_task_is_left_alone(self, authority, observer, queue):
        adapter = adapter_over(authority, default_queue=queue)
        invocation = invocation_for(queue)
        publish(adapter, authority, 1, invocation)

        resumed = AbsurdDispatch(authority, instance=adapter._instance, default_queue=queue)
        publish(resumed, authority, 1, invocation)
        [(_, state, attempts)] = task_rows(observer, queue, adapter, 1)
        assert (state, attempts) == ("pending", 1)  # one task, untouched

    def test_a_completed_task_is_collected_not_reinvoked(self, authority, observer, queue):
        adapter = adapter_over(authority, default_queue=queue)
        invocation = invocation_for(queue)
        publish(adapter, authority, 1, invocation)
        run_id, _, _ = claim_one(observer, queue)
        complete(observer, queue, run_id, "already done")

        # A fresh adapter session (the resumed authority) redispatches by
        # lookup-first: the durable outcome is observed, never re-run.
        resumed = AbsurdDispatch(authority, instance=adapter._instance, default_queue=queue)
        publish(resumed, authority, 1, invocation)
        assert resumed.collect() == ((1, "already done"),)
        assert len(task_rows(observer, queue, adapter, 1)) == 1

    def test_an_absent_task_is_respawned_under_the_same_identity(self, authority, observer, queue):
        # The reconstructible-machinery claim: Absurd state lost entirely,
        # canonical facts intact — redispatch re-enqueues under the SAME
        # recovery identity, at-least-once.
        adapter = adapter_over(authority, default_queue=queue)
        invocation = invocation_for(queue)
        publish(adapter, authority, 1, invocation)
        observer.execute(f"DELETE FROM absurd.r_{queue}")
        observer.execute(f"DELETE FROM absurd.t_{queue}")

        resumed = AbsurdDispatch(authority, instance=adapter._instance, default_queue=queue)
        publish(resumed, authority, 1, invocation)
        [(task_id, state, _)] = task_rows(observer, queue, adapter, 1)
        assert state == "pending"

    def test_a_never_started_pending_custody_moves_atomically_to_the_new_route(self, authority, observer):
        old, new = f"old_{uuid4().hex[:8]}", f"new_{uuid4().hex[:8]}"
        instance = f"move-{uuid4().hex[:8]}"
        invocation = ActivityInvocation("probe_activity")
        first = AbsurdDispatch(authority, instance=instance, default_queue=old)
        publish(first, authority, 1, invocation)

        resumed = AbsurdDispatch(authority, instance=instance, default_queue=new)
        publish(resumed, authority, 1, invocation)

        key = f"{instance}:occurrence-1"
        assert observer.execute(f"SELECT state FROM absurd.t_{old} WHERE idempotency_key = %s", (key,)).fetchone() == (
            "cancelled",
        )
        assert observer.execute(f"SELECT state FROM absurd.t_{new} WHERE idempotency_key = %s", (key,)).fetchone() == (
            "pending",
        )
        assert resumed._tasks[1][0] == new
        _, claimed_task, _ = claim_one(observer, new)
        assert str(claimed_task) == resumed._tasks[1][1]

    def test_route_back_to_a_cancelled_tombstone_refuses_without_cancelling_live_custody(self, authority, observer):
        queue_a, queue_b = f"a_{uuid4().hex[:8]}", f"b_{uuid4().hex[:8]}"
        instance = f"routeback-{uuid4().hex[:8]}"
        invocation = ActivityInvocation("probe_activity")
        publish(AbsurdDispatch(authority, instance=instance, default_queue=queue_a), authority, 1, invocation)
        publish(AbsurdDispatch(authority, instance=instance, default_queue=queue_b), authority, 1, invocation)

        route_back = AbsurdDispatch(authority, instance=instance, default_queue=queue_a)
        with pytest.raises(RuntimeError, match="target queue.*cancelled tombstone"):
            route_back.dispatch(1, invocation)
        authority.rollback()
        key = f"{instance}:occurrence-1"
        assert observer.execute(
            sql.SQL("SELECT state FROM absurd.{} WHERE idempotency_key = %s").format(sql.Identifier(f"t_{queue_b}")),
            (key,),
        ).fetchone() == ("pending",)
        assert_no_target_task(observer, queue_a, key)

    def test_cancelled_history_elsewhere_allows_a_fresh_target_without_a_tombstone(self, authority, observer):
        old, fresh = f"old_{uuid4().hex[:8]}", f"fresh_{uuid4().hex[:8]}"
        instance = f"history-{uuid4().hex[:8]}"
        invocation = ActivityInvocation("probe_activity")
        first = AbsurdDispatch(authority, instance=instance, default_queue=old)
        publish(first, authority, 1, invocation)
        (task_id,) = observer.execute(
            sql.SQL("SELECT task_id FROM absurd.{}").format(sql.Identifier(f"t_{old}"))
        ).fetchone()
        observer.execute("SELECT absurd.cancel_task(%s, %s)", (old, task_id))

        resumed = AbsurdDispatch(authority, instance=instance, default_queue=fresh)
        publish(resumed, authority, 1, invocation)
        assert resumed._tasks[1][0] == fresh

    def test_all_cancelled_route_a_to_b_to_a_refuses_without_guessing_custody(self, authority, observer):
        queue_a, queue_b = f"a_{uuid4().hex[:8]}", f"b_{uuid4().hex[:8]}"
        instance = f"all-cancelled-back-{uuid4().hex[:8]}"
        invocation = ActivityInvocation("probe_activity")
        publish(AbsurdDispatch(authority, instance=instance, default_queue=queue_a), authority, 1, invocation)
        publish(AbsurdDispatch(authority, instance=instance, default_queue=queue_b), authority, 1, invocation)
        key = f"{instance}:occurrence-1"
        (task_b,) = observer.execute(
            sql.SQL("SELECT task_id FROM absurd.{} WHERE idempotency_key = %s").format(sql.Identifier(f"t_{queue_b}")),
            (key,),
        ).fetchone()
        observer.execute("SELECT absurd.cancel_task(%s, %s)", (queue_b, task_b))

        route_back = AbsurdDispatch(authority, instance=instance, default_queue=queue_a)
        with pytest.raises(RuntimeError, match="target queue.*cancelled tombstone"):
            route_back.dispatch(1, invocation)
        authority.rollback()

        assert [queue_state(observer, queue, key)[0] for queue in (queue_a, queue_b)] == ["cancelled", "cancelled"]
        assert (
            sum(
                observer.execute(
                    sql.SQL(
                        "SELECT count(*) FROM absurd.{} WHERE idempotency_key = %s AND state != 'cancelled'"
                    ).format(sql.Identifier(f"t_{queue}")),
                    (key,),
                ).fetchone()[0]
                for queue in (queue_a, queue_b)
            )
            == 0
        )
        assert 1 not in route_back._tasks

    def test_cross_queue_transfer_refuses_autocommit_before_cancellation(self, observer, absurd_dsn):
        old, new = f"old_{uuid4().hex[:8]}", f"new_{uuid4().hex[:8]}"
        instance = f"autocommit-{uuid4().hex[:8]}"
        invocation = ActivityInvocation("probe_activity")
        with psycopg.connect(absurd_dsn, autocommit=False) as joined:
            publish(AbsurdDispatch(joined, instance=instance, default_queue=old), joined, 1, invocation)

        with pytest.raises(RuntimeError, match="autocommit mode"):
            AbsurdDispatch(observer, instance=instance, default_queue=new).dispatch(1, invocation)
        key = f"{instance}:occurrence-1"
        assert observer.execute(
            sql.SQL("SELECT state FROM absurd.{} WHERE idempotency_key = %s").format(sql.Identifier(f"t_{old}")),
            (key,),
        ).fetchone() == ("pending",)
        assert observer.execute("SELECT 1 FROM absurd.list_queues() WHERE queue_name = %s", (new,)).fetchone() is None

    def test_started_custody_is_never_cancelled_or_duplicated(self, authority, observer):
        old, new = f"old_{uuid4().hex[:8]}", f"new_{uuid4().hex[:8]}"
        instance = f"started-{uuid4().hex[:8]}"
        invocation = ActivityInvocation("probe_activity")
        first = AbsurdDispatch(authority, instance=instance, default_queue=old)
        publish(first, authority, 1, invocation)
        claim_one(observer, old)

        resumed = AbsurdDispatch(authority, instance=instance, default_queue=new)
        with pytest.raises(RuntimeError, match="never-started task may move"):
            resumed.dispatch(1, invocation)
        authority.rollback()
        key = f"{instance}:occurrence-1"
        assert observer.execute(f"SELECT state FROM absurd.t_{old} WHERE idempotency_key = %s", (key,)).fetchone() == (
            "running",
        )
        assert observer.execute("SELECT 1 FROM absurd.list_queues() WHERE queue_name = %s", (new,)).fetchone() is None
        assert_no_target_task(observer, new, key)

    def test_a_prior_started_task_forced_back_to_pending_is_refused(self, authority, observer):
        old, new = f"old_{uuid4().hex[:8]}", f"new_{uuid4().hex[:8]}"
        instance = f"forced-{uuid4().hex[:8]}"
        invocation = ActivityInvocation("probe_activity")
        publish(AbsurdDispatch(authority, instance=instance, default_queue=old), authority, 1, invocation)
        claim_one(observer, old)
        key = f"{instance}:occurrence-1"
        _, _, run_id = queue_state(observer, old, key)
        observer.execute(
            sql.SQL("UPDATE absurd.{} SET state = 'pending' WHERE idempotency_key = %s").format(
                sql.Identifier(f"t_{old}")
            ),
            (key,),
        )
        observer.execute(
            sql.SQL("UPDATE absurd.{} SET state = 'pending' WHERE run_id = %s").format(sql.Identifier(f"r_{old}")),
            (run_id,),
        )
        with pytest.raises(RuntimeError, match="never-started task may move"):
            AbsurdDispatch(authority, instance=instance, default_queue=new).dispatch(1, invocation)
        authority.rollback()
        assert_no_target_task(observer, new, key)

    def test_terminal_custody_reconciles_on_its_old_queue(self, authority, observer):
        old, new = f"old_{uuid4().hex[:8]}", f"new_{uuid4().hex[:8]}"
        instance = f"terminal-{uuid4().hex[:8]}"
        invocation = ActivityInvocation("probe_activity")
        first = AbsurdDispatch(authority, instance=instance, default_queue=old)
        publish(first, authority, 1, invocation)
        run, _, _ = claim_one(observer, old)
        complete(observer, old, run, "done")

        resumed = AbsurdDispatch(authority, instance=instance, default_queue=new)
        publish(resumed, authority, 1, invocation)
        assert resumed.collect() == ((1, "done"),)
        assert resumed._tasks[1][0] == old

    @pytest.mark.parametrize("terminal", ["completed", "failed"])
    def test_terminal_custody_survives_route_a_to_b_to_a(self, authority, observer, terminal):
        queue_a, queue_b = f"a_{uuid4().hex[:8]}", f"b_{uuid4().hex[:8]}"
        instance = f"terminal-back-{uuid4().hex[:8]}"
        invocation = ActivityInvocation("probe_activity")
        publish(AbsurdDispatch(authority, instance=instance, default_queue=queue_a), authority, 1, invocation)
        publish(AbsurdDispatch(authority, instance=instance, default_queue=queue_b), authority, 1, invocation)
        run, _, _ = claim_one(observer, queue_b)
        if terminal == "completed":
            complete(observer, queue_b, run, "done on b")
            expected = "done on b"
        else:
            fail(observer, queue_b, run, "Broken", "on b")
            expected = ActivityFailure("Broken: on b")

        route_back = AbsurdDispatch(authority, instance=instance, default_queue=queue_a)
        publish(route_back, authority, 1, invocation)

        assert route_back._tasks[1][0] == queue_b
        assert route_back.collect() == ((1, expected),)

    @pytest.mark.parametrize("broken", ["missing", "invalid"])
    def test_malformed_terminal_last_attempt_is_refused_without_a_target(self, authority, observer, broken):
        old, target = f"old_{uuid4().hex[:8]}", f"target_{uuid4().hex[:8]}"
        instance = f"broken-run-{uuid4().hex[:8]}"
        invocation = ActivityInvocation("probe_activity")
        publish(AbsurdDispatch(authority, instance=instance, default_queue=old), authority, 1, invocation)
        run, _, _ = claim_one(observer, old)
        complete(observer, old, run, "done")
        key = f"{instance}:occurrence-1"
        if broken == "missing":
            observer.execute(
                sql.SQL("UPDATE absurd.{} SET last_attempt_run = NULL WHERE idempotency_key = %s").format(
                    sql.Identifier(f"t_{old}")
                ),
                (key,),
            )
        else:
            observer.execute(
                sql.SQL("UPDATE absurd.{} SET state = 'failed' WHERE run_id = %s").format(sql.Identifier(f"r_{old}")),
                (run,),
            )

        with pytest.raises(RuntimeError, match="terminal state is invalid"):
            AbsurdDispatch(authority, instance=instance, default_queue=target).dispatch(1, invocation)
        authority.rollback()
        assert (
            observer.execute("SELECT 1 FROM absurd.list_queues() WHERE queue_name = %s", (target,)).fetchone() is None
        )

    @pytest.mark.parametrize("state", ["sleeping", "running"])
    def test_non_pending_custody_is_never_moved(self, authority, observer, state):
        old, new = f"old_{uuid4().hex[:8]}", f"new_{uuid4().hex[:8]}"
        instance = f"state-{uuid4().hex[:8]}"
        invocation = ActivityInvocation("probe_activity")
        publish(AbsurdDispatch(authority, instance=instance, default_queue=old), authority, 1, invocation)
        key = f"{instance}:occurrence-1"
        _, _, run_id = queue_state(observer, old, key)
        observer.execute(
            sql.SQL("UPDATE absurd.{} SET state = %s, first_started_at = now() WHERE idempotency_key = %s").format(
                sql.Identifier(f"t_{old}")
            ),
            (state, key),
        )
        observer.execute(
            sql.SQL("UPDATE absurd.{} SET state = %s WHERE run_id = %s").format(sql.Identifier(f"r_{old}")),
            (state, run_id),
        )

        with pytest.raises(RuntimeError, match="never-started task may move"):
            AbsurdDispatch(authority, instance=instance, default_queue=new).dispatch(1, invocation)
        authority.rollback()
        assert queue_state(observer, old, key)[0] == state
        assert_no_target_task(observer, new, key)

    def test_ambiguous_custody_refuses_without_changes(self, authority, observer):
        one, two, target = (f"q_{uuid4().hex[:8]}" for _ in range(3))
        instance = f"duplicate-{uuid4().hex[:8]}"
        invocation = ActivityInvocation("probe_activity")
        key = f"{instance}:occurrence-1"
        for queue in (one, two):
            observer.execute("SELECT absurd.create_queue(%s)", (queue,))
            observer.execute(
                "SELECT absurd.spawn_task(%s, %s, %s, %s)",
                (queue, invocation.activity, Jsonb(encode_invocation(invocation)), Jsonb({"idempotency_key": key})),
            )

        with pytest.raises(RuntimeError, match="ambiguous.*2 live tasks"):
            AbsurdDispatch(authority, instance=instance, default_queue=target).dispatch(1, invocation)
        authority.rollback()
        assert [queue_state(observer, queue, key)[0] for queue in (one, two)] == ["pending", "pending"]
        assert_no_target_task(observer, target, key)

    def test_locked_run_refuses_bounded_without_touching_the_task(self, authority, observer, absurd_dsn):
        old, new = f"old_{uuid4().hex[:8]}", f"new_{uuid4().hex[:8]}"
        instance = f"locked-{uuid4().hex[:8]}"
        invocation = ActivityInvocation("probe_activity")
        publish(AbsurdDispatch(authority, instance=instance, default_queue=old), authority, 1, invocation)
        key = f"{instance}:occurrence-1"
        _, _, run_id = queue_state(observer, old, key)
        with psycopg.connect(absurd_dsn, autocommit=False) as locker:
            locker.execute(
                sql.SQL("SELECT 1 FROM absurd.{} WHERE run_id = %s FOR UPDATE").format(sql.Identifier(f"r_{old}")),
                (run_id,),
            )
            with pytest.raises(RuntimeError, match="currently locked"):
                AbsurdDispatch(authority, instance=instance, default_queue=new).dispatch(1, invocation)
            authority.rollback()
        assert queue_state(observer, old, key)[0] == "pending"
        assert_no_target_task(observer, new, key)

    def test_adversarial_task_first_lock_refuses_without_deadlock(self, authority, observer, absurd_dsn):
        old, new = f"old_{uuid4().hex[:8]}", f"new_{uuid4().hex[:8]}"
        instance = f"tasklock-{uuid4().hex[:8]}"
        invocation = ActivityInvocation("probe_activity")
        publish(AbsurdDispatch(authority, instance=instance, default_queue=old), authority, 1, invocation)
        key = f"{instance}:occurrence-1"
        with psycopg.connect(absurd_dsn, autocommit=False) as locker:
            locker.execute(
                sql.SQL("SELECT 1 FROM absurd.{} WHERE idempotency_key = %s FOR UPDATE").format(
                    sql.Identifier(f"t_{old}")
                ),
                (key,),
            )
            authority.execute("SET LOCAL statement_timeout = '5s'")
            with pytest.raises(RuntimeError, match="currently locked"):
                AbsurdDispatch(authority, instance=instance, default_queue=new).dispatch(1, invocation)
            authority.rollback()
        assert queue_state(observer, old, key)[0] == "pending"
        assert_no_target_task(observer, new, key)

    def test_exception_after_cancel_before_spawn_rolls_back_joined_transaction_and_notify(
        self, authority, observer, listener
    ):
        old, new = f"old_{uuid4().hex[:8]}", f"new_{uuid4().hex[:8]}"
        instance = f"rollback-{uuid4().hex[:8]}"
        invocation = ActivityInvocation("probe_activity")
        publish(AbsurdDispatch(authority, instance=instance, default_queue=old), authority, 1, invocation)
        key = f"{instance}:occurrence-1"
        listener.execute(f"LISTEN {DISPATCH_CHANNEL}")

        class FailBeforeSpawn:
            autocommit = False

            def __init__(self, connection):
                self.connection = connection

            def execute(self, query, params=None):
                if query == "SELECT absurd.create_queue(%s)" and params == (new,):
                    raise RuntimeError("injected after cancel")
                return self.connection.execute(query, params)

        with pytest.raises(RuntimeError, match="injected after cancel"):
            AbsurdDispatch(FailBeforeSpawn(authority), instance=instance, default_queue=new).dispatch(1, invocation)
        authority.rollback()
        assert queue_state(observer, old, key)[0] == "pending"
        assert_no_target_task(observer, new, key)
        assert list(listener.notifies(timeout=0.3)) == []

    def test_reroute_preserves_old_and_new_idempotency_key_exactly(self, authority, observer):
        old, new = f"old_{uuid4().hex[:8]}", f"new_{uuid4().hex[:8]}"
        instance = f"identity-{uuid4().hex[:8]}"
        invocation = ActivityInvocation("probe_activity")
        publish(AbsurdDispatch(authority, instance=instance, default_queue=old), authority, 1, invocation)
        publish(AbsurdDispatch(authority, instance=instance, default_queue=new), authority, 1, invocation)
        expected = f"{instance}:occurrence-1"
        old_key = observer.execute(
            sql.SQL("SELECT idempotency_key FROM absurd.{}").format(sql.Identifier(f"t_{old}"))
        ).fetchone()[0]
        new_key = observer.execute(
            sql.SQL("SELECT idempotency_key FROM absurd.{}").format(sql.Identifier(f"t_{new}"))
        ).fetchone()[0]
        assert old_key == new_key == expected

    def test_real_claim_task_race_recovery_wins(self, authority, observer, absurd_dsn):
        old, new = f"old_{uuid4().hex[:8]}", f"new_{uuid4().hex[:8]}"
        instance = f"claim-race-{uuid4().hex[:8]}"
        invocation = ActivityInvocation("probe_activity")
        publish(AbsurdDispatch(authority, instance=instance, default_queue=old), authority, 1, invocation)
        adapter = AbsurdDispatch(authority, instance=instance, default_queue=new)
        adapter.dispatch(1, invocation)  # row locks held through cancel + replacement spawn
        claimant_query_started = threading.Barrier(2)
        claimant_name = f"recovery-loser-{uuid4().hex[:8]}"

        def race_claim():
            with psycopg.connect(absurd_dsn, autocommit=True, application_name=claimant_name) as claimant:
                claimant_query_started.wait(timeout=5)
                return claimant.execute("SELECT * FROM absurd.claim_task(%s, %s, %s, 1)", (old, "racer", 30)).fetchone()

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(race_claim)
            claimant_query_started.wait(timeout=5)
            # claim_task's SKIP LOCKED posture must execute and return no
            # claim while recovery still holds the cancelled source rows and
            # uncommitted replacement. Committing first would not prove the
            # race: the source would merely already be cancelled.
            assert future.result(timeout=5) is None
            authority.commit()
        key = f"{instance}:occurrence-1"
        assert queue_state(observer, new, key)[0] == "pending"
        _, claimed_target, _ = claim_one(observer, new, worker_id="target-claimer")
        assert str(claimed_target) == adapter._tasks[1][1]

    def test_real_claim_task_race_claim_wins(self, authority, observer, absurd_dsn):
        old, new = f"old_{uuid4().hex[:8]}", f"new_{uuid4().hex[:8]}"
        instance = f"claim-first-{uuid4().hex[:8]}"
        invocation = ActivityInvocation("probe_activity")
        publish(AbsurdDispatch(authority, instance=instance, default_queue=old), authority, 1, invocation)
        key = f"{instance}:occurrence-1"
        start = threading.Barrier(2)
        claimed = threading.Event()
        commit_claim = threading.Event()
        claimant_errors = []

        def race_claim():
            try:
                with psycopg.connect(absurd_dsn, autocommit=False) as claimant:
                    start.wait(timeout=5)
                    claim_one(claimant, old, worker_id="race-winner")
                    claimed.set()
                    assert commit_claim.wait(timeout=5)
                    claimant.commit()
            except BaseException as error:
                claimant_errors.append(error)

        claimant = threading.Thread(target=race_claim)
        claimant.start()
        try:
            start.wait(timeout=5)
            assert claimed.wait(timeout=5)
            with pytest.raises(RuntimeError, match="currently locked"):
                AbsurdDispatch(authority, instance=instance, default_queue=new).dispatch(1, invocation)
            authority.rollback()
        finally:
            commit_claim.set()
            claimant.join(timeout=5)
        assert not claimant.is_alive()
        assert claimant_errors == []
        assert queue_state(observer, old, key)[0] == "running"
        assert_no_target_task(observer, new, key)

    def test_concurrent_recovery_serializes_to_exactly_one_target_custodian(self, authority, observer, absurd_dsn):
        old, new = f"old_{uuid4().hex[:8]}", f"new_{uuid4().hex[:8]}"
        instance = f"race-{uuid4().hex[:8]}"
        invocation = ActivityInvocation("probe_activity")
        publish(AbsurdDispatch(authority, instance=instance, default_queue=old), authority, 1, invocation)
        barrier = threading.Barrier(3)

        def recover():
            with psycopg.connect(absurd_dsn, autocommit=False) as joined:
                joined.execute("SET LOCAL statement_timeout = '5s'")
                barrier.wait(timeout=5)
                publish(AbsurdDispatch(joined, instance=instance, default_queue=new), joined, 1, invocation)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(recover) for _ in range(2)]
            barrier.wait(timeout=5)
            for future in futures:
                future.result(timeout=10)
        key = f"{instance}:occurrence-1"
        assert queue_state(observer, old, key)[0] == "cancelled"
        assert queue_state(observer, new, key)[0] == "pending"
        assert observer.execute(
            sql.SQL("SELECT count(*) FROM absurd.{} WHERE idempotency_key = %s").format(sql.Identifier(f"t_{new}")),
            (key,),
        ).fetchone() == (1,)


class TestWaitForResults:
    def test_a_timeout_with_nothing_terminal_is_an_honest_false(self, authority, queue):
        adapter = adapter_over(authority, poll_interval=0.05, default_queue=queue)
        publish(adapter, authority, 1, invocation_for(queue))

        assert adapter.wait_for_results(0.2) is False

    def test_the_poll_safety_net_finds_a_result_with_the_doorbell_suppressed(
        self, authority, observer, absurd_dsn, queue
    ):
        # No NOTIFY is ever sent: the completion below is raw engine calls.
        # The poll interval alone must surface it — NOTIFY is lossy by
        # contract, so the net never depends on it.
        with psycopg.connect(absurd_dsn, autocommit=True) as listen:
            adapter = adapter_over(authority, listen=listen, poll_interval=0.1, default_queue=queue)
            publish(adapter, authority, 1, invocation_for(queue))
            run_id, _, _ = claim_one(observer, queue)
            complete(observer, queue, run_id, "quietly done")

            assert adapter.wait_for_results(5.0) is True
        assert adapter.collect() == ((1, "quietly done"),)

    def test_the_doorbell_wakes_the_wait_well_under_the_poll_interval(self, authority, observer, absurd_dsn, queue):
        # The poll interval is set far past the deadline, so ONLY the
        # doorbell can explain a timely wake — the latency claim as a
        # structural fact, not a race.
        with psycopg.connect(absurd_dsn, autocommit=True) as listen:
            adapter = adapter_over(authority, listen=listen, poll_interval=30.0, default_queue=queue)
            publish(adapter, authority, 1, invocation_for(queue))
            run_id, _, _ = claim_one(observer, queue)

            ready = threading.Barrier(2)

            def complete_then_ring():
                ready.wait(timeout=5)
                with psycopg.connect(absurd_dsn, autocommit=True) as worker:
                    complete(worker, queue, run_id, "rung in")
                    worker.execute("SELECT pg_notify(%s, %s)", (RESULTS_CHANNEL, queue))

            ringer = threading.Thread(target=complete_then_ring)
            started = time.monotonic()
            ringer.start()
            try:
                ready.wait(timeout=5)
                assert adapter.wait_for_results(10.0) is True
            finally:
                ringer.join()
            assert time.monotonic() - started < 5.0  # woken, not polled (poll floor is 30s)


class TestAdapterShape:
    def test_absurd_dispatch_structurally_satisfies_engine_facing_dispatch(self, observer):
        assert isinstance(adapter_over(observer), Dispatch)

    def test_the_listen_connection_must_be_autocommit(self, observer, authority):
        with pytest.raises(ValueError, match="listen connection must be autocommit"):
            AbsurdDispatch(observer, instance="x", listen=authority)

    def test_the_instance_id_must_be_a_non_empty_string(self, observer):
        for bad in ("", 7):
            with pytest.raises(ValueError, match="non-empty string instance"):
                AbsurdDispatch(observer, instance=bad)


class TestGuardedAttemptDispatch:
    def _spawn(self, authority, queue, *, heartbeat_timeout=2):
        adapter = adapter_over(authority, default_queue=queue)
        invocation = ActivityInvocation(
            "probe_activity",
            input={},
            policy=ExecutionPolicy(attempts=2, heartbeat_timeout=heartbeat_timeout),
        )
        publish(adapter, authority, 1, invocation)

    @staticmethod
    def _await_claim(dispatch, queue):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            delivery = dispatch.claim(queue, timeout=30)
            if delivery is not None:
                return delivery
            time.sleep(0.1)
        pytest.fail("replacement Attempt did not become claimable")

    def test_heartbeat_extends_and_atomically_snapshots_latest_details(self, authority, observer, queue):
        self._spawn(authority, queue, heartbeat_timeout=5)
        dispatch = GuardedDispatch(authority, claimant="boot-a")
        task, prior = dispatch.claim(queue, timeout=1)
        assert prior is None
        before = observer.execute(
            f"SELECT claim_expires_at FROM absurd.r_{queue} WHERE run_id = %s", (task["run_id"],)
        ).fetchone()[0]

        supplied = {"offset": [1]}
        assert (
            dispatch.heartbeat(queue, task_id=task["task_id"], run_id=task["run_id"], timeout=5, details=supplied)
            == supplied
        )
        supplied["offset"].append(2)
        after = observer.execute(
            f"SELECT claim_expires_at FROM absurd.r_{queue} WHERE run_id = %s", (task["run_id"],)
        ).fetchone()[0]
        assert after >= before
        assert dispatch.heartbeat(queue, task_id=task["task_id"], run_id=task["run_id"], timeout=5) == {"offset": [1]}

    def test_stale_claimant_epoch_and_terminal_are_fenced(self, authority, queue):
        self._spawn(authority, queue, heartbeat_timeout=1)
        original = GuardedDispatch(authority, claimant="boot-a")
        task, _ = original.claim(queue, timeout=30)
        impostor = GuardedDispatch(authority, claimant="boot-b")
        with pytest.raises(RuntimeError, match="stale Activity Attempt"):
            impostor.heartbeat(queue, task_id=task["task_id"], run_id=task["run_id"], timeout=1)

        time.sleep(1.1)
        replacement = GuardedDispatch(authority, claimant="boot-b")
        newer, _ = self._await_claim(replacement, queue)
        assert newer["task_id"] == task["task_id"]
        assert newer["run_id"] != task["run_id"]
        for operation in (
            lambda: original.heartbeat(queue, task_id=task["task_id"], run_id=task["run_id"], timeout=1),
            lambda: original.terminal(queue, task_id=task["task_id"], run_id=task["run_id"], result={}),
        ):
            with pytest.raises(RuntimeError, match="stale Activity Attempt"):
                operation()

    def test_replacement_receives_latest_details(self, authority, queue):
        self._spawn(authority, queue, heartbeat_timeout=1)
        first = GuardedDispatch(authority, claimant="boot-a")
        task, _ = first.claim(queue, timeout=30)
        first.heartbeat(queue, task_id=task["task_id"], run_id=task["run_id"], timeout=1, details={"cursor": 7})
        time.sleep(1.1)

        replacement = GuardedDispatch(authority, claimant="boot-b")
        newer, details = self._await_claim(replacement, queue)
        assert newer["task_id"] == task["task_id"]
        assert details == {"cursor": 7}

    def test_same_worker_reconnects_transport_with_same_claimant_and_guard(self, absurd_dsn, authority, queue):
        self._spawn(authority, queue, heartbeat_timeout=5)
        connection = psycopg.connect(absurd_dsn, autocommit=False)
        dispatch = _ReconnectableGuardedDispatch(absurd_dsn, connection, claimant="worker-incarnation-a")
        try:
            task, _ = dispatch.claim(queue, timeout=30)
            first_transport = dispatch.connection
            first_transport.close()

            assert dispatch.heartbeat(
                queue,
                task_id=task["task_id"],
                run_id=task["run_id"],
                timeout=5,
                details={"cursor": 1},
            ) == {"cursor": 1}
            assert dispatch.connection is not first_transport
            assert dispatch.claimant == "worker-incarnation-a"
            assert dispatch._dispatch.claimant == "worker-incarnation-a"

            restarted = GuardedDispatch(authority, claimant="worker-incarnation-b")
            with pytest.raises(RuntimeError, match="stale Activity Attempt"):
                restarted.heartbeat(
                    queue,
                    task_id=task["task_id"],
                    run_id=task["run_id"],
                    timeout=5,
                )
        finally:
            dispatch.close()
        assert first_transport.closed
        assert dispatch.connection.closed

    def test_details_and_lease_roll_back_together_when_commit_fails_after_checkpoint_write(
        self, absurd_dsn, authority, observer, queue
    ):
        self._spawn(authority, queue, heartbeat_timeout=30)
        claimant = "atomic-writer"
        baseline = GuardedDispatch(authority, claimant=claimant)
        task, _ = baseline.claim(queue, timeout=30)
        baseline.heartbeat(queue, task_id=task["task_id"], run_id=task["run_id"], timeout=30, details={"cursor": 1})
        previous_deadline = observer.execute(
            f"SELECT claim_expires_at FROM absurd.r_{queue} WHERE run_id = %s", (task["run_id"],)
        ).fetchone()[0]

        class FailAfterCheckpointWrite:
            def __init__(self, connection):
                self.connection = connection
                self.wrote = False

            @property
            def autocommit(self):
                return self.connection.autocommit

            def execute(self, query, params=None):
                text = str(query)
                cursor = self.connection.execute(query, params)
                if "set_task_checkpoint_state" in text:
                    self.wrote = True
                return cursor

            def commit(self):
                if self.wrote:
                    raise RuntimeError("injected after checkpoint write")
                return self.connection.commit()

            def rollback(self):
                return self.connection.rollback()

        with psycopg.connect(absurd_dsn, autocommit=False) as injected_connection:
            injected = GuardedDispatch(FailAfterCheckpointWrite(injected_connection), claimant=claimant)
            with pytest.raises(RuntimeError, match="injected after checkpoint write"):
                injected.heartbeat(
                    queue,
                    task_id=task["task_id"],
                    run_id=task["run_id"],
                    timeout=300,
                    details={"cursor": 2},
                )

        assert (
            observer.execute(
                f"SELECT claim_expires_at FROM absurd.r_{queue} WHERE run_id = %s", (task["run_id"],)
            ).fetchone()[0]
            == previous_deadline
        )
        assert GuardedDispatch(authority, claimant=claimant).latest_details(queue, task["task_id"]) == {"cursor": 1}

    @pytest.mark.parametrize("operation", ["heartbeat", "details", "success", "failure"])
    @pytest.mark.parametrize("cause", ["claimant", "expired", "replaced", "terminal"])
    def test_every_attempt_operation_rejects_every_stale_custody_cause(
        self, authority, observer, queue, operation, cause
    ):
        self._spawn(authority, queue, heartbeat_timeout=30)
        owner = GuardedDispatch(authority, claimant="owner")
        task, _ = owner.claim(queue, timeout=30)
        actor = owner
        if cause == "claimant":
            actor = GuardedDispatch(authority, claimant="impostor")
        elif cause in {"expired", "replaced"}:
            observer.execute(
                f"UPDATE absurd.r_{queue} SET claim_expires_at = absurd.current_time() - interval '1 second' "
                "WHERE run_id = %s",
                (task["run_id"],),
            )
            if cause == "replaced":
                newer_epoch = observer.execute(
                    f"UPDATE absurd.r_{queue} SET run_id = gen_random_uuid(), claimed_by = 'replacement', "
                    "claim_expires_at = absurd.current_time() + interval '30 seconds' WHERE run_id = %s RETURNING run_id",
                    (task["run_id"],),
                ).fetchone()[0]
                assert newer_epoch != task["run_id"]
        else:
            observer.execute(f"UPDATE absurd.r_{queue} SET state = 'completed' WHERE run_id = %s", (task["run_id"],))

        calls = {
            "heartbeat": lambda: actor.heartbeat(queue, task_id=task["task_id"], run_id=task["run_id"], timeout=30),
            "details": lambda: actor.heartbeat(
                queue, task_id=task["task_id"], run_id=task["run_id"], timeout=30, details={"cursor": 2}
            ),
            "success": lambda: actor.terminal(
                queue, task_id=task["task_id"], run_id=task["run_id"], result={"ok": True}
            ),
            "failure": lambda: actor.terminal(
                queue, task_id=task["task_id"], run_id=task["run_id"], error=ValueError("failed")
            ),
        }
        with pytest.raises(RuntimeError, match="stale Activity Attempt"):
            calls[operation]()

    def test_explicit_null_is_durable_and_invalid_details_fail_before_lease_renewal(self, authority, observer, queue):
        self._spawn(authority, queue, heartbeat_timeout=30)
        dispatch = GuardedDispatch(authority, claimant="owner")
        task, _ = dispatch.claim(queue, timeout=30)
        before = observer.execute(
            f"SELECT claim_expires_at FROM absurd.r_{queue} WHERE run_id = %s", (task["run_id"],)
        ).fetchone()[0]
        with pytest.raises(ValueError, match="heartbeat details"):
            dispatch.heartbeat(
                queue, task_id=task["task_id"], run_id=task["run_id"], timeout=300, details={"bad": object()}
            )
        assert (
            observer.execute(
                f"SELECT claim_expires_at FROM absurd.r_{queue} WHERE run_id = %s", (task["run_id"],)
            ).fetchone()[0]
            == before
        )

        assert (
            dispatch.heartbeat(queue, task_id=task["task_id"], run_id=task["run_id"], timeout=30, details=None) is None
        )
        assert dispatch.latest_details(queue, task["task_id"]) is None
        row = observer.execute(
            f"SELECT checkpoint_name, state, state IS NULL, jsonb_typeof(state), status, owner_run_id "
            f"FROM absurd.c_{queue} "
            "WHERE task_id = %s AND checkpoint_name = %s",
            (task["task_id"], "__impetus_latest_activity_details_v1"),
        ).fetchone()
        assert row is not None
        checkpoint_name, state, is_sql_null, jsonb_type, status, owner_run_id = row
        assert checkpoint_name == "__impetus_latest_activity_details_v1"
        assert state is None  # psycopg decodes the stored JSONB null as Python None.
        assert is_sql_null is False
        assert jsonb_type == "null"
        assert status == "committed"
        assert owner_run_id == task["run_id"]
