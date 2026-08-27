---
date: 2026-08-27T02:41:00Z
author: Amp Driver
kind: milestone
related:
  - CV20.DS3
  - CV20.DS3.TS1
  - ES-061
verification:
  - 61 focused portable-document and canonical-definition tests passed
  - quick static checks passed
  - exact owner fixtures passed independently in Arx
  - browser-saved Hamsterdan V5 document retained canonical definition identity
---

# Portable Net document foundation delivered

## What changed

Petrus now owns the strict `petrus-net-document` version 1 foundation. Every
document carries one canonical Net definition v3 and may carry a partial or
complete position-only view. Production APIs parse, project, serialize, and
compute definition identity; the spec and positive/negative fixtures pin the
cross-language contract.

## Why it matters

Arx and later consumers can persist arrangement without changing semantic Net
identity or inventing an editor-owned workspace format. This is the first
delivered part of ES-061's one-document direction.

## Verification

The focused owner suites passed 61 tests and the quick static gate passed. Arx
copied both owner fixtures byte-for-byte and completed the exact Hamsterdan V5
open, arrange, Save As, close, and fresh-reopen route. Petrus strictly parsed
and byte-fixed the resulting 198,551-byte document while retaining identity
`70e3778ec802435a8e57456cc7e4edce04be30b91a6a65e53afa0d122f47e1e2`.

The full Petrus gate could not complete in this orb because Docker-backed
provider and Graphviz setup were unavailable: 2,169 tests passed, with seven
failures and 256 setup errors confined to those infrastructure routes.

## Follow-up

CV20.DS3 remains Active. Its next Petrus story adds ES-061's optional strict
flat lineage; this foundation continues to refuse lineage fields until that
owner contract lands.
