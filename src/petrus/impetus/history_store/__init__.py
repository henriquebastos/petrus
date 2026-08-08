"""Canonical I/O backends for the semantic event history.

The non-optional JSONL and SQLite backends are available from this facade. PostgreSQL is
an explicit ``petrus.impetus.history_store.postgres`` opt-in so importing this
package never imports psycopg.
"""

from petrus.impetus.history_store.jsonl import DurableAppend, JsonlHistoryStore
from petrus.impetus.history_store.memory import HistoryStore, InMemoryHistoryStore
from petrus.impetus.history_store.sqlite import SqliteHistoryStore

__all__ = ["DurableAppend", "HistoryStore", "InMemoryHistoryStore", "JsonlHistoryStore", "SqliteHistoryStore"]
