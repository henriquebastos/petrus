---
date: 2026-08-18T06:51:15Z
author: Amp
kind: milestone
related:
  - CV19.DS2
verification:
  - UV_FROZEN=1 uv run pytest -q tests/dst (61 passed)
  - v1 crash/recovery replay (pass; converged; 15 operations; 25 journal entries)
  - v2 action-budget replay (pass; budget_exhausted; 2 operations; 4 journal entries)
  - v2 checker-failure replay (pass; invariant_failure; 6 operations; 15 journal entries)
  - v3 seeded crash/recovery replay (pass; converged; 17 operations; 27 journal entries)
  - scripts/check full (2242 passed)
  - scripts/check release (2242 passed in each order; 17 release-profile deselections in the additional order)
  - UV_FROZEN=1 uv build --out-dir /tmp/petrus-dst-v3-dist (sdist and wheel include petrus.testing)
---

# Separable seeded DST choice authorities

## What changed

The supported defining module now authors `petrus.testing.dst/v3` and
`petrus-dst-world` version 3 artifacts. A seeded World gives scenario authors
four SHA-256/counter choice authorities for workload, fault, identifier, and
event ordering. Each authority, and each identifier namespace, advances an
independent counter. The strict artifact records the pinned algorithm, portable
seed, and draw counts as provenance while preserving the expanded operations as
the only replay authority.

Versions 1 and 2 retain explicit models and decode/replay unchanged. Version 1
still produces its original replay-result shape; version 2 and 3 artifacts both
produce replay-result version 2. Profiles cannot access author choice streams
through `ScenarioContext`, so runtime behavior cannot hide an unjournaled
seeded decision.

## Why it matters

CV19.DS3 generators can vary workloads, faults, identifiers, and eligible event
order without observability changes perturbing unrelated streams. A discovered
failure remains durable even if generator policy or PRNG consumption changes,
because data-only replay ignores seed provenance and runs the retained
operations through the same interpreter.

## Verification

The focused DST suite passed 61 tests. Two fresh seed-1729 Engine runs produced
the same 17-operation artifact, and its replay converged with 27 journal entries
and digest
`sha256:ddf70617988b010a3300fc6703eb0c8f1bc1c4b0751b4156c2059f851d34a779`.
Retained v1 and v2 artifacts decoded byte-exactly and replayed with their
original result contracts. The full gate and both release orders passed 2,242
tests; the additional order reported the expected 17 profile deselections. A
clean sdist/wheel build retained the supported `petrus.testing` package.

## Follow-up

CV19.DS2 remains Active for the broader pre/post-durable fault adapter and cut
matrix plus profile-retained-data and wall-clock watchdog bounds. CV19.DS3 owns
Hypothesis state machines, generator policy, shrinking, semantic coverage, and
broad independent-checker campaigns over these choice authorities.
