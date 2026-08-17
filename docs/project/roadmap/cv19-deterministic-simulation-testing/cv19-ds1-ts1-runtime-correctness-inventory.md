---
code: CV19.DS1.TS1
level: Technical Story
status: Active
status_reason: Runtime seams and correctness obligations are being traced to production code, decisions, and executable evidence
updated: 2026-08-17
related:
  - index.md
  - cv19-ds1-correctness-and-simulation-contract.md
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

## Out of Scope

- Scenario parsing or replay execution.
- Harness, scheduler, or fault-adapter implementation.
- Real-provider determinism or replacement of real-boundary tests.
