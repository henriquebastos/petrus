"""CV19.DS4 bounded complementary production-boundary operation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from pydantic import JsonValue

from tests.dst import boundaries
from tests.dst.boundaries import (
    BOUNDARY_PROFILES,
    REPORT_BYTES,
    REPORT_FORMAT,
    REPORT_VERSION,
    run_boundary_qualification,
)


def test_real_boundary_route_reports_executed_claims_and_non_equivalence(tmp_path: Path) -> None:
    report_path = tmp_path / "boundaries.json"

    exit_code = run_boundary_qualification(
        profile_names=tuple(profile.name for profile in BOUNDARY_PROFILES),
        report_path=report_path,
    )

    report = cast(dict[str, JsonValue], json.loads(report_path.read_bytes()))
    assert exit_code == 0
    assert report["format"] == REPORT_FORMAT
    assert report["version"] == REPORT_VERSION
    assert report["outcome"] == "pass"
    assert report["deselected_profiles"] == []
    assert report_path.stat().st_size <= REPORT_BYTES
    profiles = cast(list[dict[str, JsonValue]], report["profiles"])
    assert len(profiles) == 6
    assert {profile["outcome"] for profile in profiles} == {"pass"}
    assert {profile["evidence"] for profile in profiles} == {
        "deterministic-world",
        "real-postgresql-absurd-transaction",
        "real-postgresql-absurd-reconstruction",
        "real-worker-process-sigkill",
        "real-zeromq-dispatch-process-kill",
    }
    comparison = cast(list[dict[str, JsonValue]], report["comparisons"])[0]
    assert comparison["status"] == "complete"
    assert "does not OS-kill the authority" in cast(str, comparison["non_equivalence"])
    assert "authority-process OS SIGKILL" in cast(list[str], report["unmodeled_boundaries"])[0]


def test_boundary_route_refuses_empty_duplicate_and_unknown_selection(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least one profile"):
        run_boundary_qualification(profile_names=(), report_path=tmp_path / "empty.json")
    with pytest.raises(ValueError, match="more than once"):
        run_boundary_qualification(
            profile_names=("simulated-dispatch-crash-load", "simulated-dispatch-crash-load"),
            report_path=tmp_path / "duplicate.json",
        )
    with pytest.raises(ValueError, match="unknown production-boundary profile"):
        run_boundary_qualification(profile_names=("unknown",), report_path=tmp_path / "unknown.json")


def test_boundary_timeout_and_report_overage_are_visible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        boundaries,
        "_execute_profiles",
        lambda profiles: {
            "elapsed_ms": 120_000,
            "outcome": "timeout",
            "returncode": -9,
            "termination": "killed",
        },
    )
    monkeypatch.setattr(boundaries, "repository_identity", lambda: {"commit": "0" * 40, "dirty": False})
    report_path = tmp_path / "timeout.json"

    exit_code = run_boundary_qualification(
        profile_names=("simulated-dispatch-crash-load",),
        report_path=report_path,
    )

    report = cast(dict[str, JsonValue], json.loads(report_path.read_bytes()))
    assert exit_code == 1
    assert report["outcome"] == "timeout"
    assert cast(list[dict[str, JsonValue]], report["profiles"])[0]["outcome"] == "not-qualified"

    monkeypatch.setattr(boundaries, "REPORT_BYTES", 1)
    with pytest.raises(ValueError, match="report has .* bytes; limit is 1"):
        run_boundary_qualification(
            profile_names=("simulated-dispatch-crash-load",),
            report_path=tmp_path / "overage.json",
        )
