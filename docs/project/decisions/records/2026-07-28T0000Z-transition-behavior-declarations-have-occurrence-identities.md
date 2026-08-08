---
status: Decided
raised: 2026-07-28
decided: 2026-07-28
deciders:
  - henrique (Navigator)
supersedes:
related:
  - ES-045
  - docs/project/decisions/records/2026-06-24T1344Z-hermes-adr-0025-flattened-net-assigns-uris-to-all-declarations.md
  - docs/project/decisions/records/2026-06-25T1428Z-hermes-adr-0026-typed-net-uri-schemes-and-anchored-declarations.md
  - docs/project/debt/items/2026-07-08T2140Z-guard-symbols-net-scoped-not-transition-local.md
---

# Transition behavior declarations have occurrence identities

## Question

How should the flattened net identify transition handlers and ordered guard
occurrences so a Python authoring layer can bind anonymous callable
implementations without deriving identity from Python names or pretending a
generated address is a local symbol?

## Decision

Every declared handler and every authored guard occurrence receives one
canonical `NetUri`. A handler is anchored at
`transition:/path#handler`. A named guard is anchored at
`transition:/path#guard:name`. An anonymous or inline guard is anchored at
`transition:/path#guard:$N`, where `N` is its absolute zero-based position in
the authored guard tuple. Position counts named, inline, and anonymous guards.

The language-neutral schema gains an explicit anonymous declaration marker;
anonymous behavior is not encoded as a fabricated string symbol. Leading `$`
is reserved for generated declaration names, and a transition cannot repeat a
named guard because both occurrences would claim one canonical URI. Repeated
anonymous or inline guards remain separate authored occurrences with distinct
positional identities.

An implementation mapping may target an exact declaration `NetUri`. For a
named declaration only, a bare local symbol remains compatibility and
convenience syntax that deliberately shares one implementation across every
matching declaration in the flat net. Supplying both an exact URI and its
local symbol for one declaration is ambiguous and fails at binding. Anonymous
declarations have no local-symbol fallback.

The runtime resolves implementation mappings once at construction into
immutable occurrence-oriented indexes. Enabledness and firing do not parse or
construct URIs in their hot paths.

This decision initially materializes handler and guard identities only. Arc
filters, timers, completion, initial markings, diagnostics, and composition
remain governed by the broader addressing ADRs but are not silently claimed
as part of this slice.

For the Python DSL, explicit callable-flavor specifications lower into these
anonymous declarations. A raw undecorated callable is rejected rather than
having its semantic flavor inferred. The immutable Python build result is
called `BuiltNet` and lives with the authoring API in `impetus.dsl`, outside
the independent Petrinet Kernel.

## Rationale

Callable object identity and `__name__` are neither portable nor stable:
lambdas, partials, callable objects, decorators, and intentional reuse all
break name-derived identity. Owner plus authored position is deterministic and
already follows ADR 0025's anonymous declaration example. A distinct marker
keeps generated identity out of the local symbol namespace.

Exact URI bindings pay the existing same-name/different-implementation debt,
while the named fallback preserves the current concise mapping for callers
that intentionally share one implementation. Failing overlap avoids a hidden
precedence rule.

## Options Considered

- **Generate private symbol strings.** Rejected because it mixes declaration
  addressing with local symbol vocabulary and creates collision rules outside
  `NetUri`.
- **Use callable names.** Rejected because Python presentation names are not
  canonical declaration identity.
- **Number anonymous guards only.** Rejected because inserting a named guard
  would leave positional diagnostics disconnected from authored order.
- **Resolve exact URI over a local-symbol fallback by precedence.** Rejected
  because two supplied implementations for one declaration should fail loud.
- **Implement every declaration kind now.** Rejected because parallel-arc
  filter fragments and several other declaration forms are not required for
  handler/guard lowering and remain separate design work.

## Consequences

- Canonical `Net` exposes immutable handler and ordered guard declaration
  indexes.
- Runtime implementation mapping keys admit `NetUri` alongside named strings.
- Named callers retain deliberate shared binding; exact URI callers gain
  transition-local binding.
- Anonymous callable behavior can enter a Python build without entering the
  language-neutral schema as code.
- `$` cannot begin a user-authored handler or guard symbol.
- The existing combined symbol-scoping debt can close only for handlers and
  guards; filter addressing remains carried.

## Review Trigger

Revisit the positional anonymous convention if source maps or schema editing
require identities stable across guard reordering, or when composition proves
that transition-owner qualification needs information beyond the flattened
`NetPath`.
