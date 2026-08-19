---
code: CV19.DS4.TS1
level: Technical Story
status: Done
status_reason: Ordinary generated profiles remain in pytest and the scheduled four-profile cohort now derives exact seeds, replays every case, enforces explicit bounds, and retains payload-free semantic reach
updated: 2026-08-19
related:
  - index.md
  - cv19-ds4-campaign-and-production-boundary-qualification.md
  - cv19-ds3-ts3-fair-shrinking-and-semantic-coverage.md
---

# CV19.DS4.TS1 — Bounded campaign tiers

## Intent

Turn the existing generated state machines into an explicit, repeatable
engineering operation whose cost, selected profiles, exact discovery seeds,
semantic reach, and exclusions are visible.

## Scope

- Keep the ordinary generated examples in the normal pytest DST suite.
- Add one pytest-backed scheduled campaign command under `tests/dst` rather
  than creating another scheduler or a parallel scripts tree.
- Derive isolated profile seeds from an explicit campaign identity, increase
  examples and state-machine steps within fixed limits, and replay every
  generated expanded artifact through the existing World interpreter.
- Retain a strict-data report containing selected/deselected profiles, exact
  seeds, observed normalized semantic labels, elapsed time, artifact sizes,
  profile resource ceilings, and declared unmodeled boundaries.
- Fail visibly on an unknown tier/profile, missing scheduled campaign
  identity, subprocess timeout, nonzero pytest result, missing examples, or a
  report-size ceiling.

## Acceptance / Done Condition

1. `uv run pytest -q tests/dst` still runs the ordinary generated profiles as
   part of the self-contained DST suite.
2. A documented `python -m tests.dst.campaign` route runs a larger bounded
   cohort without credentials or Docker and records the exact profile seeds.
3. Every recorded case came through one existing World interpreter and replayed
   from fresh profile/checker objects before it enters the campaign report.
4. The report states actual semantic reach, selected and deselected profiles,
   explicit limits, and unmodeled boundaries without retaining scenario
   payloads.
5. Focused tests and the concrete campaign route pass before this Technical
   Story closes.

## Delivered evidence

- Ordinary broad/focused identified-delivery and cross-layer runtime state
  machines remain normal pytest tests. Their previous example and step counts
  are unchanged, and every generated expanded artifact still replays from
  fresh profile/checker/runtime objects before teardown succeeds.
- `python -m tests.dst.campaign` runs those same tests in serial child pytest
  processes. An explicit campaign identity derives a different exact seed for
  each profile. The scheduled tier increases the cohort from 76 to 304
  accepted-example targets and increases each state-machine step bound by two.
- Each successful replay contributes only normalized command/fault/crash/
  checker/disposition labels, profile identity/resource ceilings, operation
  count, artifact size/digest, and journal digest. Scenario payloads, command
  results, modeled external facts, and provider data do not enter the report.
- The report records exact runtime/repository identity, selected and deselected
  profiles, unmodeled boundaries, actual cases, elapsed time, and all enforced
  limits. Unknown/duplicate selections, missing cases, case-log overage,
  subprocess failure, and timeout are red rather than partial success.
- The 2026-W34 four-profile route passed with isolated seeds, 304 accepted
  targets, 452 recorded generated/shrink cases, 34.8 seconds elapsed, a largest
  artifact of 288,032 bytes, and an 8,039-byte report. The complete ordinary
  DST corpus passed 209 tests, the full repository gate passed 2,397 tests, and
  release qualification passed 2,397 tests in both orders.

No production runtime, supported `petrus.testing.dst/v4` API, artifact schema,
profile/checker identity, or scheduler behavior changed.

## Correctness sketch

- **Authority:** expanded World operations and their replay results remain the
  execution authority; the campaign report is a detached aggregate.
- **Safety:** campaign orchestration cannot mutate a scenario, bypass its
  checker, or turn a failed/missing profile run into a green report.
- **Liveness:** each selected pytest process has a wall-clock bound. A timeout
  is campaign failure, not deterministic liveness evidence.
- **Bounds:** profile count, examples, state-machine steps, subprocess time,
  report bytes, artifact bytes, and profile-owned state ceilings are explicit.
- **Nondeterminism:** an authored campaign identity deterministically derives
  one isolated seed per selected profile. Reports retain those exact seeds;
  Hypothesis's database is disabled.
- **Crash cuts:** generated crash/load operations remain profile commands in
  the expanded schedule. Killing a campaign subprocess is harness containment,
  not a simulated crash cut.
- **Independent judgment:** existing profile checkers run at World boundaries;
  fresh replay compares the complete normalized artifact before aggregation.

## Out of Scope

- Failure-bundle retention, redaction, minimization, and promotion workflow.
- PostgreSQL, Absurd Worker, ZeroMQ, or OS process-boundary qualification.
- CI-provider configuration or an unbounded random swarm.
