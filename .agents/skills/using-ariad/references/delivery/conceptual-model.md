# Delivery Conceptual Model

This document names the core concepts of Ariad Delivery.

It does not explain the practical flow. The step-by-step sequence, examples, checkpoints, validation, and visual feedback live in [Delivery Flow](flow.md).

## Core idea

Delivery treats progress as movement toward verified change. A delivery arc is not merely advanced through tasks. It becomes trustworthy as intent, implementation, validation, documentation, review, coherence, and history converge.

Delivery begins when work has enough form to become a bounded roadmap commitment. That commitment may come from a roadmap item, direct request, known bug, operational need, or candidate promoted from Exploration.

A direct request or known bug does not automatically belong to Delivery. If it cares for existing capability without becoming a roadmap-level promise, it belongs in [Refinement](../refinement/index.md). Delivery begins when the Navigator chooses roadmap commitment.

Delivery is centered on the **Delivery Story** as an arc of delivery. The implementable units inside that arc are **User Stories** and **Technical Stories**.

## Concepts

### Value / CV

A Value or Capability Value is a major delivery boundary.

A Value / CV names a capability, product stage, public promise, or project maturity level that matters beyond one local change. A closed Value / CV may suggest a major release or public milestone.

### Delivery Story

A Delivery Story is a coherent delivery arc inside a Value / CV.

It names the meaningful outcome that is being delivered. It may contain multiple User Stories and Technical Stories. It closes when those child stories produce the intended behavior arc, capability arc, operational state, documentation promise, or process maturity and the Navigator can accept the whole as complete.

Exploration candidates normally promote into Delivery as Delivery Stories, because exploration tends to discover an arc rather than one granular implementation unit.

A Delivery Story is not a dumping ground for unrelated work. It should have a recognizable done condition and a coherent release or history boundary.

### User Story

A User Story is a bounded implementable unit with observable behavior or capability.

A User Story may come from a Delivery Story expansion, direct Navigator request, roadmap item, known bug, or explicit project need.

A User Story should add behavior or capability that can be verified by the Navigator. In user-facing work, that behavior should be visible to the Navigator through a concrete validation route. In technical, tooling, documentation, or operational work, the behavior may be a command output, dry-run report, generated document, diagnostic result, runtime state, or operation evidence. It should still be observable enough for the Navigator to understand what changed. Automated tests are supporting evidence, not a substitute for Navigator-facing validation.

A User Story should not close on private implementation alone. If the work has no observable behavior or capability yet, it should either become a Technical Story inside a Delivery Story that leads to a later visible behavior checkpoint, or the plan should expose an observable validation route such as a dry-run, diagnostic, generated artifact, or operation report.

### Technical Story

A Technical Story is an implementable delivery unit whose immediate behavior is internal rather than directly visible to the Navigator.

Technical Stories are valid when they create necessary internal capability, safety, migration, infrastructure, instrumentation, test support, or operational substrate for a Delivery Story. They still require verification, but their primary validation belongs to the Driver through automated or internal evidence: tests, type checks, diagnostics, fixtures, preflights, internal reports, or contract checks. They may not justify a Navigator behavior-validation checkpoint by themselves.

When a Delivery Story contains Technical Stories, the Driver may continue through subsequent stories until a Navigator-visible User Story checkpoint is reached, unless risk, project policy, or Navigator preference requires an earlier stop.

### Task

A task is concrete work inside a User Story or Technical Story.

Tasks are useful for execution, but they are not the normal roadmap unit. They should not be used to create a false sense of progress.

### Cadence

A Cadence is an event-triggered methodological rhythm at a Delivery boundary.

Cadences name the questions that become alive when work changes state. For example, closing a User Story triggers questions about history, parent progress, debt, next pull, and release possibility. Cadences are not mandatory full ceremonies; they are compressible prompts that help the Driver avoid silent skips.

See [Delivery Cadences](cadences.md).

### Behavior Checkpoint

A Behavior Checkpoint is the moment where the Navigator validates newly created behavior or capability.

For User Stories, the Behavior Checkpoint normally happens after implementation and validation route preparation. For Technical Stories inside a Delivery Story, the Driver records internal verification and continues until the next story that exposes behavior the Navigator can inspect.

### Operation Evidence

Operation evidence is structured proof produced by a controlled operation.

It may come from runtime health checks, backups, migrations, release doctors, smoke commands, web operation runs, approval flows, or other allowlisted project operations. Operation evidence should expose state and relevant details in a form the Navigator can inspect before falling back to raw machine payloads.

Operation evidence is especially important for Technical Stories, release candidates, and operational updates where the behavior is not a simple user-interface change.

### Validation Route

A validation route is the concrete path by which the project and Navigator can inspect the change.

It can include automated tests, commands, screenshots, local web checks, CLI outputs, logs, dry-runs, generated artifacts, operation evidence, or manual instructions.

### Delivery Handoff

A Delivery Handoff is the information carried from Exploration or a higher roadmap level into active Delivery.

When the source is Exploration, the handoff should include the source Exploratory Story, Exploration Documentation, Delivery Story seed, candidate User Stories and Technical Stories, validation seeds, Carry Forward Notes, and known kept-for-later signals.

### Technical Debt

Technical debt is structural cost consciously carried by the project.

Debt may live in code, tests, documentation, architecture, operations, release process, or method usage. Ariad does not treat all debt as failure. Some debt is a valid trade-off when it preserves delivery momentum. The method requires that debt be visible, named, and revisitable.

A Delivery Review should distinguish:

- **debt paid** — existing structural cost reduced by the story;
- **new debt introduced** — structural cost created by the story;
- **debt carried forward** — known debt accepted for now;
- **revisit trigger** — the condition that should bring the debt back into active work.

A project may keep a **Technical Debt Ledger** when debt cannot be held safely inside one story's review notes. Each debt item should live in its own record and name its source story, kind, severity, carrying reason, revisit trigger, and status.

Technical debt can become Delivery Work. Small local repayment may be Maintenance. Larger internal repayment may be a Technical Story. A broad structural arc may become a Delivery Story.

### Release Intent

Release Intent appears when a Delivery Story, Value / CV, maintenance fix, or operational change may deserve release management.

It may be known during planning or emerge when a User Story, Technical Story, Delivery Story, or Value collapses. The Driver should surface release intent when the work changes behavior, public documentation, runtime operation, packaging, or user-facing capability enough to warrant release management.

See [Release Management](release-management.md).

## Events

Delivery can be understood through events. Events are moments where the method recognizes that something changed in the delivery field.

```text
roadmap_snapshot_rendered
  the Driver renders current focus, backlog, promoted candidates, and constraints

pull_recommended
  the Driver recommends a next Delivery Story, User Story, Technical Story, Maintenance item, or Refinement Story without silently choosing it

work_pulled
  the Navigator intentionally selects a roadmap item or promoted candidate for active Delivery Work

delivery_story_identified
  the Driver recognizes a coherent delivery arc from the pulled item or promoted Exploration candidate

delivery_story_expanded
  the Driver proposes User Stories and Technical Stories that preserve validation boundaries

cadence_triggered
  a boundary such as validation, review, story closure, parent collapse, or release makes a recurring set of questions active

user_story_identified
  the Driver recognizes an implementable story with observable behavior or capability

technical_story_identified
  the Driver recognizes an implementable internal capability needed by the Delivery Story

plan_checkpoint_reached
  the Driver has enough context to propose a route before implementation

plan_confirmed
  the Navigator accepts, redirects, or narrows the delivery route

implementation_started
  the Driver begins focused repository changes inside the confirmed story boundary

technical_story_verified
  a Technical Story passes internal verification without requiring a Navigator behavior checkpoint

behavior_checkpoint_reached
  a User Story creates behavior visible enough for Navigator validation

debt_delta_recorded
  the Driver names debt paid, introduced, or carried forward during review

debt_registered
  a carried debt item is recorded in the project Technical Debt Ledger with revisit criteria

debt_payment_proposed
  the Driver recommends paying debt before continuing feature work

validation_route_prepared
  the Driver gives the Navigator a concrete route to inspect the change

operation_evidence_recorded
  a controlled operation produces structured evidence for validation, release, or operational review

documentation_updated
  project memory changes to match the implemented reality

review_completed
  the Driver inspects code, tests, docs, risks, and debt after implementation

coherence_checked
  process, project, and product are checked for agreement

user_story_closed
  the Navigator accepts the User Story and the work enters project history or another configured record

technical_story_closed
  the Technical Story is verified and recorded inside the Delivery Story

delivery_story_closed
  all child User Stories and Technical Stories in the Delivery Story have reached their validation and coherence criteria

release_intent_detected
  Delivery Story closure or another delivery boundary suggests that release management may begin
```

## Delivery surfaces

Common Delivery surfaces include:

```text
Roadmap Snapshot
  What delivery work is available to pull?

Pull Recommendation
  What should be pulled next, and why?

Plan Checkpoint
  Is the route right before implementation begins?

Delivery Story Expansion
  Should this delivery arc become multiple User Stories and Technical Stories?

Implementation Orientation
  What is being changed inside the active story boundary?

Validation Checkpoint
  What passed, what needs manual inspection, and what remains uncertain?

Operation Execution
  What controlled operation ran, what state did it reach, and what evidence did it produce?

Review Checkpoint
  What changed, what debt remains, and what documentation or refactoring is needed?

Coherence Checkpoint
  Do Process, Project, and Product still agree?

History Checkpoint
  Is the story coherent enough to enter project history?

Transition View
  What closed, where was it absorbed, what did it unlock, and what moves next?

Delivery Story Closure
  Is the delivery arc complete enough to suggest release management?

Release Intent
  Is there a release boundary now?
```

These surfaces support the method, but they do not define it. A User Story remains a User Story whether it appears as a checkpoint card, terminal panel, web task, commit proposal, or conversation summary. A Delivery Story remains a Delivery Story whether it appears as a roadmap group, milestone, release candidate, or expanded set of User Stories and Technical Stories.
