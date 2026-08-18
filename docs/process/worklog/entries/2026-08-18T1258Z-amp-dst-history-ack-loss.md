---
date: 2026-08-18T12:58:00Z
author: Amp
kind: milestone
related:
  - CV19.DS2
verification:
  - UV_FROZEN=1 uv run pytest -q tests/dst (85 passed)
  - twelve retained World replay routes (all pass with exact dispositions and journal digests)
  - History acknowledgement-loss replay (converged; 15 operations; 25 journal entries; 9 checker evaluations)
  - scripts/check full (2,266 passed)
  - scripts/check release (2,266 passed in both orders; 17 expected alternate-order deselections)
---

# Deterministic post-commit History acknowledgement loss

## What changed

A ninth exact public-Engine profile under `tests/dst/` now models the accepted
side of an ambiguous History append. Its adapter delegates `ActivityCompleted`
to the production `JsonlHistoryStore`, observes durable acceptance, and then
raises as if the acknowledgement were lost. The writing Engine correctly
poisons while canonical History remains one record ahead of its in-memory
Instance.

The World observes only detached durable records at that legal boundary,
abruptly drops the ambiguous generation, and reconstructs through public
`Engine.load`. The replacement completes projection from the already accepted
terminal without another external terminal delivery or handler preparation. An
independent checker uses the adapter's post-delegate callback as acceptance
evidence and bounds canonical terminal/projection facts by authored delivery.

## Why it matters

Together with the existing pre-commit refusal route, this proves both sides of
the terminal History ambiguity boundary. Recovery follows durable authority
rather than the failed caller's interpretation, without exposing private
runtime state, modifying production History, or inventing a maybe-state where
the adapter can distinguish acceptance.

## Verification

The focused DST suite passed 85 tests, and all twelve retained fixtures replayed
through `tests.dst.replay_world` with exact outcomes and dispositions. The new
12,272-byte fixture ended `converged` across 15 operations and 25 journal
entries, including 9 checker evaluations, with journal digest
`sha256:b69cd6760d3a1818f4cbfcc5f531d7ad3c970b0e383c5b5ba0abd62a0ff47c92`.
Source lint, format, type, and architecture checks passed. The full gate and
both release orders passed 2,266 tests, with 17 intentional deselections in the
alternate release profile.

## Follow-up

CV19.DS2 remains Active for broader delivery/transaction cuts, an accepted
provider-time design for delayed LocalDispatch retry, profile-retained-data
bounds, and wall-clock watchdog qualification.
