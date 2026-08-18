---
date: 2026-08-18T13:48:44Z
author: amp
kind: milestone
related:
  - CV19.DS2
verification:
  - UV_FROZEN=1 uv run pytest -q tests/dst (95 passed)
  - UV_FROZEN=1 uv run pytest -q tests/dst/test_process_runner.py tests/dst/test_resource_world.py (7 passed)
  - public-Engine process scenario returned and replayed its exact version-4 artifact
  - SIGTERM-resistant profile hang escalated to SIGKILL with its acknowledged prefix and unfinished command
  - scripts/check full (2,276 passed)
  - scripts/check release (2,276 passed in both orders; 17 expected serial deselections)
---

# Contain hung DST Worlds in an outer process

## What changed

The supported defining module now includes the independently versioned
`petrus.testing.dst.runner/v1` outer runner. An exact importable scenario uses a
`ProcessSession` to construct one complete World inside a fresh child process;
profiles, checkers, opaque generations, and live runtime handles never cross
the process boundary. The child synchronizes strict JSONL frames before each
operation attempt and after every legal World boundary. The parent applies a
bounded wall deadline, terminates the process group, escalates to kill after a
bounded grace, and waits for the direct child before returning.

Normal completion requires an ordinary version 1–4 World artifact whose
operations and journal digest equal the accumulated acknowledged prefix. A
wall timeout is instead a structured harness failure containing the complete
prefix and unfinished normalized attempt. It deliberately contains no replay
artifact or deterministic `FailureOperation` for the call that did not return.
Artifact/API, profile/checker, and runner protocol versions remain independent.

## Why it matters

World action, logical-time, and resource budgets cannot stop a production call
which hangs inside a profile. Thread cancellation would leave that runtime
alive, while signal injection would add runtime-specific behavior to the
generic interpreter. Supervising the complete scenario in a killable process
provides honest containment without exposing Petrus private handles or changing
the deterministic artifact contract consumed by Hamsterdan.

## Verification

The existing public-Engine resource-bounded recovery story ran through an
importable child entrypoint, returned the unchanged 14-operation,
39-journal-entry version-4 artifact, and replayed it against a second fresh
Engine graph. A deliberate profile call acknowledged `runtime.hang`, ignored
`SIGTERM`, and forced escalation to `SIGKILL`; the result retained the create
boundary and exact unfinished `SubmitAttempt` while returning no artifact.
The focused DST suite passed 95 tests. The complete gate passed 2,276 tests,
and release qualification passed the same 2,276 tests in both its four-worker
and fixed-order serial runs (17 expected qualification deselections in the
serial run).

## Follow-up

CV19.DS2 remains Active for the broader delivery/Dispatch/lifecycle/transaction
fault matrix and an accepted deterministic LocalDispatch provider-time design.
Stateful generated schedules, shrinking, and broad independent checker
coverage remain DS3; campaign and real-boundary qualification remain DS4.
