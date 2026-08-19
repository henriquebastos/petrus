---
date: 2026-08-19T03:21:00Z
author: Amp
kind: milestone
related:
  - CV19.DS3.TS1
  - CV19.DS3.TS2
verification:
  - UV_FROZEN=1 uv run pytest -q tests/dst/test_generated_delivery_world.py --hypothesis-show-statistics
  - UV_FROZEN=1 uv run pytest -q tests/dst/test_delivery_world.py tests/dst/test_generated_delivery_world.py
  - UV_FROZEN=1 scripts/check quick tests/dst/test_generated_delivery_world.py
  - UV_FROZEN=1 uv run pytest -q tests/dst
  - UV_FROZEN=1 uv run pytest -q tests/project
  - UV_FROZEN=1 scripts/check full
  - UV_FROZEN=1 scripts/check release
---

# Generated identified-delivery schedules

## What changed

Expanded CV19.DS3 into three Technical Stories and completed the first. Broad
and focused Hypothesis `RuleBasedStateMachine` programs now live directly under
`tests/dst`, so ordinary pytest executes them rather than routing generated
scenarios through a separate scripts directory or executor.

Both families author only external delivery identity/payload facts and abrupt
crash/load choices. Every state-affecting operation crosses the existing
supported World/Timeline interpreter. The broad family keeps three identities
and the integer values `-1`, `0`, and `1` independent. The focused family
guarantees applied delivery, exact idempotent redelivery, changed-content
refusal, abrupt generation drop, and public fresh load in every example, then
generates additional redelivery, conflict, distinct-delivery, and crash/load
orderings.

The state-machine model tracks authored identity authority only and compares it
with detached canonical delivery and marking observations. The existing
`DeliveryAuthorityChecker` continues to run after every accepted World atomic
boundary. No model or checker calls the production delivery operation or reads
a private Engine/Coordinator handle.

Every successful generated example is finished explicitly as an external wait,
encoded as a strict expanded artifact, and replayed immediately through fresh
profile, checker, JSONL History, and public Engine objects. The replay must
match operations, checker results, disposition, and journal digest exactly;
Hypothesis choice is discovery input rather than permanent replay authority.

## Why it matters

This is the first executable DS3 proof that the debugger-like World can also be
the one stateful generation substrate. Hand-authored timelines, broad workload
draws, focused race amplification, and strict replay no longer imply competing
execution semantics. The generated test stays self-contained under
`tests/dst`, as the Navigator requested.

It does not overstate one profile as the complete campaign. TS2 now owns one
production-Engine run spanning delivery, time, Activities, retry, lifecycle,
crash/load, and two fault classes. TS3 owns fair convergence, mutation
shrinking, semantic coverage, and durable minimized failure promotion.

## Verification

- The two generated nodes passed with Hypothesis statistics enabled. Their
  configured bounds are 30 examples × 8 generated steps for the broad family
  and 20 examples × 6 generated steps plus the high-value initializer for the
  focused family.
- The generated and hand-authored delivery suites passed all 5 tests.
- The complete DST suite passed 194 tests; project coherence passed 29.
- `scripts/check full` passed all 2,382 tests.
- `scripts/check release` passed all 2,382 tests in both orders, with 17
  expected serial qualification deselections.
- An initial full run exposed an unrelated xdist overlap in a Gondolin test's
  machine-global temporary-directory assertion. The exact serial node passed,
  no directory remained, and clean subsequent full and release gates passed.

## Review and follow-up

This slice adds test-owned generation and roadmap/process memory only. It adds
no production API, package export, artifact version, retained generated-success
fixture, decision, or debt. Abrupt drop and graceful cleanup remain distinct,
the profile generation remains opaque, and replay remains fail-closed.

CV19.DS3.TS2 is active next. Its first design task is to choose the smallest
single production-Engine net/profile that can combine the full DS3 event and
fault vocabulary without merging external authority into Petrus semantics or
reusing existing focused profiles as a second executor.
