"""CV5 Fabric acceptance demo: two Engines, split and co-located."""

from __future__ import annotations

import argparse
import json
import os
import selectors
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
from petrus.motus.dispatch import InlineDispatch  # noqa: E402
from petrus.engine import DriveOutcome, Engine  # noqa: E402
from petrus.fabric import Envelope, ReplyRoute  # noqa: E402
from petrus.fabric.ingress import FABRIC_ENVELOPE, FabricInbox  # noqa: E402
from petrus.fabric.postgres import (  # noqa: E402
    PostgresFabric,
    ensure_fabric_schema,
    issue_credential,
    register_process,
)
from petrus.impetus.history import DeliveryRegistration  # noqa: E402
from petrus.impetus.history_store.postgres import (  # noqa: E402
    PostgresHistoryStore,
    ensure_schema,
)
from petrus.engine.postgres import create_engine, load_engine  # noqa: E402
from petrus.impetus.instance import Status  # noqa: E402
from petrus.impetus.petrinet import Arc, Binding, Cel, Marking, Net, NetPath, Place, Token, Transition  # noqa: E402

POSTGRES_IMAGE = "postgres:17.5-alpine@sha256:6567bca8d7bc8c82c5922425a0baee57be8402df92bae5eacad5f01ae9544daa"
PORT = 55612
START, WAITING, REPLIES, DONE = map(NetPath, ("start", "waiting", "replies", "done"))
SEND, REPLY_SOURCE, JOIN = map(NetPath, ("send", "reply", "join"))
REQUEST_SOURCE, REQUESTS, RESPOND = map(NetPath, ("request", "requests", "respond"))


def parent_net() -> Net:
    return Net(
        places=[Place(START), Place(WAITING), Place(REPLIES), Place(DONE)],
        transitions=[
            Transition(SEND, handler="send"),
            Transition(REPLY_SOURCE, handler="reply"),
            Transition(JOIN, handler="finish"),
        ],
        arcs=[
            Arc(START, SEND),
            Arc(SEND, WAITING),
            Arc(REPLY_SOURCE, REPLIES, color=FABRIC_ENVELOPE),
            Arc(WAITING, JOIN),
            Arc(REPLIES, JOIN, color=FABRIC_ENVELOPE),
            Arc(JOIN, DONE),
        ],
        completion=Cel("size(done) != 0"),
    )


def child_net() -> Net:
    return Net(
        places=[Place(REQUESTS), Place(DONE)],
        transitions=[Transition(REQUEST_SOURCE, handler="request"), Transition(RESPOND, handler="respond")],
        arcs=[Arc(REQUEST_SOURCE, REQUESTS, color=FABRIC_ENVELOPE), Arc(REQUESTS, RESPOND), Arc(RESPOND, DONE)],
        completion=Cel("size(done) != 0"),
    )


class SendHandler:
    def __init__(self, envelope: Envelope, *, opens_reply: bool = False):
        self.envelope = envelope
        self.opens_reply = opens_reply

    def prepare(self, _binding: Binding) -> ActivityInvocation:
        return ActivityInvocation(
            "fabric.send",
            input=self.envelope.to_data(),
            correlation=self.envelope.correlation,
            idempotency=self.envelope.ingress_identity,
        )

    def project(self, _binding: Binding, result: object) -> HandlerResult:
        opens = (DeliveryRegistration(REPLY_SOURCE, self.envelope.correlation),) if self.opens_reply else ()
        return HandlerResult(
            {WAITING: (Token("Waiting", result),)} if self.opens_reply else {DONE: (Token("Done", result),)},
            opens=opens,
        )


def reply_handler(binding: Binding, _outputs: tuple[Arc, ...]) -> HandlerResult:
    (token,) = binding.tokens
    envelope = Envelope.from_data(token.data)
    return HandlerResult({REPLIES: (token,)}, closes=(DeliveryRegistration(REPLY_SOURCE, envelope.correlation),))


def finish_handler(binding: Binding, _outputs: tuple[Arc, ...]) -> dict[NetPath, tuple[Token, ...]]:
    waiting = next(token for token in binding.tokens if token.color == "Waiting")
    reply = Envelope.from_data(next(token for token in binding.tokens if token.color == FABRIC_ENVELOPE).data)
    if reply.correlation != waiting.data["correlation"]:
        raise ValueError(
            f"reply correlation {reply.correlation!r} does not answer the wait for {waiting.data['correlation']!r}"
        )
    return {DONE: (Token("Done", {"correlation": reply.correlation, "answer": reply.payload["answer"]}),)}


def request_handler(binding: Binding, _outputs: tuple[Arc, ...]) -> HandlerResult:
    (token,) = binding.tokens
    return HandlerResult({REQUESTS: (token,)}, closes=(DeliveryRegistration(REQUEST_SOURCE, "default"),))


class ResponseHandler:
    def prepare(self, binding: Binding) -> ActivityInvocation:
        request = Envelope.from_data(binding.tokens[0].data)
        assert request.reply_route is not None
        reply = Envelope(
            delivery_id=f"reply-{request.delivery_id}",
            sender=request.recipient,
            recipient=request.reply_route.instance_id,
            source=request.reply_route.source,
            correlation=request.correlation,
            payload={"answer": "pong", "request": request.delivery_id},
        )
        return ActivityInvocation(
            "fabric.send",
            input=reply.to_data(),
            correlation=reply.correlation,
            idempotency=reply.ingress_identity,
        )

    def project(self, _binding: Binding, result: object) -> dict[NetPath, tuple[Token, ...]]:
        return {DONE: (Token("Done", result),)}


class SendActivity:
    def __init__(self, dsn: str, instance: str, credential: str):
        self.connection = psycopg.connect(dsn, autocommit=True)
        self.client = PostgresFabric(self.connection, instance, credential)
        self.invocations = 0

    def __call__(self, invocation: ActivityInvocation, *, context) -> dict[str, object]:
        envelope = Envelope.from_data(invocation.input)
        if invocation.idempotency != envelope.ingress_identity:
            raise ValueError(
                f"fabric.send invocation idempotency {invocation.idempotency!r} does not match "
                f"envelope identity {envelope.ingress_identity!r}"
            )
        self.invocations += 1
        submission = self.client.submit(envelope)
        return {
            "state": submission.state,
            "duplicate": submission.duplicate,
            "delivery_id": submission.delivery_id,
            "correlation": envelope.correlation,
        }

    def close(self) -> None:
        self.connection.close()


class CustodyDroppingDispatch:
    """Return from dispatch without retaining or performing the invocation."""

    def dispatch(self, _occurrence: int, _invocation: ActivityInvocation) -> None:
        pass

    def collect(self) -> tuple[tuple[int, object], ...]:
        return ()


@dataclass
class LiveRole:
    engine: Engine
    fabric_connection: object
    fabric_client: PostgresFabric
    inbox: FabricInbox
    activity: SendActivity

    def drive(self) -> DriveOutcome:
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
        self.activity.close()


def request_envelope(parent: str, child: str) -> Envelope:
    return Envelope(
        delivery_id=f"request-{parent}",
        sender=parent,
        recipient=child,
        source=str(REQUEST_SOURCE),
        correlation=f"correlation-{parent}",
        payload={"question": "ping"},
        reply_route=ReplyRoute(parent, str(REPLY_SOURCE)),
    )


def handlers(role: str, parent: str, child: str) -> dict:
    if role == "parent":
        return {
            "send": SendHandler(request_envelope(parent, child), opens_reply=True),
            "reply": reply_handler,
            "finish": finish_handler,
        }
    return {"request": request_handler, "respond": ResponseHandler()}


def open_role(
    dsn: str,
    role: str,
    authority_id: str,
    parent: str,
    child: str,
    credential: str,
    *,
    dispatch=None,
) -> LiveRole:
    activity = None
    connection = None
    engine = None
    fabric_connection = None
    try:
        activity = SendActivity(dsn, authority_id, credential)
        connection = psycopg.connect(dsn, autocommit=False)
        engine = load_engine(
            connection,
            parent_net() if role == "parent" else child_net(),
            authority_id,
            dispatch=dispatch if dispatch is not None else InlineDispatch({"fabric.send": activity}),
            handlers=handlers(role, parent, child),
        )
        fabric_connection = psycopg.connect(dsn, autocommit=True)
        fabric_client = PostgresFabric(fabric_connection, authority_id, credential)
        inbox = FabricInbox(fabric_client, engine)
        return LiveRole(engine, fabric_connection, fabric_client, inbox, activity)
    except BaseException:
        if fabric_connection is not None:
            fabric_connection.close()
        if engine is not None:
            engine.close()
        elif connection is not None:
            connection.close()
        if activity is not None:
            activity.close()
        raise


def bootstrap(dsn: str, parent: str, child: str, credentials: dict[str, str]) -> None:
    with psycopg.connect(dsn, autocommit=True) as control:
        ensure_schema(control)
        ensure_fabric_schema(control)
        for authority_id in (parent, child):
            register_process(control, authority_id, credentials[authority_id])
        parent_fabric = PostgresFabric(control, parent, credentials[parent])
        child_fabric = PostgresFabric(control, child, credentials[child])
        parent_fabric.expose_source(str(REPLY_SOURCE))
        child_fabric.expose_source(str(REQUEST_SOURCE))
        parent_fabric.offer_service(str(REPLY_SOURCE), "fabric.reply", {"version": 1})
        child_fabric.offer_service(str(REQUEST_SOURCE), "fabric.request", {"version": 1})
        parent_fabric.grant(child, str(REPLY_SOURCE))
        child_fabric.grant(parent, str(REQUEST_SOURCE))
    parent_engine = create_engine(
        psycopg.connect(dsn, autocommit=False),
        parent_net(),
        parent,
        dispatch=InlineDispatch({}),
        marking=Marking({START: (Token("Start", {"command": "begin"}),)}),
        handlers=handlers("parent", parent, child),
    )
    try:
        parent_engine.seal(REPLY_SOURCE)
    finally:
        parent_engine.close()
    child_engine = create_engine(
        psycopg.connect(dsn, autocommit=False),
        child_net(),
        child,
        dispatch=InlineDispatch({}),
        handlers=handlers("child", parent, child),
    )
    child_engine.close()


def emit(event: str, **values: object) -> None:
    print(json.dumps({"event": event, **values}, sort_keys=True), flush=True)


def subprocess_role() -> None:
    dsn = os.environ["IMPETUS_DEMO_DSN"]
    role = os.environ["IMPETUS_DEMO_ROLE"]
    parent, child = os.environ["IMPETUS_DEMO_PARENT"], os.environ["IMPETUS_DEMO_CHILD"]
    authority_id = parent if role == "parent" else child
    live = open_role(dsn, role, authority_id, parent, child, os.environ["IMPETUS_DEMO_CREDENTIAL"])
    try:
        if role == "parent":
            live.drive()
            assert live.engine.status is Status.AWAITING
            emit("parent_waiting", status=live.engine.status.value)
        deadline = time.monotonic() + 30
        while live.engine.status is not Status.COMPLETED:
            live.drain()
            live.drive()
            if time.monotonic() > deadline:
                raise TimeoutError(f"{role} did not complete")
            time.sleep(0.05)
        emit("role_completed", role=role, history=len(live.engine.records), invocations=live.activity.invocations)
    finally:
        live.close()


def start_role(dsn: str, role: str, parent: str, child: str, credential: str) -> subprocess.Popen:
    env = {
        **os.environ,
        "IMPETUS_DEMO_DSN": dsn,
        "IMPETUS_DEMO_ROLE": role,
        "IMPETUS_DEMO_PARENT": parent,
        "IMPETUS_DEMO_CHILD": child,
        "IMPETUS_DEMO_CREDENTIAL": credential,
    }
    return subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "--internal-role"],
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def wait_event(process: subprocess.Popen, wanted: str, timeout: float = 35) -> dict:
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    deadline, seen = time.monotonic() + timeout, []
    while time.monotonic() < deadline:
        for key, _ in selector.select(0.2):
            line = key.fileobj.readline()
            if line:
                seen.append(line.rstrip())
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get("event") == wanted:
                    return event
        if process.poll() is not None:
            break
    stderr = process.stderr.read() if process.stderr else ""
    raise RuntimeError(f"subprocess failed waiting for {wanted}; rc={process.poll()} stdout={seen!r} stderr={stderr}")


def history_types(dsn: str, instance: str) -> tuple[str, ...]:
    with psycopg.connect(dsn, autocommit=True) as connection:
        return tuple(type(record).__name__ for record in PostgresHistoryStore(connection, instance).records)


def replay_inert(dsn: str, role: str, authority_id: str, parent: str, child: str, credential: str) -> tuple[int, int]:
    live = open_role(dsn, role, authority_id, parent, child, credential)
    try:
        before = len(live.engine.records)
        live.drive()
        assert live.engine.status is Status.COMPLETED
        return len(live.engine.records) - before, live.activity.invocations
    finally:
        live.close()


def run_local(dsn: str, parent: str, child: str, credentials: dict[str, str]) -> None:
    bootstrap(dsn, parent, child, credentials)
    parent_role = open_role(dsn, "parent", parent, parent, child, credentials[parent])
    child_role = open_role(dsn, "child", child, parent, child, credentials[child])
    try:
        parent_role.drive()
        assert parent_role.engine.status is Status.AWAITING
        child_role.drain()
        child_role.drive()
        parent_role.drain()
        parent_role.drive()
        assert parent_role.engine.status is child_role.engine.status is Status.COMPLETED
    finally:
        parent_role.close()
        child_role.close()


def run_in_flight_resume(dsn: str, parent: str, child: str, credentials: dict[str, str]) -> int:
    """Lose every child live object after ActivityRequested, then finish from history alone."""
    bootstrap(dsn, parent, child, credentials)
    parent_role = open_role(dsn, "parent", parent, parent, child, credentials[parent])
    child_role = open_role(
        dsn,
        "child",
        child,
        parent,
        child,
        credentials[child],
        dispatch=CustodyDroppingDispatch(),
    )
    resumed_child = None
    try:
        parent_role.drive()
        assert parent_role.engine.status is Status.AWAITING
        assert child_role.drain() == 1
        outcome = child_role.drive()
        assert outcome.waiting
        assert child_role.activity.invocations == 0
        (occurrence,) = child_role.engine.in_flight
        assert occurrence.binding.transition == RESPOND

        # The crash boundary: discard every object derived over the child
        # history after the durable begin, before its activity dispatch.
        child_role.close()
        child_role = None
        resumed_child = open_role(dsn, "child", child, parent, child, credentials[child])
        assert tuple(item.id for item in resumed_child.engine.in_flight) == (occurrence.id,)
        assert resumed_child.engine.in_flight[0].binding.transition == RESPOND
        resumed_child.drive()
        parent_role.drain()
        parent_role.drive()
        assert resumed_child.engine.status is parent_role.engine.status is Status.COMPLETED
        assert resumed_child.activity.invocations == 1
        return occurrence.id
    finally:
        parent_role.close()
        if child_role is not None:
            child_role.close()
        if resumed_child is not None:
            resumed_child.close()


def start_postgres() -> tuple[str, str]:
    name = f"impetus-cv5-demo-{os.getpid()}"
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
            "POSTGRES_PASSWORD=postgres",
            "--tmpfs",
            "/var/lib/postgresql/data",
            POSTGRES_IMAGE,
        ],
        check=True,
        capture_output=True,
    )
    dsn, deadline = f"postgres://postgres:postgres@127.0.0.1:{PORT}/postgres", time.monotonic() + 60
    while True:
        try:
            psycopg.connect(dsn, connect_timeout=2).close()
            return dsn, name
        except psycopg.OperationalError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.2)


def run(dsn: str) -> None:
    suffix = uuid4().hex[:8]
    split_parent, split_child = f"split-parent-{suffix}", f"split-child-{suffix}"
    split_credentials = {split_parent: issue_credential(), split_child: issue_credential()}
    bootstrap(dsn, split_parent, split_child, split_credentials)
    with psycopg.connect(dsn, autocommit=True) as connection:
        discovered = PostgresFabric(connection, split_parent, split_credentials[split_parent]).discover(
            "fabric.request", {"version": 1}
        )
    assert len(discovered) == 1
    assert (discovered[0].recipient, discovered[0].source) == (split_child, str(REQUEST_SOURCE))
    parent_process = start_role(dsn, "parent", split_parent, split_child, split_credentials[split_parent])
    waiting = wait_event(parent_process, "parent_waiting")
    with psycopg.connect(dsn, autocommit=True) as connection:
        offline_pending = len(PostgresFabric(connection, split_child, split_credentials[split_child]).pending())
    assert offline_pending == 1
    child_process = start_role(dsn, "child", split_parent, split_child, split_credentials[split_child])
    child_done = wait_event(child_process, "role_completed")
    parent_done = wait_event(parent_process, "role_completed")
    child_process.wait(timeout=5)
    parent_process.wait(timeout=5)
    assert child_process.returncode == parent_process.returncode == 0

    request = request_envelope(split_parent, split_child)
    with psycopg.connect(dsn, autocommit=True) as connection:
        duplicate = PostgresFabric(connection, split_parent, split_credentials[split_parent]).submit(request)
    assert duplicate.state == "accepted" and duplicate.duplicate and duplicate.occurrence is not None

    split_replay = (
        replay_inert(dsn, "parent", split_parent, split_parent, split_child, split_credentials[split_parent]),
        replay_inert(dsn, "child", split_child, split_parent, split_child, split_credentials[split_child]),
    )
    crash_parent, crash_child = f"crash-parent-{suffix}", f"crash-child-{suffix}"
    crash_credentials = {crash_parent: issue_credential(), crash_child: issue_credential()}
    resumed_occurrence = run_in_flight_resume(dsn, crash_parent, crash_child, crash_credentials)
    local_parent, local_child = f"local-parent-{suffix}", f"local-child-{suffix}"
    local_credentials = {local_parent: issue_credential(), local_child: issue_credential()}
    run_local(dsn, local_parent, local_child, local_credentials)
    shape_equal = history_types(dsn, split_parent) == history_types(dsn, local_parent) and history_types(
        dsn, split_child
    ) == history_types(dsn, local_child)
    assert shape_equal and split_replay == ((0, 0), (0, 0))

    print(
        f"authorities: parent={split_parent} history={parent_done['history']}; child={split_child} history={child_done['history']}"
    )
    print(f"parent: {waiting['status']} -> completed; child: completed")
    print(f"discovery: {discovered[0].recipient}/{discovered[0].source} authorized")
    print(f"offline pending count: {offline_pending}")
    print(f"duplicate: accepted/{str(duplicate.duplicate).lower()} occurrence={duplicate.occurrence}")
    print(f"local/split semantic-shape equality: {str(shape_equal).lower()}")
    print(
        f"replay: parent appends={split_replay[0][0]} invocations={split_replay[0][1]}; child appends={split_replay[1][0]} invocations={split_replay[1][1]}"
    )
    print(f"in-flight crash resume: occurrence={resumed_occurrence} dispatches=1 completed=true")
    print("overall: PASS")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn")
    parser.add_argument("--internal-role", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.internal_role:
        subprocess_role()
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
