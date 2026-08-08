---
id: evaluation-diagnostics-not-neturi-addressed
status: Carried
kind: design
severity: low
source: CV2 slice 5 (arc filters) review, gpt-5.5 spec-fidelity lens; Navigator adjudicated 2026-07-09
revisit_trigger: NetUri / canonical addressing (ADR 0024, 0025, 0026, 0029) lands in the kernel, or a net declares same-endpoint parallel arcs whose filters need disambiguating in diagnostics.
closure_condition: Filter and guard evaluation-error diagnostics name the raising expression by its canonical declaration NetUri (arc:...#filter, transition:...#guard:sym), with a test asserting the address form, including the ADR 0029 fragment on same-endpoint parallel arcs.
---

# Evaluation-error diagnostics carry expression repr + endpoints, not canonical NetUri

## Description

DR 2026-07-08 guard-filter-evaluation-errors rule 3 requires every runtime
evaluation diagnostic to name "the expression (by NetUri), the token, and the
error". The kernel's `FilterEvaluationWarning` (slice 5) carries the filter
declaration repr (symbol name or Cel expression), the arc's endpoint pair
(`source -> target`), the token, and the error; `GuardEvaluationWarning`
(slice 3) carries symbol, transition path, token, and error. Every enumerated
payload *item* is present — only the canonical URI *form* of the expression's
address is not, because the kernel has no NetUri type yet (NetPath only).

## Carrying Reason

Building canonical arc URIs (ASCII `->` spelling, ADR 0029 fragment
disambiguation) for one warning string would be a mini addressing subsystem
created inside a review-fix commit, ahead of the addressing slice that owns it.
The slice-3 guard diagnostic passed review with the same shape and was
distilled into convention 13. Navigator adjudicated (2026-07-09, slice-5
review debate): carry as ledger debt per convention 15 — the under-
implementation cannot mis-execute today (no net declares same-endpoint
parallel filtered arcs, where the endpoint pair would under-identify).

## Impact

Low until same-endpoint parallel arcs exist: the endpoint pair uniquely
identifies the arc in every current and test net, and the expression repr
identifies the filter. Risk is an ambiguous diagnostic (not a wrong one) once
ADR 0029 parallel arcs appear before addressing lands.

## Revisit Trigger

NetUri / canonical addressing lands in the kernel (ADR 0024–0026, 0029), or a
net declares same-endpoint parallel arcs with distinct filters.

## Closure Condition

Both warning channels address the raising expression by declaration NetUri,
asserted in tests (including the fragment-disambiguated parallel-arc case).

## Notes

Warning sites: `src/petrus/impetus/petrinet/enabledness.py` (`admitted`, `guards_hold`).
Related: DR 2026-07-08 guard-filter-evaluation-errors; ADR 0029;
`docs/project/debt/items/2026-07-08T2140Z-guard-symbols-net-scoped-not-transition-local.md`
(the sibling "flat until addressing lands" debt).
