---
date: 2026-08-18T16:56:28Z
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

# Joined terminal acknowledgement-loss replay

## What changed

Added a separately identified World v3 profile over the public Absurd Engine
and Worker providers with disposable PostgreSQL. A real Worker completes one
task and production commits `ActivityCompleted`; the test-owned connection then
raises as if that commit acknowledgement were lost. The live Engine poisons
while detached PostgreSQL truth retains one completed task and one terminal.

Fresh public `load_engine` projects exactly once without another Worker
completion, terminal delivery, or handler preparation. The independent checker
derives terminal and projection authority from accepted transaction attempts,
provider custody, and Worker completion. The retained artifact has 12
operations, 21 journal entries including 9 checker evaluations, disposition
`converged`, and digest
`sha256:77698d04b4827861bf7f090606b37a576bdee4cb558d644147f9c34891b4f6b8`.

## Why it matters

Real-provider terminal recovery now distinguishes an accepted-but-
unacknowledged commit from both pre-commit terminal refusal and refusal of the
later projection transaction. An exception after provider acceptance cannot
cause Worker repetition or terminal redelivery.

## Verification

- The focused joined profile passed all 14 tests, including authored byte
  identity, data-only replay, all prior-fixture identities, and checker
  sensitivity.
- The related Absurd/PostgreSQL transaction and Dispatch matrix passed all 128
  tests.
- All DST tests passed: 119.
- DST plus project coherence passed: 148.
- `scripts/check full` passed all 2,306 tests.
- `scripts/check release` passed all 2,306 tests in both orders; the serial
  qualification run reported 17 expected deselections.

## Follow-up

CV19.DS2 remains Active. This slice models one exact successful terminal-commit
acknowledgement loss; it does not claim PostgreSQL power loss or complete the
remaining provider transaction and lifecycle cuts.
