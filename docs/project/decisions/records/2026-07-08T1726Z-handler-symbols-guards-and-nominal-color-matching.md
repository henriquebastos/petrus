---
status: Decided
raised: 2026-07-08
decided: 2026-07-08
deciders:
  - henrique (Navigator)
supersedes:
related:
  - docs/project/decisions/records/2026-06-23T0312Z-hermes-adr-0021-schema-declares-guard-and-handler-symbols.md
  - docs/project/decisions/records/2026-06-23T0933Z-hermes-adr-0022-scoped-symbols-and-uri-addressing.md
  - docs/project/decisions/records/2026-07-08T1726Z-places-are-never-typed.md
---

# Handler symbols, guard composition, parameterized mappings, and nominal color matching

> **Amended 2026-07-27:** nominal matching is unchanged, but its declaration
> may originate on a place and be compiled into effective incident arc colors;
> see [DR place-colors-compile-to-effective-arc-inscriptions].

## Question

Two handler-contract OPENs: (1) symbol scoping, multiple-guard composition, and
parameterized mappings; (2) hermes ADR 0020's nominal-vs-structural token color
matching (and per-language contract shape).

## Decision

- **Symbol scoping: transition-local, subnet-qualified.** Guard/handler symbols
  are local names in the declaring transition/subnet, resolving to fully
  qualified NetUri addresses during composition [ADR 0022]. Local names never
  collide across subnets.
- **Multiple guards compose as conjunction.** A transition may declare more than
  one guard; the transition is guard-enabled iff **all** its guards return true.
  Order is irrelevant because guards are pure [DR arc-filters-and-guards]. Any
  logic that needs ordering or short-circuit belongs in a single named guard.
- **Mappings may be parameterized.** An implementation mapping may bind a symbol
  to a reusable function **with configuration** (the same function bound under
  different names/config to different transitions) [ADR 0021].
- **Color matching is nominal; data access is structural.** An arc or place
  admits color `Payment` iff a token's **declared color is `Payment`** (nominal
  identity — a simple name match). Filters, guards, and handlers then read the
  token's **structured data** (including aggregate fields) structurally
  [DR aggregate-token-type]. Nominal matching keeps arc type-checks a name
  comparison; structural access keeps data rich.

## Consequences

- `spec/handler-contract.md` OPENs closed for scoping/guards/mappings and for
  nominal/structural matching.
- The **per-language contract-declaration shape** (how a handler declares its
  typed inputs/outputs in Python vs TypeScript) stays kernel/binding-deferred
  [DR kernel-deferred-spec-details].
- Type identity remains nominal and runtime matching remains arc-based. A
  place may now declare the repeated nominal default that flattening compiles
  into effective incident arc colors.

## Review Trigger

Revisit multiple-guard conjunction if a real need for guard ordering/priority
appears; revisit nominal matching if cross-runtime nets need structural color
compatibility.
