# Refinement Flow

This document explains Ariad Refinement through a practical sequence.

The [Conceptual Model](conceptual-model.md) names Workbench, Change Request,
Refinement Story, and Refinement Work. This page shows how they appear in use.

## Step 1. Navigator or Driver opens the Workbench field

Refinement begins when the Navigator chooses work from the Workbench or asks for
a quick adjustment to existing capability.

A runtime may render the Workbench beside the roadmap during activation:

```text
Refinement
╭────────────────────────────────────────────────────────╮
│        🧰  WORKBENCH SNAPSHOT                         │
│                                                        │
│  active Refinement Story                              │
│  none                                                  │
│                                                        │
│  draft Refinement Stories                             │
│  RS-001 Lifecycle surface refinement                   │
│                                                        │
│  open Change Requests                                 │
│  9 candidate                                           │
│  2 parked                                              │
│                                                        │
│  available moves                                      │
│  pull RS-001                                           │
│  add Change Request                                    │
│  create quick Refinement Story                         │
╰────────────────────────────────────────────────────────╯
```

The Workbench is not the roadmap. Choosing work from this field enters
Refinement Work.

## Step 2. Change Requests are captured

A Change Request records a requested change to something that already exists.

The Navigator may capture several CRs into a draft RS while using the product in
another session:

> Add this CR to RS-001: the Done surface makes push feel implied.

```text
Refinement
╭────────────────────────────────────────────────────────╮
│        🧾  CHANGE REQUEST CAPTURED                    │
│                                                        │
│  id                                                    │
│  CR-004                                                │
│                                                        │
│  title                                                 │
│  Clarify that Done does not imply push                 │
│                                                        │
│  target Refinement Story                               │
│  RS-001 Lifecycle surface refinement                   │
│                                                        │
│  area                                                  │
│  Lifecycle surface                                     │
│                                                        │
│  status                                                │
│  candidate                                             │
╰────────────────────────────────────────────────────────╯
```

A quick refinement path may be offered as a convenience. In that path, the
runtime creates a minimal RS, captures one CR, and pulls the RS immediately. The
shortcut is equivalent to the composed path; it is not a separate method
requirement.

```text
Refinement
╭────────────────────────────────────────────────────────╮
│        🧰  QUICK REFINEMENT OPENED                    │
│                                                        │
│  Refinement Story                                      │
│  RS-014 Fix empty work-field label                     │
│                                                        │
│  Change Requests                                       │
│  CR-014 Fix empty journey label                        │
│                                                        │
│  flow                                                  │
│  Refinement Work                                       │
╰────────────────────────────────────────────────────────╯
```

## Step 3. Navigator pulls a Refinement Story

Pull makes the RS active.

```text
Refinement
╭────────────────────────────────────────────────────────╮
│        🧰▶  REFINEMENT STORY PULLED                   │
│                                                        │
│  Refinement Story                                      │
│  RS-001 Lifecycle surface refinement                   │
│                                                        │
│  field being cared for                                 │
│  Ariad-adopted lifecycle surface                       │
│                                                        │
│  Change Requests                                       │
│  12 candidate                                          │
│                                                        │
│  next move                                             │
│  select the first Change Request                       │
╰────────────────────────────────────────────────────────╯
```

No repository change happens at Pull. Pull establishes the active refinement
field and the RS boundary.

## Step 4. Navigator and Driver select the next Change Request

The Driver may recommend the next CR based on dependency, risk, locality, or
learning value, but the Navigator chooses.

```text
Refinement
╭────────────────────────────────────────────────────────╮
│        🧾▶  CHANGE REQUEST SELECTED                   │
│                                                        │
│  CR-004                                                │
│  Clarify that Done does not imply push                 │
│                                                        │
│  reason to do now                                      │
│  The wording affects the meaning of every closure      │
│  checkpoint and should be clarified before deeper      │
│  lifecycle validation.                                 │
╰────────────────────────────────────────────────────────╯
```

## Step 5. Change Request cycle

Each CR moves through a small cycle.

### Confirm

The Driver confirms understanding, scope, risk, and done condition before
planning implementation.

```text
Refinement
╭────────────────────────────────────────────────────────╮
│        🧭  CHANGE REQUEST CONFIRMATION                │
│                                                        │
│  CR-004                                                │
│  Clarify that Done does not imply push                 │
│                                                        │
│  understanding                                         │
│  Done should mean lifecycle closure, not authorization │
│  to commit, push, tag, or release.                     │
│                                                        │
│  in scope                                              │
│  Done surface wording and related docs                 │
│                                                        │
│  out of scope                                          │
│  release and push policy implementation                │
│                                                        │
│  done condition                                        │
│  Navigator can read Done without inferring push        │
│  permission.                                           │
╰────────────────────────────────────────────────────────╯
```

The Driver stops for Navigator confirmation.

### Plan

The Driver proposes the local implementation route and validation evidence.

```text
Refinement
╭────────────────────────────────────────────────────────╮
│        📝  CHANGE REQUEST PLAN                        │
│                                                        │
│  CR-004                                                │
│                                                        │
│  route                                                 │
│  update Done surface copy                              │
│  update matching documentation                         │
│  add or adjust focused surface tests                   │
│                                                        │
│  validation                                            │
│  focused surface tests                                 │
│  Navigator reads rendered Done example                 │
╰────────────────────────────────────────────────────────╯
```

The Driver stops when the CR is non-trivial or user-visible. For tiny copy or
documentation CRs, a project may configure a lighter confirmation policy, but the
boundary should remain visible.

### Implement

The Driver changes files inside the confirmed CR boundary. New scope is not
absorbed silently. If the CR grows into a broader product or process change, the
Driver recommends parking, splitting, or promoting it.

### Validate

The Driver runs focused checks and prepares the Navigator route when the CR is
visible or process-visible.

```text
Refinement
╭────────────────────────────────────────────────────────╮
│        ✅  CHANGE REQUEST VALIDATION                  │
│                                                        │
│  CR-004                                                │
│                                                        │
│  automated                                             │
│  focused surface tests passed                          │
│                                                        │
│  Navigator route                                       │
│  inspect the Done surface example                      │
│                                                        │
│  expected observation                                  │
│  Done is clearly separate from commit, push, and       │
│  release authorization.                                │
╰────────────────────────────────────────────────────────╯
```

### Done note

The CR closes locally after validation.

```text
Refinement
╭────────────────────────────────────────────────────────╮
│        ✓  CHANGE REQUEST DONE                         │
│                                                        │
│  CR-004                                                │
│                                                        │
│  outcome                                               │
│  implemented                                           │
│                                                        │
│  evidence                                              │
│  focused tests passed                                  │
│  Navigator validation route prepared                   │
│                                                        │
│  note                                                  │
│  Done now closes lifecycle state without implying      │
│  commit, push, tag, or release.                        │
╰────────────────────────────────────────────────────────╯
```

The RS then returns to CR selection until no accepted CR remains. Before the RS
can close, every attached CR should have a terminal outcome such as done,
parked, rejected, or promoted.

## Step 6. Refinement Review

Review belongs to the RS level, not the CR level.

The Review looks across all CRs and records what the refinement revealed. It does
not implement refactorings directly. If Review finds necessary changes, they
become new CRs or future work.

```text
Refinement
╭────────────────────────────────────────────────────────╮
│        🔎  REFINEMENT REVIEW                          │
│                                                        │
│  Refinement Story                                      │
│  RS-001 Lifecycle surface refinement                   │
│                                                        │
│  CR outcomes                                           │
│  8 implemented                                         │
│  2 parked                                              │
│  1 promoted to Delivery                                │
│                                                        │
│  patterns revealed                                     │
│  closure surfaces need clearer boundary language       │
│  validation weight should scale with CR risk           │
│                                                        │
│  debt candidates                                       │
│  shared outcome renderer for lifecycle surfaces        │
│                                                        │
│  action                                                │
│  record debt candidate; no review-time refactor        │
╰────────────────────────────────────────────────────────╯
```

The rule is simple: Review feeds memory and debt records. CR cycles perform
mutations.

## Step 7. Refinement Coherence

Coherence checks Process, Project, Product, and Workbench alignment.

```text
Refinement
╭────────────────────────────────────────────────────────╮
│        ◉  REFINEMENT COHERENCE                        │
│                                                        │
│  Process                                               │
│  every implemented CR has validation evidence          │
│                                                        │
│  Project                                               │
│  Workbench status and docs match current state         │
│                                                        │
│  Product                                               │
│  Lifecycle surfaces read more clearly without changing │
│  release or push policy promises                       │
│                                                        │
│  Debt                                                  │
│  renderer consolidation recorded for future work       │
│                                                        │
│  result                                                │
│  coherent                                              │
╰────────────────────────────────────────────────────────╯
```

If coherence finds a critical gap, the RS does not mutate directly. It creates or
reopens a CR and returns to the CR cycle.

## Step 8. Refinement Story Close

The RS closes when its CRs have terminal outcomes, review is complete, coherence
passes, and follow-up is preserved. A Refinement Story should not close while any
attached Change Request remains unfinished.

```text
Refinement
╭────────────────────────────────────────────────────────╮
│        🧰✓  REFINEMENT STORY CLOSED                   │
│                                                        │
│  RS-001                                                │
│  Lifecycle surface refinement                          │
│                                                        │
│  result                                                │
│  Lifecycle surfaces are clearer and more               │
│  proportional during Ariad adoption dogfooding.        │
│                                                        │
│  CR outcomes                                           │
│  8 implemented                                         │
│  2 parked                                              │
│  1 promoted to Delivery                                │
│                                                        │
│  follow-up                                             │
│  release and push policy remains next Delivery Work    │
╰────────────────────────────────────────────────────────╯
```

Refinement closure may suggest a release boundary when user-facing behavior,
public documentation, runtime operation, or packaging changed. Release management
still remains a separate decision.

A runtime should preserve enough outcome evidence for the Navigator to
understand what changed, how it was validated, what was parked or promoted, and
why the RS closed. More complete implementations may preserve phase-level event
history.

## Working principle

Every mutation enters through a Change Request. Every refinement arc closes
through a Refinement Story.
