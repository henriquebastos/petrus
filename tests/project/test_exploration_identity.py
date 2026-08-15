"""Exploratory Story identifiers remain repository-global and monotonic."""

from __future__ import annotations

import re
from pathlib import Path

from tests import REPO_ROOT

EXPLORATION_ROOT = REPO_ROOT / "docs" / "project" / "exploration"


def _frontmatter(path: Path) -> str:
    parts = path.read_text().split("---", 2)
    assert len(parts) == 3 and parts[0] == "", f"{path.relative_to(REPO_ROOT)} has no frontmatter"
    return parts[1]


def _es_field(metadata: str, name: str) -> int:
    match = re.search(rf"^{name}: ES-(\d+)$", metadata, re.MULTILINE)
    assert match is not None, f"missing {name}: ES-<N>"
    return int(match.group(1))


def test_exploration_codes_continue_after_the_reserved_historical_namespace() -> None:
    allocation = _frontmatter(EXPLORATION_ROOT / "index.md")
    historical_high_water = _es_field(allocation, "historical_high_water")
    next_code = _es_field(allocation, "next_code")
    story_codes = []

    for story_index in sorted(EXPLORATION_ROOT.glob("es-*/index.md")):
        directory_match = re.fullmatch(r"es-(\d+)-[a-z0-9]+(?:-[a-z0-9]+)*", story_index.parent.name)
        assert directory_match is not None, f"invalid Exploration directory: {story_index.parent.name}"
        directory_code = int(directory_match.group(1))
        recorded_code = _es_field(_frontmatter(story_index), "code")
        assert recorded_code == directory_code, f"{story_index.parent.name} records ES-{recorded_code:03d}"
        story_codes.append(recorded_code)

    expected_codes = list(range(historical_high_water + 1, next_code))
    assert sorted(story_codes) == expected_codes, (
        "post-baseline Exploration codes must be unique and contiguous; "
        f"expected {expected_codes}, found {sorted(story_codes)}"
    )
