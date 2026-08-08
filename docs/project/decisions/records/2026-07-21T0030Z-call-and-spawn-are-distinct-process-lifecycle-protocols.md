---
status: Decided
raised: 2026-07-20
decided: 2026-07-20
deciders:
  - henrique (Navigator)
supersedes:
related:
  - CV5.DS2
  - CV5.DS1
  - docs/project/decisions/records/2026-07-20T1114Z-process-fabric-is-an-inter-authority-protocol-plane.md
---

# Call and spawn are distinct process-lifecycle protocols

## Question

Should delegated work and durable child creation be one operation, and what
state may the process-lifecycle layer own without becoming another semantic
history or a concrete host implementation?

## Decision

Keep `call` and `spawn` as distinct protocols above Process Fabric.

`call` addresses an existing process through unchanged Fabric Envelope v1. A
parent-scoped call identity correlates one request with one result or error.
Receipt means delivery acceptance, not delegated completion. Reply validation
binds the incoming sender, destination, source, and correlation to the
original request, and the caller's net owns the meaning of the reply.

`spawn` claims one deterministic child identity from `(parent, spawn_id)` in a
mapping-only lifecycle registry, then calls an exact-retry-safe
`ProcessProvisioner.ensure`. Spawn success means the child address is durably
registered and authorized. It does not mean a host started, a child ran, or a
child completed.

The provisioner owns child credentials and host/operator territory. Generic
spawn values and outcomes contain only public identity, endpoint,
capabilities, configuration, and lineage data. The provisioner returns no live
host, provider session, connection, worker, or credential.

## Rationale

An existing delegated process and a newly created durable child have different
ownership, retry, and lifetime semantics. Combining discovery, provisioning,
request delivery, and completion would make one large operation span parent
history, protocol storage, child history, and external infrastructure without
an honest atomic boundary.

A durable mapping before idempotent provisioning closes the crash window while
preserving separate authorities. The registry records only identity and
changed-content evidence; parent and child histories remain the semantic
truth, and Fabric remains delivery truth.

## Options Considered

- **One discover/spawn/call operation.** Rejected because independently
  retryable protocol facts and semantic completion would be conflated.
- **Spawn returns a live host or credential.** Rejected because placement and
  secrets would enter parent semantics and bind process identity to one host.
- **Lifecycle status table.** Rejected because it would become a hidden second
  semantic history for the child.
- **Mapping claim followed by a minimal provisioner port — chosen.** Preserves
  crash recovery and host independence with the least new protocol state.

## Consequences

- Spawn followed by call is explicit composition, not one lifecycle.
- Each net instance remains reconstructible from its own canonical history.
- Exact spawn retry may invoke provisioning more than once but converges on one
  child identity and address.
- Changed spawn content under one identity conflicts before provisioning.
- Cancellation, retirement, orphan recovery, timeout, and supervision require
  later explicit policy; none is inferred from a Fabric receipt or claim row.
- Provider implementations begin with Codex, Claude, and pi but own their own
  continuation/session territory above these provider-neutral contracts.

## Review Trigger

Review when the first production Authority Host implements child lifecycle,
when cancellation/retirement is designed, or when a real provider integration
shows that call and spawn need an additional shared protocol primitive.
