---
code: CV10
level: Value
status: Blocked
status_reason: CV10.DS1–DS2 completed Episode ownership and host-local Activity custody; remote Worker reconstruction, live support, and retention remain blocked or unbounded
updated: 2026-08-09
related:
  - docs/project/decisions/records/2026-07-28T1052Z-local-dispatch-and-worker-provider-boundary.md
  - docs/project/decisions/records/2026-07-28T1907Z-async-worker-custody-stays-private.md
  - docs/project/decisions/records/2026-08-01T0736Z-cv10-execution-contracts-remain-private.md
  - docs/project/decisions/records/2026-08-09T1400Z-episode-owns-independent-execution-territory.md
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

- An independently leased territory belongs to one bounded Episode or host
  operation, not one Activity attempt. CV10.DS1 qualified that lifecycle with
  the hermetic Gondolin Codex runtime-protocol lane while preserving
  provider-neutral identity, export, and cleanup fences.
- CV10.DS2 qualified private host-local Motus Activity custody: a JSON-fenced
  Inline pre-admission retry keeps one stable runtime operation, Attachment, and
  lease. It does not qualify process migration or remote Worker reconstruction.
- Live model-backed Gondolin support remains blocked until the exact provider,
  image, model authority, and credentials are available through an authorized
  acceptance route.
- Durable retained-territory custody and autonomous orphan reconciliation need
  newly bounded stories before retention can become a supported settlement
  policy.
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

CV10.DS1 and CV10.DS2 are Done at their bounded hermetic qualifications. No
CV10 working session is active. Live provider support, public execution
contracts, retained territories, multi-process Activity retry/reconstruction,
and a wider profile matrix remain blocked or require newly bounded stories.
