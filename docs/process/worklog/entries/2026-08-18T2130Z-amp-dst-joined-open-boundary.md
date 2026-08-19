---
date: 2026-08-18T21:30:00Z
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

# Joined lifecycle-open transaction replay

## What changed

Added paired real Absurd/PostgreSQL profiles around public
`Engine.open_scope`. The refusal profile rejects `ScopeOpened` before
PostgreSQL acceptance. Fresh public load observes no active scope, and the same
normalized command then opens `draft:1` exactly once.

The acknowledgement-loss profile commits `ScopeOpened` and raises before the
exact scope handle returns. Fresh public load reconstructs `draft:1` from
canonical History without another open or generation 2. A poisoned Engine's
live scope view is reported as unavailable; the checker relies on detached
PostgreSQL authority until fresh load supplies a legal public observation.

The refusal artifact has 9 operations, 15 journal entries including 6 checker
evaluations, disposition `external_wait`, artifact SHA-256
`515023a8cbdb6bc378b203d118536c74eac65359bc8c28f136bdead182913ec4`,
profile digest
`sha256:c40c154addbce6386b9843ec636a5ba85778ed365d02878d9655733f9ef3a9d3`,
checker digest
`sha256:94b5446f3c8b425241924e1198de76e6ddff576d8e76384af35fb10dc46e44b5`,
and journal digest
`sha256:9dac2f26898de634f5a8ffc1c38bff00651773c5e7c18f55b7bdc97e561f0a11`.

The acknowledgement-loss artifact has 7 operations, 12 journal entries
including 5 checker evaluations, disposition `external_wait`, artifact
SHA-256
`db4f216651754d4bb02d9373be13d698326b03d672dbb16346afba33fb60d982`,
profile digest
`sha256:60fab187f067600fedf035af470f7a52f593e42b5096c3d37d76f3bfe91b2980`,
the same checker digest, and journal digest
`sha256:0343ef238810e4c74cbf31d2c424f200e0f73b8dcf5f2895bf0ed1eb6d3453cf`.

## Why it matters

Scope creation is the canonical authority that assigns lifecycle generation
numbers. Direct qualification proves rollback cannot consume a generation and
accepted-but-unacknowledged creation cannot be repeated as generation 2.

## Verification

- The joined profile passed all 52 tests; all DST tests passed: 162.
- DST plus project coherence passed all 191 tests.
- `scripts/check full` passed all 2,350 tests.
- `scripts/check release` passed all 2,350 tests in both orders, with 17
  expected serial qualification deselections.

## Review and follow-up

The change is test-owned and adds no production API. Every operation crosses
the one World interpreter and public Engine/provider doors. The checker derives
authority from detached PostgreSQL transaction and History facts plus a public
active-scope view after fresh load. Its mutation test rejects a phantom scope
after rollback and acknowledgement loss without accepted authority. Existing
artifact identities and retained fixtures remain unchanged. No debt item or
decision record is needed.

CV19.DS2 remains Active for the broader provider/fault matrix.
