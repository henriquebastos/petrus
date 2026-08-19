"""CV19.DS3 cross-layer generated runtime campaign."""

from __future__ import annotations

from copy import deepcopy
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

from petrus.testing.dst import ActionDisposition, Disposition, FaultDisposition, ScenarioRegistry, World, replay
from tests.dst.campaign import campaign_settings, record_campaign_case
from tests.dst.generated_runtime_world import (
    SCENARIO_ID,
    GeneratedRuntimeAuthorityChecker,
    GeneratedRuntimeProfile,
    SCOPE_NAME,
    WORLD_BUDGET,
    build_generated_runtime_artifact,
    execute_generated_runtime_story,
)


def test_cross_layer_runtime_story_is_exact_and_replayable(tmp_path: Path) -> None:
    artifact = build_generated_runtime_artifact(
        tmp_path / "runtime-author.jsonl",
        tmp_path / "runtime-author.db",
    )

    assert artifact.scenario_id == SCENARIO_ID
    assert artifact.version == 4
    assert artifact.api == "petrus.testing.dst/v4"
    assert artifact.budget.profile_resources == WORLD_BUDGET.profile_resources
    assert artifact.expected.disposition == Disposition.EXTERNAL_WAIT.value
    assert [operation.cut for operation in artifact.operations if operation.kind == "crash"] == [
        "generated_dispatch_refused",
        "generated_projection_refused",
    ]
    assert [operation.fault.name for operation in artifact.operations if operation.kind == "activate_fault"] == [
        "dispatch.refuse",
        "history.refuse",
    ]
    assert artifact.operations[-1].instant == 5

    registry = ScenarioRegistry()
    registry.register_profile(
        GeneratedRuntimeProfile(
            tmp_path / "runtime-replay.jsonl",
            tmp_path / "runtime-replay.db",
        )
    )
    registry.register_checker(GeneratedRuntimeAuthorityChecker())
    result = replay(artifact, registry)

    assert result.outcome == "pass"
    assert result.disposition == Disposition.EXTERNAL_WAIT.value
    assert result.operations == len(artifact.operations)
    assert result.journal_digest == artifact.expected.journal_digest


def test_cross_layer_checker_rejects_independent_authority_divergence(tmp_path: Path) -> None:
    world, _ = execute_generated_runtime_story(
        tmp_path / "runtime-checker.jsonl",
        tmp_path / "runtime-checker.db",
        finish=False,
    )
    try:
        observation = world.timeline().observe("generated-runtime-state")
        value = cast(dict[str, JsonValue], observation.value)
        mutations = {
            "replay_exact": lambda changed: changed.update(live_marking=[]),
            "in_flight_exact": lambda changed: changed.update(
                live_in_flight=[{"occurrence": 99, "phase": "activity_pending"}]
            ),
            "history_writer_valid": lambda changed: cast(list[JsonValue], changed["record_occurrences"]).append(
                {"kind": "Phantom", "occurrence": 99}
            ),
            "invocation_stable": lambda changed: cast(list[dict[str, JsonValue]], changed["dispatch_attempts"])[
                0
            ].update(idempotency="changed-invocation"),
            "delivery_acknowledgements": lambda changed: cast(list[dict[str, JsonValue]], changed["delivery_attempts"])[
                1
            ].update(disposition="applied"),
            "lifecycle_exact": lambda changed: changed.update(live_scopes={SCOPE_NAME: 99}),
            "projection_exact": lambda changed: cast(list[JsonValue], changed["projection_attempts"]).append(
                {"accepted": True, "record_types": ["FiringCompleted"]}
            ),
            "timer_exact": lambda changed: changed.update(timer_maturations=[]),
        }

        assert GeneratedRuntimeAuthorityChecker().check(observation).passed is True
        for property_name, mutate in mutations.items():
            changed = deepcopy(value)
            mutate(changed)
            result = GeneratedRuntimeAuthorityChecker().check(observation.model_copy(update={"value": changed}))
            assert result.passed is False
            assert result.detail[property_name] is False

        stateful_checker = GeneratedRuntimeAuthorityChecker()
        assert stateful_checker.check(observation).passed is True
        changed = deepcopy(value)
        first_occurrence = cast(list[JsonValue], changed["completed_occurrences"])[0]
        attempts = cast(list[dict[str, JsonValue]], changed["worker_attempts"])
        attempts.append(deepcopy(next(attempt for attempt in attempts if attempt["occurrence"] == first_occurrence)))
        result = stateful_checker.check(observation.model_copy(update={"value": changed}))
        assert result.passed is False
        assert result.detail["frozen_execution"] is False
    finally:
        world.close()


class _ReplayableRuntimeMachine(RuleBasedStateMachine):
    """Common fresh-object artifact replay and detached-authority checks."""

    campaign_profile: str

    def __init__(self) -> None:
        super().__init__()
        self._temporary = TemporaryDirectory(prefix="petrus-generated-runtime-")
        self._root = Path(self._temporary.name)
        self._world: World | None = None
        self._profile: GeneratedRuntimeProfile | None = None
        self._timeline = None
        self._accepted: dict[str, int] = {}

    @invariant()
    def detached_delivery_authority_remains_exact(self) -> None:
        if self._timeline is None:
            return
        observation = self._timeline.observe("generated-runtime-state")
        value = cast(dict[str, JsonValue], observation.value)
        canonical = cast(list[dict[str, JsonValue]], value["canonical_deliveries"])
        assert [(entry["identity"], entry["value"]) for entry in canonical] == list(self._accepted.items())

    def _install(self, world: World, profile: GeneratedRuntimeProfile) -> None:
        self._world = world
        self._profile = profile
        self._timeline = world.timeline()

    def _drain(self) -> None:
        assert self._world is not None
        while self._world.pending():
            self._world.step()

    def _crash_reload(self, cut: str) -> None:
        assert self._world is not None
        assert self._timeline is not None
        previous = self._timeline.generation
        self._timeline.crash(cut)
        generation = self._world.restart()
        self._timeline = self._world.timeline()
        assert generation > previous

    def teardown(self) -> None:
        if self._world is None or self._profile is None or self._timeline is None:
            self._temporary.cleanup()
            return
        try:
            self._drain()
            self._timeline.finish(Disposition.EXTERNAL_WAIT)
            artifact = self._world.artifact("generated-runtime-state-machine-v4")

            registry = ScenarioRegistry()
            registry.register_profile(
                GeneratedRuntimeProfile(
                    self._root / "replay-history.jsonl",
                    self._root / "replay-dispatch.db",
                )
            )
            registry.register_checker(GeneratedRuntimeAuthorityChecker())
            result = replay(artifact, registry)

            assert result.outcome == "pass"
            assert result.disposition == Disposition.EXTERNAL_WAIT.value
            assert result.operations == len(artifact.operations)
            assert result.journal_digest == artifact.expected.journal_digest
            record_campaign_case(self.campaign_profile, artifact)
        finally:
            self._world.close()
            self._temporary.cleanup()


class FocusedRuntimeScheduleMachine(_ReplayableRuntimeMachine):
    """Guarantee every high-value cross-layer dimension in every example."""

    campaign_profile = "runtime-focused"

    @initialize(
        first_value=st.integers(min_value=-3, max_value=3),
        second_value=st.integers(min_value=-3, max_value=3),
        retry_error=st.sampled_from(("worker unavailable", "lease interrupted")),
    )
    def establish_cross_layer_spine(self, first_value: int, second_value: int, retry_error: str) -> None:
        world, profile = execute_generated_runtime_story(
            self._root / "author-history.jsonl",
            self._root / "author-dispatch.db",
            first_value=first_value,
            second_value=second_value,
            retry_error=retry_error,
            finish=False,
        )
        self._install(world, profile)
        self._accepted = {
            "generated-event-1": first_value,
            "generated-event-2": second_value,
        }
        event("runtime:two-fault-cross-layer-spine")

    @precondition(lambda self: self._profile is not None and self._profile.drops < 4)
    @rule()
    def reload_quiescent_runtime(self) -> None:
        self._crash_reload("focused_generated_quiescent_cut")
        self._drain()
        event("runtime:extra-crash-reload")

    @rule()
    def inspect_detached_runtime(self) -> None:
        assert self._timeline is not None
        observation = self._timeline.observe("generated-runtime-state")
        assert cast(dict[str, JsonValue], observation.value)["status"] in {"awaiting", "running", "completed"}


class BroadRuntimeScheduleMachine(_ReplayableRuntimeMachine):
    """Vary faults, retry, cut placement, and terminal fencing with little global structure."""

    campaign_profile = "runtime-broad"

    def __init__(self) -> None:
        super().__init__()
        profile = GeneratedRuntimeProfile(
            self._root / "author-history.jsonl",
            self._root / "author-dispatch.db",
        )
        world = World(profile, WORLD_BUDGET, checkers=(GeneratedRuntimeAuthorityChecker(),))
        self._install(world, profile)
        self._activities = 0
        self._reset = False

    @initialize()
    def open_runtime_scope(self) -> None:
        assert self._timeline is not None
        self._timeline.command("scope.open", {"name": SCOPE_NAME})

    @precondition(lambda self: self._activities < 2)
    @rule(
        value=st.integers(min_value=-2, max_value=2),
        dispatch_fault=st.booleans(),
        crash_after_request=st.booleans(),
        retry=st.booleans(),
        projection_fault=st.booleans(),
        reset_before_terminal=st.booleans(),
    )
    def run_one_external_activity(
        self,
        value: int,
        dispatch_fault: bool,
        crash_after_request: bool,
        retry: bool,
        projection_fault: bool,
        reset_before_terminal: bool,
    ) -> None:
        assert self._world is not None
        assert self._profile is not None
        assert self._timeline is not None
        identity = f"broad-runtime-event-{self._activities + 1}"
        request_count = self._activities
        accepted_dispatches = sum(cast(bool, attempt["accepted"]) for attempt in self._profile.dispatch_attempts)
        work_firings_before = self._work_firing_count()

        use_dispatch_fault = dispatch_fault and self._profile.drops < WORLD_BUDGET.reloads
        if use_dispatch_fault:
            self._timeline.activate_fault(
                "dispatch.refuse",
                "activity_requested",
                disposition=FaultDisposition.REFUSE,
                payload={"message": f"broad dispatch refusal {self._activities + 1}"},
            )
        self._timeline.command("source.deliver", {"identity": identity, "value": value})
        self._accepted[identity] = value

        if use_dispatch_fault:
            refused = self._world.step()
            assert refused.result.disposition == ActionDisposition.REFUSED_EXPECTED.value
            self._crash_reload("broad_generated_dispatch_refusal")
            event("runtime:fault-dispatch")

        self._timeline.run_until(
            "generated-runtime-state",
            lambda observation: (
                len(
                    cast(
                        list[JsonValue],
                        cast(dict[str, JsonValue], observation.value)["requested_invocations"],
                    )
                )
                == request_count + 1
                and sum(
                    cast(bool, attempt["accepted"])
                    for attempt in cast(
                        list[dict[str, JsonValue]],
                        cast(dict[str, JsonValue], observation.value)["dispatch_attempts"],
                    )
                )
                >= accepted_dispatches + 1
            ),
        )
        if crash_after_request and self._profile.drops < WORLD_BUDGET.reloads:
            self._crash_reload("broad_generated_requested_cut")
            self._world.step()
            event("runtime:cut-after-request")

        first = self._timeline.command("worker.claim", {})
        assert cast(dict[str, JsonValue], first.value)["attempt"]["epoch"] == 1
        if retry:
            self._timeline.command("worker.fail", {"attempt": 1, "error": "broad generated retry"})
            second = self._timeline.command("worker.claim", {})
            assert cast(dict[str, JsonValue], second.value)["attempt"]["epoch"] == 2
            event("runtime:worker-retry")

        use_reset = reset_before_terminal and not self._reset
        if use_reset:
            self._timeline.command("scope.reset", {"name": SCOPE_NAME})
            self._reset = True
        self._timeline.command("worker.complete", {"result": {"value": value}})

        use_projection_fault = projection_fault and not use_reset and self._profile.drops < WORLD_BUDGET.reloads
        if use_projection_fault:
            self._timeline.activate_fault(
                "history.refuse",
                "projection_committed",
                disposition=FaultDisposition.REFUSE,
                payload={"message": f"broad projection refusal {self._activities + 1}"},
            )
            refused = self._timeline.command("engine.drive", {})
            assert refused.disposition == ActionDisposition.REFUSED_EXPECTED.value
            self._crash_reload("broad_generated_projection_refusal")
            event("runtime:fault-projection")
        else:
            self._timeline.command("engine.drive", {})

        if use_reset:
            expected_occurrence = cast(dict[str, JsonValue], first.value)["attempt"]["occurrence"]
            terminal = self._timeline.observe("generated-runtime-state")
            assert expected_occurrence in cast(
                list[JsonValue],
                cast(dict[str, JsonValue], terminal.value)["quarantined_occurrences"],
            )
            event("runtime:late-terminal-quarantine")
        else:
            self._timeline.run_until(
                "generated-runtime-state",
                lambda observation: self._observed_work_firings(observation) == work_firings_before + 1,
            )

        self._activities += 1
        self._drain()
        event("runtime:activity-converged")

    @precondition(lambda self: self._profile is not None and self._profile.drops == 0)
    @rule()
    def crash_between_external_facts(self) -> None:
        self._crash_reload("broad_generated_quiescent_cut")
        self._drain()
        event("runtime:quiescent-crash")

    @precondition(lambda self: bool(self._accepted) and not self._reset)
    @rule(data=st.data())
    def redeliver_external_fact(self, data: st.DataObject) -> None:
        assert self._timeline is not None
        identity = data.draw(st.sampled_from(tuple(self._accepted)), label="runtime-redelivery")
        result = self._timeline.command(
            "source.deliver",
            {"identity": identity, "value": self._accepted[identity]},
        )
        assert result.disposition == ActionDisposition.IDEMPOTENT.value
        self._drain()

    @rule()
    def inspect_runtime_without_advancing_it(self) -> None:
        assert self._timeline is not None
        observation = self._timeline.observe("generated-runtime-state")
        assert cast(dict[str, JsonValue], observation.value)["status"] in {"awaiting", "running", "completed"}

    def _work_firing_count(self) -> int:
        assert self._timeline is not None
        return self._observed_work_firings(self._timeline.observe("generated-runtime-state"))

    @staticmethod
    def _observed_work_firings(observation) -> int:
        value = cast(dict[str, JsonValue], observation.value)
        return sum(
            firing["transition"] == "work" for firing in cast(list[dict[str, JsonValue]], value["firing_completed"])
        )


def test_focused_generated_runtime_schedules_replay_exactly() -> None:
    run_state_machine_as_test(
        FocusedRuntimeScheduleMachine,
        settings=campaign_settings("runtime-focused"),
    )


def test_broad_generated_runtime_schedules_replay_exactly() -> None:
    run_state_machine_as_test(
        BroadRuntimeScheduleMachine,
        settings=campaign_settings("runtime-broad"),
    )
