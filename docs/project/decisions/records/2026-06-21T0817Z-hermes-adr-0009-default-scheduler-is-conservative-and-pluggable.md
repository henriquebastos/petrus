---
status: Decided
raised: 2026-06-21
decided: 2026-06-21
deciders:
  - henrique (Navigator, via grill-with-docs in the hermes notebook)
supersedes:
related:
  - hermes ADR 0009
  - docs/project/decisions/records/2026-07-06T1505Z-absorb-hermes-adrs-into-ariad.md
---

> Migrated from the Hermes design notebook.

# ADR 0009: Default scheduler is conservative and pluggable

## Status

Accepted

## Context

Petrus runtime scheduling selects enabled firing candidates to begin as durable firing attempts. Scheduling can strongly affect behavior because candidates may conflict over consumable tokens, and aggressive scheduling can create many concurrent handler executions, side effects, API calls, LLM calls, or human requests.

Different use cases need different scheduling policies. A local debugging workflow benefits from simple deterministic behavior. A distributed worker runtime benefits from scheduling many non-conflicting firings concurrently. Future policies may include round-robin, fairness, priority, budgets, deadlines, queue/capability awareness, or domain-specific policies.

## Decision

> **Scoped refinement — 2026-07-22:** DEC-035 preserves the conservative,
> deterministic, explicit-pluggability intent but separates Candidate Selection
> from whole-action and concurrency policy. Initial Candidate Selection
> validates First, Priority, and transition-level Round-Robin, selecting at
> most one `Binding` per Engine turn. All-non-conflicting, bounded parallel,
> budget, deadline, queue, and capability scheduling remain possible future
> concerns, not promises of the base Candidate Selection contract. See
> `2026-07-22T1413Z-candidate-selection-is-instance-scoped-immutable-policy.md`.

The simplest/default Petrus runtime should use conservative deterministic single-step scheduling.

Petrus should make scheduler policy pluggable from the beginning, so users can later choose or implement variations such as:

- one-at-a-time stable ordering;
- round-robin among competing transitions;
- all non-conflicting enabled candidates;
- bounded parallelism;
- per-handler or per-queue concurrency limits;
- budget-aware scheduling;
- deadline-aware scheduling;
- priority/fairness policies;
- custom domain-specific schedulers.

Parallel scheduling should be explicit runtime policy, not an invisible default.

## Consequences

- Candidate Selection implementations document their own behavior; the base
  contract promises no universal fairness grain.
- The initial runtime remains easier to reason about, test, debug, and replay.
- The architecture leaves room for multi-worker parallelism without changing net definitions.
- Users can opt into more aggressive scheduling with explicit concurrency and budget controls.
- Scheduler experiments can be implemented as runtime policy variations.
- Documentation should show the default as safe and deterministic while making pluggability clear.

## Example shape

```ts
localRuntime({
  scheduler: schedulers.oneAtATime({ order: 'stable' }),
})

localRuntime({
  scheduler: schedulers.allNonConflicting({
    maxConcurrent: 8,
    perHandlerLimit: 2,
  }),
})
```
