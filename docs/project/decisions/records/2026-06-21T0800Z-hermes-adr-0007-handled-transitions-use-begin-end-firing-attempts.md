---
status: Decided
raised: 2026-06-21
decided: 2026-06-21
deciders:
  - henrique (Navigator, via grill-with-docs in the hermes notebook)
supersedes:
related:
  - hermes ADR 0007
  - docs/project/decisions/records/2026-07-06T1505Z-absorb-hermes-adrs-into-ariad.md
  - docs/project/decisions/records/2026-07-14T2016Z-activity-invocation-runtime-seam.md
---

> Migrated from the Hermes design notebook.

> Partially superseded 2026-07-14 by
> `2026-07-14T2016Z-activity-invocation-runtime-seam.md`: the begin/end
> lifecycle stands, but the execution step refines — the server-side handler
> prepares one Petri-agnostic activity whose request is frozen in the begin
> batch, the execution runtime runs that activity (not the handler), and the
> handler projects the frozen result before end firing. The shipped
> synchronous seam still delegates to the bound handler inline as
> compatibility surface.

# ADR 0007: Handled transitions use begin/end firing attempts

## Status

Accepted

## Context

Petrus transitions may be purely deterministic or may have handlers. A handled transition cannot be treated as an instantaneous pure token movement because the handler may perform side effects, call activities, wait for humans, invoke agents, retry, time out, or run on another worker.

A previous Temporal-based implementation modeled this as `beginFiring`, then delegated to a handler, then called `endFiring`. The earlier version waited for one handler at a time. A more robust design should allow scheduling several or all enabled handled firings to support multi-worker parallelism.

## Decision

Petrus should model handled transition execution as a durable firing attempt lifecycle:

1. A transition is enabled under a specific firing binding.
2. The runtime creates a durable firing attempt.
3. `beginFiring` records the attempt and consumes or otherwise accounts for input tokens according to the net semantics.
4. The runtime delegates execution to the bound handler.
5. The handler returns a result, failure, or retryable outcome through the runtime.
6. `endFiring` commits the result by producing output tokens, recording failure semantics, or applying runtime policy.

The runtime should not be limited to one handled firing at a time. Runtime adapters should be able to schedule multiple enabled firing attempts concurrently, including all currently enabled activities when policy allows, so multiple workers can execute in parallel.

## Consequences

- Handler execution is durable and inspectable as an in-progress firing attempt.
- Runtime adapters can support local sequential execution, local concurrent execution, Temporal activities, or distributed workers without changing the net definition.
- Input token accounting occurs at `beginFiring`, which prevents duplicate workers from processing the same consumed work token.
- Output token production occurs at `endFiring`, after handler result is known.
- Retry, timeout, lease, and side-effect tracking remain runtime responsibilities.
- Parallel scheduling policy becomes part of the runtime adapter or process configuration, not the formal net topology.

## Notes

This decision preserves the user's previous mental model while generalizing it for multi-worker execution:

```txt
enabled firing binding
→ beginFiring
→ handler execution
→ endFiring
→ output tokens / failure state
```
