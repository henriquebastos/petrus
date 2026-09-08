"""Trusted-workspace PostgreSQL implementation of Fabric.

The fabric is a delivery and discovery protocol, not a scheduler and not semantic
history.  Its API-level credentials prevent accidental cross-instance use; they
do not protect against a hostile SQL principal with access to the shared database.
"""

from __future__ import annotations

# Python imports
import contextlib
import hashlib
import hmac
import secrets
from datetime import datetime


# Pip imports — the optional extra, refused loud by name when absent.
try:
    from psycopg.types.json import Jsonb
except ImportError as _psycopg_missing:
    raise ImportError(
        "petrus.fabric.postgres needs psycopg, which ships in the optional 'postgres' extra: "
        "install petrus-runtime[postgres] (e.g. `uv add 'petrus-runtime[postgres]'` or `pip install 'petrus-runtime[postgres]'`)"
    ) from _psycopg_missing


# Internal imports
import petrus.telemetry as telemetry
from petrus.fabric.model import Endpoint, Envelope, Receipt, Submission, _json_copy, _text

_SCHEMA_VERSION = 1
log = telemetry.get_logger("impetus")


def issue_credential() -> str:
    return secrets.token_urlsafe(32)


def _credential(credential: object) -> str:
    if not isinstance(credential, str) or len(credential.encode()) < 32 or len(set(credential)) < 16:
        raise ValueError("credential must be a high-entropy opaque token of at least 32 UTF-8 bytes")
    return credential


def _credential_digest(credential: str) -> str:
    return hashlib.sha256(credential.encode()).hexdigest()


_DDL = (
    "CREATE SCHEMA IF NOT EXISTS impetus_fabric",
    """CREATE TABLE IF NOT EXISTS impetus_fabric.schema_metadata (
        component text PRIMARY KEY, version integer NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS impetus_fabric.processes (
        instance_id text PRIMARY KEY, credential_digest text NOT NULL,
        registered_at timestamptz NOT NULL DEFAULT clock_timestamp())""",
    """CREATE TABLE IF NOT EXISTS impetus_fabric.exposed_sources (
        instance_id text NOT NULL REFERENCES impetus_fabric.processes(instance_id), source text NOT NULL,
        exposed_at timestamptz NOT NULL DEFAULT clock_timestamp(), PRIMARY KEY (instance_id, source))""",
    """CREATE TABLE IF NOT EXISTS impetus_fabric.service_offers (
        instance_id text NOT NULL, source text NOT NULL, service text NOT NULL, capabilities jsonb NOT NULL,
        offered_at timestamptz NOT NULL DEFAULT clock_timestamp(), PRIMARY KEY (instance_id, source, service),
        FOREIGN KEY (instance_id, source) REFERENCES impetus_fabric.exposed_sources(instance_id, source))""",
    """CREATE TABLE IF NOT EXISTS impetus_fabric.delivery_grants (
        sender text NOT NULL REFERENCES impetus_fabric.processes(instance_id), recipient text NOT NULL,
        source text NOT NULL, granted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        PRIMARY KEY (sender, recipient, source),
        FOREIGN KEY (recipient, source) REFERENCES impetus_fabric.exposed_sources(instance_id, source))""",
    """CREATE TABLE IF NOT EXISTS impetus_fabric.deliveries (
        sender text NOT NULL REFERENCES impetus_fabric.processes(instance_id), delivery_id text NOT NULL,
        recipient text NOT NULL REFERENCES impetus_fabric.processes(instance_id), source text NOT NULL,
        correlation text NOT NULL, envelope jsonb, digest text NOT NULL, submitted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        accepted_occurrence bigint, accepted_at timestamptz,
        PRIMARY KEY (sender, delivery_id),
        CHECK ((accepted_occurrence IS NULL) = (accepted_at IS NULL)),
        CHECK (envelope IS NOT NULL OR accepted_at IS NOT NULL))""",
    "CREATE INDEX IF NOT EXISTS fabric_pending_by_recipient ON impetus_fabric.deliveries (recipient, submitted_at) WHERE accepted_at IS NULL",
    "CREATE INDEX IF NOT EXISTS fabric_offers_by_service ON impetus_fabric.service_offers (service, instance_id, source)",
)


def ensure_fabric_schema(connection) -> None:
    """Provision the versioned fabric protocol schema without committing the caller's transaction."""
    schema_exists = connection.execute("SELECT 1 FROM pg_namespace WHERE nspname = 'impetus_fabric'").fetchone()
    if (
        schema_exists
        and connection.execute("SELECT to_regclass('impetus_fabric.schema_metadata')").fetchone()[0] is None
    ):
        known_table = connection.execute(
            """SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'impetus_fabric' AND table_name = ANY(%s) LIMIT 1""",
            (["processes", "exposed_sources", "service_offers", "delivery_grants", "deliveries"],),
        ).fetchone()
        if known_table is not None:
            raise RuntimeError(
                f"the impetus_fabric schema contains unversioned table {known_table[0]!r}: refusing to "
                "bless an unknown shape — migrate or recreate the fabric schema deliberately"
            )
    for statement in _DDL:
        connection.execute(statement)
    connection.execute(
        """INSERT INTO impetus_fabric.schema_metadata (component, version) VALUES ('fabric', %s)
        ON CONFLICT (component) DO NOTHING""",
        (_SCHEMA_VERSION,),
    )
    version = connection.execute(
        "SELECT version FROM impetus_fabric.schema_metadata WHERE component = 'fabric'"
    ).fetchone()
    if version is None or version[0] != _SCHEMA_VERSION:
        found = None if version is None else version[0]
        raise RuntimeError(
            f"the database speaks impetus_fabric schema version {found!r}, but this runtime requires "
            f"version {_SCHEMA_VERSION}: migrate deliberately rather than upgrading implicitly at boot"
        )


def register_process(connection, instance: str, credential: str) -> None:
    """Trusted-operator bootstrap. Stores only the SHA-256 credential digest."""
    instance = _text(instance, "instance")
    digest = _credential_digest(_credential(credential))
    cursor = connection.execute(
        "INSERT INTO impetus_fabric.processes (instance_id, credential_digest) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (instance, digest),
    )
    if cursor.rowcount:
        log.emit("fabric_registered", instance=instance)
        return
    row = connection.execute(
        "SELECT credential_digest FROM impetus_fabric.processes WHERE instance_id = %s", (instance,)
    ).fetchone()
    if row is None or not hmac.compare_digest(row[0], digest):
        log.emit("fabric_conflict", operation="register", instance=instance)
        raise ValueError(f"process {instance!r} is already registered with a different credential")


class PostgresFabric:
    """Authenticated fabric client using, but never silently committing, the caller's connection."""

    def __init__(self, connection, instance: str, credential: str):
        self._connection = connection
        self.instance = _text(instance, "instance")
        self._credential_digest = _credential_digest(_credential(credential))

    def _auth(self) -> None:
        row = self._connection.execute(
            "SELECT credential_digest FROM impetus_fabric.processes WHERE instance_id = %s", (self.instance,)
        ).fetchone()
        if row is None or not hmac.compare_digest(row[0], self._credential_digest):
            log.emit("fabric_denied", operation="authenticate", instance=self.instance)
            raise PermissionError(f"fabric authentication failed for {self.instance!r}")

    def authenticate(self) -> None:
        """Verify this bound process identity for higher protocol layers."""
        self._auth()

    def _transaction(self):
        return self._connection.transaction() if self._connection.autocommit else contextlib.nullcontext()

    def expose_source(self, source: str) -> None:
        source = _text(source, "source")
        self._auth()
        self._connection.execute(
            "INSERT INTO impetus_fabric.exposed_sources (instance_id, source) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (self.instance, source),
        )
        log.emit("fabric_exposed", instance=self.instance, source=source)

    def offer_service(self, source: str, service: str, capabilities: dict[str, object]) -> None:
        source, service = _text(source, "source"), _text(service, "service")
        if not isinstance(capabilities, dict):
            raise TypeError("capabilities must be a JSON object")
        snapshot = _json_copy(capabilities, "capabilities")
        self._auth()
        self._connection.execute(
            """INSERT INTO impetus_fabric.service_offers (instance_id, source, service, capabilities)
            VALUES (%s, %s, %s, %s) ON CONFLICT (instance_id, source, service)
            DO UPDATE SET capabilities = EXCLUDED.capabilities, offered_at = clock_timestamp()""",
            (self.instance, source, service, Jsonb(snapshot)),
        )
        log.emit("fabric_offered", instance=self.instance, source=source, service=service)

    def grant(self, sender: str, source: str) -> None:
        sender, source = _text(sender, "sender"), _text(source, "source")
        self._auth()
        self._connection.execute(
            "INSERT INTO impetus_fabric.delivery_grants (sender, recipient, source) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
            (sender, self.instance, source),
        )
        log.emit("fabric_granted", sender=sender, recipient=self.instance, source=source)

    def revoke(self, sender: str, source: str) -> None:
        sender, source = _text(sender, "sender"), _text(source, "source")
        self._auth()
        self._connection.execute(
            "DELETE FROM impetus_fabric.delivery_grants WHERE sender = %s AND recipient = %s AND source = %s",
            (sender, self.instance, source),
        )

    def discover(self, service: str, capabilities: dict[str, object] | None = None) -> tuple[Endpoint, ...]:
        service = _text(service, "service")
        wanted = {} if capabilities is None else capabilities
        if not isinstance(wanted, dict):
            raise TypeError("capabilities must be a JSON object")
        wanted = _json_copy(wanted, "capabilities")
        self._auth()
        rows = self._connection.execute(
            """SELECT o.instance_id, o.source, o.capabilities FROM impetus_fabric.service_offers o
            JOIN impetus_fabric.delivery_grants g ON (g.recipient, g.source) = (o.instance_id, o.source)
            WHERE g.sender = %s AND o.service = %s AND o.capabilities @> %s
            ORDER BY o.instance_id, o.source""",
            (self.instance, service, Jsonb(wanted)),
        ).fetchall()
        return tuple(Endpoint(recipient=row[0], source=row[1], capabilities=row[2]) for row in rows)

    def _prior_submission(self, envelope: Envelope, prior) -> Submission:
        if not hmac.compare_digest(prior[0], envelope.digest):
            log.emit(
                "fabric_conflict",
                operation="submit",
                sender=self.instance,
                recipient=envelope.recipient,
                source=envelope.source,
                correlation=envelope.correlation,
                delivery_id=envelope.delivery_id,
            )
            raise ValueError(
                f"fabric delivery identity conflict for ({self.instance!r}, {envelope.delivery_id!r}): "
                "content or address changed"
            )
        state = "accepted" if prior[2] is not None else "pending"
        log.emit(
            "fabric_redelivered",
            sender=self.instance,
            recipient=envelope.recipient,
            source=envelope.source,
            correlation=envelope.correlation,
            delivery_id=envelope.delivery_id,
            state=state,
        )
        return Submission(self.instance, envelope.delivery_id, state, True, prior[1], prior[2])

    def submit(self, envelope: Envelope) -> Submission:
        if not isinstance(envelope, Envelope):
            raise TypeError("submit requires an Envelope")
        if envelope.sender != self.instance:
            raise PermissionError("envelope sender must match the authenticated fabric client")
        # Envelope construction has already detached and canonicalized all input.
        self._auth()
        with self._transaction():
            prior = self._connection.execute(
                """SELECT digest, accepted_occurrence, accepted_at FROM impetus_fabric.deliveries
                WHERE sender = %s AND delivery_id = %s FOR UPDATE""",
                (self.instance, envelope.delivery_id),
            ).fetchone()
            if prior is not None:
                return self._prior_submission(envelope, prior)
            allowed = self._connection.execute(
                """SELECT 1 FROM impetus_fabric.exposed_sources e JOIN impetus_fabric.delivery_grants g
                ON (g.recipient, g.source) = (e.instance_id, e.source)
                WHERE e.instance_id = %s AND e.source = %s AND g.sender = %s""",
                (envelope.recipient, envelope.source, self.instance),
            ).fetchone()
            if allowed is None:
                log.emit(
                    "fabric_denied",
                    operation="submit",
                    sender=self.instance,
                    recipient=envelope.recipient,
                    source=envelope.source,
                    correlation=envelope.correlation,
                    delivery_id=envelope.delivery_id,
                )
                raise PermissionError("recipient source is not exposed and granted to this sender")
            inserted = self._connection.execute(
                """INSERT INTO impetus_fabric.deliveries
                (sender, delivery_id, recipient, source, correlation, envelope, digest)
                VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                (
                    self.instance,
                    envelope.delivery_id,
                    envelope.recipient,
                    envelope.source,
                    envelope.correlation,
                    Jsonb(envelope.to_data()),
                    envelope.digest,
                ),
            )
            # A concurrent submit may have won after the first read. PostgreSQL
            # waits for it here; verify its full identity exactly as any retry.
            if inserted.rowcount == 0:
                prior = self._connection.execute(
                    """SELECT digest, accepted_occurrence, accepted_at FROM impetus_fabric.deliveries
                    WHERE sender = %s AND delivery_id = %s FOR UPDATE""",
                    (self.instance, envelope.delivery_id),
                ).fetchone()
                return self._prior_submission(envelope, prior)
            self._connection.execute("SELECT pg_notify('impetus_fabric_delivery', %s)", (envelope.recipient,))
        log.emit(
            "fabric_submitted",
            sender=self.instance,
            recipient=envelope.recipient,
            source=envelope.source,
            correlation=envelope.correlation,
            delivery_id=envelope.delivery_id,
        )
        return Submission(self.instance, envelope.delivery_id, "pending", False)

    send = submit

    def pending(self, limit: int = 100) -> tuple[Envelope, ...]:
        if type(limit) is not int or limit < 1:
            raise ValueError("limit must be a positive integer")
        self._auth()
        rows = self._connection.execute(
            """SELECT envelope FROM impetus_fabric.deliveries WHERE recipient = %s AND accepted_at IS NULL
            ORDER BY submitted_at, sender, delivery_id LIMIT %s""",
            (self.instance, limit),
        ).fetchall()
        return tuple(Envelope.from_data(row[0]) for row in rows)

    def acknowledge(self, sender: str, delivery_id: str, occurrence: int) -> Receipt:
        sender, delivery_id = _text(sender, "sender"), _text(delivery_id, "delivery_id")
        if type(occurrence) is not int or occurrence < 1:
            raise ValueError("occurrence must be a positive integer")
        self._auth()
        with self._transaction():
            row = self._connection.execute(
                """SELECT recipient, source, correlation, digest, accepted_occurrence, accepted_at,
                envelope IS NOT NULL
                FROM impetus_fabric.deliveries WHERE sender = %s AND delivery_id = %s AND recipient = %s FOR UPDATE""",
                (sender, delivery_id, self.instance),
            ).fetchone()
            if row is None:
                raise LookupError(f"pending delivery ({sender!r}, {delivery_id!r}) does not exist for this recipient")
            if row[4] is not None and row[4] != occurrence:
                log.emit(
                    "fabric_conflict",
                    operation="acknowledge",
                    sender=sender,
                    recipient=self.instance,
                    source=row[1],
                    correlation=row[2],
                    delivery_id=delivery_id,
                )
                raise ValueError(f"delivery was already accepted by occurrence {row[4]}, not {occurrence}")
            if row[4] is None:
                accepted_at = self._connection.execute(
                    """UPDATE impetus_fabric.deliveries SET accepted_occurrence = %s, accepted_at = clock_timestamp()
                    WHERE sender = %s AND delivery_id = %s RETURNING accepted_at""",
                    (occurrence, sender, delivery_id),
                ).fetchone()[0]
                row = (*row[:4], occurrence, accepted_at, row[6])
        log.emit(
            "fabric_accepted",
            sender=sender,
            recipient=self.instance,
            source=row[1],
            correlation=row[2],
            delivery_id=delivery_id,
            occurrence=occurrence,
        )
        # Psycopg's heterogeneous row is dynamically typed at this SQL boundary.
        return Receipt(sender, delivery_id, row[0], row[1], row[3], "accepted", occurrence, row[5], row[6])  # ty: ignore[invalid-argument-type]

    def receipt(self, delivery_id: str) -> Receipt | None:
        delivery_id = _text(delivery_id, "delivery_id")
        self._auth()
        row = self._connection.execute(
            """SELECT recipient, source, digest, accepted_occurrence, accepted_at, envelope IS NOT NULL
            FROM impetus_fabric.deliveries WHERE sender = %s AND delivery_id = %s""",
            (self.instance, delivery_id),
        ).fetchone()
        if row is None:
            return None
        return Receipt(
            self.instance,
            delivery_id,
            row[0],
            row[1],
            row[2],
            "accepted" if row[4] is not None else "pending",
            row[3],
            row[4],
            row[5],
        )

    def prune_accepted(self, before: datetime) -> int:
        if not isinstance(before, datetime) or before.tzinfo is None or before.utcoffset() is None:
            raise ValueError("pruning cutoff must be a timezone-aware datetime")
        self._auth()
        cursor = self._connection.execute(
            """UPDATE impetus_fabric.deliveries SET envelope = NULL
            WHERE recipient = %s AND accepted_at < %s AND envelope IS NOT NULL""",
            (self.instance, before),
        )
        log.emit("fabric_pruned", instance=self.instance, deliveries=cursor.rowcount)
        return cursor.rowcount
