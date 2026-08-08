"""
JSONL storage: the durable spelling of the event history.

The durable artifact is not a new concept — a History Store stores the one
event history [DR 2026-07-21 concept-first-ontology-boundaries];
"journal" stays off the kernel surface. The canonical
``petrus.impetus.history.codec`` owns the ratified public record serialization
schema. This module owns the first store, ``JsonlHistoryStore``: it composes
an ``InMemoryHistoryStore`` value and writes every append through to a JSONL file, durable
before it is in memory. Inject one at ``Instance`` construction and the
whole history is durable from the first record, every appending door included;
load one over an existing file and the records read back value-equal.

The schema is versioned by the CV3 schema-4 History contract, with older
schemas refused rather than migrated (occurrence vocabulary, delivery
identity, and read accounting):

- envelope ``{"record": <type name>, "schema": 4, ...fields}`` — the class
  name is the discriminator and ``schema`` the envelope version; an unknown
  name fails loud (a KNOWN schema-1 name fails naming its schema-2
  successor), a missing or non-4 ``schema`` fails naming the no-migration
  posture, and
  a known category whose field shape drifted fails as the record type's own
  constructor rejection. No v1 converter exists: no production histories
  predate the migration, so a v1 payload refuses loud rather than silently
  converting;
- a record's node is spelled by its role (``place``/``transition``/``source``)
  as a dotted string; ``Token`` as ``{color, data}``; ``DeliveryRegistration`` as
  ``{source, key}``; ``ExecutionPolicy`` as ``{attempts}``; tuples as lists;
- ``instant``, ``Token.data``, and the activity family's ``input``/``result``
  pass through as JSON values, which constrains
  durable instants, token data, and activity input/result to JSON-FAITHFUL
  values — ones that read
  back equal: objects, arrays, strings, numbers, booleans, null —
  NaN/Infinity have no strict-JSON spelling (nor read back equal) and refuse
  loud at encode, on every backend. A tuple in
  token data is legal but comes back a list (pinned by test), so a record
  carrying one is not value-equal across the wire — rebuilt occurrence
  equality, and the writer's idempotent-acknowledgement value equality,
  need JSON-faithful data. An unencodable record fails loud and enters
  neither the file nor memory; data-shape validation beyond that is the
  kernel-wide validation posture's
  (debt 2026-07-09T2310Z), not this codec's.

Durability posture — split from the format as its own tiny policy object,
``DurableAppend``: each append opens, writes, and closes the file (no held
handle; an explicit fsync is a future swap there) — durable across a process
crash, the property the first real net needs; power-failure durability is a
future backend's concern. Format knowledge never crosses the split:
``JsonlHistoryStore`` keeps the codec, the envelope, the batching, and
torn-line detection (a torn line IS undecodable JSON — format knowledge the
file layer cannot own), and hands the policy fully encoded lines. A torn
final line from a crash mid-write fails loud at load, naming the line;
recovery is the operator's call, never the decoder's guess. Concurrent append
is out of scope for this backend: the instance is its history's single writer,
and the backend that coordinates writers — ``petrus.impetus.history_store.postgres.
PostgresHistoryStore``, the transactional sibling behind the same contract —
stores the same History value while bypassing the JSONL-family policy object
entirely, when distribution demands it.
"""

from __future__ import annotations

# Python imports
import json
import time
from pathlib import Path

# Internal imports
import petrus.telemetry as telemetry
from petrus.impetus.history import Record
from petrus.impetus.history.codec import decode_record, encode_record
from petrus.impetus.history_store.memory import InMemoryHistoryStore

__all__ = [
    "DurableAppend",
    "JsonlHistoryStore",
]

# The operational shadow of the durable seam [ES-020]: one emit per durable
# commit — batch size, bytes, and the wall-clock cost of encode + IO. The
# semantic content of the batch is the records' own business; telemetry
# carries only operational shape.
log = telemetry.get_logger("impetus")


# The envelope version this kernel writes and reads — bumped only at a
# current canonical schema 4; older schemas are refused without migration.
class DurableAppend:
    """
    The durability policy, split from the format: append whole batches of
    lines to a file, durable across a process crash — the parent directory
    made once needed, one open-append-close per call, no held handle (an
    explicit fsync swaps in here when a backend needs power-failure
    durability). This object never inspects what it appends: the codec, the
    envelope, batching, and torn-line detection are the composing history's
    format knowledge, and it receives lines already encoded whole.
    """

    def __init__(self, path: Path | str):
        self.path = Path(path)

    def append(self, lines: list[str]) -> None:
        """Append the batch, each line terminated, through one file handle. An OS failure mid-batch is the crash posture: a torn line fails loud at the composing history's load."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as file:
            file.writelines(line + "\n" for line in lines)


class JsonlHistoryStore:
    """
    The event history persisted as JSONL — one encoded record per line, in
    append order, written through a composed ``DurableAppend``. Constructing
    over an existing file loads it, streaming one line at a time (fail loud
    on a line that will not decode); every append writes through, durably on
    disk before it is in memory, so this history's records never claim more
    than the file holds. A record that cannot be encoded fails loud and
    enters neither the file nor this history's records; an OS write failure
    mid-batch is the crash posture — a torn line fails loud at load, and a
    complete-line prefix that splits a COMMIT BATCH loads but reads back as
    a torn commit batch that resume refuses loud (replay divergence) —
    operator recovery, never silent corruption; only a prefix landing on a
    batch boundary reads back as a consistent earlier history that memory
    never got ahead of. (Batch-atomic durability is a backend property: the
    transactional sibling, ``petrus.impetus.history_store.postgres.PostgresHistoryStore``, commits
    batches whole; this JSONL backend's posture is refuse-loud.)
    """

    def __init__(self, path: Path | str):
        self._history = InMemoryHistoryStore()
        self.path = Path(path)
        self._durable = DurableAppend(self.path)
        if not self.path.exists():
            return
        records: list[Record] = []
        with self.path.open("r", encoding="utf-8") as file:
            for number, line in enumerate(file, start=1):
                try:
                    records.append(decode_record(json.loads(line)))
                except (ValueError, TypeError) as error:  # json decoding raises a ValueError subclass
                    raise ValueError(
                        f"{self.path}: line {number} does not decode as an event history record: {error}"
                    ) from error
        self._history.extend(records)

    @property
    def records(self) -> tuple[Record, ...]:
        return self._history.records

    def __iter__(self):
        return iter(self._history)

    def __len__(self) -> int:
        return len(self._history)

    def append(self, record: Record) -> None:
        self._write([record])
        self._history.append(record)

    def extend(self, records: list[Record]) -> None:
        self._write(records)
        self._history.extend(records)

    def _write(self, records: list[Record]) -> None:
        # Encode the whole batch before anything reaches disk: a record that
        # cannot be encoded fails loud here, before the file is even opened —
        # a rejected record's batch never reaches disk at all, and encoding
        # never interleaves with writing (a mid-batch encode failure would
        # otherwise manufacture the torn-commit shape replay treats as
        # corruption). IO may stream; encoding must not. (An OS write failure
        # can still land a complete-line prefix; that is the crash posture
        # above, not an encoding concern.)
        started = time.perf_counter()
        lines = [self._encoded_line(record) for record in records]
        self._durable.append(lines)
        log.emit(
            "jsonl_commit",
            records=len(records),
            bytes=sum(len(line) + 1 for line in lines),
            elapsed_ms=telemetry.elapsed_ms(started),
        )

    def _encoded_line(self, record: Record) -> str:
        # allow_nan=False is the codec-wide rule: NaN/Infinity have no strict-
        # JSON spelling (and are not value-equal to themselves back), so they
        # refuse loud here exactly as on the PostgreSQL sibling — never a
        # durable line strict readers cannot parse.
        try:
            return json.dumps(encode_record(record), allow_nan=False)
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"cannot durably encode {type(record).__name__}: {error} — "
                f"durable instants and token data must be JSON-faithful values"
            ) from error
