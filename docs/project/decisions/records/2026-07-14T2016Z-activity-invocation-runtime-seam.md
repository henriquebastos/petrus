---
status: Decided
raised: 2026-07-14
decided: 2026-07-14
deciders:
  - henrique (Navigator)
supersedes:
  - docs/project/decisions/records/2026-07-14T1805Z-handler-invocation-runtime-seam.md
related:
  - docs/project/decisions/records/2026-07-14T1421Z-delivery-registration-terminology.md
---

# Dispatch Petri-agnostic activity invocations from server-side handlers

> **Amended by DEC-036 on 2026-07-22:** Worker capability vocabulary and
> required-capability fields are superseded. Activity requests retain typed
> business input, execution policy, correlation, and idempotency, while the
> live Engine routes them through operational default/per-Activity queues.
> Workers subscribe to queues and register Activities; DevOps provisions their
> resources and authority. See
> `2026-07-22T1539Z-engine-routes-activities-through-operational-queues.md`.

## Question

What crosses the execution-adapter seam, which lifecycle facts belong in
canonical history, and how can workers remain ignorant of Petri-net state?

## Decision

A handler is the server-side, Petri-aware bridge between a firing occurrence
and ordinary imperative work. An activity is the Petri-agnostic callable a
worker executes. Initially, one impure handler maps to exactly one activity:

```text
CandidateSelected
  → handler prepares ActivityInvocation from the candidate binding
  → NetInstance atomically commits FiringBegun, input accounting,
    and ActivityRequested
  → execution adapter dispatches it
  → worker executes Activity
  → ActivityCompleted is committed
  → handler projects the frozen result
  → token and delivery-registration effects are committed
  → FiringCompleted
```

The durable occurrence preserves the exact consumed and read selections the
handler observed. From that snapshot, the handler prepares an immutable
activity invocation carrying only typed activity input, resolved execution
policy, correlation identity, idempotency identity, and required capabilities.
It never grants the worker access to a live `NetInstance`, marking, history,
topology, token selection, or output-arc contract.

`ActivityRequested`, `ActivityCompleted`, and `ActivityFailed` are canonical
process facts. Queue publication, scheduling eligibility, claims, leases,
heartbeats, and operational `ActivityAttempt`s belong to the execution
adapter. That operational state may use durable storage, but it is
reconstructible machinery rather than canonical net truth.

`ActivityRequested` is committed in the firing's begin batch before dispatch
and acts as the authoritative outbox. `ActivityCompleted` is committed before
deterministic handler
projection. Token production, delivery-registration opens/closes, and
`FiringCompleted` then form the atomic net-effects boundary. There is no
separate durable `HandlerResultProduced` or `HandlerCompleted` lifecycle.

If the activity returns a typed business result, including a provider decline,
the activity completed successfully and the handler projects that result into
the net. If the execution adapter exhausts its retry or reconciliation policy,
it reports `ActivityFailed`; the occurrence records `FiringFailed` and the run
stops. Infrastructure failure is not converted into a business token.

## Rationale

Workers should execute ordinary imperative code and should not understand
Petri-net tokens, arcs, registrations, or history. Keeping the handler on the
server preserves that boundary while retaining a typed bridge between the net
and activity input/output.

Committing the request before dispatch closes the crash window between
reserving the firing and publishing work. Committing the activity result before
projection prevents a handler bug or server crash from repeating a completed
external side effect: after a fix and redeploy, projection resumes from the
frozen result.

One activity may have several operational attempts. Those attempts retain the
same activity-invocation identity and provider idempotency key. A new business
attempt creates a new activity invocation and idempotency key while it may keep
the broader correlation identifier of the same payment order or process.

## Options Considered

- **Worker executes the handler.** Superseded because it exposes Petri-aware
  boundary concepts to the worker and makes deployment depend on net code.
- **Handler prepares and projects one activity — chosen.** Keeps workers
  imperative and the net boundary explicit without adding a durable call stack.
- **Several durable activities inside one handler.** Deferred. A durable
  sequence is initially modeled as transitions separated by intermediate
  places, so the marking is its continuation.
- **Record handler completion as a third lifecycle.** Rejected as redundant.
  Activity records freeze external work; movement/effect records and the firing
  boundary already freeze the handler's deterministic projection.
- **Treat exhausted execution failure as a business result.** Rejected. Net
  routing requires a typed activity result; infrastructure failure stops the
  firing and run.

## Consequences

- CV3 needs asynchronous activity request/result ingress while serializing
  mutation of each `NetInstance` through one writer.
- Preparing and later projecting an activity needs the complete immutable
  firing binding in server-side history. The carried debt for recording and
  validating read selections is therefore on CV3's path.
- An inline adapter may execute the same activity invocation directly; a
  distributed adapter may queue and lease it without changing semantics.
- Workers advertise activity implementations and capabilities rather than net
  definitions. A self-contained process package may still colocate topology,
  handlers, activity declarations/implementations, and default policies; a
  worker imports only the activity implementations it serves.
- Process/activity configuration supplies semantic execution policy. Worker
  configuration supplies capacity, concurrency, polling, and resource
  placement. The resolved policy travels with the activity invocation. When
  the author declares no policy, resolution applies the maximally
  conservative default — one attempt, an exception is terminal — rather than
  rejecting the process definition.
- The handler declaration address identifies where the net requests behavior;
  a concrete activity binding identifies which implementation fulfills it;
  the firing/activity invocation identifies this occurrence; correlation
  identifies the broader business operation.
- Existing synchronous `HandlerResult` APIs and serialized history records are
  compatibility surface until a deliberate CV3/schema migration.

## Deferred

- Handler-projection versioning and audited code correction.
- Dynamic net mutation and migration of in-flight runs.
- Precise reset, branch, or restart-from-history mechanics after `FiringFailed`.
- A broader URI family for activity declarations and runtime bindings.
- Multi-activity handlers and any durable nested call stack.

For CV3, if projection fails after `ActivityCompleted`, fix the code, add a
regression test, redeploy, and retry only deterministic projection from the
frozen result. The activity is not invoked again.

## Review Trigger

The CV3 activity-dispatch slice, the next event-history schema migration, or a
demonstrated need for several independently recoverable activities inside one
transition.
