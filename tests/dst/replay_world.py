"""Replay a strict executable-world artifact through the public Engine profile."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from petrus.testing.dst import ScenarioRegistry, load_artifact, replay
from tests.dst.delayed_world import DelayedAuthorityChecker, DelayedEngineProfile
from tests.dst.delivery_world import DeliveryAuthorityChecker, DeliveryEngineProfile
from tests.dst.engine_world import (
    AcceptedCommitAuthorityChecker,
    CommitAuthorityChecker,
    EngineHistoryChecker,
    EngineProfile,
    HistoryAckLossEngineProfile,
    HistoryRefusalEngineProfile,
    ResourceBoundedEngineProfile,
    TerminalRefusalChecker,
)
from tests.dst.lifecycle_world import LifecycleAuthorityChecker, LifecycleEngineProfile
from tests.dst.retry_world import (
    RetryAuthorityChecker,
    RetryEngineProfile,
    TerminalAuthorityChecker,
    TerminalEngineProfile,
)
from tests.dst.timer_world import TimerAuthorityChecker, TimerEngineProfile


def replay_path(path: Path):
    with TemporaryDirectory(prefix="petrus-dst-world-") as directory:
        registry = ScenarioRegistry()
        registry.register_profile(DelayedEngineProfile(Path(directory) / "delayed-history.jsonl"))
        registry.register_profile(DeliveryEngineProfile(Path(directory) / "delivery-history.jsonl"))
        registry.register_profile(EngineProfile(Path(directory) / "projection-history.jsonl"))
        registry.register_profile(HistoryAckLossEngineProfile(Path(directory) / "history-ack-loss.jsonl"))
        registry.register_profile(HistoryRefusalEngineProfile(Path(directory) / "history-refusal.jsonl"))
        registry.register_profile(ResourceBoundedEngineProfile(Path(directory) / "resource-history.jsonl"))
        registry.register_profile(LifecycleEngineProfile(Path(directory) / "lifecycle-history.jsonl"))
        registry.register_profile(
            RetryEngineProfile(
                Path(directory) / "retry-history.jsonl",
                Path(directory) / "retry-dispatch.db",
            )
        )
        registry.register_profile(
            TerminalEngineProfile(
                Path(directory) / "terminal-history.jsonl",
                Path(directory) / "terminal-dispatch.db",
            )
        )
        registry.register_profile(TimerEngineProfile(Path(directory) / "timer-history.jsonl"))
        registry.register_checker(AcceptedCommitAuthorityChecker())
        registry.register_checker(CommitAuthorityChecker())
        registry.register_checker(DelayedAuthorityChecker())
        registry.register_checker(DeliveryAuthorityChecker())
        registry.register_checker(EngineHistoryChecker())
        registry.register_checker(LifecycleAuthorityChecker())
        registry.register_checker(RetryAuthorityChecker())
        registry.register_checker(TerminalAuthorityChecker())
        registry.register_checker(TerminalRefusalChecker())
        registry.register_checker(TimerAuthorityChecker())
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
