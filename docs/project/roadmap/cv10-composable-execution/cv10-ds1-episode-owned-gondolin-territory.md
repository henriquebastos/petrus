---
code: CV10.DS1
level: Delivery Story
status: Done
status_reason: Hermetic Codex A3 evidence proves one Episode-owned Gondolin lease across replacement operations, resume, export, and verified destruction
updated: 2026-08-09
related:
  - docs/project/decisions/records/2026-08-09T1400Z-episode-owns-independent-execution-territory.md
  - docs/project/decisions/records/2026-08-01T0736Z-cv10-execution-contracts-remain-private.md
---

# Qualify one Episode-owned Gondolin territory

## Intent

Qualify the existing hermetic Codex A3 runtime-protocol lane against one
independently leased Gondolin territory whose lifetime belongs to one Episode,
rather than creating a territory for each runtime operation.

## Scope

- Add Episode-collocated ownership to the Codex A3 v1 topology without removing
  its legacy ephemeral-collocated compatibility offer.
- Use one exact Gondolin lease and Episode Attachment for a failed model
  operation, its replacement runtime operation, and a resumed model operation.
- Reconstruct the provider and prove lookup observes the same lease without a
  second territory.
- Preserve exact-attachment probing, connection/private-state isolation,
  bounded workspace export, and cleanup-gated settlement.
- Correct CV10's obsolete per-Activity lifecycle target and record the accepted
  ownership decision.

## Acceptance / Done Condition

1. **Given** one Gondolin-backed Episode Attachment, **when** a model operation
   fails and a replacement operation continues the work, **then** both use the
   same territory lease and attachment identity.
2. **Given** that territory, **when** another model phase resumes the native
   Continuation, **then** it still uses the same territory and preserves native
   thread state.
3. **Given** a reconstructed Gondolin provider, **when** it looks up the stable
   territory operation identity, **then** it observes the existing exact lease
   and no duplicate territory exists.
4. **Given** Episode settlement, **when** the attachment closes, **then** its
   bounded workspace is exported before verified territory destruction and no
   credential or private rollout enters the archive.
5. **Given** unverified cleanup, **when** settlement is consumed, **then**
   success remains blocked until retry verifies cleanup.

## Driver QA and Evidence Plan

- Run the exact Gondolin Codex lifecycle acceptance node.
- Run the complete Codex runtime, Episode Attachment, Gondolin provider, and
  runtime-profile test files.
- Run `scripts/check quick` on touched Python files.
- Run `scripts/check full` and `scripts/check release`.
- Keep opt-in real Gondolin/provider routes explicitly deselected unless their
  external authority is present; do not report them as green.

## Out of Scope

- Live Gondolin, authenticated Codex, or model-quality support claims.
- One territory per Motus Activity or attempt.
- Formal Motus Activity retry, claimant reassignment, worker reconstruction,
  or non-local Dispatch integration.
- A universal Agent, Session, or public execution-provider abstraction.
- Retained territory custody across Episode settlement.
- Power-loss durability and autonomous orphan reconciliation.

## Notes

This is a hermetic lifecycle qualification of the existing private Motus and
Agenticus seams. It does not promote those seams publicly or qualify every
Gondolin runtime profile.

## Evidence

- The exact lifecycle witness passed with one stable lease and attachment
  across a failed runtime operation, replacement operation, and native resume.
  Reconstructed-provider lookup observed the exact lease; settlement exported
  a public workspace canary, excluded private authority/rollout bytes, consumed
  exact-identity `clean` evidence, and left no territory.
- The focused Codex, profile, Episode Attachment, and Gondolin provider suite
  passed with `132 passed`; its one opt-in real Gondolin test skipped because
  no live provider authority was supplied and is not claimed green.
- `scripts/check quick` passed for all touched Python paths.
- `scripts/check full` passed with `2029 passed`.
- `scripts/check release` passed with `2029 passed` in its parallel full run and
  `2029 passed, 17 deselected` in its fixed-order run. The deselected external
  installation, authenticated provider, and real Gondolin routes remain
  unqualified here.
