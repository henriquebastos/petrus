---
date: 2026-08-17T23:30:55Z
author: Amp
kind: milestone
related:
  - CV19.DS2
verification:
  - UV_FROZEN=1 uv run pytest -q tests/dst (45 passed)
  - UV_FROZEN=1 uv run python -m tests.dst.replay_world tests/dst/fixtures/projection-crash-recovery-world-v1.json (pass; converged; 15 operations)
  - scripts/check full (2226 passed)
  - scripts/check release (2226 passed in each order; 17 release-profile deselections in the additional order)
  - UV_FROZEN=1 uv build --out-dir /tmp/petrus-dst-dist (sdist and wheel include petrus.testing)
---

# Supported DST executable-World vertical slice

## What changed

Petrus now ships the accepted `petrus.testing.dst/v1` defining-module test
contract: strict normalized commands/faults/observations, deterministic logical
time and total queue ordering, explicit budgets, opaque runtime generations,
distinct abrupt drop and graceful close, fair-phase control, detached checkers,
strict expanded artifacts, and same-interpreter replay.

An imperative scenario under `tests/dst/` drives only public Engine,
HistoryStore, and Dispatch doors through Activity request, terminal freezing,
projection refusal, abrupt generation loss, fresh load, and projection-only
convergence. It generates the retained `petrus-dst-world` version 1 fixture and
the data-only replay reproduces its exact operations, checker observations,
ending disposition, and journal digest.

The DS1 `petrus-dst-scenario` version 1 and hosted
`implementation-free-v1` contracts remain unchanged. A structural ast-grep
rule prevents the supported generic kernel from importing Petrus product or
private runtime modules.

## Why it matters

Application projects can now compose domain Worlds, Timelines, opaque host
profiles, and independent oracles over one supported Petrus executor instead
of copying a scheduler or importing private Coordinator/runtime handles. The
scenario remains readable executable pytest code while expanded strict data,
not callbacks or a seed, owns replay.

## Verification

The focused DST suite passed 45 tests. The concrete replay route returned
`pass` and `converged` for 15 operations and 25 journal entries with digest
`sha256:609247836dae1f306b34e5d7308901c10f95db2207fa0e583c446d98354cab74`.
The full repository gate passed 2,226 tests. The release gate passed the same
2,226 tests in its default order and 2,226 tests with 17 release-profile
deselections in the additional fixed order. All 19 ast-grep rule fixtures
passed. A clean sdist/wheel build included both supported `petrus.testing`
modules.

## Follow-up

CV19.DS2 remains Active. Explicit separable seeded choice streams, broader
pre/post-durable fault cuts and adapters, profile-retained-data and watchdog
bounds, and serialization/replay of interpreter-failure attempts remain before
the Delivery Story can close. DS3 still owns generated stateful schedules,
shrinking, and broad independent-checker coverage.
