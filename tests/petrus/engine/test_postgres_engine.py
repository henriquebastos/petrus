"""PostgreSQL Engine provider ownership and resource behavior."""

from uuid import uuid4

import pytest
import psycopg

from petrus.engine import Engine
from petrus.engine.postgres import create_engine, load_engine
from petrus.impetus.history_store.postgres import PostgresHistoryStore, ensure_schema
from petrus.impetus.petrinet import Arc, Net, NetPath, Place, Token, Transition
from petrus.motus.dispatch import InlineDispatch

SOURCE, OUTPUT = NetPath("source"), NetPath("output")


@pytest.fixture
def instance_id():
    return f"pg-only-{uuid4()}"


def _provider_net() -> Net:
    return Net(
        places=[Place(OUTPUT)],
        transitions=[Transition(SOURCE)],
        arcs=[Arc(SOURCE, OUTPUT)],
    )


class TestPostgresEngineProvider:
    def test_create_load_and_idempotent_close_own_the_joined_connection(self, postgres_dsn, pg_connection, instance_id):
        writer = psycopg.connect(postgres_dsn, autocommit=False)
        created = create_engine(writer, _provider_net(), instance_id, dispatch=InlineDispatch({}))
        assert type(created) is Engine
        created.deliver(SOURCE, Token.black(), identity="first")
        records = created.records
        created.close()
        created.close()
        assert writer.closed

        resumed_writer = psycopg.connect(postgres_dsn, autocommit=False)
        resumed = load_engine(resumed_writer, _provider_net(), instance_id, dispatch=InlineDispatch({}))
        assert resumed.records == records
        assert len(resumed.marking.place(OUTPUT)) == 1
        resumed.close()
        assert resumed_writer.closed

    def test_autocommit_and_invalid_options_close_the_supplied_connection(
        self, postgres_dsn, pg_connection, instance_id
    ):
        autocommit = psycopg.connect(postgres_dsn, autocommit=True)
        with pytest.raises(ValueError, match="autocommit=False"):
            create_engine(autocommit, _provider_net(), instance_id, dispatch=InlineDispatch({}))
        assert autocommit.closed

        invalid = psycopg.connect(postgres_dsn, autocommit=False)
        with pytest.raises(TypeError, match="unexpected keyword argument 'unknown_option'"):
            create_engine(
                invalid,
                _provider_net(),
                instance_id,
                dispatch=InlineDispatch({}),
                unknown_option=True,
            )
        assert invalid.closed

    def test_create_and_load_preconditions_close_without_changing_history(
        self, postgres_dsn, pg_connection, instance_id
    ):
        created = create_engine(
            psycopg.connect(postgres_dsn, autocommit=False),
            _provider_net(),
            instance_id,
            dispatch=InlineDispatch({}),
        )
        records = created.records
        created.close()

        duplicate_writer = psycopg.connect(postgres_dsn, autocommit=False)
        with pytest.raises(ValueError, match="already exists"):
            create_engine(duplicate_writer, _provider_net(), instance_id, dispatch=InlineDispatch({}))
        assert duplicate_writer.closed

        missing_writer = psycopg.connect(postgres_dsn, autocommit=False)
        with pytest.raises(ValueError, match="does not exist"):
            load_engine(
                missing_writer,
                _provider_net(),
                f"missing-{instance_id}",
                dispatch=InlineDispatch({}),
            )
        assert missing_writer.closed

        probe = psycopg.connect(postgres_dsn, autocommit=True)
        try:
            assert PostgresHistoryStore(probe, instance_id).records == records
        finally:
            probe.close()

    def test_held_fence_refuses_before_history_load_and_closes_the_second_writer(
        self, postgres_dsn, pg_connection, instance_id
    ):
        first = create_engine(
            psycopg.connect(postgres_dsn, autocommit=False),
            _provider_net(),
            instance_id,
            dispatch=InlineDispatch({}),
        )
        second_writer = psycopg.connect(postgres_dsn, autocommit=False)
        with pytest.raises(RuntimeError, match="already held.*second canonical writer"):
            load_engine(second_writer, _provider_net(), instance_id, dispatch=InlineDispatch({}))
        assert second_writer.closed

        first.close()
        resumed = load_engine(
            psycopg.connect(postgres_dsn, autocommit=False),
            _provider_net(),
            instance_id,
            dispatch=InlineDispatch({}),
        )
        resumed.close()

    def test_missing_schema_releases_fence_closes_and_allows_retry(self, postgres_dsn, pg_connection, instance_id):
        pg_connection.execute("DROP SCHEMA impetus CASCADE")
        writer = psycopg.connect(postgres_dsn, autocommit=False)
        try:
            with pytest.raises(ValueError, match="ensure_schema"):
                create_engine(writer, _provider_net(), instance_id, dispatch=InlineDispatch({}))
            assert writer.closed
        finally:
            ensure_schema(pg_connection)

        retried = create_engine(
            psycopg.connect(postgres_dsn, autocommit=False),
            _provider_net(),
            instance_id,
            dispatch=InlineDispatch({}),
        )
        retried.close()

    def test_writing_failure_poison_releases_fence_for_fresh_load(self, postgres_dsn, pg_connection, instance_id):
        poisoned_writer = psycopg.connect(postgres_dsn, autocommit=False)
        poisoned = create_engine(
            poisoned_writer,
            _provider_net(),
            instance_id,
            dispatch=InlineDispatch({}),
        )
        committed = poisoned.records
        with pytest.raises(ValueError, match="unknown|source|transition"):
            poisoned.deliver(NetPath("unknown"), Token.black(), identity="bad")

        resumed = load_engine(
            psycopg.connect(postgres_dsn, autocommit=False),
            _provider_net(),
            instance_id,
            dispatch=InlineDispatch({}),
        )
        assert resumed.records == committed
        poisoned.close()
        assert poisoned_writer.closed
        resumed.close()
