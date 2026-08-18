"""Disposable PostgreSQL database support for provider-backed DST profiles."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from petrus.impetus.history_store.postgres import ensure_schema
from petrus.motus.dispatch.absurd import ensure_absurd_schema


@contextmanager
def isolated_absurd_database(server_dsn: str) -> Iterator[str]:
    """Provision and destroy one empty database on the test session's server."""

    database = f"petrus_dst_{uuid4().hex}"
    parameters = conninfo_to_dict(server_dsn)
    isolated_dsn = make_conninfo(**{**parameters, "dbname": database})
    with psycopg.connect(server_dsn, autocommit=True) as administration:
        administration.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    try:
        with psycopg.connect(isolated_dsn, autocommit=True) as connection:
            ensure_schema(connection)
            ensure_absurd_schema(connection)
        yield isolated_dsn
    finally:
        with psycopg.connect(server_dsn, autocommit=True) as administration:
            administration.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))
