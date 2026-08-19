---
date: 2026-08-19T05:07:54Z
author: Amp
kind: milestone
related:
  - CV19.DS4
  - CV19.DS4.TS1
verification:
  - uv run pytest -q tests/dst/test_campaign.py tests/dst/test_generated_delivery_world.py tests/dst/test_generated_runtime_world.py
  - uv run python -m tests.dst.campaign --tier scheduled --campaign-id 2026-W34 --report /tmp/petrus-dst-campaign-2026-W34.json
  - uv run pytest -q tests/dst --forbid-skips
  - uv run pytest -q tests/project
  - scripts/check quick
  - scripts/check full
  - scripts/check release
---

# Bounded deterministic simulation campaign tiers

## What changed

Completed CV19.DS4.TS1. The broad/focused identified-delivery and cross-layer
runtime state machines remain ordinary pytest tests under `tests/dst`; their
existing example/step counts and fresh-object replay obligations are unchanged.
Their settings now come from one test-owned campaign plan.

`python -m tests.dst.campaign` runs the same pytest nodes as a bounded serial
cohort. The scheduled tier takes an explicit campaign identity, derives one
isolated SHA-256-addressed Hypothesis seed per profile, disables the example
database, raises accepted-example targets from 76 to 304, and adds two bounded
state-machine steps per profile. Each state machine still submits only through
the existing World interpreter and replays its complete expanded artifact
before recording a case.

The operation aggregates only normalized semantic labels and identities:
commands, action dispositions, fault/cut names, crash cuts, checker triggers,
operation/disposition kinds, profile/checker-compatible resource ceilings,
artifact size/digest, and journal digest. It omits scenario payloads, command
results, modeled external facts, and provider data. The final report also names
the repository/runtime identity, exact seeds, selected/deselected profiles,
elapsed time, and explicit unmodeled real boundaries.

Limits are visible and enforced: one process at a time; 120 seconds per
scheduled profile; 510 seconds total for four profiles; 16 KiB per case
summary; at least the accepted-example target and at most ten times that many
recorded generated/shrink cases; 1 MiB per report; exact per-profile artifact
and retained-state budgets; and the 4 MiB format ceiling. Unknown or duplicate
profiles, timeout, pytest failure, missing cases, and case-log overage cannot
produce a green report.

## Why it matters

DST is now an executable engineering operation rather than only a collection
of property tests. A future Driver can run the normal corpus, rotate a larger
weekly/on-demand cohort, see what actually ran, and distinguish its semantic
reach from boundaries that still require PostgreSQL, process, Worker, or
transport evidence. This retains the Navigator's requested single
`tests/dst`/pytest structure and does not create another scheduler.

## Verification

- Six campaign-operation tests pass, including seed isolation, payload-free
  summaries, a real nested-pytest operation, invalid selection, timeout, and
  case-log overage.
- The complete scheduled 2026-W34 cohort passed all four profiles with exact
  seeds. It targeted 304 accepted examples, retained 452 generated/shrink case
  summaries, completed in 34.8 seconds, produced an 8,039-byte report, and had
  a largest exact artifact of 288,032 bytes. The observed command maximum RSS
  was about 105 MiB.
- The complete DST corpus passed 209 tests with skips forbidden. Project
  coherence passed 29 tests and static checks passed.
- `scripts/check full` passed 2,397 tests. `scripts/check release` passed 2,397
  tests in its parallel order and 2,397 tests in its additional fixed order;
  the latter reported the expected 17 explicit qualification deselections.

## Review and follow-up

No production code or supported DST compatibility surface changed. Centralizing
the four state-machine settings removed duplicated tier constants without
changing ordinary behavior. A scripts-owned campaign, a new executor, CI
provider configuration, and automatic failure promotion were considered and
deliberately excluded. There is no new technical debt or decision-record
impact.

DS4 next owns the redacted failed-artifact retention/minimization/promotion
workflow, followed by the complementary production-boundary qualification.
