---
date: 2026-08-19T02:38:00Z
author: Amp
kind: milestone
related:
  - CV19.DS2
verification:
  - UV_FROZEN=1 scripts/check quick tests/dst/joined_world.py tests/dst/joined_registration_world.py tests/dst/test_joined_registration_world.py
  - UV_FROZEN=1 uv run pytest -q tests/dst/test_joined_registration_world.py --forbid-skips
  - UV_FROZEN=1 uv run pytest -q tests/dst/test_joined_world.py tests/dst/test_joined_creation_world.py --forbid-skips
  - UV_FROZEN=1 uv run pytest -q tests/dst --forbid-skips
  - UV_FROZEN=1 uv run pytest -q tests/project --forbid-skips
  - UV_FROZEN=1 scripts/check full
  - UV_FROZEN=1 scripts/check release
---

# Joined handler-registration projection replay

## What changed

Added paired real Absurd/PostgreSQL profiles for handler-authored delivery
registration effects in an Activity projection. The effectful handler closes
the initial `source/default` registration and opens `source/replacement` in the
same production transaction as `TokensProduced` and `FiringCompleted`.

The refusal profile rejects that four-record projection batch before
PostgreSQL acceptance. Detached History retains the frozen
`ActivityCompleted`, completed provider custody, and only the default source
registration. After abrupt drop, fresh public load retries deterministic
projection once and public snapshot exposes only the replacement registration.

The acknowledgement-loss profile commits the same batch and raises before the
Engine receives the commit result. Fresh public load reconstructs the exact
replacement registration without another projection, Worker completion, or
handler preparation. A detached checker derives expected authority from the
accepted/refused PostgreSQL transaction ledger and canonical History, then
compares the public armed-registration view. Mutation checks reject phantom
effects after rollback, acknowledgement loss without accepted projection, and
a stale default registration after reload.

A narrow test-owned handler factory hook on the existing joined profile permits
this effectful handler without changing any existing profile identity or
artifact. All retained joined fixtures remained exact.

The refusal artifact has 12 operations, 21 journal entries including 9 checker
evaluations, disposition `external_wait`, artifact SHA-256
`4d53fb5c85584945da0fae8cb522e74146555c05815ee6d1c0423bc8912315a7`,
profile digest
`sha256:1e0086d5d8bc017a8591e07f9caf5c41a05c3633eedf5078d2576ecfade03c86`,
checker digest
`sha256:0b3edc3e45515fe76b356ceba9e491969f4d9bf5ea9939569f02ab1cb83adbe6`,
and journal digest
`sha256:7c0d1b65029dd0ac9808b912e154c1df516ac23248efead9b73ebc73a97f906b`.

The acknowledgement-loss artifact has the same operation, journal, and
checker counts, disposition `external_wait`, artifact SHA-256
`5324688eff5a1a3b4da694c8cd696e5b034a1ee67ca61faa4f5331e2cef4a7bc`,
profile digest
`sha256:6d651b66c08b5e13b55dc8b30201ff28abf103932f27e2d5283c8dd69b391287`,
the same checker digest, and journal digest
`sha256:4b67d89b5c0f1e15daee1d2968617a0805bdfc2eea374ab4ab0872f020b3b22e`.

## Why it matters

Registration effects are part of the occurrence's projection authority, not a
second side effect after completion. Qualifying close and open together proves
rollback cannot expose a partially replaced delivery door and accepted-but-
unacknowledged projection cannot repeat either effect after reconstruction.
The prior token-only projection pair could not establish the public armed
registration view.

## Verification

- All 5 focused tests passed, including authored byte identity, data-only
  replay for both artifacts, and checker mutation sensitivity.
- All 77 prior joined creation/provider tests passed unchanged.
- All DST tests passed: 187; all project-coherence tests passed: 29.
- `scripts/check full` passed all 2,375 tests.
- `scripts/check release` passed all 2,375 tests in both orders, with 17
  expected serial qualification deselections.

## Review and follow-up

The change remains test-owned and adds no production API. State-affecting
operations cross the one World interpreter and public Engine/Worker/load/
snapshot doors. The checker consumes only detached transaction, History,
provider-custody, and public snapshot facts. Abrupt drop and graceful close
remain distinct. No debt item or decision record is needed.

CV19.DS2 remains Active. Runtime-policy `seal` remains a distinct transaction
cut; handler effect validation remains covered by focused Instance tests rather
than being duplicated in this recovery profile.
