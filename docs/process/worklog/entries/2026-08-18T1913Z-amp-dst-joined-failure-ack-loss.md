---
date: 2026-08-18T19:13:00Z
author: Amp
kind: milestone
related:
  - CV19.DS2
verification:
  - UV_FROZEN=1 scripts/check quick src/petrus/impetus/observation.py tests/petrus/engine/test_observation.py tests/dst/joined_world.py tests/dst/test_joined_world.py
  - UV_FROZEN=1 uv run pytest -q tests/petrus/engine/test_observation.py
  - UV_FROZEN=1 uv run pytest -q tests/dst/test_joined_world.py
  - UV_FROZEN=1 uv run pytest -q tests/dst/test_joined_world.py tests/petrus/engine/test_observation.py tests/petrus/engine/test_postgres_engine.py tests/petrus/engine/test_engine.py::TestPrivateJoinedTransactionFate tests/petrus/motus/dispatch/test_absurd_adapter.py
  - UV_FROZEN=1 uv run pytest -q tests/dst
  - UV_FROZEN=1 uv run pytest -q tests/dst tests/project
  - scripts/check full
  - scripts/check release
  - UV_FROZEN=1 uv run pytest -q tests/project
---

# Joined failed-terminal-acknowledgement-loss replay

## What changed

Added the accepted side of the real Absurd/PostgreSQL failed-terminal
boundary. A real Worker reports one non-retryable `ActivityFailure`, leaving
failed provider custody. Production commits `ActivityFailed`, but the test
connection loses that transaction's acknowledgement and poisons the writing
Engine.

The World revokes and abruptly drops that generation. Fresh public
`load_engine` reconstructs the accepted failure and records exactly one
`FiringFailed`, without provider recollection, another Worker failure, task,
or handler `prepare`. A separate checker derives failure authority from failed
provider custody, recorded Worker failure, and accepted PostgreSQL transaction
facts. Its mutation test rejects an acknowledgement-loss claim without an
accepted failed-terminal transaction.

Fixture generation exposed a production observation defect: a fresh load with
a frozen failure could not produce the public protocol-v1 snapshot because the
snapshot retained the live `ActivityFailure` object. The observation owner now
detaches that failure into the strict `error`, `kind`, `details`, `retryable`,
and `retry_after` value already represented by the durable records. Successful
result snapshots retain their existing shape. A focused production regression
pins the classified-failure value.

The retained artifact has 12 operations, 21 journal entries including 9
checker evaluations, disposition `quarantined`, artifact SHA-256
`f94daf5c9ffeeb90316e839a8122b22a34c0dfafeecf9175c47ae34115df3a65`,
profile digest
`sha256:689d77f23e76c6f0d6749a1d71e6803995b094d3f94aba6456e25280f2070195`,
checker digest
`sha256:d8a756cd37b254d1687b22abcc5e5da6d7e3e4d6307928e10f8eeb2c98bd373e`,
and journal digest
`sha256:793402ed31fd80eb63a76c755ef31abdea120f9acb06cdb76cd7c74de6a1c9e1`.

## Why it matters

The paired refusal slice proved that failed provider custody can be recollected
when PostgreSQL rejected `ActivityFailed`. This slice proves the opposite
authority: once PostgreSQL accepted `ActivityFailed`, fresh load must finish
the frozen firing from History rather than repeat provider collection or
failure reporting. Together they pin both sides of the failed-terminal commit
ambiguity without widening the public Engine or DST contracts.

## Verification

- The public observation suite passed all 29 tests.
- The joined profile passed all 32 tests, including authored byte identity,
  data-only replay, all ten prior retained fixture identities, and checker
  mutation sensitivity.
- The related joined/observation/Absurd/PostgreSQL matrix passed all 175 tests.
- All DST tests passed: 137. DST plus project coherence passed: 166.
- `scripts/check full` passed all 2,325 tests.
- `scripts/check release` passed all 2,325 tests in both orders, with 17
  expected serial qualification deselections.
- Project coherence passed all 29 tests.

## Review and follow-up

The production repair stays within the existing snapshot owner and preserves
successful protocol-v1 values; no adapter or new public type was introduced.
The DST profile uses only public Engine/provider doors, keeps graceful close
distinct from abrupt drop, and judges authority through detached
PostgreSQL/provider facts. No new technical debt or decision record is needed.

CV19.DS2 remains Active. Broader transaction/provider cuts remain unqualified;
this slice does not claim PostgreSQL power loss, transport behavior, or
provider-wide fidelity.
