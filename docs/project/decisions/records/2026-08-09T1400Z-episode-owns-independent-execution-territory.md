---
status: Decided
raised: 2026-08-09
decided: 2026-08-09
deciders:
  - henrique (Navigator)
supersedes:
related:
  - CV10
  - CV10.DS1
  - docs/project/decisions/records/2026-08-01T0736Z-cv10-execution-contracts-remain-private.md
  - docs/project/decisions/records/2026-08-03T0430Z-installations-own-authority-agenticus-owns-machinery.md
---

# An Episode owns its independently leased execution territory

## Question

Does an independently leased execution territory belong to each Motus Activity,
or to the bounded Episode or host operation whose work those Activities serve?

## Decision

One independently leased territory belongs to one bounded Episode or host
operation. Model/runtime operations and any Activities a composition binds to
that work execute through the Episode's exact attachment. A replacement runtime
operation within the Episode retains the same territory operation and lease
identity.

Settlement explicitly exports the bounded workspace before it destroys the
territory; the host may accept completion only after cleanup is independently
verified.
Destruction is the only supported settlement policy now. Retention requires a
future durable custody-transfer policy; omission of destruction must never be
treated as implicit retention.

Environment and provider identity remain outside canonical Activity and Net
semantics. An application may derive the territory operation identity from its
stable Episode or host-operation identity and use Motus lookup-before-create on
reconstruction, but may not make a provider lease the semantic identity of the
Activity.

CV10.DS1 qualifies a failed Codex runtime operation, a replacement runtime
operation, and a later native resume through one existing Episode Attachment.
It does not implement or qualify Motus Activity retry, claimant reassignment,
or worker reconstruction. A future Activity integration must derive territory
identity from the stable Episode or host operation rather than attempt-local
identity.

## Rationale

Independent custody means the resource is separately addressable, observable,
recoverable, and cleanable. It does not mean Activity lifetime ownership. A
territory per attempt would discard useful workspace and runtime locality,
amplify provider startup cost, and turn ordinary retries into unrelated
resources that require orphan cleanup.

Episode ownership matches the existing Agenticus Attachment boundary: one
immutable resolution, one exact lease, one attachment epoch, scoped Hands, and
an ordered drain/export/destroy transition. Provider lookup-before-create and
lease provenance already preserve identity without placing provider concepts
in Impetus History.

## Options Considered

- **One territory per Activity attempt.** Rejected as the default because it is
  excessively ephemeral and makes retries replace resources rather than resume
  bounded work.
- **One territory per Thread or agent installation.** Rejected because those
  lifetimes outlive the bounded authority, workspace, grant, and cleanup
  boundary.
- **A universal Session abstraction.** Rejected; the existing Episode,
  Attachment, Motus lease, runtime Continuation, and provider session name
  distinct lifetimes and should not be collapsed.
- **Implicit retention when cleanup is skipped.** Rejected because it loses
  custody. Retention needs an explicit durable owner and later destruction
  obligation.

## Consequences

- CV10 qualification targets Episode/operation-owned territories, not
  per-Activity territories.
- Runtime profile vocabulary must say when a collocated territory is
  Episode-scoped. The v1 `ephemeral-collocated` offer remains for compatibility
  while `episode-collocated` carries the canonical ownership meaning.
- Replacement-runtime evidence must prove stable territory identity; formal
  Motus Activity retry evidence remains a separate qualification.
- Completion remains gated on export plus verified destruction until a future
  retention story establishes durable custody transfer and orphan
  reconciliation.

## Review Trigger

Revisit when a supported use case requires retained territories across Episode
boundaries, or when a non-local Motus Activity composition needs a public
provider-neutral way to recover an Episode attachment from durable operation
identity.
