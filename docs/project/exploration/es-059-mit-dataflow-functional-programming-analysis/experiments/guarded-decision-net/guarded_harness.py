"""The small assembly v1's ``harness`` does not offer: a selection-policy door.

Every runtime helper this experiment needs is v1's — ``create``, ``load``,
``drain``, ``deliver_head``, ``deliver_ci``, ``value_at``, ``values_at`` and
``FakeProviderLedger`` are imported from ``../typed-flow-vertical-slice``
unchanged. The one thing v1 never needed is the ability to compose an Engine
under a **non-default selection policy**, which is exactly what the
overlapping-guard counterexample must vary to show whether a rung conflict is
resolved by the domain or by runtime configuration.

This module contains no semantic decision. It only composes public doors.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from petrus.engine import Engine
from petrus.impetus.history import FiringBegun, Record
from petrus.impetus.history_store.jsonl import JsonlHistoryStore
from petrus.impetus.petrinet import Marking
from petrus.impetus.selection import SelectionPipeline, SelectionPolicy
from petrus.motus.dispatch import InlineDispatch

from lowering import CompiledFlow

INSTANCE = "guarded-readiness-slice"


def create_selecting(
    compiled: CompiledFlow,
    history_path: Path | str,
    *,
    selection: SelectionPolicy | None = None,
    marking: Marking | None = None,
) -> Engine:
    """Create one effect-free Instance under an explicit selection policy.

    ``None`` composes the Engine's own default, ``SelectionPipeline()``, so
    the two counterexample runs differ in exactly one argument.

    Used only by the counterexample flows, which route to terminals and
    declare no Activity, so an empty ``InlineDispatch`` is the honest seam.
    """
    return Engine.create(
        compiled.built.net,
        INSTANCE,
        history=JsonlHistoryStore(history_path),
        dispatch=InlineDispatch({}),
        handlers=dict(compiled.handlers),
        guards=dict(compiled.guards),
        activities=(),
        marking=compiled.initial_marking if marking is None else marking,
        selection=SelectionPipeline() if selection is None else selection,
    )


def fired_transitions(records: Sequence[Record]) -> tuple[str, ...]:
    """Every begun firing's transition path, in canonical History order."""
    return tuple(str(record.transition) for record in records if isinstance(record, FiringBegun))


def fired_rungs(records: Sequence[Record], branch: str) -> tuple[str, ...]:
    """Only the rung firings of one branch, named by rung id, in History order."""
    prefix = f"{branch}."
    return tuple(
        path.removeprefix(prefix).removesuffix(".fire")
        for path in fired_transitions(records)
        if path.startswith(prefix) and path.endswith(".fire")
    )


__all__ = ["INSTANCE", "create_selecting", "fired_rungs", "fired_transitions"]
