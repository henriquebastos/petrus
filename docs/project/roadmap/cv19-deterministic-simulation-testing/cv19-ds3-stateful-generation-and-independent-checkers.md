---
code: CV19.DS3
level: Delivery Story
status: Active
status_reason: CV19.DS2's supported interpreter, strict failure artifacts, process containment, and declared initial cut matrix are Done; DS3 now owns generated cross-layer schedules, broad independent models/checkers, shrinking, and falsification evidence
updated: 2026-08-19
related:
  - index.md
  - cv19-ds2-deterministic-event-and-fault-harness.md
---

# CV19.DS3 — Stateful generation and independent checkers

## Intent

Explore meaningful Petrus state space automatically without allowing a
sophisticated generator or a mirrored fake to define correctness by accident.

## Scope

- Build a Hypothesis state-machine layer over the DS2 scenario vocabulary.
  Commands choose only currently valid or intentionally invalid external
  actions; Petrus production logic decides their semantic consequences.
- Maintain two generator families:
  - broad, minimally structured generation that preserves dimensions a
    targeted profile might accidentally project away; and
  - focused profiles that increase the frequency of costly races, boundary
    values, failure combinations, and long recovery paths.
- Add independent checkers for the CV19 safety properties after every accepted
  event. Prefer small obvious folds and cross-representations over helpers that
  call the same production decision being checked.
- Add the smallest practical reference models for pure subsets such as queue
  occurrence identity, History/replay state, retry eligibility, and lifecycle
  disposition. Explicitly document properties that have no independent model.
- Enter a declared fair phase after generated safety faults and check bounded
  convergence separately from safety.
- Shrink failing command/event traces, preserve the minimized expanded
  scenario as a normal regression, and retain the original discovery metadata
  without making the seed the only reproduction key.
- Report semantic coverage: event/fault kinds, boundary values, lifecycle and
  terminal states, crash cuts, recovery paths, checker activations, and
  unreachable or ungenerated dimensions.

## Acceptance / Done condition

1. Stateful generation covers deliveries, timers, Activities, retries,
   lifecycle changes, crash/reload, and at least two fault classes in one run.
2. Every CV19 safety property has an executable checker or an explicit blocked
   reason with an owner and revisit trigger.
3. Fair-phase convergence can fail independently of safety and retains enough
   evidence to distinguish livelock, blocked external prerequisite, exhaustion,
   and an inadequate fairness declaration.
4. Hypothesis reduces a deliberately introduced defect or selected mutation to
   a materially smaller replayable scenario.
5. A simple broad generator reaches at least one semantic combination omitted
   by the initial targeted profile, demonstrating blind-spot resistance.
6. No checker derives its expected result by calling the production operation
   it claims to verify.

## Driver QA and evidence plan

- Use a selected mutation or temporary test-only defect to prove each major
  checker can fail. Remove the defect and retain only legitimate regression
  scenarios.
- Review generated scenario distributions and semantic coverage, not only line
  coverage and run counts.
- Run fixed reproduction fixtures, a bounded local swarm, focused production
  suites, `scripts/check full`, and `scripts/check release`.

## Out of scope

- Exhaustive state-space enumeration or formal proof.
- Treating a high seed count as evidence without semantic reach.
- Models of application-specific provider authority or business workflows.
- Automatic minimization of real external-provider incidents.
