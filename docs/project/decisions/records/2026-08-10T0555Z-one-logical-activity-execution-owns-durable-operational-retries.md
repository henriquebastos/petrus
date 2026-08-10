---
status: Decided
raised: 2026-08-10
decided: 2026-08-10
deciders:
  - henrique (Navigator)
supersedes:
related:
  - CV8.DS5
  - docs/project/decisions/records/2026-07-14T2016Z-activity-invocation-runtime-seam.md
  - docs/project/decisions/records/2026-07-28T1052Z-local-dispatch-and-worker-provider-boundary.md
---

# One logical Activity execution owns durable operational retries

## Question

How should Motus retry one logical Activity without requiring application Petri
topology for operational failure handling, while preserving canonical History,
deterministic projection, and provider neutrality?

## Decision

One immutable `ActivityInvocation` is one logical execution. Its correlation
and idempotency identities remain stable across every operational Attempt.
`ExecutionPolicy` freezes a conservative one-Attempt default and may opt into a
bounded deterministic retry policy (`initial_interval`, `coefficient`,
`max_interval`, and `attempts`), a per-Attempt `start_to_close`, and an
aggregate `schedule_to_close`. Jitter remains exactly zero until a deterministic
model is demonstrated. Heartbeat timeout remains a renewable liveness lease;
it does not extend either hard deadline. Every duration is bounded at
1,000,000,000 seconds so an accepted policy remains representable across the
provider-neutral millisecond and datetime contracts.

An Activity may raise `ActivityError` to report a safe durable
`ActivityFailure`: bounded `error`, provider-neutral `kind`, JSON-faithful
`details`, `retryable`, and optional `retry_after`. Unclassified execution
exceptions are retryable operational failures. Retryability describes the
failure; the frozen policy separately decides whether another Attempt remains.

Dispatch durably schedules eligible delayed Attempts. Inline Dispatch retries
immediately and never sleeps; it is not a durable timing provider. Local
Dispatch persists scheduling and deadline fences. The pinned Durable Dispatch
provider implements bounded retry scheduling but refuses exact start-to-close
and schedule-to-close policies it cannot enforce soundly. Operational Attempt
failures, timing, claims, and custody remain outside canonical History.

When Dispatch reports a terminal failure, Instance first appends one
`ActivityFailed` fact with the classified safe details. Only then does it run
deterministic projection or preserve legacy fail-and-halt behavior. A handler
opts into failure projection with `project_failure(binding, failure)`; absent
that method, the occurrence appends `FiringFailed` and the runtime halts as
before. Reload after a crash between these boundaries resumes projection (or
the legacy halt boundary) from the frozen failure and never dispatches another
Attempt. Identical terminal redelivery is acknowledged; a conflicting result
or failure is rejected.

## Rationale

Application Petri topology should model business progression, not queue retry
machinery. A stable logical instruction plus durable provider-owned scheduling
allows transient execution failures to recover without minting new business
identity or polluting canonical History with custody topology. Freezing terminal
failure before deterministic projection gives failure the same side-effect
safety boundary already established for successful completion.

## Options Considered

- **Application retry transitions.** Rejected for operational failures because
  they expose provider attempts as business topology and mint new logical
  invocations unless every application rebuilds the same correlation rules.
- **Unlimited retries by default.** Rejected; one Attempt remains the safe
  compatibility default.
- **Sleeping inside Inline Dispatch.** Rejected; delayed retry requires durable
  custody and must survive process loss.
- **Random jitter.** Deferred because replay-safe deterministic semantics have
  not been established.
- **Project every terminal failure.** Rejected as a compatibility break;
  projection is explicit opt-in.

## Consequences

- Applications own authority/currentness, desired-state supersession,
  lookup-before-retry recovery for external providers, and reconciliation of
  ambiguous side effects. Stable idempotency supports those duties but does not
  promise exactly-once effects.
- Dispatch schemas and transports must preserve the complete invocation and
  classified terminal value. Local Dispatch automatically migrates its exact
  v1 schema to v2 transactionally.
- Failure projectors must be deterministic and side-effect-free because reload
  may execute projection again from the frozen fact.
- Cancellation, child/local Activity abstractions, and nested durable call
  stacks remain out of scope.

## Review Trigger

Revisit when a provider can soundly enforce exact deadlines now refused, when
deterministic jitter is required, or when cancellation becomes necessary for a
bounded correctness contract rather than operational convenience.
