---
date: 2026-08-26T12:00:00Z
author: claude-driver
kind: milestone
related:
  - ES-059
  - ES-056
verification:
  - UV_FROZEN=1 uv run pytest -q docs/project/exploration/es-059-mit-dataflow-functional-programming-analysis/experiments — 117 passed (27 v1 + 38 case-table + 52 guarded-net)
  - ruff check / ruff format --check over the experiments tree — clean (36 files)
  - ty check over both new experiments' source modules (with sibling search paths) — clean
  - byte-identity asserted in tests, case-table experiment — canonical Net v3 and fixture History JSONL equal to the completed slice's retained golden and artifact
  - guarded-net experiment — record-for-record History parity against a v1 run over the identical trace; overlapping-guard and silent-stall counterexamples executed
---

# ES-059 decision-structure follow-up experiments executed

## What changed

Two bounded experiments beside the completed typed-flow vertical slice test
where the readiness decision's structure should live, dispatched as parallel
sessions and adversarially reviewed:

- **algebraic-decision-table** (promising): the ladder as an ordered,
  first-match-wins case table lowering to the same single transition. Both
  stretch targets landed — canonical Net v3 bytes and the 24-step fixture's
  canonical History are byte-identical to the completed slice, so the richer
  source provably changes nothing at the runtime IR. A 10,368-point sweep
  matches `route_ci` with zero mismatches; totality is statically checked via
  an `otherwise` sentinel; each rung owns a source-map entry. The named cost
  is the `normalize` classify/commit seam, where sequential state-dependence
  resists tabulation.
- **guarded-decision-net** (mixed): one guarded transition per rung makes the
  ladder visible in canonical topology and closes v1's Ignored-invisibility
  limit — absorption becomes a named durable firing. The price: 9→13
  transitions, 28→40 arcs, ~10× guard-evaluation amplification, and the
  decisive counterexample that overlapping guards are refused by nothing and
  reproducibly settled by the Engine's selection policy, while a
  non-exhaustive rung set strands observations silently. Exclusivity and
  exhaustiveness became executable-but-unprovable authoring obligations.

The ES-059 index records both results and the combined lesson: keep one
durable transition per decision and enrich the source, not the topology.
Boundary held throughout — the completed slice, `src/petrus`, `spec`, and
normal `tests` are untouched; the new work reuses the slice's modules
read-only with collision-free module names.
