"""PostgreSQL Engine provider ownership and resource behavior."""

from uuid import uuid4

import pytest
import psycopg

from petrus.engine import Delivery, Engine
from petrus.engine.postgres import create_engine, load_engine
from petrus.impetus.history import ExternalEventDelivered, FiringBegun, FiringCompleted, FiringFailed
from petrus.impetus.history_store.postgres import PostgresHistoryStore, ensure_schema
from petrus.impetus.instance import PriorAcknowledgement
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


class _CountCommits:
    def __init__(self, connection):
        self.connection = connection
        self.commits = 0

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def commit(self):
        self.commits += 1
        self.connection.commit()


class TestPostgresEngineProvider:
    def test_sensed_projection_failure_commits_terminal_failure_and_acknowledges_exactly(
        self, postgres_dsn, pg_connection, instance_id
    ):
        token = Token("Event", 7)

        def explode(binding, outputs):
            raise RuntimeError("projection failed")

        net = Net(
            places=[Place(OUTPUT)],
            transitions=[Transition(SOURCE, handler="project")],
            arcs=[Arc(SOURCE, OUTPUT)],
        )
        engine = create_engine(
            psycopg.connect(postgres_dsn, autocommit=False),
            net,
            instance_id,
            dispatch=InlineDispatch({}),
            handlers={"project": explode},
            sensor=lambda: (Delivery(SOURCE, token, identity="event-7"),),
        )

        with pytest.raises(RuntimeError, match="projection failed"):
            engine.advance()

        with psycopg.connect(postgres_dsn, autocommit=True) as probe:
            accepted_records = PostgresHistoryStore(probe, instance_id).records
        assert isinstance(accepted_records[-3], ExternalEventDelivered)
        assert isinstance(accepted_records[-2], FiringBegun)
        assert isinstance(accepted_records[-1], FiringFailed)
        assert not any(isinstance(record, FiringCompleted) for record in accepted_records)

        resumed = load_engine(
            psycopg.connect(postgres_dsn, autocommit=False),
            net,
            instance_id,
            dispatch=InlineDispatch({}),
            handlers={"project": lambda binding, outputs: {OUTPUT: binding.tokens}},
        )
        acknowledged = resumed.accept_delivery(SOURCE, token, identity="event-7")

        assert acknowledged == PriorAcknowledgement("event-7", 1)
        assert resumed.marking.place(OUTPUT) == ()
        resumed.close()

    def test_direct_projection_failure_commits_terminal_failure_and_acknowledges_exactly(
        self, postgres_dsn, pg_connection, instance_id
    ):
        token = Token("Event", 7)

        class ProjectionError(RuntimeError):
            def __repr__(self):
                raise AssertionError("durable failure rendering must not call exception repr")

        def explode(binding, outputs):
            raise ProjectionError("projection failed")

        net = Net(
            places=[Place(OUTPUT)],
            transitions=[Transition(SOURCE, handler="project")],
            arcs=[Arc(SOURCE, OUTPUT)],
        )
        engine = create_engine(
            psycopg.connect(postgres_dsn, autocommit=False),
            net,
            instance_id,
            dispatch=InlineDispatch({}),
            handlers={"project": explode},
        )
        accepted = engine.accept_delivery(SOURCE, token, identity="event-7")

        with pytest.raises(ProjectionError, match="projection failed"):
            engine.complete_delivery(accepted)

        with psycopg.connect(postgres_dsn, autocommit=True) as probe:
            records = PostgresHistoryStore(probe, instance_id).records
        assert records[-1] == FiringFailed(SOURCE, "ProjectionError('projection failed')", occurrence=1)

        resumed = load_engine(
            psycopg.connect(postgres_dsn, autocommit=False),
            net,
            instance_id,
            dispatch=InlineDispatch({}),
            handlers={"project": lambda binding, outputs: {OUTPUT: binding.tokens}},
        )
        assert resumed.accept_delivery(SOURCE, token, identity="event-7") == PriorAcknowledgement("event-7", 1)
        resumed.close()

    def test_exact_redelivery_does_not_commit_an_empty_joined_transaction(
        self, postgres_dsn, pg_connection, instance_id
    ):
        token = Token("Event", 7)
        connection = _CountCommits(psycopg.connect(postgres_dsn, autocommit=False))
        engine = create_engine(
            connection,
            _provider_net(),
            instance_id,
            dispatch=InlineDispatch({}),
        )
        accepted = engine.accept_delivery(SOURCE, token, identity="event-7")
        after_acceptance = connection.commits

        reconstructed = engine.accept_delivery(SOURCE, token, identity="event-7")

        assert reconstructed == accepted
        assert connection.commits == after_acceptance

        engine.complete_delivery(reconstructed)
        after_completion = connection.commits
        acknowledged = engine.accept_delivery(SOURCE, token, identity="event-7")

        assert acknowledged == PriorAcknowledgement("event-7", accepted.occurrence)
        assert connection.commits == after_completion
        engine.close()

    def test_sensed_exact_redelivery_does_not_commit_an_empty_joined_transaction(
        self, postgres_dsn, pg_connection, instance_id
    ):
        delivery = Delivery(SOURCE, Token("Event", 7), identity="event-7")
        deliveries = iter(((delivery,), (delivery,)))
        connection = _CountCommits(psycopg.connect(postgres_dsn, autocommit=False))
        engine = create_engine(
            connection,
            _provider_net(),
            instance_id,
            dispatch=InlineDispatch({}),
            sensor=lambda: next(deliveries),
        )
        engine.advance()
        after_first_delivery = connection.commits

        outcome = engine.advance()

        assert outcome.firings == ()
        assert connection.commits == after_first_delivery
        engine.close()

    @pytest.mark.parametrize("fault", ["refused", "acknowledgement-lost"])
    def test_projection_failure_commit_fault_propagates_storage_fate_and_fresh_load_decides(
        self, postgres_dsn, pg_connection, instance_id, fault
    ):
        class FaultOneCommit:
            def __init__(self, connection):
                self.connection = connection
                self.fault = None

            def __getattr__(self, name):
                return getattr(self.connection, name)

            def commit(self):
                pending_fault = self.fault
                self.fault = None
                if pending_fault == "refused":
                    raise OSError("failure commit refused")
                self.connection.commit()
                if pending_fault == "acknowledgement-lost":
                    raise OSError("failure commit acknowledgement lost")

        def explode(binding, outputs):
            del binding, outputs
            raise RuntimeError("projection failed")

        token = Token("Event", 7)
        connection = FaultOneCommit(psycopg.connect(postgres_dsn, autocommit=False))
        net = Net(
            places=[Place(OUTPUT)],
            transitions=[Transition(SOURCE, handler="project")],
            arcs=[Arc(SOURCE, OUTPUT)],
        )
        engine = create_engine(
            connection,
            net,
            instance_id,
            dispatch=InlineDispatch({}),
            handlers={"project": explode},
        )
        accepted = engine.accept_delivery(SOURCE, token, identity="event-7")
        connection.fault = fault

        with pytest.raises(OSError, match="failure commit"):
            engine.complete_delivery(accepted)

        assert connection.connection.closed
        with psycopg.connect(postgres_dsn, autocommit=True) as probe:
            records = PostgresHistoryStore(probe, instance_id).records

        resumed = load_engine(
            psycopg.connect(postgres_dsn, autocommit=False),
            net,
            instance_id,
            dispatch=InlineDispatch({}),
            handlers={"project": lambda binding, outputs: {OUTPUT: binding.tokens}},
        )
        redelivered = resumed.accept_delivery(SOURCE, token, identity="event-7")
        if fault == "refused":
            assert records[-2:] == (
                ExternalEventDelivered(SOURCE, (token,), identity="event-7", occurrence=1),
                FiringBegun(SOURCE, occurrence=1),
            )
            assert redelivered == accepted
            resumed.complete_delivery(redelivered)
            assert resumed.marking.place(OUTPUT) == (token,)
        else:
            assert records[-1] == FiringFailed(SOURCE, "RuntimeError('projection failed')", occurrence=1)
            assert redelivered == PriorAcknowledgement("event-7", accepted.occurrence)
            assert resumed.marking.place(OUTPUT) == ()
        resumed.close()

    def test_joined_completion_commit_refusal_leaves_acceptance_unfinished_for_exact_retry(
        self, postgres_dsn, pg_connection, instance_id
    ):
        class RefuseOneCommit:
            def __init__(self, connection):
                self.connection = connection
                self.refuse = False

            def __getattr__(self, name):
                return getattr(self.connection, name)

            def commit(self):
                if self.refuse:
                    self.refuse = False
                    raise OSError("joined completion commit refused")
                self.connection.commit()

        token = Token("Event", 7)
        connection = RefuseOneCommit(psycopg.connect(postgres_dsn, autocommit=False))
        engine = create_engine(
            connection,
            _provider_net(),
            instance_id,
            dispatch=InlineDispatch({}),
        )
        accepted = engine.accept_delivery(SOURCE, token, identity="event-7")
        connection.refuse = True

        with pytest.raises(OSError, match="joined completion commit refused"):
            engine.complete_delivery(accepted)

        assert connection.connection.closed
        with psycopg.connect(postgres_dsn, autocommit=True) as probe:
            refused_records = PostgresHistoryStore(probe, instance_id).records
        assert refused_records[-2:] == (
            ExternalEventDelivered(SOURCE, (token,), identity="event-7", occurrence=1),
            FiringBegun(SOURCE, occurrence=1),
        )
        assert not any(isinstance(record, FiringCompleted | FiringFailed) for record in refused_records)

        resumed = load_engine(
            psycopg.connect(postgres_dsn, autocommit=False),
            _provider_net(),
            instance_id,
            dispatch=InlineDispatch({}),
        )
        reconstructed = resumed.accept_delivery(SOURCE, token, identity="event-7")
        assert reconstructed == accepted
        assert resumed.complete_delivery(reconstructed).occurrence == accepted.occurrence
        resumed.close()

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
