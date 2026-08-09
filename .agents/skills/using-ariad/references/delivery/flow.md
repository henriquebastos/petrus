# Delivery Flow

This document explains Ariad Delivery through a practical sequence.

The [Conceptual Model](conceptual-model.md) names the concepts. [Roadmap Taxonomy](roadmap-taxonomy.md) defines Value/CV, Delivery Story, User Story, Technical Story, Task, and Maintenance. This page shows how those concepts appear in use: events, checkpoints, validation, review, coherence, and history.

The flow is not a rigid bureaucracy. Delivery work can discover new information, require refactoring, or return to an earlier step. The sequence below is a teaching path. [Cadences](cadences.md) name the recurring boundary questions that appear inside this flow, such as validation, review/debt, story closure, parent collapse, and release.

## Step 1. Navigator Pulls from the Roadmap

Delivery begins with an intentional pull.

The Navigator asks for the delivery field before choosing what to work on:

> Show me the roadmap and recommend what we should pull next.

The Driver reads the roadmap, active focus, planned work, and any recently promoted candidates from Exploration. A promoted candidate should already have a Delivery handoff: suggested Value / CV, Delivery Story seed, candidate User Stories and Technical Stories, validation seeds, pull state, and an exploration source. The exploration source should include a concise summary near the roadmap Delivery Story or child story and a link to the full Exploration document. The Driver then renders the delivery field before recommending a next item.

Promoted Exploration candidates normally enter Delivery as a Delivery Story. Direct pull as one User Story is reserved for candidates that are already behavior-sized.

```text
Delivery
╭────────────────────────────────────────────────────────╮
│        🗺️  ROADMAP SNAPSHOT                            │
│                                                        │
│  current Value / CV                                    │
│  CV2 Checkout Recovery                                 │
│                                                        │
│  active Delivery Story                                    │
│  DS3 Reduce checkout abandonment without redesign       │
│                                                        │
│  backlog                                               │
│  1. Add saved-address editing                          │
│  2. Improve checkout loading feedback                  │
│  3. Review country-specific postal code normalization  │
│                                                        │
│  recently promoted from Exploration                    │
│  Improve mobile address validation recovery            │
│                                                        │
│  active constraints                                    │
│  avoid checkout redesign                               │
│  preserve validation rule behavior                     │
╰────────────────────────────────────────────────────────╯
```

The Driver combines ordinary backlog priority with the new delivery pressure created by Exploration:

> The next backlog item would normally be **Add saved-address editing** because it is the highest planned item in CV2.DS3. However, **Improve mobile address validation recovery** was just promoted from Exploration and sits directly inside the active Delivery Story: reducing checkout abandonment without redesigning checkout. I recommend pulling the promoted User Story now, then returning to saved-address editing. That keeps the roadmap order visible, but lets recent learning influence the next commitment instead of aging in the backlog.

The Navigator decides what to pull:

> Pull the promoted validation recovery story.

The pull is the moment where the Navigator turns a candidate, backlog item, Delivery Story, User Story, Technical Story, Value, or maintenance item into active Delivery Work. If the pulled item is above story level, the Driver expands it before implementation.

## Step 2. Delivery Story Identified

The Driver identifies the selected work as Delivery because the intent is formed enough to define a roadmap object. If the pulled work came from Exploration, the Driver first checks whether it is a Delivery Story or a rare single User Story.

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

No repository change has happened yet. The Delivery Story is identified, not implemented. If the promoted candidate is a Delivery Story arc, the next step is Delivery Story Expansion into User Stories and Technical Stories before implementation.

## Step 3. Context Loaded

The Driver reads before acting.

Relevant context may include code, tests, documentation, roadmap, previous decisions, product principles, agent instructions, the Delivery Story's exploration summary, and the full Exploration document when the story was promoted from Exploration.

The Driver does not need to show every file read, but it should be able to explain what context matters.

```text
Delivery
╭────────────────────────────────────────────────────────╮
│        ◫  CONTEXT LOADED                               │
│                                                        │
│  story: Improve mobile address validation recovery     │
│                                                        │
│  read                                                  │
│  checkout address form                                 │
│  validation error mapping                              │
│  mobile autofill tests                                 │
│  product principle: recovery before rejection          │
│                                                        │
│  relevant memory                                       │
│  Exploration found mobile autofill values rejected     │
│  with generic error feedback.                          │
╰────────────────────────────────────────────────────────╯
```

Context loading prevents the Driver from treating the repository as a set of files detached from project memory.

## Step 4. Plan Checkpoint

The Driver proposes the route before implementation.

When a User Story or Technical Story is pulled, the Driver must render a Plan Checkpoint surface and stop for Navigator confirmation before implementation. Creating `plan.md` is not enough; the visible surface is the checkpoint.

A good plan names the intent, scope, exclusions, implementation approach, validation route, documentation impact, and risks. It also checks whether the pulled item is a Delivery Story arc or an implementable User Story / Technical Story. Delivery Story arcs should expand into smaller child stories before implementation.

The plan should identify the observable behavior or capability that will let the Navigator accept the story. For User Stories, Ariad recommends a lightweight BDD acceptance behavior: `Given` a starting state, `When` an action occurs, `Then` observable behavior appears, and `And` important constraints still hold. For non-UI work, this may be a dry-run, diagnostic command, generated artifact, operation evidence, documented policy, runtime state, or other inspectable output. If the plan can only name private implementation steps, the work is not yet a behavior-verifiable User Story; it should be reframed as a Technical Story inside a Delivery Story or reshaped around an observable validation route.

The Driver says:

> I will keep this story focused on field-level recovery guidance for rejected mobile autofill values. I will not redesign checkout or change address validation rules unless the current rules block the recovery message. I will add tests around mobile autofill-shaped values, update the error mapping, and document the validation route.

```text
Delivery
╭────────────────────────────────────────────────────────╮
│        🧭  PLAN CHECKPOINT                             │
│                                                        │
│  Improve mobile address validation recovery.           │
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
│  documentation impact                                  │
│  update validation notes if behavior changes           │
│                                                        │
│  risk                                                  │
│  validation rules may be coupled to generic errors     │
╰────────────────────────────────────────────────────────╯
```

The Driver stops. The Navigator confirms, redirects, or narrows the plan. If the Driver created or updated a plan file, it should still show this Plan Checkpoint surface instead of assuming the file itself is the checkpoint.

The Navigator says:

> Good. Keep it to recovery guidance. No checkout redesign.

The plan is now confirmed. Speed has direction.

If the Driver discovers that the requested work is too large for one behavior validation moment, the Driver does not hide multiple behavior steps inside one story. It proposes a Delivery Story expansion instead.

Delivery Story Expansion is a roadmap-structure checkpoint. The Driver should render the current roadmap context, explain why expansion is needed, show proposed child stories as siblings, recommend the first pull, and ask for Navigator acceptance before creating child folders or plans.

Technical Story and User Story rows should align visually. A compact Technical Story marker must not make later User Stories appear nested below it.

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

The Navigator may accept the expansion, reorder the stories, narrow the Delivery Story, or keep it unexpanded for now.

## Step 5. Implement User Story or Technical Story

The Driver implements one User Story or Technical Story at a time inside the active Delivery Story.

A User Story should create new behavior or capability that can be verified and observed through the validation route named in the plan. It should not be a container for private implementation hidden behind one validation moment. If implementation needs multiple behavior checkpoints, the parent Delivery Story should be expanded into smaller User Stories and Technical Stories.

For a behavior-visible story, the Driver implements until the new behavior can be validated by the Navigator:

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

For a technical story inside a Delivery Story, the Driver verifies the internal behavior and continues until a behavior-visible checkpoint is reached.

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

During implementation the Driver may discover adjacent work:

> I found that postal code normalization is inconsistent across countries. It does not block this Delivery Story because the rejected mobile autofill value can still be mapped to field-level guidance. I will capture normalization as follow-up instead of expanding the story.

```text
follow_up_captured
  title: Review country-specific postal code normalization
  reason: adjacent validation inconsistency found during delivery
  current story impact: not blocking
```

Delivery protects the Delivery Story boundary so the Navigator can still recognize what is being delivered.

## Step 6. Automated Checks and Navigator Validation Route

The Driver runs relevant automated checks and prepares validation appropriate to the story type.

For User Stories, automated checks tell the project that known contracts still hold, and the Navigator validation route tells the Navigator how to inspect whether the change matches the intention. A User Story Validation Checkpoint needs both: automated evidence and a concrete route the Navigator can execute or inspect.

The route should be simple: command, URL, file, operation, sample data, expected observation, pass condition, and fail condition. For non-UI work, it may be a dry-run, diagnostic command, operation report, generated artifact, documented policy, runtime state, or other inspectable evidence.

For Technical Stories inside a Delivery Story, the Driver records automated/internal verification and may continue to the next User Story. The Navigator should not normally need to validate private technical substrate manually. The Navigator-facing behavior checkpoint appears when a story creates behavior the Navigator can inspect.

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

The Driver stops when there is behavior for the Navigator to inspect.

If validation fails, the Delivery Story returns to implementation or planning. A failed validation route is not an embarrassment. It is the method doing its work.

## Step 7. Documentation Updated

Documentation changes happen in the same cycle as the change they describe.

The Driver updates the smallest documentation surface needed to keep the project memory true.

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

Documentation is not cleanup. It is part of delivery.

## Step 8. Review and Coherence Check

The Driver reviews what changed, why, and what happened to the structure of the codebase or project surface.

Review looks at the changed surface and includes a refactoring and technical-debt assessment. It should say what debt was paid, what debt was introduced, what debt remains, and whether any debt blocks closure. If carried debt should outlive the story, the Driver records it as a debt item in the project's Technical Debt Ledger or captures a follow-up with revisit criteria. Coherence checks whether Process, Project, and Product still agree.

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

The Driver stops at behavior checkpoints and coherence boundaries. If something is missing, the work returns to the relevant step instead of pretending the User Story or Technical Story is done.

## Step 9. History, Delivery Story Closure, and Release Handoff

When the User Story or Technical Story is coherent, the Driver proposes the history action according to the configured commit policy.

Ariad's default is conservative: propose a descriptive commit message and wait for Navigator confirmation before committing.

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

The Navigator accepts:

> Commit it.

The Driver records history and closes the User Story.

```text
story_closed
  title: Show field-level recovery guidance
  history: committed
  result: verified behavior
```

A User Story is not closed because files changed. It is closed because the change became intelligible, validated, documented, coherent, and recorded.

The story closure cadence now triggers transition questions. The Driver shows what closed, where it was absorbed, what it unlocked, whether debt/history/release questions are active, and what movement is coherent next.

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

When all User Stories in a Delivery Story have closed, the Delivery Story becomes the delivery-level unit of completion.

```text
Delivery
╭────────────────────────────────────────────────────────╮
│        🟩▣  DELIVERY STORY CLOSED                                │
│                                                        │
│  delivery story                                        │
│  Improve mobile address validation recovery            │
│                                                        │
│  completed child stories                            │
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

Delivery Story closure suggests, but does not automatically start, release management. The Driver should name the release handoff when the completed Delivery Story changes product behavior or operational state enough to warrant packaging, release notes, deployment, or version decisions.

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

If the closed Delivery Story also completes the Value / CV, the collapse is larger:

```text
value_closed
  value: CV2 Checkout Recovery
  completed Delivery Stories: 3/3
  emergent value: checkout abandonment can be diagnosed and reduced without broad redesign
  likely release boundary: MAJOR by Ariad default, unless the project overrides versioning policy
```

A Value / CV close does not force a major release. It asks the release-management question at the value boundary.
