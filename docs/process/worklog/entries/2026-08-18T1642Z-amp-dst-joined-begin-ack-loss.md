---
date: 2026-08-18T16:42:48Z
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

# Joined begin acknowledgement-loss replay

## What changed

Added a separately identified World v3 profile over the public Absurd Engine
provider with disposable PostgreSQL. Production commits one joined semantic
begin and task, then the test-owned connection raises as if the commit
acknowledgement were lost. The live Engine poisons; detached PostgreSQL truth
retains exactly one six-record prefix and one pending task.

Fresh public `load_engine` drives to the legitimate Worker wait without another
handler preparation, semantic append, or task. The independent checker derives
authority from recorded accepted transaction attempts and detached History/task
custody. The retained artifact has 9 operations, 15 journal entries including 6
checker evaluations, disposition `external_wait`, and digest
`sha256:e335a248d18103ea1e19e1843bb1666d760a19296cca35c7a5363ddde692466e`.

## Why it matters

The real joined-begin transaction now has both pre-commit rollback evidence and
post-commit acknowledgement-loss evidence. Recovery does not infer that an
exception means rollback and therefore does not duplicate the accepted
semantic invocation or provider task.

## Verification

- The focused joined profile passed all 11 tests, including authored byte
  identity, data-only replay, prior-fixture stability, and checker sensitivity.
- The related Absurd/PostgreSQL transaction and Dispatch matrix passed all 125
  tests.
- All DST tests passed: 116.
- DST plus project coherence passed: 145.
- `scripts/check full` passed all 2,303 tests.
- `scripts/check release` passed all 2,303 tests in both orders; the serial
  qualification run reported 17 expected deselections.

## Follow-up

CV19.DS2 remains Active. This slice models loss of a successful commit
acknowledgement at one exact joined-begin boundary; it does not claim PostgreSQL
power loss or complete the remaining provider transaction cuts.
