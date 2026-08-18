"""Joined initial-creation transaction-fault DST profiles and recovery stories."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import psycopg
from pydantic import JsonValue

from petrus.engine import Engine
from petrus.engine.absurd import create_engine, load_engine
from petrus.impetus.history import InstanceCreated, TokensInitialized
from petrus.impetus.history_store.postgres import PostgresHistoryStore
from petrus.impetus.petrinet import Marking, Net, NetPath, Place, Token
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
    Timeline,
    World,
    digest_json,
)

INPUT = NetPath("input")
INSTANCE_ID = "dst-world-joined-creation"
QUEUE = "dst_joined_creation"
REFUSAL_SCENARIO_ID = "joined-creation-commit-refusal-world-v3"
ACK_LOSS_SCENARIO_ID = "joined-creation-ack-loss-world-v3"

REFUSAL_PROFILE_IDENTITY = ProfileIdentity(
    name="petrus.engine.joined-creation-commit-refusal",
    version=1,
    digest=digest_json(
        {
            "commands": ["engine.create"],
            "fault": {
                "disposition": "refuse",
                "name": "history.commit-refuse",
                "target": "instance_created",
            },
            "instance": INSTANCE_ID,
            "observations": [
                "engine.joined-creation-authority",
                "joined-creation-absent",
                "joined-creation-recovered",
                "joined-creation-refused",
            ],
            "provider": "petrus.engine.absurd",
            "property": "a refused initial creation transaction leaves no canonical instance or marking",
            "queue": QUEUE,
        }
    ),
)
ACK_LOSS_PROFILE_IDENTITY = ProfileIdentity(
    name="petrus.engine.joined-creation-ack-loss",
    version=1,
    digest=digest_json(
        {
            "commands": ["engine.create"],
            "fault": {
                "disposition": "raise",
                "name": "history.lose-ack",
                "target": "instance_created_committed",
            },
            "instance": INSTANCE_ID,
            "observations": [
                "engine.joined-creation-authority",
                "joined-creation-ack-lost",
                "joined-creation-ack-recovered",
            ],
            "provider": "petrus.engine.absurd",
            "property": "an accepted initial creation survives loss of its commit acknowledgement",
            "queue": QUEUE,
        }
    ),
)
CHECKER_IDENTITY = CheckerIdentity(
    name="petrus.engine.joined-creation-authority",
    version=1,
    digest=digest_json(
        {
            "property": (
                "accepted PostgreSQL creation transactions alone authorize one InstanceCreated identity and "
                "initial marking"
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
    predicate_polls=4,
    artifact_bytes=131_072,
)


def creation_net() -> Net:
    return Net(
        places=[Place(INPUT)],
        transitions=[],
        arcs=[],
        name="dst-world-joined-creation",
    )


class JoinedCreationFaultConnection:
    """Provider connection that exposes one exact initial-creation commit cut."""

    def __init__(self, delegate, attempts: list[dict[str, JsonValue]]) -> None:
        self._delegate = delegate
        self._attempts = attempts
        self._record_types: list[str] = []
        self._commit_refusal: str | None = None
        self._commit_ack_loss: str | None = None

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
        return cursor

    def refuse_creation_commit(self, message: str) -> None:
        if self._commit_refusal is not None:
            raise RuntimeError("joined creation commit refusal is already armed")
        self._commit_refusal = message

    def lose_creation_commit_ack(self, message: str) -> None:
        if self._commit_ack_loss is not None:
            raise RuntimeError("joined creation acknowledgement loss is already armed")
        self._commit_ack_loss = message

    def commit(self) -> None:
        creation = InstanceCreated.__name__ in self._record_types
        if creation and self._commit_refusal is not None:
            message = self._commit_refusal
            self._commit_refusal = None
            self._attempts.append(self._attempt(False))
            raise OSError(message)
        self._delegate.commit()
        if creation:
            self._attempts.append(self._attempt(True))
        self._record_types.clear()
        if creation and self._commit_ack_loss is not None:
            message = self._commit_ack_loss
            self._commit_ack_loss = None
            raise OSError(message)

    def rollback(self) -> None:
        try:
            self._delegate.rollback()
        finally:
            self._record_types.clear()

    def close(self) -> None:
        self._delegate.close()

    def _attempt(self, accepted: bool) -> dict[str, JsonValue]:
        return {"accepted": accepted, "record_types": list(self._record_types)}


@dataclass
class JoinedCreationGeneration:
    engine: Engine | None = None


class JoinedCreationProfile:
    """Opaque host generation which creates or loads only through public Engine doors."""

    identity = REFUSAL_PROFILE_IDENTITY
    fault_name = "history.commit-refuse"
    fault_target = "instance_created"
    fault_disposition = FaultDisposition.REFUSE
    observations = {
        "engine.joined-creation-authority",
        "joined-creation-absent",
        "joined-creation-recovered",
        "joined-creation-refused",
    }

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self.transaction_attempts: list[dict[str, JsonValue]] = []
        self.creation_attempts: list[dict[str, JsonValue]] = []
        self.commit_refusals = 0
        self.commit_ack_losses = 0
        self.drops = 0
        self.closes = 0

    def validate(self, command: Command) -> Command:
        if command.name != "engine.create" or command.payload != {}:
            raise ValueError("joined-creation profile accepts only engine.create with an empty payload")
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
            raise ValueError(f"unsupported joined-creation fault for {self.identity.name}")
        return fault

    def create(self, context: ScenarioContext) -> GenerationStart[JoinedCreationGeneration]:
        del context
        return GenerationStart(JoinedCreationGeneration(), ())

    def load(self, context: ScenarioContext) -> GenerationStart[JoinedCreationGeneration]:
        del context
        engine = self._open(create=False) if self._frontier() else None
        return GenerationStart(JoinedCreationGeneration(engine), ())

    def apply(
        self,
        generation: JoinedCreationGeneration,
        command: Command,
        context: ScenarioContext,
    ) -> ApplyResult:
        del command
        if generation.engine is not None:
            raise RuntimeError("joined creation generation already owns an Engine")
        expected = self._configure_fault(context)
        connection = self._connection()
        for fault, message in expected:
            if fault.name == "history.commit-refuse":
                connection.refuse_creation_commit(message)
            else:
                connection.lose_creation_commit_ack(message)
        try:
            engine = self._open(create=True, connection=connection)
        except OSError as error:
            messages = tuple(message for _, message in expected)
            if str(error) not in messages:
                raise
            disposition = ActionDisposition.REFUSED_EXPECTED
        else:
            generation.engine = engine
            disposition = ActionDisposition.APPLIED
        attempt = cast(
            dict[str, JsonValue],
            {"disposition": disposition.value, "frontier": self._frontier()},
        )
        self.creation_attempts.append(attempt)
        return ApplyResult(disposition=disposition.value, value=attempt, scheduled=[])

    def observe(
        self,
        generation: JoinedCreationGeneration,
        request: ObservationRequest,
        context: ScenarioContext,
    ) -> JsonValue:
        del context
        if request.name not in self.observations:
            raise ValueError(f"unknown joined-creation observation {request.name!r}")
        if request.payload not in (None, {}):
            raise ValueError("joined-creation observations do not accept parameters")
        return self._observation_state(generation)

    def drop(self, generation: JoinedCreationGeneration) -> None:
        self.drops += 1
        self._dispose(generation)

    def close(self, generation: JoinedCreationGeneration) -> None:
        self.closes += 1
        self._dispose(generation)

    def _connection(self) -> JoinedCreationFaultConnection:
        return JoinedCreationFaultConnection(
            psycopg.connect(self.dsn, autocommit=False),
            self.transaction_attempts,
        )

    def _open(
        self,
        *,
        create: bool,
        connection: JoinedCreationFaultConnection | None = None,
    ) -> Engine:
        authority = connection if connection is not None else self._connection()
        listener = psycopg.connect(self.dsn, autocommit=True)
        opener = create_engine if create else load_engine
        return opener(
            authority,
            creation_net(),
            INSTANCE_ID,
            listen=listener,
            default_queue=QUEUE,
            marking=Marking({INPUT: (Token("Initial", 1),)}) if create else None,
        )

    def _frontier(self) -> int:
        with psycopg.connect(self.dsn, autocommit=True) as probe:
            return len(PostgresHistoryStore(probe, INSTANCE_ID))

    def _observation_state(self, generation: JoinedCreationGeneration) -> dict[str, JsonValue]:
        with psycopg.connect(self.dsn, autocommit=True) as probe:
            records = PostgresHistoryStore(probe, INSTANCE_ID).records
        engine_records = (
            [] if generation.engine is None else [type(record).__name__ for record in generation.engine.records]
        )
        engine_tokens: list[JsonValue] = []
        if generation.engine is not None:
            engine_tokens = [token.data for token in generation.engine.marking.place(INPUT)]
        return cast(
            dict[str, JsonValue],
            {
                "canonical_instances": [record.instance for record in records if isinstance(record, InstanceCreated)],
                "canonical_tokens": [
                    token.data for record in records if isinstance(record, TokensInitialized) for token in record.tokens
                ],
                "closes": self.closes,
                "commit_ack_losses": self.commit_ack_losses,
                "commit_refusals": self.commit_refusals,
                "creation_attempts": self.creation_attempts,
                "drops": self.drops,
                "engine_present": generation.engine is not None,
                "engine_record_types": engine_records,
                "engine_tokens": engine_tokens,
                "frontier": len(records),
                "record_types": [type(record).__name__ for record in records],
                "transaction_attempts": self.transaction_attempts,
            },
        )

    def _configure_fault(self, context: ScenarioContext) -> tuple[tuple[Fault, str], ...]:
        expected = []
        for fault in context.faults(self.fault_target):
            if fault.name != self.fault_name or fault.disposition != self.fault_disposition.value:
                raise ValueError(f"unsupported joined-creation fault {fault.name!r}")
            if type(fault.payload) is not dict or set(fault.payload) != {"message"}:
                raise ValueError(f"{self.fault_name} requires an exact message payload")
            message = fault.payload["message"]
            if not isinstance(message, str):
                raise ValueError(f"{self.fault_name} message must be a string")
            if fault.name == "history.commit-refuse":
                self.commit_refusals += 1
            else:
                self.commit_ack_losses += 1
            expected.append((fault, message))
        return tuple(expected)

    def _dispose(self, generation: JoinedCreationGeneration) -> None:
        if generation.engine is not None:
            generation.engine.close()
            generation.engine = None


class JoinedCreationAckLossProfile(JoinedCreationProfile):
    """Public Absurd profile losing acknowledgement after initial creation acceptance."""

    identity = ACK_LOSS_PROFILE_IDENTITY
    fault_name = "history.lose-ack"
    fault_target = "instance_created_committed"
    fault_disposition = FaultDisposition.RAISE
    observations = {
        "engine.joined-creation-authority",
        "joined-creation-ack-lost",
        "joined-creation-ack-recovered",
    }


class JoinedCreationAuthorityChecker:
    """Independent creation authority from PostgreSQL transaction and History facts."""

    identity = CHECKER_IDENTITY
    request = ObservationRequest(name="engine.joined-creation-authority", payload={})

    def check(self, observation: Observation) -> CheckResult:
        value = cast(dict[str, JsonValue], observation.value)
        transactions = cast(list[dict[str, JsonValue]], value["transaction_attempts"])
        creation_attempts = cast(list[dict[str, JsonValue]], value["creation_attempts"])
        refused_transaction = {
            "accepted": False,
            "record_types": ["InstanceCreated", "TokensInitialized"],
        }
        accepted_transaction = {**refused_transaction, "accepted": True}
        transactions_exact = transactions in (
            [],
            [refused_transaction],
            [refused_transaction, accepted_transaction],
            [accepted_transaction],
        )
        accepted = sum(attempt.get("accepted") is True for attempt in transactions)
        refused = sum(attempt.get("accepted") is False for attempt in transactions)
        dispositions = [attempt["disposition"] for attempt in creation_attempts]
        applied = dispositions.count(ActionDisposition.APPLIED.value)
        reported_refused = dispositions.count(ActionDisposition.REFUSED_EXPECTED.value)
        commit_refusals = cast(int, value["commit_refusals"])
        ack_losses = cast(int, value["commit_ack_losses"])
        canonical_types = cast(list[JsonValue], value["record_types"])
        canonical_instances = cast(list[JsonValue], value["canonical_instances"])
        canonical_tokens = cast(list[JsonValue], value["canonical_tokens"])
        engine_present = cast(bool, value["engine_present"])
        drops = cast(int, value["drops"])
        expected_types: list[JsonValue] = ["InstanceCreated", "TokensInitialized"] if accepted else []
        expected_instances: list[JsonValue] = [INSTANCE_ID] if accepted else []
        expected_tokens: list[JsonValue] = [1] if accepted else []
        engine_coherent = (
            (not engine_present and not accepted)
            or (not engine_present and ack_losses == 1 and drops == 0)
            or (
                engine_present
                and cast(list[JsonValue], value["engine_record_types"]) == expected_types
                and cast(list[JsonValue], value["engine_tokens"]) == expected_tokens
            )
        )
        passed = (
            transactions_exact
            and len(transactions) == len(creation_attempts)
            and accepted == applied + ack_losses <= 1
            and refused == commit_refusals <= 1
            and reported_refused == commit_refusals + ack_losses <= 1
            and canonical_types == expected_types
            and canonical_instances == expected_instances
            and canonical_tokens == expected_tokens
            and cast(int, value["frontier"]) == len(expected_types)
            and engine_coherent
        )
        return CheckResult(
            passed=passed,
            detail={
                "accepted_transactions": accepted,
                "ack_losses": ack_losses,
                "canonical_instances": canonical_instances,
                "commit_refusals": commit_refusals,
                "engine_coherent": engine_coherent,
                "refused_transactions": refused,
                "transactions_exact": transactions_exact,
            },
        )


def execute_joined_creation_refusal_story(
    dsn: str,
) -> tuple[World, JoinedCreationProfile, Timeline]:
    """Refuse initial creation, load absence, then create the instance once."""

    profile = JoinedCreationProfile(dsn)
    world = World(profile, WORLD_BUDGET, checkers=(JoinedCreationAuthorityChecker(),))
    timeline = world.timeline()

    timeline.activate_fault(
        "history.commit-refuse",
        "instance_created",
        disposition=FaultDisposition.REFUSE,
        payload={"message": "dst joined creation commit refused"},
    )
    refused_command = timeline.command("engine.create", {})
    assert refused_command.disposition == ActionDisposition.REFUSED_EXPECTED.value
    refused = cast(dict[str, JsonValue], timeline.observe("joined-creation-refused").value)
    assert refused["frontier"] == 0
    assert refused["record_types"] == []
    assert refused["canonical_instances"] == []
    assert refused["canonical_tokens"] == []
    assert refused["engine_present"] is False
    assert refused["commit_refusals"] == 1
    assert refused["commit_ack_losses"] == 0
    assert refused["transaction_attempts"] == [
        {"accepted": False, "record_types": ["InstanceCreated", "TokensInitialized"]}
    ]

    stale = timeline
    timeline.crash("joined_creation_commit_refused")
    world.restart()
    timeline = world.timeline()
    absent = cast(dict[str, JsonValue], timeline.observe("joined-creation-absent").value)
    assert absent["frontier"] == 0
    assert absent["engine_present"] is False

    accepted_command = timeline.command("engine.create", {})
    assert accepted_command.disposition == ActionDisposition.APPLIED.value
    recovered = cast(dict[str, JsonValue], timeline.observe("joined-creation-recovered").value)
    assert recovered["frontier"] == 2
    assert recovered["record_types"] == ["InstanceCreated", "TokensInitialized"]
    assert recovered["canonical_instances"] == [INSTANCE_ID]
    assert recovered["canonical_tokens"] == [1]
    assert recovered["engine_present"] is True
    assert recovered["engine_record_types"] == recovered["record_types"]
    assert recovered["engine_tokens"] == recovered["canonical_tokens"]
    assert recovered["transaction_attempts"] == [
        {"accepted": False, "record_types": ["InstanceCreated", "TokensInitialized"]},
        {"accepted": True, "record_types": ["InstanceCreated", "TokensInitialized"]},
    ]

    timeline.finish(Disposition.EXTERNAL_WAIT)
    return world, profile, stale


def build_joined_creation_refusal_artifact(dsn: str) -> ScenarioArtifactV3:
    world, _, _ = execute_joined_creation_refusal_story(dsn)
    try:
        artifact = world.artifact(REFUSAL_SCENARIO_ID)
        assert isinstance(artifact, ScenarioArtifactV3)
        return artifact
    finally:
        world.close()


def execute_joined_creation_ack_loss_story(
    dsn: str,
) -> tuple[World, JoinedCreationAckLossProfile, Timeline]:
    """Lose accepted creation acknowledgement, then reconstruct without recreating."""

    profile = JoinedCreationAckLossProfile(dsn)
    world = World(profile, WORLD_BUDGET, checkers=(JoinedCreationAuthorityChecker(),))
    timeline = world.timeline()

    timeline.activate_fault(
        "history.lose-ack",
        "instance_created_committed",
        disposition=FaultDisposition.RAISE,
        payload={"message": "dst joined creation acknowledgement lost"},
    )
    lost_command = timeline.command("engine.create", {})
    assert lost_command.disposition == ActionDisposition.REFUSED_EXPECTED.value
    lost = cast(dict[str, JsonValue], timeline.observe("joined-creation-ack-lost").value)
    assert lost["frontier"] == 2
    assert lost["record_types"] == ["InstanceCreated", "TokensInitialized"]
    assert lost["canonical_instances"] == [INSTANCE_ID]
    assert lost["canonical_tokens"] == [1]
    assert lost["engine_present"] is False
    assert lost["commit_refusals"] == 0
    assert lost["commit_ack_losses"] == 1
    assert lost["transaction_attempts"] == [
        {"accepted": True, "record_types": ["InstanceCreated", "TokensInitialized"]}
    ]

    stale = timeline
    timeline.crash("joined_creation_committed_ack_lost")
    world.restart()
    timeline = world.timeline()
    recovered = cast(dict[str, JsonValue], timeline.observe("joined-creation-ack-recovered").value)
    assert recovered["frontier"] == 2
    assert recovered["record_types"] == lost["record_types"]
    assert recovered["canonical_instances"] == lost["canonical_instances"]
    assert recovered["canonical_tokens"] == lost["canonical_tokens"]
    assert recovered["engine_present"] is True
    assert recovered["engine_record_types"] == recovered["record_types"]
    assert recovered["engine_tokens"] == recovered["canonical_tokens"]
    assert recovered["creation_attempts"] == [{"disposition": ActionDisposition.REFUSED_EXPECTED.value, "frontier": 2}]
    assert recovered["transaction_attempts"] == lost["transaction_attempts"]

    timeline.finish(Disposition.EXTERNAL_WAIT)
    return world, profile, stale


def build_joined_creation_ack_loss_artifact(dsn: str) -> ScenarioArtifactV3:
    world, _, _ = execute_joined_creation_ack_loss_story(dsn)
    try:
        artifact = world.artifact(ACK_LOSS_SCENARIO_ID)
        assert isinstance(artifact, ScenarioArtifactV3)
        return artifact
    finally:
        world.close()
