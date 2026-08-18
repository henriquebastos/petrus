"""CV19.DS2 identified-delivery World/Timeline proof."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from petrus.testing.dst import (
    RESULT_VERSION,
    CheckResult,
    Disposition,
    Observation,
    ScenarioRegistry,
    encode_artifact,
    replay,
)
from tests.dst.delivery_world import (
    SCENARIO_ID,
    DeliveryAuthorityChecker,
    DeliveryEngineProfile,
    build_delivery_artifact,
)

FIXTURE = Path("tests/dst/fixtures/identified-delivery-redelivery-world-v3.json")


def test_identified_delivery_redelivery_is_exact_and_replayable(tmp_path: Path) -> None:
    artifact = build_delivery_artifact(tmp_path / "delivery-author.jsonl")

    assert artifact.scenario_id == SCENARIO_ID
    assert artifact.origin is None
    assert encode_artifact(artifact) == FIXTURE.read_bytes().rstrip(b"\n")

    registry = ScenarioRegistry()
    registry.register_profile(DeliveryEngineProfile(tmp_path / "delivery-replay.jsonl"))
    registry.register_checker(DeliveryAuthorityChecker())
    result = replay(artifact, registry)

    assert result.version == RESULT_VERSION
    assert result.outcome == "pass"
    assert result.disposition == Disposition.EXTERNAL_WAIT.value
    assert result.operations == len(artifact.operations)


def test_identified_delivery_manual_replay_route_is_deterministic() -> None:
    command = [sys.executable, "-m", "tests.dst.replay_world", str(FIXTURE)]
    first = subprocess.run(command, check=True, capture_output=True, text=True)
    second = subprocess.run(command, check=True, capture_output=True, text=True)

    assert first.stderr == second.stderr == ""
    assert first.stdout == second.stdout
    result = json.loads(first.stdout)
    assert result["version"] == RESULT_VERSION
    assert result["scenario_id"] == SCENARIO_ID
    assert result["outcome"] == "pass"
    assert result["disposition"] == Disposition.EXTERNAL_WAIT.value


def test_delivery_checker_refuses_duplicate_canonical_identity() -> None:
    checker = DeliveryAuthorityChecker()
    observation = Observation(
        name="engine.delivery-authority",
        value={
            "canonical_deliveries": [
                {"identity": "event-3", "occurrence": 1, "value": 3},
                {"identity": "event-3", "occurrence": 2, "value": 3},
            ],
            "delivery_attempts": [
                {"disposition": "applied", "identity": "event-3", "value": 3},
                {"disposition": "idempotent", "identity": "event-3", "value": 3},
            ],
            "firing_completed": 2,
            "marking_values": [3, 3],
        },
        instant=0,
        generation=2,
        sequence=0,
    )

    result: CheckResult = checker.check(observation)

    assert result.passed is False
    assert result.detail["expected_deliveries"] == [{"identity": "event-3", "value": 3}]
