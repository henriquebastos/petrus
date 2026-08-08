"""
Shared test provisioning for the test suite.

The one shared resource is the ephemeral PostgreSQL the DS3 backend tests run
against — provisioned per the ES-009 harness practice (the absurd-full-matrix
compose shape, testcontainer-free): the digest-pinned image the evidence ran
on and tmpfs-backed data (disposable by construction). Each pytest-xdist
worker gets one container on its own Docker-assigned 127.0.0.1 port, distinct
from the ES-009 tracks' fixed ports (55521/55447). The suite FAILS LOUD — never
silently skips — when docker is genuinely required and absent: a skipped
Postgres suite would report a green bar the durable backend never earned
[CV3.DS3 scope].
"""

from __future__ import annotations

# Python imports
import os
import subprocess
import time

# Pip imports
import pytest

# The exact image digest the ES-009 evidence pinned (native control, absurd
# probe and matrix): re-pinning is a deliberate act, never a drive-by.
POSTGRES_IMAGE = "postgres:17.5-alpine@sha256:6567bca8d7bc8c82c5922425a0baee57be8402df92bae5eacad5f01ae9544daa"
# Every container this fixture starts carries this label, so a session killed
# too hard for teardown (SIGKILL) leaves a stale container the NEXT session
# recognizes and removes before binding the port.
CONTAINER_LABEL = "petrus-cv3-test"
_SKIPPED_NODE_IDS: set[str] = set()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--forbid-skips",
        action="store_true",
        help="Fail the session if any selected test skips instead of passing or failing.",
    )


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if report.skipped:
        _SKIPPED_NODE_IDS.add(report.nodeid)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int | pytest.ExitCode) -> None:
    if session.config.getoption("--forbid-skips") and _SKIPPED_NODE_IDS and exitstatus == pytest.ExitCode.OK:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(terminalreporter: pytest.TerminalReporter) -> None:
    if terminalreporter.config.getoption("--forbid-skips") and _SKIPPED_NODE_IDS:
        terminalreporter.write_sep("=", f"forbidden skips: {len(_SKIPPED_NODE_IDS)}")
        for node_id in sorted(_SKIPPED_NODE_IDS):
            terminalreporter.write_line(node_id)


def _docker(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check)


@pytest.fixture(scope="session")
def postgres_dsn():
    """DSN of a session-scoped ephemeral PostgreSQL — started here, torn down here, state on tmpfs."""
    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    label = CONTAINER_LABEL if worker in {"main", "gw0"} else f"{CONTAINER_LABEL}-{worker}"
    try:
        _docker("info")
    except (FileNotFoundError, subprocess.CalledProcessError) as error:
        pytest.fail(
            f"the PostgreSQL backend tests need docker, and it is unavailable ({error}): "
            f"start docker or run without the DS3 suite — a silent skip is not a pass",
            pytrace=False,
        )
    # Clean stale labeled containers from a session that died before teardown.
    stale = _docker("ps", "--all", "--quiet", "--filter", f"label={label}", check=False)
    for container in stale.stdout.split():
        _docker("rm", "--force", container, check=False)
    name = f"petrus-cv3-postgres-{worker}-{os.getpid()}"
    run = _docker(
        "run",
        "--rm",
        "--detach",
        "--name",
        name,
        "--label",
        label,
        "--publish",
        "127.0.0.1::5432",
        "--env",
        "POSTGRES_PASSWORD=postgres",
        "--tmpfs",
        "/var/lib/postgresql/data",
        POSTGRES_IMAGE,
        check=False,
    )
    if run.returncode != 0:
        pytest.fail(
            f"could not start the ephemeral PostgreSQL container ({run.stderr.strip()})",
            pytrace=False,
        )
    published = _docker("port", name, "5432/tcp", check=False)
    try:
        port = int(published.stdout.strip().rsplit(":", 1)[1])
    except IndexError, ValueError:
        _docker("stop", name, check=False)
        pytest.fail(f"could not discover the PostgreSQL container port ({published.stderr.strip()})", pytrace=False)
    try:
        deadline = time.monotonic() + 60
        # pg_isready inside the container, then a real connection from the
        # host: the server accepts local connections a beat before the
        # published port does.
        while True:
            ready = _docker("exec", name, "pg_isready", "-U", "postgres", check=False)
            if ready.returncode == 0:
                break
            if time.monotonic() > deadline:
                pytest.fail(f"PostgreSQL never became ready within 60s: {ready.stdout} {ready.stderr}", pytrace=False)
            time.sleep(0.2)
        dsn = f"postgres://postgres:postgres@127.0.0.1:{port}/postgres"
        import psycopg

        while True:
            try:
                psycopg.connect(dsn, connect_timeout=3).close()
                break
            except psycopg.OperationalError as error:
                if time.monotonic() > deadline:
                    pytest.fail(f"PostgreSQL port never accepted a connection within 60s: {error}", pytrace=False)
                time.sleep(0.2)
        yield dsn
    finally:
        _docker("stop", name, check=False)


@pytest.fixture(scope="session")
def absurd_dsn(postgres_dsn):
    """The session database with BOTH schemas provisioned — the ES-009 co-residence shape: the Impetus canonical history and the pinned Absurd engine in one database, which is what lets DS4's dispatch join one transaction."""
    import psycopg

    from petrus.motus.dispatch.absurd import ensure_absurd_schema
    from petrus.impetus.history_store.postgres import ensure_schema

    with psycopg.connect(postgres_dsn, autocommit=True) as connection:
        ensure_schema(connection)
        ensure_absurd_schema(connection)
    return postgres_dsn


@pytest.fixture
def pg_connection(postgres_dsn):
    """A fresh autocommit connection with the Impetus schema ensured — the backend-owned-transaction posture."""
    # Internal import lives here so collecting the suite without the postgres
    # extra still fails at USE (loud, naming the extra via petrus.impetus.history_store.postgres),
    # not at collection of unrelated tests.
    import psycopg

    from petrus.impetus.history_store.postgres import ensure_schema

    connection = psycopg.connect(postgres_dsn, autocommit=True)
    ensure_schema(connection)
    yield connection
    connection.close()
