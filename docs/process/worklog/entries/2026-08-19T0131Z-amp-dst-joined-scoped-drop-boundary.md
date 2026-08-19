---
date: 2026-08-19T01:31:00Z
author: Amp
kind: milestone
related:
  - CV19.DS2
verification:
  - UV_FROZEN=1 scripts/check quick tests/dst/joined_world.py tests/dst/test_joined_world.py
  - UV_FROZEN=1 uv run pytest -q tests/dst/test_joined_world.py --forbid-skips
  - UV_FROZEN=1 uv run pytest -q tests/dst --forbid-skips
  - UV_FROZEN=1 uv run pytest -q tests/dst tests/project --forbid-skips
  - UV_FROZEN=1 scripts/check full
  - UV_FROZEN=1 scripts/check release
---

# Joined stale-scope drop transaction replay

## What changed

Added paired real Absurd/PostgreSQL profiles for identified delivery against a
stale exact lifecycle generation. The refusal profile rejects
`ScopedDeliveryDropped` before PostgreSQL acceptance. Detached truth retains
the accepted open/reset fence but no delivery disposition; fresh public load
records the drop once, and a second exact redelivery returns the prior dropped
acknowledgement without another transaction.

The acknowledgement-loss profile commits the drop and then raises before the
caller receives its acknowledgement. Fresh public load reconstructs the
accepted identity, and exact redelivery returns the prior disposition without
another History record.

The refusal artifact has 13 operations, 22 journal entries including 9 checker
evaluations, disposition `external_wait`, artifact SHA-256
`630a6f1b0bad1a2e92c1761f03867a9f3ba4b22cadea4be0a55daaee72904345`,
profile digest
`sha256:1f0dce02d9e50884c82c819ea8625bf6f33d8b129210a17bcdf38598d6e72274`,
checker digest
`sha256:cd347ef709a94c34a8f81212ebefa8b6b9f599def47bca4b03c61cdf45971637`,
and journal digest
`sha256:933ebfb4d452f4361afe2e1d850ae88187a8e58ba5a191dd46d03adbc60858ee`.

The acknowledgement-loss artifact has 11 operations, 19 journal entries
including 8 checker evaluations, disposition `external_wait`, artifact SHA-256
`810aad82f71f205dd52f272c2d4080d1313a2e9a20f3e7c3e75fb785ce81cbe7`,
profile digest
`sha256:e38148d8e4417274ceee853ca33083f2e02b89350141f794990214ae518da29e`,
checker digest
`sha256:b8c9096b0ef6e4333e21edeb110f54a698004a4a4438f875786fff4e7b93e7cc`,
and journal digest
`sha256:ff02e6f1efa811b421011de0bdb73de9ea685ecee7b126a08fd60a0243bd59e9`.

## Why it matters

Stale-scope ingress has a terminal durable disposition without starting a
firing. Qualifying it directly proves lifecycle fencing, identity custody, and
redelivery acknowledgement remain atomic across rollback and lost commit
acknowledgement; ordinary identified-delivery evidence does not imply this
path.

## Verification

- The joined profile passed all 62 tests; all DST tests passed: 172.
- DST plus project coherence passed all 201 tests.
- `scripts/check full` passed all 2,360 tests.
- `scripts/check release` passed all 2,360 tests in both orders, with 17
  expected serial qualification deselections.

## Review and follow-up

The change remains test-owned and adds no production API. State-affecting
operations cross the one World interpreter and public Engine lifecycle,
delivery, and load doors. The independent checkers derive authority from
detached PostgreSQL transaction, lifecycle, identity, and disposition facts;
mutation checks reject a phantom drop after rollback and acknowledgement loss
without accepted authority. Retained artifact identities and fixtures are
unchanged. No debt item or decision record is needed.

CV19.DS2 remains Active. The future-generation/name-only quarantine disposition
and delivery-registration boundaries remain separate follow-up cuts.
