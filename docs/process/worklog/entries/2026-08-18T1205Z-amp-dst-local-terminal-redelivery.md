---
date: 2026-08-18T12:05:00Z
author: Amp
kind: milestone
related:
  - CV19.DS2
verification:
  - UV_FROZEN=1 uv run pytest -q tests/dst (76 passed)
  - nine retained World replay routes (all pass with exact dispositions and journal digests)
  - local-terminal replay (converged; 15 operations; 26 journal entries; 10 checker evaluations)
  - scripts/check full (2,257 passed)
  - scripts/check release (2,257 passed in both orders; 17 expected alternate-order deselections)
---

# Deterministic LocalDispatch terminal recollection after process loss

## What changed

A sixth exact public-Engine profile under `tests/dst/` now composes the real
SQLite LocalDispatch and Worker doors into the supported World interpreter. One
Activity is prepared, published, claimed at epoch 1, and successfully reported
to LocalDispatch. The exact duplicate report is acknowledged and a conflicting
report is refused while canonical History still ends at `ActivityRequested`.

The scenario abruptly drops the Engine, LocalDispatch session, and Worker at
that pre-collection cut. A fresh public `Engine.load` republishes the recorded
invocation without another `prepare`; the replacement Worker collects the
durable first result and Engine records exactly one `ActivityCompleted`, one
`FiringCompleted`, and one business projection. An independent checker derives
authority from the authored accepted-result ledger rather than Engine topology.

## Why it matters

This proves the complementary side of LocalDispatch terminal custody: a worker
can finish durably before Engine sees the result, process loss does not erase or
replace that authority, duplicate and conflicting reports retain production
semantics, and restart converges without re-preparing the logical Activity. The
test uses public production doors and contains no private runtime access,
provider-clock substitution, direct SQLite mutation, or real sleep.

## Verification

The focused DST suite passed 76 tests, and all nine retained fixtures replayed
through `tests.dst.replay_world` with exact outcomes and dispositions. An
independent fresh build was byte-identical to the retained 22,627-byte fixture
(SHA-256 `2ca33516098534c425fda5c4ed2eb5b18f1efe361a60c8d0ae785b803c177506`).
The route ended `converged` across 15 operations and 26 journal entries,
including 10 checker evaluations, with journal digest
`sha256:ff332ce259e54320354ba2006e59053d4c5fb83488482de32081b8a5503ceab9`.
Source lint, format, type, and architecture checks passed. The complete full
gate and both release orders passed 2,257 tests, with 17 intentional
deselections in the alternate release profile.

## Follow-up

CV19.DS2 remains Active for delayed retry/provider time, broader delivery and
transaction cuts, profile-retained-data bounds, and wall-clock watchdog
qualification.
