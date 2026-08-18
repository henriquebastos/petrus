---
status: Decided
raised: 2026-08-18
decided: 2026-08-18
deciders:
  - henrique (Navigator)
supersedes:
related:
  - CV19.DS2
  - 2026-07-28T1052Z-local-dispatch-and-worker-provider-boundary.md
  - ../../roadmap/cv19-deterministic-simulation-testing/cv19-ds2-deterministic-event-and-fault-harness.md
  - ../../../process/dst-world-v3.md
---

# LocalDispatch accepts an explicit provider clock without yielding SQLite authority

## Question

How can a deterministic host exercise delayed LocalDispatch retries and lease
boundaries without sleeping, changing private custody rows, substituting the
Engine clock, changing schema version 3, or weakening SQLite's serialization
ownership?

## Decision

`LocalDispatch` and `LocalWorkerDispatch` accept an optional
`LocalDispatchClock.now_ms()` provider-time contract. Omitting it retains the
existing SQLite `strftime('now')` read exactly. Supplying it changes only the
source of provider milliseconds; SQLite still owns custody, transactions,
claims, fences, retry calculations, and serialization.

Each operation samples provider time once inside its existing SQLite
transaction. `LocalDispatch.worker()` propagates the same clock and monotonicity
guard. Values must be exact nonnegative signed-64-bit millisecond integers and
must not rewind within the composed provider session. Schema and durable rows
do not encode a clock implementation or test identity.

This contract is distinct from the Engine `Clock`: Engine time remains a
semantic watermark, while LocalDispatch time governs operational custody. A
DST profile may adapt the World instant to both public contracts explicitly,
but neither production component imports or knows the World.

## Rationale

Delayed retry availability is production LocalDispatch behavior and must be
decided by its real SQL predicates. A narrow provider-time input lets an outer
host control that nondeterminism while leaving the provider's state and
decision ownership intact. Sampling under the same transaction preserves the
relationship between observed time and the custody decision it authorizes.

The optional keyword is backward compatible, and the default remains the
locally appropriate SQLite clock. A separate delayed-retry DST profile and
identity preserve every retained zero-backoff profile/artifact unchanged.

## Options Considered

- **Optional LocalDispatch provider clock — chosen.** It controls one true
  nondeterministic input at its owner without changing custody semantics.
- **Reuse Engine `Clock`.** Rejected because semantic watermark time and
  operational lease/retry time have different ownership and units.
- **Edit `available_at` or deadlines in tests.** Rejected because private row
  mutation bypasses the production scheduling calculation being tested.
- **Sleep until retry availability.** Rejected because wall time is slow,
  nondeterministic, and cannot produce strict logical replay.
- **Move retry scheduling into the generic DST World.** Rejected because that
  would create a second implementation of LocalDispatch policy.
- **Change the SQLite schema to persist clock metadata.** Rejected because no
  durable compatibility change is needed to supply process-local provider
  time.

## Consequences

- Controlled hosts may advance LocalDispatch retry and lease time directly;
  ordinary callers retain the prior SQLite-time behavior.
- Worker providers constructed through `LocalDispatch.worker()` share the
  dispatch session's clock guard; directly constructed providers validate
  their own observed sequence.
- Tests and profiles still claim only the provider operations and time ranges
  they execute. This seam does not make SQLite, process scheduling, or external
  effects generally deterministic.
- Existing `petrus-dst-world` schemas, zero-backoff profile identity, and
  retained artifacts remain unchanged. The delayed-retry profile receives its
  own exact identity and retained version-3 artifact.

## Review Trigger

Revisit if a real non-SQLite provider needs the same clock contract, if
cross-process clock monotonicity must become durable, or if controlled
lease-expiry evidence cannot preserve transaction-local sampling.
