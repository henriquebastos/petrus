---
date: 2026-08-10T13:23:33Z
author: Amp
kind: milestone
related:
  - ES-001
  - CV8
  - docs/project/decisions/records/2026-08-10T1200Z-instance-identity-scopes-shared-activity-resolution.md
verification:
  - focused Local, Worker, async, ZeroMQ, and real Absurd scope routes passed
  - scripts/check full — 2125 passed
  - scripts/check release — 2125 passed in parallel, then 2125 passed with 17 external qualification routes deselected
  - final Oracle release-blocker review — approved after coherence repair
---

# Shared durable Activity scope across isolated Instances

## What changed

Worker-facing Attempts and synchronous/asynchronous execution contexts now
carry their authorizing Instance identity. Local and Absurd custody preserve
that scope through durable retry and reconstruction; strict ZeroMQ Worker
protocol v2 transports it. Workers can optionally resolve one scoped Activity
implementation by Instance and Activity name, with ordinary mappings retained
as explicit fallback. A bounded synchronous `run_available` pump lets a host
process immediately available work without creating a Worker thread or
transferring lifecycle ownership to Petrus.

## Why it matters

Many isolated Engine Instances can share durable execution infrastructure
without putting routing fields in business payloads, serializing host
capabilities, or rebuilding Worker behavior in an application. Activity modules
remain normal reconstructible host composition. Application Nets can remove
operational Attempt/retry/due/reissue topology while keeping authorization,
operation ownership, current-state acceptance, supersession, and terminal
exhaustion explicit.

## Verification

Focused evidence covered two-Instance scope and terminal isolation, default and
scoped resolution, delayed retry after Worker reconstruction, synchronous and
native-async parity, ZeroMQ v2 scope transport, real Absurd/PostgreSQL scope,
bounded pump lifecycle/concurrency, and unchanged Inline History. The first
full pass exposed established unscoped raw Absurd tasks; scoped Workers now fail
closed on missing scope while default Workers retain that provider behavior.

`scripts/check full` then passed 2,125 tests. `scripts/check release` passed
2,125 tests in parallel and 2,125 tests with 17 explicit external qualification
routes deselected in fixed order. Those routes are not claimed green.

## Follow-up

Multi-Instance runnable indexing, wake hints, and one-owner-per-Instance claims
remain host scheduling responsibilities. A durable Activity binding or richer
scope should be reconsidered only when a concrete second field or coexisting
implementation profile requires it.
