"""
Backend behavior tests for the PostgreSQL canonical history.

``PostgresHistoryStore`` (CV3.DS3) is the transactional sibling of the JSONL
backend: the ``impetus.semantic_events`` shape the ES-009 native floor proved,
productized minimally behind the one ``InMemoryHistoryStore`` contract. What this
module pins is exactly what JSONL cannot promise and the shared
backend-contract suite (``test_history_backends.py``) therefore cannot carry:

- **Transactional batches** — a batch commits whole or not at all; the
  torn-commit shape replay refuses on JSONL is impossible here.
- **Verify-on-conflict acceptance** — the K6 discipline in DDL + code: an
  insert that conflicts (on the writer-derived event identity, or on the
  one-terminal partial unique indexes) re-reads the stored row and verifies
  value equality — identical is acknowledged idempotently, different fails
  loud naming the event.
- **Caller-provided connection posture** (the D11 transaction-mode shape) —
  on an autocommit connection the backend owns a transaction per batch; on a
  caller-held transaction the appends JOIN it, invisible until the caller
  commits, gone on rollback (DS4's spawn+append atomicity).
"""

from __future__ import annotations

# Python imports
import json
import threading
from uuid import uuid4

# Pip imports
import psycopg
import pytest

# Internal imports
from petrus.impetus.history import (
    FiringBegun,
    FiringCompleted,
    FiringFailed,
    TokensConsumed,
    TokensInitialized,
    TokensProduced,
)
from petrus.impetus.history.codec import encode_record
from petrus.impetus.history_store.postgres import (
    PostgresHistoryStore,
    ensure_schema,
)
from petrus.impetus.petrinet import NetPath, Token

PLACE, TRANSITION = NetPath("p"), NetPath("t")


@pytest.fixture
def instance_id():
    return f"pg-only-{uuid4()}"


def _rows(connection, instance_id):
    return connection.execute(
        "SELECT event_id, record_type, occurrence, payload FROM impetus.semantic_events"
        " WHERE net_instance_id = %s ORDER BY sequence",
        (instance_id,),
    ).fetchall()


class TestEnsureSchema:
    def test_ensure_schema_is_idempotent_and_survives_existing_rows(self, pg_connection, instance_id):
        # pg_connection already ran it once; a second and third pass are
        # no-ops, rows intact.
        ensure_schema(pg_connection)
        PostgresHistoryStore(pg_connection, instance=instance_id).append(
            TokensInitialized(PLACE, (Token.black(),), instant=0)
        )
        ensure_schema(pg_connection)
        assert len(PostgresHistoryStore(pg_connection, instance=instance_id)) == 1

    def test_an_unprovisioned_database_fails_loud_naming_ensure_schema(self, postgres_dsn, instance_id):
        # Serial execution only (no xdist): this test drops and re-creates the
        # shared session schema, so a parallel sibling mid-append would lose it.
        with psycopg.connect(postgres_dsn, autocommit=True) as connection:
            try:
                connection.execute("DROP SCHEMA IF EXISTS impetus CASCADE")
                with pytest.raises(ValueError, match="ensure_schema"):
                    PostgresHistoryStore(connection, instance=instance_id)
            finally:
                ensure_schema(connection)  # restore for the connection-pooling siblings


class TestBackendShape:
    def test_the_instance_id_must_be_a_non_empty_string(self, pg_connection):
        for bad in ("", 7):
            with pytest.raises(ValueError, match="non-empty string instance"):
                PostgresHistoryStore(pg_connection, instance=bad)

    def test_one_table_holds_many_instances_apart(self, pg_connection):
        # The co-residence shape: histories are scoped by net_instance_id in
        # one namespaced table — the precondition for DS4's caller-transaction
        # joins against the same database.
        first, second = f"pg-only-{uuid4()}", f"pg-only-{uuid4()}"
        PostgresHistoryStore(pg_connection, instance=first).append(
            TokensInitialized(PLACE, (Token.black(),), instant=0)
        )
        PostgresHistoryStore(pg_connection, instance=second).append(FiringBegun(TRANSITION, occurrence=1, instant=1))

        assert PostgresHistoryStore(pg_connection, instance=first).records == (
            TokensInitialized(PLACE, (Token.black(),), instant=0),
        )
        assert PostgresHistoryStore(pg_connection, instance=second).records == (
            FiringBegun(TRANSITION, occurrence=1, instant=1),
        )

    def test_the_stored_row_speaks_the_ratified_payload(self, pg_connection, instance_id):
        # The durable spelling IS the ratified codec's JSON object — the one
        # serialization home — with the writer-derived event identity
        # ("{instance}:{position}") and the denormalized indexing columns
        # beside it.
        record = FiringCompleted(TRANSITION, occurrence=7, instant=3)
        PostgresHistoryStore(pg_connection, instance=instance_id).append(record)

        [(event_id, record_type, occurrence, payload)] = _rows(pg_connection, instance_id)
        assert event_id == f"{instance_id}:0"
        assert record_type == "FiringCompleted"
        assert occurrence == 7
        assert payload == encode_record(record)

    def test_schema_2_is_refused_through_the_actual_postgresql_history_load(self, pg_connection, instance_id):
        pg_connection.execute(
            "INSERT INTO impetus.semantic_events "
            "(event_id, net_instance_id, record_type, occurrence, payload) VALUES (%s, %s, %s, %s, %s::jsonb)",
            (
                f"{instance_id}:0",
                instance_id,
                "ActivityRequested",
                1,
                json.dumps(
                    {
                        "record": "ActivityRequested",
                        "schema": 2,
                        "transition": "t",
                        "activity": "old",
                        "capabilities": ["gpu"],
                        "occurrence": 1,
                        "instant": 0,
                    }
                ),
            ),
        )

        with pytest.raises(ValueError, match=r"'schema' is 2.*reads schemas \[4, 5\] only"):
            PostgresHistoryStore(pg_connection, instance=instance_id)


class TestTransactionalBatches:
    def test_a_batch_that_fails_mid_transaction_leaves_nothing(self, pg_connection, instance_id):
        # The DS1b debate's deferral, honored: kill the transaction mid-extend
        # (here: the batch's second record trips the one-terminal index with a
        # DIFFERENT payload) and NOTHING of the batch is visible — not even
        # the valid first record. The torn-commit shape is impossible.
        history = PostgresHistoryStore(pg_connection, instance=instance_id)
        history.extend(
            [FiringBegun(TRANSITION, occurrence=1, instant=1), FiringCompleted(TRANSITION, occurrence=1, instant=2)]
        )
        stale = PostgresHistoryStore(pg_connection, instance=instance_id)

        with pytest.raises(ValueError, match="terminal"):
            stale.extend(
                [
                    TokensProduced(PLACE, (Token.black(),), occurrence=1, instant=3),
                    FiringFailed(TRANSITION, "late diverging terminal", occurrence=1, instant=3),
                ]
            )

        assert len(stale) == 2  # memory never got ahead of the rolled-back batch
        assert PostgresHistoryStore(pg_connection, instance=instance_id).records == history.records


class TestVerifyOnConflict:
    def test_a_duplicate_identical_append_is_acknowledged_without_a_second_row(self, pg_connection, instance_id):
        # Two writers in lockstep (a lost acknowledgement, a racing twin):
        # the second identical append conflicts on the event identity,
        # re-reads, verifies value equality, and is acknowledged — idempotent,
        # no error, exactly one row.
        record = FiringCompleted(TRANSITION, occurrence=1, instant=2)
        first = PostgresHistoryStore(pg_connection, instance=instance_id)
        twin = PostgresHistoryStore(pg_connection, instance=instance_id)

        first.append(record)
        twin.append(record)

        assert len(_rows(pg_connection, instance_id)) == 1
        assert twin.records == first.records == (record,)

    def test_a_conflicting_different_append_fails_loud_naming_the_event(self, pg_connection, instance_id):
        # The same conflict with a DIFFERENT payload is never absorbed: the
        # stored fact wins, the writer is told which event and both sides.
        first = PostgresHistoryStore(pg_connection, instance=instance_id)
        twin = PostgresHistoryStore(pg_connection, instance=instance_id)
        first.append(FiringCompleted(TRANSITION, occurrence=1, instant=2))

        with pytest.raises(ValueError, match=rf"{instance_id}:0.*FiringCompleted.*FiringFailed"):
            twin.append(FiringFailed(TRANSITION, "boom", occurrence=1, instant=2))

        assert len(_rows(pg_connection, instance_id)) == 1

    def test_a_second_terminal_fact_conflicts_at_the_index_and_verifies(self, pg_connection, instance_id):
        # The one-terminal-per-firing-occurrence discipline in DDL: a second
        # terminal fact for the occurrence at a DIFFERENT position (so the
        # event identity is fresh) still conflicts — at the partial unique
        # index — and the verify-on-conflict acceptance applies: identical is
        # acknowledged, different fails loud naming both sides.
        history = PostgresHistoryStore(pg_connection, instance=instance_id)
        terminal = FiringCompleted(TRANSITION, occurrence=1, instant=2)
        history.extend([FiringBegun(TRANSITION, occurrence=1, instant=1), terminal])

        history.append(terminal)  # identical re-record: acknowledged, no second row
        assert [row[1] for row in _rows(pg_connection, instance_id)] == ["FiringBegun", "FiringCompleted"]
        # An acknowledgement is not an append [review fix 1]: the fact is
        # durable at ANOTHER position, so it enters neither this history's
        # memory nor its position sequence — memory never gets ahead of the
        # table's rows.
        assert len(history) == len(_rows(pg_connection, instance_id)) == 2

        with pytest.raises(ValueError, match="terminal.*FiringCompleted.*FiringFailed"):
            history.append(FiringFailed(TRANSITION, "diverging", occurrence=1, instant=3))

    def test_the_history_continues_past_a_terminal_index_acknowledgement(self, pg_connection, instance_id):
        # The review's demonstrated defect, pinned as its regression: a
        # terminal-index acknowledgement must not gap the position sequence —
        # acknowledge, append, reload, append again, and every step stays
        # consistent (dense event identities, reload == memory).
        history = PostgresHistoryStore(pg_connection, instance=instance_id)
        terminal = FiringCompleted(TRANSITION, occurrence=1, instant=2)
        history.extend([FiringBegun(TRANSITION, occurrence=1, instant=1), terminal])

        history.append(terminal)  # acknowledged at position 1: consumes nothing
        history.append(TokensProduced(PLACE, (Token.black(),), occurrence=1, instant=3))

        reloaded = PostgresHistoryStore(pg_connection, instance=instance_id)
        assert reloaded.records == history.records
        reloaded.append(FiringBegun(TRANSITION, occurrence=2, instant=4))

        assert [row[0] for row in _rows(pg_connection, instance_id)] == [f"{instance_id}:{n}" for n in range(4)]
        assert PostgresHistoryStore(pg_connection, instance=instance_id).records == reloaded.records

    def test_two_connections_identical_terminal_at_divergent_positions_acknowledges(
        self, postgres_dsn, pg_connection, instance_id
    ):
        # The realistic cross-process shape [review fix 4]: writer A commits
        # an extra record and its terminal (positions 1, 2); writer B — its
        # own connection, loaded afterwards — appends the identical terminal,
        # which lands at position 3: a FRESH event identity, so the conflict
        # is the partial unique index, and the terminal-family verify branch
        # acknowledges the value-equal fact. Exactly one terminal row; B's
        # memory never gets ahead of the table. (The two writers cannot mint
        # divergent positions while racing from one base — position identity
        # converges them onto the event-identity branch, pinned by the racing
        # tests below — so divergence means one loaded after the other's
        # commits, which is exactly this sequence.)
        terminal = FiringCompleted(TRANSITION, occurrence=1, instant=2)
        writer_a = PostgresHistoryStore(pg_connection, instance=instance_id)
        writer_a.extend(
            [
                FiringBegun(TRANSITION, occurrence=1, instant=1),
                TokensProduced(PLACE, (Token.black(),), occurrence=1, instant=2),
                terminal,
            ]
        )

        with psycopg.connect(postgres_dsn, autocommit=True) as connection_b:
            writer_b = PostgresHistoryStore(connection_b, instance=instance_id)
            writer_b.append(terminal)
            assert len(writer_b) == len(_rows(pg_connection, instance_id)) == 3

        assert [row[1] for row in _rows(pg_connection, instance_id)].count("FiringCompleted") == 1

    def test_two_connections_different_terminal_at_divergent_positions_fails_loud(
        self, postgres_dsn, pg_connection, instance_id
    ):
        # The divergent-position conflict's loud half: writer B's DIFFERENT
        # terminal for the same occurrence is refused through the same
        # terminal-family branch, naming both sides; the stored truth stays
        # the winner's.
        writer_a = PostgresHistoryStore(pg_connection, instance=instance_id)
        writer_a.extend(
            [
                FiringBegun(TRANSITION, occurrence=1, instant=1),
                TokensProduced(PLACE, (Token.black(),), occurrence=1, instant=2),
                FiringCompleted(TRANSITION, occurrence=1, instant=2),
            ]
        )

        with psycopg.connect(postgres_dsn, autocommit=True) as connection_b:
            writer_b = PostgresHistoryStore(connection_b, instance=instance_id)
            with pytest.raises(ValueError, match="terminal.*FiringCompleted.*FiringFailed"):
                writer_b.append(FiringFailed(TRANSITION, "boom", occurrence=1, instant=3))
            assert len(writer_b) == 3  # the refused append entered nothing

        assert [row[1] for row in _rows(pg_connection, instance_id)] == [
            "FiringBegun",
            "TokensProduced",
            "FiringCompleted",
        ]

    def test_the_one_terminal_activity_fact_index_holds_the_same_discipline(self, pg_connection, instance_id):
        # The activity family's terminal pair rides its own partial unique
        # index, same acceptance discipline.
        from petrus.impetus.history import ActivityCompleted, ActivityFailed

        history = PostgresHistoryStore(pg_connection, instance=instance_id)
        history.append(ActivityCompleted(TRANSITION, {"status": "captured"}, occurrence=1, instant=2))

        history.append(ActivityCompleted(TRANSITION, {"status": "captured"}, occurrence=1, instant=2))
        assert len(_rows(pg_connection, instance_id)) == 1

        with pytest.raises(ValueError, match="terminal.*ActivityCompleted.*ActivityFailed"):
            history.append(ActivityFailed(TRANSITION, "late failure", occurrence=1, instant=3))

    def test_concurrent_duplicate_terminal_appends_one_wins_the_other_acknowledges(self, postgres_dsn, pg_connection):
        # The DS3 acceptance's race, run for real: two connections, two
        # threads, one identical terminal fact. ON CONFLICT makes the second
        # inserter wait for the first commit, then verify — both return
        # without error, exactly one row wins.
        instance_id = f"pg-race-{uuid4()}"
        record = FiringCompleted(TRANSITION, occurrence=1, instant=2)
        barrier = threading.Barrier(2)
        errors: list[Exception] = []

        def racer():
            try:
                with psycopg.connect(postgres_dsn, autocommit=True) as connection:
                    history = PostgresHistoryStore(connection, instance=instance_id)
                    barrier.wait(timeout=10)
                    history.append(record)
            except Exception as error:  # noqa: BLE001 — surfaced whole below
                errors.append(error)

        threads = [threading.Thread(target=racer) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        assert errors == []
        assert PostgresHistoryStore(pg_connection, instance=instance_id).records == (record,)

    def test_concurrent_different_terminal_appends_exactly_one_is_refused(self, postgres_dsn, pg_connection):
        # The race's loud half: two connections, two DIFFERENT terminal facts
        # for one occurrence — exactly one commits, the other is refused as an
        # operational conflict, and the stored truth is the winner's.
        instance_id = f"pg-race-{uuid4()}"
        outcomes: dict[str, Exception | None] = {}
        barrier = threading.Barrier(2)

        def racer(name: str, record):
            try:
                with psycopg.connect(postgres_dsn, autocommit=True) as connection:
                    history = PostgresHistoryStore(connection, instance=instance_id)
                    barrier.wait(timeout=10)
                    history.append(record)
                    outcomes[name] = None
            except ValueError as error:
                outcomes[name] = error

        threads = [
            threading.Thread(target=racer, args=("completed", FiringCompleted(TRANSITION, occurrence=1, instant=2))),
            threading.Thread(target=racer, args=("failed", FiringFailed(TRANSITION, "boom", occurrence=1, instant=2))),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)

        winners = [name for name, error in outcomes.items() if error is None]
        losers = [name for name, error in outcomes.items() if error is not None]
        assert len(winners) == 1 and len(losers) == 1
        [(_, record_type, _, _)] = _rows(pg_connection, instance_id)
        assert record_type == ("FiringCompleted" if winners == ["completed"] else "FiringFailed")


class TestCallerTransactionJoin:
    """The D11 transaction-mode shape: appends join a caller-held transaction; the caller commits or rolls back."""

    def test_appends_join_the_callers_transaction_and_land_at_its_commit(
        self, postgres_dsn, pg_connection, instance_id
    ):
        with psycopg.connect(postgres_dsn, autocommit=False) as caller:
            history = PostgresHistoryStore(caller, instance=instance_id)
            history.append(TokensInitialized(PLACE, (Token.black(),), instant=0))
            history.extend(
                [
                    FiringBegun(TRANSITION, occurrence=1, instant=1),
                    TokensConsumed(PLACE, (Token.black(),), occurrence=1, instant=1),
                ]
            )

            # Invisible to the world until the caller commits — the appends
            # are inside the caller's transaction, exactly where DS4's
            # spawn+append atomicity needs them.
            assert _rows(pg_connection, instance_id) == []
            caller.commit()

        assert len(_rows(pg_connection, instance_id)) == 3
        assert PostgresHistoryStore(pg_connection, instance=instance_id).records == history.records

    def test_a_rolled_back_caller_transaction_takes_the_appends_with_it(self, postgres_dsn, pg_connection, instance_id):
        with psycopg.connect(postgres_dsn, autocommit=False) as caller:
            history = PostgresHistoryStore(caller, instance=instance_id)
            history.append(TokensInitialized(PLACE, (Token.black(),), instant=0))
            caller.rollback()

        # The durable truth never held the append; the backend instance rode
        # the caller's transaction and is discarded with it — a fresh load
        # over the same instance id is empty.
        assert _rows(pg_connection, instance_id) == []
        assert PostgresHistoryStore(pg_connection, instance=instance_id).records == ()

    def test_loading_inside_the_callers_transaction_sees_its_own_appends(
        self, postgres_dsn, pg_connection, instance_id
    ):
        with psycopg.connect(postgres_dsn, autocommit=False) as caller:
            PostgresHistoryStore(caller, instance=instance_id).append(
                TokensInitialized(PLACE, (Token.black(),), instant=0)
            )
            reloaded = PostgresHistoryStore(caller, instance=instance_id)
            assert reloaded.records == (TokensInitialized(PLACE, (Token.black(),), instant=0),)
            caller.rollback()

    def test_a_rollback_discards_the_whole_runtime_derived_over_the_backend(
        self, postgres_dsn, pg_connection, instance_id
    ):
        # The join rule's full strength [review fix 3]: a Instance over
        # the joined backend advances live state — watermark, marking,
        # occurrence counter — on facts a rollback then retracts, so the
        # instance is discarded WITH the backend; the coherent continuation
        # is Instance.resume over a freshly loaded history, where the
        # rolled-back facts are gone and their identities and ids are free
        # again. (The ENFORCING session wrapper is deliberately DS4's — the
        # adapter owns the joined transaction.)
        from petrus.impetus.instance import Instance
        from petrus.impetus.petrinet import Arc, Net, Place, Transition

        intake, out = NetPath("intake"), NetPath("out")
        net = Net(places=[Place(out)], transitions=[Transition(intake)], arcs=[Arc(intake, out)])
        with psycopg.connect(postgres_dsn, autocommit=False) as caller:
            instance = Instance(net, history=PostgresHistoryStore(caller, instance=instance_id))
            instance.deliver(intake, Token.black(), identity="evt_1", at=3)
            caller.commit()
            instance.deliver(intake, Token.black(), identity="evt_2", at=5)
            caller.rollback()
            # The live instance speaks the retracted delivery — the proof it
            # must be discarded whole, not patched around.
            assert instance.watermark == 5
            assert len(instance.marking.place(out)) == 2

        resumed = Instance.resume(net, PostgresHistoryStore(pg_connection, instance=instance_id))
        assert resumed.watermark == 3
        assert len(resumed.marking.place(out)) == 1
        redelivered = resumed.deliver(intake, Token.black(), identity="evt_2", at=7)
        assert redelivered.occurrence == 2  # the rolled-back id was never durable, so it re-mints
        assert len(resumed.marking.place(out)) == 2


class TestDecodeFailsLoudAtLoad:
    def test_a_row_that_does_not_decode_names_its_event(self, pg_connection, instance_id):
        # A foreign or hand-edited row refuses at load, naming the event —
        # the JSONL backend's torn-line posture, spoken in rows.
        pg_connection.execute(
            "INSERT INTO impetus.semantic_events (event_id, net_instance_id, record_type, payload)"
            " VALUES (%s, %s, %s, %s::jsonb)",
            (f"{instance_id}:0", instance_id, "Bogus", json.dumps({"record": "Bogus", "schema": 2})),
        )
        with pytest.raises(ValueError, match=rf"{instance_id}:0.*Bogus"):
            PostgresHistoryStore(pg_connection, instance=instance_id)
