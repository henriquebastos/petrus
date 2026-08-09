---
status: Decided
raised: 2026-08-09
decided: 2026-08-09
deciders:
  - Petrus ADR 0026 and ADR 0029 composition (Driver clarification)
related:
  - docs/project/decisions/records/2026-07-06T0213Z-hermes-adr-0029-arc-identity-uses-endpoint-uri-with-optional-fragment.md
  - docs/project/decisions/records/2026-06-25T1428Z-hermes-adr-0026-typed-net-uri-schemes-and-anchored-declarations.md
  - docs/project/debt/items/2026-07-09T0000Z-evaluation-diagnostics-not-neturi-addressed.md
  - docs/project/debt/items/2026-07-08T2140Z-guard-symbols-net-scoped-not-transition-local.md
---

# Arc-filter declarations use declaration-kind-first occurrence fragments

## Question

How does one canonical URI identify a declaration attached to a parallel arc
when ADR 0029 already uses the URI's single fragment to identify the arc
occurrence and ADR 0026 uses fragments for anchored declarations?

## Decision

The flattened Net assigns arc occurrence identity from directed endpoints and
semantic arc order. A unique endpoint pair uses `arc:/p->/t`. Repeated pairs
use pair-local zero-based generated fragments `#$0`, `#$1`, and so on.

An arc filter uses a declaration-kind-first fragment. A unique arc's filter is
`arc:/p->/t#filter`; repeated occurrences use `#filter:$0`, `#filter:$1`, and
so on. The `$N` suffix identifies the owning arc occurrence, not the filter
symbol. Generated identity depends only on endpoints, pair multiplicity, and
semantic arc order—not mode, weight, color, or filter contents.

These identities are derived indexes over flattened `Net.arcs`. They do not
become fields of `Arc`, `Binding`, History, or Net-definition v3.

## Rationale

Declaration-kind-first spelling matches the existing `#guard:name` grammar
and keeps one URI fragment. Pair-local numbering avoids renaming an arc when an
unrelated earlier arc changes. Keeping identity in position-aligned Net indexes
preserves `Arc` as inscription data and correctly distinguishes repeated equal
values or even repeated references to the same `Arc` object.

## Options Considered

- **`#$0#filter`.** Rejected because a URI has one fragment and `NetUri`
  already rejects multiple `#` characters.
- **`#$0:filter`.** Rejected because owner-first spelling conflicts with the
  established declaration-kind-first grammar.
- **Put occurrence in the path or query.** Rejected because ADR 0029 fixes the
  endpoint-derived URI with optional fragment, and canonical `NetUri` rejects
  queries.
- **Store identity on `Arc` or introduce `ArcOccurrence`.** Rejected because
  occurrence identity is contextual and would disturb established Arc tuple,
  equality, enabledness, and interchange contracts.
- **Serialize identity in v3.** Rejected because dense arc position and
  endpoints already contain the derivation inputs; adding a field requires a
  successor protocol version.

## Consequences

- Filter implementation mappings may target exact declaration URIs; bare
  named symbols remain a deliberate shared fallback.
- Filter diagnostics can identify the exact parallel occurrence.
- Generated identities change when same-pair occurrences are inserted,
  deleted, or reordered.
- Explicit author-supplied arc IDs remain deferred. Adding them requires
  preserving author intent and therefore a successor interchange version.

## Review Trigger

Revisit when explicit authored arc IDs are added, source maps require more
per-occurrence metadata, or a successor Net-definition version changes arc
identity inputs.
