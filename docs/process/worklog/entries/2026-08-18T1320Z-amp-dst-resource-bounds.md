---
date: 2026-08-18T13:20:57Z
author: amp
kind: milestone
related:
  - CV19.DS2
verification:
  - UV_FROZEN=1 uv run pytest -q tests/dst (92 passed)
  - all 14 retained petrus-dst-world fixtures replayed exactly
  - UV_FROZEN=1 uv run pytest -q tests/project (29 passed)
  - scripts/check full (2,273 passed)
  - scripts/check release (one run passed both orders; latest run exposed one unrelated Gondolin xdist /tmp race)
  - UV_FROZEN=1 uv build --out-dir /tmp/petrus-dst-v4-dist (supported testing module present in wheel)
---

# Version the DST World for profile-resource bounds

## What changed

The supported defining module now authors `petrus.testing.dst/v4` and
`petrus-dst-world` version 4 artifacts when a scenario supplies `BudgetV4`.
An exact v4 profile reports a side-effect-free detached `ResourceUsage` whose
keys exactly match the artifact's named `profile_resources` limits. The World
samples and journals those gauges before create and after every legal accepted
boundary, fresh load, and abrupt drop. Legacy `Budget` scenarios never invoke
the new door and continue to author strict version 3 artifacts; versions 1
through 3 still decode and replay through the same interpreter.

The public-Engine proof profile accounts for History records/bytes, marking
tokens/bytes, pending in-flight Activities, and pending Dispatch custody. Its
retained green scenario drops a process after a durable Activity request,
measures durable state with no live generation, reloads, reconstructs custody,
and converges. A paired failure sets the History-record ceiling to five: the
real Engine drive accepts four new records after the two-record initial
History, then the World retains that accepted operation and the exact
`profile_resources:retained.history_records` failure.

The green artifact has 14 operations, 39 journal entries, and digest
`sha256:0e1ffac28729a33fe7bb19e4ec52869c150a6a5e8312018419be53c4f2d69baf`.
The retained overage has 3 operations, 10 journal entries, and digest
`sha256:845e62259ae1e18b1ab92f1a2f5c16b1757cea29181bda6e6cd767ce0857b451`.

## Why it matters

Logical action and queue limits did not bound application/profile state hidden
outside the World queue. Version 4 closes that generic gap without teaching
Petrus about Hamsterdan readiness, providers, or any other application model.
The profile owns complete resource definitions and their compatibility digest;
the kernel owns exact key enforcement, deterministic limit selection, failure
retention, and replay.

The compatibility analysis also rejected an in-process watchdog. Threads
cannot terminate a hung production call, and signal injection is not a
portable profile contract. Honest wall-clock containment requires an outer
killable-process runner with acknowledged attempt/operation streaming, so a
parent can report the last committed prefix without fabricating an ordinary
deterministic failure for a call which never returned.

## Verification

Fresh authored v4 artifacts were byte-identical to both retained fixtures.
Their replay route reconstructed fresh public Engine generations and reproduced
the exact operations, resource/checker journal, disposition, failure detail,
and digest. All 14 retained version 1 through 4 fixtures replayed successfully.
Focused DST and project tests passed; the complete and both release-order
suites passed 2,273 tests. The wheel build retained the supported
`petrus/testing/__init__.py` and `petrus/testing/dst.py` modules.

After the final strict-model separation, the current complete suite again
passed 2,273 tests. The latest release wrapper stopped with 2,272 passes when
`test_spawn_failure_removes_runtime_and_operation_directory` compared the
global `/tmp/petrus-g-*` set while another xdist worker held a transient
directory. That path disappeared immediately, the exact failed node passed in
isolation, and no Petrus Motus/Gondolin files changed in this slice. This is an
unrelated release-gate reservation rather than DST evidence.

## Follow-up

CV19.DS2 remains Active. The next compatibility slice is process-isolated
wall-clock containment with acknowledged-prefix evidence. The broader
delivery/Dispatch/lifecycle/transaction cut matrix and deterministic
LocalDispatch provider-time design also remain; v4 does not weaken SQLite's
provider-clock and cross-process serialization ownership.
