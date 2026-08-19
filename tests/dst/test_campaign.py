"""CV19.DS4 bounded campaign operation and reporting."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from pydantic import JsonValue

from petrus.testing.dst import load_artifact
from tests.dst import campaign
from tests.dst.campaign import (
    CAMPAIGN_PROFILES,
    CASE_PATH_ENV,
    ORDINARY_TIER,
    REPORT_FORMAT,
    REPORT_VERSION,
    SCHEDULED_TIER,
    SEED_ENV,
    TIER_ENV,
    campaign_seed,
    campaign_settings,
    record_campaign_case,
    run_campaign,
)

FIXTURE = Path("tests/dst/fixtures/generated-runtime-minimized-fair-regression-v4.json")


def test_campaign_tiers_are_bounded_and_profile_seeds_are_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    ordinary = {profile.name: (profile.ordinary_examples, profile.ordinary_steps) for profile in CAMPAIGN_PROFILES}
    assert ordinary == {
        "delivery-broad": (30, 8),
        "delivery-focused": (20, 6),
        "runtime-broad": (16, 5),
        "runtime-focused": (10, 4),
    }

    monkeypatch.setenv(TIER_ENV, ORDINARY_TIER)
    normal = campaign_settings("runtime-focused")
    assert normal.max_examples == 10
    assert normal.stateful_step_count == 4
    assert normal.derandomize is True
    assert normal.database is None

    monkeypatch.setenv(TIER_ENV, SCHEDULED_TIER)
    monkeypatch.setenv(CASE_PATH_ENV, "/tmp/petrus-dst-campaign-test.jsonl")
    monkeypatch.setenv(SEED_ENV, "19003")
    scheduled = campaign_settings("runtime-focused")
    assert scheduled.max_examples == 40
    assert scheduled.stateful_step_count == 6
    assert scheduled.derandomize is False
    assert scheduled.database is None

    first = campaign_seed("2026-W34", "runtime-focused")
    assert first == campaign_seed("2026-W34", "runtime-focused")
    assert first != campaign_seed("2026-W35", "runtime-focused")
    assert len({campaign_seed("2026-W34", profile.name) for profile in CAMPAIGN_PROFILES}) == 4

    monkeypatch.setenv(TIER_ENV, "unbounded")
    with pytest.raises(ValueError, match="unknown DST campaign tier"):
        campaign_settings("runtime-focused")


def test_campaign_case_summary_is_payload_free_and_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cases = tmp_path / "cases.jsonl"
    monkeypatch.setenv(CASE_PATH_ENV, str(cases))
    monkeypatch.setenv(SEED_ENV, "19003")
    artifact = load_artifact(FIXTURE)

    record_campaign_case("runtime-focused", artifact)

    encoded = cases.read_bytes()
    summary = cast(dict[str, JsonValue], json.loads(encoded))
    assert summary["campaign_profile"] == "runtime-focused"
    assert summary["campaign_seed"] == 19003
    assert summary["artifact_bytes"] == len(FIXTURE.read_bytes().rstrip(b"\n"))
    assert summary["commands"] == [
        "engine.drive",
        "scope.open",
        "source.deliver",
        "worker.claim",
        "worker.complete",
    ]
    assert summary["disposition"] == "quiescent"
    assert summary["profile_resource_limits"]
    assert b"shrink-event-" not in encoded
    assert b'"payload"' not in encoded
    assert b'"result"' not in encoded


def test_ordinary_campaign_route_runs_pytest_and_retains_actual_reach(tmp_path: Path) -> None:
    report_path = tmp_path / "campaign.json"

    exit_code = run_campaign(
        tier=ORDINARY_TIER,
        campaign_id="cv19-ts1-integration",
        profile_names=("runtime-focused",),
        report_path=report_path,
    )

    report = cast(dict[str, JsonValue], json.loads(report_path.read_bytes()))
    assert exit_code == 0
    assert report["format"] == REPORT_FORMAT
    assert report["version"] == REPORT_VERSION
    assert report["outcome"] == "pass"
    assert report["tier"] == ORDINARY_TIER
    assert report["deselected_profiles"] == ["delivery-broad", "delivery-focused", "runtime-broad"]
    assert len(cast(list[JsonValue], report["unmodeled_boundaries"])) == 5
    repository = cast(dict[str, JsonValue], report["repository"])
    assert len(cast(str, repository["commit"])) == 40
    profiles = cast(list[dict[str, JsonValue]], report["profiles"])
    assert len(profiles) == 1
    result = profiles[0]
    assert result["profile"] == "runtime-focused"
    assert result["outcome"] == "pass"
    assert cast(int, result["cases"]) >= cast(int, result["examples_target"])
    assert cast(int, result["cases"]) <= cast(int, result["case_summaries_limit"])
    assert 0 < cast(int, result["artifact_bytes_max"]) <= 4_194_304
    reach = cast(dict[str, JsonValue], result["semantic_reach"])
    assert "source.deliver" in cast(list[str], reach["commands"])
    assert "generated_dispatch_refused" in cast(list[str], reach["crash_cuts"])
    assert "dispatch.refuse@activity_requested" in cast(list[str], reach["faults"])


def test_campaign_refuses_invalid_selection_before_execution(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least one profile"):
        run_campaign(
            tier=SCHEDULED_TIER,
            campaign_id="cv19-empty",
            profile_names=(),
            report_path=tmp_path / "empty.json",
        )
    with pytest.raises(ValueError, match="more than once"):
        run_campaign(
            tier=SCHEDULED_TIER,
            campaign_id="cv19-duplicate",
            profile_names=("runtime-focused", "runtime-focused"),
            report_path=tmp_path / "duplicate.json",
        )
    with pytest.raises(ValueError, match="unknown DST campaign profile"):
        run_campaign(
            tier=SCHEDULED_TIER,
            campaign_id="cv19-unknown",
            profile_names=("unknown",),
            report_path=tmp_path / "unknown.json",
        )


def test_campaign_timeout_is_a_visible_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def timeout(*args, **kwargs):
        del args, kwargs
        raise campaign.subprocess.TimeoutExpired(["pytest"], 120, output="bounded stdout", stderr="")

    monkeypatch.setattr(campaign.subprocess, "run", timeout)
    monkeypatch.setattr(
        campaign,
        "repository_identity",
        lambda: {"commit": "0" * 40, "dirty": False},
    )
    report_path = tmp_path / "timeout.json"

    exit_code = run_campaign(
        tier=SCHEDULED_TIER,
        campaign_id="cv19-timeout",
        profile_names=("runtime-focused",),
        report_path=report_path,
    )

    report = cast(dict[str, JsonValue], json.loads(report_path.read_bytes()))
    result = cast(list[dict[str, JsonValue]], report["profiles"])[0]
    assert exit_code == 1
    assert report["outcome"] == "fail"
    assert result["outcome"] == "timeout"
    assert result["failure"] == "exceeded 120 seconds"


def test_campaign_case_log_overage_writes_a_failed_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def overflow(*args, **kwargs):
        del args
        environment = kwargs["env"]
        Path(environment[CASE_PATH_ENV]).write_bytes(b"x" * 401)
        return campaign.subprocess.CompletedProcess(["pytest"], 0, stdout="", stderr="")

    monkeypatch.setattr(campaign, "CASE_SUMMARY_BYTES", 1)
    monkeypatch.setattr(campaign.subprocess, "run", overflow)
    monkeypatch.setattr(
        campaign,
        "repository_identity",
        lambda: {"commit": "0" * 40, "dirty": False},
    )
    report_path = tmp_path / "case-overage.json"

    exit_code = run_campaign(
        tier=SCHEDULED_TIER,
        campaign_id="cv19-case-overage",
        profile_names=("runtime-focused",),
        report_path=report_path,
    )

    report = cast(dict[str, JsonValue], json.loads(report_path.read_bytes()))
    result = cast(list[dict[str, JsonValue]], report["profiles"])[0]
    assert exit_code == 1
    assert report["outcome"] == "fail"
    assert result["outcome"] == "case_budget_exhausted"
    assert result["failure"] == "DST campaign case log has 401 bytes; limit is 400"
