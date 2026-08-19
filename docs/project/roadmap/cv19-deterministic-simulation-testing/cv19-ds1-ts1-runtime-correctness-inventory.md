---
code: CV19.DS1.TS1
level: Technical Story
status: Done
status_reason: The focused DST owner now freezes evidence-graded seams, cuts, properties, taxonomies, bounds, coverage, and compatibility without finding a DS2 blocker
updated: 2026-08-17
related:
  - index.md
  - cv19-ds1-correctness-and-simulation-contract.md
  - ../../../process/deterministic-simulation-testing.md
---

# CV19.DS1.TS1 — Runtime correctness inventory

## Intent

Give DS2 one authoritative, evidence-grounded map of what the deterministic
harness controls, what remains real behind a production contract, which cuts
matter, and what every bounded run must check.

## Scope

- Classify relevant nondeterminism across Instance, Engine/Coordinator,
  History Store, Dispatch, Worker transport, timers, lifecycle, identifiers,
  and reconstruction as controlled, intentionally external, or blocking.
- Map durable and irreversible cuts at the semantic doors that own them.
- Freeze initial safety properties, fair-environment liveness, event and fault
  taxonomies, bounds and dispositions, and semantic-coverage vocabulary.
- Preserve Impetus/Motus ownership and the public `implementation-free-v1`
  compatibility boundary explicitly.

## Acceptance / Done Condition

1. Every classified source names its owner, control or exclusion, and evidence.
2. Every initial event and fault names its bound, disposition, and future
   replay spelling.
3. Safety and liveness are executable in shape and do not promise progress
   under permanent external failure.
4. No Engine/Coordinator nondeterminism needed by DS2 bypasses an owned or
   explicitly controllable seam.
5. Public hosted simulation remains unchanged and outside the DST harness.

## Driver QA and Evidence Plan

- Trace representative replay, timer, Activity, lifecycle, History Store,
  Local/Absurd Dispatch, and ZeroMQ tests.
- Search production Engine, Impetus, and Motus paths for wall clock, UUID,
  randomness, sleeps, task scheduling, and provider calls.
- Check every retained claim against executable evidence or an authoritative
  decision and grade its provenance.

## Delivered Evidence

- [`docs/process/deterministic-simulation-testing.md`](../../../process/deterministic-simulation-testing.md)
  is the focused owner. It distinguishes existing test, hosted simulation,
  DST replay/campaign, and real-adapter evidence; classifies controlled and
  external nondeterminism; and freezes the initial durable cuts, executable
  safety/fair-liveness properties, event/fault vocabulary, dispositions,
  bounds, semantic coverage, and qualification split.
- The inventory found no Engine/Coordinator semantic nondeterminism blocker
  for DS2 when the profile supplies instance identity and logical time, pins
  built-in deterministic policies, scripts existing Dispatch/History doors,
  and drives production actions explicitly. It also states the stop rule if
  implementation discovers a bypassing choice.
- The `implementation-free-v1` public result profile remains unchanged and is
  explicitly separate from the then-planned internal `engine-coordinator-v1`
  DST scenario profile subsequently delivered by DS1.TS2.
- The evidence-focused test route passed **481 tests** across hosted
  simulation, Engine/Coordinator, identity, ingress, replay properties,
  timers, selection, History backends, Activity integration, Local/ZeroMQ,
  and hermetic Gondolin behavior. One explicitly real-Gondolin acceptance test
  skipped because its SDK module and image were not configured; TS1 makes no
  real-provider qualification claim.
- The repository-required `scripts/check full` route passed lint, formatting,
  production type checking, ast-grep, and **2,181 tests** with no skips in the
  routine profile.
- Every local Markdown link in the CV19 roadmap and focused owner resolved, and
  `git diff --check` passed.

## Out of Scope

- Scenario parsing or replay execution.
- Harness, scheduler, or fault-adapter implementation.
- Real-provider determinism or replacement of real-boundary tests.
