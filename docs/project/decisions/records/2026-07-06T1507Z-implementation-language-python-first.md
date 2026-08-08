---
status: Decided
raised: 2026-07-06
decided: 2026-07-06
deciders:
  - henrique (Navigator)
supersedes:
related:
  - docs/project/decisions/records/2026-07-06T1505Z-net-instance-is-a-process.md
---

# Implementation language: Python first, with a language-agnostic base

## Question

Petrus is Python and the Navigator is fastest in Python, but the hermes notebook's bootstrap doc assumed "a composable TypeScript library stack." Which language does Impetus start in?

## Decision

**Python first, with a language-agnostic base** (ratified by the Navigator 2026-07-06). The "port later = rewrite" risk is defused structurally rather than by language choice:

1. Keep the **spec, schemas, and golden traces language-agnostic** from day one (velocitron's own principle: "the spec is the contract; implementations are bindings").
2. The Python implementation then becomes the **reference binding**, not the product identity; a future TypeScript port is a second binding validated by the same golden traces — exactly how the Petrus rebuild validated its TS kernel against the Python engine's traces in one day.
3. Keep Python-only cleverness (e.g. Petrus's `get_type_hints` kwargs extraction) in the binding layer, out of the spec.

This choice also maximizes continuity: the behavioral oracle (MIT Petrus), velocitron's reference implementation, CarlAdam, and Beans are all Python.

## Options Considered

- TypeScript first — better long-run ecosystem alignment for editor/tooling; slower for the Navigator now; loses direct continuity with the Petrus oracle.
- Python only — simplest, but the editor/agent ecosystem pull toward TS will eventually appear.
- Python-first + language-agnostic spec (recommended) — speed now, portability preserved.

## Consequences

- Dev tooling: uv, pytest; package layout and the first spike follow this decision.
- The spec/schema/golden-trace layer is authored as language-neutral artifacts (JSON/markdown) before or alongside the Python binding — treating them as Python internals would silently revoke this decision.

## Review Trigger

Revisit when a second binding (likely TypeScript) becomes concrete — the language-agnostic base is validated the day a second implementation passes the same golden traces.
