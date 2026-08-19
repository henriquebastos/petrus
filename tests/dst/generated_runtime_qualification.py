"""Fair-liveness, shrinking, and semantic-coverage support for CV19.DS3."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import cast

from pydantic import JsonValue

from petrus.testing.dst import (
    ApplyResult,
    Disposition,
    ProfileIdentity,
    ScenarioArtifact,
    ScenarioContext,
    World,
    digest_json,
)
from tests.dst.generated_runtime_world import (
    CHECKER_IDENTITY,
    MATURATION_INSTANT,
    SCOPE_NAME,
    GeneratedRuntimeAuthorityChecker,
    GeneratedRuntimeProfile,
    RuntimeGeneration,
    WORLD_BUDGET,
)

MINIMIZED_SCENARIO_ID = "generated-runtime-minimized-fair-regression-v4"
BROAD_ONLY_SCENARIO_ID = "generated-runtime-broad-retry-reset-v4"
DISCOVERY_SEED = 19_003

FAIR_BUDGET = WORLD_BUDGET.model_copy(
    update={
        "actions": 28,
        "artifact_bytes": 1_048_576,
    }
)

LIVELOCK_PROFILE_IDENTITY = ProfileIdentity(
    name="petrus.engine.generated-runtime-livelock-mutation",
    version=1,
    digest=digest_json(
        {
            "base_profile": GeneratedRuntimeProfile.identity.model_dump(mode="json"),
            "mutation": "reschedule an otherwise quiescent engine.drive at the same logical instant",
        }
    ),
)


class LivelockMutationProfile(GeneratedRuntimeProfile):
    """Test-only falsification profile which preserves safety but cannot quiesce."""

    identity = LIVELOCK_PROFILE_IDENTITY

    def _drive(self, generation: RuntimeGeneration, context: ScenarioContext) -> ApplyResult:
        result = super()._drive(generation, context)
        value = cast(dict[str, JsonValue], result.value)
        if not result.scheduled and context.now() >= MATURATION_INSTANT and value["status"] == "awaiting":
            return result.model_copy(update={"scheduled": [self._scheduled(context, context.now())]})
        return result


def establish_fair_spine(
    world: World,
    *,
    identity: str,
    value: int,
    retry: bool = False,
    perturbations: Iterable[str] = (),
) -> None:
    """Reach a fault-free fair phase with only profile-owned work retained."""

    timeline = world.timeline()
    timeline.command("scope.open", {"name": SCOPE_NAME})
    timeline.command("source.deliver", {"identity": identity, "value": value})
    timeline.run_until(
        "generated-runtime-state",
        lambda observation: (
            len(cast(list[JsonValue], cast(dict[str, JsonValue], observation.value)["requested_invocations"])) == 1
        ),
    )

    for perturbation in perturbations:
        if perturbation == "observe":
            timeline.observe("generated-runtime-state")
            continue
        if perturbation != "crash_reload":
            raise ValueError(f"unknown fair-spine perturbation {perturbation!r}")
        timeline.crash("generated_fair_spine_cut")
        world.restart()
        timeline = world.timeline()
        while world.pending() and world.pending()[0]["instant"] == world.instant:
            world.step()

    timeline.command("worker.claim", {})
    if retry:
        timeline.command("worker.fail", {"attempt": 1, "error": "generated fair retry"})
        timeline.command("worker.claim", {})
    timeline.command("worker.complete", {"result": {"value": value}})
    timeline.command("engine.drive", {})
    timeline.begin_fair()


def build_minimized_fair_regression_artifact(
    history_path: Path,
    dispatch_path: Path,
    *,
    with_checker: bool = True,
) -> ScenarioArtifact:
    """Promote the mutation's minimized schedule through the unmutated profile."""

    profile = GeneratedRuntimeProfile(history_path, dispatch_path)
    world = World(
        profile,
        FAIR_BUDGET,
        checkers=(GeneratedRuntimeAuthorityChecker(),) if with_checker else (),
        seed=DISCOVERY_SEED,
    )
    try:
        identity = world.choices.identifier("shrink-event")
        timeline = world.timeline()
        timeline.command("scope.open", {"name": SCOPE_NAME})
        timeline.command("source.deliver", {"identity": identity, "value": 0})
        world.step()
        timeline.command("worker.claim", {})
        timeline.command("worker.complete", {"result": {"value": 0}})
        timeline.command("engine.drive", {})
        timeline.begin_fair()
        while world.pending():
            world.step()
        timeline.finish(Disposition.QUIESCENT)
        artifact = world.artifact(MINIMIZED_SCENARIO_ID)
        assert isinstance(artifact, ScenarioArtifact)
        return artifact
    finally:
        world.close()


def build_broad_only_artifact(history_path: Path, dispatch_path: Path) -> ScenarioArtifact:
    """Retain the broad-only retry plus lifecycle-reset terminal combination."""

    profile = GeneratedRuntimeProfile(history_path, dispatch_path)
    world = World(profile, WORLD_BUDGET, checkers=(GeneratedRuntimeAuthorityChecker(),))
    timeline = world.timeline()
    try:
        timeline.command("scope.open", {"name": SCOPE_NAME})
        timeline.command("source.deliver", {"identity": "broad-only-event", "value": 3})
        timeline.run_until(
            "generated-runtime-state",
            lambda observation: (
                len(cast(list[JsonValue], cast(dict[str, JsonValue], observation.value)["requested_invocations"])) == 1
            ),
        )
        timeline.command("worker.claim", {})
        timeline.command("worker.fail", {"attempt": 1, "error": "broad-only retry"})
        retried = timeline.command("worker.claim", {})
        occurrence = cast(dict[str, JsonValue], retried.value)["attempt"]["occurrence"]
        timeline.command("scope.reset", {"name": SCOPE_NAME})
        timeline.command("worker.complete", {"result": {"value": 3}})
        timeline.command("engine.drive", {})
        observed = timeline.observe("generated-runtime-state")
        assert occurrence in cast(
            list[JsonValue], cast(dict[str, JsonValue], observed.value)["quarantined_occurrences"]
        )
        while world.pending():
            world.step()
        timeline.finish(Disposition.EXTERNAL_WAIT)
        artifact = world.artifact(BROAD_ONLY_SCENARIO_ID)
        assert isinstance(artifact, ScenarioArtifact)
        return artifact
    finally:
        world.close()


def semantic_labels(artifact: ScenarioArtifact) -> dict[str, set[str]]:
    """Extract semantic reach from normalized operations and checker results."""

    labels = {
        "events": set(),
        "faults": set(),
        "boundaries": set(),
        "lifecycle": set(),
        "terminals": set(),
        "crash_cuts": set(),
        "recoveries": set(),
        "checker_activations": set(),
        "combinations": set(),
    }
    retried: set[int] = set()
    claimed: int | None = None
    reset_after_claim = False
    previous_crash: str | None = None

    for operation in artifact.operations:
        if operation.kind == "activate_fault":
            labels["faults"].add(f"{operation.fault.name}@{operation.fault.target}")
            continue
        if operation.kind == "crash":
            labels["lifecycle"].add("abrupt-crash")
            labels["crash_cuts"].add(operation.cut)
            previous_crash = operation.cut
            continue
        if operation.kind == "restart":
            labels["lifecycle"].add("fresh-load")
            if previous_crash is not None:
                labels["recoveries"].add(f"{previous_crash}->fresh-load")
                previous_crash = None
            continue
        if operation.kind == "begin_fair":
            labels["lifecycle"].add("fair-phase")
            continue
        if operation.kind == "finish":
            labels["terminals"].add(operation.disposition)
            continue
        if operation.kind != "execute":
            continue

        name = operation.command.name
        labels["events"].add(name)
        labels["boundaries"].add(f"action:{operation.result.disposition}")
        if operation.instant == MATURATION_INSTANT:
            labels["boundaries"].add("logical-time:deadline")
        if name == "scope.open":
            labels["lifecycle"].add("scope-open")
        elif name == "scope.reset":
            labels["lifecycle"].add("scope-reset")
            reset_after_claim = claimed is not None
        elif name == "source.deliver":
            payload = cast(dict[str, JsonValue], operation.command.payload)
            value = cast(int, payload["value"])
            labels["boundaries"].add(
                "source-value:negative" if value < 0 else "source-value:positive" if value > 0 else "source-value:zero"
            )
        elif name == "worker.claim":
            attempt = cast(dict[str, JsonValue], cast(dict[str, JsonValue], operation.result.value)["attempt"])
            claimed = cast(int, attempt["occurrence"])
            epoch = cast(int, attempt["epoch"])
            labels["boundaries"].add(f"worker-epoch:{epoch}")
            if epoch > 1:
                labels["terminals"].add("retry-claimed")
        elif name == "worker.fail" and claimed is not None:
            retried.add(claimed)
            labels["terminals"].add("retryable-failure")
        elif name == "worker.complete":
            report = cast(dict[str, JsonValue], cast(dict[str, JsonValue], operation.result.value)["report"])
            occurrence = cast(int, report["occurrence"])
            labels["terminals"].add("provider-completed")
            if occurrence in retried and reset_after_claim:
                labels["combinations"].add("retry-then-reset-before-terminal")
            claimed = None
            reset_after_claim = False

    for entry in artifact.expected.checks:
        value = cast(dict[str, JsonValue], entry.value)
        labels["checker_activations"].add(cast(str, value["trigger"]))
        observation = cast(dict[str, JsonValue], value["observation"])
        state = cast(dict[str, JsonValue], observation["value"])
        if cast(list[JsonValue], state["completed_occurrences"]):
            labels["terminals"].add("semantic-projection-completed")
        if cast(list[JsonValue], state["quarantined_occurrences"]):
            labels["terminals"].add("late-terminal-quarantined")
        if cast(list[JsonValue], state["timer_maturations"]):
            labels["terminals"].add("timer-matured")

    return labels


def semantic_coverage_report(focused: ScenarioArtifact, broad: ScenarioArtifact) -> dict[str, JsonValue]:
    """Build the retained DS3 semantic-coverage report."""

    focused_labels = semantic_labels(focused)
    broad_labels = semantic_labels(broad)
    reached = {
        category: sorted(focused_labels[category] | broad_labels[category])
        for category in focused_labels
        if category != "combinations"
    }
    broad_only = sorted(broad_labels["combinations"] - focused_labels["combinations"])
    return cast(
        dict[str, JsonValue],
        {
            "format": "petrus-dst-semantic-coverage",
            "version": 1,
            "profile": GeneratedRuntimeProfile.identity.model_dump(mode="json"),
            "checker": CHECKER_IDENTITY.model_dump(mode="json"),
            "scenarios": [focused.scenario_id, broad.scenario_id],
            "reached": reached,
            "broad_only": broad_only,
            "unreachable": [
                {
                    "dimension": "authored-external-wait-after-fair-begin",
                    "reason": "World rejects this disposition after the fair declaration",
                },
                {
                    "dimension": "stale-generation-authored-command",
                    "reason": "generation revocation rejects the old Timeline before profile application",
                },
                {
                    "dimension": "worker-attempt-epoch-three",
                    "reason": "the profile's two-attempt policy and closed command schema refuse a third epoch",
                },
            ],
            "intentionally_ungenerated": [
                {
                    "dimension": "conflicting-identified-redelivery",
                    "owner": "retained DS2 identified-ingress profile",
                },
                {
                    "dimension": "permanent-fault-during-fair-phase",
                    "owner": "excluded by the CV19 fair-environment precondition",
                },
                {
                    "dimension": "postgresql-absurd-transaction-boundaries",
                    "owner": "CV19.DS4 production-boundary qualification",
                },
                {
                    "dimension": "application-human-or-provider-prerequisite",
                    "owner": "application scenario profile, not Petrus's generic profile",
                },
            ],
        },
    )
