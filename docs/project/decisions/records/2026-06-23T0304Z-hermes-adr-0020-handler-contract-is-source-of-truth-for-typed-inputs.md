---
status: Decided
raised: 2026-06-23
decided: 2026-06-23
deciders:
  - henrique (Navigator, via grill-with-docs in the hermes notebook)
supersedes:
related:
  - hermes ADR 0020
  - docs/project/decisions/records/2026-07-06T1505Z-absorb-hermes-adrs-into-ariad.md
---

> Migrated from the Hermes design notebook.

> Note: the original hermes status is "Refined by ADR 0021" — see docs/project/decisions/records/2026-06-23T0312Z-hermes-adr-0021-schema-declares-guard-and-handler-symbols.md. Kept as Decided here.

# ADR 0020: Handler contract is the source of truth for typed inputs and outputs

## Status

Refined by ADR 0021

## Context

After removing argument names from arc inscriptions, Petrus needs a way to resolve selected tokens into handler arguments.

One option was to declare transition input contracts in the net schema and require handlers to conform. That creates duplication: the same input/output types would be declared in the transition and again in the handler. It also makes the net schema require full understanding of all handler data types.

The corrected direction is that handler implementations should carry their own typed input/output contracts. The net connects transitions and arcs; handlers connect behavior and type contracts.

ADR 0021 refines this: the net schema declares handler symbols, and an implementation mapping connects those symbols to concrete handler functions.

## Decision

The handler implementation/contract is the source of truth for typed handler inputs and outputs.

The net schema should not require duplicate transition input declarations solely to name handler arguments or repeat handler type signatures.

The net schema may declare a handler symbol on a transition. The concrete handler function mapped to that symbol carries the typed input/output contract.

Arc inscriptions remain structural and simple:

- token color/type;
- cardinality.

When a handler is bound to a transition through an implementation mapping, the net runtime and binding layer validate that the transition's incoming/outgoing arcs can satisfy the handler's declared input/output contract.

For explicitly typed handlers, Petrus should resolve selected tokens by matching the handler's required input types against the transition's incoming arc token types. The handler receives typed arguments according to its own contract/signature.

For less-typed or fallback cases, Petrus may support a generic token-set/context input type. In that mode, the handler receives the selected token set or context bag and is responsible for interpreting it.

## Consequences

- Handler contracts are not duplicated in the net schema.
- The net schema remains focused on topology, token colors, cardinality, guards, arcs, timers, and transition structure.
- The binding layer becomes responsible for validating compatibility between transition arcs and handler contracts.
- Explicit typed handlers give stronger validation and safer automatic argument resolution.
- Generic token-set handlers provide an escape hatch when precise types are unavailable or not worth modeling yet.
- If multiple incoming arcs provide the same token color/type, the binding layer must require disambiguation through handler contract metadata, transition-local configuration, or a generic token-set handler.

## Supersedes

This ADR supersedes the suggestion that transition input contracts in the net schema should be the primary source of handler argument names and types.

## Open questions

- How exactly does a handler declare its typed input/output contract in TypeScript?
- How does the binding layer disambiguate multiple incoming arcs with the same token color?
- Are guard expressions allowed to refer to handler contract names, or must guards operate over a transition-local token selection object?
- Does the net schema need to know token colors nominally, structurally, or both?
- How much runtime reflection is possible vs requiring explicit schema objects?
