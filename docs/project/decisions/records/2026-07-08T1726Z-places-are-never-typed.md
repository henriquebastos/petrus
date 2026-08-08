---
status: Superseded
raised: 2026-07-08
decided: 2026-07-08
deciders:
  - henrique (Navigator)
supersedes:
superseded_by:
  - docs/project/decisions/records/2026-07-27T2333Z-place-colors-compile-to-effective-arc-inscriptions.md
related:
  - docs/project/decisions/records/2026-07-07T2118Z-permissive-flow-defaults.md
  - docs/project/decisions/records/2026-07-08T1726Z-handler-symbols-guards-and-nominal-color-matching.md
  - docs/project/decisions/records/2026-07-07T1700Z-output-production-per-arc-contract-handler-supplies-tokens.md
---

# Places are never typed; type shaping lives on arcs

> **Superseded 2026-07-27:** maintained package evidence showed every one
> of 29 places repeating one color across 66 incident arcs. Place colors now
> provide an optional authoring default compiled once into effective arc
> inscriptions. Runtime flow remains arc-shaped; see the superseding record.

## Question

[DR permissive-flow-defaults] made places untyped by default but left an
optional `accepts` narrowing. Should places be typeable at all, or do they
simply hold any token?

## Decision

**Places are never typed. A place holds tokens of any color.** There is no
`accepts` declaration on a place. All type shaping lives on **arcs** (input arc
color/filter; output arc routing contract) and in handler contracts; a place's
contents are wholly determined by what its incoming arcs deposit and its initial
marking.

This **revises** [DR permissive-flow-defaults]: the "optional `accepts`
narrowing" on places is removed. Places-untyped remains; place-typing goes.

## Rationale

Arc inscriptions already control what flows into a place, so a place `accepts`
declaration is a **redundant second source of type truth** that could even
contradict the arcs (place says `Payment`, an output arc deposits `Invoice`).
One source of type truth — arcs — is simpler and consistent with the
arc-centric "shape down on arcs" model. The only thing place-typing offered —
opt-in wiring-error detection — is better served by typing the arcs and letting
the validation run cross-check arc contracts. This also pairs cleanly with
nominal color matching [DR handler-symbols-guards-and-nominal-color-matching]:
color identity lives on tokens, is checked at arcs, and is never declared on a
holder.

## Consequences

- `spec/net-schema.md` §Places drops `accepts`; `CONTEXT.md` Place entry
  updated. [DR permissive-flow-defaults] gains an amendment note.
- The token type ledger (colors known to a net) is derived from arc
  inscriptions, handler contracts, and initial markings — never from place
  declarations.
- Structural (uncolored-skeleton) analysis is unaffected; it never needed place
  colors.

## Review Trigger

Revisit only if a concrete case shows a place-level type constraint that arc
typing genuinely cannot express.
