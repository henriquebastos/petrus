# Exploration Visual Grammar

This document captures the emerging visual language for Maestro's exploratory mode.

It is separate from the [Conceptual Model](conceptual-model.md). The method defines concepts, states, events, and transitions. The visual grammar chooses how those concepts appear in a specific interface.

## Design boundary

Visual components may help discover the method, but they do not define it.

A signal is a signal even when it is rendered as a triangle in a terminal, a card in a web app, a compact row in a session summary, or plain data in an API response. A story is a story whether it is rendered as a timeline, assemblage map, cluster field, or narrative card.

## Visual direction

Delivery can use block-like cards because its central object is a Delivery Story: something bounded enough to become verified change.

Exploration needs a different visual foundation because its central object is an Exploratory Story: a narrative thread that may open from a signal and thicken before it has stable borders.

The current visual direction uses triangles as the primary exploratory shape.

```text
square   delivery commitment
triangle exploratory capture, tension, direction, antenna
```

The triangle suggests antenna, signal, direction, and tension. It creates a deliberate visual break from kanban-like post-it language.

## Provisional symbol set

```text
△ signal
▲ hot or active signal
◬ cluster / constellation
◉ resonance
◎ attractor
◭ inquiry / investigation field
▧ Exploratory Story / assemblage
◮ candidate for promotion
⟁ tension or contradiction
■ delivery artifact after promotion
```

These symbols are provisional render choices. They should remain replaceable.

## Provisional color semantics

Color should encode exploratory reading, not task status.

```text
blue    cold or low-energy signal
yellow  warm or returning signal
orange  hot signal asking for attention
red     critical or saturated signal
purple  deep methodological or strategic inquiry
green   mature or promotable material
black   archived or resting material
```

The exact palette belongs to the runtime or UI implementation.

## Core exploratory surfaces

Maestro's exploratory mode currently has four primary surface concepts:

```text
Signal Radar
  What is being picked up?
  Surface for possible signals, captured signals, and signals kept for later.

Narrative Field Snapshot
  What is the current exploratory field?
  Bird's-eye view of active, paused, promoted, archived, and kept-for-later exploratory material in a journey.

Exploratory Story View
  What is happening inside this story?
  Focused view of one Exploratory Story and its current thickening.

Candidate Gate
  What is ready to cross?
  Surface for promotable Exploratory Stories or candidates that may enter Delivery.
```

Radar is not the method and not a separate extension. In this model, Signal Radar is a Maestro exploratory surface for reviewing possible, captured, and kept-for-later signals.

## Narrative Field Snapshot

A `Narrative Field Snapshot` is the Exploration counterpart to Delivery's `Roadmap Snapshot`.

Roadmap Snapshot shows what Delivery work is available to pull. Narrative Field Snapshot shows what exploratory material is alive, resting, promoted, or archived before it becomes Delivery commitment.

It should answer: **what is the current exploratory field?**

Use when:

- the Navigator asks “where are we?” inside Exploration;
- a session is about to switch from Exploration to Delivery;
- multiple Exploratory Stories, signals, candidates, or experiments are active;
- the Driver needs to show what remains in Exploration after a candidate is promoted.

Schema:

```text
Narrative Field Snapshot
  active Exploratory Stories:
    story id, title, state, current attractor, current story
  experiments:
    proposed, in progress, completed, or declined learning moves
  candidates:
    formed, promoted, paused, or archived candidates
  Carry Forward Notes:
    preserved findings and their destination, if any
  nearby kept signals / Signal Radar excerpt:
    relevant kept signals related to visible stories, not the whole Signal Radar
  documentation:
    Exploration documents and Delivery summary links
  Delivery links:
    promoted stories and pull state
```

Example:

```text
Exploration
╭────────────────────────────────────────────────────────╮
│        ◬  NARRATIVE FIELD SNAPSHOT                     │
│                                                        │
│  active / recent Exploratory Stories                   │
│                                                        │
│  ▧ ES-001 Conversation metadata lifecycle              │
│    state: promoted to Delivery                         │
│    attractor: Conversation metadata lifecycle          │
│    promoted as: 🟦 CV9.DS7 Conversation Metadata       │
│                 Lifecycle                              │
│    full doc: docs/project/exploration/es-001.../       │
│              index.md                                  │
│                                                        │
│  experiments                                           │
│                                                        │
│  🧪 Manual metadata-decision rubric                     │
│    state: completed                                    │
│    samples: 0f8f0fc0, c55b04ab, e8b49667               │
│                                                        │
│  Carry Forward Notes                                   │
│                                                        │
│  ◨ Metadata readiness rules                            │
│    status: preserved in Delivery exploration summary   │
│                                                        │
│  nearby kept signals / Signal Radar excerpt            │
│                                                        │
│  △ Journey detection after conversation start          │
│    state: kept for later                               │
│    relation: adjacent to ES-001                        │
│    why shown: excluded from promoted story scope       │
╰────────────────────────────────────────────────────────╯
```

Boundary:

- Narrative Field Snapshot does not create roadmap work.
- Promoted items may appear in the snapshot, but Delivery commitment still belongs to the roadmap and Navigator pull.
- Kept signals may appear as a scoped Signal Radar excerpt, but they remain Signal Radar items unless reactivated.
- The snapshot should show relevant nearby signals, not the whole Signal Radar.
- The snapshot should preserve distinction between active stories, resting signals, promoted candidates, and archived material.

## Possible Signal Hint

A `Possible Signal Hint` is the lightest exploratory component.

It should name one possible signal and ask whether to explore now or keep for later. It should not diagnose the whole situation, list many hypotheses, or open an Exploratory Story before the Navigator engages.

```text
△ Possible signal
Seeing a generated GUID as the web conversation title may make Mirror feel unfinished and hard to reorient in.

Is this relevant? Tell me more to explore it now, or say “keep for later”.
```

If the Navigator replies with substantive detail, that reply is engagement. The Driver should open an Exploratory Story rather than repeating the relevance prompt.

The opening visual should remain low-friction. It confirms that the signal is now being explored, makes the ES visible, and asks one small question that helps the Navigator continue dumping feelings, examples, and partial knowledge. It should not start sensemaking yet.

```text
Exploration
╭────────────────────────────────────────────────────────╮
│        ▧  EXPLORATORY STORY OPENED                     │
│                                                        │
│  ES-042  Conversation title retitle timing             │
│                                                        │
│  opened from: △ possible signal                        │
│  state: thickening                                     │
│  commitment: none                                      │
│                                                        │
│  ▶ current story                                      │
│  Web conversations can remain titled as GUIDs because  │
│  retitle only runs on narrow lifecycle triggers.       │
│                                                        │
│  in my head now...                                     │
│  What else have you noticed about when titles do or    │
│  do not change?                                        │
╰────────────────────────────────────────────────────────╯
```

After this, new substantive material should usually render as `STORY THICKENED` within the same Exploratory Story.

For early thickening cards, prefer this anatomy:

```text
STORY THICKENED
  new material
    the small piece just added by the Navigator

  ▶ current story
    the accumulated story, visibly deepened by the new material

  in my head now...
    one optional thought or question that helps the Navigator continue exploring
```

Avoid an `effect` section during early intake unless it is genuinely useful. It can distract from the central experience: watching the current story thicken. Also avoid `next question`, which can make Exploration feel like a scripted assistant flow rather than an open inquiry. Use `in my head now...` for early exploratory continuation because it reads as live thinking, not a required next step.

`STORY THICKENED` is not required on every turn. It should render when new material changes the accumulated story: a new fact, distinction, hypothesis, correction, tension, constraint, or shift in center. Lightweight conversation can continue between cards.

## Signal Reactivated

A `Signal Reactivated` component appears when a kept signal returns from Signal Radar into active attention.

It should show the previous state and the reactivation route.

Routes:

```text
open new ES
  creates a new Exploratory Story

thicken existing ES
  adds material to an active Exploratory Story

join cluster
  groups with related signals without opening a story yet

archive
  removes the signal from active radar because it no longer matters or was absorbed elsewhere
```

```text
Exploration
╭────────────────────────────────────────────────────────╮
│        △→▧  SIGNAL REACTIVATED                         │
│                                                        │
│  signal                                                │
│  Journey detection after conversation start            │
│                                                        │
│  previous state                                        │
│  kept for later in Signal Radar                        │
│                                                        │
│  route                                                 │
│  opens new Exploratory Story                           │
│                                                        │
│  new story                                             │
│  ES-002 Journey assignment lifecycle                   │
╰────────────────────────────────────────────────────────╯
```

## Possible Attractor Hint

A `Possible Attractor Hint` is a subtle component for the moment when the Driver sees a potential center of gravity but still needs Navigator validation.

It should appear when the story is narrowing around a center but has not yet become a Delivery candidate. The Driver should use it before jumping to solution or promotion.

It should behave like `Possible Signal`: lightweight, provisional, and confirmable through conversation.

```text
◎ Possible attractor
Mobile address validation and recovery feedback.

The material seems to be clustering here. “Rewrite the whole checkout” may be a pressure-driven attractor. Does this reading fit?
```

If the Navigator confirms or corrects the reading, the Driver should incorporate the attractor in the next `STORY THICKENED` card. If the Navigator rejects it, the Driver ignores the attractor and returns to the last valid story card.

## Emergent Attractor

An `Emergent Attractor` component is usually a proposed reading that asks for Navigator confirmation before it is absorbed into the story.

It may be skipped only when the Navigator has already named or accepted the center directly in natural conversation. Otherwise, the surface should ask a confirmation question such as: `Does this attractor make sense to you?`

It should show the proposed center of gravity, the clustered signals, the resonance, any misleading attractor risk, and the thickened story so far.

The attractor is a visual-method cue, not the final artifact. Its job is to pull better story integration. After confirmation, the next `STORY THICKENED` card is where the value becomes durable.

```text
Exploration
╭────────────────────────────────────────────────────────╮
│        ◎  EMERGENT ATTRACTOR                           │
│                                                        │
│  Mobile address validation and recovery feedback       │
│                                                        │
│  ◬ clustered signals                                  │
│    These observations seem to belong together:         │
│    support tickets mention address errors              │
│    analytics show mobile-heavy drop-off                │
│    logs show validation_error around address step      │
│                                                        │
│  ◉ resonance                                           │
│    support + analytics + logs point to the same area   │
│                                                        │
│  caution                                               │
│    “rewrite checkout” may be a misleading attractor    │
│                                                        │
│  inquiry                                               │
│  Is the drop-off caused by mobile validation and       │
│  recovery feedback, or is rewrite pressure too broad?  │
│                                                        │
│  proposed reading                                      │
│  The story may be organizing around mobile address     │
│  validation. Leadership pressure pulls toward rewrite, │
│  but the strongest evidence points narrower.           │
│                                                        │
│  confirm                                               │
│  Does this attractor make sense to you?                │
╰────────────────────────────────────────────────────────╯
```

## Attractor Evolution

An attractor may change as the story thickens. The Driver should show whether the attractor was refined, expanded, superseded, or rejected.

Use this when the Navigator might wonder what happened to the previous center.

```text
Exploration
╭────────────────────────────────────────────────────────╮
│        ◎⇢◎  ATTRACTOR REFINED                          │
│                                                        │
│  from                                                  │
│  Conversation title lifecycle                          │
│                                                        │
│  to                                                    │
│  Conversation metadata lifecycle                       │
│                                                        │
│  why                                                   │
│  Summary shares the same lifecycle problem as title:   │
│  it can be too early, stale, weak, or misleading.      │
│                                                        │
│  absorbs                                               │
│  Title lifecycle remains inside the broader metadata   │
│  lifecycle.                                            │
│                                                        │
│  keeps outside                                         │
│  Journey detection after conversation start            │
│                                                        │
│  confirm                                               │
│  Does this refined attractor make sense to you?        │
╰────────────────────────────────────────────────────────╯
```

If accepted, render `STORY THICKENED` with the updated current story. If rejected, keep the previous attractor and story state.

## Possible Experiment Hint

A `Possible Experiment Hint` is a lightweight component for the moment when the Driver sees that the inquiry may need evidence from outside the conversation.

It should appear before a formal `Experiment Proposal` when the learning move is plausible but not yet accepted by the Navigator.

Use when:

- hypotheses are competing and further talk would only speculate;
- the story depends on whether something is detectable;
- a Delivery decision depends on missing evidence;
- the next useful answer requires data, logs, transcripts, a prototype, a code spike, a manual check, or comparison.

```text
🧪 Possible experiment
Classify a few conversation transcripts turn by turn.

Would this help answer whether retitle needs per-turn logic, or should we keep exploring conversationally?
```

If the Navigator accepts or adjusts the learning move, render an `Experiment Proposal`. If the Navigator declines, continue the Exploratory Story without treating the experiment as committed.

## Experiment Proposal

An `Experiment Proposal` component appears when an Exploratory Story needs new evidence before it can form a candidate and the Navigator accepts or asks for that learning move.

It should show the proposed learning move, the learning intent, the method, the current situation, and the current story. It should make clear that the commitment is learning, not delivery.

Experiments may remain in progress across multiple observations. Do not render `Candidate Formed` merely because one observation is useful. Candidate formation requires enough evidence relative to the experiment's learning intent.

For transcript experiments, the proposal should define the observation unit. It may be a user message, a full exchange, a fixed turn window, or the conversation state after a lifecycle event. This is especially important for metadata experiments, where the assistant response may reveal intent that the user's first prompt did not.

```text
Exploration
╭────────────────────────────────────────────────────────╮
│        🧪  EXPERIMENT PROPOSAL                         │
│                                                        │
│  Observe where address validation fails.               │
│                                                        │
│  from: ES-042 Checkout address-step abandonment        │
│  learning intent: test the mobile validation attractor │
│  method: short instrumentation window                  │
│  commitment: learning, not delivery                    │
│                                                        │
│  current situation                                     │
│  Evidence points to mobile address validation, but     │
│  the team does not yet know where validation fails.    │
│                                                        │
│  current story                                         │
│  The story is strong enough to learn from, but not     │
│  yet strong enough to become delivery work.            │
╰────────────────────────────────────────────────────────╯
```

## Experiment In Progress

An `Experiment In Progress` component appears when an accepted experiment produces observations but has not yet answered the learning question strongly enough to form a candidate.

```text
Exploration
╭────────────────────────────────────────────────────────╮
│        🧪  EXPERIMENT IN PROGRESS                      │
│                                                        │
│  Manual title-decision rubric                          │
│                                                        │
│  observation                                           │
│  First user prompt alone may be too thin, but the      │
│  first assistant response may reveal enough intent for │
│  a useful title.                                       │
│                                                        │
│  adjusted question                                     │
│  Should early metadata use the first user prompt only, │
│  or the first exchange: user prompt + assistant        │
│  response?                                             │
│                                                        │
│  status                                                │
│  still learning, not candidate formation               │
╰────────────────────────────────────────────────────────╯
```

## Carry Forward Notes

A `Carry Forward Notes` component appears when Exploration has produced implementation-relevant findings that may be useful for Delivery, but the work is not ready or not yet chosen for promotion.

It should ask for Navigator confirmation before preserving the notes. Carrying notes forward does not create a Delivery commitment.

Use for:

- constraints or non-goals;
- readiness thresholds;
- examples and edge cases;
- validation ideas;
- technical observations;
- scope boundaries;
- risks that should not be forgotten.

```text
Exploration
╭────────────────────────────────────────────────────────╮
│        ◨  CARRY FORWARD NOTES?                         │
│                                                        │
│  from: ES-001 Conversation metadata lifecycle          │
│                                                        │
│  These findings may matter if this becomes Delivery:   │
│                                                        │
│  - metadata lifecycle is shared, but readiness is      │
│    per field                                           │
│  - title may be ready after first exchange, not first  │
│    prompt                                              │
│  - summary likely needs more substance than title      │
│  - metadata state should track source, confidence,     │
│    locks, and readiness                                │
│                                                        │
│  preserve?                                             │
│  Should I keep these as Carry Forward Notes for a      │
│  possible Delivery handoff?                            │
╰────────────────────────────────────────────────────────╯
```

If accepted, render the preserved version without the question mark:

```text
◨ Carry Forward Notes captured
Preserved for possible Delivery handoff; no Delivery commitment created.
```

## Candidate Formed

A `Candidate Formed` component appears when an experiment result, inquiry, hypothesis, or thickened Exploratory Story has enough form to be considered for Delivery.

It should show the candidate, the source Exploratory Story, the readiness, the relevant result or evidence, and the current story. It should make clear that Navigator decision is still required.

```text
Exploration
╭────────────────────────────────────────────────────────╮
│        🟩◮  CANDIDATE FORMED                           │
│                                                        │
│  Improve mobile address validation recovery.           │
│                                                        │
│  surface: Candidate Gate                               │
│  from: ES-042 Checkout address-step abandonment        │
│  readiness: enough form for Delivery              │
│  commitment: requires Navigator decision               │
│                                                        │
│  experiment result                                     │
│  Mobile autofill values are rejected without useful    │
│  field-level recovery guidance.                        │
│                                                        │
│  current story                                         │
│  The ES has thickened from unknown checkout drop-off   │
│  into a concrete mobile validation recovery problem.   │
╰────────────────────────────────────────────────────────╯
```

## Exploration Documented

An `Exploration Documented` component appears when the Driver generates or updates durable documentation for an Exploratory Story.

This may happen when a story promotes, pauses, archives, reaches an important learning boundary, or needs to be preserved for future work.

For promoted work, use two artifacts:

```text
full exploration document
  stored in the Exploration area
  contains the complete exploratory narrative

Delivery Story exploration summary
  stored beside the future roadmap Delivery Story, User Story, or Technical Story
  summarizes the exploration and links to the full document
```

Most promoted candidates should create a Delivery Story-level summary, because Exploration usually discovers a delivery arc. User Story-level summaries are reserved for rare direct-to-user-story promotions.

The full document should include:

- initial signal;
- story thickening timeline;
- attractors and attractor evolution;
- experiments and findings;
- Carry Forward Notes;
- kept-for-later signals;
- candidate rationale;
- Delivery handoff seed, when applicable.

```text
Exploration
╭────────────────────────────────────────────────────────╮
│        ◨  EXPLORATION DOCUMENTED                       │
│                                                        │
│  source                                                │
│  ES-001 Conversation metadata lifecycle                │
│                                                        │
│  full exploration document                             │
│  docs/project/exploration/es-001-conversation-         │
│  metadata-lifecycle/index.md                           │
│                                                        │
│  Delivery Story exploration summary                     │
│  docs/project/roadmap/.../exploration-summary.md       │
│                                                        │
│  includes                                              │
│  ✓ initial signal                                      │
│  ✓ thickened story                                     │
│  ✓ attractor evolution                                 │
│  ✓ experiment result                                   │
│  ✓ Carry Forward Notes                                 │
│  ✓ kept-for-later signals                              │
│  ✓ Delivery handoff seed                               │
╰────────────────────────────────────────────────────────╯
```

Boundary:

- Exploration Documentation records learning; it does not create implementation commitment.
- The Delivery Story or child story summary is a bridge, not a duplicate of the full exploration document.
- Delivery Story-level summaries are the default for promoted Exploration candidates; Story-level summaries require an explicit one-story-size justification.
- Non-promoted Exploratory Stories can still be documented in the Exploration area without creating any roadmap story.

## Candidate Promoted

A `Candidate Promoted` component appears when the Navigator accepts a candidate into Delivery.

It should make the handoff visible. Promotion should not leave the candidate as an abstract idea; it should show where the work enters the Delivery roadmap and what would make it verifiable.

Default rule: promoted Exploration candidates become a Delivery Story. Direct promotion to a User Story is rare and should be justified by showing that the candidate has one behavior/capability boundary and one end-to-end validation route.

Required handoff fields:

```text
from Exploration
  source Exploratory Story

suggested roadmap placement
  Value / CV -> Delivery Story

Delivery Story seed
  behavior arc or capability arc discovered by Exploration

candidate User Stories and Technical Stories
  proposed behavior/capability and internal checkpoints inside the Delivery Story

validation seeds
  first routes by which the Navigator could inspect each behavior/capability

exploration source
  full Exploration document and Delivery Story or child story exploration summary

pull state
  ready for Delivery Story expansion | ready for Navigator pull | backlog | needs more exploration
```

Example:

```text
Exploration → Delivery Handoff
╭────────────────────────────────────────────────────────╮
│        🟩◮→🟦▣  CANDIDATE PROMOTED                     │
│                                                        │
│  Conversation metadata lifecycle                       │
│                                                        │
│  from Exploration                                      │
│  ES-001 Conversation title retitle timing              │
│                                                        │
│  suggested roadmap placement                           │
│  🟪[CV9] Mirror 1.0                                    │
│    └─ 🟦[E?] Conversation metadata lifecycle           │
│                                                        │
│  Delivery Story seed                                             │
│  Mirror manages title, summary, tags, and metadata     │
│  state through lifecycle decisions with per-field      │
│  readiness.                                            │
│                                                        │
│  candidate User / Technical Stories                │
│  🟨[S?] Dry-run metadata lifecycle decisions            │
│  🟨[S?] Apply safe title repair lifecycle              │
│  🟨[S?] Summary readiness lifecycle                    │
│                                                        │
│  validation seeds                                      │
│  Inspect dry-run decisions; verify title repair;       │
│  verify summary readiness behavior.                    │
│                                                        │
│  exploration source                                    │
│  full brief: docs/project/exploration/es-001.../       │
│              index.md                                  │
│  Delivery Story summary: roadmap/.../exploration-summary.md      │
│                                                        │
│  pull state                                            │
│  ready for Delivery Story expansion                              │
╰────────────────────────────────────────────────────────╯
```

Boundary:

- Promotion creates Delivery visibility, not automatic implementation.
- Roadmap placement may be suggested when exact CV, Delivery Story, User Story, or Technical Story codes are not known yet.
- If no suitable Delivery Story exists, the handoff may recommend Delivery Story expansion instead of forcing a story into the wrong parent.

## Capture Flash

`Capture Flash` is the first visual component for the `signal_captured` event.

Purpose:

```text
confirm that a signal was preserved
avoid interrupting the user's thought
show that no commitment was created
show that the signal may open or thicken an Exploratory Story
```

The component should be small, transient, and low-friction. It should not look like a task card or a ticket.

Draft:

```text
Exploration
╭────────────────────────────────────────────────────────╮
│        🟧▲  SIGNAL CAPTURED                            │
│                                                        │
│  Mirror exploratory questions are getting lost         │
│  between loose memory, roadmap, and tasks.             │
│                                                        │
│  field: mirror-mind                                    │
│  state: captured                                       │
│  commitment: none                                      │
│                                                        │
│  possible thickening                                  │
│                                                        │
│  now             if it gathers weight    if it matures │
│  🟧▲ captured ─▶ ▧ story thickens ────▶ 🟩◮ candidate │
│       │                    │                 │         │
│       │                    └─ ◬ cluster      │         │
│       │                       ◉ resonance    │         │
│       │                       ◎ attractor    │         │
│       └──────────── rests / archives ◀───────┘         │
│                                                        │
│  If you want to continue, write freely about           │
│  this signal. Maestro remains in listening mode.       │
╰────────────────────────────────────────────────────────╯
```

## Signal Thickening Flow

`Signal Thickening Flow` is the compact map of possible movement after capture.

It should not imply that every signal must become a candidate. Resting or archiving is a valid outcome.

```text
now             if it gathers weight    if it matures
🟧▲ captured ─▶ ▧ story thickens ────▶ 🟩◮ candidate
     │                    │                 │
     │                    └─ ◬ cluster      │
     │                       ◉ resonance    │
     │                       ◎ attractor    │
     └──────────── rests / archives ◀───────┘
```

Conceptual mapping:

```text
captured
  the signal was preserved

story thickens
  the Exploratory Story gathers context, relation, evidence, contradiction, or interpretation

cluster
  related signals form a readable pattern

resonance
  the signal, cluster, inquiry, or story echoes across sources or returns with force

attractor
  the cluster or story begins pulling interpretation, attention, or action

candidate
  there is enough form to consider Delivery

rests / archives
  the signal remains preserved without becoming active work
```

## Language tone

The visual component should explain what the user can do without becoming a form.

Preferred invitation:

```text
If you want to continue, write freely about this signal. Maestro remains in listening mode.
```

Avoid overly metaphorical instructions that make the user ask what to do next.

Avoid form-like prompts such as:

```text
Capture this? [yes] [edit] [no]
```

The experience should feel like the system is listening and preserving, not assigning the user another administrative task.

## Open questions

- Should `Capture Flash` always include `Signal Thickening Flow`, or only when there is enough space?
- Should IDs be hidden by default in conversational surfaces and shown only in operational views?
- Should colors represent resonance, maturity, attractor strength, or a combination?
- Should `investigation` appear visually, while `inquiry` remains the conceptual entity?
- What is the best visual form for the Narrative Field as a bird's-eye view of active Exploratory Stories?
- What is the best visual form for an Exploratory Story View: timeline, stack, assemblage map, constellation, narrative card, or a hybrid?
- How should Signal Radar, Narrative Field, Exploratory Story View, and Candidate Gate translate to the web app without becoming a kanban board?
