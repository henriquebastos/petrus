---
date: 2026-08-18T14:35:56Z
author: amp
kind: milestone
related:
  - CV19.DS2
verification:
  - UV_FROZEN=1 uv run pytest -q tests/dst (101 passed)
  - Dispatch-refusal replay (converged; 14 operations; 24 journal entries; 9 checker evaluations)
  - scripts/check full (2,288 passed)
  - scripts/check release (2,288 passed in both orders; 17 expected serial deselections)
---

# Deterministic Dispatch-refusal reconstruction

## What changed

A new exact public-Engine DST profile refuses the first `Dispatch.dispatch`
after production History accepts the complete Activity-request boundary. The
profile records no custody, abruptly drops the poisoned Engine, loads a fresh
Engine and Dispatch graph, and observes production reconciliation republish
the byte-equivalent invocation without calling the Activity handler's
`prepare` again. It then completes and projects that accepted invocation.

The profile's detached checker derives terminal authority from its Dispatch
attempt ledger and continuously requires one canonical Activity request, one
total preparation, refused-then-accepted custody, stable invocation content,
and no terminal or projection before acceptance. A mutation-sensitive checker
test rejects both re-preparation and changed redispatch. The strict version-3
artifact records the fault, process cut, fresh load, checker evaluations, and
converged result through the existing World interpreter.

## Why it matters

The `activity_requested` outbox boundary is now exercised as a retained DST
story rather than inferred only from focused Coordinator tests. The scenario
shows that canonical History can safely outrun refused external custody and
that process reconstruction—not reuse of poisoned memory—restores progress
without recomputing the external invocation.

## Verification

The focused DST suite passed 101 tests. The retained replay returned `pass` /
`converged` across 14 operations and 24 journal entries, including 9
independent checker evaluations, with digest
`sha256:63301ff867ae1c9950d0307e9ad74952e4c10105e3d60d24cd00a5e0496f733a`.
The full gate passed all 2,288 tests. The release gate passed the same 2,288
tests in both its four-worker and fixed-order serial runs, with 17 expected
qualification deselections in the latter.

## Follow-up

CV19.DS2 remains Active for the broader lifecycle and joined-transaction fault
matrix. The scripted adapter proves Petrus's public Dispatch contract and
semantic recovery; it does not qualify LocalDispatch storage, transport,
provider execution, or operating-system failure, which remain DS4 boundaries.
