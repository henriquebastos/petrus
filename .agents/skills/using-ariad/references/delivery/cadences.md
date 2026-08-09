# Delivery Cadences

Cadences are event-triggered methodological rhythms at Delivery boundaries.

They are not calendar rituals and they are not bureaucracy. A cadence names the
questions that become alive when work crosses a boundary, and the surfaces that
may help the Navigator decide what happens next.

```text
Cadence = trigger + questions + surfaces + default action + compression rule
```

A cadence helps the Driver avoid silent skips: forgetting a commit question,
missing a debt snapshot, skipping release intent, or pulling the next story
before the parent state is understood.

## Principles

- **Boundary-triggered:** cadences fire when method state changes, not because a
  clock says so.
- **Question-first:** the important part is the question, not the visual card.
- **Compressible:** small, low-risk work may combine surfaces.
- **Risk-sensitive:** debt, release, data mutation, or unclear validation should
  expand the cadence rather than compress it.
- **Navigator-facing:** cadence questions preserve human judgment at transition
  points.

## Story Closure Cadence

Trigger:

```text
A User Story or Technical Story is validated, reviewed, coherent, and ready to close.
```

Questions:

- Is the story truly done or only validated?
- Should project history be recorded now?
- Did the parent Delivery Story progress change?
- Was debt paid, introduced, or carried forward?
- Is a Debt Snapshot needed before the next pull?
- What is the next coherent movement?

Common surfaces:

- Transition View;
- History Checkpoint;
- Debt Delta or Debt Snapshot when debt is present;
- compact Roadmap Snapshot.

Default action:

Close the child story, update parent progress, surface history/debt questions,
and recommend the next coherent movement.

Compression rule:

For trivial work with no debt, no release implication, and no parent ambiguity,
combine Transition View and History Checkpoint. Do not compress away the history
question when the project expects commits.

### Coupled Story Closure

A Story Closure Cadence may close more than one child story only when the closure
is genuinely coupled.

Allowed when:

- one child story was pulled to unblock another;
- the stories are causally linked;
- validation and review are shared or immediately sequential;
- closing separately would add ceremony without improving judgment;
- the closure surface names each story, closure reason, validation evidence, and
  debt impact separately.

Avoid coupled closure when:

- each story has independent behavior, risk, or debt;
- either story is large enough to need separate review;
- project history policy expects one commit per story;
- batching would hide unfinished validation or technical debt;
- the parent roadmap needs separate traceability.

A coupled closure is a compression, not a merge. The stories remain distinct in
the roadmap.

Common surface:

- Coupled Story Closure or Transition View with explicit child-story rows.

## Delivery Story Expansion Cadence

Trigger:

```text
A Delivery Story is identified but is too large for one implementable story.
```

Questions:

- What User Stories and Technical Stories preserve validation boundaries?
- Which child story should be pulled first?
- Does the Navigator accept the expansion?
- Should child folders be created now?

Common surfaces:

- Delivery Story Expansion;
- Proposed Roadmap Shape;
- Pull Recommendation.

Default action:

Render the proposed child structure and ask for Navigator acceptance before
creating child plans.

Compression rule:

If the expansion is obvious and low-risk, show a compact expansion table, but
still ask for acceptance before implementation.

## Validation Cadence

Trigger:

```text
Implementation has reached a validation point.
```

Questions:

- What automated evidence passed or failed?
- What concrete route can the Navigator run, open, inspect, or compare?
- What is the expected observation?
- What are the pass and fail conditions?
- Does failed validation return to planning or implementation?

Common surfaces:

- Validation Checkpoint;
- Operation Evidence for controlled operations;
- Navigator Validation Route.

Default action:

Show automated evidence and Navigator validation route, then stop for acceptance
when behavior or capability is Navigator-visible.

Compression rule:

Never compress away the Navigator route for User Stories. For Technical Stories,
internal verification may be compact if a later User Story will expose behavior.

## Review and Debt Cadence

Trigger:

```text
Validation has been accepted and the Driver reviews the changed surface.
```

Questions:

- What refactoring was done?
- What refactoring was considered and deferred?
- What debt was paid?
- What debt was introduced?
- What debt is carried forward, and with what revisit trigger?
- Does debt block closure or become follow-up / debt item in the Technical Debt Ledger?

Common surfaces:

- Review Checkpoint;
- Technical Debt Delta;
- Debt Register Entry;
- Debt Payment Proposal.

Default action:

Name debt movement explicitly. If debt should outlive the story's review notes,
record it as a debt item in the project's Technical Debt Ledger or capture a follow-up with revisit criteria.

Compression rule:

Even for small stories, say `new debt introduced: none` or name the carried debt.
Do not let debt remain invisible.

## Parent Collapse Cadence

Trigger:

```text
All child User Stories and Technical Stories inside a Delivery Story are done.
```

Questions:

- Did the Delivery Story produce the intended arc?
- What emergent capability or outcome can the project now name?
- Does the parent Delivery Story close?
- Is release intent present?
- What debt, follow-up, or maintenance remains?

Common surfaces:

- Delivery Story Closure;
- Transition View;
- Release Intent;
- Debt Snapshot;
- Roadmap Snapshot.

Default action:

Collapse child stories into the parent Delivery Story and ask whether the parent
is accepted as complete.

Compression rule:

If parent closure is obvious and non-release-bearing, combine Delivery Story
Closure with a compact Transition View.

## Release Cadence

Trigger:

```text
A closed User Story, Technical Story, Delivery Story, Value/CV, maintenance fix,
or operational change may deserve a release boundary.
```

Questions:

- Is this a release boundary?
- What version/channel/package/deployment decision is needed?
- Is there a release note?
- What smoke validation or operation evidence is required?
- Is rollback or recovery clear?

Common surfaces:

- Release Intent;
- Release Candidate;
- Operation Evidence;
- History Checkpoint.

Default action:

Name release intent and ask whether to enter release management, defer, or record
that no release is needed.

Compression rule:

For internal-only changes with no release boundary, explicitly say no release is
needed rather than silently skipping the question.

## Exploration Promotion Cadence

Trigger:

```text
An Exploration candidate is accepted into Delivery.
```

Questions:

- Does the candidate become a Delivery Story, User Story, or Technical Story?
- What documentation travels with it?
- Where does the full Exploration document live?
- Where does the roadmap summary live?
- What validation seeds and carry-forward notes matter?

Common surfaces:

- Candidate Promoted;
- Delivery Handoff;
- Narrative Field Snapshot;
- Roadmap Snapshot;
- Delivery Story Identified.

Default action:

Preserve full Exploration documentation, create or link the Delivery handoff,
and confirm roadmap placement before planning implementation.

Compression rule:

Direct promotion to one User Story may be compact, but only when the candidate is
already behavior-sized.

## Technical Debt Cadence

Trigger:

```text
Debt is paid, introduced, carried forward, grows, or begins to affect the next pull.
```

Questions:

- Is the debt still acceptable?
- Does it need a debt item in the Technical Debt Ledger?
- Does it block the next story?
- Should the next pull be debt payment rather than feature work?
- What revisit trigger prevents silent accumulation?

Common surfaces:

- Debt Delta;
- Debt Snapshot;
- Debt Payment Proposal;
- Review Checkpoint.

Default action:

Make the debt visible and decide whether to carry, pay, defer with trigger, or
drop it.

Compression rule:

Do not require a debt item for every small imperfection. Use the Technical Debt Ledger when
debt should survive beyond the current story review.

## Cadence selection

The Driver does not need to render every possible surface every time. It should
select the smallest surface set that preserves the live questions.

A useful heuristic:

```text
If the boundary changes project history, include History.
If the boundary changes roadmap structure, include Roadmap / Transition.
If the boundary carries debt, include Debt Delta or Debt Snapshot.
If the boundary may ship, include Release Intent.
If the boundary affects user-visible behavior, include Navigator Validation Route.
```

Cadence is how Ariad keeps transitions from becoming invisible.
