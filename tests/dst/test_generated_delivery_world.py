"""CV19.DS3 bounded stateful generation over the normalized DST interpreter."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

from hypothesis import event, strategies as st
from hypothesis.stateful import (
    RuleBasedStateMachine,
    initialize,
    invariant,
    precondition,
    rule,
    run_state_machine_as_test,
)
from pydantic import JsonValue

from petrus.testing.dst import (
    ActionDisposition,
    Budget,
    Disposition,
    ScenarioRegistry,
    World,
    replay,
)
from tests.dst.campaign import campaign_settings, record_campaign_case
from tests.dst.delivery_world import DeliveryAuthorityChecker, DeliveryEngineProfile

GENERATED_WORLD_BUDGET = Budget(
    actions=64,
    queued_commands=1,
    timer_advances=0,
    logical_instant=0,
    reloads=16,
    predicate_polls=1,
    artifact_bytes=262_144,
)


class _DeliveryScheduleMachine(RuleBasedStateMachine):
    """Author generated external facts without defining Engine semantics."""

    campaign_profile: str
    required_coverage: frozenset[str] = frozenset()

    def __init__(self) -> None:
        super().__init__()
        self._temporary = TemporaryDirectory(prefix="petrus-generated-delivery-")
        self._root = Path(self._temporary.name)
        self._profile = DeliveryEngineProfile(self._root / "author-history.jsonl")
        self._world = World(
            self._profile,
            GENERATED_WORLD_BUDGET,
            checkers=(DeliveryAuthorityChecker(),),
        )
        self._timeline = self._world.timeline()
        self._accepted: dict[str, int] = {}
        self._poisoned = False
        self._coverage: set[str] = set()
        self._next_identity = 0

    def _deliver(self, identity: str, value: int) -> None:
        if identity not in self._accepted:
            expected = ActionDisposition.APPLIED
            self._accepted[identity] = value
        elif self._accepted[identity] == value:
            expected = ActionDisposition.IDEMPOTENT
        else:
            expected = ActionDisposition.REFUSED_EXPECTED
            self._poisoned = True

        result = self._timeline.command("source.deliver", {"identity": identity, "value": value})

        assert result.disposition == expected.value
        label = f"delivery:{expected.value}"
        self._coverage.add(label)
        event(label)

    def _crash_reload(self, cut: str) -> None:
        previous_generation = self._timeline.generation
        self._timeline.crash(cut)
        next_generation = self._world.restart()
        self._timeline = self._world.timeline()
        self._poisoned = False

        assert next_generation > previous_generation
        self._coverage.update(("lifecycle:crash", "lifecycle:reload"))
        event("lifecycle:crash-reload")

    @invariant()
    def detached_history_agrees_with_the_external_authority_model(self) -> None:
        observation = self._timeline.observe("engine.delivery-authority")
        value = cast(dict[str, JsonValue], observation.value)
        canonical = cast(list[dict[str, JsonValue]], value["canonical_deliveries"])

        assert [(entry["identity"], entry["value"]) for entry in canonical] == list(self._accepted.items())
        assert value["marking_values"] == list(self._accepted.values())

    def teardown(self) -> None:
        try:
            if self._poisoned:
                self._crash_reload("generated-conflict-recovery")
            self._timeline.finish(Disposition.EXTERNAL_WAIT)
            artifact = self._world.artifact("generated-identified-delivery-world-v3")
            assert self.required_coverage <= self._coverage

            registry = ScenarioRegistry()
            registry.register_profile(DeliveryEngineProfile(self._root / "replay-history.jsonl"))
            registry.register_checker(DeliveryAuthorityChecker())
            result = replay(artifact, registry)

            assert result.outcome == "pass"
            assert result.disposition == Disposition.EXTERNAL_WAIT.value
            assert result.operations == len(artifact.operations)
            assert result.journal_digest == artifact.expected.journal_digest
            record_campaign_case(self.campaign_profile, artifact)
        finally:
            self._world.close()
            self._temporary.cleanup()


class BroadDeliveryScheduleMachine(_DeliveryScheduleMachine):
    """Preserve independent identity and payload dimensions with little structure."""

    campaign_profile = "delivery-broad"

    @precondition(lambda self: not self._poisoned)
    @rule(
        identity=st.sampled_from(("broad-event-1", "broad-event-2", "broad-event-3")),
        value=st.integers(min_value=-1, max_value=1),
    )
    def deliver(self, identity: str, value: int) -> None:
        self._deliver(identity, value)

    @precondition(lambda self: not self._poisoned)
    @rule()
    def crash_and_reload(self) -> None:
        self._crash_reload("broad-generated-delivery-boundary")

    @precondition(lambda self: self._poisoned)
    @rule()
    def recover_from_identity_conflict(self) -> None:
        self._crash_reload("broad-generated-conflict")


class FocusedDeliveryScheduleMachine(_DeliveryScheduleMachine):
    """Exercise redelivery conflicts and recovery in every targeted example."""

    campaign_profile = "delivery-focused"
    required_coverage = frozenset(
        {
            "delivery:applied",
            "delivery:idempotent",
            "delivery:refused_expected",
            "lifecycle:crash",
            "lifecycle:reload",
        }
    )

    @initialize(value=st.integers(min_value=-1, max_value=1))
    def establish_targeted_boundary_coverage(self, value: int) -> None:
        self._deliver("focused-event-1", value)
        self._deliver("focused-event-1", value)
        self._deliver("focused-event-1", value + 1)
        self._crash_reload("focused-generated-conflict")

    @precondition(lambda self: not self._poisoned)
    @rule(data=st.data())
    def exact_redelivery(self, data: st.DataObject) -> None:
        identity = data.draw(st.sampled_from(tuple(self._accepted)), label="exact-redelivery-identity")
        self._deliver(identity, self._accepted[identity])

    @precondition(lambda self: not self._poisoned)
    @rule(data=st.data())
    def conflicting_redelivery(self, data: st.DataObject) -> None:
        identity = data.draw(st.sampled_from(tuple(self._accepted)), label="conflict-identity")
        self._deliver(identity, self._accepted[identity] + 1)

    @precondition(lambda self: not self._poisoned)
    @rule(value=st.integers(min_value=-2, max_value=2))
    def distinct_delivery(self, value: int) -> None:
        self._next_identity += 1
        self._deliver(f"focused-new-{self._next_identity}", value)

    @precondition(lambda self: not self._poisoned)
    @rule()
    def crash_and_reload(self) -> None:
        self._crash_reload("focused-generated-delivery-boundary")

    @precondition(lambda self: self._poisoned)
    @rule()
    def recover_from_identity_conflict(self) -> None:
        self._crash_reload("focused-generated-conflict")


def test_broad_generated_delivery_schedules_replay_exactly() -> None:
    run_state_machine_as_test(
        BroadDeliveryScheduleMachine,
        settings=campaign_settings("delivery-broad"),
    )


def test_focused_generated_delivery_schedules_cover_high_value_boundaries_and_replay_exactly() -> None:
    run_state_machine_as_test(
        FocusedDeliveryScheduleMachine,
        settings=campaign_settings("delivery-focused"),
    )
