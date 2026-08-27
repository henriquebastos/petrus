---
code: CV20.DS3.TS2
level: Technical Story
status: Done
status_reason: >-
  Strict source custody, dense flat lineage, replay-derived navigation,
  producer-backed mixed/negative fixtures, and the owner spec are verified.
updated: 2026-08-27
related:
  - ../../cv20-ds3-live-understanding.md
  - ../../../../exploration/es-061-portable-net-document-and-forkable-execution-lineage/index.md
  - ../cv20-ds3-ts1-portable-definition-view/index.md
  - plan.md
  - experience-report.md
---

# CV20.DS3.TS2 — Forkable execution lineage foundation

## Intent

Add one optional strict execution-lineage component to the existing Petrus Net
document so observed evidence, manual hypotheses, and simulated descendants
share one navigable parent-linked entry list without changing canonical runtime
History or weakening retained source custody.

## Acceptance / Done condition

1. Existing definition-only and arranged document v1 files remain byte- and
   behavior-compatible while lineage becomes one optional non-null component.
2. A lineage has dense evidence-source ids, dense explicit entry ids equal to
   array indexes, one root, smaller parent ids, and a head naming an entry.
3. Observed and simulated evolution use the same exact `history-record` fact;
   a manual marking replacement is an explicit distinct fact in the same list.
4. Exact retained observation-capture and simulation-result bytes pass strict
   source admission, SHA-256 custody, definition equality, complete History,
   replay, snapshot, source-position coverage, and provenance checks.
5. Later observed evidence exactly extends an observed same-Instance prefix;
   simulation begins from its document-parent marking; hypotheses can never be
   presented as observed descendants.
6. Optional checkpoints agree with replay-derived state, and Petrus publishes
   one source-independent navigation projection plus producer-backed mixed-fork
   and negative conformance fixtures.

## Driver QA and evidence plan

- Promote only the accepted anchored uniform-entry candidate, not the rejected
  unanchored or whole-artifact-per-step alternatives.
- Begin with focused tests copied as semantic vectors, then implement public
  frozen wire models, strict admission, deterministic serialization, replay,
  custody, projection, and fixture generation.
- Retain exact current source protocols and canonical History codecs rather
  than adding converters or new runtime records.
- Run focused document, History, observation, and simulation tests; project
  structural tests; quick static checks; and the broad repository gate to the
  extent this orb's Docker/Graphviz capabilities permit.

## Out of scope

- Arx branch navigation, “Explore from here,” edit confirmation, and Save As
  behavior.
- Attachment stores, source deduplication, signatures, producer authenticity,
  encryption, or a final large-artifact size policy.
- Runtime History branching, `Instance.resume`, implementation/provider
  bindings, or claims that a document point is executable or resumable.
- Manual patch operations beyond complete marking replacement.
- A capable simulation profile or application-bound Hamsterdan V5 fork.
