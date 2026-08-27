---
code: ES-061
title: Portable net document and forkable execution lineage
status: Completed
status_reason: >-
  The Navigator accepted one Petrus Net document with optional view and one
  direct-marking lineage shared by observed, manual, and simulated steps. The
  candidate was promoted to CV20.DS3 and verified across Petrus, Arx, and the
  Hamsterdan V5 pressure test.
opened: 2026-08-26
updated: 2026-08-27
related:
  - ES-056
  - CV20
  - CV20.DS3
  - CV11
  - CV12
  - CV13
  - CV14
  - CV15
  - CV17
  - CV18
  - docs/product/principles.md
  - docs/project/decisions/records/2026-07-06T0229Z-hermes-adr-0030-all-transition-firings-belong-to-unified-event-history.md
  - docs/project/decisions/records/2026-07-06T1105Z-hermes-adr-0033-canonical-event-history-is-uncompacted-tracing-log.md
  - docs/project/decisions/records/2026-07-08T1725Z-explicit-token-records-and-replay-by-reapplication.md
  - docs/project/decisions/records/2026-08-03T2130Z-flat-json-is-the-canonical-net-definition-interchange.md
  - spec/event-history.md
  - spec/net-definition-v3.md
  - spec/net-document-v1.md
evidence_repositories:
  - repository: https://github.com/henriquebastos/petrus-arx
    revision: 1e81a8ddccf959597eb8d8e392182d80753be765
  - repository: https://github.com/henriquebastos/hamsterdan
    revision: cb09ee68ebda42dae966351b373501df7bf803e6
promotes_to:
  - CV20.DS3
promoted_to:
  - CV20.DS3
promoted_at: 2026-08-27
---

# Portable net document and forkable execution lineage

## Inquiry

Can Petrus define one strict portable file that lets a person arrange and
understand a Net before execution, inspect an observed run, and explore
hypothetical descendants without separate definition, capture, simulation, and
editor data models?

Hamsterdan V5 made the problem concrete. Its Python DSL builds a 108-place,
137-transition, 570-arc Net. Petrus could project the definition, but the old
inspection route opened in a static SVG rather than Arx's zoomable, pannable,
arrangeable canvas. The previous execution formats also forced consumers to
choose different models for observation, simulation, and editing.

## Accepted result

The accepted `petrus-net-document/version 1` is the only portable Petrus file
format:

- `definition` is required and retains exact canonical Net-definition v3
  semantics;
- `view` is optional and currently stores portable node positions;
- `lineage` is optional and stores one parent-linked list of execution states;
  and
- there are no alternate inspection, capture, or simulation-result envelopes,
  compatibility readers, source artifacts, hashes/base64 custody, fact unions,
  checkpoints, or replay navigation.

Every lineage entry has exactly the same state-bearing fields:

```json
{
  "id": 3,
  "parent": 2,
  "provenance": "simulated",
  "marking": [],
  "metadata": {}
}
```

`marking` is always the complete sparse marking at that step. Arx selects it
directly, regardless of provenance. `metadata` may retain History records,
Instance identity, simulation context, a manual note, or other strict JSON,
but it is never needed to compute state or ancestry.

## Complete lineage example

The following branch contains a real observed path and a hypothetical path in
one list:

```json
{
  "head": 3,
  "entries": [
    {
      "id": 0,
      "parent": null,
      "provenance": "observed",
      "marking": [
        {
          "place": "pending",
          "tokens": [
            {"color": "Work", "data": {"result": "failed"}}
          ]
        }
      ],
      "metadata": {"instance": "production-42"}
    },
    {
      "id": 1,
      "parent": 0,
      "provenance": "observed",
      "marking": [
        {
          "place": "done",
          "tokens": [
            {"color": "Work", "data": {"result": "failed"}}
          ]
        }
      ],
      "metadata": {"history_record": {"record": "FiringCompleted"}}
    },
    {
      "id": 2,
      "parent": 0,
      "provenance": "manual",
      "marking": [
        {
          "place": "pending",
          "tokens": [
            {"color": "Work", "data": {"result": "succeeded"}}
          ]
        }
      ],
      "metadata": {"note": "What if the input had succeeded?"}
    },
    {
      "id": 3,
      "parent": 2,
      "provenance": "simulated",
      "marking": [
        {
          "place": "done",
          "tokens": [
            {"color": "Work", "data": {"result": "succeeded"}}
          ]
        }
      ],
      "metadata": {"history_record": {"record": "FiringCompleted"}}
    }
  ]
}
```

The relationships are deliberate:

1. `id` equals the array index. A new entry gets the prior `entries.length`.
2. Entry 0 is the sole root. Every later `parent` names a smaller id.
3. Entries 1 and 2 share parent 0, so the branch needs no separate branch
   structure.
4. `head: 3` persists the selected point. It can name any entry, not only the
   last one.
5. Entry 2 is `manual` because a person authored that complete marking.
6. Entry 3 is `simulated` because Petrus computed the successor from entry 2.
   The manual parent does not make the computed child manual; ancestry already
   records that the experiment began from a hypothesis.

The same rule applies when a person chooses an enabled transition. Choosing the
transition is a user decision, but the successor is `simulated` when Petrus
applies Net semantics. If an external Activity needs a hypothetical result, the
UI may collect that result as input metadata; once Petrus computes the resulting
marking, the new entry remains `simulated`.

## Provenance and authority

- `observed` means the marking was projected from a real Petrus History state.
- `manual` means a person directly authored the complete marking. It may be a
  useful hypothesis even when no Net transition can reach it.
- `simulated` means Petrus computed the marking from a parent under Net and
  implementation semantics.

Provenance belongs to each entry, not to the whole document or branch. A single
branch may therefore be observed, then manual, then simulated without changing
shape or navigation code.

Canonical runtime History remains one append-only linear log for one Instance.
The portable lineage is a navigable document projection and may branch. History
may appear in metadata for diagnosis, but it does not compete with the complete
marking as navigation authority and the document does not become resume or
production-authenticity authority.

Observed entries are protected from in-place editing. “Explore from here”
appends a manual child and Save As persists the resulting hypothetical document.
The original observed file is not rewritten as if the hypothesis happened in
production.

## Ownership

Petrus owns the file contract, definition identity, marking and token rules,
lineage invariants, provenance, strict parsing, serialization, and runtime
materialization.

Arx owns interaction and presentation: the shared canvas, zoom and pan,
arrangement, lineage navigation, marking display, manual forking, hosted
simulation requests, and file custody.

Hamsterdan owns the application-built V5 Net, implementation bindings,
representative production evidence, and the large application acceptance case.

## Delivery evidence

- Petrus owner fixtures cover definition-only, mixed lineage, observed
  materialization, simulated materialization, and strict invalid lineage.
- Petrus `scripts/check full` passed all static and structural gates with
  **2,456 tests passed**.
- Arx `pnpm check` passed all typechecks, lint/style/dependency checks,
  **1,144 tests**, **49/49 conformance checks**, and its production build.
- Arx opened the exact Hamsterdan V5 document, rendered 108 places, 137
  transitions, and 570 arcs, then preserved arrangement through Save As and
  reopen without changing definition identity
  `70e3778ec802435a8e57456cc7e4edce04be30b91a6a65e53afa0d122f47e1e2`.
- The shared workspace also navigated direct markings, appended and edited a
  manual child, and appended a Petrus-hosted simulated lineage below a manual
  parent.

## Current simulation boundary and follow-up

The current `implementation-free-v1` hosted simulator is a safe, detached,
pure-Net profile. It is not the final V5 design tool. It refuses V5 because V5
has Python handlers and exceeds that profile's 128-transition and 512-arc
bounds. This does not mean Petrus cannot run V5; production Petrus already runs
it with Hamsterdan-owned bindings.

CV20.DS3 retains the next application-bound capability: from any lineage entry,
choose an enabled transition, let a Petrus service compute the successor with
the real application bindings, and pause at external-effect boundaries for a
hypothetical result instead of performing the real effect. The returned state
appends as `simulated`, including when its parent is manual. Arx should present
this as advancing the existing lineage with Petrus, not as a second workspace
or file mode.

No new Exploration or Value is needed for that work. It is a planned Delivery
follow-up under the existing CV20.DS3 application-bound simulation boundary.

## Historical experiment boundary

ES-061 initially tested retained capture/simulation source anchors, record
facts, replay-derived markings, and checkpoints. The Navigator superseded that
candidate before release because direct complete markings remove the extra
consumer logic. Those experiments remain historical evidence under this
Exploration and in Git history; they are not current protocol authority.

The normative result is [the Net document specification](../../../spec/net-document-v1.md),
and Delivery continues under
[CV20.DS3 — Live understanding](../../roadmap/cv20-approachable-petrus/cv20-ds3-live-understanding.md).
