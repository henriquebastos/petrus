---
date: 2026-08-18T20:10:00Z
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

# Joined identified-delivery transaction replay

## What changed

Added paired real Absurd/PostgreSQL profiles at the identified source-delivery
transaction boundary. The refusal profile submits one stable identity through
public `Engine.deliver`, then refuses the transaction containing
`ExternalEventDelivered` and its complete source firing. Detached PostgreSQL
truth retains no identity, produced token, completed firing, or marking effect.
After abrupt drop, fresh public `load_engine` accepts the same delivery once;
its next exact redelivery returns `PriorAcknowledgement` without another
transaction or semantic fact.

The acknowledgement-loss profile commits the same delivery and source firing,
then raises after PostgreSQL acceptance. Fresh load reconstructs exactly one
identity, occurrence, and output token. Exact redelivery returns the prior
acknowledgement and leaves the six-record frontier unchanged.

One independent checker derives authority from authored delivery attempts,
accepted/refused PostgreSQL transaction evidence, and detached delivery/source
projection records. Mutation tests reject both a canonical identity backed only
by rollback and acknowledgement loss without an accepted transaction.

The refusal artifact has 10 operations, 17 journal entries including 7 checker
evaluations, disposition `external_wait`, artifact SHA-256
`f810bddb3120605f89b219247c3a9c1774e025a05dbe3fd626856e6c84261c8a`,
profile digest
`sha256:629e317559ede232b72dced7b0b85559eca975d8d4cfcf059f23594cf75097d5`,
and journal digest
`sha256:c4a340a7e6426a799f03767648cb8068424ab88b947b84f2ad50e7a91c6856ec`.

The acknowledgement-loss artifact has 8 operations, 14 journal entries
including 6 checker evaluations, disposition `external_wait`, artifact SHA-256
`91d7c02b30c2442320e6ec5a57564e4abb26099c1eb7c6369f7e816381189735`,
profile digest
`sha256:e1364e46cde114ba20465581a6d69b8684b34f2f2848c94a77eb168cd030e446`,
and journal digest
`sha256:317898902bb290ff5f6a40fb37183f7ef461932c3171a3351f588f986fed1f7f`.
Both use checker digest
`sha256:9dbfc2513ad466502f0e9f69120d4ced26a73e8dc4e8856c89568796b8ba60d8`.

## Why it matters

The source-delivery decision requires broker acknowledgement only after durable
acceptance and makes stable identity the canonical redelivery key. These paired
cuts now prove that contract at the real PostgreSQL provider boundary: rollback
cannot create a phantom accepted identity, while an accepted-but-unacknowledged
delivery cannot mint a second occurrence or token after process loss.

## Verification

- The joined profile passed all 43 tests, including authored byte identity,
  data-only replay, all thirteen prior retained fixture identities, and checker
  mutation sensitivity.
- The related joined/observation/Absurd/PostgreSQL matrix passed all 186 tests.
- All DST tests passed: 148. DST plus project coherence passed: 177.
- `scripts/check full` passed all 2,336 tests.
- `scripts/check release` passed all 2,336 tests in both orders, with 17
  expected serial qualification deselections.
- Project coherence passed all 29 tests.

## Review and follow-up

The change remains test-owned: it extends the existing public-provider
connection adapter with paired source-transaction cuts, adds two exact profiles
and one checker, and retains two artifacts. Production Engine/provider APIs and
artifact v1-v4 identities remain unchanged. Graceful close and abrupt drop
remain distinct. No debt item or decision record is needed.

CV19.DS2 remains Active. This qualifies source delivery for the public
Absurd/PostgreSQL composition only; transport acknowledgement, PostgreSQL power
loss, and the broader transaction/provider fault matrix remain unclaimed.
