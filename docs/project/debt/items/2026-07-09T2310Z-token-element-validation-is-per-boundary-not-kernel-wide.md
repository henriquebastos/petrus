---
id: token-element-validation-is-per-boundary-not-kernel-wide
status: Carried
kind: design
severity: low
source: CV2 slice 8 (ingress) review debate — two lenses rated missing deliver() validation a blocker, two skeptics refuted it to kernel-wide posture; Navigator adjudicated 2026-07-09
revisit_trigger: A standalone Marking becomes a foreign-data boundary, a non-Token object is observed in one in practice, or another non-History token boundary grows an ad-hoc element check.
closure_condition: A deliberate standalone-value posture — validate token elements in Marking construction/deposit, or document type-trust as that API's contract — applied uniformly and pinned by tests.
---

# Token-element validation is per-boundary, not kernel-wide

## Description

`Instance.accept_delivery` validates every delivered item as a `Token` before
mutation. Shared writer validation now applies the same exact-Token rule to
every canonical History batch, including Instance construction seeds and
handler completion deposits. The authoritative Engine/Instance path therefore
cannot write or resume non-Token queue content.

The standalone value APIs remain type-trusting: `Marking()` and
`Marking.deposit` accept any object at runtime. That residual boundary does not
enter canonical History through Instance construction—the shared writer rejects
it before append—but its public runtime posture is still less strict than its
`Token` type contract. This is a bounded standalone-value inconsistency, not an
authority or replay defect.

## Carrying Reason

The authoritative writer posture is now uniform. Extending runtime validation
into standalone `Marking` value construction remains a separate public-contract
decision without an observed authority-path defect, so it stays carried rather
than expanding this delivery seam.

## Impact

Low: a caller violating the declared standalone `Marking` type contract can
hold non-Token objects until an operation rejects them. Instance construction
refuses that content before it reaches canonical History.

## Notes

Code breadcrumbs: `src/petrus/impetus/history/__init__.py`
(`validate_history_record_values`), `src/petrus/impetus/instance/__init__.py`
(`accept_delivery`), and `src/petrus/impetus/petrinet/marking.py` (`Marking`).
