---
date: 2026-08-18T06:01:45Z
author: Amp
kind: milestone
related:
  - CV19.DS2
verification:
  - UV_FROZEN=1 uv run pytest -q tests/dst (55 passed)
  - legacy v1 replay (pass; converged; 15 operations; 25 journal entries)
  - v2 action-budget replay (pass; budget_exhausted; 2 operations; 4 journal entries)
  - v2 checker-failure replay (pass; invariant_failure; 6 operations; 15 journal entries)
  - scripts/check full (2236 passed)
  - scripts/check release (2236 passed in each order; 17 release-profile deselections in the additional order)
  - UV_FROZEN=1 uv build --out-dir /tmp/petrus-dst-v2-dist (sdist and wheel include petrus.testing)
---

# Exact DST interpreter-failure replay

## What changed

The supported defining module now authors `petrus.testing.dst/v2` and
`petrus-dst-world` version 2 artifacts. A failed World operation retains its
exact normalized attempt plus either action-budget detail or checker-refusal
detail as the terminal expanded operation. Data-only replay executes that
attempt through the same interpreter and accepts it only when the accepted
operation prefix, failure boundary, checker journal, disposition, and complete
journal digest all match. The failure records whether its own call had already
accepted an operation, so replay cannot apply that operation twice when the
failure moves or disappears.

The loader and replay path still decode the retained version 1 artifact into
explicit legacy models and return the original version 1 replay-result shape,
without a new `failure` field. DS1's separate `petrus-dst-scenario` version 1
and hosted `implementation-free-v1` remain unchanged.

Two retained version 2 fixtures prove action-budget exhaustion before an
observation and independent checker refusal after a real Engine terminal
firing. Profile/checker implementation exceptions are deliberately not
reclassified as World-owned replayable failures.

## Why it matters

Generated schedules and future shrinking can now preserve the actual operation
that exposed a bound or invariant instead of serializing only successful
prefixes or claiming an unreplayable failure. Consumers retain one executor and
an exact failure artifact without weakening opaque profile ownership, detached
checker boundaries, or abrupt generation semantics.

## Verification

The focused DST suite passed 55 tests. The legacy version 1 crash/recovery
fixture remained byte-compatible and replayed to `converged`. The action-budget
fixture replayed to `budget_exhausted` with digest
`sha256:8020031489a668e435820458f07d412bfae5bfe4b816e6c8a2e5e5e80dd63275`;
the checker fixture replayed to `invariant_failure` with digest
`sha256:82ca298ed8946a75b35e65b7c8609d1d03ebebf4546f10bde88ebfbccea5a9b1`.
The full gate and both release orders passed 2,236 tests. A clean sdist/wheel
build retained the supported `petrus.testing` package.

## Follow-up

CV19.DS2 remains Active for explicit separable seeded choice streams, broader
pre/post-durable fault cuts and adapters, and the retained-data/watchdog bounds.
CV19.DS3 still owns generated stateful schedules, shrinking, semantic coverage,
and broad independent-checker models.
