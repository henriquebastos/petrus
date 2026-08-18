---
date: 2026-08-18T18:47:00Z
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
  - UV_FROZEN=1 uv run pytest -q tests/project
---

# Joined failed-terminal-commit-refusal replay

## What changed

Added the failed side of the real Absurd/PostgreSQL semantic-terminal boundary.
A real Worker reports one non-retryable `ActivityFailure`, leaving one failed
provider task. The test-owned connection then refuses the transaction
containing `ActivityFailed` before PostgreSQL accepts it, leaving canonical
History at `ActivityRequested` and poisoning the writing Engine.

The World revokes and abruptly drops that generation. Fresh public
`load_engine` recollects the same provider failure and records exactly one
`ActivityFailed` followed by one `FiringFailed`, without another Worker
failure, task, or handler `prepare`. A separate checker derives failure
authority from failed provider custody, the recorded Worker failure, and
accepted/refused PostgreSQL transactions. Its mutation test rejects a
canonical `ActivityFailed` backed only by the refused transaction.

The retained artifact has 12 operations, 21 journal entries including 9
checker evaluations, disposition `quarantined`, artifact SHA-256
`9708cdfc43d757b6e7f721a37988ae620a7c234c64fb69890526bfd6f62bb79b`,
and journal digest
`sha256:50dabde303a773fe55c4863593997f55e9685bec1fc53ffb1c496fd0f27496c3`.

## Why it matters

The earlier joined terminal profiles proved successful Worker completion and
projection. This slice proves the materially different failed-terminal fate:
refused failure state never becomes canonical, while durable failed provider
custody remains authority for fresh-load recollection and exactly one semantic
firing failure.

## Verification

- The joined profile passed all 29 tests, including authored byte identity,
  data-only replay, all nine prior retained fixture identities, and checker
  mutation sensitivity.
- The related joined/Absurd/PostgreSQL transaction matrix passed all 143 tests.
- All DST tests passed: 134. DST plus project coherence passed: 163.
- `scripts/check full` passed all 2,321 tests.
- `scripts/check release` passed all 2,321 tests in both orders, with 17
  expected serial qualification deselections.
- Project coherence passed all 29 tests.

## Follow-up

CV19.DS2 remains Active. The paired accepted-but-unacknowledged
`ActivityFailed` cut and the broader transaction/provider matrix remain; this
slice does not claim PostgreSQL power loss or exhaustive provider fidelity.
