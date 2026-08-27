---
date: 2026-08-27T03:23:00Z
author: Amp Driver
kind: milestone
related:
  - CV20.DS3
  - CV20.DS3.TS1
  - CV20.DS3.TS2
  - ES-061
verification:
  - Petrus scripts/check full passed 2,456 tests and every static and structural gate
  - Arx pnpm check passed 1,144 tests, 49 conformance checks, all static gates, and the production build
  - exact Hamsterdan V5 arrangement, Save As, reopen, manual fork, and hosted simulation append passed in the portal
  - one Docker-backed Petrus PostgreSQL History-store test passed from the Hamsterdan orb
---

# One Petrus Net document and direct-marking lineage delivered

## What changed

Petrus now has one portable file format, `petrus-net-document/version 1`. It
always contains an exact canonical Net definition and may contain portable node
positions and a parent-linked marking lineage. The unreleased inspection,
capture, and simulation-result envelopes and the interim source-anchor,
fact-union, checkpoint, and replay model were removed.

Every observed, manual, and simulated lineage entry has exactly
`id`, `parent`, `provenance`, `marking`, and `metadata`. Each marking is the
complete sparse state for direct navigation. History may be retained in
metadata for diagnosis, but consumers never replay it to discover a step's
state.

## Why it matters

Petrus producers and Arx now read and write one structure. A developer can
arrange a definition, inspect observed state, append a manual hypothesis, and
attach Petrus-computed simulated successors without switching file or timeline
models. A simulated step may have a manual parent: the parent records the
hypothesis and the child records that Petrus computed the successor.

Canonical runtime History remains linear and authoritative for one Instance.
The document lineage is a portable branch graph, not resume or production-
authenticity authority.

## Verification

Petrus's final full gate passed 2,456 tests in 66.73 seconds, including Docker-
backed PostgreSQL and Graphviz routes. The expanded document, History,
observation, simulation, and PostgreSQL selection passed 253 tests.

Arx's final `pnpm check` passed 1,144 tests, 49/49 conformance checks, every
typecheck and static/dependency gate, and the production build. The shared
workspace opened the exact 108-place, 137-transition, 570-arc Hamsterdan V5
document, preserved node arrangement through Save As and reopen, navigated
direct markings, appended and edited a manual child, and appended a bounded
Petrus-hosted simulation below a manual parent. Definition identity remained
`70e3778ec802435a8e57456cc7e4edce04be30b91a6a65e53afa0d122f47e1e2`.

The Hamsterdan orb setup now installs Docker and Graphviz. A real Docker-backed
Petrus PostgreSQL History-store test passed there, removing the earlier
environmental gap.

## Follow-up

CV20.DS3 remains Active for application-bound interactive V5 simulation and
the live semantic/operational join. The next simulation path should let a
person choose an enabled transition, ask Petrus with Hamsterdan's bindings to
compute the successor, and supply hypothetical results at external-effect
boundaries. It must append to the same lineage and must not perform real effects
or invent Arx-local execution semantics.
