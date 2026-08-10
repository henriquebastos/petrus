---
date: 2026-08-10T06:37:53Z
author: Amp
kind: milestone
related:
  - CV8.DS5
  - docs/project/decisions/records/2026-08-10T0555Z-one-logical-activity-execution-owns-durable-operational-retries.md
verification:
  - focused Motus, Engine, Local, ZeroMQ, and Worker suite — 257 passed
  - real pinned Durable Dispatch adapter suite — 92 passed
  - final Oracle release-blocker review — approved
  - scripts/check release — 2109 passed in parallel, then 2109 passed with 17 external qualification routes deselected
---

# Shipped one durable logical Activity execution

## What changed

Motus now preserves one immutable Activity invocation, correlation identity,
and idempotency identity across bounded operational Attempts. Public execution
policy supports deterministic backoff, renewable heartbeat custody,
per-Attempt and aggregate deadlines, and the conservative one-Attempt default.
Activities can report safe classified failures with optional retry-after
guidance. Local Dispatch durably schedules delayed retries and migrates its
exact v1 schema to v2; ZeroMQ preserves the complete policy and failure wire;
the pinned Durable Dispatch provider schedules supported retries and refuses
deadline contracts it cannot enforce soundly. Inline remains immediate,
in-process, and never sleeps for backoff.

Terminal failure now freezes as its own canonical `ActivityFailed` fact before
either explicit deterministic `project_failure` effects or legacy
`FiringFailed` and halt. Reload after a projection crash resumes only from the
frozen failure. Type-sensitive terminal identity acknowledges exact duplicate
reports and rejects changed content across Instance, Local, and Durable
Dispatch, including legacy custody normalized during upgrade.

## Why it matters

Applications can remove Petri topology that represented only operational retry
machinery while keeping business identity and canonical History independent of
provider custody. The same freeze-before-projection safety boundary now covers
success and terminal failure without claiming exactly-once external effects.

## Verification

Focused Motus, Engine, Local, ZeroMQ, and Worker coverage passed 257 tests. The
real pinned Durable Dispatch/PostgreSQL adapter passed 92 tests. Adversarial
review exercised restart scheduling, heartbeat versus hard deadline, aggregate
exhaustion, migration, duplicate/conflicting terminal reports, type-sensitive
JSON identity, extreme numeric policies, and failure projection crash/reload;
the final release-blocker review approved the repaired diff.

`scripts/check release` passed all static gates and 2109 tests in parallel,
then 2109 tests with 17 explicit external installation/provider qualification
routes deselected in fixed order. Those external routes are not claimed green.

## Follow-up

Applications still own authority/currentness, desired-state supersession,
lookup-first reconciliation of ambiguous external effects, and idempotent side
effects. Cancellation, deterministic jitter, child/local Activities, nested
durable calls, and exact deadlines in providers that currently refuse them
remain out of scope.
