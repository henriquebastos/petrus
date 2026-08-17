"""CV19.DS1 strict scenario contract and concrete replay route."""

from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from tests.dst.replay import APPLICATION_DIGEST, FORMAT, PROFILE, VERSION, load_scenario, replay_scenario


FIXTURE = Path("tests/dst/fixtures/projection-crash-recovery-v1.json")


def _write(tmp_path: Path, value: object) -> Path:
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps(value, allow_nan=False))
    return path


def _reverse_crash_restart(value: dict[str, object]) -> None:
    schedule = value["schedule"]
    assert isinstance(schedule, list)
    crash = schedule[3]
    restart = schedule[4]
    assert isinstance(crash, dict) and isinstance(restart, dict)
    crash["event"], restart["event"] = restart["event"], crash["event"]


def test_projection_crash_fixture_is_strict_portable_data() -> None:
    scenario = load_scenario(FIXTURE)

    assert (scenario.format, scenario.version, scenario.profile) == (FORMAT, VERSION, PROFILE)
    assert scenario.application.definition_digest == APPLICATION_DIGEST
    assert scenario.origin.shrink.parent_scenario_id is None
    assert all(type(step.position) is int for step in scenario.schedule)
    assert json.loads(FIXTURE.read_bytes()) == scenario.model_dump(mode="json")


def test_projection_crash_fixture_replays_through_fresh_production_engines() -> None:
    report = replay_scenario(load_scenario(FIXTURE))

    assert report.history_frontier == 9
    assert report.snapshot == {
        "marking": [{"place": "done", "tokens": [{"color": "Done", "data": {"value": 3}}]}],
        "status": "terminated",
        "watermark": 0,
        "in_flight": [],
    }
    assert report.observations == {
        "prepared_before_crash": 1,
        "projected_before_crash": 1,
        "prepared_after_restart": 0,
        "projected_after_restart": 1,
        "dispatch_pending_after_restart": 0,
    }
    assert report.checks == (
        "S1-replay-agreement",
        "S3-stable-invocation",
        "S4-terminal-before-projection",
    )


def test_replay_command_emits_one_strict_passing_result() -> None:
    command = [sys.executable, "-m", "tests.dst.replay", str(FIXTURE)]
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )
    repeated = subprocess.run(command, check=True, capture_output=True, text=True)

    result = json.loads(completed.stdout)
    assert completed.stderr == ""
    assert repeated.stdout == completed.stdout
    assert repeated.stderr == ""
    assert result["format"] == "petrus-dst-replay-result"
    assert result["scenario_id"] == "projection-crash-recovery-v1"
    assert result["outcome"] == "pass"
    assert result["property"] == "S4-terminal-before-projection"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update({"unknown": True}),
        lambda value: value.update({"version": 2}),
        lambda value: value.update({"profile": "other"}),
        lambda value: value["limits"].update({"events": True}),
        lambda value: value["limits"].update({"actions_per_drive": 0}),
        lambda value: value["schedule"][0]["event"].update({"kind": "surprise"}),
        lambda value: value["schedule"][2]["faults"][0].update({"kind": "surprise"}),
        lambda value: value["schedule"][2]["faults"][0].update({"cut": "projection_committed"}),
        lambda value: value["schedule"][0]["event"].update({"max_actions": 2}),
        lambda value: value["schedule"][4].update({"position": 8}),
        lambda value: value["initial"]["marking"].append(value["initial"]["marking"][0]),
        lambda value: value["expected"]["snapshot"]["marking"].append(value["expected"]["snapshot"]["marking"][0]),
        _reverse_crash_restart,
    ],
)
def test_unknown_non_strict_or_incoherent_artifacts_refuse(tmp_path: Path, mutate) -> None:
    value = deepcopy(json.loads(FIXTURE.read_bytes()))
    mutate(value)

    with pytest.raises(ValidationError):
        load_scenario(_write(tmp_path, value))


def test_duplicate_fields_and_nonfinite_numbers_refuse_before_validation(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"format":"petrus-dst-scenario","format":"other"}')
    nonfinite = tmp_path / "nonfinite.json"
    nonfinite.write_text('{"value":NaN}')

    with pytest.raises(ValueError, match="duplicate JSON field"):
        load_scenario(duplicate)
    with pytest.raises(ValueError, match="non-finite JSON number"):
        load_scenario(nonfinite)
