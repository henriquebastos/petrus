"""The repository feedback interface is bounded and self-describing."""

from __future__ import annotations

import subprocess

from tests import REPO_ROOT

CHECK = REPO_ROOT / "scripts" / "check"


def _run(*arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run([str(CHECK), *arguments], cwd=REPO_ROOT, capture_output=True, text=True)


def test_check_script_is_valid_shell_and_describes_each_profile():
    syntax = subprocess.run(["bash", "-n", str(CHECK)], cwd=REPO_ROOT, capture_output=True, text=True)
    assert syntax.returncode == 0, syntax.stderr

    help_result = _run("--help")
    assert help_result.returncode == 0
    assert "scripts/check quick [PATH ...]" in help_result.stdout
    assert "scripts/check full" in help_result.stdout
    assert "scripts/check release" in help_result.stdout
    assert "scripts/check mutation" in help_result.stdout
    script = CHECK.read_text()
    assert "uv run ty check src/petrus" in script
    assert "uv run mutmut run" in script
    assert "export UV_FROZEN=1" in script
    assert 'exec 9>"/tmp/petrus-check-full.lock"' in script
    assert script.count("exec 9>&-") == 2
    assert script.count("-n 4 --dist loadscope") == 1
    assert script.count("--basetemp=/tmp/petrus-check") == 2
    assert script.count("--durations=20 --durations-min=0.5") == 2
    assert "TMPDIR" not in script


def test_bounded_profiles_reject_paths_without_running_tools():
    for profile in ("full", "release", "mutation"):
        result = _run(profile, "tests/project/test_check_command.py")
        assert result.returncode == 2
        assert f"scripts/check {profile} does not accept paths" in result.stderr


def test_unknown_profile_fails_with_usage():
    result = _run("unknown")
    assert result.returncode == 2
    assert "usage: scripts/check quick" in result.stderr
