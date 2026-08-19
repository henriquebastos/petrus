---
date: 2026-08-19T02:18:00Z
author: Amp
kind: milestone
related:
  - CV19.DS2
verification:
  - UV_FROZEN=1 scripts/check quick tests/dst/joined_creation_world.py tests/dst/test_joined_creation_world.py
  - UV_FROZEN=1 uv run pytest -q tests/dst/test_joined_creation_world.py --forbid-skips
  - UV_FROZEN=1 uv run pytest -q tests/dst --forbid-skips
  - UV_FROZEN=1 uv run pytest -q tests/project --forbid-skips
  - UV_FROZEN=1 scripts/check full
  - UV_FROZEN=1 scripts/check release
---

# Joined initial source-registration transaction replay

## What changed

Added paired real Absurd/PostgreSQL profiles for a source-transition net's
initial creation batch. This is a distinct production transaction from the
already-qualified token-bearing creation shape: public `create_engine` commits
`InstanceCreated + DeliveryRegistrationOpened` atomically when the net begins
with one source and no initial marking.

The refusal profile rejects that transaction before PostgreSQL acceptance.
Detached History contains neither instance nor registration; after abrupt
drop, fresh profile load observes absence and the same normalized
`engine.create` command retries successfully exactly once. Public snapshot then
reports one armed default registration and `awaiting` status.

The acknowledgement-loss profile commits the same two-record batch and raises
before an Engine is returned. Fresh public `load_engine` reconstructs the exact
identity and one armed registration without another creation transaction. The
independent checker derives authority from accepted/refused transaction facts,
detached PostgreSQL History, and detached public snapshot data. Mutation checks
reject a phantom registration after rollback and acknowledgement-loss evidence
without an accepted transaction.

The refusal artifact has 9 operations, 16 journal entries including 6 checker
evaluations, disposition `external_wait`, artifact SHA-256
`6ce100cb64547520030da9b0b4977e092cdab39d2895a6efedb5ebc414c2734c`,
profile digest
`sha256:59422062364f5742bc7f039de15570cd1caec8c98230002122f378e98761a31a`,
checker digest
`sha256:dd3f1df88d9740062a4726a662bb7896c7b3686367397be49f991e9253344ca4`,
and journal digest
`sha256:fd75f35182dff7f1459ccb62ced71bc1ef3820f275987623ee9e5e03d2f95891`.

The acknowledgement-loss artifact has 7 operations, 13 journal entries
including 5 checker evaluations, disposition `external_wait`, artifact SHA-256
`799189a93710b6586a46485d5e883b59b37aa377c900b301906500398ffea018`,
profile digest
`sha256:a4047cbb7ec767ba9b5644759918e4023cf24545e48fc3f3d9fe936795cfa263`,
the same checker digest, and journal digest
`sha256:f2b3ee631609f46d598aa3662ea73fd27f9d9d94e921251dcabecc06d0dec6a3`.

## Why it matters

A source net's initial delivery readiness is durable registration authority,
not an initial token. Qualifying this shape directly proves rollback cannot
expose an armed source and accepted-but-unacknowledged construction recovers it
through public load without duplicate registration. The token-bearing creation
fixtures could not imply this boundary.

## Verification

- All 10 creation-profile tests passed, including authored byte identity,
  data-only replay for all four retained creation artifacts, and checker
  mutation sensitivity.
- All DST tests passed: 182; all project-coherence tests passed: 29.
- `scripts/check full` passed all 2,370 tests.
- `scripts/check release` passed all 2,370 tests in both orders, with 17
  expected serial qualification deselections.

The first release attempt encountered one unrelated Gondolin sidecar identity
startup race in its parallel pass. That node passed immediately in isolation,
and the complete release gate then passed in both required orders.

## Review and follow-up

The change remains test-owned and adds no production API. State-affecting
operations cross the one World interpreter and only public Engine
create/load/snapshot doors. Abrupt drop and graceful close remain distinct.
Existing v1-v4 artifacts and profiles remain byte-identical. No debt item or
decision record is needed.

CV19.DS2 remains Active. Handler-result registration open/close effects and
`seal` remain separate transaction cuts.
