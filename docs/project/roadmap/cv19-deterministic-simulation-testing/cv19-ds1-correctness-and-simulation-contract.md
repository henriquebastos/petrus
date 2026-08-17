---
code: CV19.DS1
level: Delivery Story
status: Planned
status_reason: The reusable DST contract, ownership boundaries, and project guidance have not yet been frozen
updated: 2026-08-17
related:
  - index.md
---

# CV19.DS1 — Correctness and simulation contract

## Intent

Create the smallest authoritative contract from which Petrus DST can be built
without confusing deterministic test order, bounded semantic simulation,
property testing, fault injection, and full system simulation.

## Scope

- Inventory every source of nondeterminism relevant to Instance, Engine,
  Coordinator, History Store, Dispatch, Worker transport, timers, lifecycle,
  identifiers, and process reconstruction. Classify each as controlled,
  intentionally external, or a blocker to deterministic replay.
- Map every durable and irreversible boundary, including before/after append,
  transaction commit, Activity request, external execution, terminal freeze,
  deterministic projection, delivery acknowledgement, close/reset, and
  quarantine.
- Freeze the initial safety properties, fair-environment liveness condition,
  fault taxonomy, event taxonomy, resource bounds, failure dispositions, and
  semantic-coverage vocabulary.
- Specify a versioned strict-data scenario and replay artifact. It records the
  expanded schedule and faults as well as seed, commit, runtime/dependency
  identity, property, and shrink lineage.
- Decide where a project-level **complex-system correctness sketch** belongs
  in Ariad/Petrus guidance. The routed guidance must require, only for durable,
  concurrent, stateful, or externally effectful work:
  - authoritative state;
  - safety invariants;
  - liveness assumptions;
  - explicit bounds and overflow/backpressure behavior;
  - nondeterministic inputs;
  - consequential crash cuts; and
  - an independent checker/model or the reason one is impractical.
- Route future Drivers from a concise conditional AGENTS/development-guide rule
  to one focused DST owner. Do not paste Tiger Style or a second delivery
  lifecycle into every session.
- Name Python-specific invariant policy: production correctness must not depend
  on removable `assert` statements, while test-only assertions and Hypothesis
  invariants remain appropriate.

## Acceptance / Done condition

1. A future Driver can identify exactly what is simulated, what remains real,
   and which production seams the harness will exercise.
2. Safety and liveness claims are executable in shape and distinguish permanent
   external waits from runtime livelock.
3. Every initial event and fault kind has a bound, a disposition, and a replay
   representation; no phrase such as “randomly crash things” substitutes for a
   contract.
4. The scenario schema can represent a known Petrus crash/recovery regression
   without serializing closures, credentials, clients, or live runtime objects.
5. Project guidance is concise, conditionally routed, and consistent with
   Ariad's progressive retrieval and current Petrus verification contract.
6. Existing `implementation-free-v1` simulation ownership and compatibility
   are explicitly preserved.

## Driver QA and evidence plan

- Trace the contract against representative replay, timer, Activity,
  lifecycle, JSONL/SQLite/PostgreSQL, Local/Absurd, and transport tests.
- Encode at least one existing crash-window test as a proposed scenario fixture
  and demonstrate that every required fact fits the schema.
- Review the inventory for direct wall-clock, randomness, UUID, sleep, task
  scheduling, and provider calls that bypass an owned seam.
- Run documentation/coherence checks and the smallest relevant existing tests;
  this story does not claim a working simulator.

## Out of scope

- Implementing the event scheduler or faulting adapters.
- Expanding the public hosted-simulation profile.
- Declaring every test deterministic merely because pytest order is fixed.
- Global user AGENTS.md changes.
