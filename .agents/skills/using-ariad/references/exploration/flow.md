# Exploratory Flow

This document explains Ariad Exploration through a practical sequence.

The [Conceptual Model](conceptual-model.md) names the concepts. This page shows how those concepts appear in use: events, story thickening, and visual feedback.

The flow is not a rigid pipeline. Exploratory work can loop, branch, pause, weaken, or intensify. The sequence below is a teaching path.

At any point, the Navigator may ask for a birds-eye view of Exploration. The Driver should answer with a **Narrative Field Snapshot**: the Exploration counterpart to Delivery's Roadmap Snapshot.

```text
Exploration
╭────────────────────────────────────────────────────────╮
│        ◬  NARRATIVE FIELD SNAPSHOT                     │
│                                                        │
│  active Exploratory Stories                            │
│  ▧ ES-001 Conversation metadata lifecycle              │
│    state: promoted to Delivery                         │
│    promoted as: CV9.DS7 Conversation Metadata          │
│    Lifecycle                                           │
│                                                        │
│  experiments                                           │
│  🧪 Manual metadata-decision rubric                     │
│    state: completed                                    │
│                                                        │
│  nearby kept signals / Signal Radar excerpt            │
│  △ Journey detection after conversation start          │
│    state: kept for later                               │
│    relation: adjacent to ES-001                        │
╰────────────────────────────────────────────────────────╯
```

The snapshot shows field state; it does not create Delivery commitment. It may include nearby kept signals as a scoped Signal Radar excerpt, but it should not dump the whole Signal Radar.

## Step 1. Signal Capture

Exploration begins when something that might matter appears before it is clear enough for delivery.

The Navigator says:

> Users abandon checkout after the address step, but we do not know why.

There are two entry paths.

A **Navigator-expressed signal** happens when the Navigator explicitly says something that behaves like a signal.

A **Driver-detected signal** happens when the Driver notices a possible signal inside the conversation or work context.

The default policy is:

```text
Detection can be inferred.
Capture should be visible.
Persistence should initially require Navigator expression, explicit keep-for-later intent, or exploratory engagement.
```

When the Driver detects a possible signal, it should show a subtle hint, not create a persisted record silently.

```text
△ Possible signal
Checkout abandonment may be tied to address validation.

Is this relevant? Tell me more to explore it now, or say “keep for later”.
```

If the Navigator says `keep for later`, the signal enters **Signal Radar** but does not open an Exploratory Story.

If the Navigator replies with substantive detail, correction, example, hypothesis, concern, or added context, that reply counts as exploratory engagement. The Driver should not repeat the relevance question. It should open an Exploratory Story and show that the story is beginning to thicken.

The transition should still be lightweight. At this point the Navigator may be dumping feelings, examples, and partial knowledge. The Driver should make the ES visible without starting heavy sensemaking.

```text
Exploration
╭────────────────────────────────────────────────────────╮
│        ▧  EXPLORATORY STORY OPENED                     │
│                                                        │
│  ES-042  Conversation title retitle timing             │
│                                                        │
│  opened from: △ possible signal                        │
│  surface: Exploratory Story View                       │
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

Use only one focused follow-up. In early Exploration cards, name it `in my head now...` so it reads as a live thought or invitation rather than the next step in a fixed sequence. Defer `Emerging shape`, clusters, attractors, and multi-point summaries until enough material has accumulated. From this point onward, new substantive material should be treated as story thickening, not as a new possible signal unless it clearly opens a separate thread.

In `STORY THICKENED` cards, the most important section is the accumulated `current story`. It should visibly preserve and deepen the thread instead of merely replacing the previous turn. Keep `new material` small, omit separate `effect` sections in early intake, and let the thickened current story carry the integration.

## Signal Reactivation

A kept signal can be reactivated when the Navigator or Driver brings it back into attention.

Reactivation does not always mean opening new work. The Driver should route the signal explicitly:

```text
open new ES
  the signal has enough independent center to become its own Exploratory Story

thicken existing ES
  the signal adds material to a current Exploratory Story

join cluster
  the signal belongs with other signals but does not yet need its own story

archive
  the signal no longer matters, was absorbed elsewhere, or is misleading
```

Example:

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
│                                                        │
│  ▶ current story                                      │
│  Some conversations may begin without a Journey, but   │
│  later turns can reveal one that Mirror should attach  │
│  for visibility and organization.                      │
│                                                        │
│  in my head now...                                     │
│  Should Journey assignment use the same metadata       │
│  lifecycle, or remain a separate safety boundary?      │
╰────────────────────────────────────────────────────────╯
```

## Step 2. Exploratory Story Opens

A signal becomes an Exploratory Story when the Navigator engages in a way that adds material, relation, or direction.

Engagement opens the story. Continued engagement thickens it.

The Navigator adds:

> Support is telling us that customers are complaining about confusing address errors.

The Driver responds normally to the conversation:

> That is enough to stop treating this as a generic checkout drop-off. The first
> concrete clue is the user's recovery experience: people are seeing address errors,
> but the errors are confusing.

In addition to the normal response, the Driver can name the story, move it from **Signal Radar** into the **Narrative Field**, and show an **Exploratory Story View** with the thickened story.

```text
Exploration
╭────────────────────────────────────────────────────────╮
│        ▧  EXPLORATORY STORY OPENED                     │
│                                                        │
│  ES-042  Checkout address-step abandonment             │
│                                                        │
│  opened from: 🟧▲ signal captured                       │
│  surface: Exploratory Story View                       │
│  state: thickening                                     │
│  commitment: none                                      │
│                                                        │
│  current story                                         │
│  Users abandon checkout after the address step, but    │
│  the reason is still unclear. Support tickets mention  │
│  confusing address errors.                             │
╰────────────────────────────────────────────────────────╯
```

## Step 3. Story Thickens

The story thickens as more material joins it.

This is not just adding facts. The story changes shape as the field gains relation, contrast, contradiction, and direction.

In real use, the Driver does not reply with only the thickened story. The Driver answers the Navigator's prompt normally, then may add a visual component that preserves the current state of the Exploratory Story.

`STORY THICKENED` is not a per-turn receipt. It appears when the new material changes the accumulated story.

Good triggers include:

- a new fact, example, or source;
- a useful distinction;
- a hypothesis or correction;
- a new tension or constraint;
- a shift in what the story seems to be about;
- material that makes a candidate or attractor more likely.

The Driver may skip the card for lightweight back-and-forth, direct suggestions, clarifying questions, or micro-confirmations. Those turns can still inform the next thickened story.

The Navigator adds:

> I checked analytics. The drop-off is much heavier on mobile.

The Driver responds normally:

> That changes the shape of the problem. If the drop-off is heavier on mobile, we
> should avoid jumping straight to a checkout-wide explanation. Mobile input,
> layout, autofill, and validation behavior are now worth separating.

The Driver may also show an **Exploratory Story View**:

```text
Exploration
╭────────────────────────────────────────────────────────╮
│        ▧  STORY THICKENED                              │
│                                                        │
│  ES-042  Checkout address-step abandonment             │
│                                                        │
│  new material                                          │
│  Analytics show the drop-off is mobile-heavy.          │
│                                                        │
│  ▶ current story                                      │
│  Users abandon checkout after the address step, but    │
│  the reason is still unclear. Support tickets point to │
│  confusing address errors, and analytics now suggests  │
│  the problem may involve mobile input, layout,         │
│  autofill, or validation behavior.                     │
│                                                        │
│  in my head now...                                     │
│  What happens differently on mobile?                   │
╰────────────────────────────────────────────────────────╯
```

The Navigator adds:

> I looked at the frontend logs. There are validation_error events around the
> address step, but they do not say which field failed.

The Driver responds normally:

> That makes validation more central, but the observability is still too weak.
> We know errors are happening around the address step, but not which field fails
> or what value shape is being rejected.

The Driver may update the **Exploratory Story View**:

```text
Exploration
╭────────────────────────────────────────────────────────╮
│        ▧  STORY THICKENED                              │
│                                                        │
│  ES-042  Checkout address-step abandonment             │
│                                                        │
│  new material                                          │
│  Logs show validation_error events without field data. │
│                                                        │
│  ▶ current story                                      │
│  Users abandon checkout after the address step.        │
│  Support points to confusing address errors, analytics │
│  shows heavier mobile drop-off, and logs now show      │
│  opaque validation failures around the same step.      │
│                                                        │
│  in my head now...                                     │
│  What field or value shape might be failing?           │
╰────────────────────────────────────────────────────────╯
```

The Navigator adds:

> QA tried to reproduce it on desktop, but the issue does not happen consistently.

The Driver responds normally:

> That strengthens the mobile-specific reading. If desktop reproduction is
> inconsistent, the next useful question is whether mobile behavior, especially
> autofill or input shape, is producing values the system rejects poorly.

The Driver may update the **Exploratory Story View** again:

```text
Exploration
╭────────────────────────────────────────────────────────╮
│        ▧  STORY THICKENED                              │
│                                                        │
│  ES-042  Checkout address-step abandonment             │
│                                                        │
│  new material                                          │
│  QA cannot reproduce the issue consistently on desktop.│
│                                                        │
│  ▶ current story                                      │
│  The checkout issue is taking shape as a mobile-heavy  │
│  address validation problem with unclear recovery:     │
│  support hears confusing errors, analytics shows       │
│  mobile-heavy drop-off, logs expose opaque validation  │
│  failures, and desktop reproduction is inconsistent.   │
│                                                        │
│  in my head now...                                     │
│  Is mobile autofill or input formatting involved?      │
╰────────────────────────────────────────────────────────╯
```

## Step 4. Cluster, Resonance, and Attractor Appear

As the story thickens, related material may cluster and resonate.

A cluster says that several signals can currently be read together as a pattern. In visual surfaces, prefer the clearer label `clustered signals` with a short explanation: `These observations seem to belong together:`. Resonance says that the pattern is echoing across sources or returning with force. An attractor appears when the pattern starts pulling interpretation, attention, or action.

The attractor is not a delivery input by itself. It helps the Driver and Navigator see the center of gravity around which the Exploratory Story can thicken. The attractor matters because it pulls better story integration; the thickened story is the durable artifact.

An emergent attractor should appear when the current story stops feeling like a list of observations and starts organizing around a center. Common signs:

- multiple pieces of material point to the same explanation;
- the Navigator names or confirms a central tension;
- one framing starts pulling future questions toward itself;
- alternatives begin to look like variations around a deeper pattern;
- the conversation is narrowing, but not yet ready for a Delivery candidate.

The Driver should not wait until the solution is known. The attractor is the moment of visible center-of-gravity, not the final answer.

Attractors should normally be proposed before they are incorporated. The Driver asks whether the attractor makes sense. If the Navigator accepts or corrects it, the next `STORY THICKENED` card incorporates the attractor into the current story. If the Navigator rejects it, the Driver ignores the attractor and returns to the last valid story state.

Attractors may evolve:

```text
refined / expanded
  the old attractor was useful but too narrow
  example: Conversation title lifecycle -> Conversation metadata lifecycle

superseded
  a different center explains the story better
  example: Title timing -> Journey assignment lifecycle

rejected
  the proposed center does not fit the Navigator's reading
  return to the previous story state
```

When an attractor evolves, the Driver should show what changed and then thicken the story around the updated center if the Navigator accepts it.

The Navigator adds:

> This is starting to sound less like “checkout is broken” and more like “mobile
> address validation is failing and users do not know how to recover”. However,
> leadership are impatient and suggesting we might need to rewrite the whole checkout.

The Driver proposes an emergent attractor with a subtle visual hint and checks whether it fits the Navigator's reading:

```text
◎ Possible attractor
Mobile address validation and recovery feedback.

The material seems to be clustering here. “Rewrite the whole checkout” may be a pressure-driven attractor. Does this reading fit?
```

The Navigator responds:

> Yes, that fits. The rewrite idea feels like impatience. The concrete pattern is
> mobile address validation and users not knowing how to recover.

The Driver thickens the story around the confirmed attractor.

```text
Exploration
╭────────────────────────────────────────────────────────╮
│        ▧  STORY THICKENED                              │
│                                                        │
│  ES-042  Checkout address-step abandonment             │
│                                                        │
│  new material                                          │
│  Navigator confirmed the attractor: mobile address     │
│  validation and recovery feedback.                     │
│                                                        │
│  ▶ current story                                      │
│  The checkout story is now organized around mobile     │
│  address validation and recovery feedback. Support     │
│  tickets, analytics, and logs seem to belong together  │
│  around this narrower center, while checkout rewrite   │
│  pressure may be broader than the evidence supports.   │
│                                                        │
│  in my head now...                                     │
│  What would help test whether this attractor is real?  │
╰────────────────────────────────────────────────────────╯
```

The visual feedback can make the emerging pattern visible without turning it into a delivery commitment.

The Driver can then open an inquiry around the attractor:

> Is the checkout drop-off primarily caused by mobile address validation and poor
> recovery feedback, or is the pressure to rewrite checkout pulling the team too
> broadly?

The Navigator adds:

> I want to answer that before we propose any implementation. If the validation
> problem is real, we should learn where it fails instead of redesigning the whole
> checkout.

The Driver thickens the story again:

> The story is now organized around a confirmed attractor: mobile address validation
> and recovery feedback. Leadership pressure is pulling toward a broad checkout
> rewrite, but the Navigator wants to test whether the narrower validation story is
> strong enough before committing to implementation. The next learning move is an
> experiment: reveal where validation fails and whether the failure is actually
> mobile-specific.

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
│  current story                                         │
│  The story is organized around mobile address          │
│  validation. Leadership pressure pulls toward rewrite, │
│  but the strongest evidence points narrower.           │
╰────────────────────────────────────────────────────────╯
```

## Step 5. Experiment Proposal

An experiment begins when the Exploratory Story needs new evidence before it can form a candidate.

The experiment is not delivery work by default. It is a safe-to-learn move inside exploration.

The Driver does not have to wait for the Navigator to ask for an experiment explicitly. It may suggest one when the conversation reaches a practical uncertainty that cannot be resolved by talk alone.

Good triggers include:

- hypotheses are competing and more conversation would only speculate;
- the story depends on whether something is technically or semantically detectable;
- a Delivery decision depends on evidence not yet present;
- the Navigator asks “could we know whether...?” or “do we even need this?”;
- the next useful answer requires data, logs, transcripts, a prototype, a code spike, a manual check, or a comparison.

The Driver can first use a lightweight hint:

```text
🧪 Possible experiment
Classify a few conversation transcripts turn by turn.

Would this help answer whether retitle needs per-turn logic, or should we keep exploring conversationally?
```

If the Navigator accepts or adjusts the learning move, the Driver renders an `EXPERIMENT PROPOSAL`.

The Navigator adds:

> Before deciding on a fix, I think we need to know exactly where validation is
> failing and whether it is really mobile-specific.

The Driver proposes an experiment:

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

While an experiment is running, the Driver should not jump to `Candidate Gate` after a single useful observation unless the proposal defined that as enough evidence. It should show `EXPERIMENT IN PROGRESS` when new observations adjust the learning question but do not yet settle it.

For transcript experiments, define the unit of observation carefully. A turn may mean only the user's message, or it may mean the user message plus the assistant response that reveals how the session understood the request. This matters when testing title or summary generation: the first assistant response may contain enough semantic context to avoid a weak placeholder.

```text
Exploration
╭────────────────────────────────────────────────────────╮
│        🧪  EXPERIMENT IN PROGRESS                      │
│                                                        │
│  Manual title-decision rubric                          │
│                                                        │
│  observation                                           │
│  The first user message alone may be too thin, but the │
│  first assistant response may reveal enough intent for │
│  a better title.                                       │
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

## Step 6. Carry Forward Notes, Experiment Completion, and Candidate Formation

Before an experiment completes or a candidate forms, the Driver may notice that implementation-relevant findings are accumulating.

These findings should not be silently promoted into Delivery, but they also should not be lost inside the transcript. The Driver can ask whether to preserve them as Carry Forward Notes.

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
│  - tags may depend on summary-level substance          │
│  - metadata state should track source, confidence,     │
│    locks, and readiness                                │
│                                                        │
│  preserve?                                             │
│  Should I keep these as Carry Forward Notes for a      │
│  possible Delivery handoff?                            │
╰────────────────────────────────────────────────────────╯
```

If the Navigator accepts, the notes attach to the Exploratory Story and can later populate the Delivery handoff. If the Navigator declines, the exploration continues without treating them as preserved implementation guidance.

An experiment completes when it changes the exploratory field with new observation, evidence, or contradiction.

The Navigator returns with the result:

> The data confirms it. Most failures are on mobile, and the rejected values are
> coming from autofill. Users are getting a generic error instead of field-level
> recovery guidance.

The Driver thickens the story with the experiment result:

> The mobile address validation attractor is now supported by the experiment.
> The drop-off is not just near the address step; it concentrates around mobile
> autofill values that validation rejects without useful recovery guidance. The
> story has enough form to become a delivery candidate.

The Driver forms the candidate:

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

## Step 7. Candidate Promotes, Pauses, or Archives

A candidate has three common exits from the Candidate Gate.

It can be promoted into Delivery when the Navigator accepts the candidate.

Before or during promotion, the Driver should offer to generate Exploration Documentation. This is especially important when the exploration contains attractor evolution, experiments, Carry Forward Notes, or kept-for-later signals.

The full document belongs to the Exploration area because it records the exploratory history. If the candidate promotes, the future Delivery Story should also receive a concise exploration summary with a link to the full document.

Promotion means the candidate enters the Delivery field. By default, promoted Exploration candidates become a Delivery Story, because they usually contain multiple behavior boundaries. The handoff should include suggested roadmap placement, Delivery Story seed, candidate User Stories and Technical Stories, validation seeds, pull state, and links to relevant Exploration Documentation. Promotion does not necessarily mean immediate implementation; the Delivery Story may be ready for expansion, placed in backlog, or narrowed into a rare direct User Story when it is truly behavior-sized.

The Navigator says:

> Yes. Promote this into delivery work.

The Driver may first generate documentation:

```text
exploration_documented
  source: ES-042 Checkout address-step abandonment
  full_document: docs/project/exploration/es-042-checkout-address-step-abandonment/index.md
  delivery_summary: docs/project/roadmap/cv2-checkout-recovery/cv2-ds3-mobile-validation-recovery/exploration-summary.md
```

```text
Exploration
╭────────────────────────────────────────────────────────╮
│        ◨  EXPLORATION DOCUMENTED                       │
│                                                        │
│  source                                                │
│  ES-042 Checkout address-step abandonment              │
│                                                        │
│  full exploration document                             │
│  docs/project/exploration/es-042-checkout-address-     │
│  step-abandonment/index.md                             │
│                                                        │
│  delivery story summary                                │
│  docs/project/roadmap/.../cv2-ds3-mobile-validation-   │
│  recovery/exploration-summary.md                       │
│                                                        │
│  includes                                              │
│  ✓ initial signal                                      │
│  ✓ thickened story                                     │
│  ✓ attractor and experiment result                     │
│  ✓ Carry Forward Notes                                 │
│  ✓ kept-for-later signals                              │
│  ✓ Delivery handoff seed                               │
╰────────────────────────────────────────────────────────╯
```

The Driver records the transition from candidate to roadmap story:

```text
candidate_promoted
  from: ES-042 Checkout address-step abandonment
  to: Delivery roadmap
  placement: CV2 Checkout Recovery / DS3 Mobile validation recovery
  delivery_story_seed: Reduce mobile address validation abandonment with recoverable field-level guidance.
  candidate_stories:
    - TS1 Identify rejected mobile autofill value shapes
    - US1 Show field-level recovery guidance
    - US2 Validate recovery behavior in mobile checkout
  validation_seeds:
    - inspect rejected value diagnostics
    - reproduce mobile address failure and verify field-level guidance
  exploration_document: docs/project/exploration/es-042-checkout-address-step-abandonment/index.md
  exploration_summary: docs/project/roadmap/cv2-checkout-recovery/cv2-ds3-mobile-validation-recovery/exploration-summary.md
  pull_state: ready for Delivery Story expansion
```

```text
Exploration
╭────────────────────────────────────────────────────────╮
│        🟩◮→🟦▣  CANDIDATE PROMOTED                     │
│                                                        │
│  Improve mobile address validation recovery.           │
│                                                        │
│  from Exploration                                      │
│  ES-042 Checkout address-step abandonment              │
│                                                        │
│  suggested roadmap placement                           │
│  🟪[CV2] Checkout Recovery                             │
│    └─ 🟦[DS3] Mobile validation recovery               │
│                                                        │
│  Delivery Story seed                                             │
│  Reduce mobile address validation abandonment with     │
│  recoverable field-level guidance.                     │
│                                                        │
│  candidate User / Technical Stories                │
│  ◼[TS1] Identify rejected mobile autofill shapes       │
│  🟨[US1] Show field-level recovery guidance            │
│  🟨[US2] Validate recovery behavior in mobile checkout │
│                                                        │
│  validation seeds                                      │
│  Inspect rejected value diagnostics; reproduce mobile  │
│  address failure and verify field-level guidance.      │
│                                                        │
│  exploration source                                    │
│  full brief: docs/project/exploration/es-042.../       │
│              index.md                                  │
│  Delivery Story summary: roadmap/.../exploration-summary.md      │
│                                                        │
│  pull state                                            │
│  ready for Delivery Story expansion                              │
╰────────────────────────────────────────────────────────╯
```

It can be paused when the candidate still matters but should not become delivery work yet.

The Navigator says:

> Not yet. Keep this in the Narrative Field until we have more confidence.

The Driver records the paused state:

```text
candidate_paused
  ES-042 remains in the Narrative Field
  state: paused
  last reading: mobile validation attractor likely, delivery not yet accepted
```

```text
Exploration
╭────────────────────────────────────────────────────────╮
│        ▧  STORY PAUSED                                 │
│                                                        │
│  ES-042 Checkout address-step abandonment              │
│                                                        │
│  surface: Narrative Field                              │
│  state: paused                                         │
│  reason: not enough confidence for Delivery       │
│                                                        │
│  current story                                         │
│  The ES remains meaningful, but the Navigator wants    │
│  more confidence before accepting delivery work.       │
│                                                        │
│  🟩◮ Candidate ─────▶ ▧ Narrative Field                 │
╰────────────────────────────────────────────────────────╯
```

Or it can be archived when it loses relevance, is absorbed elsewhere, or turns out to be a misleading attractor.

The Navigator says:

> Archive this for now. We found that a vendor outage caused the drop-off.

The Driver records:

```text
story_archived
  ES-042 leaves the active Narrative Field without being erased
```

```text
Exploration
╭────────────────────────────────────────────────────────╮
│        ⬛  STORY ARCHIVED                               │
│                                                        │
│  ES-042 Checkout address-step abandonment              │
│                                                        │
│  reason: vendor outage explained the drop-off          │
│                                                        │
│  final exploratory story                               │
│  The ES no longer explains the field well enough to    │
│  guide delivery, so it is preserved but inactive.      │
│                                                        │
│  🟩◮ Candidate ─────▶ ⬛ Archive                         │
╰────────────────────────────────────────────────────────╯
```

Promotion is not the only successful ending. Pausing preserves a live story without forcing delivery. Archiving prevents weak or misleading stories from becoming unnecessary delivery work.
