---
date: 2026-08-17T05:06:15Z
author: Amp
kind: milestone
related:
  - CV16
verification:
  - focused Hands and Pi runtime tests — 214 passed, 6 qualification skips
  - scripts/check quick — passed
  - scripts/check full — 2180 passed
---

# Corrected the Pi coding workspace boundary

## What changed

The version-1 Hands contract now admits whole-file writes through 1,024
characters while preserving its existing path, NUL, schema, grant, and
publication fences. Pi native operations advertise only the workspace tools
permitted by their exact current attachment grant; the helper still retains
the full closed tool vocabulary for gateway enforcement and installation
probing.

## Why it matters

A production application operation exhausted its finite coding turn while
trying unavailable advertised tools, then could not replace ordinary source
files within the former 256-character write ceiling. The corrected boundary
removes those false affordances without granting shell, test, write, or any
other authority an operation did not already hold.

## Verification

Focused contract and runtime tests exercised the exact 1,024/1,025 write
boundary, NUL rejection, fresh and resumed read-only/coding advertisements,
grant replacement, forged known and unknown methods, invalid advertised tool
sets, and the three shipped static version-1 helper schemas. `scripts/check
quick` passed. `scripts/check full` passed all 2,180 hermetic tests after the
orb's declared Docker and Graphviz prerequisites were made available.

## Follow-up

Application hosts may raise a specific coding operation's finite call budget
within their existing host ceiling. This Petrus change does not alter any
operation's budget, capability grant, authority custody, archive proof, or
publication policy.
