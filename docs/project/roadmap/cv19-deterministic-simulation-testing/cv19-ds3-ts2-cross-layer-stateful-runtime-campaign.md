---
code: CV19.DS3.TS2
level: Technical Story
status: Active
status_reason: TS1's one-interpreter generated/replay architecture is Done; TS2 now owns the one-run delivery, time, Activity, retry, lifecycle, crash, and paired-fault campaign
updated: 2026-08-19
related:
  - index.md
  - cv19-ds3-stateful-generation-and-independent-checkers.md
  - cv19-ds3-ts1-generated-delivery-schedules.md
---

# CV19.DS3.TS2 — Cross-layer stateful runtime campaign

## Intent

Exercise DS3's complete generated runtime vocabulary in one bounded run while
keeping production Petrus responsible for semantic consequences.

## Scope

- Compose one production-Engine scenario profile that admits generated source
  delivery, logical-time movement, Activity completion/failure, retry,
  lifecycle change, abrupt crash/load, and at least two qualified fault classes.
- Keep broad and focused command generation outside the profile and submit all
  operations through the supported World interpreter.
- Add the smallest independent History, occurrence, Activity, lifecycle, and
  transaction-authority folds needed for the eight CV19 safety properties.
- Preserve the DS2 ownership and compatibility boundary: opaque generations,
  detached observations, public Engine doors, and strict replay.

## Acceptance / Done Condition

1. One bounded generated run can cover deliveries, timers, Activities,
   retries, lifecycle changes, crash/load, and two fault classes.
2. Every applicable CV19 safety property has an executable independent checker;
   any inapplicable or blocked property names its owner and revisit trigger.
3. Broad and focused schedules use one interpreter and produce strict expanded
   artifacts which replay from fresh objects.
4. No checker calls the production decision it claims to judge or mirrors the
   Petri topology as expected truth.

## Out of Scope

- Fair-phase convergence qualification, shrinking proof, or CI campaign tiers.
- Application-specific provider authority or GitHub/readiness semantics.
