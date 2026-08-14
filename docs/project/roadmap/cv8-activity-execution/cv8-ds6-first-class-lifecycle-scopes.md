---
code: CV8.DS6
level: Delivery Story
status: Done
status_reason: History-first lifecycle scopes are implemented, independently reviewed, and release-qualified across Local and pinned Absurd providers
updated: 2026-08-11
related:
  - ES-051
  - docs/project/decisions/records/2026-08-11T0101Z-history-first-lifecycle-scopes.md
---

# First-class lifecycle scopes

## Intent

Let a host replace one generation of workflow work through a canonical Engine
operation instead of application retirement topology, without weakening
History truth, Dispatch fencing, or current unscoped behavior.

## Scope

- Add immutable `(name, generation)` lifecycle identities and canonical
  open/close/reset History records, codecs, folds, and replay.
- Give queued tokens durable occurrence identity and lifecycle provenance
  through consume, read, produce, and Activity request boundaries.
- Expose Engine scope lifecycle doors; make reset atomic and ordering
  deterministic.
- Treat close/reset as a recoverable post-commit cancellation outbox and fence
  pending, claimed, and running Local and supported Durable custody.
- Quarantine late terminal reports durably with exact-redelivery acknowledgement
  and conflict rejection.
- Disposition exact closed-generation ingress as acknowledged/drop and
  uncertain-generation ingress as quarantine.
- Preserve unscoped APIs and existing Activity Execution V2 / Instance-scoped
  Worker behavior.

## Acceptance / Done Condition

1. Duplicate-valued queued tokens are discarded by exact occurrence identity,
   and replay reconstructs active scopes, queue provenance, cancelled work,
   cancellation instructions, and quarantine.
2. Completion-before-close and close-before-completion are deterministic by
   append order at equal instants; reset has no unscoped semantic gap.
3. Close/reset append refusal exposes no Dispatch cancellation; a crash after
   append repairs cancellation on load.
4. Pending, claimed, and running custody is explicitly fenced, with cancelled
   terminal or late-report quarantine behavior matching each supported
   provider's honest contract.
5. Exact terminal redelivery acknowledges, conflicting redelivery fails, and
   no late report mutates a closed generation.
6. Exact closed-generation delivery is acknowledged/dropped, uncertain
   generation is quarantined, and both dispositions replay.
7. Existing unscoped, synchronous, asynchronous, transport, Local, and
   qualified Absurd behavior remains green.

## Driver QA and Evidence Plan

Use TDD at the History/Instance, Engine/Coordinator, Local Dispatch, Absurd,
Worker transport, and ingress boundaries. Run explicit focused suites,
`scripts/check full`, `scripts/check release`, available real-provider
qualification, and an independent adversarial release-blocker review.

## Out of Scope

- Multi-Instance scheduling or PostgreSQL as a prerequisite.
- Hard cancellation or exactly-once external effects.
- Implicit consumed-input restoration or generic compensation.
- Same-generation business supersession or authority ownership.
- Framework, actor, module, capability-container, or provider-webhook runtime.

## Notes

The Hamsterdan and Petrus experiment branches are evidence only. Production is
implemented fresh from accepted Petrus `main`.

Canonical records without lifecycle or queue-entry provenance retain schema 4;
lifecycle/provenance records use schema 5, and both may interleave in one
History. Local Dispatch migrates operational schema 2 to 3 transactionally for
cancellation tombstones. Absurd uses its pinned provider tombstone without a
schema fork and refuses stronger cancellation semantics it cannot prove.

Validation passed 1,246 cross-boundary tests after replay/codec repairs, 449
focused lifecycle/provider/transport tests, `scripts/check full` with 2,168
tests, and `scripts/check release` with 2,168 parallel plus 2,168 fixed-order
tests. The real PostgreSQL + pinned Absurd lifecycle cancellation/restart route
passed separately with skips forbidden. Independent adversarial review approved
all four repaired boundaries and found no code release blocker.

Review found no new technical debt requiring a ledger item. Deliberate limits
remain explicit contracts: projection-pending terminals finish before close;
quarantine is audit-only; cancellation does not deny ambiguous effects; Absurd
rejects a post-cancellation Worker terminal and may clean provider tombstones;
Inline/In-Memory custody is process-local; observation snapshot v1 omits active
scopes. The additive pre-release capability does not change Petrus's displayed
`0.0.0` package version or claim a published release.
