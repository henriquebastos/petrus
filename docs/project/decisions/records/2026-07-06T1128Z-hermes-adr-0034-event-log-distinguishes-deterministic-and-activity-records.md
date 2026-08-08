---
status: Decided
raised: 2026-07-06
decided: 2026-07-06
deciders:
  - henrique (Navigator, via grill-with-docs in the hermes notebook)
supersedes:
related:
  - hermes ADR 0034
  - docs/project/decisions/records/2026-07-06T1505Z-absorb-hermes-adrs-into-ariad.md
  - docs/project/decisions/records/2026-07-14T2016Z-activity-invocation-runtime-seam.md
---

> Migrated from the Hermes design notebook.

> Partially superseded 2026-07-14 by
> `2026-07-14T2016Z-activity-invocation-runtime-seam.md`: the
> deterministic-vs-activity distinction stands, but the activity record list
> narrows to the frozen `ActivityRequested` and its terminal
> `ActivityCompleted`/`ActivityFailed`. Started/accepted, attempt, retry, and
> handler-result records — and the clause that attempts and retries appear in
> the canonical log — are superseded: operational attempts live in the
> execution adapter's reconstructible store, and the handler's deterministic
> projection is represented by token and registration effect records.

# ADR 0034: Event log distinguishes deterministic and activity records

## Status

Accepted

## Context

Petrus is moving toward a Temporal-like event-history model: the canonical event history is append-only and uncompacted, and every transition firing participates in it.

Temporal's model suggests an important distinction:

- workflow events describe deterministic workflow evolution and allow replay/inspection of state;
- activity events describe non-deterministic side-effecting work, attempts, retries, and results.

Petrus should not copy Temporal's implementation details, but the conceptual separation is useful. Net execution must remain deterministic and replayable. Side effects must be represented as observed facts in history, not recomputed during replay.

This also clarifies that attempts, retries, inputs, outputs, initial state, and final state are not merely projected views. They should be visible in the canonical event log.

## Decision

The canonical Petrus event log will distinguish deterministic net/runtime records from semantic activity records while keeping them in one unified append-only history.

Deterministic net/runtime records include events such as:

- external event accepted into the process;
- timer matured;
- firing candidate selected;
- firing begun;
- tokens consumed/read/accounted;
- tokens produced;
- firing completed;
- marking/state boundary recorded.

Activity records include events such as:

- activity scheduled/requested;
- activity started/accepted;
- activity attempt recorded;
- activity completed/failed/timed out/cancelled;
- handler result recorded;
- retry scheduled;
- activity input recorded;
- activity output recorded.

Both kinds of records belong to the same canonical event history. The distinction is semantic, not a split into separate logs.

## Consequences

- Replay can use deterministic net/runtime records to reconstruct state without re-running side effects.
- Side-effect records are observed facts and must be treated as idempotent/replay-safe inputs during replay.
- Activity attempt tracking is a first-class runtime concern.
- Worker queue management is an execution/operational concern that should correlate to activity events without becoming the primary canonical process vocabulary.
- Attempts and retries should appear in the canonical event log, not only in derived projections.
- Inputs and outputs of handled execution should be recorded sufficiently for audit, debugging, replay, and monitoring.
- The event log should be able to show the initial and final state of a firing/execution, including what was consumed, what was produced, what input was sent to an activity/handler, and what output/result came back.

## Notes

This decision does not require using Temporal. Temporal is an inspiration for the separation between deterministic workflow evolution and non-deterministic side-effect execution.

The event log remains uncompacted. Projections and indexes may be derived for efficient reads, but attempts, failures, inputs, outputs, and state transitions should remain visible in the canonical log.

## Open follow-up questions

- What are the exact event types and payload fields for deterministic net/runtime records?
- What are the exact event types and payload fields for activity records?
- What does idempotency mean for activity execution in Petrus?
- How should retry attempts be grouped: under one firing attempt, one activity, or both?
- What input/output payloads are stored inline versus referenced as artifacts?
