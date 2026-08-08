---
status: Superseded
raised: 2026-07-07
decided: 2026-07-07
deciders:
  - henrique (Navigator)
supersedes:
superseded_by: docs/project/decisions/records/2026-07-07T2119Z-passthrough-is-a-default-handler-color-routed.md
related:
  - docs/project/decisions/records/2026-06-21T0842Z-hermes-adr-0010-no-handler-default-behavior-is-passthrough-only.md
  - docs/project/decisions/records/2026-07-07T1700Z-output-production-per-arc-contract-handler-supplies-tokens.md
---

# Passthrough is identity plus homogeneous broadcast; anything else needs a handler

> **Superseded 2026-07-07** by [DR passthrough-is-a-default-handler-color-routed]
> after Navigator review: passthrough became a default *handler* (not an engine
> special case) with color-routed forwarding under the permissive flow defaults
> [DR permissive-flow-defaults]. The strict enumeration below (identity +
> homogeneous broadcast, everything else a validation error) taxed common
> multi-color patterns with trivial handlers and is replaced.

## Question

[ADR 0010] made passthrough the only no-handler default but left it undefined for
multiple input tokens, multiple output places, and type mismatches (its Notes,
and the `firing-semantics.md` §Default behavior OPEN). This record defines it.

## Decision

A transition with no handler declared performs **passthrough**: the identity move
of the consumed token(s). It is defined only for a **single consumed color**:

- **1 consume arc → 1 output arc of the same color** — the consumed token(s) are
  deposited unchanged into the output place (identity).
- **1 consumed color → N output arcs, all of that same color** — the consumed
  token(s) are **broadcast** unchanged to every output place (homogeneous
  fan-out).
- **Anything else is a validation error requiring a handler**: an output arc
  whose color differs from the consumed color (type mismatch / retyping), or more
  than one distinct consumed color. The runtime never merges, splits, or retypes
  tokens by default.

Read and inhibit arcs participate in enablement but contribute nothing to
passthrough output (they are not consumed).

## Rationale

Honors [ADR 0010]'s "no inference": Impetus refuses to guess how to merge, split,
or retype — it errors and asks for a handler — rather than silently duplicating a
merged token everywhere like the Petrus oracle. Homogeneous broadcast (1→N same
color) is admitted because it is unambiguous — the same token to same-typed
places — and is a common, harmless routing convenience; it is not the
heterogeneous fan-out that requires a handler
[DR output-production-per-arc-contract-handler-supplies-tokens]. This keeps the
no-handler mental model tiny and total.

## Consequences

- Validation rejects no-handler transitions with heterogeneous output colors or
  multiple consumed colors, with a diagnostic pointing at the missing handler.
- Broadcast deposits the same token value to N places (consistent with one
  token / one type [DR aggregate-token-type]).
- Resolves the passthrough OPEN in `firing-semantics.md` §Default behavior and
  the [ADR 0010] Notes.
