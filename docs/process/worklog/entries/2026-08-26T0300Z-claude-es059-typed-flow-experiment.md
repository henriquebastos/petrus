---
date: 2026-08-26T03:00:00Z
author: claude-driver
kind: milestone
related:
  - ES-059
  - ES-056
verification:
  - UV_FROZEN=1 uv run pytest -q docs/project/exploration/es-059-mit-dataflow-functional-programming-analysis/experiments/typed-flow-vertical-slice — 27 passed
  - focused existing contract suites (dsl, net-definition, execution, engine, lifecycle scopes, history, persistence, dot, exploration identity) — 219 + 125 passed unchanged
  - full deterministic seed-1729 suite on four workers with --forbid-skips — 2,403 passed; 3 pre-existing host-environment failures reproduced identically on the clean baseline with the experiment stashed
  - ruff check/format, ty check (experiment sources), ast-grep scan — clean
  - run_experiment.py evidence bundle — byte-identical uninterrupted vs restarted canonical History; 0 unattributed records of 147
---

# ES-059 typed functional flow vertical slice executed

## What changed

The Navigator-authorized ES-059 experiment is implemented, adversarially
reviewed, and complete under
`docs/project/exploration/es-059-.../experiments/typed-flow-vertical-slice/`.
One Hamsterdan-shaped readiness slice is authored as a typed, functional
value (`machine`/`on`/`await_event`/`decide`/`choose`/`effect`/`low_level`),
lowered deterministically into current canonical Net v3 (14 places, 9
transitions, 28 arcs, byte-stable goldens), executed through the real
`Engine`, `JsonlHistoryStore`, scoped generations, and an interrupted-restart
route, and attributed record-by-record back to authored source through a
deterministic source-map sidecar and explained-History projection.

All fourteen completion conditions of the experiment plan pass; the
Experience Report classifies the result **promising** and names its limits
(fake providers, host-disciplined state baton, no direct-authoring twin).
Two independent adversarial reviews (Claude and gpt-5.6-terra via Codex)
produced twenty-one findings; every confirmed defect was fixed and the weaker
evidence claims restated honestly — the review rounds and resolutions are
recorded in the report. ES-059's index status reflects the executed result;
promotion toward ES-056 remains a Navigator decision.

Boundary held: no change under `src/petrus`, `spec/`, or normal `tests/`;
Hamsterdan was never imported.
