---
date: 2026-08-09T12:00:00Z
author: Amp
kind: milestone
related:
  - CV16.DS11
verification:
  - focused Pi A2 host conformance — 22 passed
  - scripts/check full — 2020 passed
  - scripts/check release — 2020 passed, then 2020 passed and 17 external qualification tests deselected
---

# Qualified the scripted Pi A2 Local host lifecycle

## What changed

Petrus now exposes a data-only scripted-conformance composition for the Pi A2
Local host lifecycle. The route owns its script interpreter and exact local
territory provider, separates scripted readiness from external installation
probing, cleanup-gates body publication, replays terminal work before readiness
or authority, and classifies a real killed-host restart without redispatch.

README and profile documentation now state the exact support matrix. Only the
scripted Local host lifecycle is supported; authenticated Pi/model/provider
execution and other binding targets remain experimental and qualification-only,
while unqualified and unsupported cells retain those classifications.

## Why it matters

CV16 now has one honest host product boundary without turning catalog presence
into a provider support claim, exposing arbitrary runtime collaborators, or
moving authority and execution ownership out of their established components.

## Verification

The focused host suite passed 22 tests, including scoped Hands, secret-free
durable stores, cleanup-gated output/Continuation/workspace bodies, terminal
replay, and a real subprocess `SIGKILL` followed by restart-indeterminate
classification. `scripts/check full` passed 2020 tests. `scripts/check release`
passed 2020 tests in its parallel run and then 2020 tests with 17 external
qualification tests explicitly deselected in fixed order.

The release route did not execute or qualify external installations,
authenticated providers, or Gondolin acceptance.

## Follow-up

Power-loss durability, orphan local-territory reconciliation, authenticated Pi
or provider support, and support for any other Agenticus profile require their
own bounded evidence. Restart residue currently fails host close closed as
`host-cleanup-uncertain`; it is not misreported as clean.
