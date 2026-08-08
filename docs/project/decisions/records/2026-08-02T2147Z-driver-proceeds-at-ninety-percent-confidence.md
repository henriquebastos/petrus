---
status: Decided
raised: 2026-08-02
decided: 2026-08-02
deciders:
  - Navigator
related:
  - docs/process/development-guide.md
---

# Driver proceeds at ninety-percent confidence

## Question

When should the Driver continue autonomously instead of asking the Navigator
for another implementation or coordination choice?

## Decision

Proceed without asking when the Driver is at least 90% confident that the
choice preserves the accepted intent, scope, and project contracts. This now
includes Ariad checkpoints: render each checkpoint and record its evidence, but
automatically release the next lifecycle phase rather than waiting when
confidence is at least 90%.

Ask only when confidence is below the threshold, an explicit stop condition
applies, material product judgment remains genuinely ambiguous, or the action
is destructive, shared, or otherwise requires approval under the project's
high-impact-action rules. The Driver must not attribute acceptance or a ruling
to the Navigator when the Navigator did not provide it; auto-release records a
Driver recommendation and delegated continuation. The Navigator retains veto
and may redirect any phase.

## Rationale

The Navigator wants delivery to keep moving when intent and evidence already
make the next choice clear. A stated threshold makes that delegation durable
without silently transferring product judgment or approval of risky actions to
the Driver.

## Consequences

- Record meaningful assumptions and validate them instead of asking by default.
- Render Plan, Experience, Review, and History checkpoint surfaces durably, but
  continue automatically at or above 90% confidence.
- Escalate a focused choice only below 90% confidence or at a governing stop.
- Never use confidence to bypass destructive/shared-action approval or invent a
  Navigator ruling for a material product trade-off.
- Apply the same rule to coordinated current-Petrus repositories unless their
  local contract explicitly requires a stricter stop.
