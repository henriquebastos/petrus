---
status: Superseded
raised: 2026-06-21
decided:
deciders:
  - henrique (Navigator, via grill-with-docs in the hermes notebook)
superseded_by: docs/project/decisions/records/2026-07-14T2016Z-activity-invocation-runtime-seam.md
supersedes:
related:
  - hermes ADR 0004
  - docs/project/decisions/records/2026-07-06T1505Z-absorb-hermes-adrs-into-ariad.md
  - docs/project/decisions/records/2026-07-14T2016Z-activity-invocation-runtime-seam.md
---

> Migrated from the Hermes design notebook.

> Partially superseded 2026-07-14 by
> `2026-07-14T2016Z-activity-invocation-runtime-seam.md`: the core principle
> stands — external results enter durable history and replay never re-runs
> side effects — but the durable record of external work is the terminal
> activity fact (`ActivityCompleted`/`ActivityFailed`), not a handler-result
> record. The handler's deterministic projection is represented directly by
> token and registration effect records.

# ADR 0004: Deterministic Petri-net execution records external results as history

## Status

Superseded in its concrete record model by
`2026-07-14T2016Z-activity-invocation-runtime-seam.md`. Its surviving principle
is settled doctrine: external results enter durable History and replay does not
re-run side effects blindly.

## Context

A previous implementation used Temporal workflows to host a Petri-net engine. Temporal provided durable workflow history, deterministic replay, activity scheduling, retries, and worker coordination. The Petri net computed enabled transitions and advanced the process, while side effects were executed through activities and returned as recorded results.

Petrus should preserve this useful separation without making Temporal the only runtime model.

## Decision

The Petrus runtime model should aim for deterministic replay:

> Given the same external events, handler results, and timer events in the same order, a net instance reaches the same state.

The Petri-net execution layer should advance deterministically from recorded history. Side effects occur through handlers and activities. Their observed results are recorded durably and reintroduced into the net as colored tokens, failure records, or events.

Temporal can be one runtime adapter that provides these properties, but the core semantics should also support local or alternative durable adapters.

## Consequences

- Handler execution is outside the pure net semantics, but handler results are part of durable history.
- Replay should not re-run side effects blindly.
- Runtime adapters must define how they persist events, handler results, timers, failures, and token movements.
- The formal core should not depend on Temporal APIs.
- The Temporal adapter can use workflows and activities to implement Petrus runtime behavior.
