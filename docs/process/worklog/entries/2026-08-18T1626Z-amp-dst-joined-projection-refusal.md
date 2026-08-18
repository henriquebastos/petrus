---
date: 2026-08-18T16:26:29Z
author: Amp
kind: milestone
related:
  - CV19.DS2
verification:
  - UV_FROZEN=1 uv run pytest -q tests/dst/test_joined_world.py
  - UV_FROZEN=1 uv run pytest -q tests/dst/test_joined_world.py tests/petrus/engine/test_postgres_engine.py tests/petrus/engine/test_engine.py::TestPrivateJoinedTransactionFate tests/petrus/motus/dispatch/test_absurd_adapter.py
  - UV_FROZEN=1 uv run pytest -q tests/dst
  - UV_FROZEN=1 uv run pytest -q tests/dst tests/project
  - scripts/check full
  - scripts/check release
---

# Joined terminal and projection-commit refusal replay

## What changed

Added a separately identified World v3 profile over the public Absurd Engine
and Worker providers with disposable PostgreSQL. A real Worker completes one
task, production commits `ActivityCompleted`, and an exact connection-boundary
fault refuses the later `TokensProduced` and `FiringCompleted` transaction.
The poisoned generation is abruptly dropped and fresh public `load_engine`
projects the accepted terminal exactly once.

The profile records accepted and refused transaction attempts plus detached
task custody. Its independent checker bounds terminal authority by completed
provider custody and Worker completion, and bounds projection by accepted
projection transactions. The retained artifact has 12 operations, 21 journal
entries including 9 checker evaluations, disposition `converged`, and digest
`sha256:a4670deb5ec8841f29c8e6f716488c22cb7c91ffe3084867ae54704a8fe2ec6b`.

## Why it matters

The generic projection-recovery contract now has real joined-provider evidence
for the cut after terminal authority commits but before its projection commits.
Fresh load does not repeat Worker completion or handler preparation, preserving
the ownership boundary while qualifying a materially different transaction
fate from the two joined-begin rollback profiles.

## Verification

- The focused joined profile passed all 8 tests, including authored byte
  identity, data-only replay, and a checker-sensitivity test.
- The related Absurd/PostgreSQL transaction and Dispatch matrix passed all 122
  tests.
- All DST tests passed: 113.
- DST plus project coherence passed: 142.
- `scripts/check full` passed all 2,300 tests.
- `scripts/check release` passed all 2,300 tests in both orders; the serial
  qualification run reported 17 expected deselections.

## Follow-up

CV19.DS2 remains Active. This slice qualifies one exact joined
terminal/projection refusal and fresh-load repair; it does not claim PostgreSQL
power-loss behavior or complete the broader fault and transaction matrix.
