---
date: 2026-08-19T04:05:41Z
author: Amp
kind: milestone
related:
  - CV19.DS3.TS2
  - CV19.DS3.TS3
verification:
  - uv run pytest -q tests/dst/test_generated_runtime_world.py --hypothesis-show-statistics
  - uv run pytest -q tests/dst
  - uv run pytest -q tests/project
  - scripts/check quick
  - scripts/check full
  - scripts/check release
---

# Cross-layer generated runtime campaign

## What changed

Completed CV19.DS3.TS2 with one self-contained production-Engine profile under
`tests/dst`. Its normalized vocabulary spans scope open/reset, identified
source delivery and exact redelivery, scheduled Engine driving, Worker
claim/fail/complete, logical-time timer maturation, abrupt generation loss and
fresh load, refused Dispatch custody, and refused semantic projection. The
profile composes public `Engine`, JSONL History, and real LocalDispatch/Worker
doors without exposing Coordinator or mutable runtime handles.

The focused Hypothesis state machine executes the full two-fault route in every
example: durable request before refused custody, stable redispatch after load,
one failed attempt and retry, frozen terminal before refused projection,
projection-only recovery, scope reset, late-terminal quarantine, and timer
maturation. The broad family varies those dimensions with fewer ordering
constraints across up to two external Activities. Every state-affecting action
crosses the same World interpreter used by the hand-authored timeline and
artifact replay.

`GeneratedRuntimeAuthorityChecker` continuously covers CV19 S1–S8 through
detached replay agreement, an independent occurrence/in-flight/lifecycle fold,
dense writer-valid identities, stable request/Dispatch/Worker invocation,
stateful no-reexecution-after-freeze counts, delivery acknowledgement
authority, terminal/projection authority, lifecycle quarantine, retry/timer
bounds, and explicit v4 profile resources. A test mutates each major detached
authority family and proves the checker refuses the divergence.

Every successful generated schedule finishes explicitly and replays current-v4
expanded operations, checker and resource samples, disposition, and journal
digest through fresh Engine, History, Dispatch, profile, and checker objects.
No generated-success fixture or second executor was added.

## Why it matters

Petrus now exercises its full generic DST safety vocabulary as an executable
world rather than a set of isolated crash examples. The design preserves the
same abstraction boundary Hamsterdan can consume: Petrus owns deterministic
scheduling, replay, and runtime safety; an application profile owns domain
truth and external effects.

The evidence remains deliberately bounded. This JSONL/LocalDispatch campaign
does not replace DS2's real Absurd/PostgreSQL transaction qualification and
does not yet claim fair convergence, shrink/promotion, semantic coverage, or
CI campaign cadence. CV19.DS3.TS3 is active for the first three.

## Verification

- The hand-authored replay, checker-divergence, focused generated, and broad
  generated nodes passed: 4 tests in 10.92 seconds with Hypothesis statistics
  enabled.
- The complete DST suite passed 198 tests; project coherence passed 29.
- `scripts/check quick` passed lint, formatting, and static checks.
- `scripts/check full` passed all 2,386 tests.
- `scripts/check release` passed all 2,386 tests in both suite orders; the
  second order reported the expected 17 serial qualification deselections.

## Review and follow-up

No production module, package export, compatibility format, decision record,
or technical-debt item changed. Abrupt drop remains distinct from graceful
cleanup, opaque profile generations remain intact, and checkers receive only
detached strict observations. The generated campaign uses current v4 resource
accounting rather than adding a compatibility version.

CV19.DS3.TS3 is next. It owns fair-phase convergence, selected-mutation
shrinking, durable minimized failure promotion, broad-only blind-spot evidence,
and semantic coverage before DS3 can close.
