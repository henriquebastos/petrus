"""Authenticated PostgreSQL spawn-lineage registry."""

from __future__ import annotations

try:
    import psycopg  # noqa: F401
except ImportError as _psycopg_missing:
    raise ImportError(
        "petrus.processes.postgres needs psycopg, which ships in the optional 'postgres' extra: "
        "install petrus-runtime[postgres] (e.g. `uv add 'petrus-runtime[postgres]'` or `pip install 'petrus-runtime[postgres]'`)"
    ) from _psycopg_missing

import petrus.telemetry as telemetry
from petrus.fabric.model import _text
from petrus.fabric.postgres import PostgresFabric
from petrus.processes.model import Lineage, SpawnClaim, SpawnSpec

_SCHEMA_VERSION = 1
log = telemetry.get_logger("impetus")
_DDL = (
    "CREATE SCHEMA IF NOT EXISTS impetus_lifecycle",
    "CREATE TABLE IF NOT EXISTS impetus_lifecycle.schema_metadata (component text PRIMARY KEY, version integer NOT NULL)",
    """CREATE TABLE IF NOT EXISTS impetus_lifecycle.spawns (
        parent text NOT NULL, spawn_id text NOT NULL, child text NOT NULL UNIQUE,
        spec_digest text NOT NULL, created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        PRIMARY KEY (parent, spawn_id))""",
)


def ensure_lifecycle_schema(connection) -> None:
    """Provision lifecycle protocol state without committing the caller's transaction."""
    exists = connection.execute("SELECT 1 FROM pg_namespace WHERE nspname = 'impetus_lifecycle'").fetchone()
    if exists and connection.execute("SELECT to_regclass('impetus_lifecycle.schema_metadata')").fetchone()[0] is None:
        known = connection.execute("SELECT to_regclass('impetus_lifecycle.spawns')").fetchone()[0]
        if known is not None:
            raise RuntimeError(
                "the impetus_lifecycle schema contains an unversioned spawns table: refusing unknown shape"
            )
    for statement in _DDL:
        connection.execute(statement)
    connection.execute(
        """INSERT INTO impetus_lifecycle.schema_metadata (component, version)
        VALUES ('lifecycle', %s) ON CONFLICT DO NOTHING""",
        (_SCHEMA_VERSION,),
    )
    row = connection.execute(
        "SELECT version FROM impetus_lifecycle.schema_metadata WHERE component = 'lifecycle'"
    ).fetchone()
    if row is None or row[0] != _SCHEMA_VERSION:
        raise RuntimeError(
            f"the database speaks impetus_lifecycle schema version {None if row is None else row[0]!r}, but this runtime requires version 1; migrate deliberately"
        )


class PostgresSpawnRegistry:
    """Parent-bound registry; every claim is committed before it returns."""

    def __init__(self, connection, parent: str, credential: str):
        if not connection.autocommit:
            raise ValueError("PostgresSpawnRegistry requires an autocommit connection")
        self._connection = connection
        self.parent = _text(parent, "parent")
        self._fabric = PostgresFabric(connection, self.parent, credential)

    def _auth(self) -> None:
        try:
            self._fabric.authenticate()
        except PermissionError:
            log.emit("lifecycle_denied", operation="authenticate", instance=self.parent)
            raise PermissionError(f"lifecycle authentication failed for {self.parent!r}") from None

    def claim(self, spec: SpawnSpec) -> SpawnClaim:
        if not isinstance(spec, SpawnSpec):
            raise TypeError("claim requires SpawnSpec")
        if spec.parent != self.parent:
            raise PermissionError("spawn parent must match the authenticated registry")
        self._auth()
        cursor = self._connection.execute(
            "INSERT INTO impetus_lifecycle.spawns (parent, spawn_id, child, spec_digest) VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (spec.parent, spec.spawn_id, spec.child, spec.digest),
        )
        row = self._connection.execute(
            "SELECT child, spec_digest FROM impetus_lifecycle.spawns WHERE parent = %s AND spawn_id = %s",
            (spec.parent, spec.spawn_id),
        ).fetchone()
        if row is None or row != (spec.child, spec.digest):
            log.emit("lifecycle_conflict", operation="spawn", parent=spec.parent, spawn_id=spec.spawn_id)
            raise ValueError(f"spawn identity conflict for ({spec.parent!r}, {spec.spawn_id!r}): content changed")
        log.emit(
            "lifecycle_claimed",
            parent=spec.parent,
            spawn_id=spec.spawn_id,
            child=row[0],
            prior_claim=cursor.rowcount == 0,
        )
        return SpawnClaim(spec.parent, spec.spawn_id, row[0], cursor.rowcount == 0)

    def child_of(self, parent: str, spawn_id: str) -> Lineage | None:
        parent, spawn_id = _text(parent, "parent"), _text(spawn_id, "spawn_id")
        self._auth_bound(parent)
        row = self._connection.execute(
            "SELECT child FROM impetus_lifecycle.spawns WHERE parent = %s AND spawn_id = %s", (parent, spawn_id)
        ).fetchone()
        return None if row is None else Lineage(parent, spawn_id, row[0])

    def children_of(self, parent: str) -> tuple[Lineage, ...]:
        parent = _text(parent, "parent")
        self._auth_bound(parent)
        rows = self._connection.execute(
            "SELECT spawn_id, child FROM impetus_lifecycle.spawns WHERE parent = %s ORDER BY spawn_id", (parent,)
        ).fetchall()
        return tuple(Lineage(parent, row[0], row[1]) for row in rows)

    def parent_of(self, child: str) -> Lineage | None:
        child = _text(child, "child")
        self._auth()
        row = self._connection.execute(
            "SELECT parent, spawn_id FROM impetus_lifecycle.spawns WHERE child = %s", (child,)
        ).fetchone()
        if row is None:
            return None
        if row[0] != self.parent:
            raise PermissionError("child does not belong to the authenticated parent")
        return Lineage(row[0], row[1], child)

    def _auth_bound(self, parent: str) -> None:
        if parent != self.parent:
            raise PermissionError("lineage parent must match the authenticated registry")
        self._auth()
