---
code: CV10
level: Value
status: Blocked
status_reason: DS1–DS4 are complete at bounded hermetic qualifications; live-provider and multi-host custody require authorized provider and fencing evidence
updated: 2026-08-10
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
- CV10.DS2 qualified private host-local Motus Activity execution through one
  existing Attachment: a JSON-fenced Inline pre-admission retry keeps one
  stable runtime operation, Attachment, and lease. Activity never owns the
  territory lifecycle.
- CV10.DS3 qualified one hermetic Local Worker process-loss route through a
  fenced host request service. A replacement Worker replays a terminal stored
  before reply without redispatching runtime work. The Episode host provisions
  and later settles the territory outside Activity; the service only borrows
  its existing Attachment. Multi-host service discovery and live providers
  remain unqualified.
- Live model-backed Gondolin support remains blocked until the exact provider,
  image, model authority, and credentials are available through an authorized
  acceptance route.
- CV10.DS4 qualified durable retained-territory custody and reconciliation for
  one hermetic host state root. Release drains all existing Attachment work,
  transfers one exact lease and bounded public archive to host custody, and
  permits reconstructed exact reclaim or verified retirement without giving
  Activity or Worker lifecycle authority. It does not imply multi-host
  transfer, live-provider support, power-loss durability, or general retention
  support.
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

CV10.DS1–DS4 are Done at their bounded hermetic qualifications. CV10 remains
Blocked beyond those boundaries: live provider support, public execution
contracts, network or multi-host Worker reconstruction and custody,
provider-side fencing, power-loss durability, and a wider profile matrix
require authorized evidence or newly bounded stories.
