---
status: Decided
raised: 2026-07-21
decided: 2026-07-22
deciders:
  - henrique (Navigator)
supersedes:
  - ES-037's recommendation to adopt a generic Observation read plane now; that architecture remains optional future evidence, not production ontology
  - ES-037's initial split between Observation-owned progress and separately typed Dispatch checkpoints for the first production floor; one application-defined heartbeat-details value serves both purposes
related:
  - docs/project/decisions/records/2026-07-22T1816Z-dispatch-leases-attempts-devops-operates-workers.md
  - docs/project/decisions/records/2026-07-22T1539Z-engine-routes-activities-through-operational-queues.md
  - docs/project/decisions/records/2026-07-22T1031Z-instance-authors-terminal-history-and-shared-firing-transform.md
---

# Dispatch snapshots heartbeat details; operational observation remains optional

## Question

What is the smallest production-capable observation model for long-running
Activity execution? Must Impetus adopt a generic Observation package, durable
event feed, progress schema, artifact protocol, cursor model, and joined UI
now, or can Dispatch expose its own Attempt state while an optional higher
operational layer is deferred? Should progress and recovery checkpoints be two
different protocols?

## Decision

Do **not** adopt `Observation` as production ontology or add an
`impetus.observation` package now. The initial production floor is the narrow
Dispatch-owned Attempt protocol approved by DEC-037. Dispatch owns Attempt
identity, active lease epoch and deadline, renewal, expiry, reassignment,
stale-epoch refusal, the latest accepted heartbeat details, and operational
terminal reports.

### Heartbeat details are one application-defined value

An Activity heartbeat renews custody for the active Attempt epoch and may
carry one optional **details** value. Details use the same JSON-faithful value
boundary as other Activity data: mappings with string keys, lists, strings,
numbers, booleans, and null. The application establishes the payload's shape
and meaning. A value may be:

- human-readable progress;
- recovery/checkpoint state;
- both progress and recovery state.

There is no Impetus-wide phase vocabulary, progress percentage schema,
checkpoint class, or mandatory schema registry. The Activity implementation
may include its own schema/version discriminator when compatibility requires
one. Dispatch snapshots and preserves the value without interpreting it.

For the active lease epoch, heartbeat acceptance and replacement of supplied
details are atomic. A heartbeat with no details renews custody without erasing
the last accepted value. Expired or superseded epochs cannot renew custody or
replace details. A replacement Attempt receives the latest accepted details
and its Activity implementation decides whether and how to resume from them.

Details are durable **operational** state because retry may depend on them.
They are not token data, an Activity result, or canonical History. They do not
prove an external effect happened and do not weaken the Activity developer's
idempotency and reconciliation responsibility. Large checkpoints, logs, model
files, media, or artifacts belong in an external application/provider store;
details may carry a small reference and integrity or version information.

Heartbeat cadence remains Activity behavior. The developer declares the
heartbeat timeout appropriate to the implementation; Engine resolves and
freezes the effective timeout in invocation execution policy. Activity code
heartbeats at meaningful progress boundaries or at a controlled interval when
one phase can run longer than the timeout. Details are optional: liveness does
not require a newly expressible progress value on every renewal.

This follows the useful part of Temporal's Activity heartbeat precedent:
custom heartbeat details describe application progress, the service retains
the latest delivered details, and a retry can continue from them. Impetus does
not thereby adopt Temporal's Workflow, cancellation, serialization, or
operational-control semantics.

### Observation remains an optional higher layer

A future operations/read-model service may join narrow owner-specific sources:

- provider or DevOps facts about deployments, processes, resources, and
  health;
- optional Worker boot/incarnation, queue, Activity-name, and build
  announcements;
- Dispatch Attempt, lease, latest-details, expiry, and terminal-report state;
- canonical per-Instance History positions; and
- logs and existing best-effort telemetry.

That service may later provide fleet inventory, subscriptions, reconnectable
cursors, retention, redaction, and provenance-aware UI joins. Those features
are not required for the Attempt floor and no generic envelope, global cursor,
store, package, or public compatibility surface is selected now. If built,
the layer must remain optional: its failure cannot stop execution, renew a
lease, accept an outcome, choose placement, operate infrastructure, or append
canonical History.

There is no total order across providers, Workers, Dispatch, telemetry, and
independent Instance histories. A future UI must preserve provenance and say
that a Worker or Dispatch **reported** an outcome until Instance has
**accepted** it at an exact History position.

Candidate Selection excluding every enabled Binding is initially an ordinary
operational diagnostic suitable for telemetry. It appends no canonical fact
merely because policy declined to act and does not require an Observation
platform.

### Cancellation is deferred

Do not add cancellation to the initial Attempt heartbeat story. Stopping a
Worker process remains DevOps/provider responsibility; abandoned custody is
handled by lease expiry. Invalidating an Attempt alone cannot settle what its
durable Instance should do and may merely cause redispatch.

True Activity-invocation cancellation requires a later Engine/Instance
semantic decision covering canonical representation, process policy,
Dispatch invalidation, cooperative delivery, and precedence against an
already reported or accepted terminal outcome. This ruling does not disguise
cancellation as `ActivityFailed`, add a History record, or decide that later
model.

## Rationale

DEC-037 already places all correctness-critical long-Activity state at
Dispatch. A second writer for progress or checkpoints would add protocol and
transaction boundaries without creating value. The Activity is the only
component that understands whether `42`, `{"last_segment": 42}`, or an object
store reference is useful status, resumable state, or both. One opaque latest
value keeps the contract small and supports replacement without making
Dispatch understand application schemas.

The current telemetry layer deliberately fails open and cannot be promoted to
custody or recovery state. Conversely, a generic durable Observation bus would
invent retention, ordering, privacy, and compatibility commitments before a
product surface needs them. Narrow owner reads leave room for a later joined UI
without making that UI a second truth.

## Options Considered

- **Promote telemetry into the product feed.** Rejected: its advisory,
  fail-open contract cannot own retry state, leases, or reconnect guarantees.
- **Adopt ES-037's generic federated Observation plane now.** Rejected for the
  current floor: the owner separation is useful evidence, but its envelope,
  cursor vectors, durable progress stream, retention, log/artifact, and UI
  contracts are premature.
- **Separate progress events and checkpoint objects.** Rejected initially:
  applications commonly use the same state for operator progress and retry
  continuation; separate protocols impose a distinction Dispatch cannot
  interpret.
- **Dispatch Attempt state with one latest heartbeat-details value — chosen.**
  It is the smallest model that supports healthy long execution, operator
  inspection, and retry continuation while preserving owner boundaries.

## Consequences

- CV6.TS5 remains the bounded implementation story. It must validate atomic
  renewal/details replacement, retry delivery of the latest JSON-faithful
  snapshot, no-details renewal, stale-epoch refusal, and unchanged canonical
  History.
- No production Observation package, Worker inventory, durable progress event
  stream, generic cursor, log/artifact protocol, or cancellation API is
  commissioned.
- A generic UI may display opaque details as JSON; an application-specific UI
  may understand its schema. Impetus does not promise a universal progress
  rendering.
- Storage limits and exact Activity-context API spelling belong to the CV6.TS5
  Plan Checkpoint. The contract requires a bounded small value and permits an
  external reference; it does not choose a blob limit in this record.
- ES-037 remains useful exploration for a future optional operations plane,
  especially provenance, partial ordering, and honest gaps, but its proposed
  production architecture is not adopted.
- Invocation cancellation remains explicitly unresolved future semantic work
  and is not a blocker for CV6.TS5.

## Review Trigger

Return to the Navigator if CV6.TS5 cannot atomically renew an Attempt and preserve
its latest details without changing canonical History or the pinned Absurd SQL;
if safe retry requires Dispatch to interpret application schemas; if details
must contain large content rather than an external reference; if a concrete
operator product requires a durable event stream rather than owner snapshots;
or if an implementation cannot proceed without deciding invocation
cancellation.
