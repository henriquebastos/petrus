---
date: 2026-08-19T04:32:54Z
author: Amp
kind: milestone
related:
  - CV19.DS3
  - CV19.DS3.TS3
  - CV19.DS4
verification:
  - uv run pytest -q tests/dst/test_generated_runtime_qualification.py --hypothesis-show-statistics
  - uv run python -m tests.dst.replay_world tests/dst/fixtures/generated-runtime-minimized-fair-regression-v4.json
  - uv run pytest -q tests/dst
  - uv run pytest -q tests/project
  - scripts/check quick
  - scripts/check full
  - scripts/check release
---

# Fair shrinking and semantic coverage

## What changed

Completed CV19.DS3.TS3 and closed DS3. The existing cross-layer generated
runtime profile now has a separate fair-liveness qualification. One normal
schedule discloses all retained internal work before `begin_fair`; the World
drains current work, advances to logical instant 5, records timer maturation,
fires the delayed transition, and reaches quiescence. Pre-fair external wait,
an inadequate fair declaration with no eligible action, action-budget
exhaustion before a fair step, late-terminal quarantine, and safety-preserving
livelock are asserted as distinct evidence rather than one generic timeout.

A separate test-only profile identity mutates only follow-up scheduling: after
the real Engine is otherwise quiescent, `engine.drive` schedules itself again
at the same instant. The independent safety checker stays green, while the
last three steps retain the same History frontier and instant until World
records exact action-budget exhaustion. The current-v4 failed-attempt artifact
replays from fresh mutated Engine, History, Dispatch, profile, and checker
objects.

Hypothesis removed retry, an observation, crash/load, and a second observation
from the selected reproduction. The failure-inducing fair prefix fell from 15
expanded operations to 8; canonical artifact size fell from 130,250 to 128,857
bytes even though both artifacts retain the same 28-action exhaustion tail.
The mutation is not in the normal profile or retained regression. The
unmutated minimized schedule is preserved as
`generated-runtime-minimized-fair-regression-v4.json`, including expanded
operations and seed/draw provenance, and replays through the ordinary manual
`tests.dst.replay_world` route. The checked run executes the identical
state-affecting operations with the independent checker after every boundary;
the compact fixture omits only duplicated checker snapshots.

`generated-runtime-semantic-coverage-v1.json` records normalized reach across
event and fault kinds, negative/zero/positive values, Worker epochs, lifecycle
and terminal states, crash cuts, recoveries, and checker activations. It names
three structurally unreachable and four intentionally ungenerated dimensions.
A deterministic broad route reaches retry followed by reset before the same
provider terminal, which the focused two-Activity spine omits.

## Why it matters

Generated safety evidence can now be distinguished from a valid liveness
claim, and a failure can be minimized without changing execution semantics or
making its seed authoritative. Broad generation has executable blind-spot
evidence instead of only a design rationale, while coverage limits are retained
next to the reached dimensions.

The result preserves the cross-project boundary: Petrus owns scheduling,
replay, generic runtime safety, and fair-phase mechanics; application profiles
own domain eligibility and external prerequisites. No production runtime,
Coordinator access, supported DST API, artifact version, or public simulation
contract changed.

## Verification

- The five focused TS3 tests passed, including the derandomized Hypothesis find,
  exact failure replay, promoted green fixture, direct manual replay, and
  semantic report comparison.
- Direct replay returned `outcome=pass`, `disposition=quiescent`, 12 operations,
  27 journal entries, and the retained journal digest.
- The complete DST suite passed 203 tests; project coherence passed 29.
- `scripts/check quick` passed lint, formatting, and static checks.
- `scripts/check full` passed all 2,391 tests.
- `scripts/check release` passed all 2,391 tests in both suite orders; the
  second order reported the expected serial-qualification deselections.

## Review and follow-up

No refactor or shared kernel change was needed: v4 already retains the failed
attempt and exact failure detail. The test-only mutation has an explicit profile
digest and cannot enter a normal artifact accidentally. The semantic reporter
reads normalized operations and detached checker outputs rather than production
enabledness.

No debt item or decision record is needed. DS4 is now active for bounded
ordinary/scheduled campaign operations and complementary PostgreSQL, Absurd,
process-kill, and transport qualification. This slice makes none of those
claims.
