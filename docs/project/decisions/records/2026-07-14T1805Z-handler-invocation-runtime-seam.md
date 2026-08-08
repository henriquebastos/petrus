---
status: Superseded
raised: 2026-07-14
decided: 2026-07-14
deciders:
  - henrique (Navigator)
supersedes:
  - docs/project/decisions/records/2026-07-10T0400Z-execution-runtime-seam-durable-attempts.md
related:
  - docs/project/decisions/records/2026-07-14T2016Z-activity-invocation-runtime-seam.md
  - docs/project/decisions/records/2026-06-21T1417Z-hermes-adr-0012-separate-net-runtime-from-execution-runtime.md
  - docs/project/decisions/records/2026-07-10T0400Z-execution-runtime-seam-durable-attempts.md
---

# Execute stable handler invocations without a durable call stack

> Superseded later in the same Session 3 discussion by
> [the activity-invocation runtime seam](2026-07-14T2016Z-activity-invocation-runtime-seam.md).
> The durable-continuation and no-multi-activity conclusions remain, but a
> worker executes a Petri-agnostic activity rather than a Petri-aware handler.

## Question

What logical unit crosses the execution-runtime seam, how does it relate to
operational retries, and how much hidden orchestration may live inside one
handled transition?

## Decision

Adopt this vocabulary and boundary for the next execution-runtime design:

- A **firing occurrence** is one durable semantic begin-to-terminal lifecycle.
- A **firing outcome** is its completed semantic result.
- One firing occurrence produces one stable **handler invocation**.
- An execution adapter may make multiple **handler attempts** to execute that
  invocation without creating another firing occurrence.
- A **handler result** returns output tokens and delivery-registration effects
  for `NetInstance` to validate and commit atomically.

A handler may perform pure preparation and result mapping, but initially
contains at most one independently recoverable impure operation. Recovery must
be safe through a stable idempotency key or reconciliation-before-reinvocation.
When durable work requires side effect A followed by side effect B, express the
sequence as two transitions with an intermediate place.

Do not build a durable call stack or nested activity history beneath a firing
occurrence now. Multi-activity handlers remain deferred.

The runner is an invariant-preserving coordinator over a small action
vocabulary. Driving policies may compose admission, priority, scheduling,
fairness, limits, and tie-breaking, but cannot mutate a `NetInstance` directly.
Execution adapters own dispatch, leases, operational retries, reconciliation,
and worker placement; they never own canonical net history.

## Rationale

`FiringAttempt` became misleading once the design distinguished a semantic
firing lifecycle from the several operational tries needed to execute it.
`FiringOccurrence` does not imply that code is currently running.
`HandlerInvocation` names the stable instruction more precisely than generic
`WorkEnvelope` and pairs naturally with the existing `HandlerResult`.

Explicit intermediate places give Impetus its own durable continuation. They
make completed side effects visible in the marking and allow recovery to resume
at the next transition without serializing a coroutine frame. Temporal can put
multiple activities inside workflow code because its activity history supplies
those inner checkpoints; importing that facility now would create another
orchestration runtime beneath the net.

Local and remote execution remain one model. An inline adapter directly invokes
the registered handler; a queue adapter transports the same logical invocation.
The stable occurrence identity closes the crash window between history append
and queue publication because recovery can derive and redispatch the invocation.

## Options Considered

- **Firing occurrence — chosen.** Semantic and neutral about whether execution
  is currently active.
- **Firing execution.** Rejected because it implies running code.
- **Firing lifecycle / operation / transaction.** Rejected as respectively a
  shape rather than an identity, overly generic, or transactionally misleading.
- **Work envelope.** Rejected because it does not say what work is requested and
  suggests a handler may prepare another execution unit.
- **Handler invocation — chosen.** Names the stable request independent of
  inline, queue, or RPC transport.
- **Multiple durable activities inside one handler.** Deferred; valuable for
  non-idempotent legacy sequences, but requires durable intermediate activity
  state beneath the firing occurrence.

## Consequences

- CV3 must separate dispatch acknowledgement from later terminal result ingress
  and allow other eligible work to proceed while occurrences remain in flight.
- Resume must reconcile or redispatch open handler invocations using their
  stable identity.
- The first committed terminal result wins. Identical result redelivery is
  acknowledged idempotently; a different late result is an operational conflict.
- Worker/provider time is evidence only. The single writer stamps canonical
  history and advances the watermark.
- Existing `FiringAttempt` / `Firing` code and serialized record fields remain
  unchanged until a deliberate schema-version migration.
- `FiringFailed` remains the simple explicit terminal mechanism for now;
  suspension, abandonment, and audited manual resolution are later refinements.

## Review Trigger

Historical record only. Follow the superseding activity-invocation decision.
