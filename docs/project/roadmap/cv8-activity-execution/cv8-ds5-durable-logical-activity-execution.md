---
code: CV8.DS5
level: Delivery Story
status: Done
status_reason: One provider-neutral logical Activity now owns bounded durable retries, deadlines, classified terminal failure, and projection-only recovery
updated: 2026-08-10
related:
  - docs/project/decisions/records/2026-08-10T0555Z-one-logical-activity-execution-owns-durable-operational-retries.md
  - docs/project/decisions/records/2026-07-14T2016Z-activity-invocation-runtime-seam.md
---

# Durable logical Activity execution

## Intent

Let applications remove Petri retry topology for operational Activity failures
without changing business identity, canonical History ownership, or provider
placement.

## Scope

- Keep one stable invocation, correlation, and idempotency identity across
  bounded Attempts.
- Carry classified safe failure metadata and provider retry-after guidance.
- Schedule deterministic retry/backoff durably in Local and Durable Dispatch;
  keep Inline immediate and non-durable.
- Fence renewable heartbeat leases with optional per-Attempt and aggregate
  deadlines where the provider can enforce them soundly.
- Freeze terminal failure before opt-in deterministic projection or legacy
  fail-and-halt, and recover projection-only after restart.
- Preserve canonical History independently of queue, lease, and Attempt
  topology.

## Acceptance / Done Condition

1. Retryable failures followed by success use one unchanged invocation and
   stable application identities.
2. Non-retryable failure terminalizes immediately and may project a typed,
   deterministic net outcome through explicit handler opt-in.
3. Delayed retry state and terminal-failure projection survive process restart
   without another logical invocation or repeated external execution.
4. Attempt and aggregate deadlines fence stale terminal reports while
   heartbeat checkpoints remain renewable within the hard deadline.
5. Identical terminal reports acknowledge and conflicting reports fail across
   Local and Durable Dispatch.
6. Legacy one-Attempt and fail-and-halt behavior remains the default.

## Driver QA and Evidence Plan

Focused Motus, Engine, transport, migration, and real pinned Durable Dispatch
tests cover retry/success, restart scheduling, deadline exhaustion,
duplicate/conflicting reports, classified failure, and projection crash/reload.
The complete `scripts/check full` and `scripts/check release` gates qualify the
coherent result.

## Out of Scope

- Application authority/currentness and desired-state supersession.
- External provider lookup-first recovery and exactly-once side effects.
- Cancellation, child/local Activities, nested durable calls, and unlimited
  default retries.

## Notes

Local Dispatch migrates its exact v1 SQLite schema to v2 on open. The pinned
Durable Dispatch provider refuses `start_to_close` and `schedule_to_close`
rather than claim deadline semantics it cannot enforce. Inline Dispatch never
blocks for backoff and offers no durable timing guarantee.
