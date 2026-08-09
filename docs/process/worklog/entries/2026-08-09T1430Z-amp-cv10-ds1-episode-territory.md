---
date: 2026-08-09T14:30:00Z
author: Amp
kind: milestone
related:
  - CV10.DS1
  - docs/project/decisions/records/2026-08-09T1400Z-episode-owns-independent-execution-territory.md
verification:
  - exact hermetic Codex A3 Gondolin lifecycle witness, 1 passed
  - focused Codex/profile/Episode/Gondolin suite, 132 passed and 1 opt-in live route skipped
  - scripts/check full, 2029 passed
  - scripts/check release, 2029 passed then 2029 passed with 17 external routes deselected
---

# Qualified one Episode-owned Gondolin territory lifecycle

## What changed

CV10 now records that independent environment custody belongs to one bounded
Episode or host operation, not to each Activity attempt. The Codex A3 profile
adds `topology.episode-collocated` while retaining its v1
`topology.ephemeral-collocated` compatibility offer.

The hermetic Codex A3 Gondolin witness now runs one failed runtime operation,
its replacement operation, and a native continuation resume through the same
Episode Attachment and exact lease. A reconstructed provider observes that
lease, the final archive carries a public workspace canary without private
authority or rollout state, and exact-identity clean evidence plus lookup prove
destruction.

## Why it matters

Independent custody no longer implies excessive per-attempt ephemerality.
Workspace and runtime locality survive bounded replacement work, while provider
identity remains outside canonical Activity and Net semantics and settlement
still fails closed on uncertain cleanup.

## Verification

The exact lifecycle node passed. The focused Codex, profile, Episode Attachment,
and Gondolin provider files produced `132 passed` plus one expected skip for the
opt-in real Gondolin route. `scripts/check quick` passed for touched Python
paths. `scripts/check full` produced `2029 passed`; `scripts/check release`
produced `2029 passed` in parallel and `2029 passed, 17 deselected` in fixed
order.

The deselected or skipped real Gondolin, external installation, and
authenticated provider routes were not executed and are not claimed green.

## Follow-up

Live Gondolin/provider qualification needs external authority. Formal Motus
Activity retry and worker-reconstruction integration remains separate from this
runtime-operation witness. Retained territory settlement requires durable
custody transfer and orphan reconciliation before it can be supported.
