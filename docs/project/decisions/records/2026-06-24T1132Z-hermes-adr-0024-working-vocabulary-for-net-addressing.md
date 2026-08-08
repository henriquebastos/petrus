---
status: Decided
raised: 2026-06-24
decided: 2026-06-24
deciders:
  - henrique (Navigator, via grill-with-docs in the hermes notebook)
supersedes:
related:
  - hermes ADR 0024
  - docs/project/decisions/records/2026-07-06T1505Z-absorb-hermes-adrs-into-ariad.md
---

> Migrated from the Hermes design notebook.

# ADR 0024: Working vocabulary for net addressing

## Status

Accepted

## Context

Petrus needs precise language for graph topology, schema elements attached to graph topology, and addresses into the composed net.

Earlier terms such as `SchemaRef`, `attribute`, and broad uses of `node` were too vague. The project needs a working vocabulary that keeps Petri-net graph structure separate from behavior/configuration declarations while still allowing all relevant parts of the net to be addressed.

## Decision

Petrus will use this working vocabulary:

- **Node** — a place or transition only.
- **Arc** — a directed connection between nodes; not itself a node.
- **Declaration** — an addressable schema element attached to a net or node, but not itself a node.
- **NetPath** — the address of a node; a subset/specialization of `NetUri`.
- **NetUri** — the address of any addressable part of the composed net.

Examples of declarations include:

- handler declaration;
- guard declaration;
- timer declaration;
- initial marking declaration.

This is accepted as the working vocabulary until concrete examples force changes.

## Consequences

- Graph topology remains clean: places/transitions are nodes, arcs connect nodes.
- Attached behavior/configuration is modeled as declarations, not nodes.
- APIs that require graph endpoints can use `NetPath`.
- APIs that need to point to any addressable part of the composed net can use `NetUri`.
- Documentation should avoid using `attribute` as a primary modeling term unless a narrower meaning is later defined.
- `SchemaRef` should not be used as the main term for addresses inside the net; `NetUri` is clearer.

## Examples

```txt
Node NetPath:
  /review/start
  /review/pending

Declaration NetUri:
  petrus:/review/start#handler
  petrus:/review/start#guard:isReady
  petrus:/review/start#timer
  petrus:/review/pending#initial
```

Exact URI syntax remains undecided.
