---
date: 2026-08-19T02:54:00Z
author: Amp
kind: milestone
related:
  - CV19.DS2
  - CV19.DS3
verification:
  - UV_FROZEN=1 scripts/check quick tests/dst/joined_world.py tests/dst/joined_seal_world.py tests/dst/test_joined_seal_world.py
  - UV_FROZEN=1 uv run pytest -q tests/dst/test_joined_seal_world.py --forbid-skips
  - UV_FROZEN=1 uv run pytest -q tests/dst/test_joined_world.py tests/dst/test_joined_creation_world.py tests/dst/test_joined_registration_world.py --forbid-skips
  - UV_FROZEN=1 uv run pytest -q tests/dst --forbid-skips
  - UV_FROZEN=1 uv run pytest -q tests/project --forbid-skips
  - UV_FROZEN=1 scripts/check full
  - UV_FROZEN=1 scripts/check release
---

# Joined runtime-policy source-seal replay

## What changed

Added paired real Absurd/PostgreSQL profiles for public `Engine.seal(source)`
after a real Activity projection arms both `source/default` and
`source/subscription`. The test-owned joined transaction observer recognizes
only a transaction made entirely of `DeliveryRegistrationClosed` facts as the
runtime-policy close-all phase; handler-authored closes remain part of their
occurrence projection boundary.

The refusal profile rejects the two-record key-ordered close batch before
PostgreSQL acceptance. Detached History exposes no close, and fresh public
load reconstructs both keys armed. The host then retries the same normalized
seal command once, closes both keys atomically, and reaches `terminated`.

The acknowledgement-loss profile commits both closes and raises before the
Engine receives the commit result. Fresh public load reconstructs an empty
armed view and `terminated` without another seal command. A detached checker
derives expected close authority from accepted/refused PostgreSQL transaction
facts and canonical registration History, then compares the public armed view.
Mutation checks reject phantom closes after rollback, acknowledgement loss
without acceptance, and an armed source after accepted reload.

The refusal artifact has 14 operations, 24 journal entries including 10
checker evaluations, disposition `converged`, artifact SHA-256
`4d9788dc613842e06d4ac3f2888a8fbc92b85d41eaacafe1b3b67c41c322a508`,
profile digest
`sha256:9dd635e6c388fbab8aa599ddf64bd8a05ae29267cd8a918bd7dacd33e29a3092`,
checker digest
`sha256:ac0e87d60c844032443f4fabe11c53dd46d3d7da21d376bfdc8f8e3ec613cc3e`,
and journal digest
`sha256:935344cd185b5ca7ca65b2447bd7151315a737bf526015bf84993ca5ce198e4a`.

The acknowledgement-loss artifact has 12 operations, 21 journal entries
including 9 checker evaluations, disposition `converged`, artifact SHA-256
`054892d225e8fbd2e6a972f14ef18d8cdb11f6bc0a50a33317c7cc146d41ab5f`,
profile digest
`sha256:f24a687302ae24bcebdce19c9e8148f9d8170f302805dfe3caac27d942d61f01`,
the same checker digest, and journal digest
`sha256:8d03db3c9d21b30395d45815abf897b54647ba25bd22a368dff925cd926c7271`.

## Why it matters

`seal` is a host/runtime-policy command rather than automatic projection
recovery. A refused command must therefore reconstruct the still-open door and
permit an explicit retry, while accepted acknowledgement loss must reconstruct
the closed door and prevent an unnecessary retry. Closing two keys proves the
production close-all batch cannot expose a valid partial seal.

This pair completes CV19.DS2's declared initial named-cut matrix. DS2 is Done;
exhaustive pairwise adapter faulting is not claimed. Stateful schedule
generation and broader property falsification now belong to active CV19.DS3.

## Verification

- All 5 focused tests passed, including authored byte identity, data-only
  replay for both artifacts, and checker mutation sensitivity.
- All 82 prior joined provider/creation/registration tests passed unchanged.
- All DST tests passed: 192; all project-coherence tests passed: 29.
- `scripts/check full` passed all 2,380 tests.
- `scripts/check release` passed all 2,380 tests in both orders, with 17
  expected serial qualification deselections.

## Review and follow-up

The change is test-owned and adds no production API. State-affecting operations
cross the one World interpreter and public Engine/Worker/load/snapshot doors.
The checker consumes only detached PostgreSQL transaction, History, provider
custody, and public snapshot facts. Abrupt drop and graceful close remain
distinct. No decision record, debt item, package version, or release note is
needed.

CV19.DS3 is the next active story. Its Plan Checkpoint must choose the smallest
generated dimension that can exercise the existing normalized interpreter and
failure artifacts while preserving independent checker ownership.
