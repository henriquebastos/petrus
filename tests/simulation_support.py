"""Test-owned fixed scenario construction and atomic simulation export."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile

from petrus.impetus.dsl import BuiltNet, NetSpec, arc
from petrus.impetus.petrinet import Cel, Delay, Marking, NetPath, Token
from petrus.simulation import simulate


def build_scenario() -> tuple[BuiltNet, Marking]:
    spec = NetSpec("bounded-simulation-demo", completion=Cel("size(done) > 0"))
    spec.p.pending(color="SimulationItem")
    spec.p.done(color="SimulationItem")
    spec.t.finish(guards=Cel("size(pending) > 0"), timers=(Delay(5),))
    spec.p.pending >> arc(filter=Cel("priority >= 1")) >> spec.t.finish >> spec.p.done
    marking = Marking({NetPath("pending"): (Token("SimulationItem", {"id": "demo-1", "priority": 2, "typed": True}),)})
    return spec.build(), marking


def export(destination: Path, *, max_actions: int = 32) -> None:
    built, marking = build_scenario()
    payload = simulate(built, marking, max_actions=max_actions)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, prefix=f".{destination.name}.", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


__all__ = ["build_scenario", "export"]
