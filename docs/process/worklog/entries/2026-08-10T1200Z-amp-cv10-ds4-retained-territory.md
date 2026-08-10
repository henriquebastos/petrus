---
date: 2026-08-10T12:00:00Z
author: Amp
kind: milestone
related:
  - CV10.DS4
  - docs/project/decisions/records/2026-08-09T1400Z-episode-owns-independent-execution-territory.md
verification:
  - focused Agenticus and package-boundary suite — 109 passed
  - scripts/check quick — all touched Python paths passed
  - scripts/check full — 2067 passed
  - scripts/check release — 2067 passed, then 2067 passed with 17 external qualification routes deselected
---

# Qualified host-owned retained Territory reconciliation

## What changed

One private SQLite custody owner now records transfer intent before an Episode
Attachment releases a quiescent exact Territory lease. Release drains Hands
and direct runtime operations, discards stages, exports the bounded public
workspace, closes old authority, and transfers the lease without destruction.
A reconstructed local host can reclaim only that exact lease into a distinct
Episode Attachment or retire it through verified identity-correlated cleanup.

The ledger prevents competing live obligations for one provider operation,
quarantines malformed durable identities without issuing cleanup, retries
trustworthy temporary identity conflicts, and clears retained archive bytes
after verified retirement. A replacement Python process exercised the same
hermetic Gondolin root and custody ledger. Activity, Worker, and runtime service
remain lifecycle-free borrowers of an existing Attachment.

## Why it matters

Territory retention is now explicit custody transfer rather than accidental
survival when destruction is omitted. The resource remains orthogonal to
Activity while the host gains a bounded, inspectable obligation to reclaim or
destroy exactly what it retained.

## Verification

Focused Agenticus and package-boundary verification passed 109 tests, including
release-versus-private-probe cleanup draining, exact-type SQLite corruption,
foreign-identity retry, no-create reclaim, crash-state fencing, and replacement
process reconciliation. `scripts/check full` passed 2067 tests.
`scripts/check release` passed 2067 tests in parallel and then 2067 tests with
17 external qualification routes deselected in fixed order.

## Follow-up

CV10 returns to Blocked beyond this bounded route. Live providers, multi-host
custody and service discovery, provider-side fencing, power-loss durability,
public retention APIs, and reconstruction of active work remain unqualified.
