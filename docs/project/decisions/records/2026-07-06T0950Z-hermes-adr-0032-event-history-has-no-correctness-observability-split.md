---
status: Decided
raised: 2026-07-06
decided: 2026-07-06
deciders:
  - henrique (Navigator, via grill-with-docs in the hermes notebook)
supersedes:
related:
  - hermes ADR 0032
  - docs/project/decisions/records/2026-07-06T1505Z-absorb-hermes-adrs-into-ariad.md
  - docs/project/decisions/records/2026-07-14T2016Z-activity-invocation-runtime-seam.md
---

> Migrated from the Hermes design notebook.

> Note 2026-07-14: the no-split principle stands untouched. The record kinds
> its examples mention follow the revised taxonomy of
> `2026-07-14T2016Z-activity-invocation-runtime-seam.md` — there is no
> handler-result record, and operational attempts live outside canonical
> history (see ADR 0031's supersession note).

# ADR 0032: Event history has no correctness/observability split

## Status

Accepted

## Context

ADR 0031 accepted a working minimal event history record model. A follow-up question asked which event history record categories are required for correctness and which are primarily for observability/debugging.

The answer is that this distinction is not useful for Petrus' semantic model.

In Petrus, observability is not an afterthought layered on top of execution. The event history is the semantic source of truth for process evolution. If a record explains how the process evolved, then it participates in correctness, replay, audit, debugging, and observability at the same time.

Implementations may still choose different indexing, projection, snapshotting, and archival strategies, but those are physical concerns, not a split in the semantic event model.

## Decision

Petrus will not classify event history record categories into separate "correctness" and "observability" groups.

The accepted event history categories are semantic records in one unified model. They explain process evolution and support correctness, replay, fork, audit, debugging, and observability together.

The meaningful distinction is not correctness versus observability. The meaningful distinction is:

- **semantic event history** — the conceptual timeline needed to explain process evolution;
- **physical storage representation** — how an implementation persists, indexes, projects, snapshots, archives, or materializes views over that timeline.

## Consequences

- No event history category is dismissed as "only observability" at the semantic level.
- Debuggability and auditability remain part of the design, not optional side channels.
- Implementations may derive projections, indexes, snapshots, summaries, and rollups from the canonical event history, but those derived views do not replace the canonical tracing log.
- Storage design can optimize query/runtime access without changing or compacting the canonical event model.
- Future API design should expose history as a coherent process timeline, not as separate correctness and telemetry streams.

## Example

A derived projection may summarize several semantic facts:

```txt
latest firing status projection:
  selected transition: transition:/review/run-review
  consumed tokens: [...]
  produced tokens: [...]
  handler result: ...
```

This does not mean token movement or handler result records are "observability only". It means a derived view summarized canonical log records for a particular query. The canonical log still preserves the original events.

## Open follow-up questions

- What projection/index/snapshot policies are acceptable?
- What retention/archive policy applies to long-running canonical logs?
- How do derived records link back to canonical event IDs?
- What are the minimal fields for each semantic event category?
