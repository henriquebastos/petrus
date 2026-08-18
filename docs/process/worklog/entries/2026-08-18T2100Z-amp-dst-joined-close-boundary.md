---
date: 2026-08-18T21:00:00Z
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

# Joined terminal scope-close transaction replay

## What changed

Added paired real Absurd/PostgreSQL profiles around public
`Engine.close_scope`. The refusal profile rejects the transaction containing
`ScopeClosed` before PostgreSQL acceptance. Detached History retains the active
scope and running task; after abrupt generation drop, fresh public load accepts
the original Worker's completion and projects it exactly once.

The acknowledgement-loss profile commits `ScopeClosed` and then raises before
the caller receives acknowledgement. Fresh public load reconstructs terminal
scope authority, installs exactly one cancellation tombstone against the
original Absurd task, and rejects stale Worker completion without a semantic
terminal or projection.

The refusal artifact has 20 operations, 33 journal entries including 13
checker evaluations, disposition `quiescent`, artifact SHA-256
`b5f6d250e797dd2da53974d9c65b5e1a10d3957f805a63e4b9d3daa82164c3ee`,
profile digest
`sha256:f12a94e502eab02681fed0119ba9bf90033999e572fee39308da276d5b04c918`,
checker digest
`sha256:35a7a7c156d63c4dad8f0e37cae627b1c98f0674a183dc485cba611b15c7d0fc`,
and journal digest
`sha256:10afccd8c4a082435cd09e1f3ec588d53e9477b9110ea0fa1643f5bbe9f1ff62`.

The acknowledgement-loss artifact has 18 operations, 30 journal entries
including 12 checker evaluations, disposition `quiescent`, artifact SHA-256
`ff15a6c7e961e8063b12fbaae4c94b8deb9533432e3913cf85bc5a3367fa4a89`,
profile digest
`sha256:84a789ddfbb728da68213ed52e92ebf888356848f139aed2a6b175128efe2d5c`,
checker digest
`sha256:292a46ed8ed7feba42559994172a549cd902127e16dee8b32e3aec4cce6e62f3`,
and journal digest
`sha256:abff4fd6f1c22490653ed0ed8c798854924272257b4bbca49afd228416d85b2a`.

## Why it matters

Terminal close and reset share cancellation mechanics but not lifecycle
meaning: close ends the named scope and reset opens a successor generation.
This pair qualifies that terminal canonical boundary directly rather than
inferring it from the existing reset evidence.

## Verification

- The joined profile passed all 47 tests; all DST tests passed: 157.
- DST plus project coherence passed all 186 tests.
- `scripts/check full` passed all 2,345 tests.
- `scripts/check release` passed all 2,345 tests in both orders, with 17
  expected serial qualification deselections.

## Review and follow-up

The change remains test-owned. It adds no production API and imports no private
runtime resource. Fault injection wraps the provider transaction while every
state-affecting scenario command still crosses the one World interpreter and
public Engine/Worker doors. Independent checks use detached PostgreSQL History,
transaction fate, and Absurd custody. Existing artifacts and version identities
are unchanged. No debt item or decision record is needed.

CV19.DS2 remains Active. This qualifies terminal scope close for the public
Absurd/PostgreSQL composition only; the broader provider/fault matrix remains.
