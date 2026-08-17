---
code: CV19.DS1.TS2
level: Technical Story
status: Done
status_reason: Version 1 now refuses non-strict artifacts and deterministically replays the retained projection-crash scenario through fresh production Engines
updated: 2026-08-17
related:
  - index.md
  - cv19-ds1-correctness-and-simulation-contract.md
  - cv19-ds1-ts1-runtime-correctness-inventory.md
  - ../../../process/dst-scenario-v1.md
  - ../../../../scripts/dst_replay.py
  - ../../../../tests/dst/fixtures/projection-crash-recovery-v1.json
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

## Delivered Evidence

- [`dst-scenario-v1`](../../../process/dst-scenario-v1.md) specifies the
  internal `engine-coordinator-v1` strict JSON contract. Its Pydantic owner
  rejects duplicate keys, non-finite numbers, unknown fields or vocabulary,
  implicit coercion, unsupported versions/profiles, invalid fault cuts,
  incoherent crash/restart order, duplicate marking places, and profile-bound
  violations before constructing runtime objects.
- The retained
  [`projection-crash-recovery-v1.json`](../../../../tests/dst/fixtures/projection-crash-recovery-v1.json)
  carries commit/runtime/dependency/property/shrink provenance, explicit
  limits, an expanded six-step schedule, the named terminal-frozen cut, and
  exact step/final expectations as data only. Live collaborators are selected
  by a digest-pinned replay-side application catalog entry, never serialized.
- `UV_FROZEN=1 uv run python scripts/replay-dst-scenario.py
  tests/dst/fixtures/projection-crash-recovery-v1.json` emitted one stable
  passing result twice: nine exact History record kinds, terminal `done`
  marking, no in-flight or pending Activity, one projection after restart,
  and zero re-prepare or redispatch.
- The focused contract/replay suite passed **17 tests**. Six equivalent
  production crash-window nodes passed across Engine, Coordinator, Activity
  integration, JSONL, and SQLite History routes.
- The repository-required `scripts/check full` route passed lint, formatting,
  production type checking, ast-grep, and **2,198 tests**. Local CV19 Markdown
  links and `git diff --check` also passed.
- No public `petrus.simulation` or `implementation-free-v1` source, spec,
  fixture, or result contract changed. General scheduling, fault adapters,
  generation, and campaign operations remain owned by DS2–DS4.

## Out of Scope

- A generalized event scheduler or faulting adapter.
- Seed expansion, generation, or shrinking.
- Stable public package or language-neutral protocol support.
