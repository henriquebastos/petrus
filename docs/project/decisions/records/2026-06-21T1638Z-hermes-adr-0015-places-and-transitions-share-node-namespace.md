---
status: Decided
raised: 2026-06-21
decided: 2026-06-21
deciders:
  - henrique (Navigator, via grill-with-docs in the hermes notebook)
supersedes:
related:
  - hermes ADR 0015
  - docs/project/decisions/records/2026-07-06T1505Z-absorb-hermes-adrs-into-ariad.md
---

> Migrated from the Hermes design notebook.

# ADR 0015: Places and transitions share a node namespace

## Status

Accepted

## Context

Petrus uses `NetPath` as the address of a node in the hierarchical Petri-net structure. The addressed node may be a place or a transition.

A naming decision is needed: within a parent net scope, should places and transitions share a namespace, or should they be separated by node kind?

Separate namespaces would allow a place and transition to have the same local name, but would make path resolution noisier or require each reference to include both path and node kind.

## Decision

Places and transitions share the same node namespace within each parent net scope.

A `NetPath` should identify exactly one node without requiring an additional node-kind discriminator.

If a place and transition would naturally have the same name, the net author should choose clearer names.

## Consequences

- Net path resolution is simpler.
- Handler bindings can reference transition paths directly.
- Arc endpoint references can resolve to exactly one node.
- Diagnostics can show one canonical path per node.
- Authors must avoid local name collisions between places and transitions.
- Naming conventions become more important.

## Example

Prefer:

```txt
/review/pending
/review/start
/review/running
/review/complete
```

Avoid trying to define both a place and a transition at:

```txt
/review/review
```
