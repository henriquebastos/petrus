# User and Technical Story Lifecycle

User Stories and Technical Stories are the normal implementable units in Delivery Work.

A **User Story** creates observable behavior or capability that the Navigator can validate through a concrete route. A **Technical Story** creates internal capability needed by the Delivery Story; it is primarily validated by the Driver through automated or internal evidence and may not have a Navigator-visible behavior checkpoint by itself.

A **Delivery Story** is the larger delivery arc that these stories close into.

## Lifecycle contracts

Each lifecycle phase has a contract: the minimum rules, outputs, and stop conditions that keep Driver movement inspectable. Contracts are method rules, not visual decorations. A runtime may render them in checkpoint surfaces, enforce them through cursor state, or use them during coherence checks.

Contract distribution:

- **Pull:** choose an explicit focus, classify the work level, and preserve Navigator choice as the commitment boundary.
- **Prepare:** read the terrain, identify story shape, risks, local guide overrides, and whether expand/collapse is needed.
- **Expand:** when a Delivery Story is pulled, expand it into implementable User Stories and/or Technical Stories before Plan. Delivery Stories are never the implementable unit.
- **Plan:** define scope, non-goals, acceptance behavior, validation route, documentation impact, implementation rules, and whether E2E validation is required for an implementable User Story or Technical Story.
- **Implement:** follow the approved Plan, use TDD or characterization tests for behavior changes when practical, keep changes scoped to the active story, and add or update E2E tests when the Plan requires them.
- **Validate:** run required checks, including E2E tests when defined by the Plan or local guide, and present evidence plus a Navigator validation route when applicable.
- **Review:** name debt paid, introduced, and carried forward, including revisit criteria and ledger decisions.
- **Coherence:** verify Process, Project, and Product alignment, including differences between Ariad defaults and the local development guide.
- **Done:** close only after validation, review, and coherence; record history at coherent story boundaries unless local policy overrides; recommend next pull, parent collapse, or release boundary when relevant.

## Read and orient

The Driver begins by reading the relevant code and project documentation. It identifies what kind of work this is, what context matters, what is in scope, what is out of scope, which risks or trade-offs should be visible before implementation, and whether the pulled work is truly one User Story or Technical Story or should be expanded as a Delivery Story.

The plan must name the observable behavior or capability that will close a User Story. Ariad recommends expressing that behavior in a lightweight BDD form: `Given` the relevant starting state, `When` the user, operator, command, or runtime action happens, `Then` the observable behavior or capability appears, and `And` important constraints still hold. For non-UI work, the observable route may be a dry-run, diagnostic, operation report, generated artifact, documented policy, or runtime state. If the Driver can only name private implementation steps, the work should be reframed as a Technical Story or expanded into a Delivery Story arc before implementation.

## Plan checkpoint

For non-trivial Delivery Work, the Driver presents the plan as a Navigator-facing checkpoint surface and stops. If the project stores `plan.md`, creating or updating that file does not replace the visible checkpoint: the Navigator still needs to see the plan, acceptance behavior, validation route, risks, and decision prompt in the conversation or runtime surface. The Navigator confirms, redirects, or narrows the route. This checkpoint is important because an agent can turn vague intention into concrete changes very quickly. The plan is where speed becomes direction.

## Implement

The Driver changes the repository to implement the User Story or Technical Story. A User Story should add behavior or capability that can be verified and observed through its validation route. Behavior changes should be test-driven when practical. Refactoring can happen inside the story when it supports the story's coherence, but new scope should not be silently absorbed.

Delivery Stories are not implemented directly. When a Delivery Story is pulled, the Driver prepares it, expands it into User Stories and Technical Stories, recommends the next implementable child story, and stops for Navigator confirmation before Plan.

If implementation is too large to reach one coherent behavior validation point, the Driver should not hide that size inside the story. The work should become or remain a Delivery Story and be expanded into smaller User Stories and Technical Stories.

## Validate

The Driver runs the relevant automated checks and prepares the right validation route for the story type.

For User Stories, the validation route should trace back to the BDD acceptance behavior where one exists: the `Given` state can be prepared, the `When` action can be performed, and the `Then` observation can be inspected. The Validation Checkpoint should show both automated evidence and a concrete Navigator route: commands, URLs, files, operation surfaces, sample data, expected observations, pass condition, and fail condition. Automated tests may encode the same behavior, but for user-visible or product-visible work, automated tests alone are not enough. The Navigator needs a way to see the change.

For Technical Stories, the Driver should validate primarily through automated or internal evidence: tests, type checks, diagnostics, fixtures, preflights, internal reports, or contract checks. The Navigator should not normally need to run scripts to inspect private substrate. The Driver may present the evidence and continue until the next Navigator-visible User Story checkpoint, unless risk, real data mutation, weak automated evidence, project policy, or Navigator preference requires a stop.

## Document

The Driver updates project memory to match reality: roadmap status, decisions, architecture, process docs, user docs, release notes, worklog, or product specs as appropriate.

Documentation is not optional bookkeeping. It is how the project remembers what the change means.

## Review

The Driver reviews the implemented change for quality, scope drift, risk, debt, and coherence with the original plan. Review is the point where the Driver looks back before asking the Navigator to accept forward motion.

The Review checkpoint must include a refactoring and technical-debt assessment, even when the decision is "no refactor now." The Driver should name:

- refactoring done;
- refactoring considered but not done;
- existing debt paid down;
- new debt introduced;
- debt intentionally carried forward, with revisit criteria;
- whether any debt blocks story closure or should become follow-up work.

A story should not close with invisible debt. If the debt is acceptable, it should be named as accepted or carried forward; if it blocks coherence, the story returns to implementation or expands into follow-up work.

## Coherence

The Driver checks whether Process, Project, and Product agree.

A technically correct change can still be incoherent if the roadmap says something else, the documentation promises a different behavior, or the process being followed contradicts the project's operating rules.

## History

When the story is coherent, the Driver proposes or records history according to the project's policy: commit, worklog, decision record, release note, or another durable record.

A User Story or Technical Story is not closed because files changed. It closes because the change became intelligible, validated, documented, coherent, and recorded.

## Collapse into Delivery Story

When all child User Stories and Technical Stories have closed, the Delivery Story can collapse.

Delivery Story closure asks what the whole arc produced, whether the Navigator accepts the outcome, what follow-up remains, and whether the closure suggests release management.
