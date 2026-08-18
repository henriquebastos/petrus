---
date: 2026-08-18T18:11:46Z
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

# Joined terminal-commit-refusal replay

## What changed

Added the refused half of the real Absurd/PostgreSQL semantic-terminal
boundary. A real Worker first completes provider custody. The test-owned
connection then refuses the transaction containing `ActivityCompleted` before
PostgreSQL accepts it, leaving one completed provider task, canonical History
at `ActivityRequested`, and a poisoned writing Engine.

The World revokes and abruptly drops that generation. Fresh public
`load_engine` recollects the same provider result and records one
`ActivityCompleted` plus one projection without another Worker completion,
handler `prepare`, or task. A separate checker derives terminal authority from
completed provider custody, recorded Worker completion, and accepted/refused
PostgreSQL transactions. Its mutation test rejects a canonical terminal backed
only by the refused transaction.

The retained artifact has 12 operations, 21 journal entries including 9
checker evaluations, disposition `converged`, artifact SHA-256
`167637c4fff369f0f603da3013f9c52b7a86150fc29cac8306042cffcd599987`,
and journal digest
`sha256:c61d9286f53a66cfa7484ff6bf440a35f377b8355b55bdf6fc4f8c9a017c631b`.

## Why it matters

This pairs the already-retained accepted-but-unacknowledged terminal cut with
its definite pre-commit refusal. Provider completion remains durable authority
for recollection, while an uncommitted Petrus terminal never becomes canonical
or authorizes projection. Recovery crosses only public Engine/Worker provider
doors and does not re-execute the external work.

## Verification

- The joined profile passed all 23 tests, including authored byte identity,
  data-only replay, all seven prior retained fixture identities, and checker
  mutation sensitivity.
- The related joined/Absurd/PostgreSQL transaction matrix passed all 137 tests.
- All DST tests passed: 128. DST plus project coherence passed: 157.
- `scripts/check full` passed all 2,315 tests.
- `scripts/check release` passed all 2,315 tests in both orders, with 17
  expected serial qualification deselections.
- Project coherence passed all 29 tests.

## Follow-up

CV19.DS2 remains Active. This slice qualifies one exact semantic-terminal
commit-refusal cut; it does not claim PostgreSQL power loss, exhaustive provider
fidelity, or close the broader transaction matrix.
