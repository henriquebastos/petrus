"""Release intent must agree with package metadata before an upload is allowed."""

import json
import os
import subprocess
import sys

import pytest

from tests import REPO_ROOT


@pytest.mark.parametrize(
    ("version", "tag", "prerelease", "draft", "error"),
    [
        ("0.1.0a1", "v0.1.0a1", True, False, None),
        ("0.1.0b1", "v0.1.0b1", True, False, None),
        ("0.1.0rc1", "v0.1.0rc1", True, False, None),
        ("0.1.0", "v0.1.0", False, False, None),
        ("0.2.3", "v0.2.3", False, False, None),
        ("0.1.0a1", "v0.1.0a2", True, False, "Release tag must be v0.1.0a1"),
        ("0.1.0a1", "0.1.0a1", True, False, "Release tag must be v0.1.0a1"),
        ("0.1.0a1", "v0.1.0a1", False, False, "GitHub prerelease must be True"),
        ("0.1.0", "v0.1.0", True, False, "GitHub prerelease must be False"),
        ("0.1.0a1", "v0.1.0a1", True, True, "A draft release cannot publish"),
        ("1.0.0", "v1.0.0", False, False, "Release version must follow the 0.x policy"),
        ("0.1.0.dev1", "v0.1.0.dev1", True, False, "Release version must follow the 0.x policy"),
        ("0.1.0+local", "v0.1.0+local", False, False, "Release version must follow the 0.x policy"),
        ("0.1.0a01", "v0.1.0a01", True, False, "Release version must follow the 0.x policy"),
    ],
)
def test_release_refuses_inconsistent_public_version_or_channel(tmp_path, version, tag, prerelease, draft, error):
    (tmp_path / "pyproject.toml").write_text(f'[project]\nname = "petrus-runtime"\nversion = "{version}"\n')
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"release": {"tag_name": tag, "prerelease": prerelease, "draft": draft}}))

    result = subprocess.run(
        [sys.executable, "-O", str(REPO_ROOT / "scripts/check-release.py")],
        cwd=tmp_path,
        env={**os.environ, "GITHUB_EVENT_PATH": str(event)},
        capture_output=True,
        text=True,
    )

    if error is None:
        assert result.returncode == 0, result.stderr
        assert result.stdout == f"Release matches petrus-runtime {version}\n"
    else:
        assert result.returncode != 0
        assert error in result.stderr
