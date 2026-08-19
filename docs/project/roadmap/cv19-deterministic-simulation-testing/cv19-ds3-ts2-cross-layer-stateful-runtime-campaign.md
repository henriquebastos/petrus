---
code: CV19.DS3.TS2
level: Technical Story
status: Done
status_reason: One public-Engine profile now spans the complete generated runtime vocabulary, continuously checks all eight applicable CV19 safety families, and replays every successful broad and focused v4 schedule from fresh objects
updated: 2026-08-19
related:
  - index.md
  - cv19-ds3-stateful-generation-and-independent-checkers.md
  - cv19-ds3-ts1-generated-delivery-schedules.md
  - cv19-ds3-ts3-fair-shrinking-and-semantic-coverage.md
  - ../../../process/deterministic-simulation-testing.md
  - ../../../../tests/dst/generated_runtime_world.py
  - ../../../../tests/dst/test_generated_runtime_world.py
---

# CV19.DS3.TS2 — Cross-layer stateful runtime campaign

## Intent

Exercise DS3's complete generated runtime vocabulary in one bounded run while
keeping production Petrus responsible for semantic consequences.

## Scope

- Compose one production-Engine scenario profile that admits generated source
  delivery, logical-time movement, Activity completion/failure, retry,
  lifecycle change, abrupt crash/load, and at least two qualified fault classes.
- Keep broad and focused command generation outside the profile and submit all
  operations through the supported World interpreter.
- Add the smallest independent History, occurrence, Activity, lifecycle, and
  transaction-authority folds needed for the eight CV19 safety properties.
- Preserve the DS2 ownership and compatibility boundary: opaque generations,
  detached observations, public Engine doors, and strict replay.

## Acceptance / Done Condition

1. One bounded generated run can cover deliveries, timers, Activities,
   retries, lifecycle changes, crash/load, and two fault classes.
2. Every applicable CV19 safety property has an executable independent checker;
   any inapplicable or blocked property names its owner and revisit trigger.
3. Broad and focused schedules use one interpreter and produce strict expanded
   artifacts which replay from fresh objects.
4. No checker calls the production decision it claims to judge or mirrors the
   Petri topology as expected truth.

## Correctness Sketch

- **Authoritative state:** JSONL History owns semantic truth and LocalDispatch
  owns Activity custody. Profile-owned delivery/dispatch/Worker/projection
  journals are modeled external facts, not a second semantic log.
- **Safety:** the detached checker compares live marking and watermark with
  canonical replay, independently folds occurrence/in-flight/lifecycle
  structure, and checks stable invocation, frozen-terminal execution,
  delivery identity, projection authority, retry, timer, and resource bounds.
- **Liveness:** TS2 ends only after deterministic scheduled work reaches a
  named external wait. It makes no fair-convergence claim; TS3 owns that
  separate judgment.
- **Bounds:** each run pins World actions, queue, logical time, timer advances,
  reloads, predicate polls, artifact bytes, History records/bytes, modeled
  external facts, and live Worker claims in a v4 artifact.
- **Nondeterminism:** Hypothesis owns generated values and schedule choices;
  logical time, stable identities, queue order, fault occurrences, and every
  accepted operation are controlled and expanded by the one World.
- **Crash cuts:** abrupt drop follows refused Dispatch custody, refused
  semantic projection, accepted Activity request, or a generated quiescent
  boundary. Fresh public `Engine.load` reconstructs from retained stores.
- **Independent judgment:** the checker consumes only strict detached
  observations and small authored-authority folds. It never receives an
  Engine/Coordinator/Instance handle or computes Petri enabledness.

## Delivered Evidence

- [`generated_runtime_world.py`](../../../../tests/dst/generated_runtime_world.py)
  composes one opaque generation around a production public `Engine`, JSONL
  History, real `LocalDispatch`/Worker doors, an injected World clock, and a
  strict closed vocabulary for scope, identified delivery, drive, Worker
  claim/fail/complete, and two one-shot faults.
- The focused family executes, in every generated example, identified delivery
  and exact acknowledgement, refused Dispatch custody after durable
  `ActivityRequested`, abrupt drop/load and byte-stable redispatch, one failed
  Worker attempt and retry, frozen successful terminal, refused semantic
  projection, projection-only load recovery, reset fencing, late-terminal
  quarantine, and logical-time timer maturation. Preparation occurs once and
  provider execution does not recur after the frozen terminal.
- The broad family independently varies values, both fault classes, retry,
  crash after accepted request, projection recovery, lifecycle reset, exact
  redelivery, and quiescent crash, up to two complete external Activities. It
  preserves fewer global ordering constraints than the focused spine while
  every operation still crosses the same interpreter.
- `GeneratedRuntimeAuthorityChecker` runs after each accepted atomic action and
  fresh load. Its executable property families map to CV19 as follows:

  | CV19 property | TS2 check |
  | --- | --- |
  | S1 replay agreement | live marking/watermark equals canonical replay; an independent begun/terminal/reset fold equals detached live in-flight phases and scope generation; selected occurrences pair with begun facts |
  | S2 History validity | begun ids are dense; every correlated record belongs to a begun occurrence; firing terminals are unique and disjoint; strict JSONL load and replay validate record decoding and monotone watermark |
  | S3 stable invocation | one request equals every Dispatch/Worker projection for its occurrence and `prepare` count equals request count |
  | S4 terminal before projection | completed provider occurrences authorize terminals; projection acceptance exactly matches work firing completion; stateful frozen execution counts cannot increase after `ActivityCompleted` |
  | S5 delivery identity | authored attempts equal canonical delivery facts and exact redelivery must report `idempotent` |
  | S6 lifecycle isolation | authored, replayed, and live scope generations agree; cancelled late completions must be quarantined and marked cancelled |
  | S7 commit authority | refused projection has no work firing completion; refused Dispatch custody maps only to the already-durable stable request before reload |
  | S8 profile bounds | World limits plus v4 History-byte/record, external-fact, and claimed-Worker gauges fail closed; checker-local semantic counts remain bounded |

- A focused mutation test alters detached marking, in-flight, occurrence,
  invocation, redelivery acknowledgement, lifecycle, projection, timer, and
  post-freeze execution facts one family at a time and proves the checker
  refuses each divergence.
- The hand-authored scenario and both generated families emit current v4
  expanded artifacts and replay operations, checks, resource samples, ending
  disposition, and journal digest through fresh profile, checker, History,
  Dispatch, and Engine objects. No successful generated fixture is retained.
- Focused generation is bounded at 10 examples × 4 generated post-spine steps;
  broad generation is bounded at 16 examples × 5 generated steps. The four
  new nodes pass; the complete DST suite passes 198 tests and project
  coherence passes 29. Repository-wide full and release evidence is retained
  in the matching worklog entry.

## Review

The slice adds only test-owned profile/generation code and durable project
memory. It adds no production API, root export, private Coordinator access,
new compatibility format, decision record, debt item, or permanent generated
success fixture. Graceful close and abrupt drop remain distinct. The checker
uses canonical replay only as a cross-representation authority; it does not
recreate topology or call the production decision it judges.

Real Absurd/PostgreSQL atomicity remains the stronger separately qualified DS2
evidence and DS4 campaign boundary, not a claim made by this JSONL/LocalDispatch
profile. Fair convergence, shrinking qualification, semantic coverage, and
durable failed-schedule promotion remain TS3-owned.

## Out of Scope

- Fair-phase convergence qualification, shrinking proof, or CI campaign tiers.
- Application-specific provider authority or GitHub/readiness semantics.
