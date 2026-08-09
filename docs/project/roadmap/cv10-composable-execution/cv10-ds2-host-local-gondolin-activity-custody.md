---
code: CV10.DS2
level: Delivery Story
status: Done
status_reason: Private host-local Activity custody preserves one Episode territory across JSON-fenced Inline pre-admission retry
updated: 2026-08-09
related:
  - CV10.DS1
  - docs/project/decisions/records/2026-08-09T1400Z-episode-owns-independent-execution-territory.md
  - docs/project/decisions/records/2026-08-01T0736Z-cv10-execution-contracts-remain-private.md
---

# Qualify host-local Gondolin Activity custody

## Intent

Prove that formal Motus Activity attempts can invoke the hermetic Codex A3 lane
through one host-owned Episode territory without serializing connection,
Attachment, provider, or runtime collaborators.

## Scope

- Add one private, profile-specific Activity adapter beside the Codex Gondolin
  runtime adapter; do not export it as a supported API.
- Accept only JSON-faithful version-1 data naming the exact Episode, Turn,
  attachment identity/epoch, connection identity/epochs, prompt, and optional
  Continuation envelope.
- Use stable Activity `idempotency` as the runtime operation identity; never use
  attempt, epoch, claimant, or Worker identity.
- Fence Activity custody before runtime admission and normalize unexpected
  admission failures to a safe machine code.
- Qualify an Inline pre-admission failure followed by a second attempt through
  the same operation identity, Attachment, and Gondolin lease.

## Acceptance / Done Condition

1. **Given** one host-owned Episode Attachment, **when** Inline attempt one
   fails before runtime admission and attempt two retries, **then** both attempts
   present distinct Motus custody epochs but the same stable operation,
   attachment, and lease identities.
2. **Given** a JSON-round-tripped Activity request, **when** the second attempt
   completes, **then** it returns only bounded lifecycle references and cleanup
   evidence before the Episode exports and destroys its territory once.
3. **Given** missing idempotency, changed attachment coordinates, non-exact
   numeric fences, non-JSON input, or stale initial heartbeat custody, **when**
   admission is attempted, **then** no runtime or connection authority starts.
4. **Given** an unexpected admission exception containing a canary, **when** it
   crosses the Activity boundary, **then** only `runtime-admission-failed` is
   exposed.
5. The Activity constant and adapter remain absent from module `__all__`.

## Driver QA and Evidence Plan

- Run both exact Activity acceptance nodes and the complete Codex test file.
- Run `scripts/check quick` on touched Python paths.
- Run `scripts/check full` and `scripts/check release`.
- Keep external installation, authenticated provider, real Gondolin, and
  multi-process Worker routes unclaimed.

## Out of Scope

- Local/Absurd/ZeroMQ multi-process Worker reconstruction or claimant migration.
- Mid-execution heartbeat loss and publication-race reconciliation.
- Post-admission lost-terminal replay through a replacement Worker.
- Public Activity, runtime, Session, or execution-provider contracts.
- Live Gondolin, authenticated model/provider, retained territory, or orphan
  reconciliation support.

## Evidence

- The exact Inline retry and fence/redaction nodes passed (`2 passed`).
- The complete Codex runtime file passed (`48 passed`) after the final
  review-driven fence and redaction cases.
- `scripts/check quick` passed for the touched production and test files.
- `scripts/check full` passed with `2031 passed`.
- `scripts/check release` passed with `2031 passed` in the parallel run and
  `2031 passed, 17 deselected` in the fixed-order run. The external routes were
  not run and are not claimed green.

## Notes

Prompts are explicit Activity input and may enter canonical Activity request
History. They are not a secret channel. Connection authority, provider-private
state, and live custody objects remain host-owned and never cross the Activity
payload.
