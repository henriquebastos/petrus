---
date: 2026-08-18T18:29:30Z
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

# Joined projection-acknowledgement-loss replay

## What changed

Added the accepted half of the real Absurd/PostgreSQL projection transaction
boundary. After a real Worker completes provider custody, production commits
`ActivityCompleted`, `TokensProduced`, and `FiringCompleted`. The test-owned
connection then loses the projection transaction's acknowledgement, leaving
completed provider custody, fully converged canonical History, and a poisoned
writing Engine.

The World revokes and abruptly drops that generation. Fresh public
`load_engine` reconstructs the converged state without another Worker
completion, terminal, task, projection, or handler `prepare`. A separate
checker derives projection authority from completed provider custody, recorded
Worker completion, and accepted PostgreSQL begin, terminal, and projection
transactions. Its mutation test rejects an acknowledgement-loss claim without
an accepted projection transaction.

The retained artifact has 12 operations, 21 journal entries including 9
checker evaluations, disposition `converged`, artifact SHA-256
`ba6c44d6f1ac5037a69403506b34b1d9fc355ed791593065e99d052ec2dcbbb2`,
and journal digest
`sha256:39110a67203cfcaa35ae527bfd9dbbd4a9ed33322b5e4fbf3cd29d5c4e83083d`.

## Why it matters

This pairs the retained projection-commit refusal with the accepted but
unacknowledged side of the same boundary. Fresh load distinguishes absent
projection authority, which must be repaired, from accepted projection
authority, which must be reconstructed without repeating application work.
Recovery crosses only public Engine/Worker provider doors.

## Verification

- The joined profile passed all 26 tests, including authored byte identity,
  data-only replay, all eight prior retained fixture identities, and checker
  mutation sensitivity.
- The related joined/Absurd/PostgreSQL transaction matrix passed all 140 tests.
- All DST tests passed: 131. DST plus project coherence passed: 160.
- `scripts/check full` passed all 2,318 tests.
- `scripts/check release` passed all 2,318 tests in both orders, with 17
  expected serial qualification deselections.
- Project coherence passed all 29 tests.

## Follow-up

CV19.DS2 remains Active. This slice qualifies one exact post-commit
acknowledgement-loss cut; it does not claim PostgreSQL power loss, exhaustive
provider fidelity, or close the broader transaction matrix.
