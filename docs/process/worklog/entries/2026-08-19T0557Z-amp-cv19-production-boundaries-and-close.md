---
date: 2026-08-19T05:57:09Z
author: amp-driver
kind: milestone
related:
  - CV19.DS4.TS3
  - CV19.DS4
  - CV19
verification:
  - uv run python -m tests.dst.boundaries --report /tmp/petrus-dst-boundaries.json — 6 profiles passed, 5,397-byte report, 7.1 seconds
  - uv run python -m tests.dst.campaign --tier scheduled --campaign-id 2026-W34-cv19-final --report /tmp/petrus-dst-campaign-cv19-final.json — 304 targets, 457 cases, 8,051-byte report, 37.7 seconds
  - uv run pytest -q tests/dst --forbid-skips — 218 passed
  - uv run pytest -q tests/project — 29 passed
  - scripts/check full — 2,406 passed
  - scripts/check release — 2,406 passed in bounded-parallel and fixed-serial orders
---

# CV19 closed with complementary real-boundary evidence

## What changed

The final CV19 operation now selects six existing evidence owners in one
bounded child: deterministic Dispatch-refusal crash/load, real joined-
transaction server abort, real post-commit PostgreSQL/Absurd reconstruction,
Worker SIGKILL and lease redelivery, and two ZeroMQ dispatch-server death/
restart routes. Its small report names exact nodes, cuts, recoveries, claims,
selected/deselected profiles, bounds, runtime identity, and unmodeled behavior.

The operation neither copies real fault mechanics into World nor promotes
nondeterministic process evidence into replay artifacts. It explicitly states
that connection drop is not authority-process kill and that actual authority
SIGKILL during an open joined transaction remains unmodeled.

## Why it matters

CV19 now has one coherent, self-contained `tests/dst` operating surface for
ordinary generated tests, larger seed-addressed campaigns, exact failed-
artifact triage/promotion, and complementary production-boundary qualification.
Petrus owns the scheduler and replay kernel; exact owner tests retain authority
for PostgreSQL, Absurd Worker, and ZeroMQ behavior; applications retain their
domain worlds and independent oracles.

## Verification

The final scheduled campaign selected all four generated profiles and passed
304 accepted-example targets with 457 recorded generated/shrink cases. The
real-boundary operation selected and passed all six routes. Ordinary DST,
project coherence, full, and both release orders passed as listed in
frontmatter.

A focused independent acceptance review confirmed that DS4's transaction cut,
actual process restart, and Worker/transport recovery obligations can be
satisfied by distinct routes. Requiring authority SIGKILL during the open
transaction would be a stronger future contract, not a condition silently
added at closure.

## Follow-up

No follow-up is required to satisfy CV19. Database power loss/failover,
authority SIGKILL during an open transaction, nonlocal network partitions,
live providers, credentials, and application-specific authority remain
explicitly unmodeled and should become new scoped work only when a concrete
need justifies them.
