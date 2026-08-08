from __future__ import annotations

from collections.abc import Mapping
from dataclasses import FrozenInstanceError, dataclass
from types import MappingProxyType

import psycopg
import pytest

from petrus.motus.activity import (
    HEARTBEAT_DETAILS_LIMIT,
    ActivityDeclaration,
    ActivityInvocation,
    ExecutionPolicy,
    snapshot_heartbeat_details,
)
from petrus.motus.dispatch import InlineDispatch
from petrus.motus.dispatch.absurd import _ReconnectableGuardedDispatch


@dataclass(frozen=True)
class AttemptModel:
    epoch: int = 0
    claimant: str | None = None
    deadline: int | None = None
    state: str = "pending"

    def claim(self, claimant: str, *, now: int, timeout: int) -> AttemptModel:
        if self.state == "terminal" or (self.state == "running" and now < self.deadline):
            raise RuntimeError("not claimable")
        return AttemptModel(self.epoch + 1, claimant, now + timeout, "running")

    def heartbeat(self, claimant: str, epoch: int, *, now: int, timeout: int) -> AttemptModel:
        self._guard(claimant, epoch, now=now)
        return AttemptModel(epoch, claimant, now + timeout, "running")

    def terminal(self, claimant: str, epoch: int, *, now: int) -> AttemptModel:
        self._guard(claimant, epoch, now=now)
        return AttemptModel(epoch, claimant, self.deadline, "terminal")

    def _guard(self, claimant: str, epoch: int, *, now: int) -> None:
        if self.state != "running" or claimant != self.claimant or epoch != self.epoch or now >= self.deadline:
            raise RuntimeError("stale Attempt")


def test_attempt_state_model_covers_renewal_expiry_reassignment_terminal_and_stale_refusal():
    first = AttemptModel().claim("worker-a", now=0, timeout=10)
    renewed = first.heartbeat("worker-a", 1, now=5, timeout=20)
    assert renewed.deadline == 25

    second = renewed.claim("worker-b", now=25, timeout=10)
    assert (second.epoch, second.claimant, second.deadline) == (2, "worker-b", 35)
    for stale in (renewed.heartbeat, renewed.terminal):
        with pytest.raises(RuntimeError, match="stale Attempt"):
            stale("worker-a", 1, now=25, **({"timeout": 10} if stale.__name__ == "heartbeat" else {}))

    terminal = second.terminal("worker-b", 2, now=30)
    for stale in (terminal.heartbeat, terminal.terminal):
        with pytest.raises(RuntimeError, match="stale Attempt"):
            stale("worker-b", 2, now=30, **({"timeout": 10} if stale.__name__ == "heartbeat" else {}))


def test_activity_declaration_and_execution_policy_require_positive_integer_timeouts():
    assert ActivityDeclaration("work").heartbeat_timeout is None
    assert ActivityDeclaration("work", heartbeat_timeout=7).heartbeat_timeout == 7
    assert ExecutionPolicy().heartbeat_timeout == 30
    for invalid in (True, 0, -1, 1.5):
        with pytest.raises(ValueError, match="heartbeat_timeout"):
            ActivityDeclaration("work", heartbeat_timeout=invalid)
        with pytest.raises(ValueError, match="heartbeat_timeout"):
            ExecutionPolicy(heartbeat_timeout=invalid)


def test_inline_context_has_synthetic_identity_and_detached_omitted_null_details():
    source = {"nested": [1]}
    observed = {}

    def activity(invocation, *, context):
        observed.update(
            attempt_id=context.attempt_id,
            epoch=context.epoch,
            claimant=context.claimant,
            initial=context.latest_details,
        )
        first = context.heartbeat(details=source)
        source["nested"].append(2)
        observed["preserved"] = context.heartbeat()
        observed["null"] = context.heartbeat(details=None)
        return first

    registry = {"work": activity}
    adapter = InlineDispatch(registry)
    registry.clear()

    assert adapter(ActivityInvocation("work")) == {"nested": [1]}
    assert observed == {
        "attempt_id": "inline-1",
        "epoch": "1",
        "claimant": "inline",
        "initial": None,
        "preserved": {"nested": [1]},
        "null": None,
    }
    with pytest.raises(TypeError):
        adapter.activities["other"] = activity
    with pytest.raises(FrozenInstanceError):
        adapter.activities = {}


@pytest.mark.parametrize("value", [{"s": "é", "items": [True, None, 4, 1.5]}, [1], "text", 2, 2.5, True, None])
def test_details_accept_every_json_faithful_shape_and_detach(value):
    assert snapshot_heartbeat_details(value) == value


def test_details_normalize_arbitrary_nested_mappings_and_detach():
    class CustomMapping(Mapping):
        def __init__(self, values):
            self.values = values

        def __getitem__(self, key):
            return self.values[key]

        def __iter__(self):
            return iter(self.values)

        def __len__(self):
            return len(self.values)

    nested = [1]
    source = MappingProxyType({"custom": CustomMapping({"nested": nested})})
    snapshot = snapshot_heartbeat_details(source)
    nested.append(2)

    assert snapshot == {"custom": {"nested": [1]}}
    assert type(snapshot) is dict
    assert type(snapshot["custom"]) is dict


def test_details_enforce_json_faithfulness_finite_numbers_and_utf8_byte_limit():
    for invalid in ({1: "non-string key"}, (1, 2), {"n": float("nan")}, {"n": float("inf")}, object()):
        with pytest.raises(ValueError, match="heartbeat details"):
            snapshot_heartbeat_details(invalid)
    assert snapshot_heartbeat_details("x" * (HEARTBEAT_DETAILS_LIMIT - 2))
    with pytest.raises(ValueError, match="limit"):
        snapshot_heartbeat_details("x" * (HEARTBEAT_DETAILS_LIMIT - 1))


@pytest.mark.parametrize("error", [psycopg.OperationalError("closed"), psycopg.InterfaceError("broken")])
def test_reconnectable_heartbeat_replaces_closed_transport_once_and_never_retries_replacement(error, monkeypatch):
    calls = []

    class Dispatch:
        def heartbeat(self, queue, **operation):
            calls.append((queue, operation))
            raise error

    facade = object.__new__(_ReconnectableGuardedDispatch)
    facade._dispatch = Dispatch()
    facade.connection = type("Connection", (), {"closed": True, "broken": False})()
    replacements = []
    monkeypatch.setattr(facade, "_replace_connection", lambda: replacements.append(True))

    with pytest.raises(type(error)):
        facade.heartbeat("queue", task_id="task")
    assert len(calls) == 2
    assert replacements == [True]


@pytest.mark.parametrize(
    "error",
    [
        psycopg.errors.QueryCanceled("cancelled"),
        psycopg.errors.DeadlockDetected("deadlock"),
        psycopg.DataError("bad data"),
        psycopg.ProgrammingError("bad query"),
        psycopg.IntegrityError("constraint"),
        RuntimeError("stale Activity Attempt"),
    ],
)
def test_reconnectable_heartbeat_does_not_replace_or_retry_semantic_errors(error, monkeypatch):
    calls = 0

    class Dispatch:
        def heartbeat(self, queue, **operation):
            nonlocal calls
            calls += 1
            raise error

    facade = object.__new__(_ReconnectableGuardedDispatch)
    facade._dispatch = Dispatch()
    facade.connection = type("Connection", (), {"closed": False, "broken": False})()
    replacements = []
    monkeypatch.setattr(facade, "_replace_connection", lambda: replacements.append(True))

    with pytest.raises(type(error)):
        facade.heartbeat("queue", task_id="task")
    assert calls == 1
    assert replacements == []
