---
code: CV19.DS3.TS3
level: Technical Story
status: Done
status_reason: Fair liveness is classified separately from safety, Hypothesis minimizes and exactly replays a test-only livelock failure, the unmutated schedule is retained as a green v4 fixture, and semantic coverage names broad-only and excluded dimensions
updated: 2026-08-19
related:
  - index.md
  - cv19-ds3-stateful-generation-and-independent-checkers.md
  - cv19-ds3-ts2-cross-layer-stateful-runtime-campaign.md
---

# CV19.DS3.TS3 — Fair shrinking and semantic coverage

## Intent

Turn generated exploration into discriminating liveness evidence and durable,
minimized regressions rather than an opaque count of passing examples.

## Scope

- Enter an explicit fair phase after generated safety faults stop and classify
  convergence, legitimate external wait, exhaustion, quarantine, and liveness
  failure independently from safety.
- Use a selected test-only mutation to prove Hypothesis materially shrinks a
  failing generated schedule and that the minimized expanded failure artifact
  replays exactly.
- Remove the mutation and retain only legitimate minimized regression evidence
  and discovery metadata.
- Report semantic coverage across events, faults, boundaries, lifecycle and
  terminal states, crash cuts, recovery paths, checker activations, and
  unreachable dimensions.
- Demonstrate one combination reached by the broad family and omitted by the
  initial targeted family.

## Acceptance / Done Condition

1. Fair convergence can fail independently of safety and its evidence
   distinguishes livelock, external prerequisite, exhaustion, and inadequate
   fairness declaration.
2. Hypothesis shrinks a selected mutation to a materially smaller replayable
   scenario.
3. The minimized expanded artifact, not a seed alone, is the durable replay
   authority.
4. Semantic coverage names reached, unreachable, and intentionally ungenerated
   dimensions, including one broad-only combination.
5. Fixed regressions, a bounded local swarm, `scripts/check full`, and
   `scripts/check release` pass before DS3 closes.

## Delivered evidence

- A normal public-`Engine` schedule enters the fair phase only after authored
  Activity completion has disclosed its follow-up work. World then drains the
  exact current-instant work, advances logical time to the retained deadline,
  matures and fires the timer, and ends quiescent. Its current-v4 expanded
  schedule is retained as
  `tests/dst/fixtures/generated-runtime-minimized-fair-regression-v4.json` and
  replays from fresh Engine, JSONL History, LocalDispatch, and profile objects.
  The same operations run with the independent checker after every atomic
  boundary; the compact retained fixture omits duplicated checker snapshots,
  not state-affecting operations.
- A pre-fair empty queue is classified as a legitimate external prerequisite.
  The same state after `begin_fair` is an inadequate fairness declaration:
  there is no eligible profile action and World refuses to relabel it an
  authored external wait. A separate nine-action fair budget exhausts before
  accepting any fair step and replays that exact failed attempt.
- A distinct test-only profile identity adds one mutation: an otherwise
  quiescent `engine.drive` reschedules itself at the same instant. All safety
  checks remain green while three final steps retain the same History frontier
  and instant, so action exhaustion is classified as livelock rather than a
  safety failure. Its v4 failed-attempt artifact replays exactly from fresh
  mutated objects.
- Hypothesis reduces the accepted mutation reproduction from a 15-operation
  fair prefix containing retry, observation, crash/load, and observation to
  the eight-operation required prefix with none of those optional actions.
  The mutation is absent from the promoted profile and fixture. The expanded
  artifact, not the seed, is replay authority; seed `19003`, shrink lineage,
  property, and before/after sizes are retained in the TS3 worklog.
- `generated-runtime-semantic-coverage-v1.json` is computed from normalized
  operations and detached checker results. It reports events, fault cuts,
  negative/zero/positive values, Activity epochs, lifecycle and terminal
  states, crash/load recoveries, and checker activations. It also records three
  structurally unreachable and four intentionally ungenerated dimensions.
  The broad schedule uniquely reaches retry followed by scope reset before the
  same provider terminal, a combination absent from the focused spine.

No production runtime, supported DST API, artifact format, Coordinator door,
or real-backend claim changed. DS4 subsequently delivered the separately owned
PostgreSQL/Absurd qualification and campaign cadence.

## Out of Scope

- DS4 PR/nightly campaign cadence and real-boundary qualification.
- Exhaustive state-space enumeration or provider-incident minimization.
