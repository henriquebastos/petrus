"""Direct production contract for the local SQLite History Store."""

import json
import sqlite3
import threading

import pytest

from petrus.impetus.history import FiringBegun, FiringCompleted, FiringFailed, TokensInitialized, TokensProduced
from petrus.impetus.history.codec import encode_record
from petrus.impetus.history_store import SqliteHistoryStore
from petrus.impetus.petrinet import NetPath, Token
from tests.petrus.impetus.history_store.test_persistence import every_record_category

PLACE, TRANSITION = NetPath("place"), NetPath("transition")


def test_schema_initializes_idempotently_reopens_and_preserves_unrelated_tables(tmp_path):
    path = tmp_path / "nested" / "local.sqlite3"
    history = SqliteHistoryStore(path, "one")
    history.append(TokensInitialized(PLACE, (Token.black(),), instant=0))
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE unrelated_dispatch_state (value TEXT)")
        connection.execute("INSERT INTO unrelated_dispatch_state VALUES ('intact')")

    assert SqliteHistoryStore(path, "one").records == history.records
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT value FROM unrelated_dispatch_state").fetchone() == ("intact",)
        assert connection.execute("SELECT version FROM impetus_history_schema").fetchone() == (1,)


@pytest.mark.parametrize("version", [0, 2])
def test_unsupported_schema_refuses_without_mutation(tmp_path, version):
    path = tmp_path / "foreign.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE impetus_history_schema (component TEXT PRIMARY KEY, version INTEGER NOT NULL)")
        connection.execute("INSERT INTO impetus_history_schema VALUES ('history', ?)", (version,))
    before = path.read_bytes()

    with pytest.raises(ValueError, match="does not migrate"):
        SqliteHistoryStore(path, "one")

    assert path.read_bytes() == before


def test_unversioned_known_shape_refuses(tmp_path):
    path = tmp_path / "unversioned.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE impetus_history_events (payload TEXT)")
    with pytest.raises(ValueError, match="unversioned"):
        SqliteHistoryStore(path, "one")


def test_current_schema_refuses_a_weakened_terminal_index_with_the_same_name(tmp_path):
    path = tmp_path / "weakened.sqlite3"
    SqliteHistoryStore(path, "one").close()
    with sqlite3.connect(path) as connection:
        connection.execute("DROP INDEX impetus_history_one_activity_terminal")
        connection.execute(
            "CREATE INDEX impetus_history_one_activity_terminal ON impetus_history_events (instance, occurrence)"
        )
    with pytest.raises(ValueError, match="DDL shape"):
        SqliteHistoryStore(path, "one")


def test_every_record_category_round_trips_and_payload_is_canonical(tmp_path):
    path = tmp_path / "history.sqlite3"
    records = every_record_category()
    SqliteHistoryStore(path, "one").extend(records)

    assert SqliteHistoryStore(path, "one").records == tuple(records)
    with sqlite3.connect(path) as connection:
        payload = json.loads(
            connection.execute("SELECT payload FROM impetus_history_events ORDER BY position").fetchone()[0]
        )
    assert payload == encode_record(records[0])


def test_failed_batch_is_atomic_and_json_unfaithful_data_never_enters(tmp_path):
    path = tmp_path / "history.sqlite3"
    history = SqliteHistoryStore(path, "one")
    history.extend(
        [FiringBegun(TRANSITION, occurrence=1, instant=1), FiringCompleted(TRANSITION, occurrence=1, instant=2)]
    )

    with pytest.raises(ValueError, match="terminal"):
        history.extend(
            [
                TokensProduced(PLACE, (Token.black(),), occurrence=1, instant=3),
                FiringFailed(TRANSITION, "different", occurrence=1, instant=3),
            ]
        )
    with pytest.raises(ValueError, match="JSON-faithful"):
        history.append(TokensInitialized(PLACE, (Token("bad", float("nan")),), instant=4))

    assert SqliteHistoryStore(path, "one").records == history.records
    assert len(history) == 2


def test_exact_retry_acknowledges_and_different_retry_refuses(tmp_path):
    path = tmp_path / "history.sqlite3"
    first = SqliteHistoryStore(path, "one")
    twin = SqliteHistoryStore(path, "one")
    record = FiringCompleted(TRANSITION, occurrence=1, instant=2)
    first.append(record)
    twin.append(record)
    assert twin.records == first.records == (record,)

    stale = SqliteHistoryStore(path, "one")
    winner = SqliteHistoryStore(path, "one")
    winner.append(FiringBegun(TRANSITION, occurrence=2, instant=3))
    with pytest.raises(ValueError, match=r"one:1.*FiringBegun.*TokensProduced"):
        stale.append(TokensProduced(PLACE, (Token.black(),), occurrence=2, instant=3))


def test_terminal_identity_and_instances_are_isolated(tmp_path):
    path = tmp_path / "history.sqlite3"
    one = SqliteHistoryStore(path, "one")
    terminal = FiringCompleted(TRANSITION, occurrence=1, instant=2)
    one.extend([FiringBegun(TRANSITION, occurrence=1, instant=1), terminal])
    one.append(terminal)
    assert len(one) == 2
    with pytest.raises(ValueError, match="terminal"):
        one.append(FiringFailed(TRANSITION, "different", occurrence=1, instant=3))

    two = SqliteHistoryStore(path, "two")
    two.append(FiringFailed(TRANSITION, "its own", occurrence=1, instant=3))
    assert two.records == (FiringFailed(TRANSITION, "its own", occurrence=1, instant=3),)
    assert SqliteHistoryStore(path, "one").records == one.records


@pytest.mark.parametrize("corruption", ["gap", "payload", "metadata"])
def test_fresh_constructor_refuses_corrupt_durable_rows(tmp_path, corruption):
    path = tmp_path / "history.sqlite3"
    SqliteHistoryStore(path, "one").append(TokensInitialized(PLACE, (Token.black(),), instant=0))
    with sqlite3.connect(path) as connection:
        if corruption == "gap":
            connection.execute("UPDATE impetus_history_events SET position = 2, event_id = 'one:2'")
        elif corruption == "payload":
            connection.execute("UPDATE impetus_history_events SET payload = '{broken'")
        else:
            connection.execute("UPDATE impetus_history_events SET record_type = 'FiringBegun'")

    with pytest.raises(ValueError, match="non-dense|does not decode|indexing metadata"):
        SqliteHistoryStore(path, "one")


def test_constructor_requires_non_empty_instance(tmp_path):
    for bad in ("", 7):
        with pytest.raises(ValueError, match="non-empty string instance"):
            SqliteHistoryStore(tmp_path / "history.sqlite3", bad)


def test_concurrent_first_initialization_for_distinct_instances(tmp_path):
    path = tmp_path / "history.sqlite3"
    barrier = threading.Barrier(2)
    failures = []

    def initialize(instance):
        try:
            barrier.wait()
            SqliteHistoryStore(path, instance).close()
        except BaseException as error:
            failures.append(error)

    threads = [threading.Thread(target=initialize, args=(instance,)) for instance in ("one", "two")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert not failures
    assert not any(thread.is_alive() for thread in threads)
