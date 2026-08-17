#!/usr/bin/env python3
"""Replay one strict Petrus DST scenario artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dst_replay import load_scenario, replay_scenario


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", type=Path, help="strict petrus-dst-scenario JSON artifact")
    arguments = parser.parse_args()
    report = replay_scenario(load_scenario(arguments.scenario))
    print(json.dumps(report.as_dict(), allow_nan=False, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
