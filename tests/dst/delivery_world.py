"""Public-Engine DST profile for identified source delivery and redelivery."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, cast

from pydantic import JsonValue

from petrus.engine import Engine
from petrus.impetus.history import ExternalEventDelivered, FiringCompleted
from petrus.impetus.history_store import JsonlHistoryStore
from petrus.impetus.instance import PriorAcknowledgement
from petrus.impetus.petrinet import Arc, Net, NetPath, Place, Token, Transition
from petrus.motus.dispatch import InMemoryDispatch
from petrus.testing.dst import (
    ActionDisposition,
    ApplyResult,
    Budget,
    CheckResult,
    CheckerIdentity,
    Command,
    Disposition,
    Fault,
    GenerationStart,
    Observation,
    ObservationRequest,
    ProfileIdentity,
    ScenarioArtifact,
    ScenarioContext,
    World,
    digest_json,
)

SOURCE = NetPath("source")
OUTPUT = NetPath("output")
INSTANCE_ID = "dst-world-identified-delivery"
SCENARIO_ID = "identified-delivery-redelivery-world-v3"

PROFILE_IDENTITY = ProfileIdentity(
    name="petrus.engine.identified-delivery",
    version=1,
    digest=digest_json(
        {
            "commands": {"source.deliver": ["identity", "value"]},
            "instance": INSTANCE_ID,
            "net": {"output": "output", "source": "source"},
            "observations": [
                "conflict-recovered",
                "conflict-refused",
                "delivery-accepted",
                "distinct-identity-accepted",
                "engine.delivery-authority",
                "redelivery-stable",
            ],
        }
    ),
)
CHECKER_IDENTITY = CheckerIdentity(
    name="petrus.engine.delivery-authority",
    version=1,
    digest=digest_json(
        {
            "properties": [
                "one canonical delivery per accepted external identity",
                "exact redelivery is idempotent and changed content is refused",
                "distinct identities preserve equal payloads as distinct facts",
            ]
        }
    ),
)
WORLD_BUDGET = Budget(
    actions=24,
    queued_commands=1,
    timer_advances=0,
    logical_instant=0,
    reloads=2,
    predicate_polls=8,
    artifact_bytes=262_144,
)


def application_net() -> Net:
    return Net(
        places=[Place(OUTPUT)],
        transitions=[Transition(SOURCE)],
        arcs=[Arc(SOURCE, OUTPUT)],
        name="dst-world-identified-delivery",
    )


class WorldClock:
    def __init__(self, context: ScenarioContext):
        self.context = context

    def now(self) -> int:
        return self.context.now()

    def observe(self, instant: int) -> int | None:
        return self.context.now() if self.context.now() >= instant else None


@dataclass
class DeliveryGeneration:
    engine: Engine
    history: JsonlHistoryStore
    marking_values: list[JsonValue]
    status: str
    poisoned: bool = False


class DeliveryEngineProfile:
    """Opaque public Engine plus authored external-delivery attempts."""

    identity = PROFILE_IDENTITY
    _debug_fields = (
        "canonical_deliveries",
        "delivery_attempts",
        "firing_completed",
        "frontier",
        "marking_values",
        "status",
    )
    observation_fields: ClassVar[dict[str, tuple[str, ...]]] = {
        "conflict-recovered": _debug_fields,
        "conflict-refused": _debug_fields,
        "delivery-accepted": _debug_fields,
        "distinct-identity-accepted": _debug_fields,
        "engine.delivery-authority": (
            "canonical_deliveries",
            "delivery_attempts",
            "firing_completed",
            "marking_values",
        ),
        "redelivery-stable": _debug_fields,
    }

    def __init__(self, history_path: Path):
        self.history_path = history_path
        self.delivery_attempts: list[dict[str, JsonValue]] = []
        self.drops = 0
        self.closes = 0

    def validate(self, command: Command) -> Command:
        if command.name != "source.deliver":
            raise ValueError(f"unknown delivery Engine profile command {command.name!r}")
        payload = command.payload
        if type(payload) is not dict or set(payload) != {"identity", "value"}:
            raise ValueError("source.deliver requires exact identity and value fields")
        if not isinstance(payload["identity"], str) or not payload["identity"]:
            raise ValueError("source.deliver identity must be a non-empty string")
        if isinstance(payload["value"], bool) or not isinstance(payload["value"], int):
            raise ValueError("source.deliver value must be an integer")
        return command

    def validate_fault(self, fault: Fault) -> Fault:
        raise ValueError(f"delivery Engine profile has no fault named {fault.name!r}")

    def create(self, context: ScenarioContext) -> GenerationStart[DeliveryGeneration]:
        return GenerationStart(self._generation(context, load=False))

    def load(self, context: ScenarioContext) -> GenerationStart[DeliveryGeneration]:
        return GenerationStart(self._generation(context, load=True))

    def apply(
        self,
        generation: DeliveryGeneration,
        command: Command,
        context: ScenarioContext,
    ) -> ApplyResult:
        del context
        payload = cast(dict[str, JsonValue], command.payload)
        identity = cast(str, payload["identity"])
        value = cast(int, payload["value"])
        try:
            outcome = generation.engine.deliver(
                SOURCE,
                Token("External", value),
                identity=identity,
            )
        except ValueError as error:
            if "identity conflict" not in str(error):
                raise
            generation.poisoned = True
            disposition = ActionDisposition.REFUSED_EXPECTED
        else:
            disposition = (
                ActionDisposition.IDEMPOTENT if isinstance(outcome, PriorAcknowledgement) else ActionDisposition.APPLIED
            )
            self._refresh(generation)
        attempt = cast(
            dict[str, JsonValue],
            {"disposition": disposition.value, "identity": identity, "value": value},
        )
        self.delivery_attempts.append(attempt)
        return ApplyResult(
            disposition=disposition.value,
            value={"attempt": attempt, "frontier": len(generation.history)},
            scheduled=[],
        )

    def observe(
        self,
        generation: DeliveryGeneration,
        request: ObservationRequest,
        context: ScenarioContext,
    ) -> JsonValue:
        del context
        if request.name not in self.observation_fields:
            raise ValueError(f"unknown delivery Engine profile observation {request.name!r}")
        if request.payload not in (None, {}):
            raise ValueError("delivery Engine profile observations do not accept parameters")
        state = self._observation_state(generation)
        return {field: state[field] for field in self.observation_fields[request.name]}

    def drop(self, generation: DeliveryGeneration) -> None:
        self.drops += 1
        generation.engine.close()

    def close(self, generation: DeliveryGeneration) -> None:
        self.closes += 1
        generation.engine.close()

    def _generation(self, context: ScenarioContext, *, load: bool) -> DeliveryGeneration:
        history = JsonlHistoryStore(self.history_path)
        factory = Engine.load if load else Engine.create
        engine = factory(
            application_net(),
            INSTANCE_ID,
            history=history,
            dispatch=InMemoryDispatch(),
            clock=WorldClock(context),
        )
        generation = DeliveryGeneration(engine, history, [], "")
        self._refresh(generation)
        return generation

    def _observation_state(self, generation: DeliveryGeneration) -> dict[str, JsonValue]:
        if not generation.poisoned:
            self._refresh(generation)
        records = generation.history.records
        deliveries = [
            {
                "identity": record.identity,
                "occurrence": record.occurrence,
                "value": record.tokens[0].data,
            }
            for record in records
            if isinstance(record, ExternalEventDelivered)
        ]
        return cast(
            dict[str, JsonValue],
            {
                "canonical_deliveries": deliveries,
                "delivery_attempts": self.delivery_attempts,
                "firing_completed": sum(isinstance(record, FiringCompleted) for record in records),
                "frontier": len(records),
                "marking_values": generation.marking_values,
                "status": "poisoned" if generation.poisoned else generation.status,
            },
        )

    @staticmethod
    def _refresh(generation: DeliveryGeneration) -> None:
        generation.marking_values = [token.data for token in generation.engine.marking.place(OUTPUT)]
        generation.status = generation.engine.status.value


class DeliveryAuthorityChecker:
    """Derive accepted delivery authority only from authored external attempts."""

    identity = CHECKER_IDENTITY
    request = ObservationRequest(name="engine.delivery-authority", payload={})

    def check(self, observation: Observation) -> CheckResult:
        value = cast(dict[str, JsonValue], observation.value)
        attempts = cast(list[dict[str, JsonValue]], value["delivery_attempts"])
        canonical = cast(list[dict[str, JsonValue]], value["canonical_deliveries"])
        accepted: dict[str, JsonValue] = {}
        expected_deliveries: list[dict[str, JsonValue]] = []
        expected_dispositions: list[str] = []
        for attempt in attempts:
            identity = cast(str, attempt["identity"])
            payload = attempt["value"]
            if identity not in accepted:
                accepted[identity] = payload
                expected_deliveries.append({"identity": identity, "value": payload})
                expected_dispositions.append(ActionDisposition.APPLIED.value)
            elif accepted[identity] == payload:
                expected_dispositions.append(ActionDisposition.IDEMPOTENT.value)
            else:
                expected_dispositions.append(ActionDisposition.REFUSED_EXPECTED.value)

        actual_deliveries = [{"identity": delivery["identity"], "value": delivery["value"]} for delivery in canonical]
        reported_dispositions = [cast(str, attempt["disposition"]) for attempt in attempts]
        expected_values = [delivery["value"] for delivery in expected_deliveries]
        firing_completed = cast(int, value["firing_completed"])
        marking_values = cast(list[JsonValue], value["marking_values"])
        passed = (
            actual_deliveries == expected_deliveries
            and reported_dispositions == expected_dispositions
            and firing_completed == len(expected_deliveries)
            and marking_values == expected_values
        )
        return CheckResult(
            passed=passed,
            detail={
                "actual_deliveries": actual_deliveries,
                "expected_deliveries": expected_deliveries,
                "expected_dispositions": expected_dispositions,
                "firing_completed": firing_completed,
                "marking_values": marking_values,
                "reported_dispositions": reported_dispositions,
            },
        )


def execute_delivery_story(history_path: Path) -> tuple[World, DeliveryEngineProfile]:
    """Accept an identity, crash, then acknowledge/refuse exact redeliveries."""

    profile = DeliveryEngineProfile(history_path)
    world = World(profile, WORLD_BUDGET, checkers=(DeliveryAuthorityChecker(),))
    timeline = world.timeline()

    accepted = timeline.command("source.deliver", {"identity": "event-3", "value": 3})
    assert accepted.disposition == ActionDisposition.APPLIED.value
    first = timeline.run_until(
        "delivery-accepted",
        lambda observation: len(cast(dict[str, JsonValue], observation.value)["canonical_deliveries"]) == 1,
    )
    first_value = cast(dict[str, JsonValue], first.value)
    assert first_value["marking_values"] == [3]
    accepted_frontier = first_value["frontier"]

    timeline.crash("source_delivery_committed_before_redelivery")
    world.restart()
    timeline = world.timeline()

    duplicate = timeline.command("source.deliver", {"identity": "event-3", "value": 3})
    assert duplicate.disposition == ActionDisposition.IDEMPOTENT.value
    stable = timeline.observe("redelivery-stable")
    stable_value = cast(dict[str, JsonValue], stable.value)
    assert stable_value["frontier"] == accepted_frontier
    assert stable_value["marking_values"] == [3]

    distinct = timeline.command("source.deliver", {"identity": "event-3-copy", "value": 3})
    assert distinct.disposition == ActionDisposition.APPLIED.value
    preserved = timeline.run_until(
        "distinct-identity-accepted",
        lambda observation: len(cast(dict[str, JsonValue], observation.value)["canonical_deliveries"]) == 2,
    )
    preserved_value = cast(dict[str, JsonValue], preserved.value)
    assert preserved_value["marking_values"] == [3, 3]
    assert preserved_value["status"] == "awaiting"
    distinct_frontier = preserved_value["frontier"]

    conflict = timeline.command("source.deliver", {"identity": "event-3", "value": 4})
    assert conflict.disposition == ActionDisposition.REFUSED_EXPECTED.value
    refused = timeline.observe("conflict-refused")
    refused_value = cast(dict[str, JsonValue], refused.value)
    assert refused_value["frontier"] == distinct_frontier
    assert refused_value["marking_values"] == [3, 3]
    assert refused_value["status"] == "poisoned"

    timeline.crash("source_identity_conflict_before_reload")
    world.restart()
    timeline = world.timeline()
    recovered_duplicate = timeline.command("source.deliver", {"identity": "event-3-copy", "value": 3})
    assert recovered_duplicate.disposition == ActionDisposition.IDEMPOTENT.value
    recovered = timeline.observe("conflict-recovered")
    recovered_value = cast(dict[str, JsonValue], recovered.value)
    assert recovered_value["frontier"] == distinct_frontier
    assert recovered_value["marking_values"] == [3, 3]
    assert recovered_value["status"] == "awaiting"

    timeline.finish(Disposition.EXTERNAL_WAIT)
    return world, profile


def build_delivery_artifact(history_path: Path) -> ScenarioArtifact:
    world, _ = execute_delivery_story(history_path)
    try:
        return world.artifact(SCENARIO_ID)
    finally:
        world.close()
