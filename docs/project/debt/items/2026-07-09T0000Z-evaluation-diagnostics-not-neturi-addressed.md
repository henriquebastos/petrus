---
id: arc-filter-evaluation-diagnostics-not-neturi-addressed
status: Paid
kind: design
severity: low
source: CV2 slice 5 (arc filters) review, gpt-5.5 spec-fidelity lens; Navigator adjudicated 2026-07-09
revisit_trigger: Canonical arc-filter declaration identities land, or a net declares same-endpoint parallel arcs whose filters need disambiguating in diagnostics.
closure_condition: Filter evaluation-error diagnostics name the raising expression by canonical declaration NetUri (arc:...#filter), with a test asserting the ADR 0029 fragment on same-endpoint parallel arcs. Guard diagnostics are paid.
---

# Arc-filter evaluation diagnostics carry expression repr + endpoints, not canonical NetUri

## Description

DR 2026-07-08 guard-filter-evaluation-errors rule 3 requires every runtime
evaluation diagnostic to name "the expression (by NetUri), the token, and the
error". Guard diagnostics now carry their exact transition declaration
`NetUri`. `FilterEvaluationWarning` still carries the filter declaration repr
(symbol name or Cel expression), the arc's endpoint pair (`source -> target`),
the token, and the error. Every payload item is present, but flattened arcs do
not yet have canonical occurrence/declaration identities, including fragments
for same-endpoint parallel arcs, so the filter's address remains incomplete.

## Carrying Reason

`NetUri` and canonical transition declaration indexes now exist, paying the
guard half. Building only a warning-local arc URI would still create a partial
identity subsystem ahead of the flattened Net's owning arc occurrence index.
The filter remainder stays carried rather than deriving an address no other
consumer can resolve. The under-implementation cannot mis-execute; it affects
diagnostic discrimination only.

## Impact

Low until same-endpoint parallel arcs exist: the endpoint pair uniquely
identifies the arc in every current and test net, and the expression repr
identifies the filter. Risk is an ambiguous diagnostic (not a wrong one) once
ADR 0029 parallel arcs appear before addressing lands.

## Revisit Trigger

Canonical arc-filter occurrence/declaration identities land, or a net declares
same-endpoint parallel arcs with distinct filters.

## Closure Condition

The filter warning addresses the raising expression by declaration NetUri,
asserted in tests including the fragment-disambiguated parallel-arc case.

## Notes

Warning sites: `src/petrus/impetus/petrinet/enabledness.py` (`admitted`, `guards_hold`).
Related: DR 2026-07-08 guard-filter-evaluation-errors; ADR 0029;
`docs/project/debt/items/2026-07-08T2140Z-guard-symbols-net-scoped-not-transition-local.md`
(the sibling "flat until addressing lands" debt).

**Guard payment / filter re-adjudication 2026-08-09:** exact guard declaration
URIs are shipped and used in evaluation diagnostics. Arc-filter declaration
identities are still absent, so this item remains `Carried` only for filters;
its metadata and carrying reason now describe the current boundary.

## Payment

Paid on 2026-08-09. The flattened Net now derives canonical arc occurrence and
filter declaration URIs in semantic arc order. `FilterEvaluationWarning`
includes the exact declaration URI, and parallel same-endpoint coverage pins
distinct `#filter:$0` and `#filter:$1` diagnostics while preserving
error-means-not-admitted behavior.
