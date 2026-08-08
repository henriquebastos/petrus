"""
Structural code conventions, enforced by ast-grep.

The rules live declaratively under ``rules/*.yml`` (discovered via ``sgconfig.yml``).
This test runs ``ast-grep scan`` over the codebase and fails on any error-severity
match, so conventions are gated by the same ``uv run pytest`` green bar as the rest
of the suite. A coverage test also requires every production module to occur in a
rule's ``files`` inventory or in the reviewed exemption manifest below.

The Petrinet and Binding rules enforce the canonical concept dependencies;
the coverage test keeps every production module covered or explicitly exempt.
"""

from __future__ import annotations

# Python imports
import subprocess
from glob import glob
from pathlib import Path

from tests import REPO_ROOT

REPO = REPO_ROOT
SOURCE_ROOT = REPO / "src" / "petrus"
RULES_ROOT = REPO / "rules"

# These modules are deliberately outside the current architectural rules. Keep
# this manifest exact: adding a production module requires either an ast-grep
# files path/glob or an explicit reviewed rationale here.
STRUCTURAL_RULE_EXEMPTIONS = {
    "src/petrus/__init__.py": "Empty project namespace; concepts are imported from their defining modules.",
    "src/petrus/telemetry.py": "Orthogonal leaf with no architectural imports to constrain.",
}


def _rule_file_patterns(rule: Path) -> tuple[str, ...]:
    """Read the simple top-level ``files`` list used by every local rule."""
    patterns = []
    in_files = False
    for line in rule.read_text().splitlines():
        if line == "files:":
            in_files = True
            continue
        if in_files and line.startswith("  - "):
            patterns.append(line.removeprefix("  - ").strip("'\""))
        elif in_files and line and not line.startswith(" "):
            break
    return tuple(patterns)


def test_every_production_module_has_structural_rule_coverage_or_rationale():
    modules = {path.relative_to(REPO).as_posix() for path in SOURCE_ROOT.rglob("*.py")}
    covered = set()
    for rule in RULES_ROOT.glob("*.yml"):
        for pattern in _rule_file_patterns(rule):
            covered.update(
                Path(path).relative_to(REPO).as_posix() for path in glob(str(REPO / pattern), recursive=True)
            )

    exemptions = set(STRUCTURAL_RULE_EXEMPTIONS)
    assert exemptions <= modules, f"stale structural-rule exemptions: {sorted(exemptions - modules)}"
    assert not (covered & exemptions), f"remove exemptions now covered by rules: {sorted(covered & exemptions)}"
    assert modules <= covered | exemptions, (
        "production modules without an ast-grep files path/glob or explicit rationale: "
        f"{sorted(modules - covered - exemptions)}"
    )


def test_concept_rules_name_canonical_forbidden_dependencies():
    expected = {
        "activity-is-a-leaf.yml": {"binding", "dispatch"},
        "binding-dependencies.yml": {"dispatch"},
        "petrinet-is-independent.yml": {"dispatch"},
        "history-store-boundary.yml": {"dispatch"},
        "history-store-postgres-provider-boundary.yml": {"dispatch", "fabric", "processes"},
        "core-no-runtime-imports.yml": {"history_store", "dispatch", "_coordination"},
    }
    for name, dependencies in expected.items():
        rule = (RULES_ROOT / name).read_text()
        regexes = "\n".join(line for line in rule.splitlines() if "regex:" in line)
        missing = dependencies - {dependency for dependency in dependencies if dependency in regexes}
        assert not missing, f"{name} does not forbid canonical dependencies: {sorted(missing)}"


def test_structural_conventions_hold():
    result = subprocess.run(
        ["ast-grep", "scan"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"ast-grep found convention violations:\n{result.stdout}{result.stderr}"


def test_structural_rule_fixtures_hold():
    result = subprocess.run(
        ["ast-grep", "test", "--skip-snapshot-tests"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"ast-grep rule fixtures failed:\n{result.stdout}{result.stderr}"
