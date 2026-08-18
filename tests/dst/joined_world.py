"""Joined History/Dispatch commit-refusal DST profile and recovery story."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

import psycopg
from psycopg import sql
from pydantic import JsonValue

from petrus.engine import Engine
from petrus.engine.absurd import create_engine, load_engine
from petrus.impetus.history import ActivityRequested, CandidateSelected, FiringBegun
from petrus.impetus.history_store.postgres import PostgresHistoryStore
from petrus.impetus.petrinet import Arc, Marking, Net, NetPath, Place, Token, Transition
from petrus.motus.activity import ActivityInvocation
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

INPUT = NetPath("input")
DONE = NetPath("done")
PROJECT = NetPath("project")
INSTANCE_ID = "dst-world-joined-begin-refusal"
QUEUE = "dst_joined_begin"
SCENARIO_ID = "joined-begin-commit-refusal-world-v3"

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
CHECKER_IDENTITY = CheckerIdentity(
    name="petrus.engine.joined-commit-authority",
    version=1,
    digest=digest_json(
        {"property": ("durable candidate, firing, request, and task counts equal accepted joined begin transactions")}
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


def application_net() -> Net:
    return Net(
        places=[Place(INPUT), Place(DONE)],
        transitions=[Transition(PROJECT, handler="bridge")],
        arcs=[Arc(INPUT, PROJECT), Arc(PROJECT, DONE)],
        name="dst-world-joined-begin-refusal",
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


class CommitRefusingConnection:
    """One provider connection which records and may refuse a joined begin commit."""

    def __init__(self, delegate, attempts: list[dict[str, JsonValue]], refused: Callable[[], None]) -> None:
        self._delegate = delegate
        self._attempts = attempts
        self._refused = refused
        self._record_types: list[str] = []
        self._dispatch_attempted = False
        self._refusal: str | None = None

    def __getattr__(self, name: str):
        return getattr(self._delegate, name)

    @property
    def autocommit(self) -> bool:
        return self._delegate.autocommit

    def execute(self, query, params=None):
        cursor = self._delegate.execute(query, params)
        if (
            isinstance(query, str)
            and query.startswith("INSERT INTO impetus.semantic_events")
            and isinstance(params, tuple)
            and len(params) >= 3
            and isinstance(params[2], str)
        ):
            self._record_types.append(params[2])
        if isinstance(query, str) and query.startswith(
            "SELECT task_id, run_id, attempt, created FROM absurd.spawn_task"
        ):
            self._dispatch_attempted = True
        return cursor

    def refuse_activity_request_commit(self, message: str) -> None:
        if self._refusal is not None:
            raise RuntimeError("joined commit refusal is already armed")
        self._refusal = message

    def commit(self) -> None:
        joined_begin = ActivityRequested.__name__ in self._record_types
        if joined_begin and self._refusal is not None:
            message = self._refusal
            self._refusal = None
            self._attempts.append(self._attempt(False))
            self._refused()
            raise OSError(message)
        self._delegate.commit()
        if joined_begin:
            self._attempts.append(self._attempt(True))
        self._clear_transaction()

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

    def _clear_transaction(self) -> None:
        self._record_types.clear()
        self._dispatch_attempted = False


@dataclass
class JoinedGeneration:
    engine: Engine
    connection: CommitRefusingConnection
    poisoned: bool = False


class JoinedBeginProfile:
    """Public Absurd-Engine profile around one exact joined begin transaction."""

    identity = PROFILE_IDENTITY

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self.transaction_attempts: list[dict[str, JsonValue]] = []
        self.prepare_calls = 0
        self.commit_refusals = 0
        self.drops = 0
        self.closes = 0

    def validate(self, command: Command) -> Command:
        if command.name != "engine.drive" or command.payload != {}:
            raise ValueError("joined-begin profile accepts only engine.drive with an empty payload")
        return command

    def validate_fault(self, fault: Fault) -> Fault:
        if (
            fault.name != "history.commit-refuse"
            or fault.target != "activity_requested"
            or fault.disposition != FaultDisposition.REFUSE.value
            or type(fault.payload) is not dict
            or set(fault.payload) != {"message"}
            or not isinstance(fault.payload["message"], str)
        ):
            raise ValueError("unsupported joined-begin commit fault")
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
            "joined-begin-refused",
            "joined-begin-recovered",
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
                "commit_refusals",
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
        generation.engine.close()

    def close(self, generation: JoinedGeneration) -> None:
        self.closes += 1
        generation.engine.close()

    def _open(self, *, create: bool) -> JoinedGeneration:
        authority = psycopg.connect(self.dsn, autocommit=False)
        connection = CommitRefusingConnection(authority, self.transaction_attempts, self._commit_refused)
        listener = psycopg.connect(self.dsn, autocommit=True)
        bridge = JoinedBridge(self._prepared)
        opener = create_engine if create else load_engine
        engine = opener(
            connection,
            application_net(),
            INSTANCE_ID,
            listen=listener,
            default_queue=QUEUE,
            marking=Marking({INPUT: (Token("Input", 3),)}) if create else None,
            handlers={"bridge": bridge},
        )
        return JoinedGeneration(engine, connection)

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
                "drops": self.drops,
                "durable_tasks": tasks,
                "frontier": len(records),
                "prepare_calls": self.prepare_calls,
                "record_types": [type(record).__name__ for record in records],
                "status": status,
                "transaction_attempts": self.transaction_attempts,
            },
        )

    def _configure_faults(self, generation: JoinedGeneration, context: ScenarioContext) -> tuple[str, ...]:
        expected = []
        for fault in context.faults("activity_requested"):
            if fault.name != "history.commit-refuse" or fault.disposition != FaultDisposition.REFUSE.value:
                raise ValueError(f"unsupported joined-begin fault {fault.name!r}")
            if type(fault.payload) is not dict or set(fault.payload) != {"message"}:
                raise ValueError("history.commit-refuse requires an exact message payload")
            message = fault.payload["message"]
            if not isinstance(message, str):
                raise ValueError("history.commit-refuse message must be a string")
            generation.connection.refuse_activity_request_commit(message)
            expected.append(message)
        return tuple(expected)

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
