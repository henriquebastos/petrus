"""The published artifacts contain build inputs, never local territory."""

from __future__ import annotations

import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

from tests import REPO_ROOT

FORBIDDEN_PARTS = {".git", ".pytest_cache", ".ruff_cache", "__pycache__"}
FORBIDDEN_NAMES = {".coverage", "credentials.json", "secrets.json"}
FORBIDDEN_SUFFIXES = {".db", ".key", ".pyc", ".sqlite", ".sqlite3"}
SDIST_TOP_LEVEL = {".gitignore", "LICENSE", "PKG-INFO", "README.md", "pyproject.toml", "src"}


def _members(archive: Path) -> tuple[str, ...]:
    if archive.suffix == ".whl":
        with zipfile.ZipFile(archive) as wheel:
            return tuple(wheel.namelist())
    with tarfile.open(archive, "r:gz") as sdist:
        return tuple(sdist.getnames())


def _assert_safe_members(archive: Path) -> tuple[str, ...]:
    members = _members(archive)
    assert members, f"{archive.name} is empty"
    for member in members:
        path = PurePosixPath(member)
        assert not path.is_absolute(), f"{archive.name} contains absolute path {member!r}"
        assert ".." not in path.parts, f"{archive.name} contains traversal path {member!r}"
        assert not (set(path.parts) & FORBIDDEN_PARTS), f"{archive.name} contains runtime territory {member!r}"
        name = path.name
        assert name not in FORBIDDEN_NAMES, f"{archive.name} contains private artifact {member!r}"
        assert not (name == ".env" or (name.startswith(".env.") and name != ".env.example")), (
            f"{archive.name} contains environment artifact {member!r}"
        )
        assert path.suffix not in FORBIDDEN_SUFFIXES, f"{archive.name} contains private artifact {member!r}"
    return members


def test_wheel_and_sdist_contain_only_declared_source_and_pass_metadata_checks(tmp_path):
    sentinel = REPO_ROOT / "UNDECLARED_PACKAGE_SENTINEL.txt"
    assert not sentinel.exists(), f"refusing to overwrite existing {sentinel.name}"
    sentinel.write_text("An undeclared repository file must not enter a distribution.\n")
    try:
        subprocess.run(
            [sys.executable, "-m", "build", "--no-isolation", "--outdir", str(tmp_path)],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    finally:
        sentinel.unlink(missing_ok=True)

    [wheel] = tmp_path.glob("*.whl")
    [sdist] = tmp_path.glob("*.tar.gz")
    wheel_members = _assert_safe_members(wheel)
    sdist_members = _assert_safe_members(sdist)
    assert "petrus/__init__.py" in wheel_members
    assert "petrus/motus/_execution/gondolin_sidecar.mjs" in wheel_members
    assert any(member.endswith(".dist-info/METADATA") for member in wheel_members)
    wheel_paths = [PurePosixPath(member) for member in wheel_members]
    dist_info_roots = {path.parts[0] for path in wheel_paths if path.parts[0].endswith(".dist-info")}
    assert len(dist_info_roots) == 1
    assert all(path.parts[0] == "petrus" or path.parts[0] in dist_info_roots for path in wheel_paths)
    sdist_paths = [PurePosixPath(member) for member in sdist_members]
    assert {path.parts[1] for path in sdist_paths} == SDIST_TOP_LEVEL
    assert all(path.parts[:3] == (path.parts[0], "src", "petrus") for path in sdist_paths if path.parts[1] == "src")
    assert any(path.parts[1:] == ("src", "petrus", "__init__.py") for path in sdist_paths)
    assert all(path.name != sentinel.name for path in sdist_paths)

    subprocess.run(
        [sys.executable, "-m", "twine", "check", str(wheel), str(sdist)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
