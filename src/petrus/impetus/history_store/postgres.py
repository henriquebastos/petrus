"""
PostgreSQL History Store: transactional storage for canonical History.

``PostgresHistoryStore`` (CV3.DS3) composes and persists the one event history in the
``impetus.semantic_events`` table — the Impetus-owned canonical-history shape
the ES-009 native floor proved and D11 kept above the execution substrate
[DR 2026-07-15 absurd-execution-substrate]. It is the JSONL backend's sibling
behind the same contract (the shared backend-contract suite pins the two
behaviorally identical), plus what only a database can promise:

- **Transactional batches.** On an autocommit connection the backend owns one
  transaction per append/extend, so a batch commits whole or not at all — the
  torn-commit shape JSONL can only refuse-loud at load is impossible here.
- **The caller-transaction join (the D11 transaction-mode shape).** On a
  connection holding a transaction (``autocommit=False``) the appends JOIN it
  and the caller commits — how Absurd Dispatch
  (``petrus.motus.dispatch.absurd``) makes the semantic append and Absurd's spawn commit
  or vanish as one transaction. Two
  obligations ride with joining. First: a rollback (or a refused append,
  which leaves the transaction holding the batch's earlier inserts — roll
  back, never commit around it) retracts facts that live state already
  advanced on, so the caller discards NOT just this backend instance but
  every ``Instance``/``Engine`` derived over it — their watermark,
  marking, occurrence counter, and in-flight set speak retracted appends —
  and reconstructs via ``Instance.resume`` over a freshly loaded history.
  Second: the in-memory records mirror the joined transaction's view, never
  more than it. (The enforcing provider doors are
  ``petrus.engine.postgres.create_engine``/``load_engine`` for a
  caller-supplied Dispatch, and ``petrus.engine.absurd`` for Absurd; they
  privately install joined transaction fate on the returned neutral Engine.)
- **Verify-on-conflict acceptance (the K6 discipline in DDL + code).** Every
  row carries a writer-derived deterministic event identity —
  ``"{instance}:{position}"``, the 0-based durable position the record fills
  in this history's sequence: an append-only sequence's own identity,
  recomputable by a retry, colliding for a diverged twin — and the
  one-terminal disciplines are partial unique indexes (one terminal firing
  fact, one terminal activity fact, per occurrence). An insert that conflicts
  on any of them re-reads the stored row and compares the durable payload:
  different fails loud naming the event; value-equal is acknowledged
  idempotently (no error, no second row) — and an acknowledgement is not an
  append: a value-equal row AT the expected identity fills that position and
  mirrors into memory, while a terminal fact acknowledged at a DIFFERENT
  position (the partial-index conflict) is already durable elsewhere and is
  a no-op for this history's memory and position sequence, so the sequence
  stays dense and reload-continuable. The single writer stays the ruled
  posture — the DDL is the cross-process backstop, not a coordination
  protocol.

One backend instance is one net instance's history (the JSONL posture),
identified by a caller-supplied ``instance`` id; many instances co-reside in
the one namespaced table, which is what lets Absurd Dispatch
join histories and task spawns in one database. Constructing over an ``instance`` with recorded
rows loads them in sequence order through the ratified codec —
``Instance.resume`` works from the database alone — and the schema itself
is provisioned by the idempotent ``ensure_schema``, a deliberate operator act
this constructor refuses loud without.

Serialization is not re-decided here: payloads are exactly
``petrus.impetus.history.codec.encode_record``/``decode_record`` — the one durable
spelling, so a history is readable regardless of which backend wrote it. The
whole batch encodes before the connection sees anything [convention 63];
NaN/Infinity have no strict-JSON spelling and refuse loud at encode, before
the sink — the codec-wide rule both backends enforce identically (jsonb would
otherwise abort a joined caller transaction mid-batch). ``recorded_at`` is
deliberate operator-audit metadata — wall-clock, stamped by the database,
never semantic time: the watermark discipline is the payload's ``instant``.
(The DS4 adapter's reconciliation turned out to read substrate task state,
not this column — it stays declared operator-audit surface awaiting its
first reader.)
"""

from __future__ import annotations

# Python imports
import json
import time

# Pip imports — the optional extra, refused loud by name when absent.
try:
    import psycopg
except ImportError as _psycopg_missing:
    raise ImportError(
        "PostgresHistoryStore needs psycopg, which ships in the optional 'postgres' extra: "
        "install petrus-runtime[postgres] (e.g. `uv add 'petrus-runtime[postgres]'` or `pip install 'petrus-runtime[postgres]'`)"
    ) from _psycopg_missing

# Internal imports
import petrus.telemetry as telemetry
from petrus.impetus.history import Record
from petrus.impetus.history.codec import decode_record, encode_record
from petrus.impetus.history_store.memory import InMemoryHistoryStore

# The operational shadow of the durable seam [ES-020], the JSONL sibling's
# posture: one emit per commit — batch size, how many records actually
# entered (an acknowledged-elsewhere terminal enters nothing), and the
# wall-clock cost of encode + insert + verify.
log = telemetry.get_logger("impetus")

# The two ruled one-terminal disciplines, by record family: at most one
# terminal firing fact and at most one terminal activity fact per occurrence
# [ES-009 native floor; DR 2026-07-14 activity-invocation-runtime-seam]. One
# home for both the DDL below and the conflict verification.
_FIRING_TERMINALS = ("FiringCompleted", "FiringFailed")
_ACTIVITY_TERMINALS = ("ActivityCompleted", "ActivityFailed")


def _sql_names(names: tuple[str, ...]) -> str:
    return ", ".join(f"'{name}'" for name in names)


# Idempotent DDL, adapted from the ES-009 native floor's semantic_events to
# the v2 record family: the correlation columns collapse to `occurrence` (the
# family's one correlation), the payload is the ratified codec's JSON object,
# and the terminal disciplines are spelled per family. Executed one statement
# at a time (psycopg's extended protocol takes one statement per execute).
_DDL = (
    "CREATE SCHEMA IF NOT EXISTS impetus",
    """
    CREATE TABLE IF NOT EXISTS impetus.semantic_events (
        sequence bigserial PRIMARY KEY,
        event_id text UNIQUE NOT NULL,
        net_instance_id text NOT NULL,
        record_type text NOT NULL,
        occurrence bigint,
        payload jsonb NOT NULL,
        recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
    )
    """,
    # One history loads as one instance's rows in sequence order — indexed so
    # co-resident instances never pay for each other.
    """
    CREATE INDEX IF NOT EXISTS semantic_events_by_instance
        ON impetus.semantic_events (net_instance_id, sequence)
    """,
    f"""
    CREATE UNIQUE INDEX IF NOT EXISTS semantic_events_one_terminal_per_firing_occurrence
        ON impetus.semantic_events (net_instance_id, occurrence)
        WHERE record_type IN ({_sql_names(_FIRING_TERMINALS)})
    """,
    f"""
    CREATE UNIQUE INDEX IF NOT EXISTS semantic_events_one_terminal_activity_fact
        ON impetus.semantic_events (net_instance_id, occurrence)
        WHERE record_type IN ({_sql_names(_ACTIVITY_TERMINALS)})
    """,
)


def ensure_schema(connection) -> None:
    """
    Provision the Impetus canonical-history schema, idempotently — CREATE
    SCHEMA/TABLE/INDEX IF NOT EXISTS, safe to run on every boot. On an
    autocommit connection the DDL applies immediately; inside a caller-held
    transaction it joins it (PostgreSQL DDL is transactional) and the caller
    commits.
    """
    for statement in _DDL:
        connection.execute(statement)


class PostgresHistoryStore:
    """
    The event history persisted in ``impetus.semantic_events``, scoped to one
    net instance by ``instance`` and written through the caller's open psycopg
    ``connection``. Constructing over recorded rows loads them (fail loud on a
    row that will not decode, naming its event); every append writes through
    before it is in memory — as one owned transaction per batch when the
    connection is autocommit, joined to the caller's transaction when it is
    not (see the module docstring for the join's two obligations). A record
    that cannot be encoded fails loud and enters neither the table nor this
    history's records; a conflicting insert is verified against the stored
    row — value-equal acknowledged, different refused loud.
    """

    def __init__(self, connection, instance: str):
        if not isinstance(instance, str) or not instance:
            raise ValueError(f"PostgresHistoryStore requires a non-empty string instance id, got {instance!r}")
        self._history = InMemoryHistoryStore()
        self._connection = connection
        self._instance = instance
        try:
            rows = connection.execute(
                "SELECT event_id, payload FROM impetus.semantic_events WHERE net_instance_id = %s ORDER BY sequence",
                (instance,),
            ).fetchall()
        except psycopg.errors.UndefinedTable as error:
            raise ValueError(
                "impetus.semantic_events does not exist on this connection's database: provision it with "
                "petrus.impetus.history_store.postgres.ensure_schema(connection) — a deliberate act, never implied by construction"
            ) from error
        records: list[Record] = []
        for event_id, payload in rows:
            try:
                records.append(decode_record(payload))
            except (ValueError, TypeError) as error:
                raise ValueError(f"event {event_id} does not decode as an event history record: {error}") from error
        self._history.extend(records)

    @property
    def records(self) -> tuple[Record, ...]:
        return self._history.records

    def __iter__(self):
        return iter(self._history)

    def __len__(self) -> int:
        return len(self._history)

    def append(self, record: Record) -> None:
        self._commit([record])

    def extend(self, records: list[Record]) -> None:
        self._commit(records)

    def _commit(self, records: list[Record]) -> None:
        # Memory mirrors durable truth, never intent: only the records the
        # insert reports as filling a position — inserted, or acknowledged
        # value-equal AT this history's expected position — enter the
        # in-memory records. A terminal fact acknowledged at a DIFFERENT
        # position (the partial-index conflict) is already durable elsewhere
        # in the sequence: mirroring it here would put memory ahead of the
        # table, gap the position sequence, and mint a colliding identity
        # after reload — an acknowledgement is not an append.
        started = time.perf_counter()
        entered = self._write(records)
        self._history.extend(entered)
        log.emit(
            "postgres_commit",
            records=len(records),
            entered=len(entered),
            elapsed_ms=telemetry.elapsed_ms(started),
        )

    def _write(self, records: list[Record]) -> list[Record]:
        # Encode the whole batch before the connection sees anything: a
        # record that cannot be spelled durably fails loud here, and encoding
        # never interleaves with inserting [convention 63].
        batch = [self._encoded_event(record) for record in records]
        if self._connection.autocommit:
            # The backend owns the batch's transaction: whole or not at all.
            with self._connection.transaction():
                return self._insert(batch)
        # The caller holds the transaction; the batch joins it and the
        # caller commits (the D11 transaction-mode shape).
        return self._insert(batch)

    def _encoded_event(self, record: Record) -> tuple[Record, str, int | None, str]:
        encoded = encode_record(record)
        try:
            payload = json.dumps(encoded, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"cannot durably encode {type(record).__name__}: {error} — durable instants, token data, "
                f"and activity input/result must be JSON-faithful values"
            ) from error
        return (record, type(record).__name__, encoded.get("occurrence"), payload)

    def _insert(self, batch: list[tuple[Record, str, int | None, str]]) -> list[Record]:
        # Event identities derive from the durable position each record will
        # actually fill — the running counter advances only when a row lands
        # or the value-equal row already sits at this position, never by the
        # batch's raw enumerated offset — so an acknowledged-elsewhere
        # terminal consumes neither a position nor a memory slot.
        entered: list[Record] = []
        position = len(self)
        for record, record_type, occurrence, payload in batch:
            event_id = f"{self._instance}:{position}"
            # Targetless ON CONFLICT DO NOTHING absorbs a conflict on ANY of
            # the table's unique indexes — the event identity and both
            # one-terminal disciplines — without aborting the transaction, so
            # verification can read and judge inside it (and inside a joined
            # caller transaction).
            cursor = self._connection.execute(
                "INSERT INTO impetus.semantic_events (event_id, net_instance_id, record_type, occurrence, payload)"
                " VALUES (%s, %s, %s, %s, %s::jsonb) ON CONFLICT DO NOTHING",
                (event_id, self._instance, record_type, occurrence, payload),
            )
            if cursor.rowcount == 0 and not self._verify_conflict(event_id, record_type, occurrence, payload):
                continue  # acknowledged at another position: durable already, a no-op here
            entered.append(record)
            position += 1
        return entered

    def _verify_conflict(self, event_id: str, record_type: str, occurrence: int | None, payload: str) -> bool:
        """
        The verify-on-conflict acceptance: the insert conflicted, so re-read
        the stored row it collided with and compare durable payloads —
        value-equal is an idempotent re-append, acknowledged quietly (the
        fact is already durable); different is refused loud naming the event
        and both sides. The event identity is checked first (a retry or a
        lockstep twin), then the terminal fact the record's family permits
        once per occurrence (the K6 discipline the partial indexes enforce).
        Returns whether the acknowledged fact FILLS the expected position —
        True for the event-identity match (the value-equal row sits exactly
        where this history was about to write), False for the terminal-index
        match (the fact is durable at a different position, so the caller
        consumes neither the position nor a memory slot).
        """
        # The re-reads below rely on READ COMMITTED (psycopg's default):
        # each statement sees the latest committed snapshot, so the row a
        # concurrent winner just committed — the one ON CONFLICT waited on —
        # is visible here.
        appending = json.loads(payload)
        stored = self._connection.execute(
            "SELECT record_type, payload FROM impetus.semantic_events WHERE event_id = %s", (event_id,)
        ).fetchone()
        if stored is not None:
            stored_type, stored_payload = stored
            if stored_payload == appending:
                return True
            raise ValueError(
                f"event {event_id} is already recorded as a different fact: refusing to overwrite an "
                f"appended fact (stored {stored_type}, appending {record_type})"
            )
        family = next((f for f in (_FIRING_TERMINALS, _ACTIVITY_TERMINALS) if record_type in f), None)
        terminal = (
            self._connection.execute(
                "SELECT event_id, record_type, payload FROM impetus.semantic_events"
                " WHERE net_instance_id = %s AND occurrence = %s AND record_type = ANY(%s)",
                (self._instance, occurrence, list(family)),
            ).fetchone()
            if family is not None
            else None
        )
        if terminal is None:
            # No unique index explains the conflict this connection observed —
            # never acknowledge what cannot be verified.
            raise RuntimeError(
                f"insert of event {event_id} ({record_type}) conflicted, but no stored row explains it: "
                f"cannot verify the conflict, refusing to acknowledge"
            )
        stored_event, stored_type, stored_payload = terminal
        if stored_payload == appending:
            return False
        raise ValueError(
            f"occurrence {occurrence} of {self._instance} already holds its terminal fact "
            f"({stored_type}, event {stored_event}): refusing a different {record_type} (event {event_id}) — "
            f"an operational conflict, not a redelivery"
        )
