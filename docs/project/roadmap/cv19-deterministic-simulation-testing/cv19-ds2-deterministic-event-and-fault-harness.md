---
code: CV19.DS2
level: Delivery Story
status: Active
status_reason: The supported petrus.testing.dst compatibility surface is accepted; the smallest generic World and public-Engine profile vertical slice is in implementation
updated: 2026-08-17
related:
  - index.md
  - cv19-ds1-correctness-and-simulation-contract.md
  - ../../decisions/records/2026-08-17T2249Z-ship-a-supported-cross-project-dst-test-kit.md
---

# CV19.DS2 — Deterministic event and fault harness

## Intent

Let authors write complex scenarios as executable pytest debugger scripts over
a deterministic World and Timeline while production Petrus semantic and
recovery logic runs under one bounded scheduler. Every authored run expands to
the strict replay data needed to reconstruct a crashed process and reproduce a
failure without executing the original Python scenario.

## Scope

- Subject to the linked compatibility decision, add a pytest-independent
  defining module under `petrus.testing.dst`, with no Petrus-root re-exports.
  It is an outer test host over registered scenario profiles, not another
  Petrus semantic runtime.
- Add a generic `World` as the composition root for deterministic logical
  time, identities, total event ordering, bounded scheduling, fault
  activation, diagnostics, checker cadence, and strict journal production.
  A profile owns each opaque runtime generation; the World does not assume
  that a generation contains one Engine or any other particular runtime graph.
- Add an imperative `Timeline` authoring facade for delivery, time, Activity
  outcomes, lifecycle, faults, crash/restart, inspection, and bounded
  debugger-like `run_until` checkpoints. Scenarios remain ordinary pytest code
  with helpers, control flow, local values, and assertions.
- Require every operation that can affect simulated execution to cross the
  Timeline and lower to the closed event/fault vocabulary. Arbitrary Python
  callbacks and assertions may guide an authored test, but are never
  serialized; the journal records the expanded events and named observations
  needed for replay.
- Introduce a test-owned deterministic event queue ordered by logical instant
  and explicit stable tie-breaker. The harness advances directly to the next
  event; no simulated path sleeps on wall time.
- Give the harness explicit seeded authorities for workload choices, fault
  choices, generated identifiers, and event ordering. Keep these streams
  separable enough that adding observability does not silently alter every
  choice.
- Add a Petrus-owned profile which drives production behavior only through
  public Engine doors. It does not export or retain a private Coordinator,
  mutable Instance, History, or Dispatch handle for application consumers.
  That profile covers:
  - identified source deliveries and redelivery;
  - timer observation and maturation;
  - candidate selection and firing;
  - Activity dispatch, delayed/duplicate/reordered terminal delivery, and
    classified failure;
  - retry eligibility and exhaustion;
  - lifecycle close/reset and late terminals; and
  - process crash, volatile-state loss, load, reconcile, and resumed drive.
- Add bounded faulting adapters at Petrus-owned contracts. Initial cuts cover
  append/commit refusal, crash before and after accepted durable facts,
  Dispatch loss/redelivery, delayed completion, ambiguous terminal delivery,
  and reconstruction. Each cut states whether the durable side accepted the
  operation; “maybe” is represented only where the contract genuinely permits
  ambiguity.
- Preserve strict ownership: the harness selects events and faults but does not
  reproduce Instance, Coordinator, projection, retry, or lifecycle decisions.
- Serialize every expanded authored or generated run and replay it without
  consulting the original Python scenario or PRNG.

## Cross-project compatibility contract

Petrus CV19 and Hamsterdan CV18 use one architecture at different abstraction
layers. The following is their joint design; it does not by itself approve the
new supported package surface.

| Owner | Responsibility |
| --- | --- |
| Petrus DST kernel | Clock, stable ids, total queue order, normalized interpreter, bounds, named cuts, fair-phase control, generation revocation, checker cadence, journal, artifacts, replay, and dispositions. |
| Petrus Engine profile | The vertical Petrus implementation through public Engine create/load/advance/deliver/scope/records/snapshot/close doors only. |
| Application profile | Complete opaque host-generation composition, simulated provider truth and effects, boundary-faithful adapters, application command validation, detached observations, external-world reconstruction, and abrupt-drop implementation. |
| Application Timeline | Domain verbs and named debugger-like checkpoints which lower to the same normalized interpreter. |
| Application oracle/checkers | Expected authority, effects, and readiness derived independently from authored external facts rather than Petrus topology or host folds. |
| DS3 generator/shrinker | Production and minimization of the same normalized commands and fair schedules, never a second executor. |

There is exactly one executor. Hand-authored Timeline calls, generated
schedules, and artifact replay all submit normalized commands to that
interpreter. Imperative Python is an authoring frontend only. Python callbacks
and predicates do not enter artifacts; the commands executed while reaching a
named checkpoint, scheduler choices, observations, checker outcomes, and final
disposition do.

### Profile and scheduling boundary

A registered profile has an exact identity, profile version, and implementation
digest. It owns an opaque generation and provides strict operations equivalent
to `validate`, `create`, `load`, `apply`, `observe`, abrupt `drop`, and graceful
`close`. The exact Python spellings remain an implementation detail until the
package decision is accepted.

- `create` and `load` return the opaque generation plus detached strict
  proposals for any initially eligible work. They do not secretly execute or
  enqueue that work.
- `ScenarioContext` may expose deterministic clock reads, stable id allocation,
  active fault evaluation, and instrumentation. It cannot schedule work,
  recursively enter the interpreter, or expose private runtime objects.
- `apply` performs one profile-defined atomic operation and returns detached
  strict values plus zero or more `ScheduledCommand` proposals. The World
  validates every proposal, assigns sequence and tie order, checks bounds,
  journals it, and alone decides when it executes.
- Application-defined command names, payloads, observations, and eligible
  actions are validated by the profile. The kernel never learns provider or
  readiness semantics.
- Observations and apply results contain detached strict data only. They cannot
  retain a generation or another mutable host object.

Checkers run after every accepted atomic interpreter action or event and after
every successful fresh load, never in the middle of a profile operation. They
receive detached observations and modeled world facts rather than a live
generation. Checker identity, version, and digest form an explicit manifest in
the artifact.

### Runtime generations and lifecycle

Graceful shutdown and simulated process crash are different operations:

- `close` is graceful final cleanup and may perform the settlement promised by
  the production host contract;
- `drop` is best-effort disposal of volatile resources with **no semantic
  settlement**; and
- the World revokes the current generation before invoking `drop`, rejects
  stale-generation use, and reconstructs only through the registered `load`
  factory from retained configuration, durable stores, and modeled external
  truth.

The generic contract prescribes these observable semantics, not whether an
application implements abrupt loss through a killable process or a narrow
application-owned resource-drop seam.

### Fairness and replay

Entering a fair phase is an explicit journaled operation. The World may not
indefinitely withhold an eligible delivery, Activity, or timer action after
that point, but it can schedule only actions the profile reports eligible.
Fairness cannot invent a provider response or human decision.

The expanded schedule is authoritative; a seed is provenance. Test-kit API
compatibility, artifact schema version, profile identity/digest, and checker
manifest/digests are separate pins and fail closed by default. DS1's
`petrus-dst-scenario` version 1 and `engine-coordinator-v1` proof remain
unchanged. The generic kernel uses a new explicit artifact/profile version or
format rather than silently widening that fixture contract.

## Delivery sequence

1. Record Navigator disposition of the linked compatibility decision before
   promising a shipped test-kit surface.
2. Implement the smallest Petrus vertical slice: authored Timeline command →
   normalized interpreter; deterministic named `run_until`; one named cut;
   generation revoke and abrupt drop; fresh public-Engine load; stale-use
   refusal; checker cadence; strict expanded artifact; and replay through the
   identical interpreter with the same normalized outcome and disposition.
3. Obtain Petrus acceptance of that supported seam before Hamsterdan updates
   its normal Petrus Git pin. Hamsterdan must not consume Petrus `tests/dst` or
   local-only code.
4. Hamsterdan then implements its opaque HostService profile, independent
   readiness oracle, and one real-host vertical scenario. Its current graceful
   `HostService.close()` is not an abrupt crash door; that application-owned
   DS2 seam must be added or isolated in a killable process.
5. DS3 generators and shrinkers emit the same normalized commands after the
   vertical profiles prove the interpreter and replay path.

## Acceptance / Done condition

1. Any supported test-kit surface has an accepted compatibility decision,
   defining-module imports, an explicit API compatibility declaration, and no
   root re-exports or private Coordinator/runtime-handle escape hatch.
2. One focused scenario reads as an imperative World/Timeline pytest story,
   runs in the ordinary gate, and emits the same normalized expanded schedule
   consumed by its data-only replay.
3. Replaying the same expanded scenario at the same commit produces the same
   accepted History, snapshots, checker observations, terminal disposition,
   and failure location.
4. Two fresh seeded runs with the same profile produce the same expanded
   scenario, while replay remains authoritative if future code changes PRNG
   consumption.
5. A process crash revokes the old generation before abrupt disposal, performs
   no graceful settlement, rejects stale use, discards all declared volatile
   objects, and resumes only through production load/reconcile paths.
6. Faults can target named semantic cuts before and after durable acceptance,
   not arbitrary implementation line numbers.
7. Every run and `run_until` checkpoint is bounded by events, actions, logical
   time, retained data, pending work, and wall-clock test budget, and reports
   which bound ended it.
8. Checkers execute at every legal atomic boundary and fresh load over detached
   data, and a fair phase drains only profile-declared eligible work.
9. The harness runs without credentials, real providers, network sleeps, or a
   second implementation of Petrus semantics.
10. Existing simulation, unit, integration, full, and release gates remain green.

## Driver QA and evidence plan

- Begin with one executable World/Timeline scenario spanning delivery →
  Activity request → terminal freeze → projection crash → process
  reconstruction → projection-only completion. Generate its strict artifact
  from the run rather than hand-authoring the JSON.
- Add one lifecycle race and one timer/retry scenario only after the vertical
  slice proves deterministic replay.
- Deliberately perturb observation/logging and verify expanded replay does not
  depend on additional PRNG draws.
- Execute focused replay tests, related recovery suites, `scripts/check full`,
  and `scripts/check release`.

## Out of scope

- Broad random workload generation and shrinking; DS3 owns it.
- A declarative replacement for normal pytest scenario authoring or
  serialization of Python source, closures, callbacks, and assertions.
- Application-domain World truth or business verbs. Applications may compose
  those over the Petrus Timeline without moving their policy into Petrus.
- Fidelity claims for real databases, kernels, sockets, or hardware.
- Simulated arbitrary byte corruption before a concrete Petrus property and
  adapter contract justify it.
- Public API stability for implementation details outside the accepted
  defining-module contract.
