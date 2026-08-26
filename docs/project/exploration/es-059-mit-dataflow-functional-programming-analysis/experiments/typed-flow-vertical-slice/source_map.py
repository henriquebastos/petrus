"""Deterministic experiment-only source-map sidecar.

Canonical Net v3 intentionally excludes implementation bindings and source
provenance; this sidecar carries attribution beside — never inside — the
canonical bytes. It is bound to one exact definition by SHA-256 and is
byte-stable across repeated lowering.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass

from petrus.impetus.petrinet import Net

from algebra import CompositionError, SourceRef

FORMAT = "petrus-experiment-source-map"
VERSION = 1


@dataclass(frozen=True)
class SourceEntry:
    id: str
    file: str
    line: int
    symbol: str


@dataclass(frozen=True)
class ElementEntry:
    kind: str
    path: str
    source: str
    role: str


@dataclass(frozen=True)
class ScopeEntry:
    name: str
    source: str


@dataclass(frozen=True)
class SourceMapV1:
    definition_sha256: str
    sources: tuple[SourceEntry, ...]
    elements: tuple[ElementEntry, ...]
    lifecycle_scopes: tuple[ScopeEntry, ...]

    def element_for(self, path: str) -> ElementEntry | None:
        return next((element for element in self.elements if element.path == path), None)

    def source_for(self, source_id: str) -> SourceEntry | None:
        return next((source for source in self.sources if source.id == source_id), None)

    def scope_for(self, name: str) -> ScopeEntry | None:
        return next((scope for scope in self.lifecycle_scopes if scope.name == name), None)


def build_source_map(
    net: Net,
    sources: Mapping[str, SourceRef],
    ownership: Mapping[str, tuple[str, str]],
    scopes: tuple[tuple[str, str], ...],
    definition_bytes: bytes,
) -> SourceMapV1:
    """Join canonical topology to authored ownership, failing on any gap."""
    nodes = [("place", str(path)) for path in net.places] + [("transition", str(path)) for path in net.transitions]
    known_paths = {path for _, path in nodes}
    for path in ownership:
        if path not in known_paths:
            raise CompositionError(f"source ownership names {path!r}, which is not a canonical node")

    elements = []
    for kind, path in nodes:
        owner = ownership.get(path)
        if owner is None:
            raise CompositionError(f"canonical {kind} {path} has no authored source ownership")
        source_id, role = owner
        if source_id not in sources:
            raise CompositionError(f"{kind} {path} is owned by unknown source id {source_id!r}")
        elements.append(ElementEntry(kind, path, source_id, role))

    for name, source_id in scopes:
        if source_id not in sources:
            raise CompositionError(f"lifecycle scope {name!r} is owned by unknown source id {source_id!r}")

    return SourceMapV1(
        definition_sha256=hashlib.sha256(definition_bytes).hexdigest(),
        sources=tuple(
            SourceEntry(source_id, reference.file, reference.line, reference.symbol)
            for source_id, reference in sorted(sources.items())
        ),
        elements=tuple(sorted(elements, key=lambda element: (element.kind, element.path))),
        lifecycle_scopes=tuple(ScopeEntry(name, source_id) for name, source_id in sorted(scopes)),
    )


def serialize_source_map(source_map: SourceMapV1) -> bytes:
    """Deterministically serialize the sidecar: UTF-8, two-space indent, final newline."""
    document = {
        "format": FORMAT,
        "version": VERSION,
        "definition_sha256": source_map.definition_sha256,
        "sources": [
            {"id": entry.id, "file": entry.file, "line": entry.line, "symbol": entry.symbol}
            for entry in source_map.sources
        ],
        "elements": [
            {"kind": entry.kind, "path": entry.path, "source": entry.source, "role": entry.role}
            for entry in source_map.elements
        ],
        "lifecycle_scopes": [{"name": entry.name, "source": entry.source} for entry in source_map.lifecycle_scopes],
    }
    return (json.dumps(document, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode("utf-8")


def parse_source_map(payload: bytes) -> SourceMapV1:
    """Reconstruct a sidecar value from its exact serialized bytes."""
    document = json.loads(payload.decode("utf-8"))
    if document.get("format") != FORMAT or document.get("version") != VERSION:
        raise ValueError(f"not a {FORMAT} v{VERSION} document")
    return SourceMapV1(
        definition_sha256=document["definition_sha256"],
        sources=tuple(SourceEntry(**entry) for entry in document["sources"]),
        elements=tuple(ElementEntry(**entry) for entry in document["elements"]),
        lifecycle_scopes=tuple(ScopeEntry(**entry) for entry in document["lifecycle_scopes"]),
    )
