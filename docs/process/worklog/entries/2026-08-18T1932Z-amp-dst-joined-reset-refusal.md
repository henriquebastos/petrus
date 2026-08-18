---
date: 2026-08-18T19:32:00Z
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
  - scripts/check full
  - scripts/check release
  - UV_FROZEN=1 uv run pytest -q tests/project
---

# Joined lifecycle-reset-commit-refusal replay

## What changed

Added the pre-fence side of the real Absurd/PostgreSQL lifecycle reset
boundary. A real Worker holds one generation-1 Activity when the test-owned
connection refuses the transaction containing `ScopeReset`. PostgreSQL retains
no canonical reset or cancellation attempt, the provider task stays running,
and the writing Engine poisons.

The World revokes and abruptly drops that generation while preserving the
external Worker. Fresh public `load_engine` reconstructs generation 1 and the
same invocation without another handler `prepare`. The original Worker
completion remains authoritative rather than stale; production records
exactly one `ActivityCompleted` plus one projection with no reset or
cancellation tombstone.

A separate checker derives reset, terminal, and projection authority from
detached PostgreSQL History/task custody and the accepted/refused transaction
ledger. Its mutation test rejects a canonical `ScopeReset` backed only by the
refused transaction.

The retained artifact has 21 operations, 34 journal entries including 13
checker evaluations, disposition `quiescent`, artifact SHA-256
`9dbe0e037a2c56ee97a782cfbffde073dc43b73a3c66808b87630ec72e7767ee`,
profile digest
`sha256:e101473ebade63a10309acdbe38216a09f2172d2f36640d4fae270c9f728819d`,
checker digest
`sha256:25b67f69cd2c7a17cd9ab598fe6ee0853f1c3e3748ffd746fc9c2a2271aa8484`,
and journal digest
`sha256:84b2b2e63f4212e942544c8d6aaeae0fc00309abcc4bd1506aec3895de605cda`.

## Why it matters

The existing lifecycle pair begins after `ScopeReset` is canonical and proves
repair or recognition of the separate cancellation tombstone. This slice pins
the opposite side of the first commit: when the fence does not exist, the old
lifecycle and Worker remain authoritative. Treating that completion as stale
would silently lose valid work; accepting a phantom reset would let volatile
state outrun PostgreSQL.

## Verification

- The joined profile passed all 35 tests, including authored byte identity,
  data-only replay, all eleven prior retained fixture identities, and checker
  mutation sensitivity.
- The related joined/observation/Absurd/PostgreSQL matrix passed all 178 tests.
- All DST tests passed: 140. DST plus project coherence passed: 169.
- `scripts/check full` passed all 2,328 tests.
- `scripts/check release` passed all 2,328 tests in both orders, with 17
  expected serial qualification deselections.
- Project coherence passed all 29 tests.

## Review and follow-up

The change is test-owned: it adds one named fault to the existing public
provider connection adapter, one exact profile/checker, and one retained
artifact. Production Engine/provider APIs and artifact v1-v4 identities remain
unchanged. Graceful close and abrupt drop remain distinct. No debt item or
decision record is needed.

CV19.DS2 remains Active. The paired accepted-but-unacknowledged `ScopeReset`
cut and the broader transaction/provider matrix remain; this slice does not
claim PostgreSQL power loss or provider-wide fidelity.
