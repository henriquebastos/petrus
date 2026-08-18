---
date: 2026-08-18T14:25:02Z
author: amp
kind: milestone
related:
  - CV19.DS2
verification:
  - UV_FROZEN=1 uv run pytest -q tests/petrus/motus/dispatch/test_local_dispatch.py tests/petrus/motus/worker/test_worker_runtime.py (53 passed)
  - UV_FROZEN=1 uv run pytest -q tests/dst (98 passed)
  - delayed retry replay (quarantined; 22 operations; 35 journal entries; 12 checker evaluations)
  - scripts/check full (2,285 passed)
  - scripts/check release (2,285 passed in both orders; 17 expected serial deselections)
---

# Deterministic LocalDispatch provider time and delayed retry replay

## What changed

LocalDispatch and LocalWorkerDispatch now accept an optional monotone
millisecond provider clock. The default remains the existing SQLite time read;
SQLite remains custody and serialization authority in either mode. Clock
values are sampled once inside each relevant transaction, validated as exact
nonnegative signed-64-bit integers, and guarded against rewind. A Worker
constructed through `LocalDispatch.worker()` receives the same clock guard.

A separately identified DST profile maps World logical seconds to that public
provider-time contract. It fails Activity epoch 1 under a five-second retry
policy, abruptly drops the Engine/Worker generation, and loads a fresh public
Engine plus LocalDispatch graph. The public Worker claim door returns no work
at instant 4 and epoch 2 at instant 5 with unchanged logical invocation
identity. Exhaustion still records one `ActivityFailed` and `FiringFailed` with
no projection. The profile retains a strict version-3 artifact without changing
the prior zero-backoff profile or any artifact schema.

## Why it matters

Delayed retry eligibility is now decided by production LocalDispatch SQL under
controlled provider time rather than by real sleep, private row mutation, the
Engine clock, or a second scheduler. This closes the compatibility boundary
that kept nonzero backoff out of the first retry scenario while preserving the
LocalDispatch/Worker ownership decision and default behavior.

## Verification

The focused LocalDispatch and Worker suites passed 53 tests, including default
clock behavior, restart persistence, exact before/at-deadline claims, malformed
clock refusal, and the shared monotonicity guard. The DST suite passed 98 tests.
The retained delayed-retry route replayed as `pass` / `quarantined` across 22
operations and 35 journal entries, including 12 independent checker
evaluations, with digest
`sha256:339da88d51c682641b7e8fc8fbf8964622c2c031dd6c373f327b94464e26a6c1`.
The complete full and release gates passed 2,285 tests; release passed both
four-worker and fixed-order serial runs, with 17 expected serial
deselections.

## Follow-up

CV19.DS2 remains Active for broader delivery, lifecycle, Dispatch, and
transaction fault adapters. Deterministic provider time does not by itself
qualify real process scheduling, SQLite kernel/filesystem failure, or
cross-process clock authority. Stateful generated schedules and shrinking
remain DS3; campaign and real-boundary qualification remain DS4.
