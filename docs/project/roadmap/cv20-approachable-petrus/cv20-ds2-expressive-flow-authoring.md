---
code: CV20.DS2
level: Delivery Story
status: Planned
status_reason: >-
  ES-056 and Hamsterdan authoring experiments provide a candidate direction,
  but AX29 and a one-PR vertical slice must select the default vocabulary and
  prove deliberate low-level descent before public delivery.
updated: 2026-08-27
related:
  - index.md
  - ../../exploration/es-056-progressive-disclosure-developer-experience/index.md
---

# CV20.DS2 — Expressive flow authoring

## Intent

Let developers read and write domain flow first—typed work leaves, sequence,
branch, join, wait, loop, failure, and named composition boundaries—while every
construct still compiles to canonical Petrus topology and any unsupported shape
can descend deliberately to the low-level Net kernel.

## Scope

- Review the retained Hamsterdan structured-authoring candidates without
  copying application vocabulary into Petrus.
- Execute AX29 to prove a mixed high-level/low-level source compiles, validates,
  renders, and runs without changing semantics.
- Select one documented default authoring surface and deterministic composition
  errors; alternatives remain lower-level APIs, not peer beginner choices.
- Preserve source attribution from authored elements to generated canonical
  nodes and binding diagnostics.
- Exercise the one-PR Hamsterdan vertical slice before a full architecture model.

## Candidate story seeds

- **TS1 — Authoring kernel and descent contract.** Freeze the smallest generic
  block/composition vocabulary and prove AX29 against canonical compilation.
- **US1 — Readable one-PR flow.** Express the representative Hamsterdan slice
  with every durable decision, wait, join, failure, and effect gate visible.
- **US2 — Local composition diagnostics.** Report type, port, soundness,
  binding, and generated-node attribution failures at the authored boundary.

## Acceptance / Done condition

1. A reviewer can identify every durable decision and external-effect gate in
   the one-PR source and its compiled topology.
2. Sequence, branch, join, loop, wait, failure, and typed exits compile through
   one deterministic composition contract rather than host-local control flow.
3. One source mixes the recommended layer with direct places, transitions,
   arcs, guards, and handlers without bypassing validation or replay.
4. Deliberate mistakes fail before motion with authored locations and concrete
   remedies.
5. Full Hamsterdan modeling reports unsupported constructs honestly; successful
   experimentation does not imply production migration.

## Driver QA and evidence plan

- Execute AX29 and fixed-point canonical definition/rendering checks.
- Compare authored and generated topology for the one-PR vertical slice.
- Run negative composition and binding diagnostics with exact source locations.
- Run focused compiler/runtime tests and the complete repository gate.

## Out of scope

- Optimizing primarily for source-line or arc-count reduction.
- Inferring global topology from Python type coincidence.
- Making arbitrary Python control flow durable.
- Generating authoring packages before DS4.
