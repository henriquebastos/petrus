---
status: Decided
raised: 2026-07-28
decided: 2026-07-28
deciders:
  - Navigator
related:
  - CV8.DS3
---

# Async Workers isolate synchronous custody by stable provider lane

> **Current scope:** CV8.DS4 retains this decision for the synchronous
> compatibility bridge. Native async providers use the private event-loop-owned
> custody path recorded in
> `2026-07-28T1907Z-async-worker-custody-stays-private.md`; DS4 also removed the
> temporary application-specific DrivingPolicy described in the review notes
> below.

## Decision

An AsyncWorker owns a fixed positive number of lanes. Each lane constructs and
uses one WorkerDispatch provider exclusively on one private stable thread,
while admitted user Activities execute as coroutines on the AsyncWorker's one
event loop. A lane admits at most one Attempt at a time.

## Rationale

WorkerDispatch providers are synchronous and may contain connection-local,
thread-sensitive reconnect and fencing state. A generic shared executor could
move successive calls or provider construction between threads and prefetch
custody beyond executable capacity. Stable lane ownership preserves the
provider contract while allowing genuine async I/O concurrency without
offloading user code.

## Consequences

Provider factories, all calls, and close must stay on their lane threads.
Readiness follows successful initialization of every lane. Startup or idle-lane
failure stops global admission, drains already admitted work, closes initialized
providers, and then surfaces the first relevant failure after attempting every
cleanup. Caller cancellation stops admission but does not cancel admitted user
Activities; a claim already executing may still return custody and must execute
and terminalize before close. Heartbeat and terminal reporting serialize per
Attempt context, while separate lanes remain independent. This does not
introduce remote cancellation, automatic heartbeat, or Worker supervision.
Startup cancellation is likewise cleanup-safe: readiness is shielded, every
already-started factory settles, and every successfully initialized provider is
closed on its owner thread before cancellation surfaces. A synchronous factory
itself remains uninterruptible. A user Activity's `CancelledError` is a terminal
Activity failure (converted to a provider-compatible error), not an abandoned
claim.

The initial implementation was rejected by independent Oracle review because
classification excluded context-aware low-level async callables, cancellation
could strand custody, heartbeat/close raced, terminal refusal was swallowed,
and provider qualification lacked real mixed arrangements. Oracle follow-up
then returned **CHANGE REQUIRED** for startup cancellation, user-coroutine
cancellation, and application ordering implemented through a sidecar marker.
The remediation closes the runtime paths and moves application ordering into
its public-Snapshot DrivingPolicy. A final lane-race pass also made partial
thread-start cleanup incremental and marks queued provider calls running before
execution so cancellation cannot race settlement and kill the owner lane. The
final independent review returned GO.
