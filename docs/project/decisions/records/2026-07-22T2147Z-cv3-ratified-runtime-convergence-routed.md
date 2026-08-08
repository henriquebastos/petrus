---
status: Decided
raised: 2026-07-18
decided: 2026-07-22
deciders:
  - henrique (Navigator)
supersedes:
  - CV3's pending-ratification status after its evidence-preserving merge
  - treating CV3's provisional package homes, helper names, compatibility exports, AuthoritySession, capability vocabulary, or Attempt mapping as doctrine
related:
  - docs/project/decisions/records/2026-07-15T0110Z-absurd-execution-substrate.md
  - docs/project/decisions/records/2026-07-22T0245Z-engine-is-one-live-instance-composition.md
  - docs/project/decisions/records/2026-07-22T1031Z-instance-authors-terminal-history-and-shared-firing-transform.md
  - docs/project/decisions/records/2026-07-22T1413Z-candidate-selection-is-instance-scoped-immutable-policy.md
  - docs/project/decisions/records/2026-07-22T1539Z-engine-routes-activities-through-operational-queues.md
  - docs/project/decisions/records/2026-07-22T1816Z-dispatch-leases-attempts-devops-operates-workers.md
  - docs/project/decisions/records/2026-07-22T1930Z-dispatch-snapshots-heartbeat-details-observation-remains-optional.md
  - docs/project/decisions/records/2026-07-22T2005Z-pre-release-apis-carry-no-compatibility-promise.md
---

# CV3 is the delivered runtime-topology proof; first-version convergence is separate

## Question

Does the merged CV3 dispatch-plane build constitute accepted runtime-topology
evidence, and if so which of its behavior and temporary implementation choices
become doctrine? Where should the substantial implementation work implied by
the later concept-first rulings live?

## Decision

Ratify and close CV3 as the delivered proof that one durable Petrinet Instance
can run inline or across PostgreSQL, Absurd, and separate Worker processes while
preserving canonical semantics and crash recovery. CV3's four Delivery Stories
and parent Value are **Done**.

The following demonstrated behavior and invariants are accepted:

- schema-v2 records, occurrence/delivery identity, and loud refusal of
  incompatible persisted data;
- the canonical Activity request/outcome lifecycle, with accepted outcomes
  frozen before deterministic projection and completed external work not
  re-executed when projection remains pending;
- replay coherence, duplicate/conflicting outcome handling, single-writer
  whole-action coordination, and detached observation of writer-owned live
  state;
- the common semantic History contract across memory, JSONL, and PostgreSQL,
  including atomic PostgreSQL batches and verify-if-equal conflicts;
- rollback invalidating live derivation and requiring reconstruction, plus
  canonical per-Instance event ordering;
- joined begin/spawn/doorbell transaction behavior and stable occurrence
  recovery identity;
- Workers reporting operational outcomes while Instance authors canonical
  History; and
- process placement not changing canonical semantics.

Ratification does **not** make CV3's temporary architecture doctrine. In
particular it does not adopt the old `impetus.execution`, `impetus.firing`, or
`impetus.postgres` package homes; `AuthoritySession`; the old Runner and
coordination surface; the exact current `Instance.complete()` door;
`runtime_checkable` as a permanent ActivityHandler requirement; helper names
such as `InlineDispatcher`; fixture/port/index choices beyond the accepted
invariants; root exports or optional-package import workarounds; Worker
capability vocabulary; or the current attempts mapping as the final
heartbeat/reassignment contract.

DEC-034 through DEC-040 govern every overlap: one live Engine composes one
durable Instance; Instance authors terminal History through a shared future
history-independent firing transform; Candidate Selection is per-Instance
immutable policy; Engines route Activities through operational queues;
Dispatch leases heartbeating Attempts while DevOps operates Workers; Dispatch
snapshots one optional application-defined heartbeat-details value; and
pre-release aliases carry no compatibility promise. The original Absurd
substrate decision remains the historical basis except where those later
records explicitly supersede it.

Route the substantial missing implementation as **CV6 — First-version runtime
convergence**, separate from the completed CV3 evidence. CV6 contains bounded
Technical Stories for the one-Instance Engine, history-independent firing,
Candidate Selection, operational Activity queue routing, and Attempt
heartbeats/details, and includes the pre-release compatibility cleanup as
linked Maintenance. Every unit still requires its normal Plan Checkpoint.

CV6 names a coherent convergence program, not the complete first release. This
decision chooses no release version, support contract, or placement for CV4,
CV5, or other product and research lanes.

## Rationale

CV3's central claim is already demonstrated: inline and split runs produced
byte-identical 66-record histories; Engine-side restart resumed exactly;
Worker lease-expiry redispatch preserved one externally deduplicated effect;
pre- and post-dispatch failures did not double-spawn; and doorbell plus polling
fallback worked. The historical build reached 737 passing tests. After the
concept-first refactor, the frozen suite recorded 1,871 passed and 5 skipped,
with 189 focused structural/topology/selection checks. A fresh current-main
topology demonstration on 2026-07-22 passed both tests.

Holding CV3 open until later refactoring would confuse proof with product
convergence. Conversely, blessing every spelling in a successful experiment
would contradict the later, more precise ontology rulings. Closing the proven
Value while routing its remaining work separately preserves both facts.

## Options Considered

- **Keep CV3 Active until every convergence story ships.** Rejected: this
  makes an already-delivered topology proof responsible for later architecture
  convergence and leaves its claim permanently ambiguous.
- **Ratify CV3 wholesale, including temporary APIs and package homes.**
  Rejected: later decisions deliberately supersede those choices.
- **Ratify only behavior, close CV3, and route convergence separately —
  chosen.** This accepts the evidence without freezing scaffolding.

## Consequences

- CV3 is Done and no longer owns Planned follow-up stories.
- CV6 owns the five bounded runtime-convergence Technical Stories. Existing
  story files move there with new codes; their acceptance constraints do not
  change.
- Pre-release compatibility cleanup remains a Maintenance item linked into
  CV6 rather than being misrepresented as already delivered.
- Historical CV3 reports and worklogs remain evidence of what was built. New
  routing annotations may point to CV6, but historical claims are not rewritten
  into current ontology.
- CV4, CV5, and the remainder of a first release keep their independently
  ruled status and priority.

## Review Trigger

Review CV6's boundary only if one of its stories proves dependent on a wider
release contract or on another Value's product scope. Do not reopen CV3 merely
because a temporary implementation choice is replaced while preserving the
ratified behavior.
