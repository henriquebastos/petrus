---
status: Decided
raised: 2026-07-06
decided: 2026-07-06
deciders:
  - henrique (Navigator, via grill-with-docs in the hermes notebook)
supersedes:
related:
  - hermes ADR 0033
  - docs/project/decisions/records/2026-07-06T1505Z-absorb-hermes-adrs-into-ariad.md
  - docs/project/decisions/records/2026-07-14T2016Z-activity-invocation-runtime-seam.md
---

> Migrated from the Hermes design notebook.

> Note 2026-07-14: the uncompacted-log principle stands untouched. The example
> record list below predates
> `2026-07-14T2016Z-activity-invocation-runtime-seam.md`: "activity attempt
> recorded" and "handler result recorded" left canonical history — the
> canonical activity records are the frozen `ActivityRequested` and terminal
> `ActivityCompleted`/`ActivityFailed` (see ADR 0031's supersession note).

# ADR 0033: Canonical event history is an uncompacted tracing log

## Status

Accepted

## Context

ADR 0030 established that all transition firings belong to one unified event history. ADR 0031 established a minimal semantic event history record model. ADR 0032 clarified that event history categories should not be split into correctness versus observability records.

A remaining question was whether physical storage may compact multiple semantic event records into summarized rows.

The answer is that Petrus should treat event history as a tracing log. Its value is not only immediate execution, but also later analysis, monitoring, replay, debugging, forking, process mining, visualization, and out-of-scope future tooling.

Compacting the canonical event history too early would destroy information that future tools may need.

## Decision

The canonical event history should be append-only and uncompacted.

Petrus should record semantic event history as a trace/log of what happened, preserving individual event records rather than compacting them into summary rows.

Derived projections, indexes, snapshots, summaries, materialized views, and rollups are allowed, but they are not the canonical event history.

## Consequences

- Event history remains maximally useful for later analysis and monitoring.
- Observability, replay, process mining, debugging, and audit can build from the same raw trace.
- Runtime performance should be improved with projections/indexes/snapshots, not by destroying the canonical log.
- Storage growth becomes an explicit operational concern.
- Retention/export/archive policy may be needed later, but that is separate from semantic compaction.
- The canonical event history is the source of truth; derived views are disposable/rebuildable.

## Important distinction

Allowed:

```txt
canonical event log -> projection/index/snapshot/summary
```

Not allowed as the canonical representation:

```txt
semantic event records -> compacted summary only
```

## Examples

Canonical event history may contain separate records:

```txt
external event recorded
firing candidate selected
firing begun
tokens consumed/read/accounted
activity scheduled/requested
activity attempt recorded
activity completed
handler result recorded
tokens produced
firing completed
```

A runtime may additionally maintain a projection:

```txt
current marking by place
active firing attempts
latest status by net instance
worker queue backlog
transition latency histogram
```

Those projections can be rebuilt from the canonical log and should not replace it.

## Open follow-up questions

- What retention/archive policies should exist for long-running systems?
- Are snapshots part of the canonical history or derived artifacts referenced by history?
- What indexes are required for efficient runtime execution?
- What event schemas/fields are required for future analysis and monitoring?
