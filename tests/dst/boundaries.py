"""Complement deterministic Worlds with bounded real-boundary qualification."""

from __future__ import annotations

import argparse
import fcntl
import importlib.metadata
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from pydantic import JsonValue

from tests.dst.campaign import repository_identity

REPORT_FORMAT = "petrus-dst-production-boundary-report"
REPORT_VERSION = 1
REPORT_BYTES = 262_144
PROFILE_TIMEOUT_SECONDS = 120
TERMINATION_GRACE_SECONDS = 5
OUTPUT_TAIL_BYTES = 8_192
LOCK_PATH = Path("/tmp/petrus-dst-production-boundaries.lock")
POSTGRES_LABEL = "petrus-cv3-test-boundary"


@dataclass(frozen=True)
class BoundaryProfile:
    name: str
    node: str
    evidence: str
    cut: str
    recovery: str
    claim: str


BOUNDARY_PROFILES = (
    BoundaryProfile(
        name="simulated-dispatch-crash-load",
        node="tests/dst/test_dispatch_refusal_world.py::test_dispatch_refusal_recovery_is_exact_and_replayable",
        evidence="deterministic-world",
        cut="scripted Dispatch refusal after durable ActivityRequested, then abrupt generation drop",
        recovery="fresh public Engine load republishes the stable invocation and converges",
        claim="one exact bounded World schedule replays through the same interpreter and independent checker",
    ),
    BoundaryProfile(
        name="postgres-open-transaction-drop",
        node=(
            "tests/petrus/motus/worker/test_worker_topology.py::TestAuthorityKill::"
            "test_a_crash_before_the_begin_transaction_commits_leaves_nothing_anywhere"
        ),
        evidence="real-postgresql-absurd-transaction",
        cut="close the real authority connection with joined History and Absurd work staged but uncommitted",
        recovery="PostgreSQL aborts both sides; fresh authority begins and completes from the prior committed fact",
        claim="the joined transaction is commit-or-vanish under the real PostgreSQL and pinned Absurd adapters",
    ),
    BoundaryProfile(
        name="postgres-absurd-postcommit-reload",
        node=(
            "tests/petrus/motus/worker/test_worker_topology.py::TestAuthorityKill::"
            "test_killed_after_the_dispatch_commit_resumes_without_a_double_spawn"
        ),
        evidence="real-postgresql-absurd-reconstruction",
        cut="abandon authority session objects after the joined begin and task commit",
        recovery="fresh provider load reconstructs one occurrence and leaves the one live task alone",
        claim="post-commit authority reconstruction preserves one invocation, task, effect, and terminal",
    ),
    BoundaryProfile(
        name="absurd-worker-sigkill-redelivery",
        node=(
            "tests/petrus/motus/worker/test_worker_topology.py::TestWorkerKill::"
            "test_sigkill_mid_activity_redispatches_on_lease_expiry_with_exactly_one_effect"
        ),
        evidence="real-worker-process-sigkill",
        cut="SIGKILL the Worker after its real external-effect commit and before terminal reporting",
        recovery="a replacement Worker reclaims after lease expiry and completes the same durable task",
        claim="two executions preserve one idempotent external effect and one canonical Activity terminal",
    ),
    BoundaryProfile(
        name="zeromq-uncertain-terminal-restart",
        node=(
            "tests/petrus/motus/transport/test_zeromq_dispatch_transport.py::"
            "test_uncertain_completion_redelivers_exactly_across_dispatch_process_death"
        ),
        evidence="real-zeromq-dispatch-process-kill",
        cut="kill the dispatch server after durable completion but before the Worker receives acknowledgement",
        recovery="replacement server accepts exact terminal redelivery and LocalDispatch collects it once",
        claim="uncertain terminal delivery survives real ZeroMQ server process death without changed content",
    ),
    BoundaryProfile(
        name="zeromq-lease-restart",
        node=(
            "tests/petrus/motus/transport/test_zeromq_dispatch_transport.py::"
            "test_dispatch_service_process_death_preserves_lease_details_and_restart_recovery"
        ),
        evidence="real-zeromq-dispatch-process-kill",
        cut="kill the dispatch server while one attempt owns a live lease and checkpoint details",
        recovery="restart preserves heartbeat details, then lease expiry authorizes epoch-2 reclaim and completion",
        claim="real IPC process restart preserves lease fencing, details, and one collected terminal",
    ),
)
_PROFILES = {profile.name: profile for profile in BOUNDARY_PROFILES}

UNMODELED_BOUNDARIES = (
    "authority-process OS SIGKILL while its joined PostgreSQL transaction is open",
    "PostgreSQL server power loss, replication, failover, and storage corruption",
    "network partition or loss outside the exercised local ZeroMQ IPC cuts",
    "live provider, credential, human-decision, and application-specific external authority",
)


def run_boundary_qualification(*, profile_names: tuple[str, ...], report_path: Path) -> int:
    """Run exact owner tests in one bounded child and retain a claim-limited report."""

    if not profile_names:
        raise ValueError("production-boundary qualification must select at least one profile")
    if len(profile_names) != len(set(profile_names)):
        raise ValueError("production-boundary qualification cannot select a profile more than once")
    profiles = tuple(_profile(name) for name in profile_names)
    started = time.monotonic()
    execution = _execute_profiles(profiles)
    elapsed_ms = round((time.monotonic() - started) * 1_000)
    selected = {profile.name for profile in profiles}
    outcome = execution["outcome"]
    report: dict[str, JsonValue] = {
        "bounds": {
            "concurrency": 1,
            "output_tail_bytes_on_failure": OUTPUT_TAIL_BYTES,
            "profiles": len(profiles),
            "report_bytes": REPORT_BYTES,
            "termination_grace_seconds": TERMINATION_GRACE_SECONDS,
            "wall_clock_seconds": PROFILE_TIMEOUT_SECONDS,
        },
        "comparisons": [_dispatch_recovery_comparison(selected)],
        "deselected_profiles": [profile.name for profile in BOUNDARY_PROFILES if profile.name not in selected],
        "elapsed_ms": elapsed_ms,
        "execution": execution,
        "format": REPORT_FORMAT,
        "outcome": outcome,
        "profiles": [
            {
                "claim": profile.claim,
                "cut": profile.cut,
                "evidence": profile.evidence,
                "name": profile.name,
                "node": profile.node,
                "outcome": "pass" if outcome == "pass" else "not-qualified",
                "recovery": profile.recovery,
            }
            for profile in profiles
        ],
        "repository": repository_identity(),
        "runtime": {
            "absurd-sdk": importlib.metadata.version("absurd-sdk"),
            "psycopg": importlib.metadata.version("psycopg"),
            "python": sys.version.split()[0],
            "pyzmq": importlib.metadata.version("pyzmq"),
        },
        "unmodeled_boundaries": list(UNMODELED_BOUNDARIES),
        "version": REPORT_VERSION,
    }
    encoded = json.dumps(report, allow_nan=False, indent=2, sort_keys=True).encode() + b"\n"
    if len(encoded) > REPORT_BYTES:
        raise ValueError(f"production-boundary report has {len(encoded)} bytes; limit is {REPORT_BYTES}")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_bytes(encoded)
    return 0 if outcome == "pass" else 1


def _execute_profiles(profiles: tuple[BoundaryProfile, ...]) -> dict[str, JsonValue]:
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--forbid-skips",
        *(profile.node for profile in profiles),
    ]
    environment = {**os.environ, "PYTEST_XDIST_WORKER": "boundary"}
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOCK_PATH.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("another production-boundary qualification owns its test resources") from None
        started = time.monotonic()
        process = subprocess.Popen(
            command,
            cwd=Path(__file__).parents[2],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        termination = "exited"
        try:
            stdout, stderr = process.communicate(timeout=PROFILE_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            termination = "terminated"
            os.killpg(process.pid, signal.SIGTERM)
            try:
                stdout, stderr = process.communicate(timeout=TERMINATION_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                termination = "killed"
                os.killpg(process.pid, signal.SIGKILL)
                stdout, stderr = process.communicate()
            _cleanup_boundary_postgres()
            _show_failure(stdout, stderr)
            return {
                "elapsed_ms": round((time.monotonic() - started) * 1_000),
                "outcome": "timeout",
                "returncode": process.returncode,
                "termination": termination,
            }

    elapsed_ms = round((time.monotonic() - started) * 1_000)
    if process.returncode != 0:
        _show_failure(stdout, stderr)
        return {
            "elapsed_ms": elapsed_ms,
            "outcome": "pytest-failure",
            "returncode": process.returncode,
            "termination": termination,
        }
    return {
        "elapsed_ms": elapsed_ms,
        "outcome": "pass",
        "returncode": process.returncode,
        "termination": termination,
    }


def _cleanup_boundary_postgres() -> None:
    listed = subprocess.run(
        ["docker", "ps", "--all", "--quiet", "--filter", f"label={POSTGRES_LABEL}"],
        capture_output=True,
        text=True,
        check=False,
    )
    for container in listed.stdout.split():
        subprocess.run(["docker", "rm", "--force", container], capture_output=True, check=False)


def _show_failure(stdout: str, stderr: str) -> None:
    print("DST production-boundary qualification failed", file=sys.stderr)
    for output in (stdout, stderr):
        if output:
            print(output[-OUTPUT_TAIL_BYTES:], file=sys.stderr)


def _dispatch_recovery_comparison(selected: set[str]) -> dict[str, JsonValue]:
    simulated = "simulated-dispatch-crash-load"
    real = "postgres-absurd-postcommit-reload"
    return {
        "real_profile": real,
        "shared_contract": (
            "an accepted ActivityRequested survives authority-generation loss and recovery reuses one stable "
            "invocation identity"
        ),
        "simulated_profile": simulated,
        "status": "complete" if {simulated, real} <= selected else "partial",
        "stronger_real_evidence": (
            "the real route reconstructs through PostgreSQL and pinned Absurd and proves one durable provider task"
        ),
        "non_equivalence": (
            "World uses deterministic abrupt generation drop plus scripted Dispatch refusal; the real route "
            "abandons in-process authority objects after commit and does not OS-kill the authority"
        ),
    }


def _profile(name: str) -> BoundaryProfile:
    try:
        return _PROFILES[name]
    except KeyError:
        raise ValueError(f"unknown production-boundary profile {name!r}") from None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", action="append", choices=tuple(_PROFILES), dest="profiles")
    parser.add_argument("--report", required=True, type=Path)
    arguments = parser.parse_args()
    profiles = tuple(arguments.profiles) if arguments.profiles else tuple(profile.name for profile in BOUNDARY_PROFILES)
    return run_boundary_qualification(profile_names=profiles, report_path=arguments.report)


if __name__ == "__main__":
    raise SystemExit(main())
