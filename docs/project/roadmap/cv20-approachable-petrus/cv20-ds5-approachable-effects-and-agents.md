---
code: CV20.DS5
level: Delivery Story
status: Planned
status_reason: >-
  This story follows DS1's coherent zero-agent profile and must select one
  actually supported Agenticus path without flattening provider or authority
  differences.
updated: 2026-08-27
related:
  - index.md
  - ../../exploration/es-056-progressive-disclosure-developer-experience/index.md
  - ../cv16-agenticus-composable-agent-infrastructure/index.md
---

# CV20.DS5 — Approachable effects and agents

## Intent

Make ordinary Activities and one honestly supported Agenticus profile simple
leaves in the same application journey while preserving the distinct custody,
credentials, retries, provider support, and effect authority each requires.

## Scope

- Begin from DS1's working zero-agent profile and existing Activity seam.
- Make named Activity bindings, worker placement, retry/deadline policy, and
  terminal projection understandable without hiding operational guarantees.
- Select one genuinely supported Agenticus profile and compose it as an
  optional leaf; catalog presence or qualification-only providers do not count.
- Keep application-owned clients, credentials, effect policy, and host
  authority outside the Net and generated artifacts.
- Preserve deliberate descent to current Motus and application-host composition.

## Candidate story seeds

- **US1 — Add an ordinary Activity without losing the local journey.** Extend a
  zero-agent example with one side effect and explain custody and recovery.
- **US2 — Add one supported agent leaf.** Use the same authored journey while
  making model/provider support and authority explicit.
- **TS1 — Authority and support diagnostics.** Refuse unsupported profiles,
  missing bindings, credentials in artifacts, and ambiguous host ownership
  before motion.

## Acceptance / Done condition

1. A zero-agent flow remains complete and first-class.
2. One ordinary Activity composes through existing Impetus/Motus boundaries
   with declared custody, retries, deadlines, and terminal projection.
3. One supported Agenticus profile composes through the same journey without
   claiming universal agent, model, provider, or environment support.
4. Credentials, provider clients, and effect authority remain application-host
   capabilities and never enter canonical Net, History payloads, or portable
   documents.
5. Advanced applications can descend to current bindings, Workers, Dispatch,
   and host composition without changing process semantics.

## Driver QA and evidence plan

- Execute one deterministic zero-agent example, one ordinary Activity example,
  and one exact supported Agenticus profile end to end.
- Exercise retry, terminal failure, restart/recovery, missing binding,
  unsupported profile, and credential-leak refusal.
- Inspect canonical artifacts for capabilities and secret-like content.
- Run focused runtime/provider tests and the complete repository gate.

## Out of scope

- A universal Agent, Session, provider, environment, or effect object.
- Promoting CV10 private execution contracts or qualification-only providers.
- Making one agent backend foundational to Petrus.
- Moving application lifecycle or external-effect authority into Petrus or Arx.
