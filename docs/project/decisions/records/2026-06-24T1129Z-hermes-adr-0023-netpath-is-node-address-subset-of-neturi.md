---
status: Decided
raised: 2026-06-24
decided: 2026-06-24
deciders:
  - henrique (Navigator, via grill-with-docs in the hermes notebook)
supersedes:
related:
  - hermes ADR 0023
  - docs/project/decisions/records/2026-07-06T1505Z-absorb-hermes-adrs-into-ariad.md
---

> Migrated from the Hermes design notebook.

# ADR 0023: NetPath is the node-address subset of NetUri

## Status

Accepted

## Context

Petrus needs names for graph elements, attached declarations, and addresses.

The current working terminology is:

- nodes are places and transitions;
- arcs are directed connections between nodes;
- declarations are non-node schema elements attached to nodes or nets;
- `NetPath` addresses nodes;
- `NetUri` addresses any addressable part of the net.

A question remained: should `NetPath` be a subset/specialization of `NetUri`?

## Decision

`NetPath` is the node-address subset of `NetUri`.

Every `NetPath` can be represented as a `NetUri`, but not every `NetUri` is a `NetPath`.

A `NetPath` addresses only a place or transition node.

A `NetUri` may address:

- a place node;
- a transition node;
- a transition's handler declaration;
- a transition's guard declaration;
- a timer declaration;
- an initial marking declaration;
- possibly an arc or other declaration if those become addressable later.

## Consequences

- Arc endpoints should use `NetPath`, because arcs connect nodes.
- Markings should be keyed by `NetPath`, because markings distribute tokens across places.
- Handler and guard implementation mappings may use `NetUri`, because they address declarations inside transitions.
- Diagnostics and tooling can use `NetUri` as the broad address type.
- APIs that require a node can accept `NetPath` specifically instead of any `NetUri`.

## Example

Conceptual examples:

```txt
NetPath: /review/start
NetUri:  petrus:/review/start
NetUri:  petrus:/review/start#handler
NetUri:  petrus:/review/start#guard:isReady
NetUri:  petrus:/review/pending#initial
```

Exact URI syntax remains undecided.
