---
code: CV19.DS1.US1
level: User Story
status: Done
status_reason: Both project entry points now conditionally route correctness-sensitive work to one complete sketch and replay workflow without burdening ordinary work
updated: 2026-08-17
related:
  - index.md
  - cv19-ds1-correctness-and-simulation-contract.md
  - cv19-ds1-ts1-runtime-correctness-inventory.md
  - cv19-ds1-ts2-strict-scenario-replay-contract.md
  - ../../../../AGENTS.md
  - ../../../process/development-guide.md
  - ../../../process/deterministic-simulation-testing.md
---

# CV19.DS1.US1 — Complex-system correctness guidance

## Intent

Let a future Driver recognize correctness-sensitive work and retrieve exactly
one focused Petrus DST contract without loading a second lifecycle into every
session.

## Acceptance / Done Condition

**Given** work is durable, concurrent, stateful, or externally effectful,
**when** a future Driver reads the repository instructions and local
development guide, **then** the Driver is routed to one focused owner and
records authoritative state, safety invariants, liveness assumptions, bounds
and overflow behavior, nondeterministic inputs, consequential crash cuts, and
an independent checker/model or why one is impractical.

**And** ordinary work receives no additional mandatory artifact or lifecycle.

**And** production correctness never depends on removable Python `assert`
statements, while tests and Hypothesis invariants may use assertions.

## Scope

- Add one concise conditional route to repository instructions and the local
  development guide.
- Keep the complete correctness-sketch template, replay-before-fix flow, and
  scenario-promotion guidance in the focused DST owner.
- Verify progressive retrieval and internal link coherence.

## Driver QA and Evidence Plan

- Follow only the new concise route from `AGENTS.md` and confirm it reaches the
  complete contract and replay command.
- Run documentation/coherence checks and the repository-required full gate.

## Delivered Evidence

- `AGENTS.md` and the local development guide each add one concise conditional
  route for durable, concurrent, stateful, or externally effectful work. Both
  point to the same focused DST owner and explicitly avoid a second lifecycle
  or mandatory artifact for ordinary work.
- The focused owner now carries the seven-part correctness sketch,
  replay-before-fix flow, minimized-scenario promotion rules, and the explicit
  production/test distinction for Python `assert`.
- A progressive-retrieval probe followed both entry points through the focused
  owner to the strict scenario contract and concrete replay command. The
  repository-wide local Markdown link scan and `git diff --check` passed.
- The repository-required `scripts/check full` route passed lint, formatting,
  production type checking, ast-grep, and **2,198 tests**.

## Out of Scope

- Global user instructions.
- A second Ariad lifecycle, mandatory correctness documents for ordinary work,
  or Tiger Style copied into project guidance.
