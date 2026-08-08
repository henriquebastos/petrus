"""Focused public-contract tests for PostgreSQL Fabric."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest

import psycopg

from petrus.fabric import MAX_INLINE_PAYLOAD_BYTES, Endpoint, Envelope, Receipt, ReplyRoute, Submission
from petrus.fabric.ingress import FABRIC_ENVELOPE, FabricInbox
from petrus.fabric.postgres import (
    PostgresFabric,
    ensure_fabric_schema,
    issue_credential,
    register_process,
)
from petrus.impetus.instance import FiringOutcome
from petrus.impetus.instance import PriorAcknowledgement
from petrus.impetus.petrinet import NetPath, Token
from tests import REPO_ROOT


def test_neutral_fabric_import_does_not_attempt_psycopg():
    code = """
import builtins
original_import = builtins.__import__
def guarded_import(name, *args, **kwargs):
    if name == "psycopg" or name.startswith("psycopg."):
        raise AssertionError(f"neutral Fabric import attempted {name}")
    return original_import(name, *args, **kwargs)
builtins.__import__ = guarded_import
from petrus.fabric import Envelope, ReplyRoute
assert Envelope is not None and ReplyRoute is not None
"""
    result = subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.fixture(autouse=True)
def fabric_schema(pg_connection):
    pg_connection.execute("DROP SCHEMA IF EXISTS impetus_fabric CASCADE")
    ensure_fabric_schema(pg_connection)
    ensure_fabric_schema(pg_connection)
    yield
    pg_connection.execute("DROP SCHEMA IF EXISTS impetus_fabric CASCADE")
    ensure_fabric_schema(pg_connection)


def test_two_authority_process_fabric_acceptance_demo(postgres_dsn):
    result = subprocess.run(
        [sys.executable, "scripts/cv5-fabric-demo.py", "--dsn", postgres_dsn],
        cwd=REPO_ROOT,
        env={**os.environ, "UV_FROZEN": "1"},
        capture_output=True,
        text=True,
        timeout=90,
    )
    evidence = result.stdout + "\n--- stderr ---\n" + result.stderr
    assert result.returncode == 0, evidence
    assert "overall: PASS" in result.stdout, evidence
    assert "offline pending count: 1" in result.stdout, evidence
    assert "parent: awaiting -> completed" in result.stdout, evidence
    assert "replay: parent appends=0 invocations=0; child appends=0 invocations=0" in result.stdout, evidence
    assert "in-flight crash resume: occurrence=" in result.stdout, evidence
    assert "dispatches=1 completed=true" in result.stdout, evidence
    assert "local/split semantic-shape equality: true" in result.stdout, evidence


@pytest.fixture
def parties(pg_connection):
    credentials = {name: issue_credential() for name in ("sender-a", "sender-b", "recipient")}
    for name, credential in credentials.items():
        register_process(pg_connection, name, credential)
    return {name: PostgresFabric(pg_connection, name, credential) for name, credential in credentials.items()}


def envelope(sender="sender-a", delivery_id="delivery-1", payload=None):
    return Envelope(
        delivery_id=delivery_id,
        sender=sender,
        recipient="recipient",
        source="commands/start",
        correlation="conversation-1",
        payload={"command": "go"} if payload is None else payload,
        reply_route=ReplyRoute(sender, "replies/finish"),
    )


def open_route(parties):
    recipient = parties["recipient"]
    recipient.expose_source("commands/start")
    recipient.offer_service("commands/start", "worker", {"model": "large", "tools": ["shell"]})
    recipient.grant("sender-a", "commands/start")


def test_envelope_is_exact_versioned_detached_strict_json_and_bounded():
    payload = {"nested": [1, {"ok": True}]}
    item = envelope(payload=payload)
    payload["nested"][1]["ok"] = False
    assert item.to_data()["payload"] == {"nested": [1, {"ok": True}]}
    with pytest.raises(TypeError):
        item.payload["new"] = "mutation"
    with pytest.raises(TypeError):
        item.payload["nested"][1]["ok"] = False
    assert Envelope.from_data(item.to_data()) == item
    assert item.to_data()["version"] == 1
    assert len(item.digest) == 64
    assert item.ingress_identity == "fabric:8:sender-a:delivery-1"

    for changed in (
        {**item.to_data(), "version": 2},
        {key: value for key, value in item.to_data().items() if key != "source"},
        {**item.to_data(), "extra": True},
        {**item.to_data(), "source": 3},
    ):
        with pytest.raises((TypeError, ValueError)):
            Envelope.from_data(changed)
    with pytest.raises(ValueError, match="unknown"):
        Envelope.from_data({**item.to_data(), 7: "non-text key"})
    with pytest.raises(ValueError, match="strict JSON"):
        envelope(payload={"bad": float("nan")})
    with pytest.raises(TypeError, match=r"payload\.items\[0\]"):
        envelope(payload={"items": [object()]})
    with pytest.raises(ValueError, match="artifact protocol"):
        envelope(payload={"bytes": "x" * (MAX_INLINE_PAYLOAD_BYTES + 1)})


def test_registration_stores_only_digest_is_idempotent_and_authenticates(pg_connection):
    credential = issue_credential()
    assert len(credential.encode()) >= 32
    register_process(pg_connection, "process", credential)
    register_process(pg_connection, "process", credential)
    [(stored,)] = pg_connection.execute(
        "SELECT credential_digest FROM impetus_fabric.processes WHERE instance_id = 'process'"
    ).fetchall()
    assert credential not in stored
    assert len(stored) == 64
    with pytest.raises(ValueError, match="different credential"):
        register_process(pg_connection, "process", issue_credential())
    with pytest.raises(ValueError, match="high-entropy"):
        register_process(pg_connection, "weak", "x" * 40)
    with pytest.raises(PermissionError, match="authentication failed"):
        PostgresFabric(pg_connection, "process", issue_credential()).discover("anything")


def test_schema_provisioning_refuses_unknown_or_mismatched_versions(pg_connection):
    pg_connection.execute("DROP SCHEMA impetus_fabric CASCADE")
    pg_connection.execute("CREATE SCHEMA impetus_fabric")
    pg_connection.execute("CREATE TABLE impetus_fabric.processes (unknown_shape text)")
    with pytest.raises(RuntimeError, match="unversioned table.*refusing"):
        ensure_fabric_schema(pg_connection)

    pg_connection.execute("DROP SCHEMA impetus_fabric CASCADE")
    ensure_fabric_schema(pg_connection)
    pg_connection.execute("UPDATE impetus_fabric.schema_metadata SET version = 999 WHERE component = 'fabric'")
    with pytest.raises(RuntimeError, match="version 999.*migrate deliberately"):
        ensure_fabric_schema(pg_connection)


def test_fabric_operations_join_a_caller_transaction_without_committing(postgres_dsn, pg_connection):
    credential = issue_credential()
    register_process(pg_connection, "joined", credential)
    joined = psycopg.connect(postgres_dsn, autocommit=False)
    try:
        PostgresFabric(joined, "joined", credential).expose_source("inbox")
        assert (
            pg_connection.execute(
                "SELECT count(*) FROM impetus_fabric.exposed_sources WHERE instance_id = 'joined'"
            ).fetchone()[0]
            == 0
        )
        joined.rollback()
        assert (
            pg_connection.execute(
                "SELECT count(*) FROM impetus_fabric.exposed_sources WHERE instance_id = 'joined'"
            ).fetchone()[0]
            == 0
        )

        PostgresFabric(joined, "joined", credential).expose_source("inbox")
        joined.commit()
        assert (
            pg_connection.execute(
                "SELECT count(*) FROM impetus_fabric.exposed_sources WHERE instance_id = 'joined'"
            ).fetchone()[0]
            == 1
        )
    finally:
        joined.close()


def test_discovery_and_send_are_deny_by_default_and_capability_filtered(parties):
    sender, recipient = parties["sender-a"], parties["recipient"]
    recipient.expose_source("commands/start")
    recipient.offer_service("commands/start", "worker", {"model": "large", "region": "eu"})
    assert sender.discover("worker") == ()
    with pytest.raises(PermissionError, match="not exposed and granted"):
        sender.submit(envelope())

    recipient.grant("sender-a", "commands/start")
    assert sender.discover("worker", {"model": "large"}) == (
        Endpoint("recipient", "commands/start", {"model": "large", "region": "eu"}),
    )
    assert sender.discover("worker", {"model": "small"}) == ()
    assert sender.submit(envelope()) == Submission("sender-a", "delivery-1", "pending", False)


def test_exact_retransmission_precedes_current_grant_and_changed_content_conflicts(parties):
    open_route(parties)
    sender, recipient = parties["sender-a"], parties["recipient"]
    first = sender.send(envelope())
    recipient.revoke("sender-a", "commands/start")
    assert first.duplicate is False
    assert sender.send(envelope()) == Submission("sender-a", "delivery-1", "pending", True)
    with pytest.raises(ValueError, match="identity conflict"):
        sender.send(envelope(payload={"command": "changed"}))
    with pytest.raises(PermissionError):
        sender.send(envelope(delivery_id="delivery-2"))


def test_same_delivery_id_from_distinct_senders_has_distinct_ingress_identity(parties):
    recipient = parties["recipient"]
    recipient.expose_source("commands/start")
    recipient.grant("sender-a", "commands/start")
    recipient.grant("sender-b", "commands/start")
    parties["sender-a"].send(envelope(sender="sender-a", delivery_id="same"))
    parties["sender-b"].send(envelope(sender="sender-b", delivery_id="same"))
    identities = {item.ingress_identity for item in recipient.pending()}
    assert identities == {"fabric:8:sender-a:same", "fabric:8:sender-b:same"}


class FakeDoor:
    def __init__(self):
        self.calls = []
        self.prior = False

    def deliver(self, source, tokens, *, identity):
        self.calls.append((source, tokens, identity))
        if self.prior:
            return PriorAcknowledgement(identity, 7)
        return FiringOutcome(NetPath(source), 7, (), (), ())


def test_inbox_delivery_acceptance_and_prior_acknowledgement_crash_recovery(parties):
    open_route(parties)
    parties["sender-a"].send(envelope())
    door = FakeDoor()
    inbox = FabricInbox(parties["recipient"], door)

    # Simulate the crash window: semantic delivery happened, fabric acknowledgement did not.
    [pending] = parties["recipient"].pending()
    result = door.deliver(
        pending.source,
        (Token(FABRIC_ENVELOPE, pending.to_data()),),
        identity=pending.ingress_identity,
    )
    assert result.occurrence == 7
    door.prior = True
    [accepted] = inbox.drain()
    assert accepted.state == "accepted"
    assert accepted.occurrence == 7
    assert parties["recipient"].pending() == ()
    source, [token], identity = door.calls[-1]
    assert (source, token.color, identity) == (
        "commands/start",
        FABRIC_ENVELOPE,
        "fabric:8:sender-a:delivery-1",
    )


def test_acknowledgement_occurrence_conflicts(parties):
    open_route(parties)
    parties["sender-a"].send(envelope())
    recipient = parties["recipient"]
    assert recipient.acknowledge("sender-a", "delivery-1", 4).occurrence == 4
    assert recipient.acknowledge("sender-a", "delivery-1", 4).occurrence == 4
    with pytest.raises(ValueError, match="already accepted by occurrence 4"):
        recipient.acknowledge("sender-a", "delivery-1", 5)
    with pytest.raises(ValueError, match="positive integer"):
        recipient.acknowledge("sender-a", "delivery-1", 0)


def test_pruning_removes_envelope_but_preserves_receipt_dedup_and_conflict(pg_connection, parties):
    open_route(parties)
    sender, recipient = parties["sender-a"], parties["recipient"]
    item = envelope(payload={"secret-inline-bytes": "do-not-retain"})
    sender.send(item)
    recipient.acknowledge("sender-a", "delivery-1", 9)
    with pytest.raises(ValueError, match="timezone-aware"):
        recipient.prune_accepted(datetime.now())
    assert recipient.prune_accepted(datetime.now(timezone.utc) + timedelta(seconds=1)) == 1

    receipt = sender.receipt("delivery-1")
    assert receipt == Receipt(
        "sender-a",
        "delivery-1",
        "recipient",
        "commands/start",
        item.digest,
        "accepted",
        9,
        receipt.accepted_at,
        False,
    )
    [(stored_envelope, stored_digest)] = pg_connection.execute(
        "SELECT envelope, digest FROM impetus_fabric.deliveries WHERE sender = 'sender-a' AND delivery_id = 'delivery-1'"
    ).fetchall()
    assert stored_envelope is None
    assert stored_digest == item.digest
    duplicate = sender.send(item)
    assert (duplicate.state, duplicate.duplicate, duplicate.occurrence) == ("accepted", True, 9)
    with pytest.raises(ValueError, match="identity conflict"):
        sender.send(envelope(payload={"secret-inline-bytes": "changed"}))
