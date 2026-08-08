---
code: CV10
level: Value
status: Blocked
status_reason: Retained execution seams are implemented, but independent environment lifecycle and Gondolin model-backed qualification remain blocked on provider capabilities and credentials; no working session is active
updated: 2026-08-08
related:
  - docs/project/decisions/records/2026-07-28T1052Z-local-dispatch-and-worker-provider-boundary.md
  - docs/project/decisions/records/2026-07-28T1907Z-async-worker-custody-stays-private.md
  - docs/project/decisions/records/2026-08-01T0736Z-cv10-execution-contracts-remain-private.md
---

# CV10 — Composable execution

## Intent

Let a Petrus application temporarily embody an Agent Program with computational
execution without making one agent backend, execution-environment provider, or
placement shape part of Activity or Net semantics. Host-owned external-effect
authority remains separate from canonical History.

## Retained technical truth

The private execution substrate belongs to Motus at
`petrus.motus._execution`. Its environment leases, attachments, command
execution, artifacts, cancellation, and recovery are qualification seams, not
public contracts. Impetus continues to own semantic History and Net execution;
Motus owns Activity custody and execution; applications own agent composition
and effect authority.

Completed work established provider-neutral private contracts for execution
territories and qualified multiple agent and environment combinations. Those
results do not promote a generic public agent or environment API.

## Incomplete boundaries

- Independent per-Activity environment lifecycle remains blocked where a
  provider cannot supply lookup/create, readiness, attachment, cancellation,
  destruction, recovery, and artifact export as a separately leased resource.
- Model-backed territory qualification remains blocked until its required
  provider capability and authority are available through a newly bounded
  story.
- Any wider provider matrix requires a newly bounded story and fresh evidence.

## Invariants

- Environment and provider identities never become canonical Activity or Net
  semantics.
- Agent substitution and environment substitution remain independent.
- External effect credentials and policy stay with the application host.
- Provider paths are not portable artifact identities.
- Execution observations may correlate with History but never become a second
  semantic ledger.

## Current state

No CV10 working session is active. The incomplete boundaries above are blocked,
not implicitly authorized by the completed private implementation.
