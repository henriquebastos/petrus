---
status: Decided
raised: 2026-07-02
decided: 2026-07-02
deciders:
  - henrique (Navigator, via grill-with-docs in the hermes notebook)
supersedes:
related:
  - hermes ADR 0027
  - docs/project/decisions/records/2026-07-06T1505Z-absorb-hermes-adrs-into-ariad.md
---

> Migrated from the Hermes design notebook.

# ADR 0027: Place roles are optional annotations

## Status

Accepted

## Context

A design insight from the Matt conversation suggested that places may benefit from role annotations:

- input;
- output;
- control;
- regular.

These roles can help users understand process boundaries, distinguish externally fed places from emitted-result places, separate coordination/control state from domain data, and make diagrams or UIs easier to navigate.

However, Petrus should avoid turning these roles into new Petri-net semantics. A place should remain a place. Firing semantics should still be determined by markings, arcs, inscriptions, guards, timers, and transition behavior.

## Decision

Place roles are optional annotations in Petrus core.

The working roles are:

- `input` — a place that receives external/user/system events or starts a process boundary;
- `output` — a place that represents emitted results or process boundary outputs;
- `control` — a place used for coordination, gates, joins, limits, retries, leases, or scheduling state;
- `regular` — an ordinary domain-data place inside the process.

The role does not directly affect Petri-net firing semantics.

If no role is specified, the place is treated as `regular` for display/tooling purposes.

## Consequences

- The formal Petri-net model stays simple.
- UI, diagrams, validation hints, adapters, and documentation can use roles to explain the process.
- Roles can support useful filtering and grouping without changing enabledness or firing behavior.
- Input/output roles can help identify process boundaries without inventing special node kinds.
- Control roles can make coordination places visible without making them semantically different.
- Future higher-level layers may add conventions around roles, but core firing semantics must not depend on them unless a later ADR explicitly changes this.

## Examples

```ts
place("requested", {
  color: "ReviewRequest",
  role: "input",
})

place("done", {
  color: "ReviewResult",
  role: "output",
})

place("reviewLease", {
  color: "Lease",
  role: "control",
})

place("prLoaded", {
  color: "PullRequest",
  role: "regular",
})
```

All four are still ordinary places for Petri-net semantics.
