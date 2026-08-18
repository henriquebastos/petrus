---
date: 2026-08-18T15:35:25Z
author: amp
kind: milestone
related:
  - CV19.DS2
verification:
  - UV_FROZEN=1 uv run pytest -q tests/dst/test_joined_world.py (3 passed)
  - joined-provider and transaction matrix (33 passed)
  - UV_FROZEN=1 uv run pytest -q tests/dst (108 passed)
  - UV_FROZEN=1 uv run pytest -q tests/dst tests/project (137 passed)
  - retained joined-begin replay (external_wait; 9 operations; 16 journal entries; 6 checker evaluations)
  - scripts/check full (2,295 passed)
  - scripts/check release (2,295 passed in both orders; 17 expected serial deselections)
---

# Deterministic joined-begin rollback and reconstruction

## What changed

A separately identified provider-backed DST profile now drives the public
`petrus.engine.absurd` composition against disposable PostgreSQL. It refuses
the joined transaction after production has prepared `CandidateSelected`, the
firing prefix, `ActivityRequested`, and the Absurd task spawn but before the
connection accepts the transaction. Independent PostgreSQL observation proves
that only construction remains durable and no task escaped rollback.

The World revokes and abruptly drops the poisoned generation. Fresh public
provider load reconstructs the prior marking, prepares the work anew because
no invocation was durable, and commits exactly one begin plus one pending
task. A detached checker continuously equates canonical candidate, firing,
request, and task counts with the connection adapter's accepted-transaction
ledger and has a mutation-sensitive phantom-task rejection.

## Why it matters

The earlier Dispatch-refusal artifact proves the split outbox posture after an
accepted `ActivityRequested`; it cannot prove the stronger Absurd guarantee.
This paired artifact reaches the actual joined History/Dispatch ownership
boundary without exporting private Engine resources or Coordinator handles and
corrects the guidance that had described request-before-dispatch as universal.

The evidence remains explicitly split: deterministic World/replay mechanics
come from DST, while commit-or-vanish fidelity comes from the pinned real
PostgreSQL/Absurd provider. The profile does not claim database power-loss,
Worker, transport, or provider-wide fidelity.

## Verification

The data-only retained replay passed with `external_wait`, 9 operations, 16
journal entries, 6 checker evaluations, and digest
`sha256:0b2129eaf3802d174a5526f5e32b0e6de8f923cd2d8ce3e05bd89c2904c930c7`.
Focused profile tests passed all 3 cases, the joined-provider and transaction
matrix passed 33, DST passed 108, and DST plus project passed 137. Full and
release gates passed all 2,295 tests; release passed both its four-worker and
fixed-order runs with 17 expected qualification deselections.

## Follow-up

CV19.DS2 remains Active for the remaining joined transaction/fault matrix. No
production API, supported DST compatibility contract, artifact schema, or
prior profile identity changed in this slice.
