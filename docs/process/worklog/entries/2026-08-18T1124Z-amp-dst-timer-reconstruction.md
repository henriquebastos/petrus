---
date: 2026-08-18T11:24:29Z
author: Amp
kind: milestone
related:
  - CV19.DS2
verification:
  - UV_FROZEN=1 uv run pytest -q tests/dst (70 passed)
  - seven retained World replay routes (all pass with exact dispositions and journal digests)
  - timer replay (converged; 15 operations; 24 journal entries; 8 checker evaluations)
  - scripts/check full (2251 passed)
  - scripts/check release (2251 passed in each order; 17 release-profile deselections in the additional order)
---

# Deterministic timer reconstruction after process loss

## What changed

A fourth exact public-Engine profile under `tests/dst/` now drives a real
delayed transition through the supported World interpreter. At logical instant
0 the profile observes deadline 5 and returns that future drive to the World.
The scenario then abruptly drops the process, proving that the volatile queued
command is discarded before it can mature.

A fresh `Engine.load` reconstructs the same deadline from canonical History
and the injected World clock. Under the fair phase the World advances directly
to instant 5, records one `TimerMatured`, and fires the delayed transition once.
An independent detached checker continuously rejects early or duplicate
maturation and any delayed firing not preceded by its canonical maturation
fact.

## Why it matters

This covers Engine-owned timer observation, volatile scheduler loss, public
load, logical-time advancement, and resumed firing without real sleep or a
second timer implementation. It deliberately does not treat an Engine timer as
Activity retry: retry delay and exhaustion belong to the Dispatch provider,
whose deterministic-time composition remains follow-up DS2 work.

## Verification

The focused DST suite passed 70 tests, and all seven retained fixtures replayed
through `tests.dst.replay_world` with exact outcomes and dispositions. The new
12,040-byte fixture ended `converged` across 15 operations and 24 journal
entries, including 8 checker evaluations, with digest
`sha256:82460bacb8628c897a35e19883cb0f91e07bc1343cd5944ea22592c940fc8a69`.
Source lint, format, type, and all 19 architecture-rule fixtures passed.
The full gate and both release orders passed 2,251 tests; the additional order
reported the expected 17 profile deselections.

## Follow-up

CV19.DS2 remains Active for deterministic Dispatch retry, broader delivery and
transaction cuts, profile-retained-data bounds, and wall-clock watchdog
qualification.
