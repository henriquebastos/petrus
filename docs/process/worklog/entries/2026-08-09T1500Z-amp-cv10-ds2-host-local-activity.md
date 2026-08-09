---
date: 2026-08-09T15:00:00Z
author: Amp
kind: milestone
related:
  - CV10.DS2
  - CV10.DS1
verification:
  - exact host-local Gondolin Activity acceptance, 2 passed
  - complete Codex runtime file, 48 passed after final fence additions
  - scripts/check full, 2031 passed
  - scripts/check release, 2031 passed then 2031 passed with 17 external routes deselected
---

# Qualified host-local Activity custody over one Episode territory

## What changed

A private Codex Gondolin Activity adapter now accepts only strict versioned JSON
data while retaining the connection, Episode Attachment, provider, and runtime
adapter as host-owned collaborators. Stable Activity idempotency names the
runtime operation; attempt identity never names the territory.

The Inline witness fails once before runtime admission and succeeds on its
second formal Motus attempt. Both attempts have distinct custody epochs and the
same runtime operation, attachment, and Gondolin lease. Missing or malformed
fences and stale initial custody fail before runtime start, and unexpected
admission diagnostics are reduced to a safe code.

## Why it matters

Petrus now proves that Episode-owned territory and formal Activity retry are
compatible without making live provider objects Activity data. The bounded
result preserves the architecture while avoiding a false claim that a closure
can survive Worker process migration.

## Verification

Both exact Activity nodes passed. The complete Codex file passed with `48
passed` after the final review-driven fence matrix. Static checks passed.
`scripts/check full` produced `2031 passed`; `scripts/check release` produced
`2031 passed` in parallel and `2031 passed, 17 deselected` in fixed order.

External installation, authenticated provider, real Gondolin, and
multi-process Worker routes were not executed and are not claimed green.

## Follow-up

Remote Worker reconstruction needs a durable host request/reconciliation
protocol. Mid-execution custody loss must define publication precedence before
heartbeat-driven migration can be safe. Retained territory custody still needs
durable transfer and orphan reconciliation.
