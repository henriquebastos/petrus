---
code: ES-061
title: Portable net document and forkable execution lineage
status: Completed
status_reason: >-
  The Navigator accepted the bounded semantic Candidate and then promoted the
  broader Approachable Petrus Value as CV20. ES-061 now supplies CV20.DS3's
  portable definition/view/lineage semantics; public protocol, Arx V5, and
  application-bound execution remain Delivery acceptance work.
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
  - spec/net-inspection-v1.md
  - spec/observation-capture-v1.md
  - spec/simulation-result-v1.md
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

Can Petrus define one strict portable document that lets a person arrange and
understand a Net before execution, inspect an exact observed run, and explore
hypothetical descendants without multiplying definition, capture, simulation,
and editor-specific logic or weakening canonical Net and History authority?

The target is one consumer model and one persisted artifact with progressively
available components, not one bag of unrelated optional fields. A definition
is required. A portable view and execution lineage may be absent. When either
is present, its internal invariants remain strict.

## Current Story

The inquiry began with a concrete Hamsterdan V5 design problem. Its Python DSL
builds a 108-place, 137-transition, 570-arc Net. Petrus projects the exact
canonical inspection JSON, but Arx opens that inspection in a separate static
SVG renderer with no zoom, pan, direct arrangement, or layout persistence. The
useful shared canvas already has those interactions. Format and source
distinctions have leaked into separate user experiences instead of converging
on one way to understand a Net.

The Navigator recognized that the desired document recovers the useful shape
of the predecessor Petrus file: definition, optional presentation, and optional
execution state. The missing capability was durable forking. The predecessor
trajectory was a linear state array plus cursor; firing or editing from the
past truncated the old future. The desired model keeps both futures.

The accepted direction is one Petrus-owned document containing:

- the exact Net definition;
- an optional portable view, including at least node positions and other
  deliberately shared presentation;
- an optional flat list of immutable lineage entries;
- an explicit current `head` when lineage exists; and
- enough source custody to protect imported observed evidence.

Each lineage entry has an explicit non-negative sequential integer `id`,
assigned as the prior `entries.length`, and an explicit `parent`. The sole root
parent is null; every other parent references a smaller existing id. The file
writes ids rather than deriving identity only from array position, while
validation requires `entry.id` to equal its array index. Two entries may share
one parent, which is the fork.

Every state-changing entry records explicit provenance:

- `observed`: preserved authoritative evidence from a real Petrus Instance;
- `simulated`: state evolution computed by Petrus under a declared simulation
  scenario; or
- `manual`: a person directly intervened in a marking or value without a Net
  transition producing that change.

Provenance is never inferred from payload completeness. Production evidence
may be redacted, while simulation data may be complete and realistic.
User-directed selection of an enabled transition still produces simulated
records when Petrus computes the evolution. Direct token replacement is manual.
Moving a node changes only the view and never adds a lineage entry.

Observed evidence is protected rather than edited in place. An observed
Hamsterdan checkpoint may show a real failed CI run folded through `ci.assess`.
Exploring “what if the retry succeeded?” creates a manual child that introduces
the hypothetical state, followed by simulated descendants in which Petrus
computes evolution. A later real production retry may separately produce an
observed sibling. Saving creates or updates a new document; it never overwrites
the imported capture as if the hypothesis happened in production.

## Ownership Boundary

Petrus owns the portable semantic contract: exact definition, typed markings
and token payloads, lineage rules, provenance, validation, canonical
projections, and the distinction between inspectable and resumable points.

Arx owns interaction and presentation: the shared canvas, rendering, zoom and
pan, arrangement, timeline navigation, inspection, “Explore from here,” and
file custody. If a view field is portable across tools and sessions, Petrus
must define its wire meaning even though Arx is its first author. Ephemeral
selection, panels, transient gestures, and similar application state remain
Arx-local.

Hamsterdan owns neither protocol nor editor. It supplies the application-owned
V5 build, implementation bindings, representative production evidence, and the
large acceptance scenario that should expose false generality.

One owner means one canonical Petrus Exploration and later one Petrus protocol
decision. Arx and Hamsterdan link to those owners rather than copying the
decision into parallel Explorations.

## Critical Invariant and Resolution

One Petrus Instance owns one append-only, dense, linear canonical History. Its
positions are immutable, and replay derives state by reapplying explicit
records. A graph with two children cannot make both children the next canonical
position of one Instance. A manual intervention did not occur in the observed
Instance at all.

The document list is therefore a **derived portable lineage**, not canonical
runtime History. It composes exact records from unchanged source Histories with
explicit manual boundaries:

- one document History entry copies one exact canonical source record and
  retains its source id and source-local History position;
- observed and simulated canonical records use the same entry fact shape;
- one manual entry carries the explicit complete replacement marking;
- an optional materialized checkpoint asserts replay-derived state and can
  accelerate navigation; and
- immutable evidence anchors retain complete source artifacts so admission can
  verify every copied record, definition, Instance relation, and checkpoint.

Each capture or simulation result remains whole and authoritative for its own
linear per-Instance History. The document does not feed its parent graph to
`Instance.resume`, invent canonical manual records, or assign simulation
records to the observed Instance. Source-specific capture/result parsing occurs
once at document admission for custody. Consumers navigate the uniform entry
list and never open a hidden source timeline.

This resolves the tension without weakening either side. The one list is the
portable human/consumer sequence; canonical History remains the runtime truth
inside each retained source.

## AX1 — Contract, Identity, Authority, and Loss Map

Grades follow the project evidence convention. `[E]` means a Petrus test or
AX2 probe executed the claim. `[D]` means current source/spec review verified
it. No Arx or Hamsterdan operation is upgraded to `[E]` here.

| Surface | Exact field boundary | Identity and state | History relation | Authority, custody, and loss |
| --- | --- | --- | --- | --- |
| Net-definition v3 | `[E/D]` Exact `{format: "petrus-net-definition", version: 3, definition}`; strict parse, canonical compile, and deterministic serialization. | `[E/D]` Complete flat topology and declarations. Canonical serialized bytes supply the candidate definition digest. No layout, marking, implementations, or runtime state. | `[D]` No Instance or History. The optional Net name is descriptive, not identity. | `[E/D]` Sole current bidirectional definition interchange. Projection/compiler fixed points reject noncanonical documents. |
| Canonical inspection v1 | `[E/D]` Exact `{format: "petrus-canonical-net-inspection", version: 1, definition}`. | `[E/D]` Embeds the same v3-pinned definition body. No marking or layout. | `[D]` No Instance or History. | `[D]` One-way read-only build inspection. Re-enveloping its definition body can create an editable copy but cannot recover or mutate Python DSL source. |
| Observation capture v1 | `[E/D]` Exact `{format, version, snapshot, history}`. Snapshot is `{protocol, instance, definition, frontier, current}`; History is `{protocol, instance, after, next, frontier, records}` and is complete `[0,F)`. | `[E/D]` Snapshot pins the definition body and current marking/status/watermark/in-flight/armed/next-maturation at `F`. | `[E/D]` Dense array positions equal explicit record positions; position zero is matching `InstanceCreated`; replayed state agrees with the snapshot. | `[D]` Inspectable evidence, not a deployment or resumable Instance. Consumer owns file custody. Schema v1 has no digest, signature, executable version, bindings, or source-authenticity claim. |
| Simulation result v1 | `[E/D]` Exact `{format, version, profile, scenario, outcome, snapshot, history}`. | `[E/D]` Scenario declares initial marking/start/action cap; outcome and snapshot describe one fresh run. | `[E/D]` Complete dense canonical History belongs to a fresh disposable Engine; replay and outcome agree. | `[D]` Evidence under named `implementation-free-v1`, not continuation or all-path analysis. V5 exceeds transition/arc limits and uses forbidden handlers. |
| Canonical History | `[E/D]` One append-only ordered record sequence; current stores expose ordered records plus append/extend. Record payloads have strict schema-specific fields. | `[E/D]` Replay derives marking, watermark, registrations, scopes, and occurrences without rerunning handlers. Records do not carry a definition digest. | `[E/D]` One Instance, one writer, dense positions. `InstanceCreated` establishes Instance identity. | `[D]` Runtime truth. `Instance.resume` requires caller-supplied Net and implementations and continues the same History; a document graph cannot become this log. |
| Uniform AX2 document | `[E]` Exact `petrus-net-document/v1`; required complete v3 definition; strict optional view; lineage `{sources, head, entries}`. Entry fact is either `history-record {source, position, record}` or `manual-replace-marking {marking}`. | `[E]` Definition identity derives only from canonical v3 bytes. View is outside identity. Every entry resolves one marking; checkpoints are optional derived assertions. | `[E]` Entry ids are dense and equal indexes; `parent < id`; source ids are dense; every source position `[after,F)` appears exactly once. Each record is exact-equal to its retained source position. | `[E]` One navigation model above unchanged source authorities. Exact bytes plus SHA-256 prove internal custody/integrity, not producer authenticity. Manual state is explicit hypothesis, never observed fact. |

### Identity and authority conclusions

1. **Definition identity.** The document embeds one complete v3 envelope.
   Candidate identity is SHA-256 over Petrus canonical v3 serialization, not a
   second mutable field. Every retained source definition must equal it. `[E]`
2. **What one entry represents.** One entry is one navigable evolution fact:
   either one exact canonical History record or one explicit manual marking
   replacement. It is not an artifact container and not necessarily a
   resumable runtime position. `[E]`
3. **Why one list suffices.** The mixed fixture presents 14 canonical records
   plus one intervention through one normalized entry surface. The same loop
   sees observed start, manual intervention, simulated run, and later observed
   sibling. No loop opens a capture/result History. `[E]`
4. **Observed custody.** A source anchor keeps the exact original capture
   bytes. Entry records must equal the anchored positions. A later capture can
   set `after` to the prior frontier; its complete retained prefix must exactly
   equal the observed parent sequence, while only its suffix enters navigation.
   `[E]`
5. **Manual placement.** Manual replacement is an entry in the same parent
   graph. It is deliberately not a synthetic canonical record. A simulation
   source may begin from its state only when the declared initial marking is
   equal. `[E]`
6. **Simulation preservation.** Simulation entries project a fresh disposable
   Engine's canonical records without relabeling them as observed continuation.
   Source position zero starts source-local replay; the document parent records
   the hypothesis relation. `[E/D]`
7. **Inspectable versus resumable.** Every admitted entry is inspectable. None
   automatically grants History Store writer authority, implementation
   bindings, provider state, or live-host custody. `[D]`
8. **Provenance.** Strict provenance/source/fact checks reject relabeling. They
   cannot prove an upstream artifact came from production because current
   source formats make no signature or authenticity claim. `[E/D]`
9. **Portable view.** Direct canonical Net paths preserve node identity and
   view does not alter the definition digest. Arx revision `1e81a8d` stores
   `Record<string, [number, number]>`, validates positions with
   `Number.isFinite`, and also knows waypoints/annotations. AX2 accepts finite
   fractional evidence but deliberately leaves the protocol number type and
   portable subset open for AX3. `[D/E]`

## Executable Shape Comparison

### A. Uniform entries without evidence anchors — navigable, rejected for custody

The entries-only probe uses the same dense list and generic navigation surface.
It passes the mixed-fork loop. It also admits a canonically valid mutation to an
observed `CandidateSelected` record once anchors are removed. Nothing remains
to prove the record came from the imported capture. One list alone therefore
does not satisfy observed-evidence custody. `[E]`

### B. Uniform entries plus immutable source anchors — recommended Candidate

```json
{
  "format": "petrus-net-document",
  "version": 1,
  "definition": { "format": "petrus-net-definition", "version": 3, "definition": {} },
  "view": { "version": 1, "nodes": [{ "node": "ci.assessed", "x": 20.5, "y": 40 }] },
  "lineage": {
    "sources": [
      { "id": 0, "kind": "observation-capture", "after": 0, "artifact": { "sha256": "…", "base64": "…" } }
    ],
    "head": 2,
    "entries": [
      { "id": 0, "parent": null, "provenance": "observed", "fact": { "kind": "history-record", "source": 0, "position": 0, "record": {} } },
      { "id": 1, "parent": 0, "provenance": "observed", "fact": { "kind": "history-record", "source": 0, "position": 1, "record": {} }, "checkpoint": [] },
      { "id": 2, "parent": 1, "provenance": "manual", "fact": { "kind": "manual-replace-marking", "marking": [] } }
    ]
  }
}
```

Source-specific parsing is confined to admission and custody verification.
Navigation uses only `entries`. A later observed source with `after: 2` retains
its complete History but projects positions 2 onward, so the document list does
not repeat the prefix. This is the smallest tested model that satisfies both
one-list consumption and exact evidence relation. `[E]`

The prototype embeds source bytes inline for portability. Candidate semantics
require immutable anchors and exact record relation; final byte encoding,
deduplication, size bounds, or attachment mechanics remain Delivery design.

### C. Whole-artifact-per-checkpoint list — control, rejected

The first AX2 parser remains as an executable control. Its mixed fork has four
outer checkpoint containers and 16 records hidden across root capture,
simulation result, and later capture. The later capture repeats its complete
two-record prefix. Consumers must discriminate source formats and open nested
timelines to see events. Its 45 passing tests prove strict source validation,
not the Navigator's one-sequence requirement. `[E]`

### D. Parent-link canonical runtime History itself — rejected

Changing canonical History records into a branch graph would assign competing
next positions to one Instance and require invented manual records. It would
change writer, stores, replay, capture cursors, and resume semantics. The
document graph instead composes unchanged linear Histories. `[X]`

### E. Arx-only workspace — rejected owner

Arx could privately join existing formats and layout, but then semantic fork,
provenance, and custody become editor inventions unavailable to other
consumers. This conflicts with the accepted Petrus ownership boundary.

## Experiment Program

### AX1 — Contract and identity map

Trace exact fields and authority through canonical inspection v1, definition
v3, observation capture v1, simulation result v1, canonical History, and
directly relevant code. Produce a loss/authority map and compare concrete
document shapes.

**Result — complete `[E/D]`.** The map above is grounded in specs, projection
code, strict v3 parser/compiler, in-memory History Store, replay folds,
`Instance.resume`, observation capture, and simulation producer/tests. The
inspected source provides no predecessor implementation or reference
capture, so predecessor behavior remains accepted directional context rather
than upgraded source evidence.

### AX2 — Strict executable document spine

Build exploration-local parser/validator probes, not public APIs. Enforce
strict JSON and envelopes; explicit dense ids; `id == index`; root, parent, and
head invariants; provenance; definition-only, view, observed, manual,
simulated, and mixed forms; exact evidence relation; and malformed/confusion
refusal. Compare uniform entries, uniform entries plus anchors, and the
whole-artifact control.

**Result — complete `[E]`.** The
[`portable-document-spine`](experiments/portable-document-spine/README.md)
contains:

- the original whole-artifact control and its 45 tests;
- a uniform entries-only parser used to demonstrate the custody gap;
- the leading uniform-entry-plus-anchor parser;
- six producer-backed positive fixture forms; and
- 42 focused comparison, one-list navigation, strictness, replay, custody, and
  refusal tests.

The decisive mixed fixture has 15 navigable entries: two observed root records,
one manual replacement, seven simulated records, and five later-observed suffix
records. One list comprehension consumes all 15 through common fields. The
source table retains 16 nested source records because exact later-capture
custody includes the two-record prefix, but those artifacts are not navigation
units. Removing the table preserves the 15-entry loop and loses mutation
detection. Keeping it rejects mutation, prefix rewrite, provenance confusion,
source-kind confusion, missing coverage, and checkpoint disagreement.

The probes remain under ES-061 and add no public Petrus API.

### AX3 — Hamsterdan V5 arrangement round trip in Arx

Use the exact V5 canonical projection from Hamsterdan revision `cb09ee6`. Open
it on Arx's real shared canvas rather than the static inspection SVG; zoom,
pan, move representative nodes, save, close, and reopen. Verify exact canonical
definition identity is unchanged while portable view data round-trips.

**Status — not run.** Exact Arx revision `1e81a8d` provides `[D]` evidence for
finite floating-point positions, waypoints, and annotations, not the required
interaction/save/reopen result. AX3 must decide coordinate number semantics and
the smallest portable view subset from actual V5 behavior. Safe integers are
not accepted by AX2.

### AX4 — Capture-to-hypothesis fork

Start from one exact observed capture. Preserve its complete canonical History.
Create one explicit manual intervention, execute simulated descendants under a
declared profile, and retain a later observed future as a sibling. Save/reopen,
derive children from parents, and prove no hypothesis can be presented as part
of the original production capture.

**Result — Petrus-local semantic core complete `[E]`; V5 application case not
run.** AX2 executes the exact shape with real Petrus producers and serialize /
reopen validation. It proves source-local Histories, shared document entries,
manual boundaries, simulation initial-state equality, observed prefix custody,
and sibling ancestry.

The large V5 case still requires Hamsterdan bindings or a future capable
profile. Current `implementation-free-v1` cannot execute it: 137 transitions
exceed 128, 570 arcs exceed 512, and V5 uses handlers the profile forbids. No
Hamsterdan execution is claimed.

## Candidate Gate

| Gate | Result |
| --- | --- |
| One shape covers definition-only, arranged, observed, manual, simulated, and mixed fork | **Pass `[E]`** — six anchored positive forms. |
| One list and one consumer logic navigate observed records, intervention, simulation, and observed sibling | **Pass `[E]`** — one common 15-entry loop; no nested timeline access. |
| Canonical History remains linear and observed truth is not rewritten | **Pass `[E/D]`** — unchanged complete source Histories plus exact projected-record relation. |
| Strict ids, parent/head, source positions, envelopes, and provenance confusion are refused | **Pass `[E]`** — focused negative suite. |
| Capture-to-hypothesis survives serialize/reopen with observed sibling protected | **Pass for Petrus semantics `[E]`** — producer-backed mixed fork. |
| Source custody is necessary and sufficient for the bounded import case | **Pass `[E]`** — entries-only mutation admitted; anchored mutation refused. |
| Inspectable/resumable and implementation-profile limits are honest | **Pass `[D]`** — points are inspectable only; V5 is outside the current profile. |
| Hamsterdan V5 layout survives Arx save/reopen | **Not run; Delivery acceptance.** It can revise view fields and coordinate semantics but not the proven lineage composition. |
| Hamsterdan V5 application-bound fork executes | **Not run; Delivery acceptance.** It must validate profile/binding integration; current inability is explicit. |
| Evidence permits roadmap judgment under one protocol owner | **Pass; promoted to CV20.DS3.** Delivery retains one Petrus protocol owner. |

## Accepted Candidate Direction

On 2026-08-27, the Navigator accepted the bounded semantic shape, not either
exploration-local prototype:

- one Petrus-owned document with one exact v3 definition;
- strict optional portable view outside definition identity and lineage;
- one dense parent-linked `entries` list;
- one common canonical-record fact for observed and simulated evolution;
- one explicit manual intervention fact in that same list;
- optional replay-checked checkpoints; and
- immutable source anchors used only to prove exact custody and source
  relations at admission.

Keep canonical History, observation capture, simulation result, and
`Instance.resume` contracts unchanged.

AX3 and the V5 AX4 case are Delivery acceptance rather than Candidate blockers.
The remaining evidence may revise view representation, source encoding, size
strategy, UX, or the application-bound simulation profile. It is not needed to
decide what a document entry means, whether one consumer list works, or how
that list composes with linear per-Instance History. No Arx or Hamsterdan
experiment is claimed here.

## Unresolved Navigator and Delivery Decisions

These choices do not block the bounded Candidate and have no invented
Navigator acceptance:

- retain or rename `petrus-net-document`; the Driver recommends “document”
  because the artifact composes definition, view, and inspectable lineage
  without claiming runtime authority;
- choose the final view coordinate number contract after AX3; current evidence
  supports finite floating-point geometry, not an accepted integer bound;
- choose the deliberately portable view subset after V5 arrangement evidence;
- choose inline byte encoding, attachment mechanics, deduplication, and size
  limits for immutable source anchors during Delivery; and
- add manual operations beyond complete marking replacement only when a real
  interaction requires their semantics.

The Navigator promoted Approachable Petrus as CV20 and routed this Candidate to
CV20.DS3, with no separate Value for ES-061. Promotion does not settle the
choices above or relabel the exploration-local prototype as a public protocol.

## Verification — 2026-08-27

- `UV_FROZEN=1 uv run pytest -q …/test_document_spine.py
  …/test_uniform_spine.py` — **87 passed** after the uniform redesign.
- `UV_FROZEN=1 uv run pytest -q tests/petrus/impetus/test_net_definition.py
  tests/petrus/engine/test_observation.py
  tests/petrus/engine/test_simulation.py` — **91 passed**.
- `UV_FROZEN=1 uv run pytest -q
  tests/project/test_exploration_identity.py` — **1 passed**.
- `scripts/check quick …/portable-document-spine` — Ruff lint and format plus
  repository production typing passed after formatter correction.
- `scripts/check full` in the delegated Petrus evidence orb — **2,406 passed**
  with complete static and structural gates clean. The source-checkout rerun
  reached **2,143 passed** but could not complete because that orb has neither
  Docker nor Graphviz; Docker/PostgreSQL setup and SVG rendering accounted for
  the remaining 7 failures and 256 setup errors.
- Relative Markdown links, `git diff --check`, and generated-file cleanup are
  checked at closure.

## Accepted Handoff and Placement Boundary

ES-061 is promoted to
[CV20.DS3 — Live understanding](../../roadmap/cv20-approachable-petrus/cv20-ds3-live-understanding.md).
No separate Value is justified for this document contract, and this handoff
does not silently satisfy CV20's wider first-motion, authoring, profile, or
agent-experience gates.

Petrus delivers protocol, validation, projection, and producer/fixture seams
first. Arx then receives a Delivery Story under its existing current-Petrus
companion Value for shared-canvas and lineage experience. Hamsterdan remains
the application acceptance case rather than opening a Value unrelated to its
active private-production boundary.

Promotion creates roadmap intent, not a canonical History, runtime, Arx, or
Hamsterdan production change. CV20.DS3 owns those implementation and acceptance
boundaries now.

## Carry Forward Notes Accepted by the Navigator

- Use one Petrus-owned portable document as the product direction; “Arx
  workspace format” was a temporary and misleading label.
- Prefer component-level optionality (`view`, `lineage`) with strict internals,
  not an unconstrained optional-field soup.
- Write explicit sequential integer entry ids even though they equal array
  indexes; assign each new id from the prior `entries.length`.
- Keep explicit parent references because storage order cannot express ancestry
  after the first fork.
- Preserve explicit `observed`, `simulated`, and `manual` provenance.
- Protect observed evidence and branch through Save As rather than editing the
  original capture.
- Keep canvas arrangement outside execution lineage and canonical Net identity.
- Normalize boundary formats once for consumers without weakening their strict
  source validation or inventing equivalent authority.
