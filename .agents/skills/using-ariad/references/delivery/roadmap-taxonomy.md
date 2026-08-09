# Delivery Roadmap Taxonomy

Ariad uses a delivery taxonomy to keep roadmap work meaningful without turning every task into roadmap structure.

```text
Value / CV -> Delivery Story -> User Story / Technical Story -> Task
```

Refinement and maintenance work sit beside the hierarchy. They are real work, but they should not be inflated into Value, Delivery Story, User Story, or Technical Story unless they change a meaningful product, project, or process capability.

## Value / CV

A **Value** or **Capability Value (CV)** is a major delivery boundary.

It names a capability, product stage, public promise, or project maturity level that matters beyond one local change. A Value / CV should be large enough to organize multiple delivery arcs and meaningful enough that closing it changes how the project describes itself.

A closed Value / CV may suggest a major release or public milestone.

Ariad uses **Capability Value** as the default meaning of CV. Other projects may adapt CV to Community Value, Customer Value, or Business Value when that vocabulary fits their domain, but the default method does not require that adaptation.

## Delivery Story

A **Delivery Story** is a coherent delivery arc inside a Value / CV.

It is the story of a meaningful delivery outcome, not the smallest implementable unit. A Delivery Story is never implemented directly in canonical Ariad. It must expand into User Stories and/or Technical Stories before Plan and implementation. It has a done condition: when it closes, the project should be able to say what capability, product behavior, operational state, documentation promise, or process maturity emerged.

Exploration candidates normally promote into Delivery as Delivery Stories, because exploration usually discovers an arc rather than one granular implementation unit.

A Delivery Story may suggest a release boundary when it closes, especially when it changes product behavior, public documentation, runtime reliability, operational capability, or project maturity enough to warrant release management.

## User Story

A **User Story** is an implementable delivery unit with observable behavior or capability.

A User Story should add behavior or capability that can be validated end to end by the Navigator. In user-facing work, the Navigator should be able to inspect the behavior through a concrete validation route. In process, documentation, tooling, or operational work, the validation route may inspect commands, dry-runs, generated output, docs, runtime state, diagnostics, operation evidence, or operational behavior. Automated tests support the story, but they do not replace Navigator-facing validation for a User Story.

Ariad recommends writing the User Story statement in the traditional agile form:

```text
As a [user persona],
I want to [action/feature],
So that [benefit/value].
```

Ariad also recommends writing the User Story's acceptance behavior in a lightweight BDD form when planning or expanding work:

```text
Given <relevant starting state>
When <the user, operator, command, or runtime action happens>
Then <observable behavior or capability is visible>
And <important constraint or protection still holds>
```

For non-UI work, the `Then` may be an operation report, dry-run output, diagnostic result, generated artifact, documented policy, runtime state, or other inspectable evidence.

A User Story should not be reduced to an internal implementation slice. If no observable behavior or capability can be named, either expose one through a validation route or treat the work as a Technical Story inside the Delivery Story.

## Technical Story

A **Technical Story** is an implementable delivery unit whose immediate behavior is internal rather than directly visible to the Navigator.

Ariad recommends writing the Technical Story statement as:

```text
In order to [achieve a technical benefit/business capability],
As [an engineering team/system component],
I want to [perform a technical action],
So that [expected technical outcome].
```

Technical Stories are valid when they create necessary internal capability, safety, migration, infrastructure, instrumentation, test support, or operational substrate for a Delivery Story. Their primary validation belongs to the Driver through automated or internal evidence: tests, type checks, diagnostics, fixtures, preflights, internal reports, or contract checks. They may not justify a Navigator behavior checkpoint by themselves, but inside a Delivery Story they should lead toward a later User Story or behavior-visible checkpoint.

The Navigator should not normally be asked to manually validate private technical substrate. Exceptions include high-risk operations, real data mutation, insufficient automated evidence, or explicit Navigator request.

## Task

A **Task** is concrete work inside a User Story or Technical Story.

Tasks help the Driver execute. They are not normally roadmap items. A task may edit a file, add a test, rename a function, update a command, or adjust a document section. Tasks should not be used to create a false sense of roadmap progress.

## Maintenance and Refinement

**Maintenance** is legitimate work that may not belong in the roadmap hierarchy.

Examples:

- dependency updates;
- local cleanup;
- one-off operational repair;
- release note fix;
- CI retry or environment adjustment.

**Refinement** is legitimate work that cares for existing capability outside the roadmap hierarchy. It is organized through the Workbench, Change Requests, and Refinement Stories rather than through Delivery Stories.

Examples:

- small bug fixes in existing behavior;
- copy or surface polish;
- documentation correction;
- test gap closure;
- contained refactoring;
- lifecycle or process surface clarification.

Do not inflate maintenance or refinement into a Value, Delivery Story, User Story, or Technical Story just to make it visible. Record maintenance in the worklog when meaningful. Record refinement in the Workbench when it has a requested-change shape.

Maintenance or refinement can still create a release boundary, especially:

- a patch release, when it changes observable behavior, public documentation, packaging, runtime reliability, or user-facing operation.

## Roadmap states

Ariad recommends a small canonical state vocabulary for roadmap items:

```text
Planned      known, not currently being worked
Active       currently pulled into Delivery Work
Blocked      cannot progress until a named dependency, decision, or condition changes
Validated    implementation passed automated evidence and Navigator validation, but story closure/history may still be pending
Done         closed, coherent, documented, and recorded in project history
Deferred     intentionally postponed while remaining valid
Dropped      intentionally abandoned or no longer valid
```

Use a short reason with `Blocked`, `Deferred`, and `Dropped`:

```text
Active; blocked by TS1 policy refinement
Deferred; waiting for release channel decision
Dropped; replaced by DS4 runtime update path
```

`Attention` is not a canonical roadmap state. It may be useful in a runtime UI, checkpoint risk posture, or visual warning, but the roadmap should name the actual lifecycle condition: usually `Blocked`, `Deferred`, `Needs expansion`, or a specific dependency.

Projects may adapt labels for local systems, but new Ariad roadmap docs should keep the method-level meaning visible.

State should live in the roadmap item's own metadata or status section, not in a central index table and not primarily in the directory path. A project may render views of planned, active, blocked, or done work, but those views should be derived from item state or maintained deliberately as coordination artifacts.

Directory moves are not the default state transition mechanism. They make paths unstable, can break links, and hide why the lifecycle changed. Moving files or folders is acceptable for coarse archival or deliberate reorganization, but the item's explicit state should remain readable inside the item itself.

## Codes and folder names

Ariad recommends stable, readable codes for roadmap levels:

```text
CV<N>      Value / Capability Value
DS<N>      Delivery Story inside a Value / CV
US<N>      User Story inside a Delivery Story
TS<N>      Technical Story inside a Delivery Story
Task       local checklist item inside a User Story or Technical Story
```

Project folders should mirror the delivery hierarchy when the project keeps roadmap work as files.
Use lowercase slugs and keep the parent code in child folder names so links remain understandable when copied out of context. Index files should explain structure and conventions; they should not become complete mutable lists unless a project explicitly accepts that coordination cost.

Recommended pattern:

```text
docs/project/roadmap/
  cv<N>-<value-slug>/
    index.md
    cv<N>-ds<M>-<delivery-story-slug>/
      index.md
      exploration-summary.md        # when promoted from Exploration
      cv<N>-ds<M>-us<K>-<user-story-slug>/
        index.md
        plan.md
        test-guide.md
      cv<N>-ds<M>-ts<K>-<technical-story-slug>/
        index.md
        plan.md
        test-guide.md
```

Example:

```text
docs/project/roadmap/
  cv9-mirror-1-0/
    cv9-ds7-conversation-metadata-lifecycle/
      index.md
      exploration-summary.md
      cv9-ds7-us1-dry-run-metadata-lifecycle-decision-path/
        index.md
        plan.md
        test-guide.md
```

Numbering is project-local. New Ariad delivery work should use `DS`, `US`, and `TS` when adopting this taxonomy.

Do not create a folder before the work has crossed the right methodological boundary. Exploration documentation may suggest placement, but the Delivery entry step should confirm whether the candidate is a Delivery Story, User Story, or Technical Story before creating roadmap paths.

## Expand and collapse in the roadmap

The roadmap expands and collapses.

Expansion:

```text
Value / CV expands into Delivery Stories.
Delivery Story expands into User Stories and Technical Stories.
User Story / Technical Story expands into Tasks.
```

Collapse:

```text
completed Tasks close a User Story or Technical Story
completed User Stories and Technical Stories close a Delivery Story
completed Delivery Stories close a Value / CV
```

Every collapse should name the emergent value of the whole. A Delivery Story is not done merely because its child stories are checked off. It is done when those stories produce a coherent capability or outcome. A Value is not done merely because its Delivery Stories are closed. It is done when the project reaches the value boundary the CV named.

See [Expand and Collapse](../method/expand-collapse.md) for the general method pattern.

## When to expand

The Driver should expand when:

- the proposed User Story needs multiple behavior checkpoints;
- technical prerequisites hide the user-facing behavior;
- validation would be too broad or vague;
- several independent risks are being bundled together;
- the Navigator cannot reasonably accept the whole in one validation moment.

In those cases, the Driver should propose a Delivery Story or Value expansion rather than hide complexity inside one story.

## When to collapse

The Driver should collapse when:

- a User Story or Technical Story has been implemented, validated, documented, reviewed, and checked for coherence;
- the last child story in a Delivery Story has been validated;
- a Value / CV's Delivery Stories have produced the intended value boundary;
- roadmap, docs, tests, decisions, and worklog now describe the same state;
- release management needs to name what changed publicly.

Collapse should produce recognition: User Story done, Technical Story done, Delivery Story done, Value done, release candidate, or next coherent horizon.
