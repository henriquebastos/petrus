---
date: 2026-08-18T12:33:00Z
author: Amp
kind: milestone
related:
  - CV19.DS2
verification:
  - UV_FROZEN=1 uv run pytest -q tests/dst (82 passed)
  - eleven retained World replay routes (all pass with exact dispositions and journal digests)
  - delayed-terminal replay (converged; 17 operations; 27 journal entries; 9 checker evaluations)
  - scripts/check full (2,263 passed)
  - scripts/check release (2,263 passed in both orders; 17 expected alternate-order deselections)
---

# Deterministic delayed external terminal reconstruction

## What changed

An eighth exact public-Engine profile under `tests/dst/` now authors one
external Activity result for logical instant 5. The normalized scheduling
command enters the World queue, then an abrupt crash discards that volatile
entry while profile-owned modeled external truth remains. Fresh public
`Engine.load` reconstructs the pending Activity and re-proposes the same
external delivery to the one interpreter.

The fair phase advances directly from instant 0 to 5, delivers the result, and
records exactly one `ActivityCompleted`, one `FiringCompleted`, and one
projection. An independent checker bounds canonical terminal facts by authored
external delivery count and rejects a completion before the authored instant.

## Why it matters

This proves delayed provider response, volatile scheduler loss, external-world
reconstruction, deterministic logical-time delivery, and convergence without
real sleep or a second Petrus executor. It deliberately does not claim
LocalDispatch retry timing: that remains owned by the provider's SQLite clock
and its separately recorded compatibility boundary.

## Verification

The focused DST suite passed 82 tests, and all eleven retained fixtures
replayed through `tests.dst.replay_world` with exact outcomes and dispositions.
An independent fresh build was byte-identical to the retained 14,491-byte
fixture (SHA-256
`7eb8323e8c7324a76ccd1ba227f58f8546200b29a92606ee724d272a0e96a716`).
The route ended `converged` across 17 operations and 27 journal entries,
including 9 checker evaluations, with journal digest
`sha256:a89273aadcb2aeb48e60832d658e6ae37ef8a09c5dcb14298e16bdd2b398c007`.
Source lint, format, type, and architecture checks passed. The full gate and
both release orders passed 2,263 tests, with 17 intentional deselections in the
alternate release profile.

## Follow-up

CV19.DS2 remains Active for broader delivery/transaction cuts, an accepted
provider-time design for delayed LocalDispatch retry, profile-retained-data
bounds, and wall-clock watchdog qualification.
