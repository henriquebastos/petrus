---
status: Superseded
raised: 2026-07-10
decided: 2026-07-10
deciders:
  - henrique (Navigator)
supersedes:
superseded_by: docs/project/decisions/records/2026-07-14T1805Z-handler-invocation-runtime-seam.md
related:
  - docs/project/decisions/records/2026-06-21T1417Z-hermes-adr-0012-separate-net-runtime-from-execution-runtime.md
---

# The execution-runtime seam: durable firing attempts driven by a Runner

## Question

ADR 0012 ratified that the **net runtime** (semantics, state) is separate from the
**execution runtime** (running handlers). What concrete seam realizes that split — how a
firing is driven, where side-effecting execution plugs in, and how time and failure are
handled — without the net owning execution policy?

## Decision

A firing is a **durable attempt** with a begin/end lifecycle on `NetInstance`, driven by
a `Runner` over a pluggable seam (slice 10, delivered as 10a→10b→10c):

- **`begin` / `complete` / `fail` + `in_flight`** on `NetInstance`. `begin(binding, at)`
  opens a `FiringAttempt` with an id carried on every firing record; `complete` mints the
  end records; `fail(attempt, error)` records a terminal `FiringFailed` — **no token
  restore, no retry** (retry/timeout/compensation are execution-runtime policy).
  Quiescence gains an in-flight leg.
- **`ExecutionRuntime` is a callable seam** `(FiringAttempt, Handler, outputs) -> result`,
  default `inline` (run the handler here, now, synchronously). Retries live *inside* an
  `ExecutionRuntime` implementation, invisible to the net.
- **`Clock` is a two-method protocol** (`now` / `wait_until`); the only shipped clock is
  `SimulatedClock` (no wall clock — a real substrate's concern). Time never travels
  backward (the single writer clamps).
- **`Runner`** drives: schedule a candidate (the `scheduler` is the *driver's* policy,
  never the net's) → `begin` → execute on the `ExecutionRuntime` → commit `complete`/
  `fail`; on nothing-enabled-but-maturation-pending it waits on the `Clock` and `wake`s.
  **Halt-on-terminal-failure is structural** — no policy knob until a second policy
  exists.
- **Handler-driven registration lifecycle** (10b) rides the observed `HandlerResult`
  (opens/closes), so the net's boundary with the world is handler-controllable.

The Navigator pre-authorized the 10c design forks in-tab ("go with your recommendation
to the end"); the shapes above are those rulings.

## Why

The seam keeps net semantics pure and durable while letting substrates (local now;
subprocess / queue / Temporal / durable-execution later) own *how* work runs. A firing
as a durable attempt with a stable identity is the precondition for crash-resume,
observability, and — later — distribution: a real substrate retries and leases however it
likes; only the terminal result or failure reaches the net.

## Consequences

- Foundation for the persistence seam (crash-resume rebuilds in-flight attempts) and the
  interleave seam (the Runner's `Sensor`), both delivered consumer-first from `es8`.
- Concurrent/async execution is deliberately deferred (debts `2330Z`, `2110Z` carry the
  distribution question); the seam is designed so an async `ExecutionRuntime` lands
  additively.
- The concrete lens-panel + codex-verified rulings and the slice ledger live in the
  worklog entries for slices 10a/10b/10c and the seam-complete milestone; the distilled
  principles in `engineering-conventions.md`.
