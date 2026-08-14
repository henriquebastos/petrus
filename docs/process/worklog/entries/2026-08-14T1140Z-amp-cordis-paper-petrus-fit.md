---
date: 2026-08-14T11:40:20Z
author: Amp
kind: milestone
related:
  - ES-052
  - CV16
verification:
  - cordiverse/paper exact checkout and PDF review at 948a07b369c62adb3b12e102458be5c18dfb69b9
  - focused Agenticus catalog, profile, and Pi A2 host tests — 102 passed
  - scripts/check quick
  - scripts/check full — static gates and 2171 passed
  - ES-052 relative Markdown links and git diff whitespace checked
---

# Related the upstream Cordis paper to Petrus

## What changed

Extended ES-052 with an independent review of the upstream Cordis paper, *A
Programming Paradigm for Spatiotemporal Composability*. The exploration now
separates the paper's claims from Petrus interpretations, records source and
license provenance, and maps Context, Component, Fiber, revertible effects,
reactive coeffects, provider identity, hierarchy, isolation, events, rollback,
async inertia, and confluence to the closest useful Petrus relations and their
false equivalents.

The future-execution brief now carries the paper's consequences into the
disposable mount experiment: classify owned acquisitions, borrowed
capabilities, and external emissions; observe provider incarnation without
mutating active snapshots; drain dependents before providers; preserve
verified/unverified cleanup evidence; report cycles and missing mandatory
dependencies; and test independent local permutations without inferring
History replay or failure confluence.

## Why it matters

The paper supports the existing Agenticus Value hypothesis but narrows the
semantics. Cordis is relevant to Petrus as a model for host-local,
dependency-aware composition ownership. It is not a replacement for Petri
causality, canonical append-only History, immutable Episode resolution,
installation authority, or provider-specific Effect and cleanup custody.

The decisive boundary comes from Cordis itself: tracked acquisitions can have
inverses, while externally visible sends and writes are emissions outside
automatic recovery. That aligns with Petrus's explicit compensation and honest
uncertainty posture and prevents a future mount from claiming that History,
Activities, or ambiguous provider Effects were rolled back.

## Verification

The source repository was checked out at exact commit
`948a07b369c62adb3b12e102458be5c18dfb69b9`; its complete three-file tree,
commit metadata, README preprint warning, PDF metadata, relevant sections, and
absence of an explicit license file were inspected. The focused local suites
covering the Agenticus contracts used in the comparison passed all 102 tests.
`scripts/check quick` passed, and `scripts/check full` passed its static gates
and all 2,171 tests. Both ES-052 files have resolving relative Markdown targets
and the resulting diff has no whitespace errors.

## Follow-up

ES-052 remains Paused. The paper adds discriminating probes to Experiment 1 but
does not provide implementation, second-use, or installation-author evidence
needed for promotion. No CV, roadmap item, production API, or plugin framework
was created. A future reactivation should use the pinned preprint as the
historical baseline and review any newer revision as a separate evolution
check.
