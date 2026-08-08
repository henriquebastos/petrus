---
status: Decided
raised: 2026-07-06
decided: 2026-07-06
deciders:
  - henrique (Navigator)
supersedes:
related:
  - ES-001
---

# Track all work via Ariad from day zero

## Question

Should pre-code work — organization, exploration, spikes, experimentation, discussions — be tracked with the same rigor as delivery work, or is tracking only needed once implementation starts?

## Decision

Adopt Ariad at project inception, before any code exists. Everything produces tracked artifacts: Exploratory Stories for sensemaking, experiment files for spikes, decision records for choices, worklog entries for milestones. All of it is committed to this repository.

## Rationale

The Navigator's prior year of Petri net + AI work is scattered across multiple repositories, folders, and conversations — and that scattering is exactly the failure mode this project wants to avoid repeating. A single durable history of the project's own development also mirrors the product's core idea (a single durable event history), so the method and the product reinforce each other.

## Options Considered

- Start tracking when code starts — rejected: the design-shaping decisions happen now, during exploration.
- Track in external tools (notes apps, issue trackers) — rejected: recreates the scattering problem.

## Consequences

- The first commits are method artifacts and references, not code.
- Spikes and experiments must land under the relevant Exploratory Story before being considered done.

## Review Trigger

If artifact ceremony measurably slows exploration, revisit the granularity (not the principle).
