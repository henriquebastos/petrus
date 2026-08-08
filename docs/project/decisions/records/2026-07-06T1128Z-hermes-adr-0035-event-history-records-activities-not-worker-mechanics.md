---
status: Decided
raised: 2026-07-06
decided: 2026-07-06
deciders:
  - henrique (Navigator, via grill-with-docs in the hermes notebook)
supersedes:
related:
  - hermes ADR 0035
  - docs/project/decisions/records/2026-07-06T1505Z-absorb-hermes-adrs-into-ariad.md
  - docs/project/decisions/records/2026-07-14T2016Z-activity-invocation-runtime-seam.md
---

> Migrated from the Hermes design notebook.

> Partially superseded 2026-07-14 by
> `2026-07-14T2016Z-activity-invocation-runtime-seam.md`, which also answers
> two open questions below: handler execution is not renamed `activity` — the
> handler stays server-side and Petri-aware while the activity is the
> Petri-agnostic work a worker executes — and the attempt boundary is decided:
> canonical history carries only `ActivityRequested` and terminal
> `ActivityCompleted`/`ActivityFailed`. The started/accepted, attempt-recorded,
> and retry-scheduled records listed below, and the clause that attempts are
> semantic when they affect process execution, are superseded — every attempt
> is operational adapter state. The core principle (activities, not worker
> mechanics) stands, strengthened.

# ADR 0035: Event history records activities, not worker mechanics

## Status

Accepted

## Context

ADR 0034 introduced a distinction between deterministic net/runtime records and semantic activity records. Further reflection clarified that the canonical process event history should not expose workers and queues as the primary semantic concepts.

Workers and queues are execution infrastructure. They matter operationally and should have logs/metrics/traces of their own, but the canonical process history should describe what happened in the process, not all implementation mechanics for how infrastructure delivered the work.

In Temporal terms, the process history should see activities and their outcomes, while worker polling, queue consumption, and local execution details belong to the worker/server operational layer.

## Decision

The canonical Petrus event history records semantic **activities** and process facts, not worker/queue mechanics.

The event history should contain records such as:

- activity scheduled/requested;
- activity started/accepted;
- activity attempt recorded;
- activity completed;
- activity failed/timed out/cancelled;
- activity input recorded;
- activity output/result recorded;
- retry scheduled;
- firing completed from activity result.

Workers should have their own operational logs/traces for:

- queue polling;
- queue lease/ack/nack;
- worker process startup/shutdown;
- sandbox, container, virtual-machine, shell, and network-service details;
- local stdout/stderr;
- resource usage;
- queue delivery failures;
- internal worker retries before reporting an activity attempt.

The main server/runtime may track the handoff between queue delivery and activity execution to ensure correctness, but those mechanics should be represented as operational records unless they affect semantic process history.

## Consequences

- The canonical event history remains focused on process semantics: the things that happen, not every detail of how infrastructure made them happen.
- Worker and queue systems can evolve without changing the process history model.
- Operational observability still exists, but in worker/server logs and traces correlated with activity IDs or event IDs.
- Activity attempts are semantic when they affect process execution and should appear in the canonical event history.
- Queue consumption attempts are operational unless they become activity attempts or affect process-visible behavior.
- The previous phrase "side-effect/worker records" should be read as "side-effect/activity records" for canonical history; worker mechanics belong to operational logs.

## Correlation

Operational worker logs should correlate back to canonical event history using IDs such as:

```txt
activityId
activityAttemptId
firingAttemptId
netInstanceId
eventId
queueMessageId
workerId
```

But the canonical process timeline should primarily speak in activity/firing terms, not queue/worker implementation terms.

## Open follow-up questions

- What is the exact difference between an activity attempt and a worker delivery attempt?
- Which queue/server handoff records must be durable for correctness but still remain outside canonical process history?
- What IDs are required to correlate worker logs with activity events?
- Should handler execution be named `activity` in Petrus, or is there a better term for semantic side-effect work?
