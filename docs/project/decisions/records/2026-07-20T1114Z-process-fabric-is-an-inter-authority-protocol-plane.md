---
status: Decided
raised: 2026-07-20
decided: 2026-07-20
deciders:
  - henrique (Navigator)
supersedes:
related:
  - CV5.DS1
---

# Process Fabric is an inter-authority protocol plane

> **Naming amendment (2026-07-23):**
> [Fabric is now the exact public capability term](2026-07-23T1851Z-fabric-public-term.md).
> This record's protocol behavior, dependency direction, and host separation
> remain decided; only its exact “Process Fabric” naming clause is superseded.

## Question

Does durable addressed messaging belong to the Petri kernel, the missing
application-host layer, or a separate Impetus layer, and how much source
reorganization should occur before process lifecycle behavior is added?

## Decision

Process Fabric is a distinct **inter-authority protocol plane** above the
one-instance authority/runtime layer and below process-lifecycle protocols.
It is neither Petri-kernel semantics nor the missing application surface host.

Use **Impetus** as the umbrella project/distribution and compatibility facade;
qualify the semantic core as **Impetus Kernel**. The logical layers are:

1. Impetus Kernel — net semantics, canonical record algebra, `EventHistory`
   contract, `NetInstance`, replay/status, ingress conflict semantics, and
   virtual time.
2. Driving Runtime — coordinator/runner, clocks/sensors, policy/actions, and
   activity/execution-adapter contracts.
3. Authority Infrastructure and Host — history/fence implementations,
   transaction fate, resume, poison, reconstruction, and composition of one
   authority.
4. Execution Adapters — operational dispatch, workers, queues, claims, and
   leases such as Absurd.
5. Process Fabric — transport-neutral addresses/envelopes/reply routes plus
   discovery, grants, inboxes, receipts, retry, and correlation.
6. Process Lifecycle — separate `call` and `spawn` contracts above Fabric.
7. Provider Adapters — Codex, Claude, and pi loops and provider-session
   territory.
8. Applications — net definitions, domain semantics, and product surfaces.

An **Authority Host** owns/resumes/drives one authoritative instance and may
attach Fabric ingress/send adapters. An **Application Surface Host** optionally
adds HTTP, SSE, CLI, browser, authentication, projection, and attach surfaces
around one or more authorities. Fabric depends on neither a concrete host nor
an application; a host may operate without Fabric.

Before CV5.DS2, perform one behavior-preserving boundary slice only on the new
CV5 modules: separate Fabric's transport-neutral model, ingress bridge, and
PostgreSQL implementation, and place PostgreSQL authority fencing explicitly.
Document and enforce import direction. Preserve established Impetus module
paths and defer a broad source/distribution reorganization.

## Rationale

DS1 supplies executable boundary evidence. Inbound messaging crosses
`Fabric row -> FabricInbox -> NetInstance.deliver -> recipient history`;
outbound messaging crosses
`ActivityRequested("fabric.send") -> adapter -> Fabric row`. Fabric therefore
bridges the existing sacred ingress/activity seams rather than scheduling a
net or authoring a shared history.

Agent Factory, Mirror, and Ariad Authority independently supply different
evidence for the outer host responsibilities. Combining those concerns with
Fabric would make HTTP/session/UI lifecycle a prerequisite for process
communication and would encourage a concrete host dependency.

The root `impetus` facade already exports kernel and runtime symbols. Making it
kernel-only now would break established callers without strengthening the
logical boundary. Conversely, moving every established module now would turn
still-evolving authority, result-acceptance, and session rulings into
cross-package compatibility work. The new unreleased CV5 modules are the
smallest safe physical boundary to establish before DS2.

## Options Considered

- **Put Fabric in the kernel.** Rejected: process addresses, grants, receipts,
  PostgreSQL, and remote lifecycle are replaceable infrastructure, not Petri
  semantics.
- **Make Fabric the application host.** Rejected: protocol routing and
  authority/application hosting are independently useful and have different
  dependencies.
- **Make the root package kernel-only immediately.** Rejected: it is already
  an umbrella facade and compatibility surface.
- **Move the whole source tree before DS2.** Rejected: too much behavioral and
  API churn while established seams remain under decision.
- **Document only and leave `fabric.py` monolithic.** Rejected: neutral
  envelope imports would still require PostgreSQL, and DS2 would accrete
  lifecycle policy beside concrete storage.
- **Bounded new-surface split — chosen.** Creates the transport-neutral home
  DS2 requires while preserving established paths.

## Consequences

- Fabric rows remain protocol state and never enter a global `EventHistory`.
- Fabric model code imports neither PostgreSQL nor a concrete authority host.
- Fabric ingress may import the public kernel delivery types and enters only
  through `NetInstance.deliver`.
- Fabric PostgreSQL implements the protocol store and keeps the version-1 wire
  and schema contracts stable.
- `call` and `spawn` depend on Fabric ports and a minimal host/provisioner port,
  never directly on PostgreSQL or Absurd.
- Provider adapters own provider continuation/session details; lower layers do
  not import Codex, Claude, or pi.
- The broad eventual source tree remains a target, not a current commission.
- Import-boundary checks make the architecture executable rather than prose.

## Review Trigger

Review when a second Fabric transport exists, the first generic Authority Host
is implemented, established modules enter a planned compatibility migration,
or real `call`/`spawn` consumers show the layer direction is wrong.
