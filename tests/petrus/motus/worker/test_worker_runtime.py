"""Provider-neutral synchronous Worker contract and Local integration."""

from __future__ import annotations

import json
import os
import select
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from petrus.motus.activity import ActivityError, ActivityInvocation, ExecutionPolicy, _OMITTED
from petrus.motus.dispatch import ActivityAttempt, InlineDispatch, WorkerDispatch
from petrus.motus.dispatch.local import LocalDispatch, LocalWorkerDispatch
from petrus.engine import Engine
from petrus.impetus.history_store import JsonlHistoryStore
from petrus.impetus.petrinet import Token
from petrus.motus.worker import Worker
from tests.absurd_support import INGRESS, ISSUE, SparkWork, topology_net


def subprocess_activities():
    """Importable Local Worker registry for process-loss and drain tests."""

    def work(invocation, *, context):
        barrier = Path(invocation.input["barrier"])
        if invocation.input["mode"] == "crash" and context.latest_details is None:
            context.heartbeat(details={"cursor": 7})
            barrier.write_text("claimed")
            time.sleep(3600)
        if invocation.input["mode"] == "drain":
            barrier.write_text("running")
            time.sleep(0.25)
        return {"cursor": None if context.latest_details is None else context.latest_details["cursor"]}

    return {"work": work}


def _start_local_worker(path: Path) -> subprocess.Popen[str]:
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "petrus.motus.worker",
            "--provider",
            "local",
            "--path",
            str(path),
            "--registry",
            "tests.petrus.motus.worker.test_worker_runtime:subprocess_activities",
            "--poll-interval",
            "0.02",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=os.environ.copy(),
    )
    assert process.stdout is not None
    readable, _, _ = select.select([process.stdout], [], [], 10)
    assert readable, "Local Worker did not become ready"
    assert json.loads(process.stdout.readline())["ready"] is True
    return process


def _wait_for_file(path: Path, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 10
    while not path.exists():
        assert process.poll() is None
        assert time.monotonic() < deadline
        time.sleep(0.01)


@dataclass
class StrictWorkerDispatch:
    attempts: list[ActivityAttempt]
    completed: list[tuple[ActivityAttempt, object]] = field(default_factory=list)
    failed: list[tuple[ActivityAttempt, str | Exception]] = field(default_factory=list)
    heartbeats: list[tuple[ActivityAttempt, object]] = field(default_factory=list)
    closed: bool = False

    def claim(self):
        return self.attempts.pop(0) if self.attempts else None

    def heartbeat(self, attempt, *, details=_OMITTED):
        self.heartbeats.append((attempt, details))
        return attempt.latest_details if details is _OMITTED else details

    def complete(self, attempt, result):
        self.completed.append((attempt, result))

    def fail(self, attempt, error):
        self.failed.append((attempt, error))

    def wait(self, timeout):
        return False

    def close(self):
        self.closed = True


def attempt(activity="work", *, details=None, instance=None):
    return ActivityAttempt(
        "provider-attempt",
        "provider-epoch",
        "provider-claimant",
        "cpu",
        ActivityInvocation(activity),
        details,
        instance,
    )


def test_worker_dispatch_is_the_exact_runtime_checkable_worker_surface():
    assert isinstance(StrictWorkerDispatch([]), WorkerDispatch)


def test_worker_runs_activity_with_exact_attempt_context_and_heartbeat_then_stops():
    claimed = attempt(details={"cursor": 1}, instance="tenant-one")
    provider = StrictWorkerDispatch([claimed])
    observed = {}

    def work(invocation, *, context):
        observed.update(
            attempt_id=context.attempt_id,
            epoch=context.epoch,
            claimant=context.claimant,
            instance=context.instance,
            latest=context.latest_details,
        )
        context.heartbeat(details={"cursor": 2})
        worker.stop()
        return {"ok": True}

    worker = Worker(provider, {"work": work})
    worker.run(poll_interval=0)

    assert observed == {
        "attempt_id": claimed.attempt_id,
        "epoch": claimed.epoch,
        "claimant": claimed.claimant,
        "instance": "tenant-one",
        "latest": {"cursor": 1},
    }
    assert provider.heartbeats == [(claimed, {"cursor": 2})]
    assert provider.completed == [(claimed, {"ok": True})]
    assert provider.closed


def test_missing_activity_and_json_unfaithful_result_report_failure():
    missing, unfaithful = attempt("missing"), attempt("bad")
    provider = StrictWorkerDispatch([missing, unfaithful])

    def bad(invocation, *, context):
        return object()

    worker = Worker(provider, {"bad": bad})
    worker._drain()

    assert len(provider.failed) == 2
    assert isinstance(provider.failed[0][1], LookupError)
    assert isinstance(provider.failed[1][1], TypeError)


def test_scoped_resolver_refuses_missing_scope_instead_of_falling_back_to_default():
    unscoped = attempt()
    provider = StrictWorkerDispatch([unscoped])
    worker = Worker(
        provider,
        {"work": lambda invocation, *, context: "wrong-default"},
        resolver=lambda instance, activity: None,
    )

    assert worker.run_available(limit=1) == 1
    assert provider.completed == []
    assert isinstance(provider.failed[0][1], LookupError)
    assert "requires an Activity Attempt instance" in str(provider.failed[0][1])


def test_local_worker_provider_executes_and_engine_collects(tmp_path):
    path = tmp_path / "dispatch.db"
    engine = LocalDispatch(path, instance="one", default_queue="cpu")
    invocation = ActivityInvocation("work", input={"value": 2}, policy=ExecutionPolicy(attempts=1))
    engine.dispatch(1, invocation)
    provider = LocalWorkerDispatch(path, queues=("cpu",), worker_id="test")
    worker = Worker(provider, {"work": lambda invocation, *, context: invocation.input})
    worker._drain()

    assert engine.collect() == ((1, {"value": 2}),)


def test_one_worker_resolves_scoped_and_default_modules_for_isolated_instances(tmp_path):
    path = tmp_path / "dispatch.db"
    one = LocalDispatch(path, instance="one")
    two = LocalDispatch(path, instance="two")
    invocation = ActivityInvocation("publish")
    one.dispatch(1, invocation)
    two.dispatch(1, invocation)
    observed = []

    def implementation(label):
        def publish(invocation, *, context):
            observed.append((label, context.instance))
            return {"module": label, "instance": context.instance}

        return publish

    modules = {"one": {"publish": implementation("scoped")}}
    worker = Worker(
        LocalWorkerDispatch(path, worker_id="shared"),
        {"publish": implementation("default")},
        resolver=lambda instance, activity: modules.get(instance, {}).get(activity),
    )

    assert worker.run_available(limit=2) == 2
    assert observed == [("scoped", "one"), ("default", "two")]
    assert one.collect() == ((1, {"module": "scoped", "instance": "one"}),)
    assert one.collect() == ()
    assert two.collect() == ((1, {"module": "default", "instance": "two"}),)
    worker.close()


def test_reconstructed_worker_resolves_delayed_retry_from_durable_instance_scope(tmp_path):
    path = tmp_path / "dispatch.db"
    dispatch = LocalDispatch(path, instance="one")
    dispatch.dispatch(
        1,
        ActivityInvocation(
            "publish",
            policy=ExecutionPolicy(attempts=2, initial_interval=0.02, heartbeat_timeout=1),
        ),
    )

    def resolver(instance, activity):
        assert (instance, activity) == ("one", "publish")

        def publish(invocation, *, context):
            if context.epoch == "1":
                raise ActivityError("transient", retryable=True)
            return {"instance": context.instance, "epoch": context.epoch}

        return publish

    first = Worker(LocalWorkerDispatch(path, worker_id="first"), {}, resolver=resolver)
    assert first.run_available(limit=1) == 1
    first.close()
    assert dispatch.collect() == ()

    time.sleep(0.03)
    replacement = Worker(LocalWorkerDispatch(path, worker_id="replacement"), {}, resolver=resolver)
    assert replacement.run_available(limit=1) == 1
    replacement.close()

    assert dispatch.collect() == ((1, {"instance": "one", "epoch": "2"}),)


def test_bounded_worker_pump_does_not_wait_or_close_and_refuses_concurrent_driving():
    entered = threading.Event()
    release = threading.Event()
    provider = StrictWorkerDispatch([attempt(), attempt()])

    def work(invocation, *, context):
        entered.set()
        release.wait(2)
        return "done"

    worker = Worker(provider, {"work": work})
    driving = threading.Thread(target=lambda: worker.run_available(limit=1))
    driving.start()
    assert entered.wait(1)
    with pytest.raises(RuntimeError, match="already being driven"):
        worker.run_available(limit=1)
    release.set()
    driving.join(2)

    assert len(provider.attempts) == 1
    assert not provider.closed
    worker.close()
    worker.close()
    assert provider.closed


def test_worker_close_failure_releases_driver_guard_and_leaves_worker_closed():
    class RefusingClose(StrictWorkerDispatch):
        def close(self):
            raise OSError("close refused")

    provider = RefusingClose([attempt()])

    def work(invocation, *, context):
        worker.stop()
        return "done"

    worker = Worker(provider, {"work": work})
    with pytest.raises(OSError, match="close refused"):
        worker.run(poll_interval=0)
    with pytest.raises(RuntimeError, match="closed"):
        worker.run_available(limit=0)
    worker.close()


def test_controlled_sequential_local_execution_is_byte_identical_to_inline_history(tmp_path):
    """Changing only custody topology does not change a sequential canonical trace."""

    def activity(invocation, *, context):
        return f"sparked {invocation.input['id']}"

    histories = []
    markings = []
    for arrangement in ("inline", "local"):
        history_path = tmp_path / f"{arrangement}.jsonl"
        dispatch_path = tmp_path / "dispatch.sqlite3"
        dispatch = (
            InlineDispatch({"spark_work": activity})
            if arrangement == "inline"
            else LocalDispatch(dispatch_path, instance="sequential")
        )
        engine = Engine.create(
            topology_net(),
            "sequential",
            history=JsonlHistoryStore(history_path),
            dispatch=dispatch,
            handlers={"spark_work": SparkWork()},
        )
        engine.deliver(INGRESS, Token(ISSUE, {"id": "one"}))
        while engine.advance().ready:
            pass
        if arrangement == "local":
            Worker(LocalWorkerDispatch(dispatch_path), {"spark_work": activity})._drain()
            while engine.advance().ready:
                pass
        histories.append(history_path.read_bytes())
        markings.append(engine.marking)
        engine.close()

    assert histories[0] == histories[1]
    assert markings[0] == markings[1]


def test_killed_local_worker_reassigns_with_recovered_heartbeat_details(tmp_path):
    path = tmp_path / "dispatch.sqlite3"
    barrier = tmp_path / "claimed"
    dispatch = LocalDispatch(path, instance="one")
    dispatch.dispatch(
        1,
        ActivityInvocation(
            "work",
            input={"mode": "crash", "barrier": str(barrier)},
            policy=ExecutionPolicy(attempts=2, heartbeat_timeout=1),
        ),
    )
    first = _start_local_worker(path)
    try:
        _wait_for_file(barrier, first)
        first.kill()
        first.wait(timeout=5)
        time.sleep(1.05)
        replacement = _start_local_worker(path)
        try:
            assert dispatch.wait_for_results(10)
            assert dispatch.collect() == ((1, {"cursor": 7}),)
        finally:
            replacement.terminate()
            replacement.wait(timeout=5)
    finally:
        if first.poll() is None:
            first.kill()
            first.wait(timeout=5)


def test_sigterm_drains_the_in_flight_local_activity_before_worker_exit(tmp_path):
    path = tmp_path / "dispatch.sqlite3"
    barrier = tmp_path / "running"
    dispatch = LocalDispatch(path, instance="one")
    dispatch.dispatch(
        1,
        ActivityInvocation(
            "work",
            input={"mode": "drain", "barrier": str(barrier)},
            policy=ExecutionPolicy(attempts=1),
        ),
    )
    process = _start_local_worker(path)
    try:
        _wait_for_file(barrier, process)
        process.terminate()
        process.wait(timeout=5)
        assert process.returncode == 0
        assert dispatch.collect() == ((1, {"cursor": None}),)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
