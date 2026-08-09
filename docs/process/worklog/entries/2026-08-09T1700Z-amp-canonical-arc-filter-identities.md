---
date: 2026-08-09T17:00:00Z
author: Amp
kind: milestone
related:
  - docs/project/decisions/records/2026-08-09T1700Z-canonical-arc-filter-occurrence-identities.md
  - docs/project/debt/items/2026-07-09T0000Z-evaluation-diagnostics-not-neturi-addressed.md
  - docs/project/debt/items/2026-07-08T2140Z-guard-symbols-net-scoped-not-transition-local.md
verification:
  - focused schema, filter, enabledness, and v3 tests, 154 passed
  - scripts/check quick passed for all touched Python paths
  - scripts/check release parallel suite, 2045 passed
  - scripts/check release fixed-order suite, 2045 passed and 17 deselected
---

# Canonicalized arc-filter occurrence identity

## What changed

The flattened Net now derives canonical occurrence URIs for every ordered arc
and exact declaration URIs for every arc filter without changing `Arc`,
History, binding, or Net-definition v3 shapes. Parallel same-endpoint arcs use
pair-local `$N` fragments. Exact filter URI bindings can differ per occurrence;
bare names remain the explicit shared fallback.

## Why it matters

Parallel filters are now independently bindable and their evaluation warnings
identify the exact declaration rather than only an expression and endpoint
pair. This pays the final filter portions of two carried addressing debts while
preserving all existing semantic and interchange contracts.

## Verification

Focused schema, filter, enabledness, and v3 fixed-point coverage passed with
`154 passed`; static checks passed for every touched Python path. The release
gate passed with `2045 passed` in parallel and `2045 passed, 17 deselected` in
fixed order. The deselected external installation, authenticated-provider, and
Gondolin qualification routes are not claimed green.

## Follow-up

Explicit authored arc IDs remain deferred until a successor interchange
version can preserve that author intent. Generated `$N` identities are stable
for one ordered flattened definition, not across same-pair insertion or
reordering.
