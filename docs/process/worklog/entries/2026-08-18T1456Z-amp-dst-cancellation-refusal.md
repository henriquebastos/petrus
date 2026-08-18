---
date: 2026-08-18T14:56:50Z
author: amp
kind: milestone
related:
  - CV19.DS2
verification:
  - UV_FROZEN=1 uv run pytest -q tests/dst/test_lifecycle_cancellation_world.py (4 passed)
  - UV_FROZEN=1 uv run pytest -q tests/dst (105 passed)
  - UV_FROZEN=1 uv run pytest -q tests/dst tests/project (134 passed)
  - cancellation-refusal replay (quiescent; 19 operations; 32 journal entries; 12 checker evaluations)
  - scripts/check full (2,292 passed)
  - scripts/check release (2,292 passed in both orders; 17 expected serial deselections)
---

# Deterministic lifecycle-cancellation repair after refusal

## What changed

A paired public-Engine DST profile now refuses the first Dispatch cancellation
after production History accepts `ScopeReset`. It observes the durable reset
and exact refused `CancellationInstruction`, revokes and abruptly drops the
poisoned generation, and loads a fresh Engine/Dispatch graph. Production
reconciliation submits the byte-equivalent instruction to the new Dispatch;
only its accepted tombstone precedes one late-terminal quarantine.

The detached checker independently bounds lifecycle, ordinary terminal,
projection, and quarantine facts by authored world authority while requiring
the refused-then-accepted instruction to remain exact. A mutation-sensitive
test rejects a changed repair instruction, while a paired ownership test keeps
the durable reset—not cancellation custody—as late-terminal authority. The
separate strict version-3 artifact records the named fault, process cut, fresh
load, checker evaluations, and quiescent result through the existing World
interpreter.

## Why it matters

The `scope_fenced` cut is now an exact retained DST story rather than only a
focused Engine unit-test claim. It demonstrates that durable lifecycle
authority outruns failed operational cancellation custody and that recovery
repairs the exact fence without projecting a result into the new generation.

## Verification

The focused test passed all 4 cases. The concrete replay returned `pass` /
`quiescent` across 19 operations and 32 journal entries, including 12
independent checker evaluations, with digest
`sha256:0b4ccbadb61d020c28ea3f330fbd2a7bf27b1af9157db2a375e25f6bcbb3da69`.
The DST suite passed 105 tests, and the DST plus project suite passed 134. The
complete full and release gates passed 2,292 tests; release passed both its
four-worker and fixed-order runs, with 17 expected qualification deselections
in the serial run.

## Follow-up

CV19.DS2 remains Active for the broader joined-transaction cut matrix. The
scripted adapter proves the public cancellation contract and semantic repair;
real provider, transport, storage, and operating-system failure remain DS4
qualification boundaries.
