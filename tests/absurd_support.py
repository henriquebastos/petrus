"""
The purpose-built topology net + worker registry for the DS4 tests — the
golden-corpus trajectory's per-slice minimal net, NOT uharness: source
ingress -> one impure activity executed on a queue-subscribing worker -> a
human-gate delivery -> done.

The worker half doubles as the ``python -m petrus.motus.worker`` registry module
for the test subprocesses (``--registry tests.absurd_support:activities``),
configured through the environment the worker process owns:
``IMPETUS_TEST_DSN`` names the database carrying the two fixture tables the
kill tests read —

- ``impetus_test.effects`` — the fake external target: ONE idempotent insert
  keyed by the invocation's idempotency identity (``ON CONFLICT DO
  NOTHING``, the ES-009 fake_external pattern), so a redelivered activity
  reconciles instead of repeating and the exactly-one-effect claim is a row
  count;
- ``impetus_test.kill_switch`` — the matrix's arming pattern: when armed,
  the FIRST delivery to take the arm blocks forever AFTER its effect
  committed (the parent SIGKILLs it there — mid-activity, effect durable,
  outcome never resolved); the redelivery finds the switch unarmed and
  completes.
"""

from __future__ import annotations

import json

# Python imports
import os
import time
from pathlib import Path

# Internal imports
from petrus.motus.activity import ActivityInvocation, ExecutionPolicy
from petrus.impetus.petrinet import Arc, Binding, Cel, Net, NetPath, Place, Token, Transition

INBOX = NetPath("inbox")
WORKED = NetPath("worked")
APPROVALS = NetPath("approvals")
DONE = NetPath("done")

INGRESS = NetPath("ingress")
WORK = NetPath("work")
OPERATOR = NetPath("operator")
APPROVE = NetPath("approve")

ISSUE = "issue"
APPROVAL = "approval"

CAPABILITY = "sparks"


class SparkWork:
    """
    The net's one impure edge: ``prepare`` reads the issue token into the
    activity input (its data mapping, whole), requires the ``sparks``
    capability, resolves the declared attempts, and keys idempotency by the
    issue id — deterministic and instance-free, so the fake-external row
    counts across authority restarts. ``project`` stamps the frozen result
    onto the issue — unless constructed ``project_poisoned`` (the
    fix-the-code-and-retry lever: a poisoned deployment crashes projection
    AFTER the result froze; the fixed one retries projection alone).
    """

    def __init__(self, attempts: int = 1, project_poisoned: bool = False):
        self._attempts = attempts
        self._project_poisoned = project_poisoned

    def prepare(self, binding: Binding) -> ActivityInvocation:
        (token,) = binding.tokens
        return ActivityInvocation(
            "spark_work",
            input=dict(token.data),
            policy=ExecutionPolicy(attempts=self._attempts),
            idempotency=f"effect-{token.data['id']}",
        )

    def project(self, binding: Binding, result: object):
        if self._project_poisoned:
            raise ValueError("projection poisoned: fix the code and retry complete()")
        (token,) = binding.tokens
        return {WORKED: (Token(ISSUE, {**token.data, "spark": result}),)}


def topology_net() -> Net:
    """Source ingress -> impure activity -> human gate -> done; complete when an issue lands."""
    return Net(
        places=[Place(INBOX), Place(WORKED), Place(APPROVALS), Place(DONE)],
        transitions=[
            Transition(INGRESS),
            Transition(WORK, handler="spark_work"),
            Transition(OPERATOR),
            Transition(APPROVE),
        ],
        arcs=[
            Arc(INGRESS, INBOX, color=ISSUE),
            Arc(INBOX, WORK, color=ISSUE),
            Arc(WORK, WORKED, color=ISSUE),
            Arc(OPERATOR, APPROVALS, color=APPROVAL),
            Arc(WORKED, APPROVE, color=ISSUE),
            Arc(APPROVALS, APPROVE, color=APPROVAL),
            Arc(APPROVE, DONE, color=ISSUE),
        ],
        completion=Cel("size(done) != 0"),
    )


def topology_handlers(attempts: int = 1, project_poisoned: bool = False):
    return {"spark_work": SparkWork(attempts, project_poisoned)}


FIXTURE_DDL = (
    "CREATE SCHEMA IF NOT EXISTS impetus_test",
    "CREATE TABLE IF NOT EXISTS impetus_test.effects (idempotency text PRIMARY KEY)",
    "CREATE TABLE IF NOT EXISTS impetus_test.kill_switch (armed boolean NOT NULL)",
)


def ensure_fixture_tables(connection) -> None:
    """The test-owned fake-external target and the kill-switch arm, co-resident in the session database."""
    for statement in FIXTURE_DDL:
        connection.execute(statement)


def activities():
    """
    The worker subprocess's registry (``--registry
    tests.absurd_support:activities``): one activity, Petri-agnostic, whose
    world is the fixture database named by ``IMPETUS_TEST_DSN``. Its
    external effect is idempotent by the invocation's idempotency identity
    (lookup-first as insert-on-conflict); an optional ``nap`` in the input
    holds the delivery open (the graceful-drain window); an armed kill
    switch blocks the first delivery forever AFTER the effect committed —
    the SIGKILL window the redelivery tests shoot into.
    """
    # Pip import lives here: the registry loads inside the worker process,
    # which has the absurd extra by construction.
    import psycopg

    dsn = os.environ["IMPETUS_TEST_DSN"]

    def spark_work(invocation: ActivityInvocation, *, context) -> str:
        mode = invocation.input.get("mode")
        barrier = Path(invocation.input["barrier"]) if invocation.input.get("barrier") else None
        if mode == "heartbeat-long":
            deadline = time.monotonic() + 2.5
            beats = 0
            while time.monotonic() < deadline:
                beats += 1
                context.heartbeat(details={"beats": beats})
                time.sleep(0.2)
        elif mode == "checkpoint-crash":
            if context.latest_details is None:
                context.heartbeat(details={"cursor": 7, "first_claimant": context.claimant})
                barrier.write_text(json.dumps({"claimant": context.claimant}), encoding="utf-8")
                time.sleep(3600)
            else:
                barrier.with_suffix(".resumed").write_text(
                    json.dumps({"claimant": context.claimant, "details": context.latest_details}), encoding="utf-8"
                )
                return f"resumed {context.latest_details['cursor']}"
        connection = psycopg.connect(dsn, autocommit=True)
        try:
            nap = invocation.input.get("nap")
            if nap:
                time.sleep(float(nap))
            if invocation.input.get("boom"):
                raise ValueError("boom requested")  # the terminal-failure lever, before any effect
            connection.execute(
                "INSERT INTO impetus_test.effects (idempotency) VALUES (%s) ON CONFLICT DO NOTHING",
                (invocation.idempotency,),
            )
            took_the_arm = connection.execute(
                "UPDATE impetus_test.kill_switch SET armed = FALSE WHERE armed RETURNING 1"
            ).fetchone()
            if took_the_arm is not None:
                time.sleep(3600)  # the parent SIGKILLs here: effect durable, outcome never resolved
            return f"sparked {invocation.input['id']}"
        finally:
            connection.close()

    return {"spark_work": spark_work}
