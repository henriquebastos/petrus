---
status: Decided
raised: 2026-07-21
decided: 2026-07-22
deciders:
  - henrique (Navigator)
supersedes:
  - ES-036's recommendation for a mandatory provider-neutral Worker registration and capability/resource envelope; its topology and missing-renewal evidence remains valid
  - ES-037's hypothesis that a core Registry must own Worker presence; an optional higher operational layer remains possible
related:
  - docs/project/decisions/records/2026-07-14T2016Z-activity-invocation-runtime-seam.md
  - docs/project/decisions/records/2026-07-15T0110Z-absurd-execution-substrate.md
  - docs/project/decisions/records/2026-07-22T1031Z-instance-authors-terminal-history-and-shared-firing-transform.md
  - docs/project/decisions/records/2026-07-22T1539Z-engine-routes-activities-through-operational-queues.md
  - docs/project/decisions/records/2026-07-22T1930Z-dispatch-snapshots-heartbeat-details-observation-remains-optional.md
---

# Dispatch leases Activity attempts while DevOps operates Workers

## Question

Does core Impetus need a durable Worker Registry and provider-neutral Worker
control plane, or can replaceable Workers poll operational queues while
Dispatch owns only the correctness-critical lifecycle of each Activity
attempt? How should long-running Activities renew custody and preserve
recoverable progress without making Worker presence or checkpoints canonical
History?

## Decision

Core Impetus has **no mandatory durable Worker Registry**. A Worker is a
replaceable operational process that:

- authenticates using externally provisioned workload credentials;
- subscribes to configured Dispatch queues;
- maintains a local registry of the Activity implementations it can execute;
- claims and executes Activity attempts; and
- reports operational terminal outcomes for Engine/Instance-side acceptance.

DevOps and provider infrastructure own Worker process creation, placement,
health checks, restart, scaling, credentials, queue access, and termination.
Impetus does not duplicate Kubernetes, AWS, E2B, systemd, or another provider's
fleet control plane.

### Identity and reconnect

A Worker may have an optional stable operational label for logs and operator
correlation. Each process boot also has an ephemeral **Worker incarnation**.
The incarnation is operational identity, not authentication, Instance
identity, or canonical History.

- Restarting the Worker process mints a new incarnation.
- A transport or network reconnect by the same still-running process retains
  its incarnation.
- Reconnect may continue an in-flight Attempt only while that Attempt's lease
  epoch remains current. Expiry or reassignment makes the old epoch stale and
  Dispatch refuses further renewal, details replacement, or terminal acceptance from
  it.

### Attempt custody and long-running Activities

Dispatch, not a Worker Registry, owns the correctness-critical Attempt
lifecycle: Attempt identity, lease epoch, deadline, renewal, expiry,
reassignment, latest-details acceptance, and stale-epoch refusal.

Long-running Activity implementations can declare a heartbeat timeout so the
Activity developer makes the judgment appropriate to the code. The effective
timeout is resolved before dispatch and snapshotted in the frozen
`ActivityInvocation` execution policy, making recovery stable across Engine
restart and Worker replacement. The future implementation/API story must find
the smallest way to carry implementation-declared policy to the Engine without
requiring the Engine to execute or silently import Worker-only implementation
code.

While executing, Activity code may heartbeat its current Attempt from
meaningful progress points or a controlled interval. A heartbeat for the
current lease epoch atomically renews custody and may include one optional
application-defined JSON-faithful `details` value serving progress, retry
checkpoint state, or both. The heartbeat cadence is Activity behavior; the
resolved timeout is durable execution policy.

Accepted details are durable **operational** state owned by Dispatch. They are
not token data, an Activity result, or canonical History. Dispatch snapshots
the latest accepted value without interpreting it and supplies it to a
replacement Attempt; the Activity implementation decides compatibility and
whether and how to resume. Details reduce repeated computation when used as a
checkpoint but never prove whether an external effect happened. This paragraph
incorporates the DEC-038 refinement of DEC-037's original “optional
checkpoint” wording; no separate checkpoint type, store, or schema is required.

When heartbeats stop, Dispatch expires the Attempt and may reassign it under
the frozen execution policy. A stale Worker cannot renew, overwrite a
details snapshot, or submit an accepted terminal report for the superseded epoch.
Dispatch fencing governs Impetus custody and acceptance; it cannot universally
fence an arbitrary external service. External-effect idempotency and
lookup-first reconciliation remain the Activity developer/provider
integration's responsibility.

### Drain and revocation

Graceful drain means stop claiming new work, finish the current Attempt, report
its outcome, and exit. This preserves the current SIGTERM behavior.

Do not add a generic core `revoke Worker` protocol. DevOps/IAM stops or kills
the process and revokes credentials or queue access to prevent new work and
reconnect. Ordinary lease expiry handles abandoned custody. Explicit
Attempt cancellation or immediate lease invalidation, including late-outcome
precedence, was deferred by DEC-038 to later Engine/Instance semantic work and
is not part of the initial Attempt protocol.

### Optional higher operational layer

A future optional Worker Operations/Observation layer may provide a durable,
advisory inventory without participating in execution correctness. It may join:

- Worker boot/incarnation announcements, queue subscriptions, local Activity
  names, and build/version metadata;
- Dispatch Attempt and lease observations; and
- provider facts from Kubernetes, AWS, E2B, systemd, or other supervisors.

That layer can answer which Workers or queue pollers are visible, what they are
running, which build is deployed, and whether a pool is draining or absent. It
must expose staleness and gaps honestly. If it is unavailable, Dispatch and
Workers continue operating.

The optional layer does not claim work, renew leases, accept terminal reports,
choose placement, scale infrastructure, match capabilities, or write canonical
History. Process Fabric authentication, storage, or envelope primitives may be
reused internally, but Fabric addresses independently authoritative Instances;
a Worker incarnation remains replaceable operational capacity. Their identity
and authority do not collapse.

## Rationale

DEC-036 established that explicit queues plus DevOps provisioning are enough
for initial routing. A mandatory Worker Registry would reintroduce much of the
placement and fleet control plane that decision deliberately excluded. Queue
polling is enough to offer work; per-Attempt leases are the narrower state
required for correctness.

The current fixed claim timeout is inadequate for healthy long-running work.
Making it exceed the worst case delays crash detection; making it shorter can
redispatch while useful work still runs. Activity heartbeats let the code that
understands progress renew a bounded Attempt lease. Optional heartbeat details
make retry less wasteful when the Activity uses them as checkpoint state,
without changing semantic truth.

Separating Worker presence from Attempt custody also leaves room for richer
agentic operations later. A durable fleet inventory, administrative UI, and
provider adapters can grow above the stable queue/Attempt seam without changing
Activity, Instance, or History.

## Options Considered

- **Mandatory Registry presence plus Dispatch Attempt leases.** Rejected for
  core: it duplicates provider lifecycle state and introduces a second
  correctness-adjacent protocol before a concrete need.
- **One Dispatch-owned Worker and Attempt control plane.** Rejected: Dispatch
  should own custody, not infrastructure fleet lifecycle.
- **Provider lifecycle plus fixed claim timeout and idempotency only.** Rejected
  as the production floor for long Activities because it cannot distinguish a
  healthy long Attempt from a dead claimant promptly.
- **Queue polling plus heartbeating Dispatch Attempt leases — chosen.** It is
  the smallest production-capable contract and supports later optional fleet
  observation.
- **Reuse Process Fabric identity for Workers.** Rejected. Lower-level
  primitives may be shared; independently authoritative Instance addresses and
  replaceable Worker incarnations retain different meanings.

## Consequences

- A bounded Planned Technical Story will validate Attempt heartbeat, renewal,
  latest-details snapshot, reconnect, expiry/reassignment, and stale-epoch behavior.
- Activity authors can declare a heartbeat timeout; the effective value is
  frozen as resolved execution policy before dispatch. The exact declaration
  and resolution API remains implementation-story work.
- No Worker registration schema, central Activity advertisement, capability
  matching, generic revocation protocol, provider control plane, or production
  Worker Operations package is commissioned.
- Worker presence remains optional operational evidence. DEC-038 declined to
  adopt a production Observation plane now; a future optional operations/read
  layer may add retention, cursors, and UI joins without owning execution.
  Invocation cancellation remains later Engine/Instance semantic work.
- Queue, Worker, incarnation, Attempt, heartbeat, and details facts remain
  outside canonical History. Only existing Activity/firing semantic facts are
  accepted by Instance.
- External-effect idempotency remains a developer/provider responsibility.
- The current Absurd pin and SQL are unchanged by this recording decision.

## Review Trigger

Return to the Navigator if implementation cannot renew or fence Attempt custody
without altering Absurd's pinned SQL; if implementation-declared timeout cannot
be resolved without coupling Engine deployment to Worker-only code; if a
heartbeat details value must enter canonical History; if reconnect cannot distinguish the
same running process from a restart; if a provider requires a core Worker
Registry for correctness; or if invocation cancellation must be decided before
the bounded heartbeat story can remain coherent.
