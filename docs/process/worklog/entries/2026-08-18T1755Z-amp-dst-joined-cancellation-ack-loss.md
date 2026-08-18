---
date: 2026-08-18T17:55:25Z
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

# Joined lifecycle cancellation-acknowledgement-loss replay

## What changed

Added the accepted half of the real Absurd/PostgreSQL lifecycle-cancellation
boundary. Production commits `ScopeReset`, commits the separate transaction
which turns the running task into a cancellation tombstone, and then receives
an injected acknowledgement loss. Detached PostgreSQL observations retain
generation 2 and exactly one cancelled task while the writing Engine poisons.

The World revokes and abruptly drops that Engine generation while preserving
the external Worker. Fresh public `load_engine` recognizes the existing
tombstone without another `cancel_task`, semantic append, task, or handler
`prepare`; the old Worker's completion is still refused as stale. A separate
checker derives authority from accepted lifecycle transaction attempts and
detached PostgreSQL History/task facts. Its mutation test rejects an
acknowledgement-loss claim without an accepted tombstone transaction.

The retained artifact has 19 operations, 31 journal entries including 12
checker evaluations, disposition `quiescent`, artifact SHA-256
`e7c39527f12dba009c94b5b7adff3afa13b9301c7bf1157056a26c3bff8f047c`,
and journal digest
`sha256:c369eda31394c6de8287f23ea462c448fd2a7fb4e894a9ad163fd8b99c44630b`.

## Why it matters

The prior cancellation slice proved repair after definite pre-commit refusal.
This paired slice proves the ambiguous accepted side: reconstruction does not
repeat a provider mutation merely because the caller did not receive its
acknowledgement. The canonical lifecycle fence and provider tombstone remain
singular, and a stale claimant cannot cross the reset.

## Verification

- The joined profile passed all 20 tests, including authored byte identity,
  data-only replay, all six prior retained fixture identities, and checker
  mutation sensitivity.
- The related joined/Absurd/PostgreSQL transaction matrix passed all 134 tests.
- All DST tests passed: 125. DST plus project coherence passed: 154.
- `scripts/check full` passed all 2,312 tests.
- `scripts/check release` passed all 2,312 tests in both orders, with 17
  expected serial qualification deselections.
- Project coherence passed all 29 tests.

## Follow-up

CV19.DS2 remains Active. This slice qualifies one exact post-commit
cancellation acknowledgement-loss cut; it does not claim PostgreSQL power loss,
exhaustive provider fidelity, or close the broader transaction and lifecycle
matrix.
