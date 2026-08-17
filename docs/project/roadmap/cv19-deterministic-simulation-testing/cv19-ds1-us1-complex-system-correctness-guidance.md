---
code: CV19.DS1.US1
level: User Story
status: Planned
status_reason: Future Drivers do not yet have a concise conditional route to the accepted correctness sketch and DST workflow
updated: 2026-08-17
related:
  - index.md
  - cv19-ds1-correctness-and-simulation-contract.md
  - cv19-ds1-ts1-runtime-correctness-inventory.md
  - cv19-ds1-ts2-strict-scenario-replay-contract.md
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

## Out of Scope

- Global user instructions.
- A second Ariad lifecycle, mandatory correctness documents for ordinary work,
  or Tiger Style copied into project guidance.
