---
date: 2026-08-13T20:37:04Z
author: Amp
kind: milestone
related:
  - ES-052
  - CV16
verification:
  - git ls-remote pinned deepseek-ai/deepseek-harness master at 47f943859bef60e4160492346772ded9b24f765a
  - focused Agenticus catalog, profile, and Pi A2 host tests — 102 passed
---

# Compared DeepSeek Harness plugin composition with Agenticus

## What changed

Created ES-052 as a source-grounded architecture comparison of DeepSeek
Harness's Cordis plugin tree and Petrus Agenticus's descriptor, Catalog,
authority, profile, adapter, and host-composition boundaries. The exploration
separates mechanisms worth copying, constraints requiring adaptation, and
patterns Agenticus should reject. It also records the MIT and vendored Cordis
provenance relevant to any future source reuse.

## Why it matters

The comparison confirms a narrower opportunity than “make everything a
plugin.” Agenticus already has stronger typed compatibility, explicit host
selection, authority custody, and immutable Episode plans. Its plausible gap is
an owned reversible executable mount between a resolved snapshot and
host-specific construction—not dynamic package discovery or ambient service
injection.

## Verification

The external source was pinned before claims were recorded. Focused local tests
were then run over the exact Agenticus contracts used by the comparison: 102
tests passed in 4.47 seconds. All relative Markdown links in ES-052 resolve and
`git diff --check` reports no whitespace errors. ES-052 contains per-claim
provenance, confidence boundaries, permanent source links, and the proposed
discriminating experiment.

## Follow-up

ES-052 remains a candidate in Exploration. Promotion would require Navigator
direction and a bounded Technical Story; no implementation or roadmap promise
was created by this milestone.
