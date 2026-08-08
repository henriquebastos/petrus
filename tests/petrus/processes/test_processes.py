"""Process lifecycle contracts above Fabric."""

from __future__ import annotations

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest

from petrus.motus.activity import ActivityInvocation
from petrus.fabric import Endpoint, Envelope, ReplyRoute
from petrus.fabric.postgres import ensure_fabric_schema, issue_credential, register_process
from petrus.processes import (
    CallError,
    CallRequest,
    CallResult,
    Lineage,
    Provisioning,
    SpawnClaim,
    SpawnOutcome,
    SpawnSpec,
    child_identity,
    error_envelope,
    reply_from_envelope,
    request_envelope,
    result_envelope,
)
from petrus.processes.postgres import PostgresSpawnRegistry, ensure_lifecycle_schema
from petrus.processes.spawn import SPAWN_ACTIVITY, SpawnActivity, spawn_idempotency
from tests import REPO_ROOT


def spec(parent: str = "parent", spawn_id: str = "spawn-1", **changes) -> SpawnSpec:
    values = {
        "parent": parent,
        "spawn_id": spawn_id,
        "process_kind": "analysis-agent",
        "source": "calls",
        "capabilities": {"protocol": "call-v1", "features": ["reply"]},
        "config": {"model": "deterministic", "tools": ["read"]},
        "reply_route": ReplyRoute(parent, "replies"),
        **changes,
    }
    return SpawnSpec(**values)


def call_request(call_id: str = "call-1") -> Envelope:
    return request_envelope(
        request=CallRequest(call_id, "answer", {"question": 42}),
        sender="parent",
        recipient="child",
        source="calls",
        reply_route=ReplyRoute("parent", "replies"),
    )


def test_neutral_process_import_attempts_neither_psycopg_nor_runtime_layers():
    code = """
import builtins
original_import = builtins.__import__
def guarded_import(name, *args, **kwargs):
    forbidden = ("psycopg",)
    if any(name == item or name.startswith(item + ".") for item in forbidden):
        raise AssertionError(f"neutral process import attempted {name}")
    return original_import(name, *args, **kwargs)
builtins.__import__ = guarded_import
from petrus.processes import CallRequest, SpawnSpec
assert CallRequest is not None and SpawnSpec is not None
"""
    result = subprocess.run([sys.executable, "-c", code], cwd=REPO_ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_spawn_spec_is_exact_detached_strict_and_fully_digested():
    config = {"nested": [1]}
    item = spec(config=config)
    config["nested"].append(2)

    assert item.to_data()["config"] == {"nested": [1]}
    with pytest.raises(TypeError):
        item.config["other"] = True
    assert SpawnSpec.from_data(item.to_data()) == item
    assert len(item.digest) == 64
    assert spec(config={"nested": [2]}).digest != item.digest
    assert spec(source="other").digest != item.digest
    assert spec(capabilities={"protocol": "call-v2"}).digest != item.digest
    with pytest.raises(ValueError, match="exact version-1"):
        SpawnSpec.from_data({**item.to_data(), "credential": "forbidden-field"})
    with pytest.raises(ValueError, match="strict JSON"):
        spec(config={"bad": float("nan")})
    with pytest.raises(ValueError, match="belong to the parent"):
        spec(reply_route=ReplyRoute("someone-else", "replies"))


def test_child_identity_is_stable_parent_scoped_and_not_spec_scoped():
    item = spec()
    assert item.child == child_identity("parent", "spawn-1")
    assert item.child == spec(process_kind="other").child
    assert item.child != child_identity("parent-2", "spawn-1")
    assert item.child != child_identity("parent", "spawn-2")
    assert item.child.startswith("process-v1-") and len(item.child) == len("process-v1-") + 64


def test_spawn_outcome_and_provisioning_refuse_cross_identity_values():
    item = spec()
    endpoint = Endpoint(item.child, item.source, item.to_data()["capabilities"])
    provisioning = Provisioning(
        item.parent,
        item.spawn_id,
        item.child,
        item.process_kind,
        endpoint,
        item.config,
        item.reply_route,
    )
    assert provisioning.config == item.config
    outcome = SpawnOutcome(item.parent, item.spawn_id, item.child, endpoint, False)
    assert SpawnOutcome.from_data(outcome.to_data()) == outcome
    with pytest.raises(ValueError, match="parent-scoped"):
        Provisioning(item.parent, item.spawn_id, "wrong", item.process_kind, endpoint, {}, item.reply_route)
    with pytest.raises(ValueError, match="address the child"):
        SpawnOutcome(item.parent, item.spawn_id, item.child, Endpoint("wrong", item.source, {}), False)
    with pytest.raises(ValueError, match="exact version-1"):
        SpawnOutcome.from_data({**outcome.to_data(), "credential": "not-public"})


def test_call_values_are_exact_detached_and_provider_neutral():
    input_data = {"nested": [1]}
    request = CallRequest("call-1", "answer", input_data)
    input_data["nested"].append(2)
    assert request.to_data()["input"] == {"nested": [1]}
    with pytest.raises(TypeError):
        request.input["new"] = True
    assert CallRequest.from_data(request.to_data()) == request
    assert CallResult.from_data(CallResult("call-1", [1, {"ok": True}]).to_data()).call_id == "call-1"
    assert CallError.from_data(CallError("call-1", "refused", "no", {"retry": False}).to_data()).code == "refused"
    with pytest.raises(ValueError, match="exact version-1"):
        CallRequest.from_data({**request.to_data(), "provider": "claude"})
    with pytest.raises(ValueError, match="strict JSON"):
        CallResult("call-1", float("inf"))


def test_call_envelopes_are_correlated_addressed_and_share_one_terminal_reply_identity():
    request = call_request()
    result = result_envelope(result=CallResult("call-1", {"answer": 42}), request=request, sender="child")
    error = error_envelope(
        error=CallError("call-1", "failed", "delegated work failed"), request=request, sender="child"
    )

    assert request.correlation == result.correlation == error.correlation == "call-1"
    assert (result.recipient, result.source) == ("parent", "replies")
    assert result.delivery_id == error.delivery_id
    assert result.digest != error.digest
    assert CallResult.from_data(result.payload).result == {"answer": 42}
    assert CallError.from_data(error.payload).message == "delegated work failed"
    assert isinstance(reply_from_envelope(result, request=request), CallResult)
    assert isinstance(reply_from_envelope(error, request=request), CallError)


def test_call_helpers_refuse_mismatched_correlation_sender_and_reply_owner():
    request = call_request()
    with pytest.raises(ValueError, match="correlate"):
        result_envelope(result=CallResult("other", None), request=request, sender="child")
    with pytest.raises(ValueError, match="correlate"):
        result_envelope(result=CallResult("call-1", None), request=request, sender="other-child")
    malformed = Envelope(
        request.delivery_id,
        request.sender,
        request.recipient,
        request.source,
        "other",
        request.to_data()["payload"],
        request.reply_route,
    )
    with pytest.raises(ValueError, match="payload.*correlation"):
        result_envelope(result=CallResult("other", None), request=malformed, sender="child")
    malformed_reply = Envelope(
        "reply",
        "child",
        "parent",
        "replies",
        "other",
        CallResult("call-1", None).to_data(),
    )
    with pytest.raises(ValueError, match="payload.*correlation"):
        reply_from_envelope(malformed_reply, request=request)
    sibling_reply = Envelope(
        result_envelope(result=CallResult("call-1", None), request=request, sender="child").delivery_id,
        "sibling",
        "parent",
        "replies",
        "call-1",
        CallResult("call-1", None).to_data(),
    )
    with pytest.raises(ValueError, match="request callee"):
        reply_from_envelope(sibling_reply, request=request)
    with pytest.raises(ValueError, match="belong to the sender"):
        request_envelope(
            request=CallRequest("call-1", "answer", {}),
            sender="parent",
            recipient="child",
            source="calls",
            reply_route=ReplyRoute("other", "replies"),
        )


def test_spawn_activity_claims_before_ensure_and_reensures_an_exact_retry():
    events = []
    item = spec()

    class Registry:
        prior = False

        def claim(self, value):
            events.append("claim")
            answer = SpawnClaim(value.parent, value.spawn_id, value.child, self.prior)
            self.prior = True
            return answer

    class Provisioner:
        def ensure(self, value):
            events.append("ensure")
            assert isinstance(value, Provisioning)
            assert not hasattr(value, "credential")

    activity = SpawnActivity(Registry(), Provisioner())
    invocation = ActivityInvocation(
        SPAWN_ACTIVITY,
        input=item.to_data(),
        idempotency=spawn_idempotency(item.parent, item.spawn_id),
    )
    first = SpawnOutcome.from_data(activity(invocation, context=None))
    second = SpawnOutcome.from_data(activity(invocation, context=None))

    assert not first.prior_claim and second.prior_claim
    assert first.child == second.child == item.child
    assert events == ["claim", "ensure", "claim", "ensure"]


def test_spawn_activity_refuses_wrong_activity_idempotency_or_registry_identity():
    item = spec()

    class Registry:
        def claim(self, _value):
            return SpawnClaim("other-parent", "other-spawn", child_identity("other-parent", "other-spawn"), False)

    class Provisioner:
        def ensure(self, _value):
            raise AssertionError("invalid claim reached provisioning")

    activity = SpawnActivity(Registry(), Provisioner())
    with pytest.raises(ValueError, match="only implements"):
        activity(ActivityInvocation("other", input=item.to_data()), context=None)
    with pytest.raises(ValueError, match="idempotency"):
        activity(ActivityInvocation(SPAWN_ACTIVITY, input=item.to_data(), idempotency="wrong"), context=None)
    with pytest.raises(ValueError, match="different identity"):
        activity(
            ActivityInvocation(
                SPAWN_ACTIVITY,
                input=item.to_data(),
                idempotency=spawn_idempotency(item.parent, item.spawn_id),
            ),
            context=None,
        )


def test_spawn_activity_refuses_a_live_object_from_the_provisioner():
    item = spec()

    class Registry:
        def claim(self, value):
            return SpawnClaim(value.parent, value.spawn_id, value.child, False)

    class Provisioner:
        def ensure(self, _value):
            return object()

    activity = SpawnActivity(Registry(), Provisioner())
    with pytest.raises(TypeError, match="never a live host or credential"):
        activity(
            ActivityInvocation(
                SPAWN_ACTIVITY,
                input=item.to_data(),
                idempotency=spawn_idempotency(item.parent, item.spawn_id),
            ),
            context=None,
        )


@pytest.fixture
def lifecycle(pg_connection):
    pg_connection.execute("DROP SCHEMA IF EXISTS impetus_lifecycle CASCADE")
    pg_connection.execute("DROP SCHEMA IF EXISTS impetus_fabric CASCADE")
    ensure_fabric_schema(pg_connection)
    ensure_lifecycle_schema(pg_connection)
    credential = issue_credential()
    register_process(pg_connection, "parent", credential)
    yield pg_connection, credential, PostgresSpawnRegistry(pg_connection, "parent", credential)
    pg_connection.execute("DROP SCHEMA IF EXISTS impetus_lifecycle CASCADE")
    pg_connection.execute("DROP SCHEMA IF EXISTS impetus_fabric CASCADE")
    ensure_fabric_schema(pg_connection)
    ensure_lifecycle_schema(pg_connection)


def test_lifecycle_schema_is_mapping_only_versioned_and_refuses_unknown_shapes(pg_connection):
    try:
        pg_connection.execute("DROP SCHEMA IF EXISTS impetus_lifecycle CASCADE")
        ensure_lifecycle_schema(pg_connection)
        columns = tuple(
            row[0]
            for row in pg_connection.execute(
                """SELECT column_name FROM information_schema.columns
                WHERE table_schema = 'impetus_lifecycle' AND table_name = 'spawns'
                ORDER BY ordinal_position"""
            ).fetchall()
        )
        assert columns == ("parent", "spawn_id", "child", "spec_digest", "created_at")

        pg_connection.execute("DROP SCHEMA impetus_lifecycle CASCADE")
        pg_connection.execute("CREATE SCHEMA impetus_lifecycle")
        pg_connection.execute("CREATE TABLE impetus_lifecycle.spawns (unknown text)")
        with pytest.raises(RuntimeError, match="unversioned.*refusing"):
            ensure_lifecycle_schema(pg_connection)

        pg_connection.execute("DROP SCHEMA impetus_lifecycle CASCADE")
        ensure_lifecycle_schema(pg_connection)
        pg_connection.execute(
            "UPDATE impetus_lifecycle.schema_metadata SET version = 999 WHERE component = 'lifecycle'"
        )
        with pytest.raises(RuntimeError, match="version 999.*migrate deliberately"):
            ensure_lifecycle_schema(pg_connection)
    finally:
        pg_connection.execute("DROP SCHEMA IF EXISTS impetus_lifecycle CASCADE")
        ensure_lifecycle_schema(pg_connection)


def test_lifecycle_schema_provisioning_does_not_commit_the_callers_transaction(postgres_dsn, pg_connection):
    pg_connection.execute("DROP SCHEMA IF EXISTS impetus_lifecycle CASCADE")
    joined = psycopg.connect(postgres_dsn, autocommit=False)
    try:
        ensure_lifecycle_schema(joined)
        assert pg_connection.execute("SELECT to_regnamespace('impetus_lifecycle')").fetchone()[0] is None
        joined.rollback()
        assert pg_connection.execute("SELECT to_regnamespace('impetus_lifecycle')").fetchone()[0] is None
    finally:
        joined.close()
        ensure_lifecycle_schema(pg_connection)


def test_postgres_registry_requires_autocommit_and_authentication(lifecycle, postgres_dsn):
    connection, _credential, _registry = lifecycle
    with psycopg.connect(postgres_dsn, autocommit=False) as joined:
        with pytest.raises(ValueError, match="autocommit"):
            PostgresSpawnRegistry(joined, "parent", issue_credential())
    with pytest.raises(PermissionError, match="lifecycle authentication"):
        PostgresSpawnRegistry(connection, "parent", issue_credential()).claim(spec())
    with pytest.raises(PermissionError, match="authenticated registry"):
        _registry.claim(spec(parent="other"))


def test_postgres_claim_is_durable_exact_conflict_detecting_and_queryable(lifecycle):
    connection, _credential, registry = lifecycle
    item = spec()
    first = registry.claim(item)
    second = registry.claim(item)

    assert first == SpawnClaim("parent", "spawn-1", item.child, False)
    assert second == SpawnClaim("parent", "spawn-1", item.child, True)
    assert registry.child_of("parent", "spawn-1") == Lineage("parent", "spawn-1", item.child)
    assert registry.children_of("parent") == (Lineage("parent", "spawn-1", item.child),)
    assert registry.parent_of(item.child) == Lineage("parent", "spawn-1", item.child)
    [(parent, spawn_id, child, digest)] = connection.execute(
        "SELECT parent, spawn_id, child, spec_digest FROM impetus_lifecycle.spawns"
    ).fetchall()
    assert (parent, spawn_id, child, digest) == ("parent", "spawn-1", item.child, item.digest)
    with pytest.raises(ValueError, match="content changed"):
        registry.claim(spec(config={"changed": True}))
    assert connection.execute("SELECT count(*) FROM impetus_lifecycle.spawns").fetchone()[0] == 1


def test_lineage_queries_are_parent_bound(lifecycle):
    connection, _credential, registry = lifecycle
    other_credential = issue_credential()
    register_process(connection, "other", other_credential)
    registry.claim(spec())
    other = PostgresSpawnRegistry(connection, "other", other_credential)
    with pytest.raises(PermissionError, match="parent must match"):
        other.child_of("parent", "spawn-1")
    with pytest.raises(PermissionError, match="does not belong"):
        other.parent_of(spec().child)


def test_concurrent_exact_claims_converge_on_one_row(lifecycle, postgres_dsn):
    _connection, credential, _registry = lifecycle
    item = spec()

    def claim():
        with psycopg.connect(postgres_dsn, autocommit=True) as connection:
            return PostgresSpawnRegistry(connection, "parent", credential).claim(item)

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = tuple(pool.map(lambda _index: claim(), range(2)))

    assert {claim.prior_claim for claim in claims} == {False, True}
    assert {claim.child for claim in claims} == {item.child}


def test_failed_provision_after_claim_retries_the_same_claim(lifecycle):
    _connection, _credential, registry = lifecycle
    item = spec()
    attempts = []

    class Provisioner:
        def ensure(self, provisioning):
            attempts.append(provisioning.child)
            if len(attempts) == 1:
                raise RuntimeError("lost after claim")

    activity = SpawnActivity(registry, Provisioner())
    invocation = ActivityInvocation(
        SPAWN_ACTIVITY,
        input=item.to_data(),
        idempotency=spawn_idempotency(item.parent, item.spawn_id),
    )
    with pytest.raises(RuntimeError, match="lost after claim"):
        activity(invocation, context=None)
    outcome = SpawnOutcome.from_data(activity(invocation, context=None))
    assert outcome.prior_claim
    assert attempts == [item.child, item.child]


def test_call_result_and_error_share_fabric_conflict_identity(lifecycle):
    connection, _credential, _registry = lifecycle
    parent_credential, child_credential = issue_credential(), issue_credential()
    register_process(connection, "caller", parent_credential)
    register_process(connection, "callee", child_credential)
    from petrus.fabric.postgres import PostgresFabric

    caller = PostgresFabric(connection, "caller", parent_credential)
    callee = PostgresFabric(connection, "callee", child_credential)
    caller.expose_source("replies")
    caller.grant("callee", "replies")
    second_credential = issue_credential()
    register_process(connection, "second-caller", second_credential)
    second_caller = PostgresFabric(connection, "second-caller", second_credential)
    second_caller.expose_source("replies")
    second_caller.grant("callee", "replies")
    request = request_envelope(
        request=CallRequest("terminal-call", "answer", {}),
        sender="caller",
        recipient="callee",
        source="calls",
        reply_route=ReplyRoute("caller", "replies"),
    )
    result = result_envelope(result=CallResult("terminal-call", {"ok": True}), request=request, sender="callee")
    error = error_envelope(
        error=CallError("terminal-call", "failed", "changed terminal outcome"),
        request=request,
        sender="callee",
    )
    second_request = request_envelope(
        request=CallRequest("terminal-call", "answer", {}),
        sender="second-caller",
        recipient="callee",
        source="calls",
        reply_route=ReplyRoute("second-caller", "replies"),
    )
    second_result = result_envelope(
        result=CallResult("terminal-call", {"ok": True}), request=second_request, sender="callee"
    )
    assert not callee.submit(result).duplicate
    with pytest.raises(ValueError, match="identity conflict"):
        callee.submit(error)
    assert result.delivery_id != second_result.delivery_id
    assert not callee.submit(second_result).duplicate


def test_process_lifecycle_acceptance_demo(postgres_dsn):
    result = subprocess.run(
        [sys.executable, "scripts/cv5-lifecycle-demo.py", "--dsn", postgres_dsn],
        cwd=REPO_ROOT,
        env={**os.environ, "UV_FROZEN": "1"},
        capture_output=True,
        text=True,
        timeout=90,
    )
    evidence = result.stdout + "\n--- stderr ---\n" + result.stderr
    assert result.returncode == 0, evidence
    for observation in (
        "spawn retry: claims=1 ensure_calls=2 prior_claim=true",
        "child history before host open: 0",
        "offline call: pending=1 parent=awaiting",
        "unrelated correlation: parent=awaiting",
        "correlated result: parent=completed child=completed",
        "correlated error: parent=completed outcome=error",
        "replay: parent appends=0 dispatches=0; child appends=0 dispatches=0",
        "credential absent from outcomes/envelopes/history: true",
        "overall: PASS",
    ):
        assert observation in result.stdout, evidence
