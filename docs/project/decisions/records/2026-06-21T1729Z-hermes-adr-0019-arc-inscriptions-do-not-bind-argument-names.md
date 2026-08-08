---
status: Decided
raised: 2026-06-21
decided: 2026-06-21
deciders:
  - henrique (Navigator, via grill-with-docs in the hermes notebook)
supersedes:
related:
  - hermes ADR 0019
  - docs/project/decisions/records/2026-07-06T1505Z-absorb-hermes-adrs-into-ariad.md
---

> Migrated from the Hermes design notebook.

# ADR 0019: Arc inscriptions do not bind argument names

## Status

Accepted

## Context

ADR 0018 said that input arc inscriptions should contain token color/type, cardinality, and a binding name. That was incorrect.

The corrected model is that arcs should not name handler arguments. An arc declares what token type and cardinality participates in a transition. The transition and handler contract own how selected tokens are resolved into handler arguments.

This keeps arcs focused on Petri-net structure and token requirements instead of coupling arcs to implementation-level parameter names.

## Decision

Arc inscriptions should not include binding names.

Input arc inscriptions should express:

- token color/type required;
- cardinality required.

Cross-token logic remains in transition guards.

Argument resolution belongs to the transition/handler invocation contract. When a transition fires, the net runtime resolves the selected tokens for that transition and passes them to the handler according to the handler's declared input contract or function signature.

## Consequences

- Arcs remain structural and type/cardinality-oriented.
- Handler parameter naming does not leak into arc definitions.
- Transition-level contracts become more important.
- The net runtime must define how selected tokens are matched to handler inputs when multiple arcs/types are involved.
- If a transition consumes multiple arcs of the same token color, the transition contract must disambiguate them without relying on arc-level bind names.

## Supersedes

This ADR supersedes the part of ADR 0018 that said arc inscriptions include a binding name.

ADR 0018 remains valid for the broader boundary that cross-token logic belongs in transition guards rather than arc inscriptions.
