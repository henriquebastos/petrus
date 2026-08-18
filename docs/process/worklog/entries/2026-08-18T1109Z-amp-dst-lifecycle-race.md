---
date: 2026-08-18T11:09:52Z
author: Amp
kind: milestone
related:
  - CV19.DS2
verification:
  - UV_FROZEN=1 uv run pytest -q tests/dst (67 passed)
  - six retained World replay routes (all pass with exact dispositions and journal digests)
  - lifecycle replay (quiescent; 22 operations; 36 journal entries; 13 checker evaluations)
  - scripts/check full (2248 passed)
  - scripts/check release (2248 passed in each order; 17 release-profile deselections in the additional order)
---

# Deterministic lifecycle reset and late-terminal race

## What changed

A third exact public-Engine profile under `tests/dst/` now authors a complete
lifecycle race through the same supported World interpreter. The scenario opens
scope generation 1, delivers identified scoped input, starts one Activity,
resets to generation 2 while that Activity is in flight, and abruptly drops the
process before the late terminal arrives. A fresh `Engine.load` reconstructs
the reset, and its first public `advance` reconciles the cancellation fence
without preparing or dispatching the cancelled Activity.

The first exact late result is quarantined once. Its exact duplicate is then
acknowledged with no additional History append, and the cancelled Activity
never appears as an ordinary terminal or projection. An independent detached
lifecycle-authority checker continuously compares active generation,
opens/resets/quarantines, terminal deliveries, and projection bounds with
authored external-world facts.

## Why it matters

CV19.DS2 now proves a lifecycle generation race rather than only Activity
terminal durability cuts. The proof still uses public Engine, lifecycle,
delivery, and Dispatch doors; it neither exports private runtime handles nor
adds a second execution semantics.

## Verification

The focused DST suite passed 67 tests. All six retained fixtures replayed
through `tests.dst.replay_world` with exact outcomes and dispositions. The new
24,275-byte fixture ended `quiescent` across 22 operations and 36 journal
entries, including 13 checker evaluations, with digest
`sha256:1719800ed00cfb705535b47b359d23988080b19a073f6247a995776ab7d9b194`.
The full gate and both release orders passed 2,248 tests; the additional order
reported the expected 17 profile deselections. Source lint, format, type, and
all 19 architecture-rule fixtures also passed.

## Follow-up

CV19.DS2 remains Active for broader delivery/Dispatch and lifecycle cuts, the
planned timer/retry story, transaction ambiguity, profile-retained-data bounds,
and wall-clock watchdog qualification.
