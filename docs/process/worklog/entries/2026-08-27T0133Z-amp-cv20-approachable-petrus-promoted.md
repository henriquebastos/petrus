---
date: 2026-08-27T01:33:24Z
author: Amp
kind: milestone
related:
  - CV20
  - CV20.DS1
  - CV20.DS2
  - CV20.DS3
  - CV20.DS4
  - CV20.DS5
  - ES-056
  - ES-061
verification:
  - UV_FROZEN=1 uv run pytest -q tests/project — 29 passed
  - focused ES-061 plus exploration identity suite — 88 passed
  - scripts/check quick — passed
  - 26 changed-surface local Markdown links checked; 0 missing
---

# CV20 Approachable Petrus promoted

## What changed

The Navigator promoted ES-056's single end-to-end adoption Candidate as
CV20 — Approachable Petrus. The roadmap now holds five Planned Delivery
Stories for one-file first motion, expressive flow authoring, live
understanding, generated authoring/examples, and approachable effects/agents.

ES-061 completed Exploration and promoted specifically to CV20.DS3. Its
accepted portable definition/view/lineage semantics remain distinct from the
public protocol, Arx V5 arrangement, live correlation, and application-bound
execution work still required in Delivery.

No Delivery Story became Active, and no runtime, protocol, release, Arx, or
Hamsterdan production behavior changed at promotion.

## Why it matters

Petrus now has one roadmap owner for the complete progressive developer
journey instead of separate Values that reproduce authoring, runtime, and
presentation seams. Promotion keeps the original evidence honest: AX27–AX29
and the application acceptance cases are carried into their owning Delivery
Stories rather than being relabeled as passed.

## Verification

All 29 project structural tests and the 88-test focused ES-061/exploration
identity suite passed. The repository quick gate passed, 26 local Markdown
links on changed surfaces resolved, and `git diff --check` was clean before
history recording. The complete suite was not repeated for this documentation-
only promotion; the preceding ES-061 evidence run passed 2,406 tests in its
Docker/Graphviz-capable orb, while this orb cannot execute those providers.

## Follow-up

CV20.DS1's first general movement is AX28, which must measure the exact
one-file-to-first-motion gap before a public facade is designed. CV20.DS3's
portable-document and static Hamsterdan V5 arrangement slice may be expanded
independently; its live-runtime join waits for DS1's concrete consumer.
