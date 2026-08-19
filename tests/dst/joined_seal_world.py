"""Joined source-seal transaction fault profiles and recovery stories."""

from __future__ import annotations

from typing import cast

import psycopg
from pydantic import JsonValue

from petrus.impetus.binding import HandlerResult
from petrus.impetus.history import (
    ActivityCompleted,
    ActivityRequested,
    CandidateSelected,
    DeliveryRegistration,
    DeliveryRegistrationClosed,
    DeliveryRegistrationOpened,
    FiringBegun,
    FiringCompleted,
    InstanceCreated,
    TokensConsumed,
    TokensInitialized,
    TokensProduced,
)
from petrus.impetus.history_store.postgres import PostgresHistoryStore
from petrus.impetus.petrinet import Arc, Net, Place, Transition
from petrus.testing.dst import (
    ActionDisposition,
    ApplyResult,
    CheckResult,
    CheckerIdentity,
    Command,
    Disposition,
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
from tests.dst.joined_world import (
    DONE,
    INPUT,
    INSTANCE_ID,
    PROJECT,
    SOURCE,
    WORLD_BUDGET,
    JoinedBridge,
    JoinedGeneration,
    JoinedProjectionProfile,
)

SUBSCRIPTION_KEY = "subscription"
REFUSAL_SCENARIO_ID = "joined-seal-commit-refusal-world-v3"
ACK_LOSS_SCENARIO_ID = "joined-seal-ack-loss-world-v3"

REFUSAL_PROFILE_IDENTITY = ProfileIdentity(
    name="petrus.engine.joined-seal-commit-refusal",
    version=1,
    digest=digest_json(
        {
            "commands": ["engine.drive", "source.seal", "worker.claim", "worker.complete"],
            "fault": {
                "disposition": "refuse",
                "name": "history.commit-refuse",
                "target": "source_sealed",
            },
            "instance": INSTANCE_ID,
            "observations": [
                "engine.joined-seal-authority",
                "joined-seal-ready",
                "joined-seal-refused",
                "joined-seal-reloaded",
                "joined-seal-recovered",
            ],
            "provider": "petrus.engine.absurd",
            "property": "a refused runtime-policy close-all leaves every source registration armed",
            "source": str(SOURCE),
        }
    ),
)
ACK_LOSS_PROFILE_IDENTITY = ProfileIdentity(
    name="petrus.engine.joined-seal-ack-loss",
    version=1,
    digest=digest_json(
        {
            "commands": ["engine.drive", "source.seal", "worker.claim", "worker.complete"],
            "fault": {
                "disposition": "raise",
                "name": "history.lose-ack",
                "target": "source_sealed_committed",
            },
            "instance": INSTANCE_ID,
            "observations": [
                "engine.joined-seal-authority",
                "joined-seal-ack-lost",
                "joined-seal-ack-recovered",
                "joined-seal-ready",
            ],
            "provider": "petrus.engine.absurd",
            "property": "accepted runtime-policy close-all survives loss of its commit acknowledgement",
            "source": str(SOURCE),
        }
    ),
)
CHECKER_IDENTITY = CheckerIdentity(
    name="petrus.engine.joined-seal-authority",
    version=1,
    digest=digest_json(
        {
            "property": (
                "accepted PostgreSQL source-seal transactions alone close every canonical registration and "
                "remove the public delivery door"
            )
        }
    ),
)


def seal_application_net() -> Net:
    return Net(
        places=[Place(INPUT), Place(DONE)],
        transitions=[Transition(PROJECT, handler="bridge"), Transition(SOURCE)],
        arcs=[Arc(INPUT, PROJECT), Arc(PROJECT, DONE), Arc(SOURCE, DONE)],
        name="dst-world-joined-seal",
    )


class JoinedSealBridge(JoinedBridge):
    """Projection which adds a second registration before runtime policy seals."""

    def project(self, binding, result) -> HandlerResult:
        return HandlerResult(
            super().project(binding, result),
            opens=(DeliveryRegistration(SOURCE, SUBSCRIPTION_KEY),),
        )


class JoinedSealRefusalProfile(JoinedProjectionProfile):
    """Refuse the close-all transaction for a source with two armed keys."""

    identity = REFUSAL_PROFILE_IDENTITY
    fault_name = "history.commit-refuse"
    fault_target = "source_sealed"
    fault_disposition = FaultDisposition.REFUSE
    observations = {
        "engine.joined-seal-authority",
        "joined-seal-ready",
        "joined-seal-refused",
        "joined-seal-reloaded",
        "joined-seal-recovered",
    }
    observation_fields = (
        "canonical_registrations",
        "drive_calls",
        "durable_tasks",
        "engine_armed",
        "frontier",
        "lifecycle_attempts",
        "prepare_calls",
        "record_types",
        "seal_ack_losses",
        "seal_calls",
        "seal_refusals",
        "status",
        "transaction_attempts",
        "worker_completions",
    )

    def __init__(self, dsn: str) -> None:
        super().__init__(dsn)
        self.seal_calls = 0

    def validate(self, command: Command) -> Command:
        if command.name == "source.seal" and command.payload == {}:
            return command
        return super().validate(command)

    def load(self, context: ScenarioContext) -> GenerationStart[JoinedGeneration]:
        del context
        return GenerationStart(self._open(create=False), ())

    def apply(
        self,
        generation: JoinedGeneration,
        command: Command,
        context: ScenarioContext,
    ) -> ApplyResult:
        if command.name != "source.seal":
            return super().apply(generation, command, context)
        expected = self._configure_faults(generation, context)
        try:
            generation.engine.seal(SOURCE)
        except OSError as error:
            if str(error) not in expected:
                raise
            generation.poisoned = True
            self.seal_calls += 1
            return ApplyResult(
                disposition=ActionDisposition.REFUSED_EXPECTED.value,
                value={"error": str(error), "frontier": self._frontier()},
                scheduled=[],
            )
        self.seal_calls += 1
        return ApplyResult(
            disposition=ActionDisposition.APPLIED.value,
            value={"frontier": self._frontier(), "source": str(SOURCE)},
            scheduled=[],
        )

    def observe(
        self,
        generation: JoinedGeneration,
        request: ObservationRequest,
        context: ScenarioContext,
    ) -> JsonValue:
        del context
        if request.name not in self.observations:
            raise ValueError(f"unknown joined-seal observation {request.name!r}")
        if request.payload not in (None, {}):
            raise ValueError("joined-seal observations do not accept parameters")
        state = self._observation_state(generation)
        return {field: state[field] for field in self.observation_fields}

    def _arm_refusal(self, generation: JoinedGeneration, message: str) -> None:
        generation.connection.refuse_seal_commit(message)

    def _handler(self) -> JoinedBridge:
        return JoinedSealBridge(self._prepared)

    def _net(self) -> Net:
        return seal_application_net()

    def _observation_state(self, generation: JoinedGeneration) -> dict[str, JsonValue]:
        state = super()._observation_state(generation)
        with psycopg.connect(self.dsn, autocommit=True) as probe:
            records = PostgresHistoryStore(probe, INSTANCE_ID).records
        registrations: list[JsonValue] = []
        for record in records:
            if isinstance(record, (DeliveryRegistrationOpened, DeliveryRegistrationClosed)):
                registrations.append(
                    {
                        "kind": "opened" if isinstance(record, DeliveryRegistrationOpened) else "closed",
                        "key": record.key,
                        "occurrence": record.occurrence,
                        "source": str(record.source),
                    }
                )
        if generation.poisoned:
            engine_armed: JsonValue = None
        else:
            current = generation.engine.snapshot()["current"]
            assert isinstance(current, dict)
            engine_armed = cast(JsonValue, current["armed"])
        state.update(
            {
                "canonical_registrations": registrations,
                "engine_armed": engine_armed,
                "lifecycle_attempts": self.lifecycle_attempts,
                "seal_calls": self.seal_calls,
            }
        )
        return state


class JoinedSealAckLossProfile(JoinedSealRefusalProfile):
    """Lose acknowledgement after accepting the source close-all batch."""

    identity = ACK_LOSS_PROFILE_IDENTITY
    fault_name = "history.lose-ack"
    fault_target = "source_sealed_committed"
    fault_disposition = FaultDisposition.RAISE
    observations = {
        "engine.joined-seal-authority",
        "joined-seal-ready",
        "joined-seal-ack-lost",
        "joined-seal-ack-recovered",
    }

    def _arm_refusal(self, generation: JoinedGeneration, message: str) -> None:
        generation.connection.lose_seal_commit_ack(message)


class JoinedSealAuthorityChecker:
    """Independent close-all authority from PostgreSQL transaction and History facts."""

    identity = CHECKER_IDENTITY
    request = ObservationRequest(name="engine.joined-seal-authority", payload={})

    def check(self, observation: Observation) -> CheckResult:
        value = cast(dict[str, JsonValue], observation.value)
        attempts = cast(list[dict[str, JsonValue]], value["transaction_attempts"])
        lifecycle_attempts = cast(list[dict[str, JsonValue]], value["lifecycle_attempts"])
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
            "record_types": ["TokensProduced", "DeliveryRegistrationOpened", "FiringCompleted"],
        }
        expected_attempts = [begin, terminal, projection]
        attempts_exact = len(attempts) <= len(expected_attempts) and attempts == expected_attempts[: len(attempts)]
        refused_seal = {
            "accepted": False,
            "phase": "source_seal",
            "record_types": ["DeliveryRegistrationClosed", "DeliveryRegistrationClosed"],
        }
        accepted_seal = {**refused_seal, "accepted": True}
        lifecycle_exact = lifecycle_attempts in (
            [],
            [refused_seal],
            [refused_seal, accepted_seal],
            [accepted_seal],
        )
        accepted_begin = attempts.count(begin)
        accepted_terminal = attempts.count(terminal)
        accepted_projection = attempts.count(projection)
        accepted_seals = lifecycle_attempts.count(accepted_seal)
        refused_seals = lifecycle_attempts.count(refused_seal)

        expected_records: list[JsonValue] = [
            InstanceCreated.__name__,
            TokensInitialized.__name__,
            DeliveryRegistrationOpened.__name__,
        ]
        if accepted_begin:
            expected_records.extend(
                [
                    CandidateSelected.__name__,
                    FiringBegun.__name__,
                    TokensConsumed.__name__,
                    ActivityRequested.__name__,
                ]
            )
        if accepted_terminal:
            expected_records.append(ActivityCompleted.__name__)
        if accepted_projection:
            expected_records.extend(
                [
                    TokensProduced.__name__,
                    DeliveryRegistrationOpened.__name__,
                    FiringCompleted.__name__,
                ]
            )
        if accepted_seals:
            expected_records.extend([DeliveryRegistrationClosed.__name__, DeliveryRegistrationClosed.__name__])

        expected_registrations: list[JsonValue] = [
            {"key": "default", "kind": "opened", "occurrence": None, "source": "source"}
        ]
        if accepted_projection:
            expected_registrations.append(
                {"key": SUBSCRIPTION_KEY, "kind": "opened", "occurrence": 1, "source": "source"}
            )
        if accepted_seals:
            expected_registrations.extend(
                [
                    {"key": "default", "kind": "closed", "occurrence": None, "source": "source"},
                    {"key": SUBSCRIPTION_KEY, "kind": "closed", "occurrence": None, "source": "source"},
                ]
            )
        expected_armed: JsonValue
        if accepted_seals:
            expected_armed = []
        else:
            keys = ["default"]
            if accepted_projection:
                keys.append(SUBSCRIPTION_KEY)
            expected_armed = [{"key": key, "source": "source"} for key in keys]

        tasks = cast(list[dict[str, JsonValue]], value["durable_tasks"])
        expected_key = f"{INSTANCE_ID}:occurrence-1"
        tasks_exact = tasks == [] or tasks in (
            [{"idempotency": expected_key, "state": "pending"}],
            [{"idempotency": expected_key, "state": "running"}],
            [{"idempotency": expected_key, "state": "completed"}],
        )
        completed_custody = tasks == [{"idempotency": expected_key, "state": "completed"}]
        worker_completions = cast(int, value["worker_completions"])
        status = cast(str, value["status"])
        engine_armed = value["engine_armed"]
        expected_status = "terminated" if accepted_seals else "awaiting" if accepted_projection else "running"
        engine_coherent = (status == "poisoned" and engine_armed is None) or (
            status == expected_status and engine_armed == expected_armed
        )
        terminal_coherent = status in {"poisoned", expected_status}
        seal_ack_losses = cast(int, value["seal_ack_losses"])
        passed = (
            attempts_exact
            and lifecycle_exact
            and cast(list[JsonValue], value["record_types"]) == expected_records
            and cast(list[JsonValue], value["canonical_registrations"]) == expected_registrations
            and cast(int, value["frontier"]) == len(expected_records)
            and cast(int, value["prepare_calls"]) == accepted_begin
            and accepted_begin == len(tasks) <= 1
            and accepted_terminal <= worker_completions <= 1
            and accepted_projection <= accepted_terminal
            and accepted_seals <= accepted_projection
            and cast(int, value["seal_calls"]) == len(lifecycle_attempts)
            and refused_seals == cast(int, value["seal_refusals"]) <= 1
            and 0 <= seal_ack_losses <= accepted_seals <= 1
            and not (refused_seals and seal_ack_losses)
            and completed_custody == (worker_completions == 1)
            and tasks_exact
            and engine_coherent
            and terminal_coherent
        )
        return CheckResult(
            passed=passed,
            detail={
                "accepted_seals": accepted_seals,
                "ack_losses": seal_ack_losses,
                "attempts_exact": attempts_exact,
                "canonical_registrations": value["canonical_registrations"],
                "engine_coherent": engine_coherent,
                "lifecycle_exact": lifecycle_exact,
                "refused_seals": refused_seals,
                "tasks_exact": tasks_exact,
                "terminal_coherent": terminal_coherent,
            },
        )


def _prepare_two_registrations(timeline: Timeline) -> dict[str, JsonValue]:
    timeline.command("engine.drive", {})
    timeline.command("worker.claim", {})
    timeline.command("worker.complete", {"result": {"value": 3}})
    timeline.command("engine.drive", {})
    ready = cast(dict[str, JsonValue], timeline.observe("joined-seal-ready").value)
    assert ready["engine_armed"] == [
        {"key": "default", "source": "source"},
        {"key": SUBSCRIPTION_KEY, "source": "source"},
    ]
    assert ready["status"] == "awaiting"
    return ready


def execute_joined_seal_refusal_story(
    dsn: str,
) -> tuple[World, JoinedSealRefusalProfile, Timeline]:
    """Refuse close-all, load both keys, and explicitly retry once."""

    profile = JoinedSealRefusalProfile(dsn)
    world = World(profile, WORLD_BUDGET, checkers=(JoinedSealAuthorityChecker(),))
    timeline = world.timeline()
    _prepare_two_registrations(timeline)

    timeline.activate_fault(
        "history.commit-refuse",
        "source_sealed",
        disposition=FaultDisposition.REFUSE,
        payload={"message": "dst joined source seal commit refused"},
    )
    refused_result = timeline.command("source.seal", {})
    assert refused_result.disposition == ActionDisposition.REFUSED_EXPECTED.value
    refused = cast(dict[str, JsonValue], timeline.observe("joined-seal-refused").value)
    assert refused["frontier"] == 11
    assert refused["canonical_registrations"][-1] == {
        "key": SUBSCRIPTION_KEY,
        "kind": "opened",
        "occurrence": 1,
        "source": "source",
    }
    assert refused["engine_armed"] is None
    assert refused["seal_calls"] == refused["seal_refusals"] == 1

    stale = timeline
    timeline.crash("joined_source_seal_commit_refused")
    world.restart()
    timeline = world.timeline()
    reloaded = timeline.run_until(
        "joined-seal-reloaded",
        lambda observation: (
            cast(dict[str, JsonValue], observation.value)["engine_armed"]
            == [
                {"key": "default", "source": "source"},
                {"key": SUBSCRIPTION_KEY, "source": "source"},
            ]
        ),
    )
    assert cast(dict[str, JsonValue], reloaded.value)["status"] == "awaiting"
    timeline.command("source.seal", {})
    recovered = cast(dict[str, JsonValue], timeline.observe("joined-seal-recovered").value)
    assert recovered["frontier"] == 13
    assert recovered["engine_armed"] == []
    assert recovered["record_types"][-2:] == ["DeliveryRegistrationClosed", "DeliveryRegistrationClosed"]
    assert recovered["seal_calls"] == 2
    assert recovered["status"] == "terminated"

    timeline.finish(Disposition.CONVERGED)
    return world, profile, stale


def build_joined_seal_refusal_artifact(dsn: str) -> ScenarioArtifactV3:
    world, _, _ = execute_joined_seal_refusal_story(dsn)
    try:
        artifact = world.artifact(REFUSAL_SCENARIO_ID)
        assert isinstance(artifact, ScenarioArtifactV3)
        return artifact
    finally:
        world.close()


def execute_joined_seal_ack_loss_story(
    dsn: str,
) -> tuple[World, JoinedSealAckLossProfile, Timeline]:
    """Lose close-all acknowledgement and reconstruct the closed source."""

    profile = JoinedSealAckLossProfile(dsn)
    world = World(profile, WORLD_BUDGET, checkers=(JoinedSealAuthorityChecker(),))
    timeline = world.timeline()
    _prepare_two_registrations(timeline)

    timeline.activate_fault(
        "history.lose-ack",
        "source_sealed_committed",
        disposition=FaultDisposition.RAISE,
        payload={"message": "dst joined source seal acknowledgement lost"},
    )
    lost_result = timeline.command("source.seal", {})
    assert lost_result.disposition == ActionDisposition.REFUSED_EXPECTED.value
    lost = cast(dict[str, JsonValue], timeline.observe("joined-seal-ack-lost").value)
    assert lost["frontier"] == 13
    assert lost["engine_armed"] is None
    assert lost["seal_ack_losses"] == lost["seal_calls"] == 1
    assert lost["seal_refusals"] == 0

    stale = timeline
    timeline.crash("joined_source_seal_committed_ack_lost")
    world.restart()
    timeline = world.timeline()
    recovered = timeline.run_until(
        "joined-seal-ack-recovered",
        lambda observation: cast(dict[str, JsonValue], observation.value)["engine_armed"] == [],
    )
    recovered_value = cast(dict[str, JsonValue], recovered.value)
    assert recovered_value["frontier"] == 13
    assert recovered_value["canonical_registrations"] == lost["canonical_registrations"]
    assert recovered_value["lifecycle_attempts"] == lost["lifecycle_attempts"]
    assert recovered_value["seal_calls"] == 1
    assert recovered_value["status"] == "terminated"

    timeline.finish(Disposition.CONVERGED)
    return world, profile, stale


def build_joined_seal_ack_loss_artifact(dsn: str) -> ScenarioArtifactV3:
    world, _, _ = execute_joined_seal_ack_loss_story(dsn)
    try:
        artifact = world.artifact(ACK_LOSS_SCENARIO_ID)
        assert isinstance(artifact, ScenarioArtifactV3)
        return artifact
    finally:
        world.close()
