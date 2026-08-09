---
code: CV10.DS3
level: Delivery Story
status: Done
status_reason: A replacement Local Worker replays one host-stored Codex terminal without redispatch or Activity-owned territory lifecycle
updated: 2026-08-09
related:
  - CV10.DS1
  - CV10.DS2
  - docs/project/decisions/records/2026-08-09T1400Z-episode-owns-independent-execution-territory.md
  - docs/project/decisions/records/2026-08-01T0736Z-cv10-execution-contracts-remain-private.md
---

# Qualify Local Worker reconstruction through host-stored runtime terminal replay

## Intent

Prove that a replacement Motus Worker can recover one completed hermetic Codex
runtime operation without serializing live collaborators or coupling territory
lifecycle to Activity execution.

## Scope

- Add one private authenticated Unix-domain request service and reconstructible
  Worker-side Activity client for the hermetic Codex Gondolin lane.
- Have the Episode host provision the territory and Attachment before Activity
  dispatch. The service borrows the existing Attachment and never provisions,
  exports, settles, cancels, or destroys its territory.
- Use stable Activity idempotency as runtime operation identity. Attempt,
  claimant, epoch, and transport identity remain Motus custody only.
- Durably admit a canonical request fingerprint before runtime start and store
  a validated terminal before replying. Exact terminal replay must not start
  runtime work again.
- Fence one live service owner, validate the exact SQLite schema and terminal
  values, renew Worker heartbeat custody while waiting, and require service
  quiescence before the host may infer that settlement is safe.
- Convert a recovered ambiguous executing record to terminal
  `operation-indeterminate`; never blindly redispatch after host loss.

## Acceptance / Done Condition

1. **Given** one host-provisioned Episode Attachment and one Local Activity
   invocation, **when** the host stores the runtime terminal and the first
   Worker loses the reply and is killed, **then** a replacement Worker receives
   the stored terminal under the same stable operation identity and runtime
   start count remains exactly one.
2. **Given** Activity completion and Worker replacement, **then** the exact
   Attachment and territory remain live until the Episode host explicitly
   exports and settles them outside Activity.
3. **Given** a conflicting request, unauthorized or malformed frame, stale
   initial attempt, malformed terminal, foreign ledger, or second live service
   owner, **when** admission is attempted, **then** the boundary fails with a
   bounded code and does not expose raw provider diagnostics.
4. **Given** a healthy long wait, **then** the Worker renews Motus heartbeat
   custody; **given** service close cannot establish quiescence, **then** close
   fails and retains the service fence rather than implying territory
   settlement is safe.
5. All service, client, Activity name, and protocol helpers remain private and
   absent from public module exports.

## Evidence

- The three focused service, Worker-replacement, and client-boundary nodes
  passed.
- The complete Codex runtime file passed with `51 passed`.
- `scripts/check quick` passed for all three touched Python paths.
- `scripts/check full` passed with `2034 passed`.
- `scripts/check release` passed with `2034 passed` in the parallel run and
  `2034 passed, 17 deselected` in the fixed-order run. External qualification
  routes were not run and are not claimed green.

## Out of Scope

- Territory creation, export, settlement, destruction, retention, or orphan
  reconciliation inside Activity or the request service.
- Network or multi-host service discovery and authentication.
- Live Gondolin, authenticated model/provider, or credential qualification.
- Resuming an ambiguous runtime operation after host loss; it fails closed as
  indeterminate.
- Power-loss exactly-once effects, generic runtime-service APIs, or public
  Activity/runtime construction contracts.

## Notes

The SQLite ledger stores request fingerprints and bounded terminal lifecycle
data, not prompts, continuation envelopes, service tokens, credentials, or live
objects. Worker death does not cancel already-admitted host work; the host may
finish and retain its terminal for a replacement request.
