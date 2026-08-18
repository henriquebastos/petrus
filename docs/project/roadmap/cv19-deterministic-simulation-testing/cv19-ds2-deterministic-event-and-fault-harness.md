---
code: CV19.DS2
level: Delivery Story
status: Active
status_reason: Split Dispatch request/cancellation refusals and the real joined begin-commit refusal now replay through crash with exact repair; DS2 remains active for the broader transaction cut matrix
updated: 2026-08-18
related:
  - index.md
  - cv19-ds1-correctness-and-simulation-contract.md
  - ../../decisions/records/2026-08-17T2249Z-ship-a-supported-cross-project-dst-test-kit.md
  - ../../decisions/records/2026-08-18T1417Z-local-dispatch-accepts-an-explicit-provider-clock.md
  - ../../../process/dst-world-v1.md
  - ../../../process/dst-world-v2.md
  - ../../../process/dst-world-v3.md
  - ../../../process/dst-world-v4.md
  - ../../../process/dst-process-runner-v1.md
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

## Implemented vertical slice

The accepted kernel ships under the supported defining module
`petrus.testing.dst`. The current API identity is `petrus.testing.dst/v4` and
its current strict artifact is `petrus-dst-world` version 4. The loader and
same interpreter retain strict version 1 through 3 decode/replay
compatibility; DS1's `petrus-dst-scenario` version 1 remains byte-for-byte
unchanged.

The first executable pytest World/Timeline story proves the post-acceptance
side of `activity_terminal_frozen` through the real public Engine surface:

1. create a fresh Engine generation and run until an Activity is pending;
2. activate the profile-validated `projection.raise` fault at the named
   `activity_terminal_frozen` cut;
3. accept the terminal result and observe the frozen terminal plus refused
   projection;
4. revoke the Timeline, abruptly drop the generation without semantic
   settlement, and reject stale use;
5. construct a fresh Engine/History/Dispatch/handler graph through `load`;
6. enter the fair phase and converge through projection-only recovery; and
7. generate and replay the same 15 expanded operations with exact checker
   entries, journal digest, and ending disposition.

The second exact profile proves the paired pre-acceptance side without changing
the supported kernel or prior profile identity:

1. accept one external terminal into the scripted Dispatch;
2. inject `history.refuse` before the JSONL delegate can accept
   `ActivityCompleted` and observe an unchanged durable frontier;
3. continuously bound canonical terminal/projection records by authored
   terminal deliveries minus observed pre-commit refusals;
4. abruptly drop the poisoned generation and load a fresh Engine graph;
5. reconcile the recorded invocation into fresh Dispatch custody without
   calling `prepare` again, preserving its occurrence, activity, input, policy,
   correlation, and idempotency identities;
6. redeliver the exact terminal and converge under the fair suffix; and
7. replay the retained 19 operations and 31 journal entries, including 11
   checker evaluations, exactly.

The third exact profile proves the first planned lifecycle race:

1. open lifecycle generation 1 and deliver identified input inside it;
2. begin an Activity, then atomically reset the scope to generation 2 while
   that Activity remains in flight;
3. abruptly drop the process before its late terminal is delivered;
4. load a fresh Engine graph and reconcile the recorded reset/cancellation
   fence without preparing or dispatching the cancelled Activity;
5. quarantine one exact late terminal, acknowledge its exact duplicate without
   another History append, and record no ordinary terminal or projection;
6. continuously compare active generation and lifecycle/terminal/projection
   records with independent authored-world authority; and
7. replay the retained 22 operations and 36 journal entries, including 13
   checker evaluations, exactly.

The fourth exact profile proves Engine-owned timer reconstruction without
conflating it with Dispatch-owned retry policy:

1. observe a delayed transition at logical instant 0 and let the profile return
   its deadline to the one World scheduler;
2. abruptly drop the process after the World has queued instant 5, discarding
   that volatile future command before maturation;
3. load a fresh public Engine at instant 0 and reconstruct the same deadline
   from canonical History and the injected World clock;
4. enter the fair phase, advance the World directly to instant 5, append one
   `TimerMatured`, and fire the delayed transition exactly once;
5. continuously reject early or duplicate maturation and any delayed firing
   without its canonical maturation fact; and
6. replay the retained 15 operations and 24 journal entries, including 8
   checker evaluations, exactly.

The fifth exact profile proves zero-backoff retry reconstruction and exhaustion
through production LocalDispatch custody:

1. prepare and publish one canonical Activity invocation with two attempts;
2. claim epoch 1 through the public LocalDispatch Worker door and report one
   classified retryable failure with exact zero backoff;
3. abruptly drop the Engine/Worker generation after LocalDispatch has durably
   admitted the retry but before another claim;
4. load a fresh public Engine and LocalDispatch session, reconcile the recorded
   invocation without another `prepare`, and claim epoch 2 with unchanged
   activity, input, policy, correlation, and idempotency;
5. report a second retryable failure, let LocalDispatch exhaust the declared
   attempt budget, and record exactly one `ActivityFailed` plus `FiringFailed`
   with no business projection; and
6. replay the retained 18 operations and 30 journal entries, including 11
   independent checker evaluations, exactly.

A separate delayed-retry profile closes the planned LocalDispatch
provider-time boundary without changing that retained zero-backoff identity:

1. inject World logical time through the optional public LocalDispatch
   millisecond clock while SQLite remains custody and serialization authority;
2. fail epoch 1 under a five-second retry policy and abruptly drop the process
   after durable retry admission;
3. load a fresh public Engine/LocalDispatch graph at instant 0 without another
   handler `prepare`;
4. execute the public Worker claim door at instant 4 and observe no eligible
   retry, then execute it at instant 5 and receive epoch 2 with stable logical
   invocation identity;
5. exhaust the retry budget with exactly one canonical `ActivityFailed` and
   `FiringFailed`, no projection, and continuous independent deadline/retry
   checks; and
6. replay the retained 22 operations and 35 journal entries, including 12
   checker evaluations, exactly.

The sixth exact profile proves successful LocalDispatch terminal custody and
recollection across the complementary pre-collection crash cut:

1. prepare, publish, and claim one canonical Activity invocation;
2. report one successful terminal to LocalDispatch, acknowledge its exact
   duplicate, and refuse a conflicting report through the public Worker door;
3. observe that the provider terminal is durable while canonical History still
   ends at `ActivityRequested`;
4. abruptly drop the Engine/Worker generation before Engine collection;
5. load a fresh public Engine and LocalDispatch session, republish the recorded
   invocation without another `prepare`, recollect the first provider result,
   and append exactly one `ActivityCompleted` plus `FiringCompleted`; and
6. replay the retained 15 operations and 26 journal entries, including 10
   independent checker evaluations, exactly.

The seventh exact profile proves identified source delivery authority through
public Engine ingress and reconstruction:

1. accept one identified source delivery and its canonical source firing;
2. abruptly drop the process after durable acceptance and load a fresh public
   Engine from JSONL History;
3. acknowledge an exact redelivery without appending History or duplicating
   output;
4. accept an equal payload under a distinct identity as a second external fact;
5. refuse changed content under the first identity, observe unchanged durable
   History at the legal atomic boundary, then drop the poisoned generation and
   recover through another public load; and
6. replay the retained 15 operations and 26 journal entries, including 10
   independent checker evaluations, exactly, ending in the open source's
   legitimate external wait.

The eighth exact profile proves delayed external terminal reconstruction under
the World clock without treating it as Dispatch retry time:

1. begin one production Activity and author one external result for logical
   instant 5;
2. abruptly drop the process while that delivery exists in both modeled
   external truth and the World's volatile queue;
3. discard the volatile queue entry, load a fresh public Engine, and re-propose
   the same delivery from retained external truth;
4. enter the fair phase, advance directly from instant 0 to 5, and deliver the
   result through the one normalized interpreter; and
5. record exactly one `ActivityCompleted`, `FiringCompleted`, and projection,
   then replay 17 operations and 27 journal entries, including 9 independent
   checker evaluations, exactly.

The ninth exact profile proves post-commit History acknowledgement loss:

1. deliver one external Activity result and durably append its
   `ActivityCompleted` record;
2. lose the append acknowledgement after acceptance, poisoning the live Engine
   while leaving canonical History one record ahead of its in-memory Instance;
3. observe the durable terminal through the faulting History adapter, then
   abruptly drop the ambiguous generation;
4. load a fresh public Engine and complete projection from the accepted terminal
   without another terminal delivery or handler preparation; and
5. replay 15 operations and 25 journal entries, including 9 independent checker
   evaluations, exactly.

The tenth exact profile proves Dispatch refusal after canonical request
acceptance:

1. activate one exact `dispatch.refuse` fault before the first Engine drive;
2. let production commit `CandidateSelected`, the firing prefix, and
   `ActivityRequested`, then refuse the public Dispatch acceptance door;
3. observe no custody or terminal authority, abruptly drop the poisoned live
   Engine, and load a fresh public Engine graph from the accepted History;
4. reconcile the byte-equivalent occurrence, activity, input, policy,
   correlation, and idempotency through a fresh Dispatch without another
   handler `prepare`;
5. complete the accepted invocation and converge with one terminal and
   projection; and
6. replay 14 operations and 24 journal entries, including 9 independent
   checker evaluations, exactly.

The eleventh exact profile proves cancellation refusal after the reset fence:

1. start one scoped Activity and activate a one-shot refusal at the public
   Dispatch cancellation door;
2. let production commit `ScopeReset` before cancellation raises, then observe
   canonical generation 2, the exact refused instruction, and a poisoned live
   Engine;
3. revoke and abruptly drop that generation without semantic settlement;
4. load a fresh public Engine and repeat the byte-equivalent occurrence,
   invocation, execution policy, correlation, idempotency, and History position
   through a new Dispatch;
5. accept that tombstone, deliver the late result, and record one quarantine
   with no ordinary terminal or projection; and
6. replay 19 operations and 32 journal entries, including 12 independent
   checker evaluations, exactly.

A separately identified real-provider profile proves the joined begin
transaction without exposing the private Engine resource seam:

1. construct through public `petrus.engine.absurd.create_engine` over a
   disposable PostgreSQL database and activate one connection-boundary commit
   refusal at `activity_requested`;
2. let production prepare `CandidateSelected`, the firing prefix,
   `ActivityRequested`, and the Absurd task spawn in one transaction, then
   refuse before the connection accepts it;
3. observe through an independent PostgreSQL connection that only construction
   remains durable and no task exists, while the live Engine is poisoned;
4. revoke and abruptly drop that generation, then construct a fresh public
   provider generation through `load_engine`;
5. prove the uncommitted selection/invocation was not installed: production
   prepares anew from the prior marking and commits exactly one begin plus one
   pending task; and
6. replay the retained 9 operations and 16 journal entries, including 6
   independent checker evaluations, exactly, ending in the legitimate
   external wait for a Worker result.

The twelfth exact profile proves generic retained-resource and hidden-pending-work
accounting across a production Engine crash:

1. declare exact profile gauges for History records/bytes, marking
   tokens/bytes, in-flight Activities, and Dispatch custody;
2. sample the same complete detached key set before create and after every
   accepted command, observation, crash/drop, fresh load, fair, and finish
   boundary;
3. abruptly drop a generation with one durable Activity request, measure the
   retained History with all live-only gauges at zero, then reconstruct the
   pending invocation through public `Engine.load` and drive doors;
4. converge under inclusive resource ceilings and replay 14 operations and 39
   journal entries exactly; and
5. in a paired failure fixture, accept the first Engine drive, observe six
   History records against a limit of five, retain that accepted operation plus
   `profile_resources:retained.history_records`, and replay the exact 3-operation
   / 10-journal-entry failure.

The independently versioned outer runner closes the wall-clock containment
gap without changing World or artifact semantics:

1. an exact importable entrypoint constructs the complete profile, checker,
   World, and runtime generation inside a fresh child process;
2. strict synchronized JSONL acknowledges each attempt before entering a
   profile call and each complete operation/journal/resource/check boundary;
3. the existing public-Engine resource scenario completes under the runner,
   returns its unchanged version-4 artifact, and replays exactly;
4. a deliberate profile hang acknowledges its normalized `SubmitAttempt`,
   ignores termination, and forces the parent through terminate → kill → reap;
   and
5. the structured harness failure retains the exact create boundary and
   unfinished command but contains no fabricated `FailureOperation` or replay
   artifact.

All authored support and retained evidence live together under `tests/dst/`.
The application profile returns detached follow-up proposals; only the World
validates, orders, journals, and executes them. Checkers consume detached
History-derived observations after legal atomic boundaries and fresh load.
The production module has no Coordinator, Engine, or mutable runtime-handle
export and no Petrus-root re-export.

Focused evidence includes strict profile/fault validation, constructor cleanup,
all generic budget classes, total queue ordering, logical-time advancement,
fair-phase interference refusal, pending-work refusal for every authored
ending, stale-generation rejection, strict JSON/artifact refusal, exact
registry/digest matching, same-interpreter replay, and deterministic replay
CLI output. The History-refusal profile additionally proves pre-commit adapter
refusal, poison/drop/load, exact invocation redispatch, terminal redelivery,
and a mutation-sensitive detached commit-authority checker. Version 2
additionally retains the exact attempted operation for
action-budget exhaustion and checker refusal, reproduces both failures through
the same interpreter, refuses shifted or mismatched failures, and does not
misclassify profile/checker implementation exceptions as World failures.
Version 3 adds workload/fault/identifier/event-order authorities isolated by
hash domain and counter, strict seed/algorithm/draw provenance, and a retained
seeded Engine scenario whose replay never consults the PRNG.

### Acceptance assessment after the slice

| Done condition | Slice result |
| --- | --- |
| 1. Accepted defining-module compatibility surface | Met by the accepted decision, current `petrus.testing.dst/v4`, explicit v1-v3 constants/models, exact identities, no root/private exports, and the versioned [`dst-world-v4`](../../../process/dst-world-v4.md), [`dst-world-v3`](../../../process/dst-world-v3.md), [`dst-world-v2`](../../../process/dst-world-v2.md), and [`dst-world-v1`](../../../process/dst-world-v1.md) contracts. |
| 2. Imperative story emits replay data | Met by the executable profiles under `tests/dst/` and retained projection, pre/post-commit History, split Dispatch request/cancellation refusal, joined begin rollback, ingress-redelivery, delayed-terminal, lifecycle-race, timer-recovery, zero/delayed retry-exhaustion, terminal-recollection, and resource-bound fixtures. |
| 3. Same-interpreter replay agreement | Met for all fourteen public-Engine/provider crash/recovery stories plus the retained resource-overage failure, including exact operations, resource/checker observations, dispositions, and journal digests. |
| 4. Seeded repeatability | Met: two fresh seed-1729 Engine runs produce the same expanded artifact; workload, fault, identifier, and event-order streams are independently pinned, and replay ignores changed seed provenance. |
| 5. Abrupt generation reconstruction | Met for the public-Engine profile, including revoke-before-drop and stale Timeline refusal. |
| 6. Named cuts before/after durable acceptance | Partial: paired pre-commit refusal/post-commit acknowledgement-loss History cuts, split Dispatch refusal after a durable request and lifecycle fence, joined begin+spawn commit rollback, identified ingress redelivery, delayed external completion, lifecycle and timer reconstruction, zero- and nonzero-backoff LocalDispatch retry reconstruction/exhaustion, and provider-terminal custody before Engine collection are proved; the broader transaction matrix remains. |
| 7. Complete bounds | Met for the generic harness: action, queue, logical-time/advance, reload, predicate, artifact, profile-retained-data, hidden-pending-work, process-progress, and wall-clock limits are executable and identify the ending bound. |
| 8. Checker cadence and fair draining | Met for the vertical slice; broader independent S1–S8 checker coverage belongs to the remaining DS2/DS3 work. |
| 9. Hermetic real-runtime execution | Met for the provider-neutral vertical slice: no credentials, external providers, network sleeps, or substitute Petrus semantics. The joined profile is separately identified real-boundary qualification against disposable PostgreSQL/Absurd and claims only that composition's transaction contract. |
| 10. Repository gates | Met: focused DST and project tests pass, and the current full and release gates pass all 2,295 tests in both release orders with 17 expected serial qualification deselections. |

Version 1 artifacts intentionally retain only authored endings. Version 2
removes that format limit: it preserves one exact terminal failed attempt plus
its budget or checker detail, and replay succeeds only when the same interpreter
reproduces the same operation boundary, checks, disposition, and digest. A
successful replay reports `outcome: pass` separately from the retained
`budget_exhausted` or `invariant_failure` disposition; it does not relabel the
counterexample itself as passing behavior.

Version 3 adds seed provenance without making the seed executable. Four
SHA-256/counter authorities isolate workload, fault, identifier namespace, and
event-order draws. Their chosen consequences still cross the normalized
Timeline/World doors, and replay constructs an unseeded World from the expanded
operations. The replay-result schema therefore remains version 2 even though
the authoring API and artifact are version 3.

Version 4 adds exact profile-owned resource manifests without changing prior
profiles or artifacts. `BudgetV4` limits strict named gauges returned by the
side-effect-free `resource_usage(generation | None)` door. The World samples
and journals them at legal boundaries, rejects changing key sets as profile
contract errors, and deterministically retains the lexicographically first
overage as a budget failure. A legacy `Budget` never invokes the new door and
continues to author version 3. The wall-clock watchdog remains a distinct
outer-process concern: [`petrus.testing.dst.runner/v1`](../../../process/dst-process-runner-v1.md)
now supervises the complete World, retains acknowledged operation/journal
prefixes and unfinished attempts, and never manufactures an ordinary
deterministic `FailureOperation` for a killed call.

### Executed evidence

- `UV_FROZEN=1 uv run pytest -q tests/dst` — 108 passed.
- `UV_FROZEN=1 uv run pytest -q tests/dst tests/project` — 137 passed.
- `UV_FROZEN=1 uv run pytest -q tests/dst/test_process_runner.py` — 3 passed;
  the public-Engine process run returned and replayed its unchanged 14-operation
  / 39-journal-entry v4 artifact, while the deliberate SIGTERM-resistant hang
  escalated to SIGKILL and returned its exact unfinished `runtime.hang`
  attempt with no artifact.
- `UV_FROZEN=1 uv run python -m tests.dst.replay_world
  tests/dst/fixtures/projection-crash-recovery-world-v1.json` — `pass`,
  `converged`, 15 operations, 25 journal entries, digest
  `sha256:609247836dae1f306b34e5d7308901c10f95db2207fa0e583c446d98354cab74`.
- The same replay route over `action-budget-exhaustion-world-v2.json` returned
  `pass` / `budget_exhausted`, 2 operations, 4 journal entries, and digest
  `sha256:8020031489a668e435820458f07d412bfae5bfe4b816e6c8a2e5e5e80dd63275`.
- The same replay route over `terminal-checker-failure-world-v2.json` returned
  `pass` / `invariant_failure`, 6 operations, 15 journal entries, and digest
  `sha256:82ca298ed8946a75b35e65b7c8609d1d03ebebf4546f10bde88ebfbccea5a9b1`.
- The same replay route over
  `seeded-projection-crash-recovery-world-v3.json` returned `pass` /
  `converged`, 17 operations, 27 journal entries, and digest
  `sha256:ddf70617988b010a3300fc6703eb0c8f1bc1c4b0751b4156c2059f851d34a779`.
- The same replay route over
  `history-refusal-crash-recovery-world-v3.json` returned `pass` /
  `converged`, 19 operations, 31 journal entries including 11 checker
  evaluations, and digest
  `sha256:d8a9dec14dc40dc5a27afeaec9028ac37646695e22ff75bee2ce7f2c0f06aff1`.
- The same replay route over
  `lifecycle-reset-late-terminal-world-v3.json` returned `pass` / `quiescent`,
  22 operations, 36 journal entries including 13 checker evaluations, and
  digest
  `sha256:1719800ed00cfb705535b47b359d23988080b19a073f6247a995776ab7d9b194`.
- The same replay route over `timer-crash-recovery-world-v3.json` returned
  `pass` / `converged`, 15 operations, 24 journal entries including 8 checker
  evaluations, and digest
  `sha256:82460bacb8628c897a35e19883cb0f91e07bc1343cd5944ea22592c940fc8a69`.
- The same replay route over `retry-crash-exhaustion-world-v3.json` returned
  `pass` / `quarantined`, 18 operations, 30 journal entries including 11
  checker evaluations, and digest
  `sha256:8158a70525b02afd7fb705ddec9ffc62a66d8c4ec6c9c0872062d36a05402392`.
- The same replay route over `delayed-retry-crash-recovery-world-v3.json`
  returned `pass` / `quarantined`, 22 operations, 35 journal entries including
  12 checker evaluations, and digest
  `sha256:339da88d51c682641b7e8fc8fbf8964622c2c031dd6c373f327b94464e26a6c1`.
- The same replay route over `local-terminal-redelivery-world-v3.json`
  returned `pass` / `converged`, 15 operations, 26 journal entries including
  10 checker evaluations, and digest
  `sha256:ff332ce259e54320354ba2006e59053d4c5fb83488482de32081b8a5503ceab9`.
- The same replay route over `identified-delivery-redelivery-world-v3.json`
  returned `pass` / `external_wait`, 15 operations, 26 journal entries
  including 10 checker evaluations, and digest
  `sha256:e0223b0e0dd5ce6ce964cb9a72e38a9370f7f6b8a38d9571cdc1179e9a03d8bc`.
- The same replay route over `delayed-terminal-recovery-world-v3.json`
  returned `pass` / `converged`, 17 operations, 27 journal entries including 9
  checker evaluations, and digest
  `sha256:a89273aadcb2aeb48e60832d658e6ae37ef8a09c5dcb14298e16bdd2b398c007`.
- The same replay route over `history-ack-loss-recovery-world-v3.json`
  returned `pass` / `converged`, 15 operations, 25 journal entries including 9
  checker evaluations, and digest
  `sha256:b69cd6760d3a1818f4cbfcc5f531d7ad3c970b0e383c5b5ba0abd62a0ff47c92`.
- The same replay route over `dispatch-refusal-crash-recovery-world-v3.json`
  returned `pass` / `converged`, 14 operations, 24 journal entries including 9
  checker evaluations, and digest
  `sha256:63301ff867ae1c9950d0307e9ad74952e4c10105e3d60d24cd00a5e0496f733a`.
- The same replay route over
  `lifecycle-cancellation-refusal-world-v3.json` returned `pass` /
  `quiescent`, 19 operations, 32 journal entries including 12 checker
  evaluations, and digest
  `sha256:0b4ccbadb61d020c28ea3f330fbd2a7bf27b1af9157db2a375e25f6bcbb3da69`.
- `UV_FROZEN=1 uv run pytest -q
  tests/dst/test_joined_world.py::test_retained_joined_begin_fixture_replays_without_the_authored_scenario`
  returned `pass` / `external_wait`, 9 operations, 16 journal entries including
  6 checker evaluations, and digest
  `sha256:0b2129eaf3802d174a5526f5e32b0e6de8f923cd2d8ce3e05bd89c2904c930c7`.
- The same replay route over `resource-bounded-recovery-world-v4.json`
  returned `pass` / `converged`, 14 operations, 39 journal entries, and digest
  `sha256:0e1ffac28729a33fe7bb19e4ec52869c150a6a5e8312018419be53c4f2d69baf`.
- The same replay route over `history-record-budget-exhaustion-world-v4.json`
  returned `pass` / `budget_exhausted`, 3 operations, 10 journal entries, and
  digest
  `sha256:845e62259ae1e18b1ab92f1a2f5c16b1757cea29181bda6e6cd767ce0857b451`.
- `scripts/check full` — 2,295 passed.
- `scripts/check release` — 2,295 passed in both the four-worker and fixed-order
  serial runs; the serial run reported 17 expected qualification deselections.
- `UV_FROZEN=1 uv run ast-grep test --skip-snapshot-tests` — all 19
  architectural rule fixtures passed, including the runtime-neutral supported
  test-kit boundary.
- `UV_FROZEN=1 uv build --out-dir /tmp/petrus-dst-v4-dist` plus wheel listing —
  built the sdist and wheel and confirmed both `petrus/testing/__init__.py` and
  `petrus/testing/dst.py` are packaged.

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
9. The provider-neutral harness runs without credentials, external providers,
   network sleeps, or a second implementation of Petrus semantics; any
   provider-backed qualification is named separately with its exact substrate
   and weaker claim.
10. Existing simulation, unit, integration, full, and release gates remain green.

## Driver QA and evidence plan

- Begin with one executable World/Timeline scenario spanning delivery →
  Activity request → terminal freeze → projection crash → process
  reconstruction → projection-only completion. Generate its strict artifact
  from the run rather than hand-authoring the JSON.
- Keep delayed-backoff and lease-expiry scenarios at their Dispatch-owned
  provider-time boundary rather than editing SQLite state or using an Engine
  timer as a substitute for retry scheduling.
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
- Broad fidelity claims for real databases, kernels, sockets, or hardware; the
  joined profile claims only the induced public-provider transaction boundary.
- Simulated arbitrary byte corruption before a concrete Petrus property and
  adapter contract justify it.
- Public API stability for implementation details outside the accepted
  defining-module contract.
