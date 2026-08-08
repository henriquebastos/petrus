---
code: CV16
level: Value
status: Blocked
status_reason: Host adoption, supported-profile qualification, and release acceptance require a new bounded story.
updated: 2026-08-08
related:
  - docs/project/decisions/records/2026-08-03T0430Z-installations-own-authority-agenticus-owns-machinery.md
  - docs/project/decisions/records/2026-08-05T0923Z-net-owned-pi-loop-mirrors-a-bounded-public-seam.md
  - docs/project/decisions/records/2026-08-05T1405Z-pi-a2-recovery-separates-work-identity-from-process-fences.md
---

# CV16 — Agenticus composable agent infrastructure

## Status

**Blocked.** The reusable package work represented by DS1–DS10 is implemented.
Host adoption, supported-profile qualification, and release acceptance are not
complete. No work session is active. Continuing requires a new bounded story
with explicit acceptance behavior and an executable validation route.

## Intent

Provide optional, reusable agent infrastructure as a Petrus-level composition
without moving agent concepts into Petri semantics or generic Activity
execution.

Agenticus supplies machinery that applications can compose with their own
authority, policy, workflows, configuration, and user experience. It does not
make agents mandatory for Petrus.

## Package ontology and dependency direction

`petrus.agenticus` is an optional composition subsystem over Impetus and Motus:

- Impetus owns Net semantics, Instance state, and canonical History.
- Motus owns Activity execution, Dispatch, Workers, transport, and execution
  territory lifecycle.
- Agenticus owns agent-oriented composition over those capabilities.
- Impetus and Motus do not depend on Agenticus.
- Agenticus does not become a foundational component beside Impetus, Motus,
  and Arx.

The package defines distinct concepts rather than a universal Agent or Session:

- Agent Connection custody and authority references;
- Agent Program;
- Thread, Continuation, Episode, and Turn lifetimes;
- runtime profiles and capability catalog resolution;
- capability-scoped Hands;
- Episode Attachment to Motus-owned execution territory;
- effect proposal and fencing;
- agent behavior composed as a Net.

Concepts are imported from their defining modules. The package root is not a
facade that erases ownership.

## Responsibility boundary

Agenticus owns reusable mechanism:

- custody contracts and lifecycle state for Agent Connections;
- immutable program and turn descriptions;
- runtime-adapter contracts that state their actual capabilities;
- capability discovery and compatibility results;
- bounded attachment of one Episode to execution territory;
- scoped Hands that expose only granted operations;
- effect proposals, approvals, and stale-authority fencing;
- composition of agent turns into ordinary Petrus process behavior.

An installation owns authority and product policy:

- concrete credentials and secret storage;
- provider and model enablement;
- approval rules and user intent;
- application workflows and durable business state;
- host lifecycle, configuration, and user experience;
- selection of supported runtime profiles;
- cleanup and reconciliation required by its providers.

Motus continues to own execution territory, command execution, leases,
transport, lookup, reconciliation, and destruction. Agenticus may attach agent
meaning to those capabilities but does not expose
`petrus.motus._execution` as public API. That module remains legitimate private
implementation.

Agenticus does not own canonical History and does not treat operational
telemetry as semantic execution authority. Durable process facts enter through
ordinary Impetus and Motus contracts.

## Implemented reusable package boundary

DS1–DS10 established the reusable package surface:

1. ontology and package ownership;
2. Agent Connection custody;
3. Thread and Agent Program values;
4. runtime execution contracts;
5. runtime profiles and capability catalog;
6. Hands and Episode Attachment;
7. effect proposal and fencing;
8. host-composition seams;
9. runtime adapter boundaries;
10. Agent-as-a-Net composition.

This summary records implemented package scope, not acceptance of every
provider, host, deployment, or support claim. Supported behavior is limited to
the package API and capability statements documented in the README and proven
by the included tests.

## Incomplete boundary

The Value remains blocked because reusable implementation alone does not
establish an accepted host product boundary. A future bounded story must decide
and verify:

- one explicit host composition using installation-owned authority;
- which runtime profiles are supported, experimental, or unavailable;
- authority materialization and teardown behavior;
- crash and recovery behavior for the selected profile;
- provider-specific cleanup and reconciliation where applicable;
- operator-facing failure behavior;
- package support and release acceptance.

No live-provider support is inferred from adapter existence. A profile is
supported only when current package documentation says so and the included
validation route proves the corresponding contract.

## Acceptance invariants

Any story that resumes CV16 must preserve these invariants:

1. Installations own concrete authority; Agenticus owns reusable machinery.
2. Credentials and provider authority do not enter canonical History.
3. Capability access is explicit, scoped, and fail-closed.
4. Stale Connection, Attachment, grant, or execution authority cannot publish
   effects.
5. Thread, Continuation, Episode, Turn, workspace, territory, and provider
   session identities remain distinct.
6. Runtime profiles state real differences rather than claiming false
   equivalence.
7. Agent output becomes durable process truth only through accepted Petrus
   boundaries.
8. Recovery distinguishes stable logical work identity from process-scoped
   fences and never invents exactly-once external execution.
9. Provider-specific types do not leak through provider-neutral Agenticus
   contracts.
10. Impetus and Motus remain usable without Agenticus.
11. Agenticus remains optional and does not reverse dependency direction.
12. Cleanup uncertainty is represented honestly and fails closed where
    authority cannot be proven current.

## Out of scope

- A universal Agent or Session abstraction.
- Moving agent concepts into Impetus or Motus.
- Making Agenticus required for ordinary Petrus processes.
- Provider account provisioning or credential distribution.
- Host-specific workflows, user interfaces, or business policy.
- A claim of support for every implemented adapter.
- Exactly-once provider execution or external effects.
- Public promotion of private Motus implementation modules.
- New host adoption, support, or release work without a bounded story.

## Resume condition

Create one bounded story naming the selected host-neutral composition and
support profile, its authority and recovery boundaries, and an executable
acceptance route. Until that story exists and is accepted, CV16 remains
Blocked and no working session is active.
