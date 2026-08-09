---
date: 2026-08-09T16:00:00Z
author: Amp
kind: milestone
related:
  - CV10.DS3
  - CV10.DS2
  - docs/project/decisions/records/2026-08-09T1400Z-episode-owns-independent-execution-territory.md
verification:
  - three focused Codex service and Worker-replacement nodes passed
  - complete Codex runtime file, 51 passed
  - scripts/check quick passed for all touched Python paths
  - scripts/check full, 2034 passed
  - scripts/check release, 2034 passed then 2034 passed with 17 external routes deselected
---

# Qualified Local Worker terminal replay without Activity-owned territory lifecycle

## What changed

A private host request service now lends one pre-existing Episode Attachment to
Codex runtime operations requested by real Local Worker processes. Workers
carry strict JSON Activity data while endpoint and authentication configuration
remain process-local. Stable Activity idempotency identifies the runtime
operation; Worker attempt identity remains transport custody.

The host ledger stores a request fingerprint before runtime admission and a
validated terminal before reply. In the acceptance route, the first Worker is
killed after the terminal is stored but before it can report completion. A
replacement Worker replays that terminal, and the runtime starts exactly once.

## Why it matters

Process reconstruction no longer requires serializing an Attachment, provider,
connection authority, credentials, or runtime adapter into Activity payloads.
The result also preserves the stronger ownership rule: Territory is orthogonal
to Activity. The Episode host provisions it first and explicitly exports and
settles it later; neither Activity nor the request service owns that lifecycle.

## Verification

The real subprocess witness passed together with service ownership, exact
request conflict, authentication, frame bounds, terminal validation, restart
indeterminacy, heartbeat renewal, stale-custody refusal, storage corruption,
and fail-closed quiescence checks. The complete Codex file passed with `51
passed`; `scripts/check full` passed with `2034 passed`; and
`scripts/check release` passed with `2034 passed` in parallel and `2034 passed,
17 deselected` in fixed order. The external qualification routes were not run
and are not claimed green.

## Follow-up

This is hermetic Local qualification only. Live provider/model authority,
network or multi-host service discovery, ambiguous provider-operation
reconciliation, retained territory custody, and power-loss exactly-once effects
remain outside the supported boundary.
