---
status: Decided
raised: 2026-07-08
decided: 2026-07-08
deciders:
  - henrique (Navigator)
supersedes:
related:
  - docs/project/decisions/records/2026-07-06T0325Z-hermes-adr-0031-minimal-event-history-record-model.md
  - docs/project/decisions/records/2026-07-06T1128Z-hermes-adr-0035-event-history-records-activities-not-worker-mechanics.md
  - docs/project/decisions/records/2026-06-24T1344Z-hermes-adr-0025-flattened-net-assigns-uris-to-all-declarations.md
  - docs/project/decisions/records/2026-07-14T2016Z-activity-invocation-runtime-seam.md
---

# Four spec details are intentionally deferred to kernel time

## Question

Four remaining `**OPEN**` markers are genuinely implementation-revealed — they
cannot be settled well before a kernel exists. Rather than leave them as
floating unresolved gaps, decide to **defer them intentionally**, each with a
review trigger.

## Decision

The following are **deferred to kernel implementation**, not unresolved design
gaps. The governing decisions listed already fix the *principles*; only the
listed *details* wait.

1. **Source maps** (`net-schema.md`) — the model for tracing flattened-net
   elements back to authoring file/subnet/mount/local-symbol. A tooling/debug
   feature with no core-semantics impact [ADR 0025]. *Revisit:* when the editor
   or a debugger needs source mapping.
2. **Event-history record payload schemas** (`event-history.md`) — exact fields
   per ADR 0031 category and whether "firing candidate selected" is durable
   before "firing begun". The semantic categories are fixed [ADR 0031, as
   revised by DR 2026-07-14 activity-invocation-runtime-seam]; only payload
   shapes wait. Retry grouping, originally deferred here, was decided
   2026-07-14: operational retries are activity attempts against one frozen
   activity invocation, outside canonical history. (Token movements are
   explicit records, already decided
   [DR explicit-token-records-and-replay-by-reapplication].) *Revisit:* when the
   kernel fixes record schemas.
3. **Activity-attempt vs worker-delivery-attempt boundary** (`event-history.md`)
   — **decided 2026-07-14**, ahead of its worker-layer trigger
   [DR 2026-07-14 activity-invocation-runtime-seam]: canonical history carries
   exactly the frozen `ActivityRequested` and its terminal
   `ActivityCompleted`/`ActivityFailed`; every attempt, claim, lease, and
   queue/server handoff is execution-adapter state — durable if coordination
   needs it, but reconstructible from the activity lifecycle facts.
4. **Per-language handler contract-declaration shape** (`handler-contract.md`) —
   how a handler declares its typed inputs/outputs in a specific binding
   language (Python vs TypeScript) [ADR 0020]. A binding-layer detail; nominal
   color matching is already decided
   [DR handler-symbols-guards-and-nominal-color-matching]. *Revisit:* when the
   first binding is implemented.

## Consequences

- The corresponding `**OPEN:**` markers in the spec are reworded to
  **DEFERRED (kernel)** pointing here, so the spec carries no unresolved OPENs —
  only decided answers and tracked deferrals.

## Review Trigger

Each item names its own trigger above. None may be silently resolved by
implementation drift — each returns to a decision record when its trigger fires.
