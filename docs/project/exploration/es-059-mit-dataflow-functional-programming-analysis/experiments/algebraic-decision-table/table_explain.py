"""Case-aware explained History.

v1's ``explain.explain_history`` already attributes every canonical record to
an authored node. This projection adds the one thing the case table makes
possible: naming the **rung that fired** inside the single decision firing.

The join is honest about its limit. A decision firing is identified in
History by the colors it produced, so a rung is nameable exactly when its
emitted color identifies it uniquely. Every ``.drop()`` rung produces only the
state token, so all four absorbing rungs of this flow look identical in
canonical History; the projection reports them as an explicit candidate set
rather than guessing. That is a finding about what a runtime log can carry,
not a defect of the table — see ``report.md`` §6.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import cast

from petrus.impetus.history import Record

from explain import explain_history
from source_map import SourceMapV1
from table_lowering import TableCompiledFlow

FORMAT = "petrus-experiment-explained-history-cases"
VERSION = 1


def _source_entry(source_map: SourceMapV1, source_id: str) -> dict[str, object]:
    entry = source_map.source_for(source_id)
    if entry is None:
        raise ValueError(f"source id {source_id!r} is not in the source map")
    return {"id": entry.id, "file": entry.file, "line": entry.line, "symbol": entry.symbol}


def _authored_table(compiled: TableCompiledFlow, source_map: SourceMapV1) -> list[dict[str, object]]:
    return [
        {
            "case": entry.case_id,
            "when": entry.when,
            "fold": entry.fold,
            "emit": entry.emit,
            "emits": entry.emit_color,
            "source": _source_entry(source_map, entry.source_id),
        }
        for entry in compiled.cases
    ]


def _produced_colors(group: dict[str, object]) -> list[str]:
    colors: list[str] = []
    for produced in cast("list[dict[str, object]]", group.get("produced", [])):
        for token in cast("list[dict[str, object]]", produced["tokens"]):
            colors.append(cast(str, token["color"]))
    return colors


def explain_history_with_cases(
    records: Sequence[Record],
    source_map: SourceMapV1,
    compiled: TableCompiledFlow,
) -> dict[str, object]:
    """v1's explained History plus per-firing case attribution."""
    document = explain_history(records, source_map)
    decision_path = compiled.cases[0].match_id if compiled.cases else None
    absorbing = [entry.case_id for entry in compiled.absorbing_cases]

    for group in cast("list[dict[str, object]]", document["occurrences"]):
        if group.get("transition") != decision_path:
            continue
        named = None
        for color in _produced_colors(group):
            attribution = compiled.case_for_color(color)
            if attribution is not None:
                named = attribution
                break
        if named is None:
            # Absorption: only the state token moved, so the produced colors
            # cannot distinguish these rungs from one another.
            group["case"] = None
            group["case_candidates"] = absorbing
        else:
            group["case"] = {
                "case": named.case_id,
                "when": named.when,
                "fold": named.fold,
                "emit": named.emit,
                "emits": named.emit_color,
                "source": _source_entry(source_map, named.source_id),
            }
            group["case_candidates"] = [named.case_id]

    return {
        "format": FORMAT,
        "version": VERSION,
        "definition_sha256": source_map.definition_sha256,
        "decision_transition": decision_path,
        "cases": _authored_table(compiled, source_map),
        "entries": document["entries"],
        "occurrences": document["occurrences"],
    }


def case_attribution_gaps(document: dict[str, object]) -> tuple[str, ...]:
    """Name every decision firing whose fired rung is not uniquely identified."""
    gaps = []
    for group in cast("list[dict[str, object]]", document["occurrences"]):
        if group.get("transition") != document["decision_transition"]:
            continue
        if group.get("case") is None:
            candidates = cast("list[str]", group.get("case_candidates", []))
            gaps.append(f"occurrence {group['occurrence']}: absorbed, one of {candidates}")
    return tuple(gaps)


def serialize_explained_cases(document: dict[str, object]) -> bytes:
    return (json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")
