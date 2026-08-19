---
date: 2026-08-19T05:31:10Z
author: amp-driver
kind: milestone
related:
  - CV19.DS4.TS2
verification:
  - uv run pytest -q tests/dst/test_failure.py tests/dst/test_generated_runtime_qualification.py — 11 passed
  - uv run python -m tests.dst.failure demonstrate --output /tmp/petrus-dst-failure-demo-v2 — pass
  - uv run python -m tests.dst.failure replay /tmp/petrus-dst-failure-demo-v2 — exact failed journal and green promotion passed
  - uv run pytest -q tests/dst --forbid-skips — 215 passed
  - uv run pytest -q tests/project — 29 passed
  - scripts/check full — 2,403 passed
  - scripts/check release — 2,403 passed in bounded-parallel and fixed-serial orders
---

# CV19.DS4.TS2 retained failures through ordinary promotion

## What changed

Petrus now has one repository-owned operation which rehearses a deliberately
noisy DST liveness failure through exact replay, Hypothesis minimization,
bounded two-file retention, retained replay, and verification of the existing
ordinary green regression. The strict manifest records provenance and concise
semantic reach but never replaces the canonical v4 artifact as execution
authority. The standard replay registry recognizes the test-only mutation
profile only so its retained failure can cross the same interpreter.

Retention fails closed on credential-like keys and values rather than
rewriting replay bytes. It also rejects malformed or unknown manifests, extra
files, tampering, provenance mismatch, and byte overage.

## Why it matters

A future generated counterexample no longer has to survive only as Hypothesis
output or transcript context. The operation demonstrates a bounded,
inspectable handoff to triage and ordinary regression while preserving the
original DST ownership rule: expanded operations are authoritative, a seed is
provenance, and production/runtime semantics are not copied into the harness.

## Verification

The deliberate mutation minimized by removing one retry and three optional
perturbations. Because the 28-action failure budget fixes terminal length, both
artifacts had 29 operations; fair-phase entry moved from operation 16 to 9 and
canonical bytes fell from 130,303 to 128,910. The retained artifact replayed
`pass` / `budget_exhausted` with the exact journal, while the unmutated promoted
fixture replayed `pass` / `quiescent`. Focused, complete DST, project, full, and
release checks all passed as listed in frontmatter.

## Follow-up

CV19.DS4 continues by assembling complementary PostgreSQL transaction,
operating-system process death/restart, Absurd Worker, and ZeroMQ transport
evidence. Those real-boundary claims remain distinct from deterministic
simulation evidence.
