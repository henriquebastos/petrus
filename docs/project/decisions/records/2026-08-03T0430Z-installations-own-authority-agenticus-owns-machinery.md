---
status: Decided
raised: 2026-08-03
decided: 2026-08-03
deciders:
  - henrique (Navigator)
supersedes:
  - earlier host-specific connection-ownership proposals
related:
  - CV16
  - docs/project/decisions/records/2026-08-01T0736Z-cv10-execution-contracts-remain-private.md
  - docs/project/decisions/records/2026-07-29T2316Z-petrus-is-project-over-impetus-motus-and-arx.md
---

# Installations own authority; Petrus Agenticus owns reusable agent machinery

## Question

Should every Petrus host application implement its own Agent Connection
custody, agent-loop, runtime, Hands, attachment, and effect-fencing machinery,
or should Petrus provide those reusable mechanisms while host applications
compose them with product-specific policy?

## Decision

Petrus owns the reusable machinery in a new **`petrus.agenticus`** composition
subsystem. Agenticus owns Agent Connection custody contracts, Agent Programs,
Thread/Continuation/Episode/Turn concepts, honest runtime profiles, the
capability-scoped Hands protocol, Episode Attachment over Motus territory,
effect proposal and fencing contracts, and a host-facing capability Catalog.

A host application owns concrete authority instances, provider enablement,
product policy, approvals, workflows, configuration, and user experience. The
installation remains the security principal for its Agent Connections; Petrus
does not become the principal merely because Agenticus implements custody. A
host composes or registers Agenticus capabilities instead of rebuilding their
infrastructure.

Agenticus is a Petrus-level composition subsystem, not a fourth foundational
component beside Impetus, Motus, and Arx. It may depend on Impetus and Motus;
neither may depend on Agenticus. Motus continues to own execution territories,
leases, command execution, transport, lookup, reconciliation, and destruction.
Agenticus owns the agent meaning composed over those capabilities. Agenticus
does not own canonical History, may not read operational Timeline as execution
authority, and must not expose provisional private Motus execution types as its
public API.

There is no universal `Agent` or `Session` concept. Provider-owned,
harness-owned, and Net-owned Agent Programs remain distinct. `Thread`,
`Continuation`, `Episode`, and `Turn` name separate lifetimes. Agent Home,
workspace, Motus territory, provider session, and Thread remain separate
objects. Concepts are imported from their defining modules; the
`petrus.agenticus` root is not a concept facade.

## Rationale

The package tests prove the same application-owned loop and capability-scoped
Hands contract across territory adapters, together with connection custody,
staged-write fencing, cleanup, and provider reconciliation. Making each host
copy that mechanism would produce incompatible security behavior and force
business products to own infrastructure unrelated to their proposition.

Putting the machinery directly in Impetus or Motus would create the opposite
error. Agent loops and credentials are not Petri semantics, canonical History,
Activity, Dispatch, Worker, or territory lifecycle. A Petrus-level composition
can reuse both components without reversing their dependency direction or
pretending provider-specific behavior is one universal runtime.

## Options Considered

- **Each host implements its own agent infrastructure.** Rejected because it
  duplicates security-sensitive machinery and prevents portable compositions.
- **Put all agent concepts in Motus.** Rejected because Motus owns generic
  Activity execution and territory lifecycle, not agent identity or loops.
- **Put all agent concepts in Impetus.** Rejected because agents are optional
  compositions over the kernel, not Petri-net semantics or canonical History.
- **Create an independent fourth foundational component.** Rejected because
  Agenticus composes existing Petrus capabilities rather than defining a new
  foundation or separate product identity.
- **Create `petrus.agenticus` as a Petrus-level subsystem — chosen.** It gives
  reusable mechanisms a coherent home while keeping host policy and provider
  differences explicit.

## Consequences

- Host adoption follows reusable Agenticus delivery and requires its own
  bounded acceptance story.
- Host applications select and register capabilities through Agenticus but do
  not receive raw credentials or private Motus implementation objects.
- Runtime profiles must state their real differences rather than claiming
  false equivalence.
- Provider support requires bounded authority materialization, secret-free
  evidence, and explicit local/provider cleanup.
- The private status of `petrus.motus._execution` remains in force until CV16
  deliberately promotes the smallest Motus-owned contract needed by Episode
  Attachment.

## Review Trigger

Revisit the subsystem boundary if Agenticus can no longer remain an optional
composition over Impetus/Motus, or if a concrete implementation requires a
foundational component to depend on Agenticus. Provider-specific limitations
change support profiles, not this ownership direction.
