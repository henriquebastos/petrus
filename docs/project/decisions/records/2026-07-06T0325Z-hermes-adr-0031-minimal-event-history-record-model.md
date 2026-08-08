---
status: Decided
raised: 2026-07-06
decided: 2026-07-06
deciders:
  - henrique (Navigator, via grill-with-docs in the hermes notebook)
supersedes:
related:
  - hermes ADR 0031
  - docs/project/decisions/records/2026-07-06T1505Z-absorb-hermes-adrs-into-ariad.md
  - docs/project/decisions/records/2026-07-14T2016Z-activity-invocation-runtime-seam.md
---

> Migrated from the Hermes design notebook.

> Partially superseded 2026-07-14 by
> `2026-07-14T2016Z-activity-invocation-runtime-seam.md`: categories 7
> ("activity attempt recorded") and 8 ("handler result recorded") leave
> canonical history. The canonical activity lifecycle is the frozen
> `ActivityRequested` and its terminal `ActivityCompleted`/`ActivityFailed`;
> operational attempts live in the execution adapter, and the handler's
> deterministic projection is represented directly by token and registration
> effect records. The other categories stand; `spec/event-history.md` carries
> the current list.

# ADR 0031: Minimal event history record model

## Status

Accepted

## Context

ADR 0030 established that every transition firing is semantically part of one unified event history. Petrus now needs a minimal event history record model that can explain process evolution without collapsing execution queues, workers, and context into the same concept.

The model must support:

- external events entering the process;
- timers and time-based enablement;
- scheduler decisions;
- transition firing lifecycle;
- token movement and marking changes;
- handled work routed to workers;
- handler results and failures;
- replay, fork, diagnostics, and observability.

## Decision

Petrus will use these minimal semantic event history record categories as the working model:

1. **External event recorded**
   - A webhook, user message, poll result, human decision, imported file, or other outside signal entered the process history.

2. **Timer matured**
   - A time-based enablement condition became true.

3. **Firing candidate selected**
   - The scheduler selected an enabled transition/firing binding to proceed.

4. **Firing begun**
   - The runtime began the selected firing attempt and durably recorded the attempt boundary.

5. **Tokens consumed/read/accounted**
   - The runtime recorded how input arcs interacted with selected tokens: consumed, read, inhibited/absent, or otherwise accounted for.

6. **Activity scheduled/requested**
   - A handled transition required semantic side-effect work and an activity was requested.

7. **Activity attempt recorded**
   - An activity attempt started, completed, failed, cancelled, timed out, or otherwise produced an observed execution outcome.

8. **Handler result recorded**
   - The runtime recorded the semantic result to integrate into the net, separate from delivery mechanics.

9. **Firing completed**
   - The runtime completed the firing attempt by committing success/failure semantics and marking evolution.

10. **Tokens produced**
    - The runtime recorded output tokens produced into places.

11. **Firing failed/cancelled/compensated**
    - The runtime recorded non-success terminal semantics for a firing attempt, including cancellation, compensation, or retry-triggering failure.

These are semantic categories. ADR 0033 later clarifies that the canonical event history should preserve them as an append-only, uncompacted tracing log. Derived projections, indexes, snapshots, summaries, and rollups are allowed, but they are not the canonical event history.

## Consequences

- Event history can explain both deterministic/passthrough and worker-routed transitions.
- Queue operations remain delivery mechanics and do not replace history records.
- Activity execution has explicit semantic boundaries: scheduled/requested, attempted, completed/failed/timed out/cancelled, and result recorded.
- Handler results are separated from worker mechanics so different execution substrates can produce the same semantic history.
- Token movement can be audited independently of handler execution.
- The runtime can support replay, fork, debug timelines, and meta-workflows over process history.

## Notes

The exact event payload schemas remain unresolved. The current decision only accepts the semantic categories.

ADR 0033 later clarifies that the canonical event history should not compact these records away. Runtime implementations may maintain derived projections or snapshots that group facts for fast reads, but those derived artifacts do not replace the canonical log.

## Open follow-up questions

- What projection/index/snapshot policies are acceptable?
- What retention/archive policies are acceptable for long-running canonical logs?
- Should `tokens consumed/read/accounted` and `tokens produced` be explicit records or deltas inside firing records?
- Should `firing candidate selected` be durable before `firing begun`, or only part of the begin record?
- How are retries represented: new firing attempts, activity attempts under one firing, or both?
- What is the relationship between `activity completed` and `handler result recorded` for in-process deterministic handlers?
