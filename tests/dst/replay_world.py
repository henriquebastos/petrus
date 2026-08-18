"""Replay a strict executable-world artifact through the public Engine profile."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from petrus.testing.dst import ScenarioRegistry, load_artifact, replay
from tests.dst.engine_world import (
    CommitAuthorityChecker,
    EngineHistoryChecker,
    EngineProfile,
    HistoryRefusalEngineProfile,
    TerminalRefusalChecker,
)


def replay_path(path: Path):
    with TemporaryDirectory(prefix="petrus-dst-world-") as directory:
        registry = ScenarioRegistry()
        registry.register_profile(EngineProfile(Path(directory) / "projection-history.jsonl"))
        registry.register_profile(HistoryRefusalEngineProfile(Path(directory) / "history-refusal.jsonl"))
        registry.register_checker(CommitAuthorityChecker())
        registry.register_checker(EngineHistoryChecker())
        registry.register_checker(TerminalRefusalChecker())
        return replay(load_artifact(path), registry)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    arguments = parser.parse_args()
    result = replay_path(arguments.artifact)
    print(json.dumps(result.model_dump(mode="json"), allow_nan=False, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
