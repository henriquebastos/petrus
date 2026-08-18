---
date: 2026-08-18T10:54:13Z
author: Amp
kind: milestone
related:
  - CV19.DS2
verification:
  - UV_FROZEN=1 uv run pytest -q tests/dst (64 passed)
  - five retained World replay routes (all pass with exact dispositions and journal digests)
  - history-refusal replay (converged; 19 operations; 31 journal entries; 11 checker evaluations)
  - scripts/check full (2245 passed)
  - scripts/check release (2245 passed in each order; 17 release-profile deselections in the additional order)
---

# Pre-commit terminal History refusal and recovery

## What changed

The Petrus-owned public-Engine DST profile now has a paired pre-commit fault
proof for the existing post-commit projection-recovery scenario. A complete
`HistoryStore` adapter refuses one `ActivityCompleted` append before its JSONL
delegate accepts anything. The World then revokes and abruptly drops the
poisoned generation, reloads through `Engine.load`, and reconciles the recorded
Activity into fresh Dispatch custody without preparing a second logical
invocation. Detached observations prove the occurrence, activity, input,
execution policy, correlation, and idempotency identities remain exact before
terminal redelivery and fair convergence.

An independent commit-authority checker runs after each atomic operation and
fresh load. It bounds canonical terminal and projection records by authored
external terminal deliveries minus observed pre-commit refusals. A focused
mutation-sensitive test proves the checker rejects a terminal above that
external acceptance authority.

## Why it matters

The retained proof now covers both unambiguous sides of the Activity terminal
durability boundary without exposing Coordinator or mutable runtime handles:
pre-commit refusal repeats the external terminal after reconstruction, while
post-commit projection refusal resumes from the frozen durable result. Both use
the same supported World interpreter and strict replay contract.

## Verification

The focused DST suite passed 64 tests. All five retained fixtures replayed
through `tests.dst.replay_world` with their exact outcomes and dispositions.
The new 16,071-byte fixture converged across 19 operations and 31 journal
entries, including 11 checker evaluations, with digest
`sha256:d8a9dec14dc40dc5a27afeaec9028ac37646695e22ff75bee2ce7f2c0f06aff1`.
The full gate and both release orders passed 2,245 tests; the additional order
reported the expected 17 profile deselections. Source lint, format, type, and
all 19 architecture-rule fixtures also passed.

## Follow-up

CV19.DS2 remains Active. The wider delivery, Dispatch, lifecycle, and
transaction fault matrix, profile-retained-data bounds, and wall-clock watchdog
qualification remain; this proof makes no claim about ambiguous partial writes
or those broader cuts.
