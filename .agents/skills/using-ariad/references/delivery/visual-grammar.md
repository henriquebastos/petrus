# Delivery Visual Grammar

This document captures the emerging visual language for Maestro's delivery behavior.

It is separate from the [Conceptual Model](conceptual-model.md). The method defines concepts, events, checkpoints, and criteria. The visual grammar chooses how those concepts appear in a specific interface.

## Design boundary

Visual components may help operate Delivery, but they do not define it.

A User Story or Technical Story remains itself whether it appears as a terminal card, web task, compact checkpoint, roadmap row, commit proposal, or conversation summary. A checkpoint is a methodological pause before it is a visual component.

## Surface transport contract

A rendered Ariad surface is a runtime artifact, not conversational prose. When a runtime emits a marked Ariad surface, the Driver transports that surface verbatim before adding interpretation.

```text
transport: verbatim
marker_protocol: ariad_compact
interpretation_policy: after_block_only
```

The Driver may explain what a surface means, but it must not replace the surface with a summary, translation, or reformatted version. If multiple Ariad surfaces are emitted, preserve their order and content. This contract is phase-independent: Roadmap, Pull, Prepare, Expand, Plan, Approval, Implementation Guard, Validation, Debt Review, Coherence, Done, and future delivery surfaces follow the same transport rule.

## Visual direction

Delivery can use block-like cards because its central structure is the roadmap taxonomy: Value / CV, Delivery Story, User Story, Technical Story, Task, and Maintenance. Its central implementation objects are User Stories and Technical Stories: units bounded enough to become verified change inside a Delivery Story arc.

Exploration uses triangles to express capture, tension, and emergence. Delivery uses squares and blocks to express bounded commitment, verification, and closure.

```text
triangle exploratory capture, tension, direction, antenna
square   delivery commitment, bounded change, verified artifact
```

The square should not imply rigidity. It means the work has enough boundary to be planned, implemented, validated, documented, and recorded.

## Provisional symbol set

```text
🟪 Value / CV
▣ Delivery Story
■ User Story / delivery artifact
◼ technical story
◫ context loaded
🧭 plan checkpoint
✅ validation checkpoint
◨ documentation update
🔎 review checkpoint
◉ coherence check
🟩■ closed delivery
↳ follow-up captured
△ debt carried, introduced, or payment opportunity
```

These symbols are provisional render choices. They should remain replaceable.

When User Stories and Technical Stories appear as siblings, their markers must occupy the same visual column and width. A Technical Story icon or glyph should not be smaller in a way that makes following User Stories appear indented beneath it. Prefer fixed-width labels such as `[TS1]`, `[US1]`, `[US2]` or padded icon+code groups such as `◼ [TS1]` and `■ [US1]`.

## Visual primitives

Delivery visuals should combine shape, icon, color, and state instead of rendering every component as a plain text rectangle.

Cadences help decide which surfaces appear at a boundary. A story closure may call for Transition View plus History Checkpoint; a debt-bearing review may call for Debt Delta; a release boundary may call for Release Intent. The visual grammar renders those choices, but the cadence supplies the methodological question.

Ariad defines the semantic mapping. The runtime chooses exact rendering.

### Shape language

```text
■ square card
  bounded delivery commitment

▣ framed square
  parent delivery arc, usually Delivery Story

🟪 colored block
  Value / CV taxonomy card

🟦 colored block
  User Story taxonomy card

🟨 colored block
  User Story taxonomy card

◼ compact filled block
  technical story or internal capability

◉ circle
  current focus, coherence point, or active method state

○ hollow circle
  pending or not-yet-started method state

✓ check
  accepted, validated, or done

✕ cross
  blocked, failed, or rejected

↳ hook
  follow-up or adjacent work captured outside current boundary

⇄ transition
  movement from closed work into parent structure or next coherent pull

🚢 release marker
  release intent, release candidate, or release handoff

△ debt marker
  debt carried, debt introduced, or repayment opportunity
```

### Card anatomy

A rich Delivery card should make its visual role visible before the reader parses the prose.

```text
[color/shape][code]  title                       state marker
  level: Value / Delivery Story / User Story / Technical Story / Task
  role: why this card exists in the current surface
  evidence or next movement
```

Examples:

```text
🟪[CV2]  Checkout Recovery                         ◉ active
  value: reduce checkout abandonment without broad redesign
  progress: 2/3 User Stories

🟦[DS3]  Mobile validation recovery                ◉ current
  delivery story: recover from address validation failures
  stories: 2/3 done

■ [US1]  Show field-level recovery guidance        ✓ done
  behavior: mobile users see actionable field-level guidance
  validated: Navigator behavior checkpoint passed

◼ [TS1]  Classify mobile autofill failures         ✓ verified
  technical: internal classifier and diagnostics
  behavior checkpoint: not yet, continues to US1

↳       Review postal normalization                ○ captured
  follow-up: adjacent, not blocking current story
```

### Surface composition

A surface may use a shell, but the shell should contain cards, markers, and visual relations when roadmap structure matters.

```text
🟪[CV2] Checkout Recovery ◉
  └─ 🟦[DS3] Mobile validation recovery ◉
       ├─ ◼ [TS1] Classify autofill failures ✓
       ├─ ■ [US1] Show recovery guidance ◉
       └─ ■ [US2] Record validation guidance ○
```

The goal is orientation before reading: the Navigator should see level, state, and movement at a glance.

## Provisional color semantics

Taxonomy level and method state should remain visually distinct.

Taxonomy examples:

```text
🟪[CV2]  Capability Value
🟦[DS3]  Delivery Story
🟨[US4]  User Story
```

Method state examples:

```text
✓ done
◉ current
○ pending
✕ blocked
```

Color may support delivery posture, but it should not confuse roadmap level with lifecycle state.

```text
gray    context, documentation, or neutral project memory
blue    implementation in progress
green   validated, coherent, or closed delivery
yellow  attention, risk, or pending Navigator judgment
red     blocked validation or incoherent User Story
black   abandoned or superseded delivery work
```

The exact palette belongs to the runtime or UI implementation.

## Core delivery surfaces

Maestro currently uses structured checkpoint surfaces for Delivery:

```text
Roadmap Snapshot
  What delivery work is available to pull?

Lifecycle Board
  Where are active and candidate items in the Delivery lifecycle?

Pull Recommendation
  What should be pulled next, and why?

Plan Checkpoint
  Is the route right before implementation begins?

Delivery Story Expansion
  Should this work become multiple User Stories?

Implementation Orientation
  What is being changed inside the active User Story or Technical Story boundary?

Validation Checkpoint
  What passed, what needs manual inspection, and what remains uncertain?

Review Checkpoint
  What changed, what debt remains, and what documentation or refactoring is needed?

Coherence Checkpoint
  Do Process, Project, and Product still agree?

History Checkpoint
  Is the active User Story or Technical Story coherent enough to enter project history?

Transition View
  What closed, where was it absorbed, what did it unlock, and what moves next?

Delivery Story Closure
  Is the Delivery Story complete enough to suggest release management?

Release Intent
  Is there a release boundary now?

Operation Execution
  What controlled operation ran, what state did it reach, and what evidence did it produce?
```

These surfaces are introduced in [Delivery Flow](flow.md). Operation Execution is included here as a visual schema because it often supports technical validation, release checks, runtime operations, and web-console evidence, but the exact web layout belongs to the implementing runtime.

## Surface Shell

A `Surface Shell` is a reusable information structure for rich Delivery surfaces.

It is inspired by web-console and runtime-operation surfaces, but it is not a CSS or layout contract. Ariad defines the information architecture. The runtime chooses whether it appears as tabs, terminal panels, web cards, tables, collapsible sections, or conversation prose.

Use a Surface Shell when a surface needs more than a compact checkpoint card.

Schema:

```text
Surface Shell
  label:
    uppercase surface family or execution category
  title:
    human-readable surface title
  description:
    one sentence explaining what the surface shows or what limitation applies
  tabs or panels:
    optional named views such as Overview, Backlog, Details, Timeline, Result details
  status line:
    compact state sentence, often "result of <surface-id> — <state>"
  primary panel:
    structured human-readable evidence or current state
  secondary evidence:
    optional raw payload, details, links, or audit trail
```

Example shape:

```text
SURFACE LABEL
Surface title

Short explanation of what this surface shows.

Tabs
  Overview | Details

result of surface-id      state

╭────────────────────────────────────────────────────────╮
│ Key:        value                                      │
│ Key:        value                                      │
│                                                        │
│ Evidence or current state                              │
╰────────────────────────────────────────────────────────╯
```

Boundary:

- Ariad owns the shell semantics: label, title, description, panels, status line, evidence.
- The runtime owns typography, spacing, colors, tab implementation, streaming, polling, and collapsible behavior.
- A surface may omit shell parts when the compact form is clearer.

## Operation Execution

An `Operation Execution` surface appears when Delivery runs a controlled operation and needs to preserve visible evidence.

It should show the operation category, operation title, execution mode, state, primary result, and detailed evidence. It may include tabs or panels when the runtime separates live or polled output from structured result details.

Schema:

```text
Operation Execution
  category: operation class or execution domain
  title: human-readable operation name
  description: what this surface is showing or what limitation applies
  primary panels:
    polled console | result details | timeline | approvals
  status line:
    result of <operation-id> — <state>
  result card:
    structured evidence as readable key-value data
  raw evidence:
    optional collapsed machine-readable payload
```

Example:

```text
OPERATION EXECUTION
Runtime health diagnosis

This surface updates from durable run state. True streaming remains future work.

Tabs
  Polled console | Result details

Console
╭────────────────────────────────────────────────────────╮
│ result of runtime-health      attention needed         │
│                                                        │
│  Runtime status: attention needed                      │
│  Version: 0.15.0                                       │
│  Git branch: cv13/v2-agentic-web-console               │
│  Mirror home: /Users/example/.mirror-minds/example     │
│  Database: present                                     │
╰────────────────────────────────────────────────────────╯
```

Use when:

- a technical story is verified through an operation run;
- a release candidate needs runtime health, backup, migration, or smoke evidence;
- a web or runtime surface executes allowlisted operations and preserves audit evidence;
- the Navigator needs to inspect operation state without reading raw JSON first.

Boundary:

- Ariad owns the requirement that controlled operations expose state and evidence when they are used for validation.
- The runtime owns polling, streaming, tabs, colors, typography, raw payload shape, and operation-specific rendering.
- Unknown, attention, blocked, failed, cancelled, and approval-required states should be represented honestly rather than flattened into pass/fail.

## Delivery Lifecycle Ribbon

A `Delivery Lifecycle Ribbon` may appear as a compact breadcrumb above Delivery surfaces. It helps the Navigator see where the current surface sits in the Ariad lifecycle.

Current runtime stages:

```text
pull -> prepare -> expand -> plan -> implement -> validate -> debt review -> coherence -> done
```

Marker semantics:

```text
✓ completed stage
◉ current stage
○ future stage
```

Example:

```text
Ariad: ✓ Pull | ◉ Prepare | ○ Expand | ○ Plan | ○ Implement | ○ Validate | ○ Debt Review | ○ Coherence | ○ Done
```

The ribbon is orientation, not permission. A stage marked current still must obey its checkpoint boundary. For example, `Prepare` being current does not allow implementation; `Plan` must be rendered and approved first.

## Roadmap Snapshot

A `Roadmap Snapshot` component appears when the Navigator asks to see the delivery field before pulling work.

It should show Value / CV, Delivery Story, child story backlog, recently promoted candidates from Exploration, active constraints, and enough context for an intentional pull. It should not silently choose the next story.

Roadmap Snapshot may use the reusable [Surface Shell](#surface-shell) when it needs to feel closer to a web-console or operation surface.

Schema:

```text
Roadmap Snapshot
  label: ROADMAP SNAPSHOT
  title: Delivery field overview
  description: source and limits of the roadmap state
  tabs or panels: Overview | Backlog | Promoted | Details
  status line: result of roadmap-snapshot — ready to pull | attention | unknown
  primary panel: current Value / CV, active Delivery Story, backlog, promoted candidates, constraints
  secondary evidence: roadmap links, counts, progress bars, unknowns, stale-state warnings
```

Example:

```text
ROADMAP SNAPSHOT
Delivery field overview

This surface reads project roadmap state and recently promoted Exploration candidates.

Tabs
  Overview | Backlog | Promoted | Details

result of roadmap-snapshot      ready to pull

╭────────────────────────────────────────────────────────╮
│ 🟪[CV2]  Checkout Recovery                      ◉ active │
│          value: reduce abandonment without redesign     │
│                                                        │
│   └─ 🟦[DS3] Reduce checkout abandonment          ◉ current│
│      progress: 1/4 User Stories done               │
│                                                        │
│      Backlog                                           │
│      ○ 🟨[US3] Add saved-address editing                 │
│      ○ 🟨[US4] Improve checkout loading feedback         │
│      ○ 🟨[US5] Review postal code normalization          │
│                                                        │
│      Recently promoted from Exploration                │
│      ◉ 🟨[US2] Improve mobile validation recovery        │
│                                                        │
│      Active constraints                                │
│      ✕ broad checkout redesign                         │
│      ✓ preserve validation rule behavior               │
╰────────────────────────────────────────────────────────╯
```

Compact runtimes may render the same information as a smaller checkpoint card instead of the full shell.

## Lifecycle Board

A `Lifecycle Board` component appears when the Navigator needs a compact view of
where multiple roadmap items sit across the Delivery lifecycle. It is an
orientation surface, not a checkpoint surface. It can show current movement,
completed phases, pending phases, and blocked gates at a glance, but it should
not replace Plan, Validation, Review, Coherence, History, or Delivery Story
Closure components.

The board is most useful when a Delivery Story arc has several candidate items,
when a runtime resumes work and needs to show active state, or when the Navigator
asks what is in flight before deciding what to pull or approve.

Schema:

```text
Lifecycle Board
  label: LIFECYCLE BOARD
  title: Delivery lifecycle overview
  description: source and limits of lifecycle state
  scope: Value / CV, Delivery Story, or active journey slice
  legend: done, current, pending, blocked, gate, evidence markers
  matrix: roadmap items against lifecycle phases
  current gate: the next Navigator decision or methodological block
  focus link: the detailed checkpoint surface for the current cell
```

State markers should remain distinct from roadmap level markers. A row marker
such as `▣`, `■`, or `◼` says what kind of work item it is; a cell marker such as
`✓`, `◉`, `○`, or `✕` says where it is in the lifecycle. Checkpoint icons may be
paired with the current lifecycle marker when the cell represents a gate.

```text
✓ done       ◉ current       ○ pending       ✕ blocked
🧭 plan gate ✅ validation    🔎 review       ◉ coherence
```

Example:

```text
LIFECYCLE BOARD
Delivery lifecycle overview

This surface reads the active Delivery cursor and roadmap state. It orients the
Navigator before a detailed checkpoint surface.

result of lifecycle-board      plan approval required

╭────────────────────────────────────────────────────────╮
│ 🟪[CV20] Builder Mode Evolution              ◉ active │
│                                                        │
│ Item      Lev State    Pull Prep Exp Plan Impl Val Rev │
│ ────────  ─── ───────  ──── ──── ─── ──── ──── ─── ─── │
│ ▣ [DS5]   DS  Active    ✓    ✓    ✓   ◉🧭   ○    ○   ○  │
│ ▣ [DS6]   DS  Planned   ○    ○    ○   ○    ○    ○   ○  │
│ ▣ [DS7]   DS  Planned   ○    ○    ○   ○    ○    ○   ○  │
│                                                        │
│ More phases: Coh ○, Done ○                             │
│                                                        │
│ current gate                                           │
│ 🧭 [DS5] Plan is waiting for Navigator approval.       │
│                                                        │
│ focus surface                                          │
│ Render Plan Checkpoint before implementation begins.   │
╰────────────────────────────────────────────────────────╯
```

When the active Delivery Story has child User Stories and Technical Stories, the
board may expand the parent row. Child story markers should align as siblings;
technical stories must not appear visually nested under user stories.

```text
Item          Type   Pull  Prep  Exp   Plan  Impl  Val   Rev   Coh   Done
────────────  ────   ────  ────  ────  ────  ────  ────  ────  ────  ────
▣ [DS5]       DS      ✓     ✓     ✓     ◉🧭   ○     ○     ○     ○     ○
◼ [TS1]       TS      ✓     ✓     —     ○     ○     ○     ○     ○     ○
■ [US1]       US      ○     ○     —     ○     ○     ○     ○     ○     ○
■ [US2]       US      ○     ○     —     ○     ○     ○     ○     ○     ○
↳ Debt note   Debt    —     —     —     —     —     —     △     ○     ○
```

Boundary:

- The Lifecycle Board shows lifecycle orientation; it does not grant approval.
- The current gate should link or lead to the appropriate checkpoint component.
- A completed cell should be backed by durable evidence when evidence is required
  by the method or local policy.
- A board row may be compact, but it should not flatten Value / Delivery Story /
  User Story / Technical Story semantics into a generic task list.

## Pull Recommendation

A `Pull Recommendation` component or response appears after the roadmap snapshot.

It should balance normal backlog priority with newly promoted exploratory learning. The Driver may recommend a promoted candidate over the next backlog item, but it must make the trade-off explicit and leave the pull decision with the Navigator.

Preferred response shape:

```text
The next backlog item would normally be **Add saved-address editing** because it is the highest planned item in CV2.DS3. However, **Improve mobile address validation recovery** was just promoted from Exploration and sits directly inside the active Delivery Story: reducing checkout abandonment without redesigning checkout. I recommend pulling the promoted User Story now, then returning to saved-address editing. That keeps the roadmap order visible, but lets recent learning influence the next commitment instead of aging in the backlog.
```

## Delivery Story Identified

A `Delivery Story Identified` component appears when the Navigator intentionally pulls work into Delivery.

It should show the story title, source, roadmap placement, intent, commitment state, and current story. If the source is a promoted Exploration candidate, the exploration source should be visible.

Schema:

```text
Delivery Story Identified
  title
  source:
    roadmap backlog | promoted Exploration candidate | maintenance | pulled Delivery Story expansion
  roadmap placement:
    Value / CV -> Delivery Story -> User Story / Technical Story
  intent
  commitment
  current story
  exploration source, when promoted from Exploration:
    source Exploratory Story
    full Exploration document
    Delivery Story exploration summary
    Carry Forward Notes status
```

Example:

```text
Delivery
╭────────────────────────────────────────────────────────╮
│        🟪■  DELIVERY STORY IDENTIFIED                  │
│                                                        │
│  Improve mobile address validation recovery.           │
│                                                        │
│  source                                                │
│  promoted Exploration candidate                        │
│                                                        │
│  promoted from                                         │
│  ES-042 Checkout address-step abandonment              │
│                                                        │
│  roadmap placement                                     │
│  🟪[CV2] Checkout Recovery                             │
│    └─ 🟦[DS3] Reduce checkout abandonment               │
│         └─ 🟨[US3] Mobile validation recovery           │
│                                                        │
│  intent                                                │
│  help mobile users recover from address errors         │
│                                                        │
│  exploration source                                    │
│  full doc: docs/project/exploration/es-042.../index.md │
│  summary: roadmap/.../exploration-summary.md           │
│  carry forward notes: preserved                        │
│                                                        │
│  commitment                                            │
│  delivery pending plan confirmation                    │
│                                                        │
│  current story                                         │
│  Mobile autofill values are rejected without useful    │
│  field-level recovery guidance.                        │
╰────────────────────────────────────────────────────────╯
```

## Prepare Field Reading

A `Prepare Field Reading` component appears after work has been pulled and before the Plan Checkpoint. It shows what the Driver read, how the pulled item is currently shaped, what risks are visible, and which Ariad rules govern the next transition.

It should make clear that Prepare reads terrain only. It does not create a plan, approve a checkpoint, start implementation, or silently expand scope. If the pulled item is a Delivery Story, the surface may name that Plan should decide whether expansion into User Stories or Technical Stories is required.

Schema:

```text
Prepare Field Reading
  active item
  terrain read
  story shape
  risks
  applicable rules
  next event
  boundary
```

Example:

```text
Delivery
╭────────────────────────────────────────────────────────╮
│        🧭  PREPARE FIELD READING                       │
│                                                        │
│  active item                                           │
│  🟦[CV2.DS1]                                           │
│                                                        │
│  terrain read                                          │
│  ✓ README.md: present                                  │
│  ✓ docs/project/roadmap/index.md: present              │
│  ○ docs/process/development-guide/index.md: missing    │
│                                                        │
│  story shape                                           │
│  Delivery Story candidate. Plan should decide whether  │
│  to expand into child User Stories before build.       │
│                                                        │
│  risks                                                 │
│  ✕ Scope may expand if checkout mixes address, payment │
│    and confirmation.                                   │
│  ✕ Implementation remains blocked until Plan approval. │
│                                                        │
│  applicable rules                                      │
│  ✓ Pull selects active work; Prepare reads terrain.    │
│  ✓ Plan is next and requires Navigator approval.       │
│                                                        │
│  next event                                            │
│  Plan                                                  │
│                                                        │
│  boundary                                              │
│  Plan was not created.                                 │
│  Implementation remains blocked.                       │
╰────────────────────────────────────────────────────────╯
```

## Plan Checkpoint

A `Plan Checkpoint` component appears after a User Story or Technical Story is pulled and before implementation begins.

It should show the story, parent Delivery Story, scope, out-of-scope boundaries, acceptance behavior, validation route, documentation impact, risks, and a Navigator decision prompt. For User Stories, the acceptance behavior should usually be written in lightweight BDD form (`Given` / `When` / `Then` / optional `And`) so the observable behavior is explicit. It should make clear that Navigator confirmation is required before implementation begins.

If the project stores a `plan.md`, writing the file does not replace this component. The Driver should render the Plan Checkpoint surface in the conversation or runtime so the Navigator can accept, narrow, redirect, or reorder before implementation.

```text
Delivery
╭────────────────────────────────────────────────────────╮
│        🧭  PLAN CHECKPOINT                             │
│                                                        │
│  story                                                 │
│  ■ [US1] Improve mobile address validation recovery    │
│                                                        │
│  parent                                                │
│  🟦 [DS3] Mobile validation recovery                   │
│                                                        │
│  scope                                                 │
│  add field-level recovery guidance for rejected        │
│  mobile autofill values                                │
│                                                        │
│  out of scope                                          │
│  checkout redesign                                     │
│  address validation rule redesign                      │
│                                                        │
│  acceptance behavior                                   │
│  Given a mobile autofill value is rejected             │
│  When checkout shows the validation error              │
│  Then the user sees field-level recovery guidance      │
│  And checkout redesign is not required                 │
│                                                        │
│  validation                                            │
│  automated tests for mobile autofill-shaped values     │
│  manual checkout check on mobile viewport              │
│                                                        │
│  risk                                                  │
│  validation rules may be coupled to generic errors     │
│                                                        │
│  Navigator decision                                    │
│  Accept this plan, narrow it, redirect it, or reorder? │
╰────────────────────────────────────────────────────────╯
```

## Delivery Story Expansion

A `Delivery Story Expansion` component appears when the Driver identifies a Delivery Story arc that must be expanded before implementation. This may happen during Delivery entry, planning, or after reading context.

It should show the roadmap context, why the work is a Delivery Story, the proposed sibling User Stories and Technical Stories, the recommended first pull, and an explicit Navigator decision prompt. It should prevent large work from being hidden behind one story-level validation moment, and it should not create child folders or plans before the Navigator accepts the expansion.

Sibling rows must align visually. Technical Stories and User Stories are peers inside the Delivery Story; a compact technical marker must not make following User Stories look nested under it.

```text
Delivery
╭────────────────────────────────────────────────────────╮
│        🧩  DELIVERY STORY EXPANSION                    │
│                                                        │
│  roadmap context                                       │
│  🟪 [CV2]  Checkout Recovery                           │
│  🟦 [DS3]  Mobile validation recovery                  │
│                                                        │
│  why expansion is needed                               │
│  The work contains multiple behavior and technical     │
│  steps that should not be hidden inside one story.     │
│                                                        │
│  proposed child stories                                │
│  ◼ [TS1]  Classify mobile autofill failures            │
│           validation: automated and diagnostic         │
│  ■ [US1]  Show field-level recovery guidance           │
│           validation: Navigator behavior checkpoint    │
│  ■ [US2]  Record validation guidance in project docs   │
│           validation: documentation review             │
│                                                        │
│  recommended first pull                                │
│  ■ [US1] Show field-level recovery guidance            │
│                                                        │
│  Navigator decision                                    │
│  Accept this expansion, reorder it, narrow it, or      │
│  keep the Delivery Story unexpanded for now?           │
╰────────────────────────────────────────────────────────╯
```

## User Story Implemented

A `User Story Implemented` component appears when a User Story has created behavior or capability ready for verification.

It should show what changed and what behavior was created. It should not represent a private implementation chunk inside a larger hidden story.

```text
Delivery
╭────────────────────────────────────────────────────────╮
│        ◼  USER STORY IMPLEMENTED                  │
│                                                        │
│  story                                                │
│  Show field-level recovery guidance                   │
│                                                        │
│  changed                                               │
│  address error classifier                              │
│  field-level recovery message                          │
│  mobile autofill regression test                       │
│                                                        │
│  behavior created                                      │
│  rejected mobile autofill values now show field-level  │
│  recovery guidance instead of generic failure          │
╰────────────────────────────────────────────────────────╯
```

## Technical Story Verified

A `Technical Story Verified` component appears when a technical story inside a Delivery Story creates internal capability without producing Navigator-visible behavior yet.

It should show internal verification and the next behavior-visible story. It should make clear that the Driver may continue until a behavior checkpoint is reached, unless risk or project policy requires a stop.

```text
Delivery
╭────────────────────────────────────────────────────────╮
│        ◼  TECHNICAL STORY VERIFIED                    │
│                                                        │
│  story                                                │
│  Classify mobile autofill validation failures          │
│                                                        │
│  verification                                          │
│  classifier tests passed                               │
│  diagnostic output identifies rejected autofill shape  │
│                                                        │
│  Navigator behavior checkpoint                         │
│  not yet                                               │
│                                                        │
│  next story                                            │
│  Show field-level recovery guidance                    │
╰────────────────────────────────────────────────────────╯
```

## Validation Checkpoint

A `Validation Checkpoint` component appears after automated checks and validation preparation.

For User Stories, it should show automated evidence, a concrete Navigator validation route, expected observations, pass condition, fail condition, exclusions, and any blocker or uncertainty. For product-visible or capability-visible work, it should never rely on automated checks alone. The Navigator should have something simple to run, open, inspect, or compare.

For Technical Stories, automated/internal evidence is normally the validation route. The component should show the evidence clearly and name the next Navigator-visible User Story checkpoint when relevant, without asking the Navigator to manually validate private substrate unless risk or project policy requires it.

```text
Delivery
╭────────────────────────────────────────────────────────╮
│        ✅  VALIDATION CHECKPOINT                       │
│                                                        │
│  story: Improve mobile address validation recovery     │
│                                                        │
│  automated                                             │
│  address validation tests passed                       │
│  checkout form tests passed                            │
│  build passed                                          │
│                                                        │
│  Navigator validation route                            │
│  1. open checkout in mobile viewport                   │
│  2. enter autofill-shaped address values               │
│  3. submit address step                                │
│                                                        │
│  expected observation                                  │
│  field-level recovery guidance appears                 │
│  generic address failure message does not appear       │
│                                                        │
│  pass condition                                        │
│  Navigator can recover from the rejected field         │
│                                                        │
│  fail condition                                        │
│  only generic feedback appears or recovery is unclear  │
│                                                        │
│  conscious exclusions                                  │
│  no desktop visual redesign                            │
│  no validation rule changes                            │
╰────────────────────────────────────────────────────────╯
```

## Documentation Updated

A `Documentation Updated` component appears when project memory changes as part of the story.

It should show what was updated, why it changed, and what was intentionally left unchanged.

```text
Delivery
╭────────────────────────────────────────────────────────╮
│        ◨  DOCUMENTATION UPDATED                        │
│                                                        │
│  updated                                               │
│  checkout validation notes                             │
│  roadmap Delivery Story status                         │
│                                                        │
│  reason                                                │
│  mobile address errors now expose field-level          │
│  recovery guidance instead of generic failure          │
│                                                        │
│  not updated                                           │
│  architecture overview, because no rule architecture   │
│  changed                                               │
╰────────────────────────────────────────────────────────╯
```

## Review Checkpoint

A `Review Checkpoint` component appears when the Driver has inspected the changed surface.

It should show what changed and include a refactoring and technical-debt assessment. The component should name refactoring done, refactoring considered, debt paid, new debt introduced, debt carried forward with revisit criteria, whether a debt item in the Technical Debt Ledger is needed, and follow-up. If no refactor was needed or no new debt was introduced, say so explicitly.

```text
Delivery
╭────────────────────────────────────────────────────────╮
│        🔎  REVIEW CHECKPOINT                           │
│                                                        │
│  changed                                               │
│  mobile autofill validation failures now map to        │
│  field-level recovery guidance                         │
│                                                        │
│  refactoring done                                      │
│  extracted error classifier branch for readability     │
│                                                        │
│  refactoring considered                                │
│  separate postal normalization module                  │
│                                                        │
│  debt paid                                             │
│  generic error branch is no longer duplicated          │
│                                                        │
│  new debt introduced                                   │
│  none                                                  │
│                                                        │
│  debt carried forward                                  │
│  country-specific postal normalization remains uneven  │
│  revisit when a second country-specific case appears   │
│                                                        │
│  debt ledger                                           │
│  no new debt item in the ledger; follow-up is enough   │
│                                                        │
│  follow-up                                             │
│  Review country-specific postal code normalization     │
╰────────────────────────────────────────────────────────╯
```

## Coupled Story Closure

A `Coupled Story Closure` component appears when two or more child stories close together because their validation and review boundary is genuinely shared.

It should name each story separately, explain why the closure is coupled, show validation/review evidence for each, and preserve distinct roadmap status. It should not hide unfinished validation, debt, or history questions.

```text
Delivery
╭────────────────────────────────────────────────────────╮
│        ⇄  COUPLED STORY CLOSURE                        │
│                                                        │
│  parent                                                │
│  🟦 [DS7] Conversation Metadata Lifecycle              │
│                                                        │
│  closing together                                      │
│  ◼ [TS1] Metadata Lifecycle Decision Policy            │
│     reason: pulled to unblock US1 policy validation    │
│     evidence: policy tests and Navigator samples pass  │
│                                                        │
│  ■ [US1] Dry-run Metadata Lifecycle Decision Path      │
│     reason: dry-run behavior accepted after TS1        │
│     evidence: CLI dry-run samples pass, mutated=false  │
│                                                        │
│  why coupled                                           │
│  TS1 and US1 share the same validation/review boundary │
│  and closing separately would not add judgment.        │
│                                                        │
│  debt impact                                           │
│  D-001 carried with revisit trigger before/during US2  │
│                                                        │
│  history question                                      │
│  one combined history action is acceptable if project  │
│  policy allows it                                     │
╰────────────────────────────────────────────────────────╯
```

## Debt Delta

A `Debt Delta` component may appear inside Review or as a compact standalone surface when debt movement needs special attention.

It should show whether the story reduced, increased, or carried technical debt, and what action follows.

```text
Delivery
╭────────────────────────────────────────────────────────╮
│        △  TECHNICAL DEBT DELTA                         │
│                                                        │
│  source story                                          │
│  US1 Dry-run metadata lifecycle decision path          │
│                                                        │
│  debt paid                                             │
│  none                                                  │
│                                                        │
│  new debt introduced                                   │
│  metadata lifecycle policy remains inside              │
│  ConversationService                                   │
│                                                        │
│  debt carried forward                                  │
│  evidence term filtering is noisy                      │
│                                                        │
│  revisit trigger                                       │
│  before apply/mutation behavior in US2                 │
│                                                        │
│  action                                                │
│  record debt item in the ledger or follow-up           │
╰────────────────────────────────────────────────────────╯
```

## Debt Snapshot

A `Debt Snapshot` component appears when debt near the active roadmap item should influence the next pull.

```text
Delivery
╭────────────────────────────────────────────────────────╮
│        △  DEBT SNAPSHOT                                │
│                                                        │
│  near DS7 Conversation Metadata Lifecycle              │
│                                                        │
│  carried debt                                          │
│  △ evidence term filtering/ranking is noisy            │
│  △ policy helpers live inside ConversationService      │
│                                                        │
│  recommendation                                        │
│  pay or isolate policy debt before US2 if apply        │
│  behavior would make mutation boundaries unclear       │
╰────────────────────────────────────────────────────────╯
```

## Debt Payment Proposal

A `Debt Payment Proposal` appears when the Driver recommends paying debt before continuing planned delivery work.

```text
Delivery
╭────────────────────────────────────────────────────────╮
│        △→◼  DEBT PAYMENT PROPOSAL                      │
│                                                        │
│  debt                                                  │
│  metadata lifecycle policy embedded in                 │
│  ConversationService                                   │
│                                                        │
│  why now                                               │
│  US2 will introduce mutation behavior; policy boundary │
│  should be clearer before writes are added             │
│                                                        │
│  proposed work                                         │
│  TS2 Extract metadata lifecycle policy object          │
│                                                        │
│  Navigator decision                                    │
│  Pay now, defer with revisit trigger, or reject?       │
╰────────────────────────────────────────────────────────╯
```

## Coherence Check

A `Coherence Check` component appears when the Driver verifies alignment across Process, Project, and Product.

It should show the three dimensions and a clear result. If one dimension is not coherent, the story should return to the relevant step.

```text
Delivery
╭────────────────────────────────────────────────────────╮
│        ◉  COHERENCE CHECK                              │
│                                                        │
│  Process                                               │
│  story stayed inside confirmed scope                   │
│  validation route prepared                             │
│                                                        │
│  Project                                               │
│  roadmap and validation notes updated                  │
│  follow-up captured                                    │
│                                                        │
│  Product                                               │
│  user now receives field-level recovery guidance       │
│  checkout redesign avoided                             │
│                                                        │
│  result                                                │
│  coherent                                              │
╰────────────────────────────────────────────────────────╯
```

## History Checkpoint

A `History Checkpoint` component appears before recording the change according to the configured commit policy.

It should show the proposed message, the reason for the change, and the closure evidence.

```text
Delivery
╭────────────────────────────────────────────────────────╮
│        🟩■  HISTORY CHECKPOINT                         │
│                                                        │
│  story: Improve mobile address validation recovery     │
│                                                        │
│  proposed message                                      │
│  Improve recovery guidance for mobile address errors   │
│                                                        │
│  why                                                   │
│  Mobile autofill values were rejected with generic     │
│  feedback. Field-level guidance now helps users        │
│  recover without broad checkout redesign.              │
│                                                        │
│  ready to close                                        │
│  tests passed                                          │
│  manual validation route prepared                      │
│  documentation updated                                 │
│  coherence checked                                     │
╰────────────────────────────────────────────────────────╯
```

## Transition View

A `Transition View` appears when a Delivery Story, User Story, Technical Story, or Value closes and the Driver needs to show how the completed work changes the larger roadmap.

It should show what completed, where it was absorbed, what it unlocked, what remains, and why the next movement is coherent.

```text
Delivery
╭────────────────────────────────────────────────────────╮
│        ⇄  TRANSITION VIEW                              │
│                                                        │
│  completed                                             │
│  US1 Show field-level recovery guidance                 │
│                                                        │
│  absorbed into                                         │
│  DS3 Improve mobile address validation recovery         │
│                                                        │
│  unlocked                                              │
│  Navigator can validate recovery behavior on mobile    │
│                                                        │
│  remaining in Delivery Story                            │
│  US2 Record validation guidance in project docs         │
│                                                        │
│  next coherent movement                                │
│  Pull US2, then collapse the Delivery Story if validation and     │
│  documentation remain coherent.                        │
╰────────────────────────────────────────────────────────╯
```

## Delivery Story Closure

A `Delivery Story Closure` component appears when completed User Stories and Technical Stories collapse into a Delivery Story.

It should name the completed stories, the emergent capability, and whether release management is suggested.

```text
Delivery
╭────────────────────────────────────────────────────────╮
│        🟩▣  EPIC CLOSED                                │
│                                                        │
│  delivery story                                        │
│  Improve mobile address validation recovery            │
│                                                        │
│  completed User Stories                            │
│  ✓ Classify mobile autofill validation failures        │
│  ✓ Show field-level recovery guidance                  │
│  ✓ Record validation guidance in project docs          │
│                                                        │
│  result                                                │
│  mobile users can recover from address validation      │
│  failures without broad checkout redesign              │
│                                                        │
│  suggested next process                                │
│  release management                                    │
│                                                        │
│  likely release boundary                               │
│  Delivery Story close suggests a MINOR release by Ariad default  │
╰────────────────────────────────────────────────────────╯
```

## Release Intent

A `Release Intent` component appears when release context is known or emerges from closure.

It should show whether the release is known or emergent, the likely boundary, required release work, and the Navigator decision.

```text
Delivery
╭────────────────────────────────────────────────────────╮
│        🚢  RELEASE INTENT                              │
│                                                        │
│  state                                                 │
│  emergent                                              │
│                                                        │
│  likely boundary                                       │
│  MINOR, because a Delivery Story closed without closing CV2     │
│                                                        │
│  release candidate                                     │
│  Checkout Recovery: mobile validation guidance         │
│                                                        │
│  required before release                               │
│  release note                                          │
│  version or package decision                           │
│  release-specific smoke validation                     │
│                                                        │
│  Navigator decision                                    │
│  enter release management now, defer it, or record     │
│  that no release is needed                             │
╰────────────────────────────────────────────────────────╯
```

## Story Flow Map

`Story Flow Map` is the compact map of Delivery movement.

It should not imply that every story moves linearly without returns. Validation failure, review findings, and coherence gaps can send the story back to implementation, documentation, or planning.

```text
🗺️ roadmap snapshot
      │
      ▼
⇢ pull recommendation ───▶ Navigator chooses what to pull
      │ pulled
      ▼
🟪■ Delivery Story identified
      │
      ▼
◫ context loaded
      │
      ▼
🧭 plan checkpoint ──────▶ Navigator redirects or narrows
      │ confirmed
      ▼
🧩 delivery story expansion ───────▶ expands if too large
      │ story-sized
      ▼
◼ User Story ────────────▶ ↳ follow-up captured
      │
      ▼
✅ behavior checkpoint ──▶ returns if validation fails
      │
      ▼
◨ documentation updated
      │
      ▼
🔎 review checkpoint ─────▶ returns if refactoring is needed
      │
      ▼
◉ coherence check ───────▶ returns if Process, Project, Product drift
      │
      ▼
🟩■ history checkpoint ───▶ Delivery Story closed
      │
      ▼
⇄ transition view ───────▶ next story, Delivery Story closure, or release intent
```

Conceptual mapping:

```text
roadmap snapshot
  current focus, backlog, promoted candidates, and constraints are visible

pull recommendation
  the Driver recommends what to pull by balancing backlog order and recent Exploration learning

Delivery Story identified
  the Navigator has intentionally pulled work into Delivery

context loaded
  project memory and relevant code are read before action

plan checkpoint
  the Navigator confirms direction before implementation

delivery story expansion
  large work becomes multiple User Stories instead of one oversized story

Delivery Story
  implementation creates verifiable behavior or capability

behavior checkpoint
  automated evidence and Navigator-visible validation route are ready when behavior is inspectable

documentation updated
  project memory changes with the story

review checkpoint
  changed surfaces, debt, and follow-up are named

coherence check
  Process, Project, and Product are reconciled

history checkpoint
  the User Story or Technical Story is ready to enter project history

transition view
  closed work is absorbed into its parent and the next coherent movement is named

delivery story closure
  completed User Stories and Technical Stories collapse into a Delivery Story

release intent
  the completed arc may suggest release management
```

## Language tone

The visual component should make delivery state legible without pretending certainty.

Preferred language:

```text
Here is the route before implementation. Confirm, narrow, or redirect it.
```

```text
Automated checks passed. Here is the Navigator validation route to inspect the intended change.
```

```text
This User Story is coherent enough to enter history if you accept the closure.
```

Avoid language that collapses judgment too early:

```text
Done.
```

```text
All good.
```

```text
Ready because tests passed.
```

Delivery visuals should preserve the Navigator's authority. They show evidence, boundary, and state. They do not declare acceptance on the Navigator's behalf.

## Open questions

- Should technical stories always render a component, or only when they occur inside a Delivery Story?
- Should Delivery use one compact card per checkpoint or a single story card that changes state?
- How should follow-up capture appear without becoming a distracting task board?
- Should the Story Flow Map appear in validation and review checkpoints, or only in documentation and teaching surfaces?
- How should Delivery visuals show a story that returns from validation to implementation?
- How should commit policy differences appear without making the history checkpoint noisy?
