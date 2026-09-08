---
date: 2026-09-08T18:20:00Z
author: codex
kind: milestone
verification:
  - Hosted scheduled DST campaign
  - Hosted scripts/check release, parallel and serial suites
  - Independent review of the test repairs
---

# 1 Release validation and test scheduling repairs

Two test-setup repairs restored passing release checks. Production code,
formats, and package version `0.0.0` are unchanged.

The async Worker test now queues both heartbeats before releasing the provider.
The ZeroMQ lost-terminal-reply test uses the normal timeout for its initial
claim and the short deadline for completion. Both preserve the original
behavior assertions. Controlled schedules reproduced each failure, and
independent probes confirmed that incorrect context closure or disabled
completion retries still fail the tests. The focused files passed 29 and 30
tests. The [test debt record](../../../project/debt/items/2026-09-08T0300Z-process-tests-assume-short-wall-clock-budgets.md)
contains the diagnosis and remaining timing concerns.

## 1a Executed checks

On Ubuntu 24.04 with Python 3.14.7:

| Check | Result |
| --- | --- |
| Scheduled DST campaign | Four profiles passed; 451 generated/shrink cases against 304 target examples; 47.659 seconds. |
| Static checks | Ruff lint/format, typing, and structural checks passed. |
| Four-worker suite | 2,595 passed in 139.94 seconds; no skips. |
| Additional serial suite | 2,595 passed in 197.15 seconds; no skips; 17 acceptance tests explicitly deselected. |

The release profile excludes real-provider, real Gondolin guest, and
installation acceptance tests. These results do not qualify those external
integrations. The [manual workflow](../../../../.github/workflows/release-check.yml)
runs the scheduled campaign and release checks with read-only repository
permissions and without provider credentials.
