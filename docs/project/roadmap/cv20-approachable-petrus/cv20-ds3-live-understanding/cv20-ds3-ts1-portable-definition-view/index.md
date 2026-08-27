---
code: CV20.DS3.TS1
level: Technical Story
status: Done
status_reason: >-
  Strict document models, parser, serializer, identity, projection, owner spec,
  and interoperability fixtures are verified; Arx consumed the exact fixture
  and completed the real Hamsterdan V5 arrangement route.
updated: 2026-08-27
related:
  - ../../cv20-ds3-live-understanding.md
  - ../../../../exploration/es-061-portable-net-document-and-forkable-execution-lineage/index.md
  - plan.md
  - experience-report.md
---

# CV20.DS3.TS1 — Portable definition and view document foundation

## Intent

Give Petrus one strict portable document foundation that carries an exact
canonical Net v3 definition and an optional portable node arrangement without
changing Net identity or claiming runtime, History, or simulation authority.

## Acceptance / Done condition

1. Definition-only and arranged `petrus-net-document` v1 files strictly parse,
   deterministically serialize, and survive parse/serialize fixed points.
2. The required embedded v3 definition compiles through the existing canonical
   boundary; its SHA-256 identity is computed from canonical v3 bytes and is
   unchanged by adding or moving view positions.
3. The optional view contains only finite coordinates for unique, canonical,
   definition-owned node paths in canonical order; partial layouts are valid.
4. Duplicate members, non-finite numbers, unknown or null components,
   unsupported discriminators, duplicate/foreign/noncanonical nodes, and
   malformed embedded definitions are refused before publication.
5. Petrus publishes the owner spec, generated schema, positive and negative
   fixtures, and a Net projection suitable for the Arx consumer story.

## Driver QA and evidence plan

- Use strict red/green tests around parsing, identity, projection, fixed points,
  coordinate admission, and malformed/confused inputs.
- Verify generated JSON Schema and retained fixtures match the production model.
- Run focused Impetus suites, project structural tests, and the repository gate
  justified by the production protocol change.
- Hand exact owner fixtures and revision provenance to Arx before its consumer
  implementation begins.

## Out of scope

- Forkable lineage, source anchors, checkpoints, markings, History records, and
  manual/simulated/observed provenance.
- Camera state, waypoints, annotations, panels, selection, and other Arx-local
  session state.
- Arx interaction code, Hamsterdan production migration, execution bindings,
  resume authority, or a capable V5 simulation profile.

## Notes

This is an additive foundation for the accepted one-document direction, not a
second format. A later story adds the optional strict lineage component to the
same v1 envelope before CV20.DS3 closes.
