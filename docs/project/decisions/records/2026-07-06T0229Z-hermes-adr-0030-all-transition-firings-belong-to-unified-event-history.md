---
status: Decided
raised: 2026-07-06
decided: 2026-07-06
deciders:
  - henrique (Navigator, via grill-with-docs in the hermes notebook)
supersedes:
related:
  - hermes ADR 0030
  - docs/project/decisions/records/2026-07-06T1505Z-absorb-hermes-adrs-into-ariad.md
---

> Migrated from the Hermes design notebook.

# ADR 0030: All transition firings belong to unified event history

## Status

Accepted

## Context

Petrus aims to break implicit agent loops into explicit event-backed coordination. A recent design reflection separated concepts that current agent systems often collapse into one process:

- context;
- loop;
- history;
- queue;
- worker;
- Petri-net dynamics.

This raised an important question: should only external/side-effecting transition work appear in event history, or should every transition firing — including passthrough and deterministic internal transitions — participate in the same semantic history model?

If passthrough transitions are treated as outside history, the runtime gains a possible optimization but loses a uniform timeline. If every firing is history-visible at the semantic level, Petrus gets a single source of truth for observability, replay, fork, debugging, and meta-workflows.

## Decision

Every transition firing is semantically part of one unified event history.

This includes:

- passthrough transitions;
- deterministic/internal transitions;
- handled transitions;
- side-effecting transitions;
- transitions whose work is routed to external workers.

The canonical event history is append-only and uncompacted. Derived projections, indexes, snapshots, summaries, materialized views, and rollups are allowed, but they are not the canonical event history.

The conceptual model remains:

```txt
event/history + marking
  -> enabled transitions
  -> selected firing
  -> recorded firing/result
  -> new marking
```

## Consequences

- Petrus has one timeline for process evolution.
- Passthrough and side-effect transitions differ by execution requirements, not by whether they belong to history.
- Replay, fork, debugging, traces, and observability can reason over one event-history model.
- Meta-workflows can inspect process evolution without special-casing deterministic transitions.
- Implementations may optimize runtime performance through derived projections, indexes, snapshots, and materialized views, but the canonical event history remains uncompacted.
- The queue remains distinct from history: queues deliver work; history records durable truth.

## Notes

This decision requires preserving the canonical event history as a tracing log. Later ADRs clarify that derived views are allowed, but they do not replace the canonical log.

## Open follow-up questions

- What is the minimal event history record model?
- What derived projections/indexes/snapshots are required for efficient execution?
- How does a queue item relate to a selected firing attempt and eventual history record?
- What worker capability declarations are needed to route handled transitions?
