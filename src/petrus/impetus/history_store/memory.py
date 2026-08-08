"""Structural History Store contract and in-memory implementation."""

from collections.abc import Iterator
from typing import Protocol

from petrus.impetus.history import Record

__all__ = ["HistoryStore", "InMemoryHistoryStore"]


class HistoryStore(Protocol):
    """The structural History Store contract accepted by an Instance."""

    @property
    def records(self) -> tuple[Record, ...]: ...

    def append(self, record: Record) -> None: ...

    def extend(self, records: list[Record]) -> None: ...

    def __iter__(self) -> Iterator[Record]: ...

    def __len__(self) -> int: ...


class InMemoryHistoryStore:
    """An append-only sequence of records, per net instance."""

    def __init__(self):
        self._records: list[Record] = []

    def append(self, record: Record) -> None:
        self._records.append(record)

    def extend(self, records: list[Record]) -> None:
        self._records.extend(records)

    @property
    def records(self) -> tuple[Record, ...]:
        return tuple(self._records)

    def __iter__(self):
        return iter(self.records)

    def __len__(self) -> int:
        return len(self._records)
