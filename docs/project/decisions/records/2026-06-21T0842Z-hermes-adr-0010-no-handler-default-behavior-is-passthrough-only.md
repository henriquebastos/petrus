---
status: Decided
raised: 2026-06-21
decided: 2026-06-21
deciders:
  - henrique (Navigator, via grill-with-docs in the hermes notebook)
supersedes:
related:
  - hermes ADR 0010
  - docs/project/decisions/records/2026-07-06T1505Z-absorb-hermes-adrs-into-ariad.md
---

> Migrated from the Hermes design notebook.

# ADR 0010: No-handler default behavior is passthrough only

## Status

Accepted

## Context

Petrus may allow transitions without explicit handlers. A previous exploratory idea considered default no-handler behavior for passthrough, packing, unpacking, filtering, forwarding, and projection.

However, Petri nets are already difficult for many developers to grasp. If Petrus adds too much implicit inference or a complex inscription DSL, the API may become too hard to start with and too magical to inspect.

The user wants typed handlers and simple handlers separated from the net schema. The net schema should remain simple, and richer data shaping should happen in explicit typed handlers or simple handler functions rather than through hidden inference.

## Decision

A transition with no handler symbol declared has exactly one default behavior: passthrough.

Petrus should not infer packing, unpacking, filtering, forwarding, projection, or fan-out from arbitrary input/output shapes.

For anything other than passthrough, the user must provide explicit behavior, preferably as a typed handler or simple handler separated from the net schema.

## Consequences

- The no-handler mental model stays simple.
- Petrus avoids hidden inference and surprising data transformations.
- The net schema remains focused on process structure rather than becoming a complex data transformation language.
- Typed handlers become the primary ergonomic tool for shaping data beyond passthrough.
- Petrus still supports simple dataflow nets where transitions only move tokens forward.

## Notes

Passthrough should still be precisely defined before implementation. For example, Petrus must decide what happens when there are multiple input tokens, multiple output places, or type mismatches. Until then, passthrough should be treated as the only intended default behavior, not as a broad inference system.
