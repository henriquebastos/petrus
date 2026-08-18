"""Joined History/Dispatch transaction-fault DST profiles and recovery stories."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

import psycopg
from psycopg import sql
from pydantic import JsonValue

from petrus.engine import Engine
from petrus.engine.absurd import create_engine, load_engine
from petrus.impetus.history import (
    ActivityCompleted,
    ActivityFailed,
    ActivityRequested,
    CandidateSelected,
    ExternalEventDelivered,
    FiringBegun,
    FiringCompleted,
    FiringFailed,
    ScopeOpened,
    ScopeReset,
)
from petrus.impetus.history_store.postgres import PostgresHistoryStore
from petrus.impetus.petrinet import Arc, Marking, Net, NetPath, Place, Token, Transition
from petrus.motus.activity import ActivityFailure, ActivityInvocation
from petrus.motus.dispatch import ActivityAttempt
from petrus.motus.dispatch.absurd import AbsurdWorkerDispatch
from petrus.testing.dst import (
    ActionDisposition,
    ApplyResult,
    Budget,
    CheckResult,
    CheckerIdentity,
    Command,
    Disposition,
    Fault,
    FaultDisposition,
    GenerationStart,
    Observation,
    ObservationRequest,
    ProfileIdentity,
    ScenarioArtifactV3,
    ScenarioContext,
    ScheduledCommand,
    Timeline,
    World,
    digest_json,
)

SOURCE = NetPath("source")
INPUT = NetPath("input")
DONE = NetPath("done")
PROJECT = NetPath("project")
INSTANCE_ID = "dst-world-joined-begin-refusal"
QUEUE = "dst_joined_begin"
SCENARIO_ID = "joined-begin-commit-refusal-world-v3"
DISPATCH_SCENARIO_ID = "joined-dispatch-refusal-world-v3"
PROJECTION_SCENARIO_ID = "joined-projection-commit-refusal-world-v3"
PROJECTION_ACK_LOSS_SCENARIO_ID = "joined-projection-ack-loss-world-v3"
ACK_LOSS_SCENARIO_ID = "joined-begin-ack-loss-world-v3"
TERMINAL_REFUSAL_SCENARIO_ID = "joined-terminal-commit-refusal-world-v3"
TERMINAL_ACK_LOSS_SCENARIO_ID = "joined-terminal-ack-loss-world-v3"
FAILURE_REFUSAL_SCENARIO_ID = "joined-failure-commit-refusal-world-v3"
FAILURE_ACK_LOSS_SCENARIO_ID = "joined-failure-ack-loss-world-v3"
RESET_REFUSAL_SCENARIO_ID = "joined-reset-commit-refusal-world-v3"
RESET_ACK_LOSS_SCENARIO_ID = "joined-reset-ack-loss-world-v3"
CANCELLATION_SCENARIO_ID = "joined-cancellation-commit-refusal-world-v3"
CANCELLATION_ACK_LOSS_SCENARIO_ID = "joined-cancellation-ack-loss-world-v3"

PROFILE_IDENTITY = ProfileIdentity(
    name="petrus.engine.joined-begin-commit-refusal",
    version=1,
    digest=digest_json(
        {
            "commands": ["engine.drive"],
            "fault": {
                "disposition": "refuse",
                "name": "history.commit-refuse",
                "target": "activity_requested",
            },
            "instance": INSTANCE_ID,
            "observations": [
                "engine.joined-commit-authority",
                "joined-begin-refused",
                "joined-begin-recovered",
            ],
            "provider": "petrus.engine.absurd",
            "property": "joined semantic begin and Dispatch spawn commit or vanish together",
            "queue": QUEUE,
        }
    ),
)
DISPATCH_PROFILE_IDENTITY = ProfileIdentity(
    name="petrus.engine.joined-dispatch-refusal",
    version=1,
    digest=digest_json(
        {
            "commands": ["engine.drive"],
            "fault": {
                "disposition": "refuse",
                "name": "dispatch.refuse",
                "target": "activity_requested",
            },
            "instance": INSTANCE_ID,
            "observations": [
                "engine.joined-commit-authority",
                "joined-dispatch-recovered",
                "joined-dispatch-refused",
            ],
            "provider": "petrus.engine.absurd",
            "property": "failed joined Dispatch spawn rolls back the uncommitted semantic begin",
            "queue": QUEUE,
        }
    ),
)
PROJECTION_PROFILE_IDENTITY = ProfileIdentity(
    name="petrus.engine.joined-projection-commit-refusal",
    version=1,
    digest=digest_json(
        {
            "commands": ["engine.drive", "worker.claim", "worker.complete"],
            "fault": {
                "disposition": "refuse",
                "name": "history.commit-refuse",
                "target": "projection_committed",
            },
            "instance": INSTANCE_ID,
            "observations": [
                "engine.joined-projection-authority",
                "joined-projection-recovered",
                "joined-projection-refused",
            ],
            "provider": "petrus.engine.absurd",
            "property": "a frozen terminal survives refusal of the later projection commit",
            "queue": QUEUE,
        }
    ),
)
PROJECTION_ACK_LOSS_PROFILE_IDENTITY = ProfileIdentity(
    name="petrus.engine.joined-projection-ack-loss",
    version=1,
    digest=digest_json(
        {
            "commands": ["engine.drive", "worker.claim", "worker.complete"],
            "fault": {
                "disposition": "raise",
                "name": "history.lose-ack",
                "target": "projection_committed",
            },
            "instance": INSTANCE_ID,
            "observations": [
                "engine.joined-accepted-projection-authority",
                "joined-projection-ack-lost",
                "joined-projection-ack-recovered",
            ],
            "provider": "petrus.engine.absurd",
            "property": "an accepted projection survives loss of its commit acknowledgement",
            "queue": QUEUE,
        }
    ),
)
ACK_LOSS_PROFILE_IDENTITY = ProfileIdentity(
    name="petrus.engine.joined-begin-ack-loss",
    version=1,
    digest=digest_json(
        {
            "commands": ["engine.drive"],
            "fault": {
                "disposition": "raise",
                "name": "history.lose-ack",
                "target": "activity_requested_committed",
            },
            "instance": INSTANCE_ID,
            "observations": [
                "engine.joined-accepted-begin-authority",
                "joined-begin-ack-lost",
                "joined-begin-ack-recovered",
            ],
            "provider": "petrus.engine.absurd",
            "property": "an accepted joined begin survives loss of its commit acknowledgement",
            "queue": QUEUE,
        }
    ),
)
TERMINAL_ACK_LOSS_PROFILE_IDENTITY = ProfileIdentity(
    name="petrus.engine.joined-terminal-ack-loss",
    version=1,
    digest=digest_json(
        {
            "commands": ["engine.drive", "worker.claim", "worker.complete"],
            "fault": {
                "disposition": "raise",
                "name": "history.lose-ack",
                "target": "activity_completed_committed",
            },
            "instance": INSTANCE_ID,
            "observations": [
                "engine.joined-accepted-terminal-authority",
                "joined-terminal-ack-lost",
                "joined-terminal-ack-recovered",
            ],
            "provider": "petrus.engine.absurd",
            "property": "an accepted joined terminal survives loss of its commit acknowledgement",
            "queue": QUEUE,
        }
    ),
)
TERMINAL_REFUSAL_PROFILE_IDENTITY = ProfileIdentity(
    name="petrus.engine.joined-terminal-commit-refusal",
    version=1,
    digest=digest_json(
        {
            "commands": ["engine.drive", "worker.claim", "worker.complete"],
            "fault": {
                "disposition": "refuse",
                "name": "history.commit-refuse",
                "target": "activity_completed",
            },
            "instance": INSTANCE_ID,
            "observations": [
                "engine.joined-terminal-authority",
                "joined-terminal-refused",
                "joined-terminal-recovered",
            ],
            "provider": "petrus.engine.absurd",
            "property": "a completed provider task survives refusal of its semantic terminal commit",
            "queue": QUEUE,
        }
    ),
)
FAILURE_REFUSAL_PROFILE_IDENTITY = ProfileIdentity(
    name="petrus.engine.joined-failure-commit-refusal",
    version=1,
    digest=digest_json(
        {
            "commands": ["engine.drive", "worker.claim", "worker.fail"],
            "fault": {
                "disposition": "refuse",
                "name": "history.commit-refuse",
                "target": "activity_failed",
            },
            "instance": INSTANCE_ID,
            "observations": [
                "engine.joined-failure-authority",
                "joined-failure-refused",
                "joined-failure-recovered",
            ],
            "provider": "petrus.engine.absurd",
            "property": "a failed provider task survives refusal of its semantic failure commit",
            "queue": QUEUE,
        }
    ),
)
FAILURE_ACK_LOSS_PROFILE_IDENTITY = ProfileIdentity(
    name="petrus.engine.joined-failure-ack-loss",
    version=1,
    digest=digest_json(
        {
            "commands": ["engine.drive", "worker.claim", "worker.fail"],
            "fault": {
                "disposition": "raise",
                "name": "history.lose-ack",
                "target": "activity_failed_committed",
            },
            "instance": INSTANCE_ID,
            "observations": [
                "engine.joined-accepted-failure-authority",
                "joined-failure-ack-lost",
                "joined-failure-ack-recovered",
            ],
            "provider": "petrus.engine.absurd",
            "property": "an accepted ActivityFailed survives loss of its commit acknowledgement",
            "queue": QUEUE,
        }
    ),
)
RESET_REFUSAL_PROFILE_IDENTITY = ProfileIdentity(
    name="petrus.engine.joined-reset-commit-refusal",
    version=1,
    digest=digest_json(
        {
            "commands": [
                "engine.drive",
                "scope.open",
                "scope.reset",
                "source.deliver",
                "worker.claim",
                "worker.complete",
            ],
            "fault": {
                "disposition": "refuse",
                "name": "history.commit-refuse",
                "target": "scope_reset",
            },
            "instance": INSTANCE_ID,
            "observations": [
                "engine.joined-reset-refusal-authority",
                "joined-reset-ready",
                "joined-reset-refused",
                "joined-reset-recovered",
                "joined-reset-terminal-recovered",
            ],
            "provider": "petrus.engine.absurd",
            "property": "a refused ScopeReset leaves the old lifecycle and Worker attempt authoritative",
            "queue": QUEUE,
        }
    ),
)
RESET_ACK_LOSS_PROFILE_IDENTITY = ProfileIdentity(
    name="petrus.engine.joined-reset-ack-loss",
    version=1,
    digest=digest_json(
        {
            "commands": [
                "engine.drive",
                "scope.open",
                "scope.reset",
                "source.deliver",
                "worker.claim",
                "worker.complete-stale",
            ],
            "fault": {
                "disposition": "raise",
                "name": "history.lose-ack",
                "target": "scope_reset_committed",
            },
            "instance": INSTANCE_ID,
            "observations": [
                "engine.joined-accepted-reset-authority",
                "joined-reset-ack-ready",
                "joined-reset-ack-lost",
                "joined-reset-ack-recovered",
                "joined-reset-ack-worker-fenced",
            ],
            "provider": "petrus.engine.absurd",
            "property": "an accepted ScopeReset survives acknowledgement loss and installs one cancellation fence",
            "queue": QUEUE,
        }
    ),
)
CANCELLATION_PROFILE_IDENTITY = ProfileIdentity(
    name="petrus.engine.joined-cancellation-commit-refusal",
    version=1,
    digest=digest_json(
        {
            "commands": [
                "engine.drive",
                "scope.open",
                "scope.reset",
                "source.deliver",
                "worker.claim",
                "worker.complete-stale",
            ],
            "fault": {
                "disposition": "refuse",
                "name": "history.commit-refuse",
                "target": "cancellation_committed",
            },
            "instance": INSTANCE_ID,
            "observations": [
                "engine.joined-cancellation-authority",
                "joined-cancellation-ready",
                "joined-cancellation-refused",
                "joined-cancellation-recovered",
                "joined-late-worker-fenced",
            ],
            "provider": "petrus.engine.absurd",
            "property": "a committed scope reset survives refusal and fresh-load repair of its task tombstone",
            "queue": QUEUE,
        }
    ),
)
CANCELLATION_ACK_LOSS_PROFILE_IDENTITY = ProfileIdentity(
    name="petrus.engine.joined-cancellation-ack-loss",
    version=1,
    digest=digest_json(
        {
            "commands": [
                "engine.drive",
                "scope.open",
                "scope.reset",
                "source.deliver",
                "worker.claim",
                "worker.complete-stale",
            ],
            "fault": {
                "disposition": "raise",
                "name": "history.lose-ack",
                "target": "cancellation_committed",
            },
            "instance": INSTANCE_ID,
            "observations": [
                "engine.joined-accepted-cancellation-authority",
                "joined-cancellation-ack-ready",
                "joined-cancellation-ack-lost",
                "joined-cancellation-ack-recovered",
                "joined-cancellation-ack-worker-fenced",
            ],
            "provider": "petrus.engine.absurd",
            "property": "an accepted post-reset cancellation survives loss of its commit acknowledgement",
            "queue": QUEUE,
        }
    ),
)
CHECKER_IDENTITY = CheckerIdentity(
    name="petrus.engine.joined-commit-authority",
    version=1,
    digest=digest_json(
        {"property": ("durable candidate, firing, request, and task counts equal accepted joined begin transactions")}
    ),
)
PROJECTION_CHECKER_IDENTITY = CheckerIdentity(
    name="petrus.engine.joined-projection-authority",
    version=1,
    digest=digest_json(
        {
            "property": (
                "worker completion bounds one frozen terminal; accepted projection transactions bound one projection"
            )
        }
    ),
)
PROJECTION_ACK_LOSS_CHECKER_IDENTITY = CheckerIdentity(
    name="petrus.engine.joined-accepted-projection-authority",
    version=1,
    digest=digest_json(
        {"property": "an acknowledgement-lost projection remains singular and converged after fresh load"}
    ),
)
ACK_LOSS_CHECKER_IDENTITY = CheckerIdentity(
    name="petrus.engine.joined-accepted-begin-authority",
    version=1,
    digest=digest_json(
        {"property": ("an acknowledged-lost begin has exactly one accepted semantic prefix and one durable task")}
    ),
)
TERMINAL_ACK_LOSS_CHECKER_IDENTITY = CheckerIdentity(
    name="petrus.engine.joined-accepted-terminal-authority",
    version=1,
    digest=digest_json(
        {"property": ("an acknowledged-lost terminal remains singular and authorizes exactly one later projection")}
    ),
)
TERMINAL_REFUSAL_CHECKER_IDENTITY = CheckerIdentity(
    name="petrus.engine.joined-terminal-authority",
    version=1,
    digest=digest_json(
        {
            "property": (
                "one Worker completion authorizes one accepted terminal after refusal and exactly one projection"
            )
        }
    ),
)
FAILURE_REFUSAL_CHECKER_IDENTITY = CheckerIdentity(
    name="petrus.engine.joined-failure-authority",
    version=1,
    digest=digest_json(
        {"property": ("one Worker failure authorizes one accepted ActivityFailed after refusal and one FiringFailed")}
    ),
)
FAILURE_ACK_LOSS_CHECKER_IDENTITY = CheckerIdentity(
    name="petrus.engine.joined-accepted-failure-authority",
    version=1,
    digest=digest_json(
        {"property": ("an acknowledgement-lost ActivityFailed remains singular and authorizes one FiringFailed")}
    ),
)
RESET_REFUSAL_CHECKER_IDENTITY = CheckerIdentity(
    name="petrus.engine.joined-reset-refusal-authority",
    version=1,
    digest=digest_json(
        {
            "property": (
                "a refused ScopeReset leaves generation one and its Worker completion authoritative for one "
                "terminal and projection after fresh load"
            )
        }
    ),
)
RESET_ACK_LOSS_CHECKER_IDENTITY = CheckerIdentity(
    name="petrus.engine.joined-accepted-reset-authority",
    version=1,
    digest=digest_json(
        {
            "property": (
                "an acknowledgement-lost ScopeReset reconstructs generation two, installs one tombstone, and "
                "fences its old Worker"
            )
        }
    ),
)
CANCELLATION_CHECKER_IDENTITY = CheckerIdentity(
    name="petrus.engine.joined-cancellation-authority",
    version=1,
    digest=digest_json(
        {
            "property": (
                "accepted reset authority survives a refused cancellation transaction; fresh load creates one "
                "tombstone and fences the stale Worker without semantic terminal or projection"
            )
        }
    ),
)
CANCELLATION_ACK_LOSS_CHECKER_IDENTITY = CheckerIdentity(
    name="petrus.engine.joined-accepted-cancellation-authority",
    version=1,
    digest=digest_json(
        {
            "property": (
                "an acknowledgement-lost cancellation has one accepted reset and tombstone; fresh load and a "
                "stale Worker cannot add a task, terminal, or projection"
            )
        }
    ),
)
WORLD_BUDGET = Budget(
    actions=16,
    queued_commands=2,
    timer_advances=0,
    logical_instant=0,
    reloads=1,
    predicate_polls=8,
    artifact_bytes=262_144,
)
CANCELLATION_WORLD_BUDGET = Budget(
    actions=24,
    queued_commands=2,
    timer_advances=0,
    logical_instant=0,
    reloads=1,
    predicate_polls=8,
    artifact_bytes=262_144,
)


def application_net() -> Net:
    return Net(
        places=[Place(INPUT), Place(DONE)],
        transitions=[Transition(PROJECT, handler="bridge")],
        arcs=[Arc(INPUT, PROJECT), Arc(PROJECT, DONE)],
        name="dst-world-joined-begin-refusal",
    )


def lifecycle_application_net() -> Net:
    return Net(
        places=[Place(INPUT), Place(DONE)],
        transitions=[Transition(SOURCE), Transition(PROJECT, handler="bridge")],
        arcs=[Arc(SOURCE, INPUT), Arc(INPUT, PROJECT), Arc(PROJECT, DONE)],
        name="dst-world-joined-cancellation-refusal",
    )


class JoinedBridge:
    """Deterministic application handler with profile-owned call evidence."""

    def __init__(self, prepared: Callable[[], None]) -> None:
        self._prepared = prepared

    def prepare(self, binding) -> ActivityInvocation:
        self._prepared()
        return ActivityInvocation("calculate", input=binding.tokens[0].data)

    def project(self, binding, result):
        del binding
        return {DONE: (Token("Done", result),)}


class JoinedFaultConnection:
    """One provider connection which records and may refuse a joined begin boundary."""

    def __init__(
        self,
        delegate,
        attempts: list[dict[str, JsonValue]],
        commit_refused: Callable[[], None],
        dispatch_refused: Callable[[], None],
        terminal_refused: Callable[[], None],
        projection_refused: Callable[[], None],
        projection_ack_lost: Callable[[], None],
        commit_ack_lost: Callable[[], None],
        terminal_ack_lost: Callable[[], None],
        lifecycle_attempts: list[dict[str, JsonValue]],
        reset_refused: Callable[[], None],
        reset_ack_lost: Callable[[], None],
        cancellation_refused: Callable[[], None],
        cancellation_ack_lost: Callable[[], None],
    ) -> None:
        self._delegate = delegate
        self._attempts = attempts
        self._commit_refused = commit_refused
        self._dispatch_refused = dispatch_refused
        self._terminal_refused = terminal_refused
        self._projection_refused = projection_refused
        self._projection_ack_lost = projection_ack_lost
        self._commit_ack_lost = commit_ack_lost
        self._terminal_ack_lost = terminal_ack_lost
        self._lifecycle_attempts = lifecycle_attempts
        self._reset_refused = reset_refused
        self._reset_ack_lost = reset_ack_lost
        self._cancellation_refused = cancellation_refused
        self._cancellation_ack_lost = cancellation_ack_lost
        self._record_types: list[str] = []
        self._dispatch_attempted = False
        self._cancellation_attempted = False
        self._commit_refusal: str | None = None
        self._dispatch_refusal: str | None = None
        self._terminal_refusal: str | None = None
        self._projection_refusal: str | None = None
        self._projection_ack_loss: str | None = None
        self._commit_ack_loss: str | None = None
        self._terminal_ack_loss: str | None = None
        self._reset_refusal: str | None = None
        self._reset_ack_loss: str | None = None
        self._cancellation_refusal: str | None = None
        self._cancellation_ack_loss: str | None = None

    def __getattr__(self, name: str):
        return getattr(self._delegate, name)

    @property
    def autocommit(self) -> bool:
        return self._delegate.autocommit

    def execute(self, query, params=None):
        spawning = isinstance(query, str) and query.startswith(
            "SELECT task_id, run_id, attempt, created FROM absurd.spawn_task"
        )
        if spawning:
            self._dispatch_attempted = True
            if self._dispatch_refusal is not None:
                message = self._dispatch_refusal
                self._dispatch_refusal = None
                self._attempts.append(self._attempt(False))
                self._dispatch_refused()
                raise OSError(message)
        if isinstance(query, str) and query.startswith("SELECT absurd.cancel_task"):
            self._cancellation_attempted = True
        cursor = self._delegate.execute(query, params)
        if (
            isinstance(query, str)
            and query.startswith("INSERT INTO impetus.semantic_events")
            and isinstance(params, tuple)
            and len(params) >= 3
            and isinstance(params[2], str)
        ):
            self._record_types.append(params[2])
        return cursor

    def refuse_activity_request_commit(self, message: str) -> None:
        if self._commit_refusal is not None:
            raise RuntimeError("joined commit refusal is already armed")
        self._commit_refusal = message

    def refuse_activity_request_dispatch(self, message: str) -> None:
        if self._dispatch_refusal is not None:
            raise RuntimeError("joined Dispatch refusal is already armed")
        self._dispatch_refusal = message

    def refuse_projection_commit(self, message: str) -> None:
        if self._projection_refusal is not None:
            raise RuntimeError("joined projection refusal is already armed")
        self._projection_refusal = message

    def refuse_activity_terminal_commit(self, message: str) -> None:
        if self._terminal_refusal is not None:
            raise RuntimeError("joined terminal refusal is already armed")
        self._terminal_refusal = message

    def lose_projection_commit_ack(self, message: str) -> None:
        if self._projection_ack_loss is not None:
            raise RuntimeError("joined projection acknowledgement loss is already armed")
        self._projection_ack_loss = message

    def refuse_scope_reset_commit(self, message: str) -> None:
        if self._reset_refusal is not None:
            raise RuntimeError("joined scope-reset refusal is already armed")
        self._reset_refusal = message

    def lose_scope_reset_commit_ack(self, message: str) -> None:
        if self._reset_ack_loss is not None:
            raise RuntimeError("joined scope-reset acknowledgement loss is already armed")
        self._reset_ack_loss = message

    def refuse_cancellation_commit(self, message: str) -> None:
        if self._cancellation_refusal is not None:
            raise RuntimeError("joined cancellation refusal is already armed")
        self._cancellation_refusal = message

    def lose_activity_request_commit_ack(self, message: str) -> None:
        if self._commit_ack_loss is not None:
            raise RuntimeError("joined commit acknowledgement loss is already armed")
        self._commit_ack_loss = message

    def lose_activity_terminal_commit_ack(self, message: str) -> None:
        if self._terminal_ack_loss is not None:
            raise RuntimeError("joined terminal acknowledgement loss is already armed")
        self._terminal_ack_loss = message

    def lose_cancellation_commit_ack(self, message: str) -> None:
        if self._cancellation_ack_loss is not None:
            raise RuntimeError("joined cancellation acknowledgement loss is already armed")
        self._cancellation_ack_loss = message

    def commit(self) -> None:
        joined_begin = ActivityRequested.__name__ in self._record_types
        activity_terminal = any(
            name in self._record_types for name in (ActivityCompleted.__name__, ActivityFailed.__name__)
        )
        projection_completed = FiringCompleted.__name__ in self._record_types
        scope_reset = ScopeReset.__name__ in self._record_types
        cancellation_attempted = self._cancellation_attempted
        tracked = joined_begin or any(
            name in self._record_types
            for name in (
                ActivityCompleted.__name__,
                ActivityFailed.__name__,
                FiringCompleted.__name__,
                FiringFailed.__name__,
            )
        )
        if joined_begin and self._commit_refusal is not None:
            message = self._commit_refusal
            self._commit_refusal = None
            self._attempts.append(self._attempt(False))
            self._commit_refused()
            raise OSError(message)
        if activity_terminal and self._terminal_refusal is not None:
            message = self._terminal_refusal
            self._terminal_refusal = None
            self._attempts.append(self._attempt(False))
            self._terminal_refused()
            raise OSError(message)
        if FiringCompleted.__name__ in self._record_types and self._projection_refusal is not None:
            message = self._projection_refusal
            self._projection_refusal = None
            self._attempts.append(self._attempt(False))
            self._projection_refused()
            raise OSError(message)
        if scope_reset and self._reset_refusal is not None:
            message = self._reset_refusal
            self._reset_refusal = None
            self._lifecycle_attempts.append(self._lifecycle_attempt(False, "scope_reset"))
            self._reset_refused()
            raise OSError(message)
        if cancellation_attempted and self._cancellation_refusal is not None:
            message = self._cancellation_refusal
            self._cancellation_refusal = None
            self._lifecycle_attempts.append(self._lifecycle_attempt(False, "cancellation"))
            self._cancellation_refused()
            raise OSError(message)
        self._delegate.commit()
        if tracked:
            self._attempts.append(self._attempt(True))
        if scope_reset:
            self._lifecycle_attempts.append(self._lifecycle_attempt(True, "scope_reset"))
        if cancellation_attempted:
            self._lifecycle_attempts.append(self._lifecycle_attempt(True, "cancellation"))
        self._clear_transaction()
        if joined_begin and self._commit_ack_loss is not None:
            message = self._commit_ack_loss
            self._commit_ack_loss = None
            self._commit_ack_lost()
            raise OSError(message)
        if activity_terminal and self._terminal_ack_loss is not None:
            message = self._terminal_ack_loss
            self._terminal_ack_loss = None
            self._terminal_ack_lost()
            raise OSError(message)
        if projection_completed and self._projection_ack_loss is not None:
            message = self._projection_ack_loss
            self._projection_ack_loss = None
            self._projection_ack_lost()
            raise OSError(message)
        if scope_reset and self._reset_ack_loss is not None:
            message = self._reset_ack_loss
            self._reset_ack_loss = None
            self._reset_ack_lost()
            raise OSError(message)
        if cancellation_attempted and self._cancellation_ack_loss is not None:
            message = self._cancellation_ack_loss
            self._cancellation_ack_loss = None
            self._cancellation_ack_lost()
            raise OSError(message)

    def rollback(self) -> None:
        try:
            self._delegate.rollback()
        finally:
            self._clear_transaction()

    def close(self) -> None:
        self._delegate.close()

    def _attempt(self, accepted: bool) -> dict[str, JsonValue]:
        return {
            "accepted": accepted,
            "dispatch_attempted": self._dispatch_attempted,
            "record_types": list(self._record_types),
        }

    def _lifecycle_attempt(self, accepted: bool, phase: str) -> dict[str, JsonValue]:
        return {
            "accepted": accepted,
            "phase": phase,
            "record_types": list(self._record_types),
        }

    def _clear_transaction(self) -> None:
        self._record_types.clear()
        self._dispatch_attempted = False
        self._cancellation_attempted = False


@dataclass
class JoinedGeneration:
    engine: Engine
    connection: JoinedFaultConnection
    worker: AbsurdWorkerDispatch | None = None
    attempt: ActivityAttempt | None = None
    poisoned: bool = False


class JoinedBeginProfile:
    """Public Absurd-Engine profile around one exact joined begin transaction."""

    identity = PROFILE_IDENTITY
    fault_name = "history.commit-refuse"
    fault_target = "activity_requested"
    fault_disposition = FaultDisposition.REFUSE
    refused_observation = "joined-begin-refused"
    recovered_observation = "joined-begin-recovered"
    refusal_field = "commit_refusals"

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self.transaction_attempts: list[dict[str, JsonValue]] = []
        self.lifecycle_attempts: list[dict[str, JsonValue]] = []
        self.prepare_calls = 0
        self.commit_refusals = 0
        self.dispatch_refusals = 0
        self.terminal_refusals = 0
        self.projection_refusals = 0
        self.projection_ack_losses = 0
        self.reset_refusals = 0
        self.reset_ack_losses = 0
        self.cancellation_refusals = 0
        self.cancellation_ack_losses = 0
        self.commit_ack_losses = 0
        self.terminal_ack_losses = 0
        self.worker_completions = 0
        self.worker_failures = 0
        self.drive_calls = 0
        self.drops = 0
        self.closes = 0

    def validate(self, command: Command) -> Command:
        if command.name != "engine.drive" or command.payload != {}:
            raise ValueError("joined-begin profile accepts only engine.drive with an empty payload")
        return command

    def validate_fault(self, fault: Fault) -> Fault:
        if (
            fault.name != self.fault_name
            or fault.target != self.fault_target
            or fault.disposition != self.fault_disposition.value
            or type(fault.payload) is not dict
            or set(fault.payload) != {"message"}
            or not isinstance(fault.payload["message"], str)
        ):
            raise ValueError(f"unsupported joined-begin fault for {self.identity.name}")
        return fault

    def create(self, context: ScenarioContext) -> GenerationStart[JoinedGeneration]:
        del context
        return GenerationStart(self._open(create=True), ())

    def load(self, context: ScenarioContext) -> GenerationStart[JoinedGeneration]:
        generation = self._open(create=False)
        return GenerationStart(generation, (self._scheduled(context),))

    def apply(
        self,
        generation: JoinedGeneration,
        command: Command,
        context: ScenarioContext,
    ) -> ApplyResult:
        self.drive_calls += 1
        expected = self._configure_faults(generation, context)
        try:
            outcome = generation.engine.advance()
        except OSError as error:
            if str(error) not in expected:
                raise
            generation.poisoned = True
            return ApplyResult(
                disposition=ActionDisposition.REFUSED_EXPECTED.value,
                value={"error": str(error), "frontier": self._frontier()},
                scheduled=[],
            )
        current = generation.engine.snapshot()["current"]
        assert isinstance(current, dict)
        return ApplyResult(
            disposition=ActionDisposition.APPLIED.value,
            value={
                "firings": [str(firing.transition) for firing in outcome.firings],
                "frontier": self._frontier(),
                "ready": outcome.ready,
                "status": current["status"],
                "waiting": outcome.waiting,
            },
            scheduled=[],
        )

    def observe(
        self,
        generation: JoinedGeneration,
        request: ObservationRequest,
        context: ScenarioContext,
    ) -> JsonValue:
        del context
        if request.name not in {
            "engine.joined-commit-authority",
            self.refused_observation,
            self.recovered_observation,
        }:
            raise ValueError(f"unknown joined-begin observation {request.name!r}")
        if request.payload not in (None, {}):
            raise ValueError("joined-begin observations do not accept parameters")
        state = self._observation_state(generation)
        if request.name == "engine.joined-commit-authority":
            fields = (
                "durable_tasks",
                "prepare_calls",
                "record_types",
                "transaction_attempts",
            )
        else:
            fields = (
                self.refusal_field,
                "drops",
                "durable_tasks",
                "frontier",
                "prepare_calls",
                "record_types",
                "status",
                "transaction_attempts",
            )
        return {field: state[field] for field in fields}

    def drop(self, generation: JoinedGeneration) -> None:
        self.drops += 1
        self._dispose(generation)

    def close(self, generation: JoinedGeneration) -> None:
        self.closes += 1
        self._dispose(generation)

    def _open(self, *, create: bool) -> JoinedGeneration:
        authority = psycopg.connect(self.dsn, autocommit=False)
        connection = JoinedFaultConnection(
            authority,
            self.transaction_attempts,
            self._commit_refused,
            self._dispatch_refused,
            self._terminal_refused,
            self._projection_refused,
            self._projection_ack_lost,
            self._commit_ack_lost,
            self._terminal_ack_lost,
            self.lifecycle_attempts,
            self._reset_refused,
            self._reset_ack_lost,
            self._cancellation_refused,
            self._cancellation_ack_lost,
        )
        listener = psycopg.connect(self.dsn, autocommit=True)
        bridge = JoinedBridge(self._prepared)
        opener = create_engine if create else load_engine
        engine = opener(
            connection,
            self._net(),
            INSTANCE_ID,
            listen=listener,
            default_queue=QUEUE,
            marking=self._marking(create=create),
            handlers={"bridge": bridge},
        )
        return JoinedGeneration(engine, connection)

    def _net(self) -> Net:
        return application_net()

    def _marking(self, *, create: bool) -> Marking | None:
        return Marking({INPUT: (Token("Input", 3),)}) if create else None

    def _observation_state(self, generation: JoinedGeneration) -> dict[str, JsonValue]:
        with psycopg.connect(self.dsn, autocommit=True) as probe:
            records = PostgresHistoryStore(probe, INSTANCE_ID).records
            queue_exists = probe.execute(
                "SELECT 1 FROM absurd.list_queues() WHERE queue_name = %s", (QUEUE,)
            ).fetchone()
            if queue_exists is None:
                tasks = []
            else:
                tasks = [
                    {"idempotency": key, "state": state}
                    for key, state in probe.execute(
                        sql.SQL("SELECT idempotency_key, state FROM absurd.{} ORDER BY idempotency_key").format(
                            sql.Identifier(f"t_{QUEUE}")
                        )
                    ).fetchall()
                ]
        if generation.poisoned:
            status = "poisoned"
        else:
            current = generation.engine.snapshot()["current"]
            assert isinstance(current, dict)
            status = current["status"]
        return cast(
            dict[str, JsonValue],
            {
                "commit_refusals": self.commit_refusals,
                "commit_ack_losses": self.commit_ack_losses,
                "dispatch_refusals": self.dispatch_refusals,
                "drops": self.drops,
                "drive_calls": self.drive_calls,
                "durable_tasks": tasks,
                "frontier": len(records),
                "prepare_calls": self.prepare_calls,
                "projection_refusals": self.projection_refusals,
                "projection_ack_losses": self.projection_ack_losses,
                "record_types": [type(record).__name__ for record in records],
                "reset_refusals": self.reset_refusals,
                "reset_ack_losses": self.reset_ack_losses,
                "status": status,
                "terminal_refusals": self.terminal_refusals,
                "terminal_ack_losses": self.terminal_ack_losses,
                "transaction_attempts": self.transaction_attempts,
                "worker_completions": self.worker_completions,
                "worker_failures": self.worker_failures,
            },
        )

    def _configure_faults(self, generation: JoinedGeneration, context: ScenarioContext) -> tuple[str, ...]:
        expected = []
        for fault in context.faults(self.fault_target):
            if fault.name != self.fault_name or fault.disposition != self.fault_disposition.value:
                raise ValueError(f"unsupported joined-begin fault {fault.name!r}")
            if type(fault.payload) is not dict or set(fault.payload) != {"message"}:
                raise ValueError(f"{self.fault_name} requires an exact message payload")
            message = fault.payload["message"]
            if not isinstance(message, str):
                raise ValueError(f"{self.fault_name} message must be a string")
            self._arm_refusal(generation, message)
            expected.append(message)
        return tuple(expected)

    def _arm_refusal(self, generation: JoinedGeneration, message: str) -> None:
        generation.connection.refuse_activity_request_commit(message)

    def _dispose(self, generation: JoinedGeneration) -> None:
        try:
            if generation.worker is not None:
                generation.worker.close()
        finally:
            generation.engine.close()

    def _frontier(self) -> int:
        with psycopg.connect(self.dsn, autocommit=True) as probe:
            return len(PostgresHistoryStore(probe, INSTANCE_ID))

    def _scheduled(self, context: ScenarioContext) -> ScheduledCommand:
        return ScheduledCommand(
            instant=context.now(),
            command=Command(profile=self.identity, name="engine.drive", payload={}),
        )

    def _prepared(self) -> None:
        self.prepare_calls += 1

    def _commit_refused(self) -> None:
        self.commit_refusals += 1

    def _dispatch_refused(self) -> None:
        self.dispatch_refusals += 1

    def _projection_refused(self) -> None:
        self.projection_refusals += 1

    def _terminal_refused(self) -> None:
        self.terminal_refusals += 1

    def _projection_ack_lost(self) -> None:
        self.projection_ack_losses += 1

    def _reset_refused(self) -> None:
        self.reset_refusals += 1

    def _reset_ack_lost(self) -> None:
        self.reset_ack_losses += 1

    def _cancellation_refused(self) -> None:
        self.cancellation_refusals += 1

    def _cancellation_ack_lost(self) -> None:
        self.cancellation_ack_losses += 1

    def _commit_ack_lost(self) -> None:
        self.commit_ack_losses += 1

    def _terminal_ack_lost(self) -> None:
        self.terminal_ack_losses += 1


class JoinedDispatchProfile(JoinedBeginProfile):
    """Public Absurd-Engine profile refusing task spawn inside a joined begin."""

    identity = DISPATCH_PROFILE_IDENTITY
    fault_name = "dispatch.refuse"
    refused_observation = "joined-dispatch-refused"
    recovered_observation = "joined-dispatch-recovered"
    refusal_field = "dispatch_refusals"

    def _arm_refusal(self, generation: JoinedGeneration, message: str) -> None:
        generation.connection.refuse_activity_request_dispatch(message)


class JoinedBeginAckLossProfile(JoinedBeginProfile):
    """Public Absurd-Engine profile losing acknowledgement after joined begin acceptance."""

    identity = ACK_LOSS_PROFILE_IDENTITY
    fault_name = "history.lose-ack"
    fault_target = "activity_requested_committed"
    fault_disposition = FaultDisposition.RAISE
    refused_observation = "joined-begin-ack-lost"
    recovered_observation = "joined-begin-ack-recovered"
    refusal_field = "commit_ack_losses"

    def observe(
        self,
        generation: JoinedGeneration,
        request: ObservationRequest,
        context: ScenarioContext,
    ) -> JsonValue:
        if request.name == "engine.joined-accepted-begin-authority":
            if request.payload not in (None, {}):
                raise ValueError("joined accepted-begin authority observation does not accept parameters")
            state = self._observation_state(generation)
            fields = (
                "commit_ack_losses",
                "durable_tasks",
                "prepare_calls",
                "record_types",
                "transaction_attempts",
            )
            return {field: state[field] for field in fields}
        value = cast(dict[str, JsonValue], super().observe(generation, request, context))
        return {**value, "drive_calls": self.drive_calls}

    def _arm_refusal(self, generation: JoinedGeneration, message: str) -> None:
        generation.connection.lose_activity_request_commit_ack(message)


class JoinedProjectionProfile(JoinedBeginProfile):
    """Public Absurd-Engine profile refusing the projection transaction."""

    identity = PROJECTION_PROFILE_IDENTITY
    fault_name = "history.commit-refuse"
    fault_target = "projection_committed"
    refused_observation = "joined-projection-refused"
    recovered_observation = "joined-projection-recovered"
    refusal_field = "projection_refusals"

    def validate(self, command: Command) -> Command:
        if command.name in {"engine.drive", "worker.claim"} and command.payload == {}:
            return command
        if command.name == "worker.complete" and type(command.payload) is dict and set(command.payload) == {"result"}:
            return command
        raise ValueError(f"unsupported joined-projection command {command.name!r}")

    def apply(
        self,
        generation: JoinedGeneration,
        command: Command,
        context: ScenarioContext,
    ) -> ApplyResult:
        if command.name == "engine.drive":
            return super().apply(generation, command, context)
        if command.name == "worker.claim":
            if generation.worker is not None:
                raise RuntimeError("joined-projection worker already exists")
            worker = AbsurdWorkerDispatch(self.dsn, queues=(QUEUE,), worker_id="dst-joined-projection")
            attempt = worker.claim()
            if attempt is None:
                worker.close()
                raise RuntimeError("joined-projection worker found no pending Activity")
            generation.worker = worker
            generation.attempt = attempt
            return ApplyResult(
                disposition=ActionDisposition.APPLIED.value,
                value={"activity": attempt.invocation.activity, "claimed": True},
                scheduled=[],
            )
        if generation.worker is None or generation.attempt is None:
            raise RuntimeError("worker.complete requires one claimed joined Activity")
        payload = cast(dict[str, JsonValue], command.payload)
        generation.worker.complete(generation.attempt, payload["result"])
        generation.attempt = None
        self.worker_completions += 1
        return ApplyResult(
            disposition=ActionDisposition.APPLIED.value,
            value={"completed": True},
            scheduled=[],
        )

    def observe(
        self,
        generation: JoinedGeneration,
        request: ObservationRequest,
        context: ScenarioContext,
    ) -> JsonValue:
        if request.name == "engine.joined-projection-authority":
            if request.payload not in (None, {}):
                raise ValueError("joined-projection authority observation does not accept parameters")
            state = self._observation_state(generation)
            fields = (
                "durable_tasks",
                "prepare_calls",
                "projection_refusals",
                "record_types",
                "transaction_attempts",
                "worker_completions",
            )
            return {field: state[field] for field in fields}
        value = cast(dict[str, JsonValue], super().observe(generation, request, context))
        return {**value, "worker_completions": self.worker_completions}

    def _arm_refusal(self, generation: JoinedGeneration, message: str) -> None:
        generation.connection.refuse_projection_commit(message)


class JoinedProjectionAckLossProfile(JoinedProjectionProfile):
    """Public Absurd-Engine profile losing acknowledgement after projection acceptance."""

    identity = PROJECTION_ACK_LOSS_PROFILE_IDENTITY
    fault_name = "history.lose-ack"
    fault_disposition = FaultDisposition.RAISE
    refused_observation = "joined-projection-ack-lost"
    recovered_observation = "joined-projection-ack-recovered"
    refusal_field = "projection_ack_losses"

    def observe(
        self,
        generation: JoinedGeneration,
        request: ObservationRequest,
        context: ScenarioContext,
    ) -> JsonValue:
        if request.name == "engine.joined-accepted-projection-authority":
            if request.payload not in (None, {}):
                raise ValueError("joined accepted-projection authority observation does not accept parameters")
            state = self._observation_state(generation)
            fields = (
                "durable_tasks",
                "prepare_calls",
                "projection_ack_losses",
                "record_types",
                "transaction_attempts",
                "worker_completions",
            )
            return {field: state[field] for field in fields}
        value = cast(dict[str, JsonValue], super().observe(generation, request, context))
        return {**value, "drive_calls": self.drive_calls, "projection_ack_losses": self.projection_ack_losses}

    def _arm_refusal(self, generation: JoinedGeneration, message: str) -> None:
        generation.connection.lose_projection_commit_ack(message)


class JoinedTerminalRefusalProfile(JoinedProjectionProfile):
    """Public Absurd-Engine profile refusing the semantic terminal commit."""

    identity = TERMINAL_REFUSAL_PROFILE_IDENTITY
    fault_target = "activity_completed"
    refused_observation = "joined-terminal-refused"
    recovered_observation = "joined-terminal-recovered"
    refusal_field = "terminal_refusals"

    def observe(
        self,
        generation: JoinedGeneration,
        request: ObservationRequest,
        context: ScenarioContext,
    ) -> JsonValue:
        if request.name == "engine.joined-terminal-authority":
            if request.payload not in (None, {}):
                raise ValueError("joined terminal authority observation does not accept parameters")
            state = self._observation_state(generation)
            fields = (
                "durable_tasks",
                "prepare_calls",
                "record_types",
                "terminal_refusals",
                "transaction_attempts",
                "worker_completions",
            )
            return {field: state[field] for field in fields}
        value = cast(dict[str, JsonValue], super().observe(generation, request, context))
        return {**value, "drive_calls": self.drive_calls, "terminal_refusals": self.terminal_refusals}

    def _arm_refusal(self, generation: JoinedGeneration, message: str) -> None:
        generation.connection.refuse_activity_terminal_commit(message)


class JoinedFailureRefusalProfile(JoinedProjectionProfile):
    """Public Absurd-Engine profile refusing the semantic Activity failure commit."""

    identity = FAILURE_REFUSAL_PROFILE_IDENTITY
    fault_target = "activity_failed"
    refused_observation = "joined-failure-refused"
    recovered_observation = "joined-failure-recovered"
    refusal_field = "terminal_refusals"

    def validate(self, command: Command) -> Command:
        if command.name in {"engine.drive", "worker.claim"} and command.payload == {}:
            return command
        if (
            command.name == "worker.fail"
            and type(command.payload) is dict
            and set(command.payload) == {"error"}
            and isinstance(command.payload["error"], str)
        ):
            return command
        raise ValueError(f"unsupported joined-failure command {command.name!r}")

    def apply(
        self,
        generation: JoinedGeneration,
        command: Command,
        context: ScenarioContext,
    ) -> ApplyResult:
        if command.name == "worker.fail":
            if generation.worker is None or generation.attempt is None:
                raise RuntimeError("worker.fail requires one claimed joined Activity")
            payload = cast(dict[str, JsonValue], command.payload)
            error = cast(str, payload["error"])
            generation.worker.fail(
                generation.attempt,
                ActivityFailure(
                    error,
                    kind="InvalidRequest",
                    details={"source": "dst"},
                    retryable=False,
                ),
            )
            generation.attempt = None
            self.worker_failures += 1
            return ApplyResult(
                disposition=ActionDisposition.APPLIED.value,
                value={"failed": True},
                scheduled=[],
            )
        if command.name != "engine.drive":
            return super().apply(generation, command, context)
        try:
            return super().apply(generation, command, context)
        except RuntimeError as error:
            with psycopg.connect(self.dsn, autocommit=True) as probe:
                records = PostgresHistoryStore(probe, INSTANCE_ID).records
            if (
                len(records) < 2
                or not isinstance(records[-2], ActivityFailed)
                or not isinstance(records[-1], FiringFailed)
            ):
                raise
            generation.poisoned = True
            return ApplyResult(
                disposition=ActionDisposition.QUARANTINED.value,
                value={"error": str(error), "frontier": len(records)},
                scheduled=[],
            )

    def observe(
        self,
        generation: JoinedGeneration,
        request: ObservationRequest,
        context: ScenarioContext,
    ) -> JsonValue:
        if request.name == "engine.joined-failure-authority":
            if request.payload not in (None, {}):
                raise ValueError("joined failure authority observation does not accept parameters")
            state = self._observation_state(generation)
            fields = (
                "durable_tasks",
                "prepare_calls",
                "record_types",
                "terminal_refusals",
                "transaction_attempts",
                "worker_failures",
            )
            return {field: state[field] for field in fields}
        value = cast(dict[str, JsonValue], super().observe(generation, request, context))
        return {
            **value,
            "drive_calls": self.drive_calls,
            "terminal_refusals": self.terminal_refusals,
            "worker_failures": self.worker_failures,
        }

    def _arm_refusal(self, generation: JoinedGeneration, message: str) -> None:
        generation.connection.refuse_activity_terminal_commit(message)


class JoinedFailureAckLossProfile(JoinedFailureRefusalProfile):
    """Public Absurd-Engine profile losing acknowledgement after ActivityFailed acceptance."""

    identity = FAILURE_ACK_LOSS_PROFILE_IDENTITY
    fault_name = "history.lose-ack"
    fault_target = "activity_failed_committed"
    fault_disposition = FaultDisposition.RAISE
    refused_observation = "joined-failure-ack-lost"
    recovered_observation = "joined-failure-ack-recovered"
    refusal_field = "terminal_ack_losses"

    def observe(
        self,
        generation: JoinedGeneration,
        request: ObservationRequest,
        context: ScenarioContext,
    ) -> JsonValue:
        if request.name == "engine.joined-accepted-failure-authority":
            if request.payload not in (None, {}):
                raise ValueError("joined accepted-failure authority observation does not accept parameters")
            state = self._observation_state(generation)
            fields = (
                "durable_tasks",
                "prepare_calls",
                "record_types",
                "terminal_ack_losses",
                "transaction_attempts",
                "worker_failures",
            )
            return {field: state[field] for field in fields}
        value = cast(dict[str, JsonValue], super().observe(generation, request, context))
        return {**value, "terminal_ack_losses": self.terminal_ack_losses}

    def _arm_refusal(self, generation: JoinedGeneration, message: str) -> None:
        generation.connection.lose_activity_terminal_commit_ack(message)


class JoinedTerminalAckLossProfile(JoinedProjectionProfile):
    """Public Absurd-Engine profile losing acknowledgement after terminal acceptance."""

    identity = TERMINAL_ACK_LOSS_PROFILE_IDENTITY
    fault_name = "history.lose-ack"
    fault_target = "activity_completed_committed"
    fault_disposition = FaultDisposition.RAISE
    refused_observation = "joined-terminal-ack-lost"
    recovered_observation = "joined-terminal-ack-recovered"
    refusal_field = "terminal_ack_losses"

    def observe(
        self,
        generation: JoinedGeneration,
        request: ObservationRequest,
        context: ScenarioContext,
    ) -> JsonValue:
        if request.name == "engine.joined-accepted-terminal-authority":
            if request.payload not in (None, {}):
                raise ValueError("joined accepted-terminal authority observation does not accept parameters")
            state = self._observation_state(generation)
            fields = (
                "durable_tasks",
                "prepare_calls",
                "record_types",
                "terminal_ack_losses",
                "transaction_attempts",
                "worker_completions",
            )
            return {field: state[field] for field in fields}
        value = cast(dict[str, JsonValue], super().observe(generation, request, context))
        return {**value, "drive_calls": self.drive_calls, "terminal_ack_losses": self.terminal_ack_losses}

    def _arm_refusal(self, generation: JoinedGeneration, message: str) -> None:
        generation.connection.lose_activity_terminal_commit_ack(message)


class JoinedCancellationProfile(JoinedBeginProfile):
    """Public Absurd profile refusing the post-reset cancellation commit."""

    identity = CANCELLATION_PROFILE_IDENTITY
    fault_name = "history.commit-refuse"
    fault_target = "cancellation_committed"
    refused_observation = "joined-cancellation-refused"
    recovered_observation = "joined-cancellation-recovered"
    refusal_field = "cancellation_refusals"
    _observations = {
        "engine.joined-cancellation-authority",
        "joined-cancellation-ready",
        "joined-cancellation-refused",
        "joined-cancellation-recovered",
        "joined-late-worker-fenced",
    }
    _observation_fields = (
        "cancellation_refusals",
        "drops",
        "drive_calls",
        "durable_tasks",
        "frontier",
        "lifecycle_attempts",
        "prepare_calls",
        "record_types",
        "scope_opens",
        "scope_resets",
        "source_deliveries",
        "stale_worker_refusals",
        "status",
        "transaction_attempts",
        "worker_claims",
    )

    def __init__(self, dsn: str) -> None:
        super().__init__(dsn)
        self.scope_opens = 0
        self.scope_resets = 0
        self.source_deliveries = 0
        self.worker_claims = 0
        self.stale_worker_refusals = 0
        self._external_worker: AbsurdWorkerDispatch | None = None
        self._external_attempt: ActivityAttempt | None = None

    def validate(self, command: Command) -> Command:
        payload = command.payload
        if command.name in {"engine.drive", "worker.claim", "worker.complete-stale"} and payload == {}:
            return command
        if command.name in {"scope.open", "scope.reset"} and payload == {"name": "draft"}:
            return command
        if (
            command.name == "source.deliver"
            and type(payload) is dict
            and payload == {"identity": "draft-input-3", "scope": "draft", "value": 3}
        ):
            return command
        raise ValueError(f"unsupported joined-cancellation command {command.name!r}")

    def apply(
        self,
        generation: JoinedGeneration,
        command: Command,
        context: ScenarioContext,
    ) -> ApplyResult:
        if command.name == "engine.drive":
            return super().apply(generation, command, context)
        if command.name == "scope.open":
            scope = generation.engine.open_scope("draft")
            self.scope_opens += 1
            return self._applied({"frontier": self._frontier(), "generation": scope.generation})
        if command.name == "source.deliver":
            generation.engine.deliver(
                SOURCE,
                Token("Input", 3),
                identity="draft-input-3",
                scope=generation.engine.active_scopes["draft"],
            )
            self.source_deliveries += 1
            return self._applied(
                {"frontier": self._frontier()},
                scheduled=[self._scheduled(context)],
            )
        if command.name == "worker.claim":
            if self._external_worker is not None:
                raise RuntimeError("joined-cancellation Worker already exists")
            worker = AbsurdWorkerDispatch(self.dsn, queues=(QUEUE,), worker_id="dst-joined-cancellation")
            attempt = worker.claim()
            if attempt is None:
                worker.close()
                raise RuntimeError("joined-cancellation Worker found no pending Activity")
            self._external_worker = worker
            self._external_attempt = attempt
            self.worker_claims += 1
            return self._applied({"activity": attempt.invocation.activity, "claimed": True})
        if command.name == "worker.complete-stale":
            if self._external_worker is None or self._external_attempt is None:
                raise RuntimeError("worker.complete-stale requires one claimed joined Activity")
            try:
                self._external_worker.complete(self._external_attempt, {"value": 3})
            except RuntimeError as error:
                if "stale Activity Attempt" not in str(error):
                    raise
                self.stale_worker_refusals += 1
                self._external_attempt = None
                return ApplyResult(
                    disposition=ActionDisposition.REFUSED_EXPECTED.value,
                    value={"reason": "stale Activity Attempt"},
                    scheduled=[],
                )
            raise AssertionError("cancelled Absurd custody accepted a stale Worker completion")

        expected = self._configure_faults(generation, context)
        try:
            opened = generation.engine.reset_scope(generation.engine.active_scopes["draft"])
        except OSError as error:
            if str(error) not in expected:
                raise
            generation.poisoned = True
            self.scope_resets += 1
            return ApplyResult(
                disposition=ActionDisposition.REFUSED_EXPECTED.value,
                value={"error": str(error), "frontier": self._frontier()},
                scheduled=[],
            )
        self.scope_resets += 1
        return self._applied({"frontier": self._frontier(), "generation": opened.generation})

    def observe(
        self,
        generation: JoinedGeneration,
        request: ObservationRequest,
        context: ScenarioContext,
    ) -> JsonValue:
        del context
        if request.name not in self._observations:
            raise ValueError(f"unknown joined-cancellation observation {request.name!r}")
        if request.payload not in (None, {}):
            raise ValueError("joined-cancellation observations do not accept parameters")
        state = self._observation_state(generation)
        return {field: state[field] for field in self._observation_fields}

    def close(self, generation: JoinedGeneration) -> None:
        self.closes += 1
        try:
            if self._external_worker is not None:
                self._external_worker.close()
                self._external_worker = None
                self._external_attempt = None
        finally:
            self._dispose(generation)

    def _net(self) -> Net:
        return lifecycle_application_net()

    def _marking(self, *, create: bool) -> Marking | None:
        del create
        return None

    def _arm_refusal(self, generation: JoinedGeneration, message: str) -> None:
        generation.connection.refuse_cancellation_commit(message)

    def _observation_state(self, generation: JoinedGeneration) -> dict[str, JsonValue]:
        state = super()._observation_state(generation)
        state.update(
            {
                "cancellation_refusals": self.cancellation_refusals,
                "lifecycle_attempts": self.lifecycle_attempts,
                "scope_opens": self.scope_opens,
                "scope_resets": self.scope_resets,
                "source_deliveries": self.source_deliveries,
                "stale_worker_refusals": self.stale_worker_refusals,
                "worker_claims": self.worker_claims,
            }
        )
        return state

    @staticmethod
    def _applied(
        value: dict[str, JsonValue],
        *,
        scheduled: list[ScheduledCommand] | None = None,
    ) -> ApplyResult:
        return ApplyResult(
            disposition=ActionDisposition.APPLIED.value,
            value=value,
            scheduled=[] if scheduled is None else scheduled,
        )


class JoinedResetRefusalProfile(JoinedCancellationProfile):
    """Public Absurd profile refusing the canonical ScopeReset transaction."""

    identity = RESET_REFUSAL_PROFILE_IDENTITY
    fault_name = "history.commit-refuse"
    fault_target = "scope_reset"
    refused_observation = "joined-reset-refused"
    recovered_observation = "joined-reset-recovered"
    refusal_field = "reset_refusals"
    _observations = {
        "engine.joined-reset-refusal-authority",
        "joined-reset-ready",
        "joined-reset-refused",
        "joined-reset-recovered",
        "joined-reset-terminal-recovered",
    }
    _observation_fields = (
        *JoinedCancellationProfile._observation_fields,
        "reset_refusals",
        "worker_completions",
    )

    def validate(self, command: Command) -> Command:
        if command.name == "worker.complete" and command.payload == {}:
            return command
        return super().validate(command)

    def apply(
        self,
        generation: JoinedGeneration,
        command: Command,
        context: ScenarioContext,
    ) -> ApplyResult:
        if command.name != "worker.complete":
            return super().apply(generation, command, context)
        if self._external_worker is None or self._external_attempt is None:
            raise RuntimeError("worker.complete requires one claimed joined Activity")
        self._external_worker.complete(self._external_attempt, {"value": 3})
        self._external_attempt = None
        self.worker_completions += 1
        return self._applied(
            {"completed": True},
            scheduled=[self._scheduled(context)],
        )

    def _arm_refusal(self, generation: JoinedGeneration, message: str) -> None:
        generation.connection.refuse_scope_reset_commit(message)


class JoinedResetAckLossProfile(JoinedCancellationProfile):
    """Public Absurd profile losing acknowledgement after ScopeReset acceptance."""

    identity = RESET_ACK_LOSS_PROFILE_IDENTITY
    fault_name = "history.lose-ack"
    fault_target = "scope_reset_committed"
    fault_disposition = FaultDisposition.RAISE
    refused_observation = "joined-reset-ack-lost"
    recovered_observation = "joined-reset-ack-recovered"
    refusal_field = "reset_ack_losses"
    _observations = {
        "engine.joined-accepted-reset-authority",
        "joined-reset-ack-ready",
        "joined-reset-ack-lost",
        "joined-reset-ack-recovered",
        "joined-reset-ack-worker-fenced",
    }
    _observation_fields = (
        *JoinedCancellationProfile._observation_fields,
        "reset_ack_losses",
        "reset_refusals",
    )

    def _arm_refusal(self, generation: JoinedGeneration, message: str) -> None:
        generation.connection.lose_scope_reset_commit_ack(message)


class JoinedCancellationAckLossProfile(JoinedCancellationProfile):
    """Public Absurd profile losing acknowledgement after tombstone acceptance."""

    identity = CANCELLATION_ACK_LOSS_PROFILE_IDENTITY
    fault_name = "history.lose-ack"
    fault_disposition = FaultDisposition.RAISE
    refused_observation = "joined-cancellation-ack-lost"
    recovered_observation = "joined-cancellation-ack-recovered"
    refusal_field = "cancellation_ack_losses"
    _observations = {
        "engine.joined-accepted-cancellation-authority",
        "joined-cancellation-ack-ready",
        "joined-cancellation-ack-lost",
        "joined-cancellation-ack-recovered",
        "joined-cancellation-ack-worker-fenced",
    }
    _observation_fields = (
        *JoinedCancellationProfile._observation_fields,
        "cancellation_ack_losses",
    )

    def _arm_refusal(self, generation: JoinedGeneration, message: str) -> None:
        generation.connection.lose_cancellation_commit_ack(message)

    def _observation_state(self, generation: JoinedGeneration) -> dict[str, JsonValue]:
        state = super()._observation_state(generation)
        state["cancellation_ack_losses"] = self.cancellation_ack_losses
        return state


class JoinedCommitAuthorityChecker:
    """Independent durable-authority check over provider transaction outcomes."""

    identity = CHECKER_IDENTITY
    request = ObservationRequest(name="engine.joined-commit-authority", payload={})

    def check(self, observation: Observation) -> CheckResult:
        value = cast(dict[str, JsonValue], observation.value)
        records = cast(list[JsonValue], value["record_types"])
        attempts = cast(list[dict[str, JsonValue]], value["transaction_attempts"])
        tasks = cast(list[dict[str, JsonValue]], value["durable_tasks"])
        accepted = sum(attempt["accepted"] is True for attempt in attempts)
        refused = sum(attempt["accepted"] is False for attempt in attempts)
        selected = records.count(CandidateSelected.__name__)
        begun = records.count(FiringBegun.__name__)
        requested = records.count(ActivityRequested.__name__)
        expected_key = f"{INSTANCE_ID}:occurrence-1"
        expected_batch = ["CandidateSelected", "FiringBegun", "TokensConsumed", "ActivityRequested"]
        attempts_whole = all(
            attempt["dispatch_attempted"] is True and cast(list[JsonValue], attempt["record_types"]) == expected_batch
            for attempt in attempts
        )
        tasks_exact = tasks in ([], [{"idempotency": expected_key, "state": "pending"}])
        passed = (
            0 <= refused <= 1
            and 0 <= accepted <= 1
            and len(attempts) <= 2
            and attempts_whole
            and cast(int, value["prepare_calls"]) == len(attempts)
            and selected == begun == requested == len(tasks) == accepted
            and tasks_exact
        )
        return CheckResult(
            passed=passed,
            detail={
                "accepted_joined_begins": accepted,
                "activity_requested": requested,
                "candidate_selected": selected,
                "durable_tasks": len(tasks),
                "firing_begun": begun,
                "joined_attempts_whole": attempts_whole,
                "prepare_calls": value["prepare_calls"],
                "refused_joined_begins": refused,
                "tasks_exact": tasks_exact,
            },
        )


class JoinedProjectionAuthorityChecker:
    """Independent terminal/projection authority from provider and transaction facts."""

    identity = PROJECTION_CHECKER_IDENTITY
    request = ObservationRequest(name="engine.joined-projection-authority", payload={})

    def check(self, observation: Observation) -> CheckResult:
        value = cast(dict[str, JsonValue], observation.value)
        records = cast(list[JsonValue], value["record_types"])
        attempts = cast(list[dict[str, JsonValue]], value["transaction_attempts"])
        tasks = cast(list[dict[str, JsonValue]], value["durable_tasks"])
        begin = {
            "accepted": True,
            "dispatch_attempted": True,
            "record_types": ["CandidateSelected", "FiringBegun", "TokensConsumed", "ActivityRequested"],
        }
        terminal = {
            "accepted": True,
            "dispatch_attempted": False,
            "record_types": ["ActivityCompleted"],
        }
        projection_refused = {
            "accepted": False,
            "dispatch_attempted": False,
            "record_types": ["TokensProduced", "FiringCompleted"],
        }
        projection_accepted = {**projection_refused, "accepted": True}
        attempts_exact = attempts in (
            [],
            [begin],
            [begin, terminal, projection_refused],
            [begin, terminal, projection_refused, projection_accepted],
        )
        accepted_begin = sum(attempt == begin for attempt in attempts)
        accepted_terminal = sum(attempt == terminal for attempt in attempts)
        accepted_projection = sum(attempt == projection_accepted for attempt in attempts)
        refused_projection = sum(attempt == projection_refused for attempt in attempts)
        selected = records.count(CandidateSelected.__name__)
        begun = records.count(FiringBegun.__name__)
        requested = records.count(ActivityRequested.__name__)
        completed = records.count(ActivityCompleted.__name__)
        produced = records.count("TokensProduced")
        projected = records.count(FiringCompleted.__name__)
        worker_completions = cast(int, value["worker_completions"])
        expected_key = f"{INSTANCE_ID}:occurrence-1"
        tasks_exact = tasks == [] or tasks in (
            [{"idempotency": expected_key, "state": "pending"}],
            [{"idempotency": expected_key, "state": "running"}],
            [{"idempotency": expected_key, "state": "completed"}],
        )
        completed_custody = tasks == [{"idempotency": expected_key, "state": "completed"}]
        passed = (
            attempts_exact
            and cast(int, value["prepare_calls"]) == accepted_begin
            and selected == begun == requested == accepted_begin == len(tasks)
            and completed == accepted_terminal <= worker_completions <= 1
            and produced == projected == accepted_projection <= completed
            and refused_projection == cast(int, value["projection_refusals"])
            and refused_projection <= 1
            and completed_custody == (worker_completions == 1)
            and tasks_exact
        )
        return CheckResult(
            passed=passed,
            detail={
                "accepted_begins": accepted_begin,
                "accepted_projections": accepted_projection,
                "accepted_terminals": accepted_terminal,
                "attempts_exact": attempts_exact,
                "canonical_projections": projected,
                "canonical_terminals": completed,
                "completed_custody": completed_custody,
                "refused_projections": refused_projection,
                "tasks_exact": tasks_exact,
                "worker_completions": worker_completions,
            },
        )


class JoinedAcceptedProjectionAuthorityChecker:
    """Independent accepted-projection authority from PostgreSQL and Worker facts."""

    identity = PROJECTION_ACK_LOSS_CHECKER_IDENTITY
    request = ObservationRequest(name="engine.joined-accepted-projection-authority", payload={})

    def check(self, observation: Observation) -> CheckResult:
        value = cast(dict[str, JsonValue], observation.value)
        records = cast(list[JsonValue], value["record_types"])
        attempts = cast(list[dict[str, JsonValue]], value["transaction_attempts"])
        tasks = cast(list[dict[str, JsonValue]], value["durable_tasks"])
        begin = {
            "accepted": True,
            "dispatch_attempted": True,
            "record_types": ["CandidateSelected", "FiringBegun", "TokensConsumed", "ActivityRequested"],
        }
        terminal = {
            "accepted": True,
            "dispatch_attempted": False,
            "record_types": ["ActivityCompleted"],
        }
        projection = {
            "accepted": True,
            "dispatch_attempted": False,
            "record_types": ["TokensProduced", "FiringCompleted"],
        }
        attempts_exact = attempts in ([], [begin], [begin, terminal, projection])
        accepted_begins = sum(attempt == begin for attempt in attempts)
        accepted_terminals = sum(attempt == terminal for attempt in attempts)
        accepted_projections = sum(attempt == projection for attempt in attempts)
        selected = records.count(CandidateSelected.__name__)
        begun = records.count(FiringBegun.__name__)
        requested = records.count(ActivityRequested.__name__)
        completed = records.count(ActivityCompleted.__name__)
        produced = records.count("TokensProduced")
        projected = records.count(FiringCompleted.__name__)
        worker_completions = cast(int, value["worker_completions"])
        ack_losses = cast(int, value["projection_ack_losses"])
        expected_key = f"{INSTANCE_ID}:occurrence-1"
        tasks_exact = tasks == [] or tasks in (
            [{"idempotency": expected_key, "state": "pending"}],
            [{"idempotency": expected_key, "state": "running"}],
            [{"idempotency": expected_key, "state": "completed"}],
        )
        completed_custody = tasks == [{"idempotency": expected_key, "state": "completed"}]
        passed = (
            attempts_exact
            and cast(int, value["prepare_calls"]) == accepted_begins
            and selected == begun == requested == accepted_begins == len(tasks)
            and completed == accepted_terminals <= worker_completions <= 1
            and produced == projected == accepted_projections <= completed
            and 0 <= ack_losses <= accepted_projections <= 1
            and completed_custody == (worker_completions == 1)
            and tasks_exact
        )
        return CheckResult(
            passed=passed,
            detail={
                "accepted_begins": accepted_begins,
                "accepted_projections": accepted_projections,
                "accepted_terminals": accepted_terminals,
                "ack_losses": ack_losses,
                "attempts_exact": attempts_exact,
                "canonical_projections": projected,
                "canonical_terminals": completed,
                "completed_custody": completed_custody,
                "tasks_exact": tasks_exact,
                "worker_completions": worker_completions,
            },
        )


class JoinedTerminalAuthorityChecker:
    """Independent terminal authority from completed custody and transaction fate."""

    identity = TERMINAL_REFUSAL_CHECKER_IDENTITY
    request = ObservationRequest(name="engine.joined-terminal-authority", payload={})

    def check(self, observation: Observation) -> CheckResult:
        value = cast(dict[str, JsonValue], observation.value)
        records = cast(list[JsonValue], value["record_types"])
        attempts = cast(list[dict[str, JsonValue]], value["transaction_attempts"])
        tasks = cast(list[dict[str, JsonValue]], value["durable_tasks"])
        begin = {
            "accepted": True,
            "dispatch_attempted": True,
            "record_types": ["CandidateSelected", "FiringBegun", "TokensConsumed", "ActivityRequested"],
        }
        terminal_refused = {
            "accepted": False,
            "dispatch_attempted": False,
            "record_types": ["ActivityCompleted"],
        }
        terminal_accepted = {**terminal_refused, "accepted": True}
        projection = {
            "accepted": True,
            "dispatch_attempted": False,
            "record_types": ["TokensProduced", "FiringCompleted"],
        }
        attempts_exact = attempts in (
            [],
            [begin],
            [begin, terminal_refused],
            [begin, terminal_refused, terminal_accepted],
            [begin, terminal_refused, terminal_accepted, projection],
        )
        accepted_begins = sum(attempt == begin for attempt in attempts)
        refused_terminals = sum(attempt == terminal_refused for attempt in attempts)
        accepted_terminals = sum(attempt == terminal_accepted for attempt in attempts)
        accepted_projections = sum(attempt == projection for attempt in attempts)
        selected = records.count(CandidateSelected.__name__)
        begun = records.count(FiringBegun.__name__)
        requested = records.count(ActivityRequested.__name__)
        completed = records.count(ActivityCompleted.__name__)
        produced = records.count("TokensProduced")
        projected = records.count(FiringCompleted.__name__)
        worker_completions = cast(int, value["worker_completions"])
        expected_key = f"{INSTANCE_ID}:occurrence-1"
        tasks_exact = tasks == [] or tasks in (
            [{"idempotency": expected_key, "state": "pending"}],
            [{"idempotency": expected_key, "state": "running"}],
            [{"idempotency": expected_key, "state": "completed"}],
        )
        completed_custody = tasks == [{"idempotency": expected_key, "state": "completed"}]
        passed = (
            attempts_exact
            and cast(int, value["prepare_calls"]) == accepted_begins
            and selected == begun == requested == accepted_begins == len(tasks)
            and completed == accepted_terminals <= worker_completions <= 1
            and produced == projected == accepted_projections <= completed
            and refused_terminals == cast(int, value["terminal_refusals"]) <= 1
            and completed_custody == (worker_completions == 1)
            and tasks_exact
        )
        return CheckResult(
            passed=passed,
            detail={
                "accepted_begins": accepted_begins,
                "accepted_projections": accepted_projections,
                "accepted_terminals": accepted_terminals,
                "attempts_exact": attempts_exact,
                "canonical_projections": projected,
                "canonical_terminals": completed,
                "completed_custody": completed_custody,
                "refused_terminals": refused_terminals,
                "tasks_exact": tasks_exact,
                "worker_completions": worker_completions,
            },
        )


class JoinedFailureAuthorityChecker:
    """Independent failure authority from failed provider custody and transaction fate."""

    identity = FAILURE_REFUSAL_CHECKER_IDENTITY
    request = ObservationRequest(name="engine.joined-failure-authority", payload={})

    def check(self, observation: Observation) -> CheckResult:
        value = cast(dict[str, JsonValue], observation.value)
        records = cast(list[JsonValue], value["record_types"])
        attempts = cast(list[dict[str, JsonValue]], value["transaction_attempts"])
        tasks = cast(list[dict[str, JsonValue]], value["durable_tasks"])
        begin = {
            "accepted": True,
            "dispatch_attempted": True,
            "record_types": ["CandidateSelected", "FiringBegun", "TokensConsumed", "ActivityRequested"],
        }
        failure_refused = {
            "accepted": False,
            "dispatch_attempted": False,
            "record_types": ["ActivityFailed"],
        }
        failure_accepted = {**failure_refused, "accepted": True}
        firing_failed = {
            "accepted": True,
            "dispatch_attempted": False,
            "record_types": ["FiringFailed"],
        }
        attempts_exact = attempts in (
            [],
            [begin],
            [begin, failure_refused],
            [begin, failure_refused, failure_accepted],
            [begin, failure_refused, failure_accepted, firing_failed],
        )
        accepted_begins = attempts.count(begin)
        refused_failures = attempts.count(failure_refused)
        accepted_failures = attempts.count(failure_accepted)
        accepted_firings_failed = attempts.count(firing_failed)
        selected = records.count(CandidateSelected.__name__)
        begun = records.count(FiringBegun.__name__)
        requested = records.count(ActivityRequested.__name__)
        failed = records.count(ActivityFailed.__name__)
        firings_failed = records.count(FiringFailed.__name__)
        worker_failures = cast(int, value["worker_failures"])
        expected_key = f"{INSTANCE_ID}:occurrence-1"
        tasks_exact = tasks == [] or tasks in (
            [{"idempotency": expected_key, "state": "pending"}],
            [{"idempotency": expected_key, "state": "running"}],
            [{"idempotency": expected_key, "state": "failed"}],
        )
        failed_custody = tasks == [{"idempotency": expected_key, "state": "failed"}]
        passed = (
            attempts_exact
            and cast(int, value["prepare_calls"]) == accepted_begins
            and selected == begun == requested == accepted_begins == len(tasks)
            and failed == accepted_failures <= worker_failures <= 1
            and firings_failed == accepted_firings_failed <= failed
            and refused_failures == cast(int, value["terminal_refusals"]) <= 1
            and records.count(FiringCompleted.__name__) == records.count("TokensProduced") == 0
            and failed_custody == (worker_failures == 1)
            and tasks_exact
        )
        return CheckResult(
            passed=passed,
            detail={
                "accepted_begins": accepted_begins,
                "accepted_failures": accepted_failures,
                "accepted_firings_failed": accepted_firings_failed,
                "attempts_exact": attempts_exact,
                "canonical_failures": failed,
                "canonical_firings_failed": firings_failed,
                "failed_custody": failed_custody,
                "refused_failures": refused_failures,
                "tasks_exact": tasks_exact,
                "worker_failures": worker_failures,
            },
        )


class JoinedAcceptedFailureAuthorityChecker:
    """Independent accepted-failure authority from PostgreSQL and Worker facts."""

    identity = FAILURE_ACK_LOSS_CHECKER_IDENTITY
    request = ObservationRequest(name="engine.joined-accepted-failure-authority", payload={})

    def check(self, observation: Observation) -> CheckResult:
        value = cast(dict[str, JsonValue], observation.value)
        records = cast(list[JsonValue], value["record_types"])
        attempts = cast(list[dict[str, JsonValue]], value["transaction_attempts"])
        tasks = cast(list[dict[str, JsonValue]], value["durable_tasks"])
        begin = {
            "accepted": True,
            "dispatch_attempted": True,
            "record_types": ["CandidateSelected", "FiringBegun", "TokensConsumed", "ActivityRequested"],
        }
        failure = {
            "accepted": True,
            "dispatch_attempted": False,
            "record_types": ["ActivityFailed"],
        }
        firing_failed = {
            "accepted": True,
            "dispatch_attempted": False,
            "record_types": ["FiringFailed"],
        }
        attempts_exact = attempts in ([], [begin], [begin, failure], [begin, failure, firing_failed])
        accepted_begins = attempts.count(begin)
        accepted_failures = attempts.count(failure)
        accepted_firings_failed = attempts.count(firing_failed)
        selected = records.count(CandidateSelected.__name__)
        begun = records.count(FiringBegun.__name__)
        requested = records.count(ActivityRequested.__name__)
        failed = records.count(ActivityFailed.__name__)
        firings_failed = records.count(FiringFailed.__name__)
        worker_failures = cast(int, value["worker_failures"])
        ack_losses = cast(int, value["terminal_ack_losses"])
        expected_key = f"{INSTANCE_ID}:occurrence-1"
        tasks_exact = tasks == [] or tasks in (
            [{"idempotency": expected_key, "state": "pending"}],
            [{"idempotency": expected_key, "state": "running"}],
            [{"idempotency": expected_key, "state": "failed"}],
        )
        failed_custody = tasks == [{"idempotency": expected_key, "state": "failed"}]
        passed = (
            attempts_exact
            and cast(int, value["prepare_calls"]) == accepted_begins
            and selected == begun == requested == accepted_begins == len(tasks)
            and failed == accepted_failures <= worker_failures <= 1
            and firings_failed == accepted_firings_failed <= failed
            and 0 <= ack_losses <= accepted_failures <= 1
            and records.count(FiringCompleted.__name__) == records.count("TokensProduced") == 0
            and failed_custody == (worker_failures == 1)
            and tasks_exact
        )
        return CheckResult(
            passed=passed,
            detail={
                "accepted_begins": accepted_begins,
                "accepted_failures": accepted_failures,
                "accepted_firings_failed": accepted_firings_failed,
                "ack_losses": ack_losses,
                "attempts_exact": attempts_exact,
                "canonical_failures": failed,
                "canonical_firings_failed": firings_failed,
                "failed_custody": failed_custody,
                "tasks_exact": tasks_exact,
                "worker_failures": worker_failures,
            },
        )


class JoinedAcceptedTerminalAuthorityChecker:
    """Independent terminal authority from Worker custody and PostgreSQL transactions."""

    identity = TERMINAL_ACK_LOSS_CHECKER_IDENTITY
    request = ObservationRequest(name="engine.joined-accepted-terminal-authority", payload={})

    def check(self, observation: Observation) -> CheckResult:
        value = cast(dict[str, JsonValue], observation.value)
        records = cast(list[JsonValue], value["record_types"])
        attempts = cast(list[dict[str, JsonValue]], value["transaction_attempts"])
        tasks = cast(list[dict[str, JsonValue]], value["durable_tasks"])
        begin = {
            "accepted": True,
            "dispatch_attempted": True,
            "record_types": ["CandidateSelected", "FiringBegun", "TokensConsumed", "ActivityRequested"],
        }
        terminal = {
            "accepted": True,
            "dispatch_attempted": False,
            "record_types": ["ActivityCompleted"],
        }
        projection = {
            "accepted": True,
            "dispatch_attempted": False,
            "record_types": ["TokensProduced", "FiringCompleted"],
        }
        attempts_exact = attempts in ([], [begin], [begin, terminal], [begin, terminal, projection])
        accepted_begins = sum(attempt == begin for attempt in attempts)
        accepted_terminals = sum(attempt == terminal for attempt in attempts)
        accepted_projections = sum(attempt == projection for attempt in attempts)
        selected = records.count(CandidateSelected.__name__)
        begun = records.count(FiringBegun.__name__)
        requested = records.count(ActivityRequested.__name__)
        completed = records.count(ActivityCompleted.__name__)
        produced = records.count("TokensProduced")
        projected = records.count(FiringCompleted.__name__)
        worker_completions = cast(int, value["worker_completions"])
        ack_losses = cast(int, value["terminal_ack_losses"])
        expected_key = f"{INSTANCE_ID}:occurrence-1"
        tasks_exact = tasks == [] or tasks in (
            [{"idempotency": expected_key, "state": "pending"}],
            [{"idempotency": expected_key, "state": "running"}],
            [{"idempotency": expected_key, "state": "completed"}],
        )
        completed_custody = tasks == [{"idempotency": expected_key, "state": "completed"}]
        passed = (
            attempts_exact
            and cast(int, value["prepare_calls"]) == accepted_begins
            and selected == begun == requested == accepted_begins == len(tasks)
            and completed == accepted_terminals <= worker_completions <= 1
            and produced == projected == accepted_projections <= completed
            and 0 <= ack_losses <= accepted_terminals <= 1
            and completed_custody == (worker_completions == 1)
            and tasks_exact
        )
        return CheckResult(
            passed=passed,
            detail={
                "accepted_begins": accepted_begins,
                "accepted_projections": accepted_projections,
                "accepted_terminals": accepted_terminals,
                "ack_losses": ack_losses,
                "attempts_exact": attempts_exact,
                "canonical_projections": projected,
                "canonical_terminals": completed,
                "completed_custody": completed_custody,
                "tasks_exact": tasks_exact,
                "worker_completions": worker_completions,
            },
        )


class JoinedAcceptedBeginAuthorityChecker:
    """Independent accepted-begin authority from PostgreSQL transaction and task truth."""

    identity = ACK_LOSS_CHECKER_IDENTITY
    request = ObservationRequest(name="engine.joined-accepted-begin-authority", payload={})

    def check(self, observation: Observation) -> CheckResult:
        value = cast(dict[str, JsonValue], observation.value)
        records = cast(list[JsonValue], value["record_types"])
        attempts = cast(list[dict[str, JsonValue]], value["transaction_attempts"])
        tasks = cast(list[dict[str, JsonValue]], value["durable_tasks"])
        accepted_begin = {
            "accepted": True,
            "dispatch_attempted": True,
            "record_types": ["CandidateSelected", "FiringBegun", "TokensConsumed", "ActivityRequested"],
        }
        accepted_begins = sum(attempt == accepted_begin for attempt in attempts)
        attempts_exact = attempts in ([], [accepted_begin])
        selected = records.count(CandidateSelected.__name__)
        begun = records.count(FiringBegun.__name__)
        requested = records.count(ActivityRequested.__name__)
        ack_losses = cast(int, value["commit_ack_losses"])
        expected_tasks = (
            [] if accepted_begins == 0 else [{"idempotency": f"{INSTANCE_ID}:occurrence-1", "state": "pending"}]
        )
        passed = (
            attempts_exact
            and selected == begun == requested == accepted_begins == len(tasks)
            and cast(int, value["prepare_calls"]) == accepted_begins
            and tasks == expected_tasks
            and 0 <= ack_losses <= accepted_begins <= 1
        )
        return CheckResult(
            passed=passed,
            detail={
                "accepted_begins": accepted_begins,
                "ack_losses": ack_losses,
                "attempts_exact": attempts_exact,
                "durable_tasks": len(tasks),
                "prepare_calls": value["prepare_calls"],
            },
        )


class JoinedResetRefusalAuthorityChecker:
    """Independent pre-fence authority from PostgreSQL and Worker facts."""

    identity = RESET_REFUSAL_CHECKER_IDENTITY
    request = ObservationRequest(name="engine.joined-reset-refusal-authority", payload={})

    def check(self, observation: Observation) -> CheckResult:
        value = cast(dict[str, JsonValue], observation.value)
        records = cast(list[JsonValue], value["record_types"])
        attempts = cast(list[dict[str, JsonValue]], value["transaction_attempts"])
        lifecycle_attempts = cast(list[dict[str, JsonValue]], value["lifecycle_attempts"])
        tasks = cast(list[dict[str, JsonValue]], value["durable_tasks"])
        source = {
            "accepted": True,
            "dispatch_attempted": False,
            "record_types": ["ExternalEventDelivered", "FiringBegun", "TokensProduced", "FiringCompleted"],
        }
        begin = {
            "accepted": True,
            "dispatch_attempted": True,
            "record_types": ["CandidateSelected", "FiringBegun", "TokensConsumed", "ActivityRequested"],
        }
        terminal = {
            "accepted": True,
            "dispatch_attempted": False,
            "record_types": ["ActivityCompleted"],
        }
        projection = {
            "accepted": True,
            "dispatch_attempted": False,
            "record_types": ["TokensProduced", "FiringCompleted"],
        }
        expected_attempts = [source, begin, terminal, projection]
        attempts_exact = len(attempts) <= len(expected_attempts) and attempts == expected_attempts[: len(attempts)]
        refused_reset = {"accepted": False, "phase": "scope_reset", "record_types": ["ScopeReset"]}
        lifecycle_exact = lifecycle_attempts in ([], [refused_reset])
        accepted_begins = attempts.count(begin)
        accepted_terminals = attempts.count(terminal)
        accepted_projections = attempts.count(projection)
        reset_attempts = cast(int, value["scope_resets"])
        reset_refusals = cast(int, value["reset_refusals"])
        worker_claims = cast(int, value["worker_claims"])
        worker_completions = cast(int, value["worker_completions"])
        expected_key = f"{INSTANCE_ID}:occurrence-2"
        if worker_completions:
            expected_tasks: list[dict[str, JsonValue]] = [{"idempotency": expected_key, "state": "completed"}]
        elif worker_claims:
            expected_tasks = [{"idempotency": expected_key, "state": "running"}]
        elif accepted_begins:
            expected_tasks = [{"idempotency": expected_key, "state": "pending"}]
        else:
            expected_tasks = []
        canonical_sources = records.count(ExternalEventDelivered.__name__)
        canonical_opens = records.count(ScopeOpened.__name__)
        canonical_resets = records.count(ScopeReset.__name__)
        requested = records.count(ActivityRequested.__name__)
        completed = records.count(ActivityCompleted.__name__)
        projected = records.count(FiringCompleted.__name__) - canonical_sources
        passed = (
            attempts_exact
            and lifecycle_exact
            and canonical_opens == cast(int, value["scope_opens"]) <= 1
            and canonical_sources == cast(int, value["source_deliveries"]) <= 1
            and canonical_resets == 0
            and reset_attempts == reset_refusals == lifecycle_attempts.count(refused_reset) <= 1
            and requested == accepted_begins <= 1
            and cast(int, value["prepare_calls"]) == accepted_begins
            and tasks == expected_tasks
            and 0 <= worker_completions <= worker_claims <= accepted_begins
            and completed == accepted_terminals <= worker_completions
            and projected == accepted_projections <= completed
            and cast(int, value["cancellation_refusals"]) == 0
            and cast(int, value["stale_worker_refusals"]) == 0
            and records.count(ActivityFailed.__name__) == records.count(FiringFailed.__name__) == 0
        )
        return CheckResult(
            passed=passed,
            detail={
                "accepted_begins": accepted_begins,
                "accepted_projections": accepted_projections,
                "accepted_terminals": accepted_terminals,
                "attempts_exact": attempts_exact,
                "canonical_resets": canonical_resets,
                "lifecycle_exact": lifecycle_exact,
                "reset_refusals": reset_refusals,
                "task_state": None if not tasks else tasks[0]["state"],
                "worker_completions": worker_completions,
            },
        )


class JoinedAcceptedResetAuthorityChecker:
    """Independent accepted-reset authority from PostgreSQL and Worker facts."""

    identity = RESET_ACK_LOSS_CHECKER_IDENTITY
    request = ObservationRequest(name="engine.joined-accepted-reset-authority", payload={})

    def check(self, observation: Observation) -> CheckResult:
        value = cast(dict[str, JsonValue], observation.value)
        records = cast(list[JsonValue], value["record_types"])
        attempts = cast(list[dict[str, JsonValue]], value["transaction_attempts"])
        lifecycle_attempts = cast(list[dict[str, JsonValue]], value["lifecycle_attempts"])
        tasks = cast(list[dict[str, JsonValue]], value["durable_tasks"])
        source = {
            "accepted": True,
            "dispatch_attempted": False,
            "record_types": ["ExternalEventDelivered", "FiringBegun", "TokensProduced", "FiringCompleted"],
        }
        begin = {
            "accepted": True,
            "dispatch_attempted": True,
            "record_types": ["CandidateSelected", "FiringBegun", "TokensConsumed", "ActivityRequested"],
        }
        expected_attempts = [source, begin]
        attempts_exact = len(attempts) <= len(expected_attempts) and attempts == expected_attempts[: len(attempts)]
        accepted_reset = {"accepted": True, "phase": "scope_reset", "record_types": ["ScopeReset"]}
        accepted_cancellation = {"accepted": True, "phase": "cancellation", "record_types": []}
        lifecycle_exact = lifecycle_attempts in (
            [],
            [accepted_reset],
            [accepted_reset, accepted_cancellation],
        )
        accepted_begins = attempts.count(begin)
        accepted_resets = lifecycle_attempts.count(accepted_reset)
        accepted_cancellations = lifecycle_attempts.count(accepted_cancellation)
        worker_claims = cast(int, value["worker_claims"])
        expected_key = f"{INSTANCE_ID}:occurrence-2"
        if accepted_cancellations:
            expected_tasks: list[dict[str, JsonValue]] = [{"idempotency": expected_key, "state": "cancelled"}]
        elif worker_claims:
            expected_tasks = [{"idempotency": expected_key, "state": "running"}]
        elif accepted_begins:
            expected_tasks = [{"idempotency": expected_key, "state": "pending"}]
        else:
            expected_tasks = []
        canonical_sources = records.count(ExternalEventDelivered.__name__)
        canonical_opens = records.count(ScopeOpened.__name__)
        canonical_resets = records.count(ScopeReset.__name__)
        requested = records.count(ActivityRequested.__name__)
        completed = records.count(ActivityCompleted.__name__)
        projected = records.count(FiringCompleted.__name__) - canonical_sources
        ack_losses = cast(int, value["reset_ack_losses"])
        stale_refusals = cast(int, value["stale_worker_refusals"])
        passed = (
            attempts_exact
            and lifecycle_exact
            and canonical_opens == cast(int, value["scope_opens"]) <= 1
            and canonical_sources == cast(int, value["source_deliveries"]) <= 1
            and canonical_resets == cast(int, value["scope_resets"]) == accepted_resets <= 1
            and requested == accepted_begins <= 1
            and cast(int, value["prepare_calls"]) == accepted_begins
            and tasks == expected_tasks
            and 0 <= worker_claims <= accepted_begins
            and 0 <= ack_losses <= accepted_resets
            and 0 <= accepted_cancellations <= accepted_resets
            and 0 <= stale_refusals <= accepted_cancellations
            and cast(int, value["reset_refusals"]) == 0
            and cast(int, value["cancellation_refusals"]) == 0
            and completed == projected == 0
            and records.count(ActivityFailed.__name__) == records.count(FiringFailed.__name__) == 0
        )
        return CheckResult(
            passed=passed,
            detail={
                "accepted_begins": accepted_begins,
                "accepted_cancellations": accepted_cancellations,
                "accepted_resets": accepted_resets,
                "ack_losses": ack_losses,
                "attempts_exact": attempts_exact,
                "canonical_resets": canonical_resets,
                "lifecycle_exact": lifecycle_exact,
                "stale_worker_refusals": stale_refusals,
                "task_state": None if not tasks else tasks[0]["state"],
            },
        )


class JoinedCancellationAuthorityChecker:
    """Independent reset/tombstone authority from authored and PostgreSQL facts."""

    identity = CANCELLATION_CHECKER_IDENTITY
    request = ObservationRequest(name="engine.joined-cancellation-authority", payload={})

    def check(self, observation: Observation) -> CheckResult:
        value = cast(dict[str, JsonValue], observation.value)
        records = cast(list[JsonValue], value["record_types"])
        attempts = cast(list[dict[str, JsonValue]], value["transaction_attempts"])
        lifecycle_attempts = cast(list[dict[str, JsonValue]], value["lifecycle_attempts"])
        tasks = cast(list[dict[str, JsonValue]], value["durable_tasks"])
        source = {
            "accepted": True,
            "dispatch_attempted": False,
            "record_types": ["ExternalEventDelivered", "FiringBegun", "TokensProduced", "FiringCompleted"],
        }
        begin = {
            "accepted": True,
            "dispatch_attempted": True,
            "record_types": ["CandidateSelected", "FiringBegun", "TokensConsumed", "ActivityRequested"],
        }
        attempts_exact = attempts in ([], [source], [source, begin])
        accepted_begins = sum(attempt == begin for attempt in attempts)
        scope_resets = cast(int, value["scope_resets"])
        expected_lifecycle: list[dict[str, JsonValue]] = []
        if scope_resets:
            expected_lifecycle = [
                {"accepted": True, "phase": "scope_reset", "record_types": ["ScopeReset"]},
                {"accepted": False, "phase": "cancellation", "record_types": []},
            ]
        accepted_cancellations = sum(
            attempt == {"accepted": True, "phase": "cancellation", "record_types": []} for attempt in lifecycle_attempts
        )
        if accepted_cancellations:
            expected_lifecycle.append({"accepted": True, "phase": "cancellation", "record_types": []})
        lifecycle_exact = lifecycle_attempts == expected_lifecycle
        expected_key = f"{INSTANCE_ID}:occurrence-2"
        worker_claims = cast(int, value["worker_claims"])
        if accepted_cancellations:
            expected_tasks: list[dict[str, JsonValue]] = [{"idempotency": expected_key, "state": "cancelled"}]
        elif worker_claims:
            expected_tasks = [{"idempotency": expected_key, "state": "running"}]
        elif accepted_begins:
            expected_tasks = [{"idempotency": expected_key, "state": "pending"}]
        else:
            expected_tasks = []
        canonical_sources = records.count(ExternalEventDelivered.__name__)
        canonical_opens = records.count(ScopeOpened.__name__)
        canonical_resets = records.count(ScopeReset.__name__)
        requested = records.count(ActivityRequested.__name__)
        completed = records.count(ActivityCompleted.__name__)
        projected = records.count(FiringCompleted.__name__) - canonical_sources
        stale_refusals = cast(int, value["stale_worker_refusals"])
        cancellation_refusals = cast(int, value["cancellation_refusals"])
        passed = (
            attempts_exact
            and lifecycle_exact
            and canonical_opens == cast(int, value["scope_opens"]) <= 1
            and canonical_sources == cast(int, value["source_deliveries"]) <= 1
            and canonical_resets == scope_resets <= 1
            and requested == accepted_begins <= 1
            and cast(int, value["prepare_calls"]) == accepted_begins
            and tasks == expected_tasks
            and 0 <= worker_claims <= accepted_begins
            and cancellation_refusals
            == lifecycle_attempts.count({"accepted": False, "phase": "cancellation", "record_types": []})
            and 0 <= accepted_cancellations <= scope_resets
            and 0 <= stale_refusals <= accepted_cancellations
            and completed == projected == 0
        )
        return CheckResult(
            passed=passed,
            detail={
                "accepted_begins": accepted_begins,
                "accepted_cancellations": accepted_cancellations,
                "attempts_exact": attempts_exact,
                "canonical_resets": canonical_resets,
                "cancellation_refusals": cancellation_refusals,
                "lifecycle_exact": lifecycle_exact,
                "stale_worker_refusals": stale_refusals,
                "task_state": None if not tasks else tasks[0]["state"],
            },
        )


class JoinedAcceptedCancellationAuthorityChecker:
    """Independent accepted-tombstone authority from PostgreSQL and Worker facts."""

    identity = CANCELLATION_ACK_LOSS_CHECKER_IDENTITY
    request = ObservationRequest(name="engine.joined-accepted-cancellation-authority", payload={})

    def check(self, observation: Observation) -> CheckResult:
        value = cast(dict[str, JsonValue], observation.value)
        records = cast(list[JsonValue], value["record_types"])
        attempts = cast(list[dict[str, JsonValue]], value["transaction_attempts"])
        lifecycle_attempts = cast(list[dict[str, JsonValue]], value["lifecycle_attempts"])
        tasks = cast(list[dict[str, JsonValue]], value["durable_tasks"])
        source = {
            "accepted": True,
            "dispatch_attempted": False,
            "record_types": ["ExternalEventDelivered", "FiringBegun", "TokensProduced", "FiringCompleted"],
        }
        begin = {
            "accepted": True,
            "dispatch_attempted": True,
            "record_types": ["CandidateSelected", "FiringBegun", "TokensConsumed", "ActivityRequested"],
        }
        attempts_exact = attempts in ([], [source], [source, begin])
        accepted_begins = sum(attempt == begin for attempt in attempts)
        scope_resets = cast(int, value["scope_resets"])
        accepted_cancellation = {"accepted": True, "phase": "cancellation", "record_types": []}
        expected_lifecycle: list[dict[str, JsonValue]] = []
        if scope_resets:
            expected_lifecycle = [
                {"accepted": True, "phase": "scope_reset", "record_types": ["ScopeReset"]},
                accepted_cancellation,
            ]
        accepted_cancellations = lifecycle_attempts.count(accepted_cancellation)
        lifecycle_exact = lifecycle_attempts == expected_lifecycle
        expected_key = f"{INSTANCE_ID}:occurrence-2"
        worker_claims = cast(int, value["worker_claims"])
        if accepted_cancellations:
            expected_tasks: list[dict[str, JsonValue]] = [{"idempotency": expected_key, "state": "cancelled"}]
        elif worker_claims:
            expected_tasks = [{"idempotency": expected_key, "state": "running"}]
        elif accepted_begins:
            expected_tasks = [{"idempotency": expected_key, "state": "pending"}]
        else:
            expected_tasks = []
        canonical_sources = records.count(ExternalEventDelivered.__name__)
        canonical_opens = records.count(ScopeOpened.__name__)
        canonical_resets = records.count(ScopeReset.__name__)
        requested = records.count(ActivityRequested.__name__)
        completed = records.count(ActivityCompleted.__name__)
        projected = records.count(FiringCompleted.__name__) - canonical_sources
        stale_refusals = cast(int, value["stale_worker_refusals"])
        ack_losses = cast(int, value["cancellation_ack_losses"])
        passed = (
            attempts_exact
            and lifecycle_exact
            and canonical_opens == cast(int, value["scope_opens"]) <= 1
            and canonical_sources == cast(int, value["source_deliveries"]) <= 1
            and canonical_resets == scope_resets <= 1
            and requested == accepted_begins <= 1
            and cast(int, value["prepare_calls"]) == accepted_begins
            and tasks == expected_tasks
            and 0 <= worker_claims <= accepted_begins
            and cast(int, value["cancellation_refusals"]) == 0
            and 0 <= accepted_cancellations <= scope_resets
            and 0 <= ack_losses <= accepted_cancellations
            and 0 <= stale_refusals <= accepted_cancellations
            and completed == projected == 0
        )
        return CheckResult(
            passed=passed,
            detail={
                "accepted_begins": accepted_begins,
                "accepted_cancellations": accepted_cancellations,
                "ack_losses": ack_losses,
                "attempts_exact": attempts_exact,
                "canonical_resets": canonical_resets,
                "lifecycle_exact": lifecycle_exact,
                "stale_worker_refusals": stale_refusals,
                "task_state": None if not tasks else tasks[0]["state"],
            },
        )


def execute_joined_begin_story(dsn: str) -> tuple[World, JoinedBeginProfile, Timeline]:
    """Refuse one joined begin commit, drop, reload, and begin exactly once."""

    profile = JoinedBeginProfile(dsn)
    world = World(profile, WORLD_BUDGET, checkers=(JoinedCommitAuthorityChecker(),))
    timeline = world.timeline()

    timeline.activate_fault(
        "history.commit-refuse",
        "activity_requested",
        disposition=FaultDisposition.REFUSE,
        payload={"message": "dst joined begin commit refused"},
    )
    timeline.command("engine.drive", {})
    refused = timeline.observe("joined-begin-refused")
    refused_value = cast(dict[str, JsonValue], refused.value)
    assert refused_value["frontier"] == 2
    assert refused_value["record_types"] == ["InstanceCreated", "TokensInitialized"]
    assert refused_value["durable_tasks"] == []
    assert refused_value["prepare_calls"] == refused_value["commit_refusals"] == 1
    assert refused_value["status"] == "poisoned"

    stale = timeline
    timeline.crash("semantic_batch_refused")
    world.restart()
    timeline = world.timeline()
    recovered = timeline.run_until(
        "joined-begin-recovered",
        lambda observation: len(cast(dict[str, JsonValue], observation.value)["durable_tasks"]) == 1,
    )
    recovered_value = cast(dict[str, JsonValue], recovered.value)
    assert recovered_value["frontier"] == 6
    assert recovered_value["record_types"] == [
        "InstanceCreated",
        "TokensInitialized",
        "CandidateSelected",
        "FiringBegun",
        "TokensConsumed",
        "ActivityRequested",
    ]
    assert recovered_value["prepare_calls"] == 2
    assert recovered_value["transaction_attempts"] == [
        {
            "accepted": False,
            "dispatch_attempted": True,
            "record_types": ["CandidateSelected", "FiringBegun", "TokensConsumed", "ActivityRequested"],
        },
        {
            "accepted": True,
            "dispatch_attempted": True,
            "record_types": ["CandidateSelected", "FiringBegun", "TokensConsumed", "ActivityRequested"],
        },
    ]
    timeline.finish(Disposition.EXTERNAL_WAIT)
    return world, profile, stale


def build_joined_begin_artifact(dsn: str) -> ScenarioArtifactV3:
    world, _, _ = execute_joined_begin_story(dsn)
    try:
        artifact = world.artifact(SCENARIO_ID)
        assert isinstance(artifact, ScenarioArtifactV3)
        return artifact
    finally:
        world.close()


def execute_joined_dispatch_story(dsn: str) -> tuple[World, JoinedDispatchProfile, Timeline]:
    """Refuse one joined task spawn, drop, reload, and begin exactly once."""

    profile = JoinedDispatchProfile(dsn)
    world = World(profile, WORLD_BUDGET, checkers=(JoinedCommitAuthorityChecker(),))
    timeline = world.timeline()

    timeline.activate_fault(
        "dispatch.refuse",
        "activity_requested",
        disposition=FaultDisposition.REFUSE,
        payload={"message": "dst joined Dispatch spawn refused"},
    )
    timeline.command("engine.drive", {})
    refused = timeline.observe("joined-dispatch-refused")
    refused_value = cast(dict[str, JsonValue], refused.value)
    assert refused_value["frontier"] == 2
    assert refused_value["record_types"] == ["InstanceCreated", "TokensInitialized"]
    assert refused_value["durable_tasks"] == []
    assert refused_value["prepare_calls"] == refused_value["dispatch_refusals"] == 1
    assert refused_value["status"] == "poisoned"

    stale = timeline
    timeline.crash("joined_dispatch_refused")
    world.restart()
    timeline = world.timeline()
    recovered = timeline.run_until(
        "joined-dispatch-recovered",
        lambda observation: len(cast(dict[str, JsonValue], observation.value)["durable_tasks"]) == 1,
    )
    recovered_value = cast(dict[str, JsonValue], recovered.value)
    assert recovered_value["frontier"] == 6
    assert recovered_value["record_types"] == [
        "InstanceCreated",
        "TokensInitialized",
        "CandidateSelected",
        "FiringBegun",
        "TokensConsumed",
        "ActivityRequested",
    ]
    assert recovered_value["prepare_calls"] == 2
    assert recovered_value["transaction_attempts"] == [
        {
            "accepted": False,
            "dispatch_attempted": True,
            "record_types": ["CandidateSelected", "FiringBegun", "TokensConsumed", "ActivityRequested"],
        },
        {
            "accepted": True,
            "dispatch_attempted": True,
            "record_types": ["CandidateSelected", "FiringBegun", "TokensConsumed", "ActivityRequested"],
        },
    ]
    timeline.finish(Disposition.EXTERNAL_WAIT)
    return world, profile, stale


def build_joined_dispatch_artifact(dsn: str) -> ScenarioArtifactV3:
    world, _, _ = execute_joined_dispatch_story(dsn)
    try:
        artifact = world.artifact(DISPATCH_SCENARIO_ID)
        assert isinstance(artifact, ScenarioArtifactV3)
        return artifact
    finally:
        world.close()


def execute_joined_ack_loss_story(dsn: str) -> tuple[World, JoinedBeginAckLossProfile, Timeline]:
    """Lose one accepted joined-begin acknowledgement, drop, and load exact truth."""

    profile = JoinedBeginAckLossProfile(dsn)
    world = World(profile, WORLD_BUDGET, checkers=(JoinedAcceptedBeginAuthorityChecker(),))
    timeline = world.timeline()

    timeline.activate_fault(
        "history.lose-ack",
        "activity_requested_committed",
        disposition=FaultDisposition.RAISE,
        payload={"message": "dst joined begin acknowledgement lost"},
    )
    timeline.command("engine.drive", {})
    lost = timeline.observe("joined-begin-ack-lost")
    lost_value = cast(dict[str, JsonValue], lost.value)
    assert lost_value["frontier"] == 6
    assert lost_value["record_types"] == [
        "InstanceCreated",
        "TokensInitialized",
        "CandidateSelected",
        "FiringBegun",
        "TokensConsumed",
        "ActivityRequested",
    ]
    assert lost_value["durable_tasks"] == [{"idempotency": f"{INSTANCE_ID}:occurrence-1", "state": "pending"}]
    assert lost_value["prepare_calls"] == lost_value["commit_ack_losses"] == 1
    assert lost_value["drive_calls"] == 1
    assert lost_value["status"] == "poisoned"

    stale = timeline
    timeline.crash("joined_begin_committed_ack_lost")
    world.restart()
    timeline = world.timeline()
    recovered = timeline.run_until(
        "joined-begin-ack-recovered",
        lambda observation: cast(dict[str, JsonValue], observation.value)["drive_calls"] == 2,
    )
    recovered_value = cast(dict[str, JsonValue], recovered.value)
    assert recovered_value["frontier"] == 6
    assert recovered_value["record_types"] == lost_value["record_types"]
    assert recovered_value["durable_tasks"] == lost_value["durable_tasks"]
    assert recovered_value["prepare_calls"] == recovered_value["commit_ack_losses"] == 1
    assert recovered_value["transaction_attempts"] == [
        {
            "accepted": True,
            "dispatch_attempted": True,
            "record_types": ["CandidateSelected", "FiringBegun", "TokensConsumed", "ActivityRequested"],
        }
    ]
    timeline.finish(Disposition.EXTERNAL_WAIT)
    return world, profile, stale


def build_joined_ack_loss_artifact(dsn: str) -> ScenarioArtifactV3:
    world, _, _ = execute_joined_ack_loss_story(dsn)
    try:
        artifact = world.artifact(ACK_LOSS_SCENARIO_ID)
        assert isinstance(artifact, ScenarioArtifactV3)
        return artifact
    finally:
        world.close()


def execute_joined_terminal_refusal_story(
    dsn: str,
) -> tuple[World, JoinedTerminalRefusalProfile, Timeline]:
    """Refuse one semantic terminal commit, drop, recollect, and project once."""

    profile = JoinedTerminalRefusalProfile(dsn)
    world = World(profile, WORLD_BUDGET, checkers=(JoinedTerminalAuthorityChecker(),))
    timeline = world.timeline()

    timeline.command("engine.drive", {})
    timeline.command("worker.claim", {})
    timeline.command("worker.complete", {"result": {"value": 3}})
    timeline.activate_fault(
        "history.commit-refuse",
        "activity_completed",
        disposition=FaultDisposition.REFUSE,
        payload={"message": "dst joined terminal commit refused"},
    )
    timeline.command("engine.drive", {})
    refused = timeline.observe("joined-terminal-refused")
    refused_value = cast(dict[str, JsonValue], refused.value)
    assert refused_value["record_types"] == [
        "InstanceCreated",
        "TokensInitialized",
        "CandidateSelected",
        "FiringBegun",
        "TokensConsumed",
        "ActivityRequested",
    ]
    assert refused_value["durable_tasks"] == [{"idempotency": f"{INSTANCE_ID}:occurrence-1", "state": "completed"}]
    assert refused_value["frontier"] == 6
    assert refused_value["prepare_calls"] == refused_value["terminal_refusals"] == 1
    assert refused_value["status"] == "poisoned"
    assert refused_value["worker_completions"] == 1

    stale = timeline
    timeline.crash("joined_terminal_commit_refused")
    world.restart()
    timeline = world.timeline()
    recovered = timeline.run_until(
        "joined-terminal-recovered",
        lambda observation: (
            "FiringCompleted" in cast(list[JsonValue], cast(dict[str, JsonValue], observation.value)["record_types"])
        ),
    )
    recovered_value = cast(dict[str, JsonValue], recovered.value)
    assert recovered_value["record_types"] == [
        "InstanceCreated",
        "TokensInitialized",
        "CandidateSelected",
        "FiringBegun",
        "TokensConsumed",
        "ActivityRequested",
        "ActivityCompleted",
        "TokensProduced",
        "FiringCompleted",
    ]
    assert recovered_value["frontier"] == 9
    assert recovered_value["prepare_calls"] == recovered_value["worker_completions"] == 1
    assert recovered_value["terminal_refusals"] == 1
    assert recovered_value["transaction_attempts"] == [
        {
            "accepted": True,
            "dispatch_attempted": True,
            "record_types": ["CandidateSelected", "FiringBegun", "TokensConsumed", "ActivityRequested"],
        },
        {
            "accepted": False,
            "dispatch_attempted": False,
            "record_types": ["ActivityCompleted"],
        },
        {
            "accepted": True,
            "dispatch_attempted": False,
            "record_types": ["ActivityCompleted"],
        },
        {
            "accepted": True,
            "dispatch_attempted": False,
            "record_types": ["TokensProduced", "FiringCompleted"],
        },
    ]
    timeline.finish(Disposition.CONVERGED)
    return world, profile, stale


def build_joined_terminal_refusal_artifact(dsn: str) -> ScenarioArtifactV3:
    world, _, _ = execute_joined_terminal_refusal_story(dsn)
    try:
        artifact = world.artifact(TERMINAL_REFUSAL_SCENARIO_ID)
        assert isinstance(artifact, ScenarioArtifactV3)
        return artifact
    finally:
        world.close()


def execute_joined_failure_refusal_story(
    dsn: str,
) -> tuple[World, JoinedFailureRefusalProfile, Timeline]:
    """Refuse one semantic failure commit, drop, recollect, and fail once."""

    profile = JoinedFailureRefusalProfile(dsn)
    world = World(profile, WORLD_BUDGET, checkers=(JoinedFailureAuthorityChecker(),))
    timeline = world.timeline()

    timeline.command("engine.drive", {})
    timeline.command("worker.claim", {})
    timeline.command("worker.fail", {"error": "dst joined terminal failure"})
    timeline.activate_fault(
        "history.commit-refuse",
        "activity_failed",
        disposition=FaultDisposition.REFUSE,
        payload={"message": "dst joined failure commit refused"},
    )
    timeline.command("engine.drive", {})
    refused = timeline.observe("joined-failure-refused")
    refused_value = cast(dict[str, JsonValue], refused.value)
    assert refused_value["record_types"] == [
        "InstanceCreated",
        "TokensInitialized",
        "CandidateSelected",
        "FiringBegun",
        "TokensConsumed",
        "ActivityRequested",
    ]
    assert refused_value["durable_tasks"] == [{"idempotency": f"{INSTANCE_ID}:occurrence-1", "state": "failed"}]
    assert refused_value["frontier"] == 6
    assert refused_value["prepare_calls"] == refused_value["terminal_refusals"] == 1
    assert refused_value["status"] == "poisoned"
    assert refused_value["worker_failures"] == 1

    stale = timeline
    timeline.crash("joined_failure_commit_refused")
    world.restart()
    timeline = world.timeline()
    recovered = timeline.run_until(
        "joined-failure-recovered",
        lambda observation: (
            "FiringFailed" in cast(list[JsonValue], cast(dict[str, JsonValue], observation.value)["record_types"])
        ),
    )
    recovered_value = cast(dict[str, JsonValue], recovered.value)
    assert recovered_value["record_types"] == [
        "InstanceCreated",
        "TokensInitialized",
        "CandidateSelected",
        "FiringBegun",
        "TokensConsumed",
        "ActivityRequested",
        "ActivityFailed",
        "FiringFailed",
    ]
    assert recovered_value["frontier"] == 8
    assert recovered_value["prepare_calls"] == recovered_value["worker_failures"] == 1
    assert recovered_value["terminal_refusals"] == 1
    assert recovered_value["transaction_attempts"] == [
        {
            "accepted": True,
            "dispatch_attempted": True,
            "record_types": ["CandidateSelected", "FiringBegun", "TokensConsumed", "ActivityRequested"],
        },
        {
            "accepted": False,
            "dispatch_attempted": False,
            "record_types": ["ActivityFailed"],
        },
        {
            "accepted": True,
            "dispatch_attempted": False,
            "record_types": ["ActivityFailed"],
        },
        {
            "accepted": True,
            "dispatch_attempted": False,
            "record_types": ["FiringFailed"],
        },
    ]
    timeline.finish(Disposition.QUARANTINED)
    return world, profile, stale


def build_joined_failure_refusal_artifact(dsn: str) -> ScenarioArtifactV3:
    world, _, _ = execute_joined_failure_refusal_story(dsn)
    try:
        artifact = world.artifact(FAILURE_REFUSAL_SCENARIO_ID)
        assert isinstance(artifact, ScenarioArtifactV3)
        return artifact
    finally:
        world.close()


def execute_joined_failure_ack_loss_story(
    dsn: str,
) -> tuple[World, JoinedFailureAckLossProfile, Timeline]:
    """Lose one accepted ActivityFailed acknowledgement, drop, and finish once."""

    profile = JoinedFailureAckLossProfile(dsn)
    world = World(profile, WORLD_BUDGET, checkers=(JoinedAcceptedFailureAuthorityChecker(),))
    timeline = world.timeline()

    timeline.command("engine.drive", {})
    timeline.command("worker.claim", {})
    timeline.command("worker.fail", {"error": "dst joined terminal failure"})
    timeline.activate_fault(
        "history.lose-ack",
        "activity_failed_committed",
        disposition=FaultDisposition.RAISE,
        payload={"message": "dst joined failure acknowledgement lost"},
    )
    timeline.command("engine.drive", {})
    lost = timeline.observe("joined-failure-ack-lost")
    lost_value = cast(dict[str, JsonValue], lost.value)
    assert lost_value["record_types"] == [
        "InstanceCreated",
        "TokensInitialized",
        "CandidateSelected",
        "FiringBegun",
        "TokensConsumed",
        "ActivityRequested",
        "ActivityFailed",
    ]
    assert lost_value["durable_tasks"] == [{"idempotency": f"{INSTANCE_ID}:occurrence-1", "state": "failed"}]
    assert lost_value["frontier"] == 7
    assert lost_value["prepare_calls"] == lost_value["terminal_ack_losses"] == 1
    assert lost_value["status"] == "poisoned"
    assert lost_value["worker_failures"] == 1

    stale = timeline
    timeline.crash("joined_failure_committed_ack_lost")
    world.restart()
    timeline = world.timeline()
    recovered = timeline.run_until(
        "joined-failure-ack-recovered",
        lambda observation: (
            "FiringFailed" in cast(list[JsonValue], cast(dict[str, JsonValue], observation.value)["record_types"])
        ),
    )
    recovered_value = cast(dict[str, JsonValue], recovered.value)
    assert recovered_value["record_types"] == [
        "InstanceCreated",
        "TokensInitialized",
        "CandidateSelected",
        "FiringBegun",
        "TokensConsumed",
        "ActivityRequested",
        "ActivityFailed",
        "FiringFailed",
    ]
    assert recovered_value["frontier"] == 8
    assert recovered_value["prepare_calls"] == recovered_value["worker_failures"] == 1
    assert recovered_value["terminal_ack_losses"] == 1
    assert recovered_value["transaction_attempts"] == [
        {
            "accepted": True,
            "dispatch_attempted": True,
            "record_types": ["CandidateSelected", "FiringBegun", "TokensConsumed", "ActivityRequested"],
        },
        {
            "accepted": True,
            "dispatch_attempted": False,
            "record_types": ["ActivityFailed"],
        },
        {
            "accepted": True,
            "dispatch_attempted": False,
            "record_types": ["FiringFailed"],
        },
    ]
    timeline.finish(Disposition.QUARANTINED)
    return world, profile, stale


def build_joined_failure_ack_loss_artifact(dsn: str) -> ScenarioArtifactV3:
    world, _, _ = execute_joined_failure_ack_loss_story(dsn)
    try:
        artifact = world.artifact(FAILURE_ACK_LOSS_SCENARIO_ID)
        assert isinstance(artifact, ScenarioArtifactV3)
        return artifact
    finally:
        world.close()


def execute_joined_terminal_ack_loss_story(
    dsn: str,
) -> tuple[World, JoinedTerminalAckLossProfile, Timeline]:
    """Lose one accepted terminal acknowledgement, drop, load, and project once."""

    profile = JoinedTerminalAckLossProfile(dsn)
    world = World(profile, WORLD_BUDGET, checkers=(JoinedAcceptedTerminalAuthorityChecker(),))
    timeline = world.timeline()

    timeline.command("engine.drive", {})
    timeline.command("worker.claim", {})
    timeline.command("worker.complete", {"result": {"value": 3}})
    timeline.activate_fault(
        "history.lose-ack",
        "activity_completed_committed",
        disposition=FaultDisposition.RAISE,
        payload={"message": "dst joined terminal acknowledgement lost"},
    )
    timeline.command("engine.drive", {})
    lost = timeline.observe("joined-terminal-ack-lost")
    lost_value = cast(dict[str, JsonValue], lost.value)
    assert lost_value["record_types"] == [
        "InstanceCreated",
        "TokensInitialized",
        "CandidateSelected",
        "FiringBegun",
        "TokensConsumed",
        "ActivityRequested",
        "ActivityCompleted",
    ]
    assert lost_value["durable_tasks"] == [{"idempotency": f"{INSTANCE_ID}:occurrence-1", "state": "completed"}]
    assert lost_value["frontier"] == 7
    assert lost_value["prepare_calls"] == lost_value["terminal_ack_losses"] == 1
    assert lost_value["status"] == "poisoned"
    assert lost_value["worker_completions"] == 1

    stale = timeline
    timeline.crash("joined_terminal_committed_ack_lost")
    world.restart()
    timeline = world.timeline()
    recovered = timeline.run_until(
        "joined-terminal-ack-recovered",
        lambda observation: (
            "FiringCompleted" in cast(list[JsonValue], cast(dict[str, JsonValue], observation.value)["record_types"])
        ),
    )
    recovered_value = cast(dict[str, JsonValue], recovered.value)
    assert recovered_value["record_types"] == [
        "InstanceCreated",
        "TokensInitialized",
        "CandidateSelected",
        "FiringBegun",
        "TokensConsumed",
        "ActivityRequested",
        "ActivityCompleted",
        "TokensProduced",
        "FiringCompleted",
    ]
    assert recovered_value["frontier"] == 9
    assert recovered_value["prepare_calls"] == recovered_value["worker_completions"] == 1
    assert recovered_value["terminal_ack_losses"] == 1
    assert recovered_value["transaction_attempts"] == [
        {
            "accepted": True,
            "dispatch_attempted": True,
            "record_types": ["CandidateSelected", "FiringBegun", "TokensConsumed", "ActivityRequested"],
        },
        {
            "accepted": True,
            "dispatch_attempted": False,
            "record_types": ["ActivityCompleted"],
        },
        {
            "accepted": True,
            "dispatch_attempted": False,
            "record_types": ["TokensProduced", "FiringCompleted"],
        },
    ]
    timeline.finish(Disposition.CONVERGED)
    return world, profile, stale


def build_joined_terminal_ack_loss_artifact(dsn: str) -> ScenarioArtifactV3:
    world, _, _ = execute_joined_terminal_ack_loss_story(dsn)
    try:
        artifact = world.artifact(TERMINAL_ACK_LOSS_SCENARIO_ID)
        assert isinstance(artifact, ScenarioArtifactV3)
        return artifact
    finally:
        world.close()


def execute_joined_projection_story(dsn: str) -> tuple[World, JoinedProjectionProfile, Timeline]:
    """Freeze one real terminal, refuse projection commit, and recover it once."""

    profile = JoinedProjectionProfile(dsn)
    world = World(profile, WORLD_BUDGET, checkers=(JoinedProjectionAuthorityChecker(),))
    timeline = world.timeline()

    timeline.command("engine.drive", {})
    timeline.command("worker.claim", {})
    timeline.command("worker.complete", {"result": {"value": 3}})
    timeline.activate_fault(
        "history.commit-refuse",
        "projection_committed",
        disposition=FaultDisposition.REFUSE,
        payload={"message": "dst joined projection commit refused"},
    )
    timeline.command("engine.drive", {})
    refused = timeline.observe("joined-projection-refused")
    refused_value = cast(dict[str, JsonValue], refused.value)
    assert refused_value["record_types"] == [
        "InstanceCreated",
        "TokensInitialized",
        "CandidateSelected",
        "FiringBegun",
        "TokensConsumed",
        "ActivityRequested",
        "ActivityCompleted",
    ]
    assert refused_value["durable_tasks"] == [{"idempotency": f"{INSTANCE_ID}:occurrence-1", "state": "completed"}]
    assert refused_value["frontier"] == 7
    assert refused_value["prepare_calls"] == refused_value["projection_refusals"] == 1
    assert refused_value["status"] == "poisoned"
    assert refused_value["worker_completions"] == 1

    stale = timeline
    timeline.crash("projection_batch_refused")
    world.restart()
    timeline = world.timeline()
    recovered = timeline.run_until(
        "joined-projection-recovered",
        lambda observation: (
            "FiringCompleted" in cast(list[JsonValue], cast(dict[str, JsonValue], observation.value)["record_types"])
        ),
    )
    recovered_value = cast(dict[str, JsonValue], recovered.value)
    assert recovered_value["record_types"] == [
        "InstanceCreated",
        "TokensInitialized",
        "CandidateSelected",
        "FiringBegun",
        "TokensConsumed",
        "ActivityRequested",
        "ActivityCompleted",
        "TokensProduced",
        "FiringCompleted",
    ]
    assert recovered_value["frontier"] == 9
    assert recovered_value["prepare_calls"] == recovered_value["worker_completions"] == 1
    assert recovered_value["transaction_attempts"] == [
        {
            "accepted": True,
            "dispatch_attempted": True,
            "record_types": ["CandidateSelected", "FiringBegun", "TokensConsumed", "ActivityRequested"],
        },
        {
            "accepted": True,
            "dispatch_attempted": False,
            "record_types": ["ActivityCompleted"],
        },
        {
            "accepted": False,
            "dispatch_attempted": False,
            "record_types": ["TokensProduced", "FiringCompleted"],
        },
        {
            "accepted": True,
            "dispatch_attempted": False,
            "record_types": ["TokensProduced", "FiringCompleted"],
        },
    ]
    timeline.finish(Disposition.CONVERGED)
    return world, profile, stale


def build_joined_projection_artifact(dsn: str) -> ScenarioArtifactV3:
    world, _, _ = execute_joined_projection_story(dsn)
    try:
        artifact = world.artifact(PROJECTION_SCENARIO_ID)
        assert isinstance(artifact, ScenarioArtifactV3)
        return artifact
    finally:
        world.close()


def execute_joined_projection_ack_loss_story(
    dsn: str,
) -> tuple[World, JoinedProjectionAckLossProfile, Timeline]:
    """Lose one accepted projection acknowledgement, drop, and load exact truth."""

    profile = JoinedProjectionAckLossProfile(dsn)
    world = World(profile, WORLD_BUDGET, checkers=(JoinedAcceptedProjectionAuthorityChecker(),))
    timeline = world.timeline()

    timeline.command("engine.drive", {})
    timeline.command("worker.claim", {})
    timeline.command("worker.complete", {"result": {"value": 3}})
    timeline.activate_fault(
        "history.lose-ack",
        "projection_committed",
        disposition=FaultDisposition.RAISE,
        payload={"message": "dst joined projection acknowledgement lost"},
    )
    timeline.command("engine.drive", {})
    lost = timeline.observe("joined-projection-ack-lost")
    lost_value = cast(dict[str, JsonValue], lost.value)
    assert lost_value["record_types"] == [
        "InstanceCreated",
        "TokensInitialized",
        "CandidateSelected",
        "FiringBegun",
        "TokensConsumed",
        "ActivityRequested",
        "ActivityCompleted",
        "TokensProduced",
        "FiringCompleted",
    ]
    assert lost_value["durable_tasks"] == [{"idempotency": f"{INSTANCE_ID}:occurrence-1", "state": "completed"}]
    assert lost_value["frontier"] == 9
    assert lost_value["prepare_calls"] == lost_value["projection_ack_losses"] == 1
    assert lost_value["status"] == "poisoned"
    assert lost_value["worker_completions"] == 1

    stale = timeline
    timeline.crash("joined_projection_committed_ack_lost")
    world.restart()
    timeline = world.timeline()
    recovered = timeline.run_until(
        "joined-projection-ack-recovered",
        lambda observation: cast(dict[str, JsonValue], observation.value)["drive_calls"] == 3,
    )
    recovered_value = cast(dict[str, JsonValue], recovered.value)
    assert recovered_value["record_types"] == lost_value["record_types"]
    assert recovered_value["durable_tasks"] == lost_value["durable_tasks"]
    assert recovered_value["frontier"] == 9
    assert recovered_value["prepare_calls"] == recovered_value["worker_completions"] == 1
    assert recovered_value["projection_ack_losses"] == 1
    assert recovered_value["transaction_attempts"] == [
        {
            "accepted": True,
            "dispatch_attempted": True,
            "record_types": ["CandidateSelected", "FiringBegun", "TokensConsumed", "ActivityRequested"],
        },
        {
            "accepted": True,
            "dispatch_attempted": False,
            "record_types": ["ActivityCompleted"],
        },
        {
            "accepted": True,
            "dispatch_attempted": False,
            "record_types": ["TokensProduced", "FiringCompleted"],
        },
    ]
    timeline.finish(Disposition.CONVERGED)
    return world, profile, stale


def build_joined_projection_ack_loss_artifact(dsn: str) -> ScenarioArtifactV3:
    world, _, _ = execute_joined_projection_ack_loss_story(dsn)
    try:
        artifact = world.artifact(PROJECTION_ACK_LOSS_SCENARIO_ID)
        assert isinstance(artifact, ScenarioArtifactV3)
        return artifact
    finally:
        world.close()


def execute_joined_reset_refusal_story(dsn: str) -> tuple[World, JoinedResetRefusalProfile, Timeline]:
    """Refuse the canonical reset, reload generation one, and accept its Worker result."""

    profile = JoinedResetRefusalProfile(dsn)
    world = World(profile, CANCELLATION_WORLD_BUDGET, checkers=(JoinedResetRefusalAuthorityChecker(),))
    timeline = world.timeline()

    timeline.command("scope.open", {"name": "draft"})
    timeline.command(
        "source.deliver",
        {"identity": "draft-input-3", "scope": "draft", "value": 3},
    )
    ready = timeline.run_until(
        "joined-reset-ready",
        lambda observation: (
            cast(dict[str, JsonValue], observation.value)["durable_tasks"]
            == [{"idempotency": f"{INSTANCE_ID}:occurrence-2", "state": "pending"}]
        ),
    )
    ready_value = cast(dict[str, JsonValue], ready.value)
    assert ready_value["frontier"] == 11
    assert ready_value["prepare_calls"] == 1

    timeline.command("worker.claim", {})
    claimed = timeline.observe("joined-reset-ready")
    claimed_value = cast(dict[str, JsonValue], claimed.value)
    assert claimed_value["durable_tasks"] == [{"idempotency": f"{INSTANCE_ID}:occurrence-2", "state": "running"}]
    assert claimed_value["worker_claims"] == 1

    timeline.activate_fault(
        "history.commit-refuse",
        "scope_reset",
        disposition=FaultDisposition.REFUSE,
        payload={"message": "dst joined scope reset commit refused"},
    )
    timeline.command("scope.reset", {"name": "draft"})
    refused = timeline.observe("joined-reset-refused")
    refused_value = cast(dict[str, JsonValue], refused.value)
    assert refused_value["frontier"] == 11
    assert ScopeReset.__name__ not in cast(list[JsonValue], refused_value["record_types"])
    assert refused_value["durable_tasks"] == claimed_value["durable_tasks"]
    assert refused_value["lifecycle_attempts"] == [
        {"accepted": False, "phase": "scope_reset", "record_types": ["ScopeReset"]}
    ]
    assert refused_value["reset_refusals"] == refused_value["scope_resets"] == 1
    assert refused_value["cancellation_refusals"] == 0
    assert refused_value["status"] == "poisoned"

    stale = timeline
    timeline.crash("joined_scope_reset_commit_refused")
    world.restart()
    timeline = world.timeline()
    recovered = timeline.run_until(
        "joined-reset-recovered",
        lambda observation: cast(dict[str, JsonValue], observation.value)["drive_calls"] == 2,
    )
    recovered_value = cast(dict[str, JsonValue], recovered.value)
    assert recovered_value["frontier"] == 11
    assert recovered_value["record_types"] == refused_value["record_types"]
    assert recovered_value["durable_tasks"] == claimed_value["durable_tasks"]
    assert recovered_value["prepare_calls"] == 1
    assert recovered_value["lifecycle_attempts"] == refused_value["lifecycle_attempts"]

    timeline.command("worker.complete", {})
    completed = timeline.run_until(
        "joined-reset-terminal-recovered",
        lambda observation: (
            cast(list[JsonValue], cast(dict[str, JsonValue], observation.value)["record_types"]).count(
                FiringCompleted.__name__
            )
            == 2
        ),
    )
    completed_value = cast(dict[str, JsonValue], completed.value)
    assert completed_value["frontier"] == 14
    assert completed_value["record_types"][-3:] == ["ActivityCompleted", "TokensProduced", "FiringCompleted"]
    assert completed_value["durable_tasks"] == [{"idempotency": f"{INSTANCE_ID}:occurrence-2", "state": "completed"}]
    assert completed_value["prepare_calls"] == completed_value["worker_claims"] == 1
    assert completed_value["worker_completions"] == completed_value["reset_refusals"] == 1
    assert completed_value["lifecycle_attempts"] == refused_value["lifecycle_attempts"]
    assert completed_value["transaction_attempts"] == [
        {
            "accepted": True,
            "dispatch_attempted": False,
            "record_types": ["ExternalEventDelivered", "FiringBegun", "TokensProduced", "FiringCompleted"],
        },
        {
            "accepted": True,
            "dispatch_attempted": True,
            "record_types": ["CandidateSelected", "FiringBegun", "TokensConsumed", "ActivityRequested"],
        },
        {
            "accepted": True,
            "dispatch_attempted": False,
            "record_types": ["ActivityCompleted"],
        },
        {
            "accepted": True,
            "dispatch_attempted": False,
            "record_types": ["TokensProduced", "FiringCompleted"],
        },
    ]

    timeline.begin_fair()
    timeline.finish(Disposition.QUIESCENT)
    return world, profile, stale


def build_joined_reset_refusal_artifact(dsn: str) -> ScenarioArtifactV3:
    world, _, _ = execute_joined_reset_refusal_story(dsn)
    try:
        artifact = world.artifact(RESET_REFUSAL_SCENARIO_ID)
        assert isinstance(artifact, ScenarioArtifactV3)
        return artifact
    finally:
        world.close()


def execute_joined_reset_ack_loss_story(dsn: str) -> tuple[World, JoinedResetAckLossProfile, Timeline]:
    """Lose the accepted reset acknowledgement, reload, and fence its old Worker."""

    profile = JoinedResetAckLossProfile(dsn)
    world = World(profile, CANCELLATION_WORLD_BUDGET, checkers=(JoinedAcceptedResetAuthorityChecker(),))
    timeline = world.timeline()

    timeline.command("scope.open", {"name": "draft"})
    timeline.command(
        "source.deliver",
        {"identity": "draft-input-3", "scope": "draft", "value": 3},
    )
    ready = timeline.run_until(
        "joined-reset-ack-ready",
        lambda observation: (
            cast(dict[str, JsonValue], observation.value)["durable_tasks"]
            == [{"idempotency": f"{INSTANCE_ID}:occurrence-2", "state": "pending"}]
        ),
    )
    ready_value = cast(dict[str, JsonValue], ready.value)
    assert ready_value["frontier"] == 11
    assert ready_value["prepare_calls"] == 1

    timeline.command("worker.claim", {})
    claimed = timeline.observe("joined-reset-ack-ready")
    claimed_value = cast(dict[str, JsonValue], claimed.value)
    assert claimed_value["durable_tasks"] == [{"idempotency": f"{INSTANCE_ID}:occurrence-2", "state": "running"}]
    assert claimed_value["worker_claims"] == 1

    timeline.activate_fault(
        "history.lose-ack",
        "scope_reset_committed",
        disposition=FaultDisposition.RAISE,
        payload={"message": "dst joined scope reset acknowledgement lost"},
    )
    timeline.command("scope.reset", {"name": "draft"})
    lost = timeline.observe("joined-reset-ack-lost")
    lost_value = cast(dict[str, JsonValue], lost.value)
    assert lost_value["frontier"] == 12
    assert lost_value["record_types"][-1] == ScopeReset.__name__
    assert lost_value["durable_tasks"] == claimed_value["durable_tasks"]
    assert lost_value["lifecycle_attempts"] == [
        {"accepted": True, "phase": "scope_reset", "record_types": ["ScopeReset"]}
    ]
    assert lost_value["reset_ack_losses"] == lost_value["scope_resets"] == 1
    assert lost_value["cancellation_refusals"] == 0
    assert lost_value["status"] == "poisoned"

    stale = timeline
    timeline.crash("joined_scope_reset_committed_ack_lost")
    world.restart()
    timeline = world.timeline()
    recovered = timeline.run_until(
        "joined-reset-ack-recovered",
        lambda observation: (
            cast(dict[str, JsonValue], observation.value)["durable_tasks"]
            == [{"idempotency": f"{INSTANCE_ID}:occurrence-2", "state": "cancelled"}]
        ),
    )
    recovered_value = cast(dict[str, JsonValue], recovered.value)
    assert recovered_value["frontier"] == 12
    assert recovered_value["prepare_calls"] == 1
    assert recovered_value["lifecycle_attempts"] == [
        {"accepted": True, "phase": "scope_reset", "record_types": ["ScopeReset"]},
        {"accepted": True, "phase": "cancellation", "record_types": []},
    ]

    timeline.command("worker.complete-stale", {})
    fenced = timeline.observe("joined-reset-ack-worker-fenced")
    fenced_value = cast(dict[str, JsonValue], fenced.value)
    assert fenced_value["durable_tasks"] == recovered_value["durable_tasks"]
    assert fenced_value["reset_ack_losses"] == fenced_value["stale_worker_refusals"] == 1
    assert ActivityCompleted.__name__ not in cast(list[JsonValue], fenced_value["record_types"])

    timeline.begin_fair()
    timeline.finish(Disposition.QUIESCENT)
    return world, profile, stale


def build_joined_reset_ack_loss_artifact(dsn: str) -> ScenarioArtifactV3:
    world, _, _ = execute_joined_reset_ack_loss_story(dsn)
    try:
        artifact = world.artifact(RESET_ACK_LOSS_SCENARIO_ID)
        assert isinstance(artifact, ScenarioArtifactV3)
        return artifact
    finally:
        world.close()


def execute_joined_cancellation_story(dsn: str) -> tuple[World, JoinedCancellationProfile, Timeline]:
    """Commit reset, refuse its real tombstone, reload, and fence the stale Worker."""

    profile = JoinedCancellationProfile(dsn)
    world = World(profile, CANCELLATION_WORLD_BUDGET, checkers=(JoinedCancellationAuthorityChecker(),))
    timeline = world.timeline()

    timeline.command("scope.open", {"name": "draft"})
    timeline.command(
        "source.deliver",
        {"identity": "draft-input-3", "scope": "draft", "value": 3},
    )
    ready = timeline.run_until(
        "joined-cancellation-ready",
        lambda observation: (
            cast(dict[str, JsonValue], observation.value)["durable_tasks"]
            == [{"idempotency": f"{INSTANCE_ID}:occurrence-2", "state": "pending"}]
        ),
    )
    ready_value = cast(dict[str, JsonValue], ready.value)
    assert ready_value["prepare_calls"] == 1
    assert ready_value["frontier"] == 11

    timeline.command("worker.claim", {})
    claimed = timeline.observe("joined-cancellation-ready")
    claimed_value = cast(dict[str, JsonValue], claimed.value)
    assert claimed_value["durable_tasks"] == [{"idempotency": f"{INSTANCE_ID}:occurrence-2", "state": "running"}]
    assert claimed_value["worker_claims"] == 1

    timeline.activate_fault(
        "history.commit-refuse",
        "cancellation_committed",
        disposition=FaultDisposition.REFUSE,
        payload={"message": "dst joined cancellation commit refused"},
    )
    timeline.command("scope.reset", {"name": "draft"})
    refused = timeline.observe("joined-cancellation-refused")
    refused_value = cast(dict[str, JsonValue], refused.value)
    assert refused_value["frontier"] == 12
    assert refused_value["record_types"][-1] == ScopeReset.__name__
    assert refused_value["durable_tasks"] == claimed_value["durable_tasks"]
    assert refused_value["lifecycle_attempts"] == [
        {"accepted": True, "phase": "scope_reset", "record_types": ["ScopeReset"]},
        {"accepted": False, "phase": "cancellation", "record_types": []},
    ]
    assert refused_value["cancellation_refusals"] == refused_value["scope_resets"] == 1
    assert refused_value["status"] == "poisoned"

    stale = timeline
    timeline.crash("joined_cancellation_commit_refused")
    world.restart()
    timeline = world.timeline()
    recovered = timeline.run_until(
        "joined-cancellation-recovered",
        lambda observation: (
            cast(dict[str, JsonValue], observation.value)["durable_tasks"]
            == [{"idempotency": f"{INSTANCE_ID}:occurrence-2", "state": "cancelled"}]
        ),
    )
    recovered_value = cast(dict[str, JsonValue], recovered.value)
    assert recovered_value["frontier"] == 12
    assert recovered_value["prepare_calls"] == 1
    assert recovered_value["lifecycle_attempts"] == [
        {"accepted": True, "phase": "scope_reset", "record_types": ["ScopeReset"]},
        {"accepted": False, "phase": "cancellation", "record_types": []},
        {"accepted": True, "phase": "cancellation", "record_types": []},
    ]

    timeline.command("worker.complete-stale", {})
    fenced = timeline.observe("joined-late-worker-fenced")
    fenced_value = cast(dict[str, JsonValue], fenced.value)
    assert fenced_value["durable_tasks"] == recovered_value["durable_tasks"]
    assert fenced_value["stale_worker_refusals"] == 1
    assert ActivityCompleted.__name__ not in fenced_value["record_types"]

    timeline.begin_fair()
    timeline.finish(Disposition.QUIESCENT)
    return world, profile, stale


def build_joined_cancellation_artifact(dsn: str) -> ScenarioArtifactV3:
    world, _, _ = execute_joined_cancellation_story(dsn)
    try:
        artifact = world.artifact(CANCELLATION_SCENARIO_ID)
        assert isinstance(artifact, ScenarioArtifactV3)
        return artifact
    finally:
        world.close()


def execute_joined_cancellation_ack_loss_story(
    dsn: str,
) -> tuple[World, JoinedCancellationAckLossProfile, Timeline]:
    """Lose accepted tombstone acknowledgement, reload, and fence the stale Worker."""

    profile = JoinedCancellationAckLossProfile(dsn)
    world = World(profile, CANCELLATION_WORLD_BUDGET, checkers=(JoinedAcceptedCancellationAuthorityChecker(),))
    timeline = world.timeline()

    timeline.command("scope.open", {"name": "draft"})
    timeline.command(
        "source.deliver",
        {"identity": "draft-input-3", "scope": "draft", "value": 3},
    )
    ready = timeline.run_until(
        "joined-cancellation-ack-ready",
        lambda observation: (
            cast(dict[str, JsonValue], observation.value)["durable_tasks"]
            == [{"idempotency": f"{INSTANCE_ID}:occurrence-2", "state": "pending"}]
        ),
    )
    ready_value = cast(dict[str, JsonValue], ready.value)
    assert ready_value["prepare_calls"] == 1
    assert ready_value["frontier"] == 11

    timeline.command("worker.claim", {})
    claimed = timeline.observe("joined-cancellation-ack-ready")
    claimed_value = cast(dict[str, JsonValue], claimed.value)
    assert claimed_value["durable_tasks"] == [{"idempotency": f"{INSTANCE_ID}:occurrence-2", "state": "running"}]
    assert claimed_value["worker_claims"] == 1

    timeline.activate_fault(
        "history.lose-ack",
        "cancellation_committed",
        disposition=FaultDisposition.RAISE,
        payload={"message": "dst joined cancellation acknowledgement lost"},
    )
    timeline.command("scope.reset", {"name": "draft"})
    lost = timeline.observe("joined-cancellation-ack-lost")
    lost_value = cast(dict[str, JsonValue], lost.value)
    assert lost_value["frontier"] == 12
    assert lost_value["record_types"][-1] == ScopeReset.__name__
    assert lost_value["durable_tasks"] == [{"idempotency": f"{INSTANCE_ID}:occurrence-2", "state": "cancelled"}]
    assert lost_value["lifecycle_attempts"] == [
        {"accepted": True, "phase": "scope_reset", "record_types": ["ScopeReset"]},
        {"accepted": True, "phase": "cancellation", "record_types": []},
    ]
    assert lost_value["cancellation_ack_losses"] == lost_value["scope_resets"] == 1
    assert lost_value["status"] == "poisoned"

    stale = timeline
    timeline.crash("joined_cancellation_committed_ack_lost")
    world.restart()
    timeline = world.timeline()
    recovered = timeline.run_until(
        "joined-cancellation-ack-recovered",
        lambda observation: cast(dict[str, JsonValue], observation.value)["drive_calls"] == 2,
    )
    recovered_value = cast(dict[str, JsonValue], recovered.value)
    assert recovered_value["frontier"] == 12
    assert recovered_value["prepare_calls"] == 1
    assert recovered_value["durable_tasks"] == lost_value["durable_tasks"]
    assert recovered_value["lifecycle_attempts"] == lost_value["lifecycle_attempts"]

    timeline.command("worker.complete-stale", {})
    fenced = timeline.observe("joined-cancellation-ack-worker-fenced")
    fenced_value = cast(dict[str, JsonValue], fenced.value)
    assert fenced_value["durable_tasks"] == recovered_value["durable_tasks"]
    assert fenced_value["stale_worker_refusals"] == 1
    assert ActivityCompleted.__name__ not in fenced_value["record_types"]

    timeline.begin_fair()
    timeline.finish(Disposition.QUIESCENT)
    return world, profile, stale


def build_joined_cancellation_ack_loss_artifact(dsn: str) -> ScenarioArtifactV3:
    world, _, _ = execute_joined_cancellation_ack_loss_story(dsn)
    try:
        artifact = world.artifact(CANCELLATION_ACK_LOSS_SCENARIO_ID)
        assert isinstance(artifact, ScenarioArtifactV3)
        return artifact
    finally:
        world.close()
