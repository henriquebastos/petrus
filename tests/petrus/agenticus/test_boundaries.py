"""Executable ownership and dependency boundaries for Agenticus."""

from __future__ import annotations

import ast
import importlib
import subprocess
import sys
from pathlib import Path

from tests import REPO_ROOT

OWNERSHIP_PACKAGES = (
    "connection",
    "program",
    "thread",
    "runtime",
    "hands",
    "attachment",
    "effect",
    "catalog",
)
AGENTICUS_ROOT = REPO_ROOT / "src" / "petrus" / "agenticus"
AGENTICUS_TEST_ROOT = REPO_ROOT / "tests" / "petrus" / "agenticus"


def _imports(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(), filename=str(path.relative_to(REPO_ROOT)))
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.append(node.module)
            modules.extend(f"{node.module}.{alias.name}" for alias in node.names)
    return tuple(modules)


def test_exact_ownership_packages_have_empty_namespaces() -> None:
    assert {path.name for path in AGENTICUS_ROOT.iterdir() if path.is_dir() and not path.name.startswith("_")} == set(
        OWNERSHIP_PACKAGES
    )
    assert {
        path.name for path in AGENTICUS_TEST_ROOT.iterdir() if path.is_dir() and not path.name.startswith("_")
    } == set(OWNERSHIP_PACKAGES) | {"conformance"}
    for path in (AGENTICUS_ROOT, *(AGENTICUS_ROOT / name for name in OWNERSHIP_PACKAGES)):
        module = importlib.import_module(".".join(path.relative_to(REPO_ROOT / "src").parts))
        assert module.__all__ == []
        tree = ast.parse((path / "__init__.py").read_text())
        assert len(tree.body) == 1 and isinstance(tree.body[0], ast.Assign)


def test_root_import_has_no_facade_or_optional_provider_side_effects() -> None:
    packages = ", ".join(repr(f"petrus.agenticus.{name}") for name in OWNERSHIP_PACKAGES)
    code = f"""
import importlib
import sys
root = importlib.import_module('petrus.agenticus')
assert not [name for name in vars(root) if not name.startswith('_')]
for package in ({packages},):
    importlib.import_module(package)
for forbidden in ('anthropic', 'claude_agent_sdk', 'e2b', 'openai'):
    assert forbidden not in sys.modules
"""
    subprocess.run([sys.executable, "-c", code], check=True)


def test_impetus_and_motus_do_not_depend_on_agenticus() -> None:
    for owner in ("impetus", "motus"):
        for path in (REPO_ROOT / "src" / "petrus" / owner).rglob("*.py"):
            assert not any(
                module == "petrus.agenticus" or module.startswith("petrus.agenticus.") for module in _imports(path)
            ), path


def test_agenticus_does_not_import_private_motus_or_its_own_root_facade() -> None:
    for path in AGENTICUS_ROOT.rglob("*.py"):
        imports = _imports(path)
        assert not any(
            module == "petrus.motus._execution" or module.startswith("petrus.motus._execution.") for module in imports
        ), path
        assert "petrus.agenticus" not in imports, path


def test_forbidden_universal_concepts_are_not_defined() -> None:
    forbidden = {"Agent", "Session"}
    for path in AGENTICUS_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path.relative_to(REPO_ROOT)))
        definitions = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        }
        assert not definitions & forbidden, path
