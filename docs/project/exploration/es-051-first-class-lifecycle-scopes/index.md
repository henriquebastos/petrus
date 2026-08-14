---
code: ES-051
status: Completed
opened: 2026-08-11
related:
  - CV8.DS6
  - docs/project/decisions/records/2026-08-11T0101Z-history-first-lifecycle-scopes.md
---

# First-class lifecycle scopes

## Inquiry

What is the smallest provider-neutral production contract that can close or
reset one generation of workflow work exactly, including duplicate-valued
queued tokens and Activities already in operational custody, without making
Dispatch or a host scheduler canonical?

Hamsterdan RS-003 requires lifecycle replacement to become one first-class
runtime operation. The requirement is narrower than general business
supersession: a scope generation groups token occurrences and firing
occurrences whose future accepted execution must end together. Same-generation
operation ownership, provider-effect reconciliation, and domain compensation
remain separate application responsibilities.

## Evidence

1. `[R]` The approved Hamsterdan synthesis fixes durable scope identity as
   `(name, generation)`, makes append order the race authority, requires exact
   queued-occurrence cleanup without consumed-input restoration, and requires
   canonical close/reset to commit before Dispatch cancellation is visible.
2. `[R]` Lane 3's disposable Petrus model passed seven focused semantic tests
   and the then-current 2,074-test Petrus suite. It demonstrated atomic reset,
   append-failure behavior, duplicate-value cleanup by identity, pending and
   running cancellation intent, equal-instant append ordering, replay-stable
   late-result quarantine, and reset continuity.
3. `[X]` The disposable model did not integrate Engine, HistoryStore,
   Dispatch, or generic ingress. It cannot establish production behavior and
   its branch or runtime must not be copied.
4. `[E]` Current production inspection shows token queues retain value and
   entry instant but not durable occurrence identity or lifecycle provenance.
   `ActivityRequested` is the canonical outbox, while the provider-neutral
   Dispatch contract has only `dispatch` and `collect`.
5. `[E]` Current Local and Absurd custody already fence claims and terminal
   reports. Local can add an explicit cancelled terminal and epoch fence;
   pinned Absurd exposes durable task cancellation/tombstones that Petrus can
   integrate without claiming hard interruption or exactly-once effects.
6. `[E]` Production source delivery already records stable identity before
   projection and acknowledges exact redelivery. It has no generic generation
   target or quarantine contract, so lifecycle disposition must be added at
   that existing canonical door rather than delegated to provider webhooks.

## Alternatives

| Candidate | Benefit | Rejection or boundary |
| --- | --- | --- |
| Marking-side scope index | Small local edit | Refuted: value-only replay cannot identify duplicate occurrences exactly |
| Standalone scope runtime | Isolates implementation | Rejected: creates a second business truth outside real History and Engine |
| Cancel Dispatch before History | Fast operational fence | Rejected: append failure would leave custody contradicting canonical replay |
| Restore consumed inputs | Appears reversible | Rejected: claims accepted execution did not happen; compensation is domain work |
| Timestamp precedence | Familiar ordering | Refuted: equal instants require canonical append order |
| History-integrated occurrence provenance plus post-commit cancellation | Exact, replayable, provider-neutral | Accepted |

## Conclusion

Production lifecycle scopes belong in the existing History record union,
movement fold, Instance writer, Engine doors, and Dispatch providers. Queue
entries need durable identity and optional scope provenance; firing and
Activity records inherit that provenance. Close/reset records are canonical
terminal facts for affected occurrences and durable cancellation instructions.
Engine exposes cancellation only after the close/reset commit and reconciles
unapplied instructions after restart.

Exact active-generation ingress proceeds through the existing delivery door.
A proven closed target is recorded as acknowledged and dropped; a target whose
generation is not known is recorded as quarantined. Existing unscoped delivery
remains unchanged. No scope value contains live code, clients, credentials,
Engines, or other capabilities.

## Disposition

Promoted to `CV8.DS6` and the decided History-first lifecycle-scope record.
The experiment branches remain evidence only.
