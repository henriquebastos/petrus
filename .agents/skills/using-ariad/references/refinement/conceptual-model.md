# Refinement Conceptual Model

This document names the core concepts of Ariad Refinement.

It does not define roadmap delivery. Delivery concepts live in
[Delivery Conceptual Model](../delivery/conceptual-model.md). Refinement lives
beside Delivery as a separate work area because it cares for existing capability
without inflating that care into roadmap structure.

## Core idea

Refinement treats progress as improved habitability of something that already
exists.

A refinement arc does not start from a new product promise. It starts from a
capability, flow, surface, document, test boundary, or operational behavior that
is already present and now needs adjustment. The change may be small or broad,
but its intention is care: clarify, harden, smooth, repair, reduce friction, or
make the existing system easier to inhabit.

Refinement is centered on the **Refinement Story** as the unit of flow. A
Refinement Story is composed of one or more **Change Requests**.

## Concepts

### Workbench

The Workbench is the project surface for Refinement Work.

It holds Change Requests and Refinement Stories outside the roadmap. The
Workbench is not a backlog of product promises. It is a curated place for
requested changes to existing capability.

A runtime may render the Workbench beside the roadmap during activation so the
Navigator can choose whether to enter Delivery Work or Refinement Work.

### Change Request

A Change Request, or CR, is a requested change to something that already exists.

A CR should name the requested adjustment, the context where it appeared, the
area affected, the reason it matters, and its current outcome. It is smaller
than a Refinement Story. It says what should change, not the whole story of the
refinement.

Typical CR semantic states include:

- `candidate` or `captured` — recorded, not yet accepted into an active cycle;
- `accepted`, `selected`, or `active` — chosen for the active Refinement Story cycle;
- `planned` — the local route and validation expectation have been recorded;
- `implemented` — the change has been made or implementation evidence has been recorded;
- `validated` — validation evidence has been recorded;
- `done` — the CR has a local done note and is complete inside the RS;
- `parked` — valid but not part of the current refinement;
- `rejected` — intentionally not pursued;
- `promoted` — moved to Delivery because it became roadmap-level work.

Ariad does not require these exact status names. It requires the semantic state
of the CR to be visible enough for the Navigator to understand where the CR is,
what has been decided, and whether it can block RS closure.

### Refinement Story

A Refinement Story, or RS, is the unit of Refinement Work.

It tells the story of a refinement arc: which existing field is being cared for,
which CRs belong to the arc, what boundary protects the work from expanding, how
each CR moved, what was validated, what debt or follow-up was recorded, and why
the arc can close.

A Refinement Story may contain one CR. This is the quick refinement path. It may
also contain many CRs collected during real use or curated from the Workbench.
The structure stays the same; only the size changes.

A Refinement Story is not a Delivery Story and does not live in the roadmap. If
the work becomes a new capability, public contract, broad architecture change, or
release-defining promise, it should be promoted to Delivery.

### Refinement Work

Refinement Work is the flow that moves a Refinement Story.

The RS level owns pull, CR selection, review, coherence, and close. The CR level
owns confirm, plan, implement, validate, and done note.

```text
Refinement Story flow
  pull
  select next Change Request
  Change Request cycle
  select next Change Request
  Change Request cycle
  review
  coherence
  close

Change Request cycle
  confirm
  plan
  implement
  validate
  done note
```

### Work-field orientation

A runtime may offer an activation surface that renders current work fields before
work begins.

For Ariad, the important method rule is not the visual name of the surface. The
rule is that the Navigator should be able to see the available fields and choose
the field before the work starts.

```text
Roadmap   -> Delivery Stories   -> Delivery Work
Workbench -> Refinement Stories -> Refinement Work
Exploration material -> Exploratory Stories -> Exploration
```

The source field determines the default flow. A roadmap item enters Delivery. A
Workbench item enters Refinement. Exploration material remains exploratory until
it is promoted.

## Events

Refinement can be understood through events:

```text
workbench_snapshot_rendered
  the Driver renders open Refinement Stories, pending Change Requests, and active refinement state

change_request_captured
  the Driver records a requested change in the Workbench or inside a draft Refinement Story

refinement_story_created
  a Refinement Story is created from one or more Change Requests or a direct Navigator request

refinement_story_pulled
  the Navigator intentionally selects a Refinement Story for active Refinement Work

change_request_selected
  the Navigator and Driver choose the next CR to traverse inside the active RS

change_request_confirmed
  the Driver confirms understanding, scope, risk, and done condition with the Navigator

change_request_planned
  the Driver proposes the local route, likely files, validation evidence, and manual check if needed

change_request_implemented
  the Driver changes the repository inside the confirmed CR boundary

change_request_validated
  automated evidence and Navigator validation route are prepared or completed

change_request_done
  the CR receives an outcome and done note

refinement_review_completed
  the Driver reviews the set of CRs, names patterns, and records debt candidates or follow-up without mutating files directly

refinement_coherence_checked
  process, project, product, Workbench, roadmap links, docs, tests, and debt records are checked for agreement

refinement_story_closed
  the Refinement Story is closed with terminal CR outcomes, validation evidence, debt entries, and follow-up preserved
```

## Refinement surfaces

Common Refinement surfaces include:

```text
Workbench Snapshot
  What refinement work is available to pull?

Change Request Captured
  What requested change was recorded, where, and why?

Refinement Story Overview
  What existing field is being refined, and which CRs belong to the story?

Refinement Story Pull
  What RS has entered active Refinement Work?

Change Request Confirmation
  What exactly will change, and what stays out?

Change Request Plan
  How will this CR be implemented and validated?

Change Request Validation
  What evidence proves the CR has been handled?

Change Request Done Note
  What changed, what was validated, and what outcome did the CR receive?

Refinement Review
  What did the full set of CRs reveal, and what debt or future work should be recorded?

Refinement Coherence
  Do Process, Project, Product, Workbench, roadmap, and documentation agree?

Refinement Story Close
  Is the refinement arc complete enough to leave active work?
```

A runtime may render one surface per phase or a consolidated flow-event surface.
The method requirement is that the Navigator can see the event, current phase,
recorded detail, active state, next move, and mutation boundary.

## Working principle

The CR says what should change. The RS tells the story of the refinement.

Ariad defines semantic obligations, not a particular storage model or visual
implementation. The Navigator should see the work field before entering work;
CRs should move through visible phases; mutations should happen only inside CR
cycles; RS review and coherence should not mutate directly; RS close should
require terminal CR outcomes; and closure should preserve enough evidence and
follow-up to understand the arc.
