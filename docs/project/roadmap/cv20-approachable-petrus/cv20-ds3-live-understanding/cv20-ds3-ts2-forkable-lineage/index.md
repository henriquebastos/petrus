---
code: CV20.DS3.TS2
level: Technical Story
status: Done
status_reason: >-
  One strict direct-marking lineage, observed and simulated producer
  materialization, and common Petrus/Arx consumption are implemented. The final
  Petrus full gate passed 2,456 tests and Arx passed its complete 1,144-test
  gate.
updated: 2026-08-27
related:
  - ../../cv20-ds3-live-understanding.md
  - ../../../../exploration/es-061-portable-net-document-and-forkable-execution-lineage/index.md
  - ../cv20-ds3-ts1-portable-definition-view/index.md
  - plan.md
  - experience-report.md
---

# CV20.DS3.TS2 — Direct-marking execution lineage foundation

## Intent

Add one optional strict marking lineage to the Petrus Net document so observed
production state, manual hypotheses, and simulated descendants share the same
direct navigation shape. Keep canonical runtime History linear and available
only as optional non-authoritative metadata in the portable document.

## Acceptance / Done condition

1. Definition-only and arranged documents remain valid while lineage becomes
   one optional non-null component of the same file format.
2. Every entry has exactly `id`, `parent`, `provenance`, a complete sparse
   `marking`, and strict-JSON `metadata`.
3. Entry ids equal array indexes; the sole root has a null parent; every later
   parent is smaller; and `head` names any existing entry.
4. `observed`, `simulated`, and `manual` entries have the same core shape and
   navigation selects their marking without replay.
5. Engine observation and hosted simulation materialize the same Net document
   format with complete per-entry markings and optional History metadata.
6. Owner fixtures cover definition-only, observed, simulated, manual, and
   mixed forks; strict negative fixtures cover lineage and marking laws.
7. Provenance is per entry: a person-authored marking may parent a Petrus-
   computed simulated successor without changing either entry's shape.

## Out of scope

- Runtime History branching or changing `Instance.resume`.
- Claims that a portable document is production-authentic, executable, or
  resumable.
- Source artifacts, hashes, base64 custody, checkpoints, replay navigation,
  attachment stores, or migration from an earlier unreleased file format.
- Capable application-bound Hamsterdan V5 simulation.
