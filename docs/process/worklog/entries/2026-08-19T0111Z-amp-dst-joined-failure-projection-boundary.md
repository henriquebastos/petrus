---
date: 2026-08-19T01:11:00Z
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

# Joined failed-firing projection transaction replay

## What changed

Added paired real Absurd/PostgreSQL profiles around the separate transaction
that appends `FiringFailed` after accepted `ActivityFailed`. The refusal profile
rejects the projection before PostgreSQL acceptance. Detached facts retain
failed provider custody and the canonical terminal failure but no
`FiringFailed`; fresh public load appends it exactly once.

The acknowledgement-loss profile commits `FiringFailed` and then raises before
the caller receives acknowledgement. Fresh public load reconstructs the
already-quarantined state without another projection, provider recollection,
Worker failure, task, or handler `prepare`.

The refusal artifact has 12 operations, 21 journal entries including 9 checker
evaluations, disposition `quarantined`, artifact SHA-256
`6d73210128cfa3054e2845beda9de4070d9a4e3e31ae3ceb8d5b87af11b8f543`,
profile digest
`sha256:c22a7b66688101c5f432600e244786c24af1838da69e503640605e1302ec57de`,
checker digest
`sha256:5de3ccf8c10f439e38d40d7ca4783e4162600140c12cf89f86e6aaa3ce114ac6`,
and journal digest
`sha256:bfb93abcd6616cb9c012acd6210f42f68ad9b8ac313b0cad42bc402dfd1599c1`.

The acknowledgement-loss artifact has the same operation, journal, checker,
and disposition counts, artifact SHA-256
`3324bfb058df3de2f1dda80391b210b5907b13fbd639c916ee13087b2b5a766b`,
profile digest
`sha256:fe3746c8df9bb4f34c512b0d658101e482c32bba44dba633bbdc3d7193e8540f`,
checker digest
`sha256:05205850df0b6aa382777393f3611fc38efbd6145474b0dadbc33e5445708fb3`,
and journal digest
`sha256:74ecfca17035bb137b7825e9ca0074bfcf3bb36b93ee5f3495496b602a510fa8`.

## Why it matters

Successful projection evidence does not prove the failed-firing path: failure
projects a distinct canonical record and terminates as quarantined. This pair
directly qualifies both durability sides without inferring them from
`FiringCompleted` behavior.

## Verification

- The joined profile passed all 57 tests; all DST tests passed: 167.
- DST plus project coherence passed all 196 tests.
- `scripts/check full` passed all 2,355 tests.
- `scripts/check release` passed all 2,355 tests in both orders, with 17
  expected serial qualification deselections.

## Review and follow-up

The change remains test-owned and adds no production API. Every operation
crosses the one World interpreter and public Engine/Worker doors. The
independent checkers derive authority from detached PostgreSQL transaction and
History facts plus Absurd custody; mutation checks reject a phantom projection
after refusal and acknowledgement loss without accepted authority. Retained
artifact identities and fixtures are unchanged. No debt item or decision
record is needed.

CV19.DS2 remains Active for the broader provider/fault matrix.
