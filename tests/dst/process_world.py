"""Importable complete scenarios for the DST outer-process runner proof."""

from __future__ import annotations

import signal
import time
from pathlib import Path
from typing import cast

from pydantic import JsonValue

from petrus.testing.dst import (
    ActionDisposition,
    ApplyResult,
    Budget,
    Command,
    Fault,
    GenerationStart,
    ObservationRequest,
    ProcessSession,
    ProfileIdentity,
    ScenarioArtifact,
    ScenarioContext,
    digest_json,
)
from tests.dst.engine_world import RESOURCE_SCENARIO_ID, execute_resource_bounded_story

HANG_SCENARIO_ID = "process-watchdog-hang-v1"
HANG_PROFILE_IDENTITY = ProfileIdentity(
    name="petrus.testing.process-watchdog-hang",
    version=1,
    digest=digest_json({"commands": ["runtime.hang"], "observations": ["state"]}),
)
HANG_BUDGET = Budget(
    actions=8,
    queued_commands=1,
    timer_advances=0,
    logical_instant=0,
    reloads=0,
    predicate_polls=1,
    artifact_bytes=64_000,
)


class HangProfile:
    """Deliberately non-returning profile call, isolated to a killable child."""

    identity = HANG_PROFILE_IDENTITY

    def validate(self, command: Command) -> Command:
        if command.name != "runtime.hang" or command.payload is not None:
            raise ValueError("unsupported watchdog proof command")
        return command

    def validate_fault(self, fault: Fault) -> Fault:
        raise ValueError("the watchdog proof profile has no faults")

    def create(self, context: ScenarioContext) -> GenerationStart[object]:
        return GenerationStart(object())

    def load(self, context: ScenarioContext) -> GenerationStart[object]:
        raise ValueError("the watchdog proof profile cannot load")

    def apply(self, generation: object, command: Command, context: ScenarioContext) -> ApplyResult:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        time.sleep(60)
        return ApplyResult(disposition=ActionDisposition.APPLIED, value=None, scheduled=[])

    def observe(self, generation: object, request: ObservationRequest, context: ScenarioContext) -> JsonValue:
        if request.name != "state" or request.payload is not None:
            raise ValueError("unsupported watchdog proof observation")
        return {"state": "waiting"}

    def drop(self, generation: object) -> None:
        return None

    def close(self, generation: object) -> None:
        return None


def resource_recovery(session: ProcessSession, payload: JsonValue) -> ScenarioArtifact:
    values = cast(dict[str, JsonValue], payload)
    history_path = values.get("history_path")
    if not isinstance(history_path, str):
        raise ValueError("resource recovery requires one history_path")
    world, _ = execute_resource_bounded_story(Path(history_path), process=session)
    artifact = world.artifact(RESOURCE_SCENARIO_ID)
    if not isinstance(artifact, ScenarioArtifact):
        raise AssertionError("resource-bounded process proof must produce a version-4 artifact")
    return artifact


def hang_during_command(session: ProcessSession, payload: JsonValue) -> ScenarioArtifact:
    if payload is not None:
        raise ValueError("watchdog hang scenario payload must be null")
    world = session.world(HangProfile(), HANG_BUDGET)
    world.timeline().command("runtime.hang", None)
    raise AssertionError("the deliberately hanging profile call returned")
