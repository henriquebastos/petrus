---
date: 2026-08-19T01:50:00Z
author: Amp
kind: milestone
related:
  - CV19.DS2
verification:
  - UV_FROZEN=1 scripts/check quick tests/dst/joined_world.py tests/dst/test_joined_world.py
  - UV_FROZEN=1 uv run pytest -q tests/dst/test_joined_world.py -k 'scoped_quarantine' --forbid-skips
  - UV_FROZEN=1 uv run pytest -q tests/dst/test_joined_world.py --forbid-skips
  - UV_FROZEN=1 uv run pytest -q tests/dst --forbid-skips
  - UV_FROZEN=1 uv run pytest -q tests/project --forbid-skips
  - UV_FROZEN=1 scripts/check full
  - UV_FROZEN=1 scripts/check release
---

# Joined future-scope quarantine transaction replay

## What changed

Added paired real Absurd/PostgreSQL profiles for identified delivery against a
future exact lifecycle generation. The refusal profile rejects
`ScopedDeliveryQuarantined` before PostgreSQL acceptance. Detached truth
retains the current generation but no delivery disposition; fresh public load
records the quarantine once, and exact redelivery returns the prior
quarantined acknowledgement without another transaction.

The acknowledgement-loss profile commits the quarantine and then raises
before the caller receives its acknowledgement. Fresh public load reconstructs
the accepted identity, and exact redelivery returns the prior disposition
without another History record.

The refusal artifact has 12 operations, 20 journal entries including 8 checker
evaluations, disposition `external_wait`, artifact SHA-256
`b55032380b61df27a99d0b256a2ec2a84f677a122a95f53950205b66d7ca4935`,
profile digest
`sha256:d21432b1b54898099513b50058e91024e4e64c0c8221f0a321be7a591d45bd8c`,
checker digest
`sha256:926f5ec04be3e72e08db3cfff3a7405cab05a364870ad827e8a9764a665a9cf0`,
and journal digest
`sha256:86bddb242f305b8136b772ae60ee2b05d3bf4487926ff6340a2e3ea59bf87252`.

The acknowledgement-loss artifact has 10 operations, 17 journal entries
including 7 checker evaluations, disposition `external_wait`, artifact SHA-256
`8fd756a54297965afba4f9011d85674f578f21a96c58f3d7e910cd60558c2f1a`,
profile digest
`sha256:acfe4ea69236073be8b499f5f52ad910b298e78a3f105428ba7a86f64990e041`,
checker digest
`sha256:01fc2120c068da0ce02be3bd4af0dee5de5033951c645563a2acbf0da4863b66`,
and journal digest
`sha256:4f46e664b2951f0cb7faeb4eee8d5907fe76c7486c69e11c09f25590dc12b35b`.

## Why it matters

Future-scope ingress has a terminal durable quarantine disposition without
starting a firing. Qualifying it directly proves current lifecycle authority,
future target identity, delivery custody, and redelivery acknowledgement remain
atomic across rollback and lost commit acknowledgement. The stale-generation
drop route cannot imply this quarantine path.

## Verification

- The five focused quarantine tests and all 67 joined-profile tests passed.
- All DST tests passed: 177; all project-coherence tests passed: 29.
- `scripts/check full` passed all 2,365 tests.
- `scripts/check release` passed all 2,365 tests in both orders, with 17
  expected serial qualification deselections.

## Review and follow-up

The change remains test-owned and adds no production API. State-affecting
operations cross the one World interpreter and public Engine lifecycle,
delivery, and load doors. The independent checkers derive authority from
detached PostgreSQL transaction, lifecycle, identity, and disposition facts;
mutation checks reject a phantom quarantine after rollback and acknowledgement
loss without accepted authority. Retained artifact identities and fixtures are
unchanged. Name-only and future-exact delivery share the same canonical
`ScopedDeliveryQuarantined` transaction; this slice uses the stronger detached
future target and leaves name-only routing to existing behavioral coverage. No
debt item or decision record is needed.

CV19.DS2 remains Active. Delivery-registration initialization and handler
registration effects, then `seal`, remain separate transaction cuts.
