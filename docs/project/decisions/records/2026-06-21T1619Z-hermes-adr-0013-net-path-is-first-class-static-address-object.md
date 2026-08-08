---
status: Superseded
raised: 2026-06-21
decided: 2026-06-21
deciders:
  - henrique (Navigator, via grill-with-docs in the hermes notebook)
supersedes:
related:
  - hermes ADR 0013
  - docs/project/decisions/records/2026-07-06T1505Z-absorb-hermes-adrs-into-ariad.md
  - superseded by docs/project/decisions/records/2026-06-21T1633Z-hermes-adr-0014-net-path-addresses-place-and-transition-nodes.md
---

> Migrated from the Hermes design notebook.

> Superseded by hermes ADR 0014, migrated as docs/project/decisions/records/2026-06-21T1633Z-hermes-adr-0014-net-path-addresses-place-and-transition-nodes.md.

# ADR 0013: Net path is a first-class static address object

## Status

Superseded by ADR 0014

## Context

Petrus needs a way to address places, transitions, arcs, and nested components inside composed nets. A previous implementation used a dotted path to identify nodes within nested/subnet structure and to construct arcs and bindings.

One proposal separated stable opaque node IDs from human-readable paths. The user rejected this for now: net paths should not be treated as dynamic aliases that change independently from the process. A Petrus process instance is tied to a specific net plus execution runtime. Renames or structural changes should require reloading or migrating the net and validating all references.

The inspiration is Python's `pathlib.Path`: not necessarily for filesystem resolution behavior, but for having a real path object with formatting, composition, parent/child relationships, and structured manipulation.

## Decision

Petrus should treat net path as a first-class object, not merely an arbitrary string.

A net path is the static address of a node or component within a net definition. Net paths may have a string representation, but code should be able to compose, inspect, and manipulate them as structured objects.

Net paths are validated strictly when loading or instantiating a net. If a handler binding, arc reference, subnet reference, or configuration refers to a missing or invalid net path, validation should fail.

Renaming or moving nodes changes the net definition and should require reloading, validation, and eventually explicit migration support for existing process instances.

The net runtime may impose strict binding rules, such as allowing only one handler per transition.

## Consequences

- Net path becomes an important part of the net schema model.
- Users can still author path-like strings, but internally Petrus should treat paths as structured values.
- Composition APIs can build child paths safely rather than concatenating strings.
- Binding validation becomes strict and early.
- Refactors that rename or move nodes are real net changes, not transparent alias updates.
- Future migration/versioning support must account for net path changes.

## Notes

Possible capabilities for a `NetPath` object:

- create root path;
- append child segment;
- get parent;
- get basename/last segment;
- compare ancestry;
- render canonical string;
- parse from canonical string;
- validate segment syntax;
- join subnet path with exported node path.
