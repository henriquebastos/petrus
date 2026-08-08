---
id: token-element-validation-is-per-boundary-not-kernel-wide
status: Carried
kind: design
severity: low
source: CV2 slice 8 (ingress) review debate — two lenses rated missing deliver() validation a blocker, two skeptics refuted it to kernel-wide posture; Navigator adjudicated 2026-07-09
revisit_trigger: The validation-run layer lands, or a non-Token object observed inside a marking or history record in practice, or a second boundary grows its own ad-hoc element check.
closure_condition: A deliberate kernel-wide posture — validate token elements at every foreign-data boundary (Marking construction/seed, handler deposits, delivery), or document type-trust as the contract everywhere — applied uniformly and pinned by tests.
---

# Token-element validation is per-boundary, not kernel-wide

## Description

`NetInstance.deliver` validates that every delivered item is a `Token`
(slice-8 Navigator ruling: ingress is the seam where outside-world data enters
the kernel, and a `str` payload is a `Sequence` that would otherwise explode
into character "tokens", recorded and routed silently). The sibling token
boundaries do not validate: `Marking()`/`Marking.deposit` accept any object,
`NetInstance(marking=...)` seeds and records unvalidated queues, and `fire()`
deposits whatever a handler returns. The kernel therefore has one validated
boundary and several trusting ones — a posture inconsistency, not a defect:
replay stays self-consistent either way (the skeptics verified), and typed
arcs fail loud on garbage at `admits`.

## Carrying Reason

Making element validation kernel-wide is a posture decision spanning every
slice-1..8 boundary and belongs to the validation-run layer, not a review-fix
commit. The Navigator chose: guard the ingress seam now, ledger the uniform
posture question.

## Impact

Low: a caller violating a declared type contract at a non-ingress boundary
can still put non-Token objects into a marking and its history records.

## Notes

Code breadcrumb: `src/petrus/impetus/instance/__init__.py` (`deliver` docstring).
