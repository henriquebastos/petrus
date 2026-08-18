---
date: 2026-08-18T17:19:53Z
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

# Joined lifecycle cancellation-refusal replay

## What changed

Added a separately identified World v3 profile over the public Absurd Engine
and Worker providers with disposable PostgreSQL. Production commits
`ScopeReset`, then the test-owned connection refuses the separate transaction
which would turn the real running task into a cancellation tombstone. Detached
PostgreSQL truth retains generation 2 and running custody while the live Engine
poisons.

The World revokes and drops only that Engine generation, preserving the
external Worker. Fresh public `load_engine` commits one tombstone against the
same task; the old Worker's completion is then refused as stale without an
`ActivityCompleted` or business projection. The independent checker derives
authority from authored lifecycle and Worker facts, accepted/refused
transaction attempts, and detached History/task custody. The retained artifact
has 19 operations, 31 journal entries including 12 checker evaluations,
disposition `quiescent`, and digest
`sha256:1c49f2de218e8579894a9f55248e81b3e058a977a2ebffecd82b19880661dbf0`.

## Why it matters

The provider-neutral cancellation-refusal scenario now has real-provider
qualification for the stronger operational transaction shape. A canonical
lifecycle fence remains authority when real tombstone persistence refuses;
fresh construction repairs custody without semantic re-execution, and provider
fencing prevents a stale claimant from crossing the reset.

## Verification

- The joined profile passed all 17 tests, including authored byte identity,
  data-only replay, all five prior retained fixture identities, and checker
  mutation sensitivity.
- The related joined/Absurd/PostgreSQL transaction matrix passed all 131 tests;
  focused production lifecycle/tombstone behavior passed 2 tests.
- All DST tests passed: 122. DST plus project coherence passed: 151.
- `scripts/check full` passed all 2,309 tests.
- The first release-order run encountered an unrelated 50 ms ZeroMQ server
  startup timeout. Its exact test passed immediately in isolation; a complete
  `scripts/check release` rerun then passed all 2,309 tests in both orders, with
  17 expected serial qualification deselections.

## Follow-up

CV19.DS2 remains Active. This slice qualifies one exact post-reset
cancellation-commit refusal; it does not claim PostgreSQL power loss or close
the broader provider transaction and lifecycle matrix.
