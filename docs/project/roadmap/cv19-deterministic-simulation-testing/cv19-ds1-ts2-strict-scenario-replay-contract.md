---
code: CV19.DS1.TS2
level: Technical Story
status: Planned
status_reason: The strict-data scenario/replay artifact and fixture have not yet been implemented
updated: 2026-08-17
related:
  - index.md
  - cv19-ds1-correctness-and-simulation-contract.md
  - cv19-ds1-ts1-runtime-correctness-inventory.md
---

# CV19.DS1.TS2 — Strict scenario and replay contract

## Intent

Make an expanded deterministic schedule a durable, strict-data reproduction
contract instead of relying on a seed, closures, or live runtime objects.

## Scope

- Define a versioned, closed scenario/replay artifact carrying generation,
  runtime, property, and shrink provenance; explicit bounds and fair phase;
  expanded events and named semantic cuts; and expected observations.
- Keep the contract internal/test-owned until separate public-API acceptance.
- Encode the existing Activity-terminal-freeze → process crash → load →
  projection-only completion regression as the first fixture.
- Add one exact replay test that validates the document before driving the
  production Engine/Coordinator route without consulting a PRNG.

## Acceptance / Done Condition

1. Unknown fields, unsupported versions, malformed exact integers, unknown
   events/cuts, and non-JSON values fail before runtime construction.
2. The fixture contains no callable, client, credential, provider, Dispatch,
   Engine, Instance, or other live-object serialization.
3. Replaying the fixture reaches the expected History kinds, marking, status,
   and projection-only evidence with no Activity redispatch or re-prepare.
4. Commit/runtime/dependency identity, property, expanded schedule, cut,
   original seed, and shrink lineage all fit the artifact.

## Driver QA and Evidence Plan

- Run exact positive and negative contract tests.
- Run the existing equivalent Coordinator and durable-backend crash nodes.
- Demonstrate the exact fixture replay command from a fresh test process.

## Out of Scope

- A generalized event scheduler or faulting adapter.
- Seed expansion, generation, or shrinking.
- Stable public package or language-neutral protocol support.
