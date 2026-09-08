"""Bounded pytest-backed deterministic simulation campaigns for CV19.DS4."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from hypothesis import settings
from pydantic import JsonValue

from petrus.testing.dst import AnyScenarioArtifact, ExecuteOperation, encode_artifact

REPORT_FORMAT = "petrus-dst-campaign-report"
REPORT_VERSION = 1
REPORT_BYTES = 1_048_576
CASE_SUMMARY_BYTES = 16_384
ORDINARY_TIER = "ordinary"
SCHEDULED_TIER = "scheduled"
TIER_ENV = "PETRUS_DST_CAMPAIGN_TIER"
CASE_PATH_ENV = "PETRUS_DST_CAMPAIGN_CASES"
SEED_ENV = "PETRUS_DST_CAMPAIGN_SEED"
_CAMPAIGN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


@dataclass(frozen=True)
class CampaignProfile:
    name: str
    node: str
    ordinary_examples: int
    ordinary_steps: int

    def examples(self, tier: str) -> int:
        return self.ordinary_examples if tier == ORDINARY_TIER else self.ordinary_examples * 4

    def steps(self, tier: str) -> int:
        return self.ordinary_steps if tier == ORDINARY_TIER else self.ordinary_steps + 2


CAMPAIGN_PROFILES = (
    CampaignProfile(
        "delivery-broad",
        "tests/dst/test_generated_delivery_world.py::test_broad_generated_delivery_schedules_replay_exactly",
        30,
        8,
    ),
    CampaignProfile(
        "delivery-focused",
        "tests/dst/test_generated_delivery_world.py::test_focused_generated_delivery_schedules_cover_high_value_boundaries_and_replay_exactly",
        20,
        6,
    ),
    CampaignProfile(
        "runtime-broad",
        "tests/dst/test_generated_runtime_world.py::test_broad_generated_runtime_schedules_replay_exactly",
        16,
        5,
    ),
    CampaignProfile(
        "runtime-focused",
        "tests/dst/test_generated_runtime_world.py::test_focused_generated_runtime_schedules_replay_exactly",
        10,
        4,
    ),
)
_PROFILES = {profile.name: profile for profile in CAMPAIGN_PROFILES}

UNMODELED_BOUNDARIES = (
    "database-server power loss and PostgreSQL implementation behavior",
    "operating-system scheduling and authority-process death",
    "pinned Absurd transport, Worker process, and lease implementation behavior",
    "ZeroMQ socket, dispatch-server process, and IPC implementation behavior",
    "application-owned provider, credential, human-decision, and network authority",
)


def campaign_settings(profile_name: str) -> settings:
    """Return the bounded Hypothesis settings for one generated profile."""

    profile = _profile(profile_name)
    tier = _tier(os.environ.get(TIER_ENV, ORDINARY_TIER))
    recording = CASE_PATH_ENV in os.environ
    if tier == SCHEDULED_TIER and not recording:
        raise RuntimeError("scheduled DST settings must run through tests.dst.campaign")
    if recording and SEED_ENV not in os.environ:
        raise RuntimeError("campaign case recording requires an exact campaign seed")
    return settings(
        max_examples=profile.examples(tier),
        stateful_step_count=profile.steps(tier),
        derandomize=tier == ORDINARY_TIER and not recording,
        database=None,
        deadline=None,
    )


def record_campaign_case(profile_name: str, artifact: AnyScenarioArtifact) -> None:
    """Append one payload-free semantic summary after exact fresh replay."""

    path_value = os.environ.get(CASE_PATH_ENV)
    if path_value is None:
        return
    profile = _profile(profile_name)
    seed_value = os.environ.get(SEED_ENV)
    if seed_value is None:
        raise RuntimeError("campaign case recording requires an exact campaign seed")
    encoded = encode_artifact(artifact)
    commands: set[str] = set()
    action_dispositions: set[str] = set()
    faults: set[str] = set()
    crash_cuts: set[str] = set()
    checker_triggers: set[str] = set()
    operation_kinds: set[str] = set()
    for operation in artifact.operations:
        operation_kinds.add(operation.kind)
        if isinstance(operation, ExecuteOperation):
            commands.add(operation.command.name)
            action_dispositions.add(operation.result.disposition)
        elif operation.kind == "activate_fault":
            faults.add(f"{operation.fault.name}@{operation.fault.target}")
        elif operation.kind == "crash":
            crash_cuts.add(operation.cut)
    for entry in artifact.expected.checks:
        value = cast(dict[str, JsonValue], entry.value)
        trigger = value.get("trigger")
        if type(trigger) is str:
            checker_triggers.add(trigger)
    budget = artifact.budget.model_dump(mode="json")
    summary = {
        "action_dispositions": sorted(action_dispositions),
        "artifact_bytes": len(encoded),
        "artifact_digest": "sha256:" + hashlib.sha256(encoded).hexdigest(),
        "campaign_profile": profile.name,
        "campaign_seed": int(seed_value),
        "checker_triggers": sorted(checker_triggers),
        "commands": sorted(commands),
        "crash_cuts": sorted(crash_cuts),
        "disposition": artifact.expected.disposition,
        "faults": sorted(faults),
        "journal_digest": artifact.expected.journal_digest,
        "operation_kinds": sorted(operation_kinds),
        "operations": len(artifact.operations),
        "profile": artifact.profile.model_dump(mode="json"),
        "profile_resource_limits": budget.get("profile_resources", {}),
    }
    encoded_summary = json.dumps(summary, allow_nan=False, separators=(",", ":"), sort_keys=True).encode() + b"\n"
    if len(encoded_summary) > CASE_SUMMARY_BYTES:
        raise ValueError(f"DST campaign case summary has {len(encoded_summary)} bytes; limit is {CASE_SUMMARY_BYTES}")
    with Path(path_value).open("ab") as stream:
        stream.write(encoded_summary)


def campaign_seed(campaign_id: str, profile_name: str) -> int:
    """Derive an isolated 32-bit Hypothesis seed for one campaign/profile."""

    _validate_campaign_id(campaign_id)
    _profile(profile_name)
    payload = json.dumps(
        [REPORT_FORMAT, REPORT_VERSION, campaign_id, profile_name],
        separators=(",", ":"),
    ).encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:4])


def run_campaign(
    *,
    tier: str,
    campaign_id: str,
    profile_names: tuple[str, ...],
    report_path: Path,
) -> int:
    """Run selected pytest profiles serially and retain one bounded report."""

    tier = _tier(tier)
    _validate_campaign_id(campaign_id)
    if not profile_names:
        raise ValueError("a DST campaign must select at least one profile")
    if len(profile_names) != len(set(profile_names)):
        raise ValueError("a DST campaign cannot select a profile more than once")
    profiles = tuple(_profile(name) for name in profile_names)
    profile_timeout_seconds = 60 if tier == ORDINARY_TIER else 120
    total_timeout_seconds = profile_timeout_seconds * len(profiles) + 30
    started = time.monotonic()
    results: list[dict[str, JsonValue]] = []
    exit_code = 0

    with tempfile.TemporaryDirectory(prefix="petrus-dst-campaign-") as directory:
        root = Path(directory)
        for profile in profiles:
            seed = campaign_seed(campaign_id, profile.name)
            cases_path = root / f"{profile.name}.jsonl"
            command = [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                profile.node,
                "--forbid-skips",
            ]
            command.append(f"--hypothesis-seed={seed}")
            environment = {
                **os.environ,
                TIER_ENV: tier,
                CASE_PATH_ENV: str(cases_path),
                SEED_ENV: str(seed),
            }
            profile_started = time.monotonic()
            try:
                completed = subprocess.run(
                    command,
                    cwd=Path(__file__).parents[2],
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=profile_timeout_seconds,
                    check=False,
                )
                elapsed_ms = round((time.monotonic() - profile_started) * 1_000)
                expected_cases = profile.examples(tier)
                case_limit = expected_cases * 10
                case_error: str | None = None
                try:
                    cases = _load_cases(cases_path, byte_limit=case_limit * CASE_SUMMARY_BYTES)
                except ValueError as error:
                    cases = []
                    case_error = str(error)
                outcome = "pass"
                detail: str | None = None
                if completed.returncode != 0:
                    outcome = "pytest_failure"
                    detail = f"pytest exited {completed.returncode}"
                elif case_error is not None:
                    outcome = "case_budget_exhausted"
                    detail = case_error
                elif len(cases) < expected_cases:
                    outcome = "incomplete"
                    detail = f"recorded {len(cases)} cases; expected at least {expected_cases}"
                elif len(cases) > case_limit:
                    outcome = "case_budget_exhausted"
                    detail = f"recorded {len(cases)} cases; limit is {case_limit}"
                if outcome != "pass":
                    exit_code = 1
                    _show_failure(profile.name, completed.stdout, completed.stderr)
                results.append(
                    _profile_result(
                        profile,
                        tier,
                        seed,
                        elapsed_ms,
                        cases,
                        outcome,
                        detail,
                    )
                )
            except subprocess.TimeoutExpired as error:
                exit_code = 1
                elapsed_ms = round((time.monotonic() - profile_started) * 1_000)
                _show_failure(profile.name, error.stdout or "", error.stderr or "")
                try:
                    cases = _load_cases(
                        cases_path,
                        byte_limit=profile.examples(tier) * 10 * CASE_SUMMARY_BYTES,
                    )
                except ValueError:
                    cases = []
                results.append(
                    _profile_result(
                        profile,
                        tier,
                        seed,
                        elapsed_ms,
                        cases,
                        "timeout",
                        f"exceeded {profile_timeout_seconds} seconds",
                    )
                )

    elapsed_ms = round((time.monotonic() - started) * 1_000)
    if elapsed_ms > total_timeout_seconds * 1_000:
        exit_code = 1
    selected = {profile.name for profile in profiles}
    report = {
        "bounds": {
            "artifact_bytes_per_scenario": 4_194_304,
            "case_summary_bytes": CASE_SUMMARY_BYTES,
            "concurrency": 1,
            "profile_timeout_seconds": profile_timeout_seconds,
            "profiles": len(profiles),
            "report_bytes": REPORT_BYTES,
            "total_timeout_seconds": total_timeout_seconds,
        },
        "campaign_id": campaign_id,
        "deselected_profiles": [profile.name for profile in CAMPAIGN_PROFILES if profile.name not in selected],
        "elapsed_ms": elapsed_ms,
        "format": REPORT_FORMAT,
        "outcome": "pass" if exit_code == 0 else "fail",
        "profiles": results,
        "repository": repository_identity(),
        "runtime": {
            "hypothesis": importlib.metadata.version("hypothesis"),
            "petrus": importlib.metadata.version("petrus-runtime"),
            "python": sys.version.split()[0],
        },
        "tier": tier,
        "unmodeled_boundaries": list(UNMODELED_BOUNDARIES),
        "version": REPORT_VERSION,
    }
    encoded_report = json.dumps(report, allow_nan=False, indent=2, sort_keys=True).encode() + b"\n"
    if len(encoded_report) > REPORT_BYTES:
        raise ValueError(f"DST campaign report has {len(encoded_report)} bytes; limit is {REPORT_BYTES}")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_bytes(encoded_report)
    return exit_code


def _profile_result(
    profile: CampaignProfile,
    tier: str,
    seed: int,
    elapsed_ms: int,
    cases: list[dict[str, JsonValue]],
    outcome: str,
    detail: str | None,
) -> dict[str, JsonValue]:
    commands: set[str] = set()
    dispositions: set[str] = set()
    faults: set[str] = set()
    cuts: set[str] = set()
    action_dispositions: set[str] = set()
    operation_kinds: set[str] = set()
    checker_triggers: set[str] = set()
    artifact_sizes: list[int] = []
    resource_limits: dict[str, JsonValue] = {}
    for case in cases:
        if case["campaign_profile"] != profile.name or case["campaign_seed"] != seed:
            raise ValueError(f"campaign case identity mismatch for {profile.name}")
        commands.update(cast(list[str], case["commands"]))
        dispositions.add(cast(str, case["disposition"]))
        faults.update(cast(list[str], case["faults"]))
        cuts.update(cast(list[str], case["crash_cuts"]))
        action_dispositions.update(cast(list[str], case["action_dispositions"]))
        operation_kinds.update(cast(list[str], case["operation_kinds"]))
        checker_triggers.update(cast(list[str], case["checker_triggers"]))
        artifact_sizes.append(cast(int, case["artifact_bytes"]))
        resource_limits = cast(dict[str, JsonValue], case["profile_resource_limits"])
    result: dict[str, JsonValue] = {
        "artifact_bytes_max": max(artifact_sizes, default=0),
        "case_summaries_limit": profile.examples(tier) * 10,
        "cases": len(cases),
        "elapsed_ms": elapsed_ms,
        "examples_target": profile.examples(tier),
        "node": profile.node,
        "outcome": outcome,
        "profile": profile.name,
        "profile_resource_limits": resource_limits,
        "seed": seed,
        "semantic_reach": {
            "action_dispositions": sorted(action_dispositions),
            "checker_triggers": sorted(checker_triggers),
            "commands": sorted(commands),
            "crash_cuts": sorted(cuts),
            "dispositions": sorted(dispositions),
            "faults": sorted(faults),
            "operation_kinds": sorted(operation_kinds),
        },
        "stateful_steps_limit": profile.steps(tier),
    }
    if detail is not None:
        result["failure"] = detail
    return result


def _load_cases(path: Path, *, byte_limit: int) -> list[dict[str, JsonValue]]:
    if not path.exists():
        return []
    size = path.stat().st_size
    if size > byte_limit:
        raise ValueError(f"DST campaign case log has {size} bytes; limit is {byte_limit}")
    cases: list[dict[str, JsonValue]] = []
    for line in path.read_bytes().splitlines():
        value = json.loads(line)
        if type(value) is not dict:
            raise ValueError("DST campaign case must be a JSON object")
        cases.append(cast(dict[str, JsonValue], value))
    return cases


def repository_identity() -> dict[str, JsonValue]:
    root = Path(__file__).parents[2]
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("DST operation requires an exact Git commit identity")
    dirty = bool(
        subprocess.run(
            ["git", "status", "--short"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    return {"commit": commit, "dirty": dirty}


def _show_failure(profile: str, stdout: str | bytes, stderr: str | bytes) -> None:
    print(f"DST campaign profile {profile} failed", file=sys.stderr)
    for output in (stdout, stderr):
        if isinstance(output, bytes):
            output = output.decode(errors="replace")
        if output:
            print(output[-8_192:], file=sys.stderr)


def _profile(name: str) -> CampaignProfile:
    try:
        return _PROFILES[name]
    except KeyError:
        raise ValueError(f"unknown DST campaign profile {name!r}") from None


def _tier(value: str) -> str:
    if value not in {ORDINARY_TIER, SCHEDULED_TIER}:
        raise ValueError(f"unknown DST campaign tier {value!r}")
    return value


def _validate_campaign_id(value: str) -> None:
    if not _CAMPAIGN_ID.fullmatch(value):
        raise ValueError("DST campaign id must be 1-128 normalized characters")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tier", choices=(ORDINARY_TIER, SCHEDULED_TIER), default=SCHEDULED_TIER)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--profile", action="append", choices=tuple(_PROFILES), dest="profiles")
    parser.add_argument("--report", type=Path, required=True)
    arguments = parser.parse_args()
    profiles = tuple(arguments.profiles) if arguments.profiles else tuple(profile.name for profile in CAMPAIGN_PROFILES)
    return run_campaign(
        tier=arguments.tier,
        campaign_id=arguments.campaign_id,
        profile_names=profiles,
        report_path=arguments.report,
    )


if __name__ == "__main__":
    raise SystemExit(main())
