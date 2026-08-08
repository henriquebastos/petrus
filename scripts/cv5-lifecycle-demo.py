"""CV5.DS2 acceptance: retry-safe spawn and correlated process calls."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

REPO_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(REPO_ROOT))

import psycopg  # noqa: E402

from petrus.motus.activity import ActivityInvocation  # noqa: E402
from petrus.impetus.binding import HandlerResult  # noqa: E402
from petrus.engine import DriveOutcome, Engine  # noqa: E402
from petrus.fabric import Envelope, ReplyRoute  # noqa: E402
from petrus.fabric.ingress import FABRIC_ENVELOPE, FabricInbox  # noqa: E402
from petrus.fabric.postgres import (  # noqa: E402
    PostgresFabric,
    ensure_fabric_schema,
    issue_credential,
    register_process,
)
from petrus.impetus.history import (  # noqa: E402
    ActivityCompleted,  # noqa: E402
    DeliveryRegistration,
)
from petrus.impetus.history_store.postgres import (  # noqa: E402
    PostgresHistoryStore,
    ensure_schema,
)
from petrus.engine.postgres import create_engine, load_engine  # noqa: E402
from petrus.impetus.instance import Status  # noqa: E402
from petrus.impetus.petrinet import Arc, Binding, Marking, Net, NetPath, Place, Token, Transition  # noqa: E402
from petrus.processes import (  # noqa: E402
    CallError,
    CallRequest,
    CallResult,
    SpawnOutcome,
    SpawnSpec,
    error_envelope,
    reply_from_envelope,
    request_envelope,
    result_envelope,
)
from petrus.processes.postgres import PostgresSpawnRegistry, ensure_lifecycle_schema  # noqa: E402
from petrus.processes.spawn import SPAWN_ACTIVITY, SpawnActivity, spawn_idempotency  # noqa: E402

POSTGRES_IMAGE = "postgres:17.5-alpine@sha256:6567bca8d7bc8c82c5922425a0baee57be8402df92bae5eacad5f01ae9544daa"
PORT = 55613
DEMO_PASSWORD = "post" + "gres"

START, SPAWNED, WAITING, REPLIES, UNRELATED, DONE = map(
    NetPath, ("start", "spawned", "waiting", "replies", "unrelated", "done")
)
SPAWN, CALL, REPLY_SOURCE, JOIN = map(NetPath, ("spawn", "call", "reply", "join"))
REQUESTS, CHILD_DONE = map(NetPath, ("requests", "child_done"))
REQUEST_SOURCE, RESPOND = map(NetPath, ("request", "respond"))

SPAWN_READY = "SpawnReady"
CALL_WAIT = "CallWait"
CALL_REPLY = "CallReply"
CALL_DONE = "CallDone"
CALL_ID = "call/main"


def parent_net(*, with_spawn: bool = True) -> Net:
    places = [Place(START), Place(WAITING), Place(REPLIES), Place(UNRELATED), Place(DONE)]
    transitions = [
        Transition(CALL, handler="call"),
        Transition(REPLY_SOURCE, handler="reply"),
        Transition(JOIN, handler="join"),
    ]
    arcs = [
        Arc(START, CALL),
        Arc(CALL, WAITING),
        Arc(REPLY_SOURCE, REPLIES, color=FABRIC_ENVELOPE),
        Arc(REPLY_SOURCE, UNRELATED, color=FABRIC_ENVELOPE),
        Arc(WAITING, JOIN),
        Arc(REPLIES, JOIN, color=FABRIC_ENVELOPE),
        Arc(JOIN, DONE),
    ]
    if with_spawn:
        places.append(Place(SPAWNED))
        transitions.insert(0, Transition(SPAWN, handler="spawn"))
        arcs = [Arc(START, SPAWN), Arc(SPAWN, SPAWNED), Arc(SPAWNED, CALL), *arcs[1:]]
    return Net(places=places, transitions=transitions, arcs=arcs, completion="done")


def child_net() -> Net:
    return Net(
        places=[Place(REQUESTS), Place(CHILD_DONE)],
        transitions=[Transition(REQUEST_SOURCE, handler="request"), Transition(RESPOND, handler="respond")],
        arcs=[
            Arc(REQUEST_SOURCE, REQUESTS, color=FABRIC_ENVELOPE),
            Arc(REQUESTS, RESPOND),
            Arc(RESPOND, CHILD_DONE),
        ],
        completion="done",
    )


def completed(marking: Marking) -> bool:
    return bool(marking.place(DONE) or marking.place(CHILD_DONE))


class SpawnHandler:
    def __init__(self, spec: SpawnSpec):
        self.spec = spec

    def prepare(self, _binding: Binding) -> ActivityInvocation:
        return ActivityInvocation(
            SPAWN_ACTIVITY,
            input=self.spec.to_data(),
            correlation=self.spec.spawn_id,
            idempotency=spawn_idempotency(self.spec.parent, self.spec.spawn_id),
        )

    def project(self, _binding: Binding, result: object) -> dict[NetPath, tuple[Token, ...]]:
        outcome = SpawnOutcome.from_data(result)
        return {SPAWNED: (Token(SPAWN_READY, outcome.to_data()),)}


class CallHandler:
    def __init__(self, envelope: Envelope):
        self.envelope = envelope

    def prepare(self, _binding: Binding) -> ActivityInvocation:
        return ActivityInvocation(
            "fabric.send",
            input=self.envelope.to_data(),
            correlation=self.envelope.correlation,
            idempotency=self.envelope.ingress_identity,
        )

    def project(self, _binding: Binding, result: object) -> HandlerResult:
        return HandlerResult(
            {WAITING: (Token(CALL_WAIT, {"call_id": self.envelope.correlation, "submission": result}),)},
            opens=(DeliveryRegistration(REPLY_SOURCE, self.envelope.correlation),),
        )


@dataclass(frozen=True)
class ReplyHandler:
    request: Envelope

    def __call__(self, binding: Binding, _outputs: tuple[Arc, ...]) -> HandlerResult:
        (token,) = binding.tokens
        envelope = Envelope.from_data(token.data)
        payload = envelope.payload
        call_id = payload.get("call_id") if hasattr(payload, "get") else None
        if call_id != CALL_ID:
            return HandlerResult({UNRELATED: (token,)})
        reply_from_envelope(envelope, request=self.request)
        return HandlerResult(
            {REPLIES: (token,)},
            closes=(DeliveryRegistration(REPLY_SOURCE, envelope.correlation),),
        )


def join_handler(binding: Binding, _outputs: tuple[Arc, ...]) -> dict[NetPath, tuple[Token, ...]]:
    reply = Envelope.from_data(next(token for token in binding.tokens if token.color == FABRIC_ENVELOPE).data)
    if reply.correlation != CALL_ID:
        raise ValueError("join received an unrelated call reply")
    kind = "result" if reply.payload["kind"] == CallResult.kind else "error"
    return {DONE: (Token(CALL_DONE, {"call_id": CALL_ID, "outcome": kind}),)}


def request_handler(binding: Binding, _outputs: tuple[Arc, ...]) -> HandlerResult:
    (token,) = binding.tokens
    return HandlerResult(
        {REQUESTS: (token,)},
        closes=(DeliveryRegistration(REQUEST_SOURCE, "default"),),
    )


class RespondHandler:
    def __init__(self, child: str, outcome: str):
        self.child = child
        self.outcome = outcome

    def prepare(self, binding: Binding) -> ActivityInvocation:
        request = Envelope.from_data(binding.tokens[0].data)
        call = CallRequest.from_data(request.payload)
        if self.outcome == "result":
            reply = result_envelope(
                result=CallResult(call.call_id, {"answer": 42}),
                request=request,
                sender=self.child,
            )
        else:
            reply = error_envelope(
                error=CallError(call.call_id, "delegated-refusal", "child refused delegated work"),
                request=request,
                sender=self.child,
            )
        return ActivityInvocation(
            "fabric.send",
            input=reply.to_data(),
            correlation=reply.correlation,
            idempotency=reply.ingress_identity,
        )

    def project(self, _binding: Binding, result: object) -> dict[NetPath, tuple[Token, ...]]:
        return {CHILD_DONE: (Token(CALL_DONE, {"submission": result, "outcome": self.outcome}),)}


class SendActivity:
    def __init__(self, dsn: str, instance: str, credential: str):
        self.connection = psycopg.connect(dsn, autocommit=True)
        self.client = PostgresFabric(self.connection, instance, credential)

    def __call__(self, invocation: ActivityInvocation, *, context) -> dict[str, object]:
        envelope = Envelope.from_data(invocation.input)
        if invocation.idempotency != envelope.ingress_identity:
            raise ValueError("fabric.send idempotency must match the envelope identity")
        submission = self.client.submit(envelope)
        return {
            "state": submission.state,
            "duplicate": submission.duplicate,
            "delivery_id": submission.delivery_id,
            "correlation": envelope.correlation,
        }

    def close(self) -> None:
        self.connection.close()


class DemoInlineDispatch:
    """Execute activities now; optionally lose one post-effect completion."""

    def __init__(self, activities: dict[str, object], *, drop_once: set[str] | None = None):
        self.activities = activities
        self.drop_once = set() if drop_once is None else set(drop_once)
        self.dropped = set()
        self.completed = []
        self.dispatches = 0

    def dispatch(self, occurrence: int, invocation: ActivityInvocation) -> None:
        self.dispatches += 1
        result = self.activities[invocation.activity](invocation, context=None)
        if invocation.activity in self.drop_once and invocation.activity not in self.dropped:
            self.dropped.add(invocation.activity)
            return
        self.completed.append((occurrence, result))

    def collect(self):
        completed = tuple(self.completed)
        self.completed.clear()
        return completed


@dataclass
class LiveAuthority:
    engine: Engine
    fabric_connection: object
    dispatch: DemoInlineDispatch
    inbox: FabricInbox
    send: SendActivity

    def drive(self):
        firings = []
        while True:
            outcome = self.engine.advance()
            firings.extend(outcome.firings)
            if not outcome.ready:
                return DriveOutcome(tuple(firings), outcome.waiting, next_maturation=outcome.next_maturation)

    def drain(self) -> int:
        return len(self.inbox.drain())

    def close(self) -> None:
        self.engine.close()
        self.fabric_connection.close()
        self.send.close()


class DemoProvisioner:
    """Application-owned provisioner; its workspace key never enters protocol data."""

    def __init__(self, dsn: str, parent: str, parent_credential: str, workspace_key: bytes):
        self.dsn = dsn
        self.parent = parent
        self.parent_credential = parent_credential
        self.workspace_key = workspace_key
        self.ensure_calls = 0

    def child_credential(self, child: str) -> str:
        digest = hmac.new(self.workspace_key, child.encode(), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).decode()

    def ensure(self, provisioning) -> None:
        self.ensure_calls += 1
        child_credential = self.child_credential(provisioning.child)
        with psycopg.connect(self.dsn, autocommit=True) as connection:
            register_process(connection, provisioning.child, child_credential)
            child = PostgresFabric(connection, provisioning.child, child_credential)
            child.expose_source(provisioning.endpoint.source)
            child.offer_service(
                provisioning.endpoint.source,
                provisioning.process_kind,
                provisioning.endpoint.to_data()["capabilities"],
            )
            child.grant(provisioning.parent, provisioning.endpoint.source)
            if provisioning.reply_route is not None:
                parent = PostgresFabric(connection, provisioning.parent, self.parent_credential)
                parent.expose_source(provisioning.reply_route.source)
                parent.grant(provisioning.child, provisioning.reply_route.source)


def parent_handlers(spec: SpawnSpec, envelope: Envelope, *, with_spawn: bool) -> dict[str, object]:
    handlers = {
        "call": CallHandler(envelope),
        "reply": ReplyHandler(envelope),
        "join": join_handler,
    }
    if with_spawn:
        handlers["spawn"] = SpawnHandler(spec)
    return handlers


def open_parent(
    dsn: str,
    parent: str,
    credential: str,
    spec: SpawnSpec,
    envelope: Envelope,
    dispatch: DemoInlineDispatch,
    send: SendActivity,
    *,
    create: bool,
    with_spawn: bool,
) -> LiveAuthority:
    connection = None
    engine = None
    fabric_connection = None
    try:
        connection = psycopg.connect(dsn, autocommit=False)
        handlers = parent_handlers(spec, envelope, with_spawn=with_spawn)
        options = {
            "handlers": handlers,
            "completions": {"done": completed},
        }
        if create:
            options["marking"] = Marking({START: (Token("Start", {"call_id": CALL_ID}),)})
        provider = create_engine if create else load_engine
        engine = provider(
            connection,
            parent_net(with_spawn=with_spawn),
            parent,
            dispatch=dispatch,
            **options,
        )
        if create:
            engine.seal(REPLY_SOURCE)
        fabric_connection = psycopg.connect(dsn, autocommit=True)
        inbox = FabricInbox(
            PostgresFabric(fabric_connection, parent, credential),
            engine,
        )
        return LiveAuthority(engine, fabric_connection, dispatch, inbox, send)
    except BaseException:
        if fabric_connection is not None:
            fabric_connection.close()
        if engine is not None:
            engine.close()
        elif connection is not None:
            connection.close()
        send.close()
        raise


def open_child(
    dsn: str,
    parent: str,
    child: str,
    credential: str,
    outcome: str,
    *,
    create: bool,
) -> LiveAuthority:
    connection = None
    send = None
    engine = None
    fabric_connection = None
    try:
        connection = psycopg.connect(dsn, autocommit=False)
        handlers = {"request": request_handler, "respond": RespondHandler(child, outcome)}
        send = SendActivity(dsn, child, credential)
        dispatch = DemoInlineDispatch({"fabric.send": send})
        provider = create_engine if create else load_engine
        engine = provider(
            connection,
            child_net(),
            child,
            dispatch=dispatch,
            handlers=handlers,
            completions={"done": completed},
        )
        fabric_connection = psycopg.connect(dsn, autocommit=True)
        inbox = FabricInbox(
            PostgresFabric(fabric_connection, child, credential),
            engine,
        )
        return LiveAuthority(engine, fabric_connection, dispatch, inbox, send)
    except BaseException:
        if fabric_connection is not None:
            fabric_connection.close()
        if engine is not None:
            engine.close()
        elif connection is not None:
            connection.close()
        if send is not None:
            send.close()
        raise


def child_subprocess() -> None:
    live = open_child(
        os.environ["IMPETUS_LIFECYCLE_DSN"],
        os.environ["IMPETUS_LIFECYCLE_PARENT"],
        os.environ["IMPETUS_LIFECYCLE_CHILD"],
        os.environ["IMPETUS_LIFECYCLE_CHILD_CREDENTIAL"],
        os.environ["IMPETUS_LIFECYCLE_OUTCOME"],
        create=True,
    )
    try:
        assert live.drain() == 1
        live.drive()
        assert live.engine.status is Status.COMPLETED
    finally:
        live.close()


def run_child(dsn: str, parent: str, child: str, credential: str, outcome: str) -> None:
    env = {
        **os.environ,
        "IMPETUS_LIFECYCLE_DSN": dsn,
        "IMPETUS_LIFECYCLE_PARENT": parent,
        "IMPETUS_LIFECYCLE_CHILD": child,
        "IMPETUS_LIFECYCLE_CHILD_CREDENTIAL": credential,
        "IMPETUS_LIFECYCLE_OUTCOME": outcome,
    }
    process = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--internal-child"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
    )
    if process.returncode:
        raise RuntimeError(f"child process failed: {process.stdout}\n{process.stderr}")


def call_envelope(parent: str, child: str) -> Envelope:
    return request_envelope(
        request=CallRequest(CALL_ID, "answer", {"question": 42}),
        sender=parent,
        recipient=child,
        source=str(REQUEST_SOURCE),
        reply_route=ReplyRoute(parent, str(REPLY_SOURCE)),
    )


def history_size(dsn: str, instance: str) -> int:
    with psycopg.connect(dsn, autocommit=True) as connection:
        return len(PostgresHistoryStore(connection, instance))


def bootstrap(dsn: str, *processes: tuple[str, str]) -> None:
    with psycopg.connect(dsn, autocommit=True) as connection:
        ensure_schema(connection)
        ensure_fabric_schema(connection)
        ensure_lifecycle_schema(connection)
        for instance, credential in processes:
            register_process(connection, instance, credential)


def run_error_call(dsn: str, suffix: str) -> tuple[str, str]:
    parent, child = f"error-parent-{suffix}", f"error-child-{suffix}"
    parent_credential = issue_credential()
    child_credential = issue_credential()
    bootstrap(dsn, (parent, parent_credential), (child, child_credential))
    with psycopg.connect(dsn, autocommit=True) as connection:
        parent_fabric = PostgresFabric(connection, parent, parent_credential)
        child_fabric = PostgresFabric(connection, child, child_credential)
        parent_fabric.expose_source(str(REPLY_SOURCE))
        parent_fabric.grant(child, str(REPLY_SOURCE))
        child_fabric.expose_source(str(REQUEST_SOURCE))
        child_fabric.grant(parent, str(REQUEST_SOURCE))

    placeholder = SpawnSpec(parent, "unused", "call-only", str(REQUEST_SOURCE), {}, {})
    envelope = call_envelope(parent, child)
    send = SendActivity(dsn, parent, parent_credential)
    dispatch = DemoInlineDispatch({"fabric.send": send})
    live = open_parent(
        dsn,
        parent,
        parent_credential,
        placeholder,
        envelope,
        dispatch,
        send,
        create=True,
        with_spawn=False,
    )
    try:
        live.drive()
        assert live.engine.status is Status.AWAITING
        run_child(dsn, parent, child, child_credential, "error")
        assert live.drain() == 1
        live.drive()
        assert live.engine.status is Status.COMPLETED
        done = live.engine.marking.place(DONE)[0]
        assert done.data["outcome"] == "error"
    finally:
        live.close()
    return parent, child


def run(dsn: str) -> None:
    suffix = uuid4().hex[:8]
    parent = f"lifecycle-parent-{suffix}"
    parent_credential = issue_credential()
    bootstrap(dsn, (parent, parent_credential))
    spec = SpawnSpec(
        parent,
        f"spawn-{suffix}",
        "analysis-agent",
        str(REQUEST_SOURCE),
        {"protocol": "call-v1"},
        {"role": "agent"},
        ReplyRoute(parent, str(REPLY_SOURCE)),
    )
    envelope = call_envelope(parent, spec.child)
    registry_connection = psycopg.connect(dsn, autocommit=True)
    registry = PostgresSpawnRegistry(registry_connection, parent, parent_credential)
    provisioner = DemoProvisioner(dsn, parent, parent_credential, os.urandom(32))
    spawn = SpawnActivity(registry, provisioner)

    first_send = SendActivity(dsn, parent, parent_credential)
    first_dispatch = DemoInlineDispatch(
        {SPAWN_ACTIVITY: spawn, "fabric.send": first_send},
        drop_once={SPAWN_ACTIVITY},
    )
    first = open_parent(
        dsn,
        parent,
        parent_credential,
        spec,
        envelope,
        first_dispatch,
        first_send,
        create=True,
        with_spawn=True,
    )
    first.drive()
    assert first.engine.status is Status.RUNNING
    assert len(first.engine.in_flight) == 1
    first.close()

    assert history_size(dsn, spec.child) == 0
    second_send = SendActivity(dsn, parent, parent_credential)
    second_dispatch = DemoInlineDispatch({SPAWN_ACTIVITY: spawn, "fabric.send": second_send})
    parent_live = open_parent(
        dsn,
        parent,
        parent_credential,
        spec,
        envelope,
        second_dispatch,
        second_send,
        create=False,
        with_spawn=True,
    )
    try:
        parent_live.drive()
        assert parent_live.engine.status is Status.AWAITING
        with psycopg.connect(dsn, autocommit=True) as connection:
            claim_count = connection.execute(
                "SELECT count(*) FROM impetus_lifecycle.spawns WHERE parent = %s AND spawn_id = %s",
                (parent, spec.spawn_id),
            ).fetchone()[0]
            child_registration_count = connection.execute(
                "SELECT count(*) FROM impetus_fabric.processes WHERE instance_id = %s",
                (spec.child,),
            ).fetchone()[0]
            pending = len(PostgresFabric(connection, spec.child, provisioner.child_credential(spec.child)).pending())
        spawn_results = [
            record.result
            for record in parent_live.engine.records
            if isinstance(record, ActivityCompleted) and record.transition == SPAWN
        ]
        assert len(spawn_results) == 1
        spawn_outcome = SpawnOutcome.from_data(spawn_results[0])
        assert spawn_outcome.prior_claim
        assert (claim_count, child_registration_count, provisioner.ensure_calls, pending) == (1, 1, 2, 1)

        unrelated_request = request_envelope(
            request=CallRequest("unrelated", "noise", {}),
            sender=parent,
            recipient=spec.child,
            source=str(REQUEST_SOURCE),
            reply_route=ReplyRoute(parent, str(REPLY_SOURCE)),
        )
        unrelated = result_envelope(
            result=CallResult("unrelated", {"ignored": True}),
            request=unrelated_request,
            sender=spec.child,
        )
        with psycopg.connect(dsn, autocommit=True) as connection:
            PostgresFabric(connection, spec.child, provisioner.child_credential(spec.child)).submit(unrelated)
        assert parent_live.drain() == 1
        parent_live.drive()
        assert parent_live.engine.status is Status.AWAITING

        child_history_before = history_size(dsn, spec.child)
        run_child(dsn, parent, spec.child, provisioner.child_credential(spec.child), "result")
        assert parent_live.drain() == 1
        parent_live.drive()
        assert parent_live.engine.status is Status.COMPLETED

        parent_before = len(parent_live.engine.records)
        parent_live.close()
        replay_send = SendActivity(dsn, parent, parent_credential)
        replay_dispatch = DemoInlineDispatch({SPAWN_ACTIVITY: spawn, "fabric.send": replay_send})
        replay_parent = open_parent(
            dsn,
            parent,
            parent_credential,
            spec,
            envelope,
            replay_dispatch,
            replay_send,
            create=False,
            with_spawn=True,
        )
        child_replay = open_child(
            dsn,
            parent,
            spec.child,
            provisioner.child_credential(spec.child),
            "result",
            create=False,
        )
        try:
            child_before = len(child_replay.engine.records)
            replay_parent.drive()
            child_replay.drive()
            replay = (
                len(replay_parent.engine.records) - parent_before,
                replay_dispatch.dispatches,
                len(child_replay.engine.records) - child_before,
                child_replay.dispatch.dispatches,
            )
            parent_records = repr(replay_parent.engine.records)
            child_records = repr(child_replay.engine.records)
        finally:
            replay_parent.close()
            child_replay.close()
    finally:
        parent_live.close()

    run_error_call(dsn, suffix)
    with psycopg.connect(dsn, autocommit=True) as connection:
        envelopes = repr(
            connection.execute(
                "SELECT envelope FROM impetus_fabric.deliveries WHERE sender = ANY(%s)",
                ([parent, spec.child],),
            ).fetchall()
        )
    credential = provisioner.child_credential(spec.child)
    credential_absent = all(
        credential not in value for value in (repr(spawn_results), envelopes, parent_records, child_records)
    )
    assert replay == (0, 0, 0, 0) and credential_absent

    print(f"spawn retry: claims={claim_count} ensure_calls={provisioner.ensure_calls} prior_claim=true")
    print(f"child history before host open: {child_history_before}")
    print(f"offline call: pending={pending} parent=awaiting")
    print("unrelated correlation: parent=awaiting")
    print("correlated result: parent=completed child=completed")
    print("correlated error: parent=completed outcome=error")
    print("replay: parent appends=0 dispatches=0; child appends=0 dispatches=0")
    print(f"credential absent from outcomes/envelopes/history: {str(credential_absent).lower()}")
    print("overall: PASS")
    registry_connection.close()


def start_postgres() -> tuple[str, str]:
    name = f"impetus-cv5-lifecycle-{os.getpid()}"
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--detach",
            "--name",
            name,
            "--publish",
            f"127.0.0.1:{PORT}:5432",
            "--env",
            f"POSTGRES_PASSWORD={DEMO_PASSWORD}",
            "--tmpfs",
            "/var/lib/postgresql/data",
            POSTGRES_IMAGE,
        ],
        check=True,
        capture_output=True,
    )
    dsn = f"postgres://postgres:{DEMO_PASSWORD}@127.0.0.1:{PORT}/postgres"
    deadline = time.monotonic() + 60
    while True:
        try:
            psycopg.connect(dsn, connect_timeout=2).close()
            return dsn, name
        except psycopg.OperationalError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn")
    parser.add_argument("--internal-child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.internal_child:
        child_subprocess()
        return
    container = None
    try:
        dsn = args.dsn
        if dsn is None:
            dsn, container = start_postgres()
        run(dsn)
    finally:
        if container is not None:
            subprocess.run(["docker", "stop", container], check=False, capture_output=True)


if __name__ == "__main__":
    main()
