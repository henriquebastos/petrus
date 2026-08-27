---
date: 2026-08-27T03:23:00Z
author: Amp Driver
kind: milestone
related:
  - CV20.DS3
  - CV20.DS3.TS2
  - ES-061
verification:
  - 146 focused document, definition, History, observation, and simulation tests passed
  - quick static and 29 project-structure tests passed
  - producer-backed 15-entry mixed fork parsed, replayed, serialized, and reopened
  - broad gate reached 2,192 passes; only unavailable Docker and Graphviz routes failed
---

# Forkable Net document lineage delivered

## What changed

Petrus Net document v1 now optionally retains exact observation-capture and
simulation-result sources and projects them with manual marking replacements
into one dense parent-linked lineage. Public parsing verifies source bytes,
History, replay, provenance, branch continuity, source coverage, and optional
checkpoints; `resolve_lineage` returns one common navigation sequence.

## Why it matters

Observed production evidence, simulation, and manual exploration no longer
need separate consumer timeline models. Canonical runtime History remains
linear, while the document can preserve an observed sibling and a hypothetical
branch without rewriting the retained source.

## Verification

The focused owner and adjacent producer suites passed 146 tests, project
structure passed 29 tests, and quick static checks passed. The 15-entry owner
fixture contains real Engine capture and simulation outputs and round-trips
byte-exactly. Its SHA-256 is
`63173b9a70e729c42f898eae5b06afeb1e4e3cb0ae643fc303ea50ca8d92fea0`.

The full gate reached 2,192 passes. Seven failures and 256 setup errors were
confined to unavailable Docker-backed provider or Graphviz routes in this orb.

## Follow-up

CV20.DS3 remains Active. Petrus Arx should consume this exact owner contract for
branch-aware navigation, observed-evidence protection, and Save As exploration
before the application-bound Hamsterdan V5 simulation slice.
