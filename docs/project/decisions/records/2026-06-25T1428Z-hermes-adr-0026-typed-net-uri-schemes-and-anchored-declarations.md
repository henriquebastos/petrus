---
status: Decided
raised: 2026-06-25
decided: 2026-06-25
deciders:
  - henrique (Navigator, via grill-with-docs in the hermes notebook)
supersedes:
related:
  - hermes ADR 0026
  - docs/project/decisions/records/2026-07-06T1505Z-absorb-hermes-adrs-into-ariad.md
---

> Migrated from the Hermes design notebook.

# ADR 0026: Typed net URI schemes and anchored declarations

## Status

Accepted

## Context

Petrus needs a concrete addressing syntax for first-class Petri-net graph citizens and for declarations attached to them.

Earlier ADRs established:

- places and transitions are nodes;
- arcs are graph edges, not nodes;
- places, transitions, and arcs are first-class Petri-net graph citizens;
- declarations are addressable schema elements attached to a net or node;
- `NetPath` addresses nodes;
- `NetUri` addresses addressable net parts.

A single generic `petrus:` scheme would identify the address space but would not reveal the kind of addressed thing. Runtime and UI APIs benefit when the address itself carries the kind of graph citizen.

## Decision

Petrus will use typed URI schemes as the working canonical address syntax for graph citizens:

```txt
place:/review/pending
transition:/review/start
arc:/review/pending->/review/start
```

Arcs use a `from->to` shape because it matches how Petri nets are read visually: a directed edge from one graph citizen to another.

Declarations remain anchored on the graph citizen where they belong using fragment syntax (`#`):

```txt
transition:/review/start#handler
transition:/review/start#guard:isReady
transition:/review/start#timer:retryDelay
place:/review/pending#initial
```

The URI scheme communicates the owner kind. The fragment communicates the attached declaration.

## Consequences

- Address strings are self-describing: `place:`, `transition:`, and `arc:` reveal the addressed kind.
- UI and runtime diagnostics do not need to infer the kind from a generic path alone.
- Declarations do not become peer graph citizens; they remain attached to places or transitions.
- Declaration URIs are still precise enough for binding, diagnostics, validation, source maps, and editor tooling.
- A generic `petrus:` namespace is not the primary working syntax for now.
- A future globally qualified form may be added if Petrus needs package/net namespaces across multiple address spaces.

## Examples

Enabledness diagnostic:

```txt
Transition transition:/review/start is not enabled.

Missing token:
  place:/review/pending

Required by arc:
  arc:/review/pending->/review/start

Guard declaration:
  transition:/review/start#guard:isReady
```

Flattened indexes may use these URI forms:

```txt
places:      Map<PlaceUri, Place>
transitions: Map<TransitionUri, Transition>
arcs:        Map<ArcUri, Arc>
```

Declaration indexes can be anchored views over graph citizens:

```txt
handlerDeclarationsByTransition:
  transition:/review/start -> transition:/review/start#handler

guardDeclarationsByTransition:
  transition:/review/start -> [transition:/review/start#guard:isReady]

initialMarkingDeclarationsByPlace:
  place:/review/pending -> place:/review/pending#initial
```

Exact escaping rules and Unicode-vs-ASCII arrow spelling remain open. The ASCII `->` form is the working syntax for now.
