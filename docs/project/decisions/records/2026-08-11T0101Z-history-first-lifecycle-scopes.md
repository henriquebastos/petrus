---
status: Decided
raised: 2026-08-11
decided: 2026-08-11
deciders:
  - Hamsterdan Navigator approval, adopted under Petrus checkpoint policy
related:
  - ES-051
  - CV8.DS6
  - docs/project/decisions/records/2026-08-10T0555Z-one-logical-activity-execution-owns-durable-operational-retries.md
  - docs/project/decisions/records/2026-08-10T1200Z-instance-identity-scopes-shared-activity-resolution.md
---

# History-first lifecycle scopes

## Question

How can Petrus close and reset a durable generation of queued and executing
work while preserving canonical History, deterministic replay, and the
provider-neutral separation between business truth and operational custody?

## Decision

A lifecycle scope is the immutable durable value `(name, generation)`. The
Instance records scope open, close, and reset facts in canonical History.
Reset is one atomic semantic operation that closes generation N, performs the
same exact cleanup as close, and opens N+1 without an unscoped gap.

Every queued token has a durable occurrence identity and optional lifecycle
scope provenance. Consumed and read movements name exact queue occurrences;
produced occurrences inherit the firing's scope. A firing may combine
unscoped inputs with one scope, but Petrus refuses a binding that combines
different lifecycle scopes rather than guessing which generation owns its
work. `ActivityRequested` carries the same scope.

Close/reset records name the exact queued occurrences discarded and firing
occurrences cancelled. Already-consumed firing inputs stay consumed. Petrus
does not restore them implicitly; a domain that requires compensation models
an explicit compensating operation.

Canonical append order alone decides close/completion races, including equal
instants. A terminal Activity fact appended before close is accepted and its
deterministic projection is completed before close cleanup. A terminal report
after close is recorded in durable quarantine and cannot alter the closed
generation. Exact accepted or quarantined redelivery is acknowledged without a
second fact; conflicting redelivery fails loudly.

Scope close/reset commits before any cancellation instruction becomes visible
to Dispatch. The committed close/reset fact is also the recoverable outbox:
Engine reconciliation reapplies its cancellation instructions after restart.
Dispatch fences pending, claimed, and running custody and records an explicit
cancelled disposition. This fence prevents future accepted execution or
terminal mutation where the provider can prove that boundary; it never claims
that an ambiguous external effect did not occur and does not promise hard
interruption.

Scoped source delivery extends the existing canonical identity door. An exact
active generation is accepted normally. An exact closed generation is
canonically acknowledged and dropped. A delivery naming a scope but not a
provable generation is canonically quarantined, never reinterpreted as the
current generation. External provider and webhook custody remain host code.

Unscoped Engine, History, Dispatch, Worker, and source-delivery behavior stays
the default. Scope generation does not replace same-generation operation
ownership, authority epochs, publication identity, or domain supersession.
The host remains the multi-Instance scheduler.

## Rationale

Only canonical History can provide one replayable ordering for scope lifecycle,
terminal reports, and token movement. Durable occurrence identity closes the
duplicate-value ambiguity at its source. Making close/reset the cancellation
outbox prevents an operational action from getting ahead of business truth and
turns a crash after commit into ordinary reconciliation.

The design adds one constrained value and explicit records rather than an
actor/module runtime or capability container. Dispatch remains responsible for
claims, leases, and fences because those are operational custody, not Petri
business facts.

## Options Considered

- **Copy or merge the disposable scope runtime.** Rejected; it deliberately
  bypassed production ownership seams.
- **Attach scope only to token values.** Rejected; duplicate values cannot be
  cleaned exactly or replayed safely.
- **Use `ActivityFailed` / `FiringFailed` for cancellation.** Rejected;
  exhausted execution and lifecycle cancellation are different terminal
  causes.
- **Cancel before append.** Rejected; append refusal would make Dispatch state
  contradict replay truth.
- **Restore consumed inputs.** Rejected; only explicit domain compensation can
  honestly account for accepted work.
- **Require PostgreSQL or add a Petrus scheduler.** Rejected; Local remains
  first-class and hosting many Instances remains an application concern.

## Consequences

- Canonical records without lifecycle or queue-entry provenance preserve the
  public schema-4 encoding. Lifecycle/provenance records use schema 5. The
  codec reads both, requires the one canonical spelling for each record, and
  permits mixed-version records in one append-ordered History without a
  log-wide migration.
- Local Dispatch migrates its own SQLite schema from 2 to 3 transactionally by
  adding durable cancellation tombstones. This is an operational custody
  migration, independent of the canonical History record schema.
- Pinned Absurd behavior is qualified only to the cancellation/tombstone fence
  it actually provides. Petrus uses Absurd's existing durable task tombstones
  without forking the pinned Absurd schema; unsupported stronger semantics are
  refused. Absurd may eventually clean cancelled provider tasks, so operators
  align retention with their recovery window; canonical repair can rematerialize
  and cancel absent custody, but an Absurd worker terminal after cancellation
  is stale and is not available for canonical quarantine.
- Scope-aware callers retain the exact scope returned by `open_scope` or
  `reset_scope` and supply it on ingress. A bare name means generation is
  uncertain and therefore quarantined.
- An accepted Activity terminal awaiting deterministic projection must finish
  projection before its generation closes or resets. Quarantine is an audit
  fact, not a generic reprocessing queue; release or compensation is explicit
  application reconciliation.
- Applications retain stable external idempotency, lookup-first reconciliation,
  business ownership, and explicit compensation responsibilities.

## Review Trigger

Revisit if a real workflow needs a firing to combine multiple lifecycle scopes,
if a provider can prove stronger cooperative interruption semantics, or if a
second safe durable scope dimension is demonstrated.
