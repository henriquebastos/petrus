---
date: 2026-08-18T11:37:50Z
author: Amp
kind: milestone
related:
  - CV19.DS2
verification:
  - UV_FROZEN=1 uv run pytest -q tests/dst (73 passed)
  - eight retained World replay routes (all pass with exact dispositions and journal digests)
  - retry replay (quarantined; 18 operations; 30 journal entries; 11 checker evaluations)
  - scripts/check full (2,254 passed)
  - scripts/check release (2,254 passed in both orders; 17 expected alternate-order deselections)
---

# Deterministic LocalDispatch retry reconstruction and exhaustion

## What changed

A fifth exact public-Engine profile under `tests/dst/` now composes the real
LocalDispatch retry provider into the supported World interpreter. One Activity
with a two-attempt policy is claimed at epoch 1 and reports a classified
retryable failure with zero backoff. The scenario abruptly drops the process
after LocalDispatch admits the retry, then constructs a fresh Engine,
LocalDispatch session, and Worker through public doors.

The replacement claims epoch 2 with the exact recorded activity, input,
policy, correlation, and idempotency, while the replacement handler performs no
second `prepare`. A second retryable failure exhausts the policy and lands one
canonical `ActivityFailed` plus `FiringFailed`, with no business projection. An
independent checker continuously bounds terminal facts by authored failures and
compares the detached provider claim identities across epochs.

## Why it matters

This proves that retry decisions stay owned by production LocalDispatch rather
than being recreated in the test World. Because both policy backoff and
`retry_after` are exactly zero, the proof is hermetic and requires no real
sleep, private SQLite mutation, or provider-clock substitution. Delayed
backoff, lease expiry, and provider-time advancement remain explicitly
unclaimed.

## Verification

The focused DST suite passed 73 tests, and all eight retained fixtures replayed
through `tests.dst.replay_world` with exact outcomes and dispositions. The new
24,604-byte fixture ended `quarantined` across 18 operations and 30 journal
entries, including 11 checker evaluations, with digest
`sha256:8158a70525b02afd7fb705ddec9ffc62a66d8c4ec6c9c0872062d36a05402392`.
Source lint, format, type, and all 19 architecture-rule fixtures passed.
The complete `scripts/check full` gate passed 2,254 tests. The release gate
passed the same 2,254 tests in both orders, with 17 intentional deselections in
the alternate release profile.

## Follow-up

CV19.DS2 remains Active for delayed retry/provider time, broader delivery and
transaction cuts, profile-retained-data bounds, and wall-clock watchdog
qualification.
