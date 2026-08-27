# CV20.DS3.TS2 Experience Report

## Recommendation

**Pass — accepted.** Petrus Net document v1 now uses one direct-marking lineage
for observed, manual, and simulated state. Each entry is independently
navigable without History replay. The earlier source-anchor, fact-union, and
checkpoint design was removed before release.

## Acceptance evidence

| Contract | Evidence | Result |
| --- | --- | --- |
| One portable format | Definition-only, arranged, observed, simulated, manual, and mixed-fork fixtures use `petrus-net-document/version 1`; the old inspection, capture, and simulation-result envelopes are absent | Pass |
| One entry shape | Every provenance uses exactly `id`, `parent`, `provenance`, `marking`, and `metadata` | Pass |
| Dense lineage | Entry ids equal indexes, entry zero is the sole root, later parents are smaller, and head names an existing entry | Pass |
| Direct navigation | Every entry carries one complete admitted sparse marking; History is optional metadata and is never replay authority | Pass |
| Per-entry provenance | Observed means projected from a real History state, manual means person-authored marking, and simulated means Petrus-computed successor; a manual entry may parent a simulated entry | Pass |
| Producer materialization | Engine observation produces a seven-entry all-observed document; hosted simulation produces an eight-entry all-simulated document | Pass |
| Strict owner contract | Positive inspection/lineage/observation/simulation fixtures and negative marking/lineage fixtures round-trip or refuse exactly | Pass |
| Arx consumption | One Arx document model arranges, navigates, manually forks, saves/reopens, and appends a Petrus-hosted simulation below the selected marking | Pass |

## Automated and operational evidence

- Petrus `scripts/check full` passed all static, format, structural, and test
  gates with **2,456 tests passed in 66.73 seconds**.
- The expanded Petrus document, History, observation, simulation, and
  PostgreSQL selection passed **253 tests**.
- Arx `pnpm check` passed all typechecks, lint/style/dependency checks,
  **1,144 tests**, **49/49 conformance checks**, and the production build. Node
  26 produced the existing warning against the repository's Node 24 pin; Vite
  produced the existing large-chunk advisory.
- The exact Hamsterdan V5 definition-only document opened on the shared Arx
  canvas with 108 places, 137 transitions, and 570 arcs. Arrangement survived
  Save As and reopen with definition identity
  `70e3778ec802435a8e57456cc7e4edce04be30b91a6a65e53afa0d122f47e1e2`.
- Browser QA selected complete markings, appended and edited a manual child,
  and appended an implementation-free Petrus simulation below a manual parent.

## Review and debt

The public model remains in `petrus.impetus.net_document`. Observation and
simulation call that owner rather than creating alternate envelopes. Runtime
History remains canonical and linear. The portable lineage deliberately
repeats complete markings so every consumer has the same navigation path.

No compatibility or migration debt is accepted because no format has been
released. File growth from repeated markings is accepted for the current
design and can be reconsidered only with measured evidence.

## Current limit and next movement

The current `implementation-free-v1` simulator is a detached pure-Net profile.
It cannot execute Hamsterdan V5 because V5 has handlers and exceeds the
profile's transition and arc bounds. This is not a Petrus Engine limitation.

CV20.DS3 remains Active for application-bound V5 simulation. That follow-up
will let a person choose an enabled transition from any selected marking, ask
Petrus with Hamsterdan's real bindings to compute the successor, and supply
hypothetical results at external-effect boundaries. Each returned successor
will append as `simulated`, including when its parent is manual.
