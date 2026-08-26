"""Join canonical History to the source-map sidecar, and name the branch that answered.

v1's ``explain`` module is reused whole and unmodified: this experiment produces
the same record types over the same sidecar shape, so the attribution rules,
occurrence grouping, and serialization are already right.

The one addition is ``decisions``: because every ordered-choice branch is its own
transition, "which rule answered this observation" is already in canonical
History — the transition path *is* the branch id. That is the durable
"why nothing happened" spelling experiment B bought with four extra transitions
and an unprovable exclusivity obligation, and A could not produce at all.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from petrus.impetus.history import FiringCompleted, Record

from explain import explain_history as _explain_history, serialize_explained, unattributed_records
from source_map import SourceMapV1

FORMAT = "petrus-experiment-explained-history"
VERSION = 1

__all__ = [
    "FORMAT",
    "VERSION",
    "decisions",
    "explain_history",
    "serialize_explained",
    "unattributed_records",
]


def decisions(records: Sequence[Record], source_map: SourceMapV1, prefix: str = "decide.") -> list[dict[str, object]]:
    """One row per decision firing: the branch that answered, and why, from durable data alone."""
    rows: list[dict[str, object]] = []
    for record in records:
        if not isinstance(record, FiringCompleted):
            continue
        path = str(record.transition)
        if not path.startswith(prefix):
            continue
        element = source_map.element_for(path)
        if element is None:  # pragma: no cover - the sidecar covers every canonical node
            raise ValueError(f"decision firing at {path} has no source-map element")
        entry = source_map.source_for(element.source)
        if entry is None:  # pragma: no cover - build_source_map refuses an unknown owner
            raise ValueError(f"decision element {path} names unknown source {element.source!r}")
        rows.append(
            {
                "occurrence": record.occurrence,
                "branch": path.removeprefix(prefix),
                "transition": path,
                "role": element.role,
                "source": {"file": entry.file, "line": entry.line, "symbol": entry.symbol},
            }
        )
    return rows


def explain_history(records: Sequence[Record], source_map: SourceMapV1) -> dict[str, object]:
    """v1's attributed projection plus the branch-level decision index."""
    document = _explain_history(records, source_map)
    document["decisions"] = cast("object", decisions(records, source_map))
    return document
