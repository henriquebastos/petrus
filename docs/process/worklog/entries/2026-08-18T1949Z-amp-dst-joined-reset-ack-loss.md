---
date: 2026-08-18T19:49:00Z
author: Amp
kind: milestone
related:
  - CV19.DS2
verification:
  - UV_FROZEN=1 scripts/check quick tests/dst/joined_world.py tests/dst/test_joined_world.py
  - UV_FROZEN=1 uv run pytest -q tests/dst/test_joined_world.py
  - UV_FROZEN=1 uv run pytest -q tests/dst/test_joined_world.py tests/petrus/engine/test_observation.py tests/petrus/engine/test_postgres_engine.py tests/petrus/engine/test_engine.py::TestPrivateJoinedTransactionFate tests/petrus/motus/dispatch/test_absurd_adapter.py
  - UV_FROZEN=1 uv run pytest -q tests/dst
  - UV_FROZEN=1 uv run pytest -q tests/dst tests/project
  - UV_FROZEN=1 scripts/check full
  - UV_FROZEN=1 scripts/check release
  - UV_FROZEN=1 uv run pytest -q tests/project
---

# Joined lifecycle-reset acknowledgement-loss replay

## What changed

Added the accepted side of the real Absurd/PostgreSQL canonical reset
boundary. A real Worker holds one generation-1 Activity when production commits
`ScopeReset`; the test-owned connection then loses that transaction's
acknowledgement before the separate cancellation transaction begins.
PostgreSQL retains canonical generation 2 and the running task while the
writing Engine poisons.

The World revokes and abruptly drops that generation while preserving the
external Worker. Fresh public `load_engine` reconstructs the accepted fence
and repairs exactly one cancellation tombstone against the original
idempotency key. The old Worker's completion is refused as stale, and no
ordinary terminal or business projection crosses the fence.

A separate checker derives reset and cancellation authority from detached
PostgreSQL History/task custody and the accepted lifecycle-transaction ledger.
Its mutation test rejects reset acknowledgement loss without an accepted
canonical `ScopeReset`.

The retained artifact has 19 operations, 31 journal entries including 12
checker evaluations, disposition `quiescent`, artifact SHA-256
`091a75c90c33f9bc969bc426fbc62d9b85ca1a3127782b2bd6adf5c595a891c2`,
profile digest
`sha256:0507a9a159398c14eedf636d63672720313f6b05f9e010ed1110f07f660de0f8`,
checker digest
`sha256:37b7a0bacb6794f2045cd757daf23140f01d093d35e896cd18aa41347e884c3a`,
and journal digest
`sha256:58cb1b8cec3eb0dcb9329c64a3da48b2c839b96a149b5d7308edddab3e1bbf88`.

## Why it matters

Together with the pre-commit refusal fixture, this pins both sides of the
canonical reset transaction. Before acceptance, generation 1 and its Worker
remain authoritative. After acceptance, generation 2 is authoritative even if
the writer never receives the acknowledgement, so fresh load must repair
cancellation and fence the old Worker. Confusing those outcomes either loses
valid work or lets stale work cross a durable lifecycle fence.

## Verification

- The joined profile passed all 38 tests, including authored byte identity,
  data-only replay, all twelve prior retained fixture identities, and checker
  mutation sensitivity.
- The related joined/observation/Absurd/PostgreSQL matrix passed all 181 tests.
- All DST tests passed: 143. DST plus project coherence passed: 172.
- `scripts/check full` passed all 2,331 tests.
- `scripts/check release` passed all 2,331 tests in both orders, with 17
  expected serial qualification deselections.
- Project coherence passed all 29 tests.

## Review and follow-up

The change remains test-owned: it adds one named post-commit fault to the
existing public provider connection adapter, one exact profile/checker, and
one retained artifact. Production Engine/provider APIs and artifact v1-v4
identities remain unchanged. Graceful close and abrupt drop remain distinct.
No debt item or decision record is needed.

CV19.DS2 remains Active. The canonical reset transaction is now paired, but
the broader transaction/provider fault matrix remains; this slice does not
claim PostgreSQL power loss or provider-wide fidelity.
