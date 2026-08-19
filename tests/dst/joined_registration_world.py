"""Joined handler-registration projection fault profiles and recovery stories."""

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
    TokensInitialized,
)
from petrus.impetus.history_store.postgres import PostgresHistoryStore
from petrus.impetus.petrinet import Arc, Net, Place, Transition
from petrus.testing.dst import (
    CheckResult,
    CheckerIdentity,
    Disposition,
    FaultDisposition,
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
    QUEUE,
    SOURCE,
    WORLD_BUDGET,
    JoinedBridge,
    JoinedGeneration,
    JoinedProjectionProfile,
)

REPLACEMENT_KEY = "replacement"
REFUSAL_SCENARIO_ID = "joined-registration-projection-commit-refusal-world-v3"
ACK_LOSS_SCENARIO_ID = "joined-registration-projection-ack-loss-world-v3"

REFUSAL_PROFILE_IDENTITY = ProfileIdentity(
    name="petrus.engine.joined-registration-projection-commit-refusal",
    version=1,
    digest=digest_json(
        {
            "commands": ["engine.drive", "worker.claim", "worker.complete"],
            "effect": {
                "close": {"key": "default", "source": "source"},
                "open": {"key": REPLACEMENT_KEY, "source": "source"},
            },
            "fault": {
                "disposition": "refuse",
                "name": "history.commit-refuse",
                "target": "projection_committed",
            },
            "instance": INSTANCE_ID,
            "observations": [
                "engine.joined-registration-projection-authority",
                "joined-registration-projection-refused",
                "joined-registration-projection-recovered",
            ],
            "provider": "petrus.engine.absurd",
            "property": "handler registration close/open effects commit with projection or vanish together",
            "queue": QUEUE,
        }
    ),
)
ACK_LOSS_PROFILE_IDENTITY = ProfileIdentity(
    name="petrus.engine.joined-registration-projection-ack-loss",
    version=1,
    digest=digest_json(
        {
            "commands": ["engine.drive", "worker.claim", "worker.complete"],
            "effect": {
                "close": {"key": "default", "source": "source"},
                "open": {"key": REPLACEMENT_KEY, "source": "source"},
            },
            "fault": {
                "disposition": "raise",
                "name": "history.lose-ack",
                "target": "projection_committed",
            },
            "instance": INSTANCE_ID,
            "observations": [
                "engine.joined-registration-projection-authority",
                "joined-registration-projection-ack-lost",
                "joined-registration-projection-ack-recovered",
            ],
            "provider": "petrus.engine.absurd",
            "property": "accepted handler registration effects survive loss of projection acknowledgement",
            "queue": QUEUE,
        }
    ),
)
CHECKER_IDENTITY = CheckerIdentity(
    name="petrus.engine.joined-registration-projection-authority",
    version=1,
    digest=digest_json(
        {
            "property": (
                "accepted PostgreSQL projection transactions alone replace the default source registration with "
                "the handler-authored registration"
            )
        }
    ),
)


def registration_application_net() -> Net:
    return Net(
        places=[Place(INPUT), Place(DONE)],
        transitions=[Transition(PROJECT, handler="bridge"), Transition(SOURCE)],
        arcs=[Arc(INPUT, PROJECT), Arc(PROJECT, DONE), Arc(SOURCE, DONE)],
        name="dst-world-joined-registration-projection",
    )


class JoinedRegistrationBridge(JoinedBridge):
    """Projection which atomically replaces one source registration."""

    def project(self, binding, result) -> HandlerResult:
        return HandlerResult(
            super().project(binding, result),
            closes=(DeliveryRegistration(SOURCE, "default"),),
            opens=(DeliveryRegistration(SOURCE, REPLACEMENT_KEY),),
        )


class JoinedRegistrationProjectionProfile(JoinedProjectionProfile):
    """Refuse the projection batch containing handler registration effects."""

    identity = REFUSAL_PROFILE_IDENTITY
    refused_observation = "joined-registration-projection-refused"
    recovered_observation = "joined-registration-projection-recovered"
    observations = {
        "engine.joined-registration-projection-authority",
        refused_observation,
        recovered_observation,
    }
    observation_fields = (
        "canonical_registrations",
        "drive_calls",
        "durable_tasks",
        "engine_armed",
        "frontier",
        "prepare_calls",
        "projection_ack_losses",
        "projection_refusals",
        "record_types",
        "status",
        "transaction_attempts",
        "worker_completions",
    )

    def observe(
        self,
        generation: JoinedGeneration,
        request: ObservationRequest,
        context: ScenarioContext,
    ) -> JsonValue:
        del context
        if request.name not in self.observations:
            raise ValueError(f"unknown joined-registration observation {request.name!r}")
        if request.payload not in (None, {}):
            raise ValueError("joined-registration observations do not accept parameters")
        state = self._observation_state(generation)
        return {field: state[field] for field in self.observation_fields}

    def _handler(self) -> JoinedBridge:
        return JoinedRegistrationBridge(self._prepared)

    def _net(self) -> Net:
        return registration_application_net()

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
            }
        )
        return state


class JoinedRegistrationProjectionAckLossProfile(JoinedRegistrationProjectionProfile):
    """Lose acknowledgement after accepting projection and registration effects."""

    identity = ACK_LOSS_PROFILE_IDENTITY
    fault_name = "history.lose-ack"
    fault_disposition = FaultDisposition.RAISE
    refused_observation = "joined-registration-projection-ack-lost"
    recovered_observation = "joined-registration-projection-ack-recovered"
    observations = {
        "engine.joined-registration-projection-authority",
        refused_observation,
        recovered_observation,
    }
    refusal_field = "projection_ack_losses"

    def _arm_refusal(self, generation: JoinedGeneration, message: str) -> None:
        generation.connection.lose_projection_commit_ack(message)


class JoinedRegistrationProjectionAuthorityChecker:
    """Independent registration authority from transaction and History facts."""

    identity = CHECKER_IDENTITY
    request = ObservationRequest(name="engine.joined-registration-projection-authority", payload={})

    def check(self, observation: Observation) -> CheckResult:
        value = cast(dict[str, JsonValue], observation.value)
        records = cast(list[JsonValue], value["record_types"])
        attempts = cast(list[dict[str, JsonValue]], value["transaction_attempts"])
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
            "record_types": [
                "TokensProduced",
                "DeliveryRegistrationClosed",
                "DeliveryRegistrationOpened",
                "FiringCompleted",
            ],
        }
        projection_accepted = {**projection_refused, "accepted": True}
        attempts_exact = attempts in (
            [],
            [begin],
            [begin, terminal, projection_refused],
            [begin, terminal, projection_refused, projection_accepted],
            [begin, terminal, projection_accepted],
        )
        accepted_begin = attempts.count(begin)
        accepted_terminal = attempts.count(terminal)
        accepted_projection = attempts.count(projection_accepted)
        refused_projection = attempts.count(projection_refused)
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
                    "TokensConsumed",
                    ActivityRequested.__name__,
                ]
            )
        if accepted_terminal:
            expected_records.append(ActivityCompleted.__name__)
        if accepted_projection:
            expected_records.extend(
                [
                    "TokensProduced",
                    DeliveryRegistrationClosed.__name__,
                    DeliveryRegistrationOpened.__name__,
                    FiringCompleted.__name__,
                ]
            )
        expected_registrations: list[JsonValue] = [
            {"key": "default", "kind": "opened", "occurrence": None, "source": "source"}
        ]
        if accepted_projection:
            expected_registrations.extend(
                [
                    {"key": "default", "kind": "closed", "occurrence": 1, "source": "source"},
                    {"key": REPLACEMENT_KEY, "kind": "opened", "occurrence": 1, "source": "source"},
                ]
            )
        expected_armed: JsonValue = [{"key": REPLACEMENT_KEY if accepted_projection else "default", "source": "source"}]
        status = cast(str, value["status"])
        engine_armed = cast(JsonValue, value["engine_armed"])
        engine_coherent = (status == "poisoned" and engine_armed is None) or (
            status != "poisoned" and engine_armed == expected_armed
        )
        tasks = cast(list[dict[str, JsonValue]], value["durable_tasks"])
        worker_completions = cast(int, value["worker_completions"])
        expected_key = f"{INSTANCE_ID}:occurrence-1"
        tasks_exact = tasks == [] or tasks in (
            [{"idempotency": expected_key, "state": "pending"}],
            [{"idempotency": expected_key, "state": "running"}],
            [{"idempotency": expected_key, "state": "completed"}],
        )
        completed_custody = tasks == [{"idempotency": expected_key, "state": "completed"}]
        ack_losses = cast(int, value["projection_ack_losses"])
        passed = (
            attempts_exact
            and records == expected_records
            and cast(list[JsonValue], value["canonical_registrations"]) == expected_registrations
            and cast(int, value["prepare_calls"]) == accepted_begin
            and accepted_begin == len(tasks) <= 1
            and accepted_terminal <= worker_completions <= 1
            and accepted_projection <= accepted_terminal
            and refused_projection == cast(int, value["projection_refusals"]) <= 1
            and 0 <= ack_losses <= accepted_projection <= 1
            and not (refused_projection and ack_losses)
            and completed_custody == (worker_completions == 1)
            and tasks_exact
            and engine_coherent
        )
        return CheckResult(
            passed=passed,
            detail={
                "accepted_projections": accepted_projection,
                "ack_losses": ack_losses,
                "attempts_exact": attempts_exact,
                "canonical_registrations": value["canonical_registrations"],
                "engine_coherent": engine_coherent,
                "refused_projections": refused_projection,
                "tasks_exact": tasks_exact,
            },
        )


def execute_joined_registration_projection_refusal_story(
    dsn: str,
) -> tuple[World, JoinedRegistrationProjectionProfile, Timeline]:
    """Refuse one effectful projection, then load and apply it exactly once."""

    profile = JoinedRegistrationProjectionProfile(dsn)
    world = World(profile, WORLD_BUDGET, checkers=(JoinedRegistrationProjectionAuthorityChecker(),))
    timeline = world.timeline()

    timeline.command("engine.drive", {})
    timeline.command("worker.claim", {})
    timeline.command("worker.complete", {"result": {"value": 3}})
    timeline.activate_fault(
        "history.commit-refuse",
        "projection_committed",
        disposition=FaultDisposition.REFUSE,
        payload={"message": "dst joined registration projection commit refused"},
    )
    timeline.command("engine.drive", {})
    refused = cast(dict[str, JsonValue], timeline.observe("joined-registration-projection-refused").value)
    assert refused["frontier"] == 8
    assert refused["record_types"][-1] == "ActivityCompleted"
    assert refused["canonical_registrations"] == [
        {"key": "default", "kind": "opened", "occurrence": None, "source": "source"}
    ]
    assert refused["engine_armed"] is None
    assert refused["projection_refusals"] == refused["worker_completions"] == 1

    stale = timeline
    timeline.crash("joined_registration_projection_commit_refused")
    world.restart()
    timeline = world.timeline()
    recovered = timeline.run_until(
        "joined-registration-projection-recovered",
        lambda observation: (
            cast(dict[str, JsonValue], observation.value)["engine_armed"]
            == [{"key": REPLACEMENT_KEY, "source": "source"}]
        ),
    )
    recovered_value = cast(dict[str, JsonValue], recovered.value)
    assert recovered_value["frontier"] == 12
    assert recovered_value["record_types"][-4:] == [
        "TokensProduced",
        "DeliveryRegistrationClosed",
        "DeliveryRegistrationOpened",
        "FiringCompleted",
    ]
    assert recovered_value["canonical_registrations"] == [
        {"key": "default", "kind": "opened", "occurrence": None, "source": "source"},
        {"key": "default", "kind": "closed", "occurrence": 1, "source": "source"},
        {"key": REPLACEMENT_KEY, "kind": "opened", "occurrence": 1, "source": "source"},
    ]
    assert recovered_value["status"] == "awaiting"

    timeline.finish(Disposition.EXTERNAL_WAIT)
    return world, profile, stale


def build_joined_registration_projection_refusal_artifact(dsn: str) -> ScenarioArtifactV3:
    world, _, _ = execute_joined_registration_projection_refusal_story(dsn)
    try:
        artifact = world.artifact(REFUSAL_SCENARIO_ID)
        assert isinstance(artifact, ScenarioArtifactV3)
        return artifact
    finally:
        world.close()


def execute_joined_registration_projection_ack_loss_story(
    dsn: str,
) -> tuple[World, JoinedRegistrationProjectionAckLossProfile, Timeline]:
    """Lose effectful projection acknowledgement, then reconstruct exact effects."""

    profile = JoinedRegistrationProjectionAckLossProfile(dsn)
    world = World(profile, WORLD_BUDGET, checkers=(JoinedRegistrationProjectionAuthorityChecker(),))
    timeline = world.timeline()

    timeline.command("engine.drive", {})
    timeline.command("worker.claim", {})
    timeline.command("worker.complete", {"result": {"value": 3}})
    timeline.activate_fault(
        "history.lose-ack",
        "projection_committed",
        disposition=FaultDisposition.RAISE,
        payload={"message": "dst joined registration projection acknowledgement lost"},
    )
    timeline.command("engine.drive", {})
    lost = cast(dict[str, JsonValue], timeline.observe("joined-registration-projection-ack-lost").value)
    assert lost["frontier"] == 12
    assert lost["record_types"][-4:] == [
        "TokensProduced",
        "DeliveryRegistrationClosed",
        "DeliveryRegistrationOpened",
        "FiringCompleted",
    ]
    assert lost["engine_armed"] is None
    assert lost["projection_ack_losses"] == lost["worker_completions"] == 1

    stale = timeline
    timeline.crash("joined_registration_projection_committed_ack_lost")
    world.restart()
    timeline = world.timeline()
    recovered = timeline.run_until(
        "joined-registration-projection-ack-recovered",
        lambda observation: cast(dict[str, JsonValue], observation.value)["drive_calls"] == 3,
    )
    recovered_value = cast(dict[str, JsonValue], recovered.value)
    assert recovered_value["frontier"] == 12
    assert recovered_value["record_types"] == lost["record_types"]
    assert recovered_value["canonical_registrations"] == lost["canonical_registrations"]
    assert recovered_value["engine_armed"] == [{"key": REPLACEMENT_KEY, "source": "source"}]
    assert recovered_value["status"] == "awaiting"
    assert len(recovered_value["transaction_attempts"]) == 3

    timeline.finish(Disposition.EXTERNAL_WAIT)
    return world, profile, stale


def build_joined_registration_projection_ack_loss_artifact(dsn: str) -> ScenarioArtifactV3:
    world, _, _ = execute_joined_registration_projection_ack_loss_story(dsn)
    try:
        artifact = world.artifact(ACK_LOSS_SCENARIO_ID)
        assert isinstance(artifact, ScenarioArtifactV3)
        return artifact
    finally:
        world.close()
