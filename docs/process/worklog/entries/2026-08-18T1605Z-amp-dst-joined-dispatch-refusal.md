---
date: 2026-08-18T16:05:29Z
author: amp
kind: milestone
related:
  - CV19.DS2
verification:
  - UV_FROZEN=1 uv run pytest -q tests/dst/test_joined_world.py (5 passed)
  - joined provider and transaction matrix (119 passed)
  - UV_FROZEN=1 uv run pytest -q tests/dst (110 passed)
  - UV_FROZEN=1 uv run pytest -q tests/dst tests/project (139 passed)
  - retained joined-Dispatch replay (external_wait; 9 operations; 16 journal entries; 6 checker evaluations)
  - scripts/check full (2,297 passed)
  - scripts/check release (2,297 passed in both orders; 17 expected serial deselections)
---

# Deterministic joined-Dispatch rollback and reconstruction

## What changed

A second separately identified provider-backed DST profile now refuses the
Absurd task-spawn call while the public Engine's four-record semantic begin is
still uncommitted. The existing test-owned connection adapter records the
complete attempted batch and raises before task insertion. Independent
PostgreSQL observation proves production rollback retained only construction
and no task custody.

The World then revokes and abruptly drops the poisoned generation. Fresh public
provider load prepares from the original marking and commits exactly one begin
plus one pending task. The retained v3 artifact replays through the identical
interpreter and the same detached joined-transaction authority checker.

## Why it matters

The prior artifact refused the joined commit after both History and Dispatch
preparation succeeded. This paired cut reaches a materially different failure
source: Dispatch itself fails before commit acceptance. Together they mirror
the production transaction-fate pins without exposing private Coordinator or
Engine-resource handles and prove the commit-or-vanish guarantee from both
owned boundaries.

The evidence remains deliberately narrow. It qualifies the pinned public
Absurd/PostgreSQL composition's task-spawn failure and fresh-load repair; it
does not claim database power-loss, Worker execution, transport, or arbitrary
SQL fault fidelity.

## Verification

The retained replay passed with `external_wait`, 9 operations, 16 journal
entries, 6 checker evaluations, and digest
`sha256:e9bc6574670b3c2d55c8659c3ba9b0bea826544502bd174cd4d5885577483a7a`.
The joined profile passed all 5 cases and the broader joined/provider matrix
passed 119. DST passed 110 and DST plus project passed 139. Full and release
gates passed all 2,297 tests; release passed both its four-worker and
fixed-order runs with 17 expected qualification deselections.

## Follow-up

CV19.DS2 remains Active for the broader transaction/fault matrix. No production
API, supported DST compatibility contract, artifact schema, prior profile
identity, or checker identity changed in this slice.
