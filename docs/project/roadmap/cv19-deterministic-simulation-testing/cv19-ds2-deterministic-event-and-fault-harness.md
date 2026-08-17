---
code: CV19.DS2
level: Delivery Story
status: Planned
status_reason: Production Engine and Coordinator logic do not yet run under one seeded logical event-and-fault scheduler
updated: 2026-08-17
related:
  - index.md
  - cv19-ds1-correctness-and-simulation-contract.md
---

# CV19.DS2 — Deterministic event and fault harness

## Intent

Run production Petrus semantic and recovery logic under one bounded,
single-process scheduler that controls every simulated event and can reconstruct
a crashed process from retained durable state.

## Scope

- Introduce a test-owned deterministic event queue ordered by logical instant
  and explicit stable tie-breaker. The harness advances directly to the next
  event; no simulated path sleeps on wall time.
- Give the harness explicit seeded authorities for workload choices, fault
  choices, generated identifiers, and event ordering. Keep these streams
  separable enough that adding observability does not silently alter every
  choice.
- Drive the production Engine/Coordinator doors for:
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
- Serialize every expanded run and replay it without consulting the PRNG.

## Acceptance / Done condition

1. Replaying the same expanded scenario at the same commit produces the same
   accepted History, snapshots, checker observations, terminal disposition,
   and failure location.
2. Two fresh seeded runs with the same profile produce the same expanded
   scenario, while replay remains authoritative if future code changes PRNG
   consumption.
3. A process crash discards all declared volatile objects and resumes only
   through production load/reconcile paths; the test cannot retain a hidden
   live Instance or Coordinator.
4. Faults can target named semantic cuts before and after durable acceptance,
   not arbitrary implementation line numbers.
5. Every run is bounded by events, logical time, retained data, pending work,
   and wall-clock test budget, and reports which bound ended it.
6. The harness runs without credentials, real providers, network sleeps, or a
   second implementation of Petrus semantics.
7. Existing simulation, unit, integration, full, and release gates remain green.

## Driver QA and evidence plan

- Begin with one vertical scenario spanning delivery → Activity request →
  terminal freeze → projection crash → process reconstruction → projection-only
  completion.
- Add one lifecycle race and one timer/retry scenario only after the vertical
  slice proves deterministic replay.
- Deliberately perturb observation/logging and verify expanded replay does not
  depend on additional PRNG draws.
- Execute focused replay tests, related recovery suites, `scripts/check full`,
  and `scripts/check release`.

## Out of scope

- Broad random workload generation and shrinking; DS3 owns it.
- Fidelity claims for real databases, kernels, sockets, or hardware.
- Simulated arbitrary byte corruption before a concrete Petrus property and
  adapter contract justify it.
- Public API stability for harness internals.
