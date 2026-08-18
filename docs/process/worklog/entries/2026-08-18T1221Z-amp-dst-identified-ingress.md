---
date: 2026-08-18T12:21:00Z
author: Amp
kind: milestone
related:
  - CV19.DS2
verification:
  - UV_FROZEN=1 uv run pytest -q tests/dst (79 passed)
  - ten retained World replay routes (all pass with exact dispositions and journal digests)
  - identified-ingress replay (external_wait; 15 operations; 26 journal entries; 10 checker evaluations)
  - scripts/check full (2,260 passed)
  - scripts/check release (2,260 passed in both orders; 17 expected alternate-order deselections)
---

# Deterministic identified-ingress redelivery and conflict recovery

## What changed

A seventh exact public-Engine profile under `tests/dst/` now drives identified
external events through the production source-delivery door. The scenario
accepts one identity, abruptly drops the process after its durable canonical
firing, loads a fresh Engine, and proves that exact redelivery acknowledges the
prior occurrence without appending or duplicating output. Equal data under a
different identity remains a second external fact.

Changed content under the first identity is refused by production ingress.
Because a failed writing door correctly poisons that Engine generation, the
profile observes only unchanged durable JSONL History and the last legal
detached marking at that boundary, then explicitly drops and reloads before an
exact redelivery proves recovery. The independent checker derives accepted
identity/value authority and expected dispositions solely from authored
delivery attempts.

## Why it matters

This closes the identified source-ingress gap without replacing Petrus identity
or projection semantics. It proves acceptance, duplicate acknowledgement,
changed-content refusal, equal-payload distinctness, process reconstruction,
and poisoned-generation recovery through public Engine doors and the one World
interpreter. No production API, private runtime handle, artifact version, real
sleep, or test-owned source semantics were added.

The investigation also confirmed that nonzero LocalDispatch retry time is not
yet a valid DST slice: SQLite intentionally owns provider time and
serialization, and no public deterministic provider-time seam exists. The
maintained v3 contract now records that compatibility boundary rather than
substituting the Engine clock or mutating private SQLite rows.

## Verification

The focused DST suite passed 79 tests, and all ten retained fixtures replayed
through `tests.dst.replay_world` with exact outcomes and dispositions. An
independent fresh build was byte-identical to the retained 16,881-byte fixture
(SHA-256 `1164bf57dda335890ea6efce863a9f384a9346aa4f2da89bfba0056a74128fc9`).
The route ended `external_wait` across 15 operations and 26 journal entries,
including 10 checker evaluations, with journal digest
`sha256:e0223b0e0dd5ce6ce964cb9a72e38a9370f7f6b8a38d9571cdc1179e9a03d8bc`.
Source lint, format, type, and architecture checks passed. The complete full
gate and both release orders passed 2,260 tests, with 17 intentional
deselections in the alternate release profile.

## Follow-up

CV19.DS2 remains Active for broader delivery/transaction cuts, an accepted
provider-time design for delayed LocalDispatch retry, profile-retained-data
bounds, and wall-clock watchdog qualification.
