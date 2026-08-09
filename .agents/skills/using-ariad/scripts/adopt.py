#!/usr/bin/env python3
"""Safely adopt Ariad project templates. This does not migrate or update them."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

READY, ALREADY, MANUAL_AGENTS, COLLISION = 0, 0, 3, 4
ASSETS = Path(__file__).resolve().parents[1] / "assets/project-templates"
INTEGRATION_MARKER = b"<!-- ariad-entrypoint: docs/ariad/index.md -->"
INTEGRATION_DIRECTIVE = b"@docs/ariad/index.md"

def files() -> list[tuple[Path, Path]]:
    return [(p, p.relative_to(ASSETS)) for p in sorted(ASSETS.rglob("*")) if p.is_file()]

def integrated_agents(data: bytes) -> bool:
    lines = {line.strip() for line in data.splitlines()}
    return INTEGRATION_MARKER in lines and INTEGRATION_DIRECTIVE in lines

def collision(destination: Path, target: Path) -> str | None:
    """Return the first unsafe destination component (cooperative local CLI safety)."""
    for parent in destination.parents:
        if parent == target:
            break
        if parent.is_symlink() or (parent.exists() and not parent.is_dir()):
            return f"destination parent collides: {parent.relative_to(target)}"
    if destination.is_symlink():
        return f"destination is a symlink: {destination.relative_to(target)}"
    if destination.exists():
        return f"destination already exists: {destination.relative_to(target)}"
    return None

def create_exclusive(destination: Path, data: bytes) -> None:
    """Create a file without truncation; callers must also recheck its parents."""
    with destination.open("xb") as stream:
        stream.write(data)

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path, help="target repository path")
    parser.add_argument("--apply", action="store_true", help="write after a successful preflight")
    args = parser.parse_args()
    target = args.target.expanduser().resolve()
    if not target.is_dir():
        print(f"error: target repository is not a directory: {target}", file=sys.stderr)
        return 2

    pending: list[tuple[Path, bytes]] = []
    present = 0
    for source, rel in files():
        destination = target / rel
        data = source.read_bytes()
        parent_problem = collision(destination, target)
        if parent_problem and not destination.exists() and not destination.is_symlink():
            print(f"manual integration required: {parent_problem}", file=sys.stderr)
            return COLLISION
        if destination.is_symlink():
            print(f"manual integration required: destination is a symlink: {rel}", file=sys.stderr)
            return COLLISION
        if destination.exists():
            if not destination.is_file() or destination.read_bytes() != data:
                if rel.as_posix() == "AGENTS.md" and destination.is_file():
                    if integrated_agents(destination.read_bytes()):
                        present += 1
                        continue
                    print("manual integration required: existing AGENTS.md does not clearly integrate Ariad", file=sys.stderr)
                    print("Add this block without removing project-owned instructions:\n\n<!-- ariad-entrypoint: docs/ariad/index.md -->\n@docs/ariad/index.md\nIf the @path directive is not expanded by this runtime, read `docs/ariad/index.md` directly before meaningful work.", file=sys.stderr)
                    return MANUAL_AGENTS
                print(f"manual integration required: destination differs: {rel}", file=sys.stderr)
                return COLLISION
            present += 1
        else:
            pending.append((destination, data))

    if not pending:
        print(f"already adopted: all {present} template files are present")
        return ALREADY
    print(f"ready: {len(pending)} files to create, {present} already present ({'apply' if args.apply else 'dry-run'})")
    for destination, _ in pending:
        print(f"  create {destination.relative_to(target)}")
    if not args.apply:
        return READY
    for destination, data in pending:
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            problem = collision(destination, target)
            if problem:
                raise FileExistsError(problem)
            create_exclusive(destination, data)
        except (FileExistsError, FileNotFoundError, NotADirectoryError, IsADirectoryError, OSError) as exc:
            print(f"manual integration required: creation collision at {destination.relative_to(target)}: {exc}", file=sys.stderr)
            return COLLISION
    print("adoption applied")
    return READY

if __name__ == "__main__":
    raise SystemExit(main())
