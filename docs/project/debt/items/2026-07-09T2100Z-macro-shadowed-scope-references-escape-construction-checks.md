---
id: macro-shadowed-scope-references-escape-construction-checks
status: Carried
kind: design
severity: low
source: CV2 slice 7 (CEL guards) review, gpt-5.5 spec-fidelity lens; Navigator adjudicated 2026-07-09
revisit_trigger: A scope-aware CEL walker exists (e.g. for NetUri-addressed diagnostics or the validation run), or a real net hits the shadow case and the late diagnostic proves confusing in practice.
closure_condition: free_variables (or its successor) subtracts macro-bound names only within their macro body, so a shadowed out-of-scope reference is a construction-time declared mismatch for guards and completion alike, pinned by a test on the shadow case.
---

# Macro-shadowed out-of-scope references escape construction-time checks

## Description

`cel.free_variables` subtracts macro-bound names globally rather than
scope-precisely (the slice-6 conservative approximation, pinned by
`tests/petrus/impetus/binding/test_cel.py::test_a_macro_variable_shadowing_a_place_name_is_permissively_skipped`).
The permissive direction has a second face: a macro variable shadowing an
OUT-of-scope name hides the genuinely free reference too. A guard like
`p.exists(q, q.color == null) && size(q) == 0` with scope `{p}` constructs
successfully; the out-of-scope `size(q)` surfaces only at evaluation, as a
per-binding skip plus `GuardEvaluationWarning`. The same shape applies to the
completion condition's unknown-place check.

## Carrying Reason

Navigator adjudicated (2026-07-09, slice-7 review debate): defer. The miss
degrades to the ruled evaluation-error path — a deterministic skip plus a
mandatory diagnostic — so nothing mis-executes or goes silent; it is caught
later than the declared-mismatch ideal, not never. Making the extraction
scope-precise means reworking the shared substrate mid-slice and revisiting
the slice-6 pinned permissive contract, ahead of any consumer that needs it.

## Impact

Low: the escape requires an author to reuse an out-of-scope place name as a
macro variable in the same expression. The failure mode is a delayed, noisy
diagnostic (warning at enablement), not silence or wrong routing.

## Revisit Trigger

A scope-aware CEL AST walker lands (NetUri-addressed diagnostics or the
validation run are the natural owners), or the shadow case bites in practice.

## Closure Condition

Scope-precise macro subtraction with the shadow case pinned at construction
for both guard and completion compilation.

## Notes

Code breadcrumb: `src/petrus/impetus/binding/cel.py` (`free_variables` docstring).
Related: DR 2026-07-08 guard-filter-evaluation-errors (the evaluation-error
path the miss degrades to); engineering convention 22 (the slice-6 defense
and its pinned test).
