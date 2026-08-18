---
code: CV19
level: Value
status: Active
status_reason: CV19.DS1 is Done and DS2 now proves split request/cancellation refusal plus joined begin commit- and Dispatch-failure rollback/reconstruction in addition to bounded World v4, process containment, and LocalDispatch provider time; broader cuts and DS3–DS4 remain active
updated: 2026-08-18
related:
  - ../../../../src/petrus/simulation.py
  - ../../../../tests/petrus/impetus/instance/test_instance_replay_properties.py
  - ../../decisions/records/2026-08-17T2249Z-ship-a-supported-cross-project-dst-test-kit.md
  - ../../decisions/records/2026-08-18T1417Z-local-dispatch-accepts-an-explicit-provider-clock.md
  - https://github.com/tigerbeetle/tigerbeetle/blob/main/docs/TIGER_STYLE.md
  - https://github.com/tigerbeetle/tigerbeetle/blob/main/docs/internals/vopr.md
  - https://github.com/henriquebastos/hamsterdan
---

# CV19 — Deterministic simulation testing

## Intent

Make Petrus systematically testable as a complex durable system: run production
semantic and recovery logic under bounded, generated schedules of time,
delivery, Activity completion, retry, lifecycle change, storage failure, and
process restart; check independent safety and liveness properties continuously;
and reduce every discovered failure to a durable scenario that can be replayed
locally.

This Value does not ask Python to imitate Zig. It transfers the language-neutral
discipline behind TigerBeetle's Deterministic Simulation Testing (DST): put
explicit limits on work, isolate nondeterminism behind owned seams, distinguish
programmer invariants from expected operating failures, state the environment
under which progress is required, and use seeded state-space exploration as a
final line of defense rather than as proof of correctness.

## Existing foundation

Petrus is not starting from zero:

- canonical History and deterministic replay already own semantic truth;
- the kernel reads the History watermark rather than a wall clock;
- Engine and Coordinator already accept Clock, Dispatch, Sensor, selection, and
  driving-policy seams;
- `petrus.simulation` already provides an explicitly bounded,
  implementation-free semantic simulation profile;
- golden traces, deterministic suite ordering, Hypothesis replay/resume
  properties, selected mutation testing, and hand-authored crash-window tests
  already exercise important layers;
- Activity result freezing, projection-only recovery, lifecycle fencing, and
  backend reconstruction already expose concrete safety invariants.

These capabilities are necessary but not sufficient for DST. The current
hosted simulation profile deliberately forbids implementations, Dispatch, and
in-flight work. Existing crash tests select known cuts individually. No one
seeded scheduler currently controls event order, logical time, adapter faults,
crash/reconstruction, workload generation, independent checkers, and replay
artifacts across the production Engine/Coordinator boundary.

## Ownership boundary

Petrus owns reusable simulation mechanics and runtime properties:

- deterministic logical time, event ordering, identifiers, randomness, and
  scenario serialization;
- faulting History Store and Dispatch test adapters at Petrus-owned contracts;
- process-crash reconstruction from retained durable state;
- generic History, marking, occurrence, Activity, timer, lifecycle, and
  convergence checkers;
- generated state-machine campaigns and their replay/shrinking protocol;
- bounded CI and longer-running campaign operations.

Applications own their domain model, authority policy, provider truth, and
external-effect fault worlds. Hamsterdan may consume an accepted Petrus test
surface, but GitHub readiness semantics do not enter Petrus. Conversely,
Hamsterdan must not fork Petrus's event scheduler or recovery model.

The existing `petrus.simulation` `implementation-free-v1` profile is a public,
portable product contract with its own bounds. CV19 does not silently broaden,
rename, or break it. DS1's DST proof remains internal to `tests/dst`. Petrus
and Hamsterdan have agreed on a separate generic test-kit boundary under the
accepted `petrus.testing.dst` defining module. This is a supported
cross-project test surface, not a silent promotion of the DS1 proof.

## Correctness contract

### Safety properties

At minimum, every campaign must continuously check:

1. live marking, watermark, in-flight state, lifecycle state, and candidate
   selection agree with replay from the same accepted History;
2. History positions, occurrence identities, and terminal records remain
   contiguous, unique, and writer-valid;
3. one firing occurrence prepares at most one stable logical Activity
   invocation, regardless of redispatch or process restart;
4. a frozen Activity terminal is never re-executed merely because projection
   or the host crashes;
5. one accepted source-delivery identity creates at most one semantic fact and
   exact redelivery receives the prior acknowledgement;
6. close/reset ordering and late terminal handling never mutate a closed
   lifecycle generation;
7. an append or transaction failure exposes no state that only an uncommitted
   fact could authorize;
8. bounded retry, queue, payload, History, event, and work-per-turn limits fail
   with their specified disposition rather than becoming hidden unbounded
   behavior.

### Liveness condition

Liveness is never asserted under arbitrary permanent failure. A campaign may
demand progress only after entering a declared fair environment in which:

- faults selected for recovery have stopped;
- logical time can advance to every retained deadline;
- required durable state remains readable;
- at least one eligible Dispatch/Worker path can accept the relevant work; and
- no application-owned human or external event is still a stated prerequisite.

Under those conditions, every bounded run must converge to quiescence, an
explicit terminal, a declared external/human wait, bounded exhaustion, or
quarantine. It must not livelock, silently abandon eligible work, or depend on
a process-local accident for progress.

### Replay identity

A seed alone is not a permanent reproduction contract. Every failure artifact
must retain the Petrus Git commit, scenario/profile version, expanded event and
fault choices, relevant runtime/dependency versions, failing property, and
smallest available replay path. Shrinking may change the seed-derived trace;
the minimized expanded scenario becomes the durable regression fixture.

## Delivery

1. [CV19.DS1 — Correctness and simulation contract](cv19-ds1-correctness-and-simulation-contract.md)
   is Done. It freezes the correctness and strict scenario contracts, proves
   one concrete production crash replay, and conditionally routes future
   correctness-sensitive work before a broad harness is built.
2. [CV19.DS2 — Deterministic event and fault harness](cv19-ds2-deterministic-event-and-fault-harness.md)
   runs production Engine/Coordinator behavior under one bounded logical event
   scheduler with faulting adapters and crash reconstruction. Its generic
   executor/profile design and supported test-kit surface are accepted. The
   first public-Engine crash/recovery slice and strict world replay are
   implemented; version 2 retains exact action-budget/checker failures, and
   version 3 adds separable seeded authorities while replaying retained version
   1 and 2 artifacts unchanged. Version 4 adds exact profile-owned retained and
   pending resource gauges while preserving version 1 through 3 replay. The
   separate runner v1 executes a complete World in a killable child, retains
   synchronized acknowledged prefixes and unfinished attempts, and classifies
   wall timeout as harness containment rather than a deterministic artifact.
   Paired terminal-boundary profiles now prove a
   pre-commit History refusal beside post-commit projection recovery, and a
   lifecycle-reset profile proves crash reconstruction plus late-terminal
   quarantine/duplicate acknowledgement. A timer profile now proves loss and
   reconstruction of a queued deadline followed by one exact logical-time
   maturation. A LocalDispatch profile proves a retry epoch across process
   loss and exact attempt-budget exhaustion without re-preparing the logical
   Activity. A separate profile now drives nonzero provider backoff through
   public LocalDispatch clock and Worker doors, refusing a claim immediately
   before the durable availability time and claiming at the exact deadline
   after crash/reload. A complementary profile proves durable successful-terminal
   recollection, exact duplicate acknowledgement, conflict refusal, and one
   projection after pre-collection process loss. An identified-ingress profile
   proves exact source redelivery, changed-content refusal, distinct equal-data
   identities, and recovery from both process loss and the poisoned conflict
   generation. A delayed-terminal profile reconstructs modeled external truth
   after volatile queue loss and delivers once at the authored logical instant.
   A post-commit History profile loses an acknowledgement after durable terminal
   acceptance and recovers projection without redelivery. A Dispatch-refusal
   profile now proves the paired outbox boundary: `ActivityRequested` commits
   before refused custody, and fresh load republishes the byte-equivalent
   invocation without another `prepare`. A paired cancellation-refusal profile
   proves `ScopeReset` commits before refused cancellation custody, then fresh
   load repeats the exact instruction before a late terminal is quarantined. A
   pair of separately identified real Absurd/PostgreSQL profiles now proves the
   stronger joined shape: either a refused begin commit or a failing task spawn
   leaves neither semantic prefix nor task, and fresh provider load begins
   exactly once from the prior marking. The broader fault/cut matrix keeps DS2
   active.
3. [CV19.DS3 — Stateful generation and independent checkers](cv19-ds3-stateful-generation-and-independent-checkers.md)
   adds broad and targeted workload generation, independent models/checkers,
   shrinking, semantic coverage, and durable replay fixtures.
4. [CV19.DS4 — Campaign and production-boundary qualification](cv19-ds4-campaign-and-production-boundary-qualification.md)
   establishes PR/nightly campaign tiers and proves how simulation composes
   with real storage, transport, and process-kill tests without overstating
   either layer.

## Done condition

CV19 is Done when a fresh checkout can run a documented deterministic campaign
against production Petrus runtime logic, replay an exact retained failure
without real sleeps or provider authority, and demonstrate all of the following:

- generated deliveries, timers, Activity outcomes, retries, lifecycle changes,
  crash points, and recoveries cross their real semantic doors;
- independent safety checkers run after every accepted event and a declared
  fair phase checks bounded convergence;
- at least one intentionally seeded defect or mutation is found, shrunk,
  replayed, and retained as an ordinary regression, proving that the harness
  can falsify behavior rather than merely exercise code;
- fixed regression scenarios run in the ordinary gate and rotating bounded
  campaigns run on their documented cadence with useful failure artifacts;
- targeted real-backend and process tests remain green and their stronger and
  weaker claims are stated separately from simulated evidence;
- project guidance teaches future Drivers when to produce a correctness sketch,
  how to replay before fixing, and how to promote a minimized failure without
  burdening unrelated work.

## Evidence strategy

Evidence must report semantic reach, not only line coverage or number of seeds:
visited lifecycle states, event kinds, fault cuts, recovery paths, terminal
dispositions, checker activations, fair-phase convergence, and scenarios that
could not be generated. Campaign duration and resource budgets must be explicit.

The complete repository gate remains necessary but is not the only claim.
Focused deterministic replays, mutation/fault sensitivity, campaign summaries,
and real-backend/process routes each retain their own evidence and limits.

## Out of scope

- Formal verification or exhaustive model checking claims.
- Simulating every CPython, asyncio, operating-system, database, ZeroMQ,
  filesystem, or hardware behavior.
- Replacing real PostgreSQL, transport, process-kill, provider, load, security,
  or compatibility testing.
- Random chaos without deterministic replay and executable properties.
- Reimplementing production logic inside the simulator.
- Tiger Style's Zig-specific no-allocation rule, zero-dependency policy, blanket
  recursion ban, or numeric assertion/function-size rules.
- Additional package-support or API compatibility claims for DST
  infrastructure without an explicit accepted decision and version identity.

## Grounding and cautions

TigerBeetle describes DST as production code running with clock, network, and
disk nondeterminism stubbed, with faults selected from a seed and failures
replayed by seed plus Git commit. Its VOPR checks both assertions and additional
cluster checkers. [D]

TigerBeetle also documents a correctness defect missed by four fuzzers because
their sophisticated workload projected away the triggering states. CV19
therefore requires simpler broad generators beside targeted profiles and an
independent exact model where one is practical. Simulation proves the presence
of discovered bugs, not their absence. [D]

Sources:

- <https://github.com/tigerbeetle/tigerbeetle/blob/main/docs/TIGER_STYLE.md>
- <https://github.com/tigerbeetle/tigerbeetle/blob/main/docs/internals/vopr.md>
- <https://tigerbeetle.com/blog/2023-07-06-simulation-testing-for-liveness/>
- <https://tigerbeetle.com/blog/2025-06-06-fuzzer-blind-spots-meet-jepsen/>
