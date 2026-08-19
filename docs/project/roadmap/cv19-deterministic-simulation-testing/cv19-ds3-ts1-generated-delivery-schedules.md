---
code: CV19.DS3.TS1
level: Technical Story
status: Done
status_reason: Broad and focused identified-delivery state machines now drive only the supported World, check detached authority continuously, and replay every successful expanded schedule from fresh objects
updated: 2026-08-19
related:
  - index.md
  - cv19-ds3-stateful-generation-and-independent-checkers.md
  - ../../../process/deterministic-simulation-testing.md
  - ../../../../tests/dst/test_generated_delivery_world.py
---

# CV19.DS3.TS1 — Generated identified-delivery schedules

## Intent

Establish DS3's generation shape on one already-qualified public-Engine profile
without adding another executor, teaching a generator Petrus semantics, or
making a Hypothesis seed the replay contract.

## Scope

- Drive `DeliveryEngineProfile` only through the supported `World` and
  `Timeline` normalized interpreter.
- Add a broad state machine that draws source identity and payload dimensions
  independently.
- Add a focused state machine that makes exact redelivery, identity conflict,
  abrupt crash, and fresh load frequent rather than accidental.
- Maintain a small external authority model over authored identity/payload
  facts and compare it with detached canonical observations.
- Run `DeliveryAuthorityChecker` at the World's atomic boundaries.
- Finish every successful generated example explicitly and replay its expanded
  artifact through fresh profile, checker, and Engine objects.

## Acceptance / Done Condition

1. Broad and focused Hypothesis state machines submit every state-affecting
   operation through the one supported interpreter.
2. Applied delivery, exact idempotent redelivery, conflicting redelivery,
   abrupt crash, and fresh load are executable in the focused family.
3. The independent model and checker derive expected identity authority only
   from authored external facts and detached observations.
4. Every successful generated artifact replays exactly from fresh objects,
   including its checks, operations, ending disposition, and journal digest.
5. The slice introduces no production API, private runtime access, second
   scheduler, permanent generated-success fixture, or DS3-wide coverage claim.

## Correctness Sketch

- **Authoritative state:** canonical JSONL History owns accepted deliveries;
  profile-owned authored attempts are independent external-world facts.
- **Safety:** one canonical fact exists per accepted identity; exact redelivery
  is idempotent; changed content is refused; reload neither invents nor loses
  accepted authority.
- **Liveness:** the source-only profile legitimately ends in an explicit
  external wait; TS1 makes no fair-convergence claim.
- **Bounds:** generated examples, state-machine steps, World actions, reloads,
  queue length, logical time, polling, and artifact bytes are explicit.
- **Nondeterminism:** Hypothesis owns workload choice; the expanded World
  operations own permanent replay.
- **Crash cuts:** abrupt drop may follow any complete delivery attempt; fresh
  construction uses public `Engine.load` from retained History.
- **Independent judgment:** the model and `DeliveryAuthorityChecker` fold
  authored identities and detached canonical facts without calling delivery
  or topology decisions from production.

## Driver QA and Evidence Plan

- Run the broad and focused generated nodes directly, including Hypothesis
  statistics.
- Run the existing hand-authored identified-delivery scenario beside them.
- Run the complete `tests/dst` suite, `scripts/check full`, and
  `scripts/check release`.

## Delivered Evidence

- [`test_generated_delivery_world.py`](../../../../tests/dst/test_generated_delivery_world.py)
  contains both generator families beside the World/profile support they
  exercise. The broad family draws three identities and three integer boundary
  values independently. The focused family executes applied delivery, exact
  redelivery, conflicting redelivery, abrupt crash, and fresh load in every
  example before generating additional ordered combinations.
- The state-machine authority model tracks only authored identity/payload
  facts. Its invariant compares detached canonical deliveries and marking
  values, while `DeliveryAuthorityChecker` independently evaluates every World
  atomic boundary. Neither calls `Engine.deliver`, replays a Petri topology, or
  receives a live generation.
- Broad generation is bounded at 30 examples and eight generated steps;
  focused generation is bounded at 20 examples and six generated steps. Each
  example emits a strict expanded artifact, explicitly ends as
  `external_wait`, and replays operations, checker results, disposition, and
  journal digest through a fresh `DeliveryEngineProfile` and Engine.
- The generated nodes passed beside the hand-authored delivery story: 5 tests.
  The complete DST suite passed 194 tests and project coherence passed 29.
  `scripts/check full` passed all 2,382 tests; `scripts/check release` passed
  all 2,382 tests in both orders with 17 expected serial qualification
  deselections.
- The first full attempt exposed an unrelated xdist race in a Gondolin test's
  machine-global `/tmp/petrus-g-*` comparison. Its exact serial node passed,
  left no directory behind, and the subsequent complete full and release gates
  passed. TS1 changed no Gondolin code.

## Review

The generated programs remain self-contained under `tests/dst` and run under
ordinary pytest discovery. No script-only execution path, production API,
compatibility version, persistent generated-success fixture, private Engine
handle, decision record, or debt item was added. The fixed high-value prefix is
deliberately a focused family rather than a claim that broad generation has the
same reach. Composite dimensions, mutation shrinking, fair liveness, and
semantic coverage remain explicitly owned by TS2 and TS3.

## Out of Scope

- Timers, Worker retries, lifecycle fencing, storage faults, or fair liveness.
- Deliberate mutation and minimized failure promotion.
- A composite profile satisfying DS3's full cross-layer acceptance condition.
