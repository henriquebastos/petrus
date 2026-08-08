---
status: Superseded
raised: 2026-07-30
decided: 2026-07-30
deciders:
  - Navigator
related:
  - CV9.DS4
  - CV9.DS5
  - CV9.DS6
  - CV9.DS7
  - CV9.DS8
---

# Deterministic reviewers prove the conversation before real Actions or agents

## Decision

Deliver the first interactive GitHub PR-conversation story with deterministic
correctness, test-quality, and risk Activities. Label them explicitly as
deterministic demo reviewers, never agents. They publish typed proposals and
exercise closed human decision, apply, status, and stop commands against the
existing repository hook, runtime, PR Instance, Inbox, and History.

Real GitHub Actions lifecycle correlation is the next coherent story. Real
review agents remain blocked behind the accepted provider-attestation decision.
Formal GitHub review approval is not proposal approval in V1; only closed
`/impetus` commands authorize proposal decisions.

## Rationale

The conversation, authorization, idempotent publication, current-head fencing,
and recovery behavior are independently valuable and reviewable. Adding real
Actions in the same slice would join a second event family, run/attempt state
machine, rerun authority, and several failure classes. Waiting for real agents
would leave the already-approved interaction semantics untested.

## Options Considered

- Add Actions and comments together: rejected as more than one coherent review
  and recording story.
- Resume GitHub App/JWT/PEM work: rejected; the exact-repository bootstrap
  credential already has the bounded authority and App work has no current
  Navigator ruling.
- Call deterministic reviewers agents: rejected because it would overstate the
  external capability and obscure the DS5 blocker.

## Consequences

- Demo comments and reports must always disclose the deterministic stand-in.
- `rerun-ci` is parsed but visibly refused as `real_actions_deferred` until DS6.
- Proposal IDs bind one generation; exact head remains carried by the typed
  ledger and fenced again before mutation.
- The current long-lived relay/runtime remains the sole live owner. No generic
  multi-PR registry, App, force push, workflow edit, or implicit cleanup is
  introduced.

## Review Trigger

Superseded on 2026-07-31 by the clean replacement workflow decision. Preserve
this record as the rationale and boundary of the completed deterministic demo;
do not use its sequencing or topology as the replacement implementation path.
