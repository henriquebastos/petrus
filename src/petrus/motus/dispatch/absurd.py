"""
The Absurd Dispatch: CV3's optional durable Dispatch implementation over Absurd 0.4.0 —
hash-pinned, never forked [DR 2026-07-15 absurd-execution-substrate, D11].

Absurd sits entirely on the adapter side of the activity-invocation seam:
tasks, runs, claims, leases, and retries are operational state —
reconstructible machinery, never canonical net truth. The authority stays the
sole canonical writer: workers never touch ``impetus.semantic_events`` and
never author canonical time; ``collect()`` observes completed runs and the
authority's ``record_activity_completion`` stamps the acceptance
(``ActivityCompleted`` — authority time). If Absurd state were lost after a
worker's ``complete_run`` and before acceptance, the canonical outbox
(``ActivityRequested`` without a terminal activity fact) redispatches under
the same recovery identity — K4's lookup-first before re-invoke, at-least-once
by construction.

The D11 same-transaction shape lands on the DISPATCH side: over a join-mode
``PostgresHistoryStore`` connection (``autocommit=False``), the begin batch,
the ``absurd.spawn_task``, and the ``pg_notify`` doorbell all ride ONE
authority-held transaction — commit or vanish together, closing the
request-vs-publication crash window structurally (the ES-009 matrix's K1/K2
dissolve). The doorbell is adapter-side and inside the spawning transaction:
PostgreSQL delivers NOTIFY on commit, so there are no phantom wakes; workers
treat it purely as a wake hint and polling stays the safety net (NOTIFY is
lossy) — the native floor's own ratified discipline, composed with Absurd
untouched.

Schema pinning is the harness practice made a library obligation: the exact
release schema is vendored verbatim (``petrus/motus/dispatch/absurd_schema``), its sha256
re-verified at every apply, and any already-provisioned database must speak
exactly the pinned version — a re-pin is a deliberate act that re-runs the
ES-009 matrix, never a drive-by.

``petrus.engine.absurd.create_engine`` and ``load_engine`` are the Absurd
composition's construction doors. They acquire the PostgreSQL writer fence
before loading History, compose the joined store and this Dispatch, and return
the provider-neutral ``Engine``.
The Engine privately owns both dedicated connections and their one transaction
fate; a writing-door failure rolls back and poisons the whole composition, and
the coherent continuation is a fresh ``petrus.engine.absurd.load_engine``.
"""

from __future__ import annotations

# Python imports
import hashlib
import json
import os
import re
import time
import uuid
from collections.abc import Mapping, Sequence
from datetime import timedelta
from importlib import resources
from typing import Any, cast

# Pip imports — the optional extra, refused loud by name when absent.
try:
    import absurd_sdk  # noqa: F401 -- validate the complete optional extra
    import psycopg
    from psycopg import sql
    from psycopg.types.json import Jsonb
except ImportError as _psycopg_missing:
    raise ImportError(
        "the Absurd Dispatch needs psycopg, which ships in the optional 'absurd' extra: "
        "install petrus[absurd] (e.g. `uv add 'petrus[absurd]'` or `pip install 'petrus[absurd]'`)"
    ) from _psycopg_missing

# Internal imports
import petrus.telemetry as telemetry
from petrus.motus.activity import (
    ActivityFailure,
    ActivityInvocation,
    ExecutionPolicy,
    _OMITTED,
    snapshot_heartbeat_details,
)
from petrus.motus.dispatch import ActivityAttempt

# The D11 triple pin — release tag, its commit, and the sha256 of the release's
# sql/absurd.sql, exactly as the ES-009 matrix recorded them
# (absurd-full-matrix/run-proof.sh). The vendored copy in petrus/motus/dispatch/absurd_schema
# is verified against ABSURD_SQL_SHA256 at every apply: the schema is never
# forked, so any edit breaks the hash loud, and a version re-pin re-verifies
# the new triple and reruns the matrix — a deliberate act.
ABSURD_VERSION = "0.4.0"
ABSURD_COMMIT = "05282a40c8dddc378acdc6933adc4c221583808a"
ABSURD_SQL_SHA256 = "c2ed3a301aa2a4782257843e514e8057c3049de5998ea8dc632a1a159464b51c"

# The two doorbells, one channel each: dispatch (authority -> workers, rung
# inside the spawning transaction, payload = the queue) and results (workers
# -> authority, rung after the worker's terminal commit, payload = the queue).
# Both are wake hints only; polling stays the safety net on both sides.
DISPATCH_CHANNEL = "impetus_dispatch"
RESULTS_CHANNEL = "impetus_results"
DETAILS_CHECKPOINT = "__impetus_latest_activity_details_v1"

# Configured queue targets use a deliberately conservative operator-facing
# vocabulary. Provider-discovered names are not revalidated here: Absurd
# permits every non-empty name up to 57 bytes, and every use of such a name in
# SQL is quoted with ``sql.Identifier`` below.
_QUEUE_NAME = re.compile(r"^[a-z][a-z0-9_]{0,56}$")

# The operational shadow of the substrate seam [ES-020]: one emit per
# dispatched invocation and per non-empty collect — the two moments net work
# crosses into and out of the execution substrate. An empty collect poll
# emits nothing: nothing crossed.
log = telemetry.get_logger("impetus")


def validate_queue(queue: str) -> str:
    """Validate one operational queue name before it becomes a table suffix."""
    if not isinstance(queue, str) or not _QUEUE_NAME.match(queue):
        raise ValueError(
            f"queue {queue!r} is invalid: a queue name must match {_QUEUE_NAME.pattern} "
            f"(it becomes the t_/r_/c_/e_/w_ table suffix)"
        )
    return queue


def encode_invocation(invocation: ActivityInvocation) -> dict:
    """
    The invocation's wire spelling for the task payload — operational state,
    reconstructible from the canonical ``ActivityRequested`` and spelled
    field-for-field like it (including the resolved heartbeat timeout): the worker's
    whole world crosses the queue whole [convention 67].
    """
    return {
        "activity": invocation.activity,
        "input": invocation.input,
        "policy": {
            "attempts": invocation.policy.attempts,
            "heartbeat_timeout": invocation.policy.heartbeat_timeout,
            "initial_interval": invocation.policy.initial_interval,
            "coefficient": invocation.policy.coefficient,
            "max_interval": invocation.policy.max_interval,
            "jitter": invocation.policy.jitter,
            "start_to_close": invocation.policy.start_to_close,
            "schedule_to_close": invocation.policy.schedule_to_close,
        },
        "correlation": invocation.correlation,
        "idempotency": invocation.idempotency,
    }


def _canonical_json(value: object) -> str:
    """Deterministic type-sensitive JSON comparison spelling for decoded jsonb."""
    return json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


# The exact wire shape decode_invocation admits — nothing more, nothing less:
# a worker executes only payloads this module's encoder could have written.
_WIRE_FIELDS = frozenset({"activity", "input", "policy", "correlation", "idempotency"})


def decode_invocation(payload: Mapping) -> ActivityInvocation:
    """
    Rebuild the ``ActivityInvocation`` a worker executes from its task
    payload — the strict inverse of ``encode_invocation``: exactly the six
    wire fields, ``policy`` exactly the current resolved policy, identities nullable non-empty strings (the
    value type's own door enforces those). Anything else — a missing or
    extra field, a widened policy this pin does not know, a foreign shape —
    is refused loud: a worker never guesses at an instruction.
    """
    rejection = "task payload does not decode as an activity invocation"
    if not isinstance(payload, Mapping) or set(payload) != _WIRE_FIELDS:
        raise ValueError(f"{rejection}: expected exactly the fields {sorted(_WIRE_FIELDS)}, got {payload!r}")
    policy = payload["policy"]
    if (
        not isinstance(policy, Mapping)
        or set(policy)
        not in (
            {"attempts", "heartbeat_timeout"},
            {
                "attempts",
                "heartbeat_timeout",
                "initial_interval",
                "coefficient",
                "max_interval",
                "jitter",
                "start_to_close",
                "schedule_to_close",
            },
        )
        or isinstance(policy["attempts"], bool)
        or not isinstance(policy["attempts"], int)
        or isinstance(policy["heartbeat_timeout"], bool)
        or not isinstance(policy["heartbeat_timeout"], int)
    ):
        raise ValueError(
            f"{rejection}: policy must be exactly {{'attempts': int, 'heartbeat_timeout': int}}, got {policy!r}"
        )
    try:
        return ActivityInvocation(
            payload["activity"],
            input=payload["input"],
            policy=ExecutionPolicy(**policy),
            correlation=payload["correlation"],
            idempotency=payload["idempotency"],
        )
    except ValueError as error:
        raise ValueError(f"{rejection}: {error}") from error


class GuardedDispatch:
    """Exclusive Worker-side door over Absurd custody, fenced by the active run lease."""

    def __init__(self, connection, *, claimant: str | None = None):
        if connection.autocommit:
            raise ValueError("GuardedDispatch requires autocommit=False for atomic guarded operations")
        self._connection = connection
        self.claimant = claimant or str(uuid.uuid4())

    def claim(self, queue: str, *, timeout: int) -> tuple[dict, object] | None:
        validate_queue(queue)
        try:
            cursor = self._connection.execute(
                "SELECT * FROM absurd.claim_task(%s, %s, %s, 1)", (queue, self.claimant, timeout)
            )
            row = cursor.fetchone()
            if row is None:
                self._connection.commit()
                return None
            task = dict(zip([column.name for column in cursor.description], row, strict=True))
            policy_timeout = decode_invocation(task["params"]).policy.heartbeat_timeout
            self._connection.execute("SELECT absurd.extend_claim(%s, %s, %s)", (queue, task["run_id"], policy_timeout))
            details = self._connection.execute(
                "SELECT state FROM absurd.get_task_checkpoint_state(%s, %s, %s)",
                (queue, task["task_id"], DETAILS_CHECKPOINT),
            ).fetchone()
            self._connection.commit()
            return task, (details[0] if details else None)
        except BaseException:
            self._connection.rollback()
            raise

    def heartbeat(self, queue: str, *, task_id, run_id, timeout: int, details: object = _OMITTED) -> object:
        supplied = details is not _OMITTED
        snapshot = snapshot_heartbeat_details(details) if supplied else None
        try:
            self._guard(queue, task_id=task_id, run_id=run_id)
            if supplied:
                self._connection.execute(
                    "SELECT absurd.set_task_checkpoint_state(%s, %s, %s, %s, %s, %s)",
                    (queue, task_id, DETAILS_CHECKPOINT, Jsonb(snapshot), run_id, timeout),
                )
            else:
                self._connection.execute("SELECT absurd.extend_claim(%s, %s, %s)", (queue, run_id, timeout))
            accepted = snapshot if supplied else self.latest_details(queue, task_id)
            self._connection.commit()
            return accepted
        except BaseException:
            self._connection.rollback()
            raise

    def terminal(
        self,
        queue: str,
        *,
        task_id,
        run_id,
        result: object = _OMITTED,
        error: Exception | ActivityFailure | None = None,
    ) -> None:
        if error is None and result is _OMITTED:
            raise ValueError("a successful terminal report requires a result")
        failure = None
        if error is not None:
            failure = (
                error
                if isinstance(error, ActivityFailure)
                else ActivityFailure(str(error), kind=type(error).__name__, retryable=True)
            )
        reason = (
            None
            if failure is None
            else {
                "petrus_failure": 1,
                "name": failure.kind,
                "message": failure.error,
                "details": failure.details,
                "retryable": failure.retryable,
                "retry_after": failure.retry_after,
            }
        )
        try:
            if self._guard_terminal(
                queue, task_id=task_id, run_id=run_id, result=result if failure is None else _OMITTED, reason=reason
            ):
                self._connection.commit()
                return
            if error is None:
                self._connection.execute("SELECT absurd.complete_run(%s, %s, %s)", (queue, run_id, Jsonb(result)))
            else:
                assert failure is not None and reason is not None
                run = self._connection.execute(
                    "SELECT attempt, absurd.current_time() FROM absurd.{} WHERE run_id=%s".format(f"r_{queue}"),
                    (run_id,),
                ).fetchone()
                if run is None:
                    raise RuntimeError("stale Activity Attempt: run disappeared while guarded")
                attempt, provider_now = run
                params = self._connection.execute(
                    "SELECT t.params FROM absurd.{} t JOIN absurd.{} r USING(task_id) WHERE r.run_id=%s".format(
                        f"t_{queue}", f"r_{queue}"
                    ),
                    (run_id,),
                ).fetchone()[0]
                policy = decode_invocation(params).policy
                delay = max(policy.retry_policy.delay(attempt), failure.retry_after or 0)
                retry_at = provider_now + timedelta(seconds=delay) if failure.retryable else None
                if not failure.retryable:
                    self._connection.execute(
                        "UPDATE absurd.{} t SET max_attempts=%s FROM absurd.{} r "
                        "WHERE r.run_id=%s AND t.task_id=r.task_id".format(f"t_{queue}", f"r_{queue}"),
                        (attempt, run_id),
                    )
                self._connection.execute(
                    "SELECT absurd.fail_run(%s, %s, %s, %s)", (queue, run_id, Jsonb(reason), retry_at)
                )
            self._connection.commit()
        except BaseException:
            self._connection.rollback()
            raise

    def _guard_terminal(self, queue: str, *, task_id, run_id, result: object, reason: object) -> bool:
        validate_queue(queue)
        query = sql.SQL(
            "SELECT r.task_id,r.state,r.claimed_by,r.claim_expires_at,"
            "r.claim_expires_at > absurd.current_time(),r.result,r.failure_reason,t.state FROM absurd.{} r "
            "JOIN absurd.{} t USING(task_id) WHERE r.run_id=%s FOR UPDATE OF r"
        ).format(sql.Identifier(f"r_{queue}"), sql.Identifier(f"t_{queue}"))
        row = self._connection.execute(query, (run_id,)).fetchone()
        if row is None or str(row[0]) != str(task_id):
            raise RuntimeError("stale Activity Attempt: task/run identity is not current")
        _, state, claimant, deadline, unexpired, stored_result, stored_failure, task_state = row
        if claimant != self.claimant:
            raise RuntimeError("stale Activity Attempt: claimant, state, or lease deadline is no longer current")
        if state == "completed":
            if task_state != "completed":
                raise RuntimeError("stale Activity Attempt: claimant, state, or lease deadline is no longer current")
            if result is not _OMITTED and _canonical_json(stored_result) == _canonical_json(result):
                return True
            raise ValueError("conflicting terminal report")
        if state == "failed":
            if not isinstance(stored_failure, Mapping) or stored_failure.get("petrus_failure") != 1:
                raise RuntimeError("stale Activity Attempt: claimant, state, or lease deadline is no longer current")
            if reason is not None and _canonical_json(stored_failure) == _canonical_json(reason):
                return True
            raise ValueError("conflicting terminal report")
        if state != "running" or deadline is None or not unexpired:
            raise RuntimeError("stale Activity Attempt: claimant, state, or lease deadline is no longer current")
        return False

    def latest_details(self, queue: str, task_id) -> object:
        row = self._connection.execute(
            "SELECT state FROM absurd.get_task_checkpoint_state(%s, %s, %s)",
            (queue, task_id, DETAILS_CHECKPOINT),
        ).fetchone()
        return row[0] if row else None

    def _guard(self, queue: str, *, task_id, run_id) -> None:
        validate_queue(queue)
        query = sql.SQL(
            "SELECT task_id, state, claimed_by, claim_expires_at, "
            "claim_expires_at > absurd.current_time() FROM absurd.{} "
            "WHERE run_id = %s FOR UPDATE"
        ).format(sql.Identifier(f"r_{queue}"))
        row = self._connection.execute(query, (run_id,)).fetchone()
        if row is None or str(row[0]) != str(task_id):
            raise RuntimeError("stale Activity Attempt: task/run identity is not current")
        _, state, claimant, deadline, unexpired = row
        if state != "running" or claimant != self.claimant or deadline is None or not unexpired:
            raise RuntimeError("stale Activity Attempt: claimant, state, or lease deadline is no longer current")


class _ReconnectableGuardedDispatch:
    """Provider-local custody facade that reconnects one failed transport heartbeat."""

    def __init__(self, dsn: str, connection, *, claimant: str):
        self._dsn = dsn
        self.connection = connection
        self.claimant = claimant
        self._dispatch = GuardedDispatch(connection, claimant=claimant)

    def claim(self, queue: str, *, timeout: int):
        return self._dispatch.claim(queue, timeout=timeout)

    def heartbeat(self, queue: str, **operation):
        try:
            return self._dispatch.heartbeat(queue, **operation)
        except psycopg.OperationalError, psycopg.InterfaceError:
            if not (self.connection.closed or self.connection.broken):
                raise
            self._replace_connection()
            return self._dispatch.heartbeat(queue, **operation)

    def terminal(self, queue: str, **operation) -> None:
        self._dispatch.terminal(queue, **operation)

    def close(self) -> None:
        self.connection.close()

    def _replace_connection(self) -> None:
        self.connection.close()
        connection = psycopg.connect(self._dsn, autocommit=False)
        try:
            connection.execute(f"LISTEN {DISPATCH_CHANNEL}")
            connection.commit()
            dispatch = GuardedDispatch(connection, claimant=self.claimant)
        except BaseException:
            connection.close()
            raise
        self.connection = connection
        self._dispatch = dispatch


class AbsurdWorkerDispatch:
    """Worker-facing Absurd adapter; PostgreSQL values never cross this boundary."""

    def __init__(
        self,
        dsn: str,
        *,
        queues: Sequence[str] = ("default",),
        worker_id: str | None = None,
        claim_timeout: int = 30,
    ):
        self._dsn = dsn
        self.queues = tuple(dict.fromkeys(validate_queue(queue) for queue in queues))
        if not self.queues:
            raise ValueError("Absurd Worker Dispatch requires at least one queue")
        self.claimant = f"{worker_id or f'worker-{os.getpid()}'}:{uuid.uuid4()}"
        self._claim_timeout = claim_timeout
        self.connection = psycopg.connect(dsn, autocommit=False)
        try:
            for queue in self.queues:
                self.connection.execute("SELECT absurd.create_queue(%s)", (queue,))
            self.connection.commit()
            self.connection.execute(f"LISTEN {DISPATCH_CHANNEL}")
            self.connection.commit()
            self._dispatch = _ReconnectableGuardedDispatch(dsn, self.connection, claimant=self.claimant)
        except BaseException:
            self.connection.close()
            raise

    def claim(self) -> ActivityAttempt | None:
        for queue in self.queues:
            delivery = self._dispatch.claim(queue, timeout=self._claim_timeout)
            if delivery is None:
                continue
            task, details = delivery
            return ActivityAttempt(
                str(task["task_id"]),
                str(task["run_id"]),
                self.claimant,
                queue,
                decode_invocation(task["params"]),
                details,
            )
        return None

    def heartbeat(self, attempt: ActivityAttempt, *, details: object = _OMITTED) -> object:
        operation = {
            "task_id": attempt.attempt_id,
            "run_id": attempt.epoch,
            "timeout": attempt.invocation.policy.heartbeat_timeout,
            "details": details,
        }
        accepted = self._dispatch.heartbeat(attempt.queue, **operation)
        self.connection = self._dispatch.connection
        return accepted

    def complete(self, attempt: ActivityAttempt, result: object) -> None:
        self._dispatch.terminal(attempt.queue, task_id=attempt.attempt_id, run_id=attempt.epoch, result=result)
        self._notify(attempt.queue)

    def fail(self, attempt: ActivityAttempt, error: str | Exception | ActivityFailure) -> None:
        failure = error if isinstance(error, (Exception, ActivityFailure)) else RuntimeError(error)
        self._dispatch.terminal(attempt.queue, task_id=attempt.attempt_id, run_id=attempt.epoch, error=failure)
        self._notify(attempt.queue)

    def wait(self, timeout: float) -> bool:
        for _ in self.connection.notifies(timeout=timeout, stop_after=1):
            return True
        return False

    def close(self) -> None:
        self._dispatch.close()

    def _notify(self, queue: str) -> None:
        self.connection.execute("SELECT pg_notify(%s, %s)", (RESULTS_CHANNEL, queue))
        self.connection.commit()


def _pinned_schema() -> str:
    """The vendored release schema, sha256-verified against the pin on every read — the RAW BYTES, exactly how the pin was computed (an encoding round trip could mask a byte-level edit); a drifted or edited copy is a hard stop, never applied."""
    vendored = (
        resources.files("petrus.motus.dispatch").joinpath(f"absurd_schema/absurd-{ABSURD_VERSION}.sql").read_bytes()
    )
    digest = hashlib.sha256(vendored).hexdigest()
    if digest != ABSURD_SQL_SHA256:
        raise RuntimeError(
            f"vendored absurd-{ABSURD_VERSION}.sql hash mismatch: expected {ABSURD_SQL_SHA256}, found {digest} — "
            f"the pinned schema is never forked; restore the verbatim release file or re-pin deliberately "
            f"(re-verifying the triple pin and re-running the ES-009 matrix)"
        )
    return vendored.decode()


def ensure_absurd_schema(connection) -> None:
    """
    Provision the pinned Absurd schema, idempotently by version: a database
    already speaking ``absurd`` must report exactly the pinned
    ``get_schema_version()`` (anything else is a foreign or drifted install,
    refused loud — a re-pin is a deliberate act); an unprovisioned database
    gets the vendored release script, applied as one multi-statement unit
    (atomic: a failed apply leaves nothing behind). The vendored file's hash
    is re-verified on EVERY call, the already-provisioned path included — a
    tampered copy is refused before this function touches or vouches for
    anything, never only on the apply path. Co-resident with the Impetus
    canonical schema in one database — the ES-009 co-residence shape
    ``petrus.impetus.history_store.postgres.ensure_schema`` provisions beside this.
    """
    pinned = _pinned_schema()
    present = connection.execute("SELECT 1 FROM pg_namespace WHERE nspname = 'absurd'").fetchone()
    if present:
        try:
            version = connection.execute("SELECT absurd.get_schema_version()").fetchone()[0]
        except psycopg.Error as error:
            raise RuntimeError(
                f"an 'absurd' schema exists but does not answer absurd.get_schema_version(): not the pinned "
                f"engine — refusing to touch it ({error})"
            ) from error
        if version != ABSURD_VERSION:
            raise RuntimeError(
                f"the database speaks absurd schema version {version!r}, but this adapter is pinned to "
                f"{ABSURD_VERSION!r}: a re-pin is a deliberate act [D11] — never an implicit upgrade at boot"
            )
        return
    connection.execute(pinned)


def _spell_failure(reason: object) -> str:
    """One error string from Absurd's ``failure_reason`` jsonb — ``"name: message"`` when the SDK shape is there, the raw JSON otherwise (never silently empty)."""
    if isinstance(reason, Mapping) and "name" in reason:
        message = reason.get("message")
        # Membership above establishes this dynamic JSON mapping's key.
        return f"{reason['name']}: {message}" if message else str(reason["name"])  # ty: ignore[invalid-argument-type]
    return json.dumps(reason)


def _decode_failure(reason: object) -> ActivityFailure:
    if isinstance(reason, Mapping) and reason.get("petrus_failure") == 1:
        return ActivityFailure(
            cast(Any, reason.get("message")),
            cast(Any, reason.get("name")),
            reason.get("details"),
            cast(Any, reason.get("retryable")),
            cast(Any, reason.get("retry_after")),
        )
    return ActivityFailure(_spell_failure(reason))


class AbsurdDispatch:
    """
    The ``Dispatch`` over Absurd: ``dispatch`` spawns the invocation's
    task on the caller's ``connection`` — in join mode (``autocommit=False``)
    it rides the authority's OPEN transaction beside the begin batch, and
    rings the dispatch doorbell inside it (delivered on commit) — and
    ``collect`` drains the terminal outcomes of dispatched occurrences from
    Absurd state, in completion order (the substrate's recorded terminal
    instants). The spawn is keyed idempotently on the occurrence —
    ``"{instance}:occurrence-{id}"``, the recovery identity — so an
    at-least-once redispatch never double-enqueues, and the spawn-by-key IS
    the K4 substrate lookup: a live or completed task is returned untouched
    (``created=false`` — the completed one surfaces from the next
    ``collect``), a definitely-absent one is respawned under the SAME key,
    and ambiguity never invents a process fact. (PROVIDER-level
    reconciliation — looking the external effect up by the invocation's
    idempotency identity before re-invoking — is the future activity
    protocol's, not this adapter's.)

    Policy is enforced at the substrate, mapped honestly at dispatch:
    ``invocation.policy.attempts`` becomes the task's ``max_attempts`` with
    ``retry_strategy {"kind": "none"}`` (an exhausted retry is terminal, a
    surviving failure retries immediately); a terminally failed task surfaces
    from ``collect`` as an ``ActivityFailure``. Absurd's accounting counts
    DELIVERIES: a lease swept after a worker crash (``$ClaimTimeout``) spends
    an attempt exactly like an activity exception — an activity that must
    survive N crashes declares the headroom in its policy.

    ``wait_for_results`` is the coordinator's ``Wait`` consumer: LISTEN on
    the results doorbell (over the separate autocommit ``listen`` connection
    — the joined transaction must never own the notification wire) with the
    poll interval as the lossy-NOTIFY safety net.

    The adapter is derived over the caller's connection exactly like the
    history and the instance: a rollback retracts spawns and queue creations
    its session state already advanced on, so it shares the whole-runtime
    rollback fate [convention 71] — the provider-constructed ``Engine``
    enforces that.
    """

    def __init__(
        self,
        connection,
        *,
        instance: str,
        listen=None,
        poll_interval: float = 0.25,
        default_queue: str = "default",
        activity_queues: Mapping[str, str] | None = None,
    ):
        if not isinstance(instance, str) or not instance:
            raise ValueError(f"AbsurdDispatch requires a non-empty string instance id, got {instance!r}")
        if listen is not None and not listen.autocommit:
            raise ValueError(
                "the listen connection must be autocommit: PostgreSQL delivers notifications between "
                "transactions, and the joined authority transaction must never own the notification wire"
            )
        self._connection = connection
        self._instance = instance
        self._listen = listen
        self._poll_interval = poll_interval
        self._default_queue = validate_queue(default_queue)
        self._activity_queues = {activity: validate_queue(queue) for activity, queue in (activity_queues or {}).items()}
        if any(not isinstance(activity, str) or not activity for activity in self._activity_queues):
            raise ValueError("activity queue overrides require non-empty string Activity names")
        self._tasks: dict[int, tuple[str, str]] = {}  # occurrence -> (queue, task id), this session's dispatches
        self._collected: set[int] = set()
        self._known_queues: set[str] = set()
        self._listening = False

    def queue_for(self, activity_name: str) -> str:
        """Resolve an exact Activity override, otherwise this Engine's default."""
        if not isinstance(activity_name, str) or not activity_name:
            raise ValueError("queue routing requires a non-empty Activity name")
        return self._activity_queues.get(activity_name, self._default_queue)

    def dispatch(self, occurrence: int, invocation: ActivityInvocation) -> None:
        """
        Durably enqueue one invocation, idempotently keyed by the occurrence
        (`"{instance}:occurrence-{id}"`, the recovery identity), and ring the
        dispatch doorbell — all inside the caller's open transaction (join
        mode): the begin batch, the spawn, and the bell commit or vanish
        together [D11]. The keyed spawn doubles as K4's lookup-first at the
        substrate: an existing task (live or already terminal) is returned
        untouched, a definitely-absent one is (re)created under the same
        key — so the coordinator's reconcile leg redispatches through this
        one door with nothing invented.
        """
        if self._connection.autocommit:
            raise RuntimeError(
                "Absurd dispatch publication cannot run in autocommit mode; it requires a joined transaction "
                "(autocommit=False): occurrence "
                "discovery, custody reconciliation, spawn, and notification must commit or roll back together"
            )
        if invocation.policy.start_to_close is not None or invocation.policy.schedule_to_close is not None:
            raise ValueError(
                "AbsurdDispatch does not support start_to_close or schedule_to_close with the pinned provider; "
                "exact deadlines require cancellation tombstones and are therefore refused"
            )
        queue = self.queue_for(invocation.activity)
        existing = self._recover_custody(occurrence, queue, invocation)
        if existing is not None:
            self._tasks[occurrence] = existing
            return
        if queue not in self._known_queues:
            # Idempotent per Absurd (insert-on-conflict + IF NOT EXISTS DDL);
            # cached per session so steady-state dispatch skips the DDL.
            self._connection.execute("SELECT absurd.create_queue(%s)", (queue,))
            self._known_queues.add(queue)
        options = {
            "idempotency_key": f"{self._instance}:occurrence-{occurrence}",
            "max_attempts": invocation.policy.attempts,
            # GuardedDispatch computes the complete Petrus retry policy from
            # the canonical params against absurd.current_time().
            "retry_strategy": {"kind": "none"},
        }
        (task_id, _run_id, _attempt, _created) = self._connection.execute(
            "SELECT task_id, run_id, attempt, created FROM absurd.spawn_task(%s, %s, %s, %s)",
            (queue, invocation.activity, Jsonb(encode_invocation(invocation)), Jsonb(options)),
        ).fetchone()
        self._tasks[occurrence] = (queue, str(task_id))
        self._connection.execute("SELECT pg_notify(%s, %s)", (DISPATCH_CHANNEL, queue))
        log.emit(
            "absurd_dispatched",
            occurrence=occurrence,
            activity=invocation.activity,
            queue=queue,
            task=str(task_id),
        )

    # Complexity exception: reviewed as one transactional custody state machine.
    def _recover_custody(  # noqa: C901
        self, occurrence: int, target: str, invocation: ActivityInvocation
    ) -> tuple[str, str] | None:
        """Find and, when safe, atomically transfer one provider custody to the current route."""
        key = f"{self._instance}:occurrence-{occurrence}"
        # One deterministic transaction-scoped mutex for this canonical
        # occurrence. Production Engine construction always supplies a joined
        # transaction, so this is held from discovery through any cancel,
        # replacement spawn, and notification (commit releases it).
        self._connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (key,))
        queues = [row[0] for row in self._connection.execute("SELECT queue_name FROM absurd.list_queues()")]
        found: list[tuple[str, str, str, object, str | None, str | None]] = []
        for queue in queues:
            query = sql.SQL(
                "SELECT task_id::text, state, first_started_at, last_attempt_run::text, "
                "(SELECT state FROM absurd.{} r WHERE r.run_id = t.last_attempt_run) "
                "FROM absurd.{} t WHERE idempotency_key = %s"
            ).format(sql.Identifier(f"r_{queue}"), sql.Identifier(f"t_{queue}"))
            found.extend((queue, *row) for row in self._connection.execute(query, (key,)).fetchall())

        live = [row for row in found if row[2] != "cancelled"]
        target_tombstones = [row for row in found if row[0] == target and row[2] == "cancelled"]
        if target_tombstones and not live:
            raise RuntimeError(
                f"cannot establish Absurd custody for {key}: target queue {target!r} has a cancelled tombstone"
            )
        if not live:
            return None
        if len(live) != 1:
            raise RuntimeError(
                f"ambiguous Absurd custody for {key}: found {len(live)} live tasks across provider queues"
            )
        queue, task_id, task_state, first_started, run_id, run_state = live[0]
        identity = sql.SQL("SELECT task_name,params FROM absurd.{} WHERE task_id=%s").format(
            sql.Identifier(f"t_{queue}")
        )
        task_name, params = self._connection.execute(identity, (task_id,)).fetchone()
        try:
            recovered_params = encode_invocation(decode_invocation(params))
        except ValueError as error:
            raise ValueError(f"Absurd publication conflict for {key}: stored invocation params are invalid") from error
        if task_name != invocation.activity or _canonical_json(recovered_params) != _canonical_json(
            encode_invocation(invocation)
        ):
            raise ValueError(f"Absurd publication conflict for {key}: activity or invocation params differ")
        # Terminal custody wins over routing history. In an A -> B -> A
        # sequence A necessarily contains the transfer tombstone; if B has
        # since finished, that sole durable outcome must be collected rather
        # than hidden by the target tombstone.
        if task_state in {"completed", "failed"}:
            if run_id is None or run_state != task_state:
                raise RuntimeError(
                    f"cannot reconcile terminal Absurd custody for {key}: task/run terminal state is invalid "
                    f"(task={task_state!r}, last_attempt_run={run_id!r}, run={run_state!r})"
                )
            return (queue, task_id)
        if target_tombstones:
            raise RuntimeError(
                f"cannot establish Absurd custody for {key}: target queue {target!r} has a cancelled tombstone"
            )
        if queue == target:
            return (queue, task_id)
        if run_id is None:
            raise RuntimeError(f"cannot transfer Absurd custody for {key}: task has no active run")
        try:
            run_lock = sql.SQL("SELECT state FROM absurd.{} WHERE run_id = %s FOR UPDATE NOWAIT").format(
                sql.Identifier(f"r_{queue}")
            )
            locked_run = self._connection.execute(run_lock, (run_id,)).fetchone()
            task_lock = sql.SQL(
                "SELECT state, first_started_at, last_attempt_run::text FROM absurd.{} "
                "WHERE task_id = %s FOR UPDATE NOWAIT"
            ).format(sql.Identifier(f"t_{queue}"))
            locked_task = self._connection.execute(task_lock, (task_id,)).fetchone()
        except psycopg.errors.LockNotAvailable as error:
            raise RuntimeError(f"cannot transfer Absurd custody for {key}: custody is currently locked") from error
        if locked_run != ("pending",) or locked_task != ("pending", None, run_id):
            raise RuntimeError(
                f"cannot transfer Absurd custody for {key}: only one pending/pending never-started task may move "
                f"(run={locked_run!r}, task={locked_task!r})"
            )
        self._connection.execute("SELECT absurd.cancel_task(%s, %s)", (queue, task_id))
        return None

    def collect(self) -> tuple[tuple[int, object], ...]:
        """
        The terminal outcomes of dispatched, not-yet-collected occurrences,
        in completion order (the substrate's recorded terminal instants —
        ``completed_at``/``failed_at`` of the last attempt's run): a
        completed task yields its ``complete_run`` payload verbatim; a
        terminally failed one (policy exhausted) yields an
        ``ActivityFailure`` spelling the last failure reason. A cancelled
        task is refused loud — cancellation is a custody-transfer tombstone,
        never a terminal activity outcome to fold.
        """
        pending: dict[str, dict[str, int]] = {}
        for occurrence, (queue, task_id) in self._tasks.items():
            if occurrence not in self._collected:
                pending.setdefault(queue, {})[task_id] = occurrence
        arrived: list[tuple[object, int, object]] = []
        for queue, ids in sorted(pending.items()):
            query = sql.SQL(
                "SELECT t.task_id::text, t.state, t.completed_payload, r.failure_reason, "
                "coalesce(r.completed_at, r.failed_at, r.created_at) FROM absurd.{} t "
                "LEFT JOIN absurd.{} r ON r.run_id = t.last_attempt_run "
                "WHERE t.task_id = ANY(%s::uuid[]) AND t.state IN ('completed', 'failed', 'cancelled')"
            ).format(sql.Identifier(f"t_{queue}"), sql.Identifier(f"r_{queue}"))
            rows = self._connection.execute(query, (list(ids),)).fetchall()
            for task_id, state, payload, failure, terminal_at in rows:
                occurrence = ids[task_id]
                if state == "cancelled":
                    raise RuntimeError(
                        f"task {task_id} (occurrence {occurrence}) is cancelled in Absurd: a custody tombstone "
                        f"is not an activity outcome, refusing to fold a guess"
                    )
                outcome = payload if state == "completed" else _decode_failure(failure)
                arrived.append((terminal_at, occurrence, outcome))
        arrived.sort(key=lambda item: (item[0], item[1]))
        self._collected.update(occurrence for _, occurrence, _ in arrived)
        if arrived:
            log.emit(
                "absurd_collected",
                results=len(arrived),
                failures=sum(1 for _, _, outcome in arrived if isinstance(outcome, ActivityFailure)),
            )
        return tuple((occurrence, outcome) for _, occurrence, outcome in arrived)

    def wait_for_results(self, timeout: float) -> bool:
        """
        Block until a dispatched occurrence has a terminal outcome to
        collect, or ``timeout`` elapses — the driver's ``Wait`` consumer
        (drive -> waiting -> wait_for_results -> drive again). Wakes on the
        results doorbell when a ``listen`` connection was supplied, and polls
        every ``poll_interval`` regardless: NOTIFY is lossy, so the poll is
        the safety net, never the doorbell the guarantee. Returns whether
        results are ready (a timeout is an honest False, not an error).
        """
        deadline = time.monotonic() + timeout
        if self._listen is not None and not self._listening:
            self._listen.execute(f"LISTEN {RESULTS_CHANNEL}")
            self._listening = True
        while True:
            if self._terminal_ready():
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            interval = min(self._poll_interval, remaining)
            if self._listen is not None:
                # Wake hint or poll tick, whichever first; the loop re-probes.
                for _ in self._listen.notifies(timeout=interval, stop_after=1):
                    break
            else:
                time.sleep(interval)

    def _terminal_ready(self) -> bool:
        """Whether any dispatched, uncollected occurrence already has a terminal outcome — the poll probe, on the listen connection when there is one (the joined transaction stays untouched while a driver waits)."""
        probe = self._listen if self._listen is not None else self._connection
        pending: dict[str, list[str]] = {}
        for occurrence, (queue, task_id) in self._tasks.items():
            if occurrence not in self._collected:
                pending.setdefault(queue, []).append(task_id)
        for queue, ids in pending.items():
            query = sql.SQL(
                "SELECT 1 FROM absurd.{} WHERE task_id = ANY(%s::uuid[]) "
                "AND state IN ('completed', 'failed', 'cancelled') LIMIT 1"
            ).format(sql.Identifier(f"t_{queue}"))
            row = probe.execute(query, (ids,)).fetchone()
            if row is not None:
                return True
        return False
