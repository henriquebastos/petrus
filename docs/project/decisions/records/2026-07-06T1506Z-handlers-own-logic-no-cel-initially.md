---
status: Superseded
raised: 2026-07-06
decided: 2026-07-06
deciders:
  - henrique (Navigator)
supersedes:
superseded_by: docs/project/decisions/records/2026-07-07T1600Z-arc-filters-and-guards-cel-or-named-both-pure.md
related:
---

# Transition–handler decoupling is the load-bearing seam; logic is code, no CEL initially

> **Superseded 2026-07-07** by [DR arc-filters-and-guards-cel-or-named-both-pure]
> after the ES-003 comparison: the "no CEL initially" clause is reversed — arc
> filters and guards now carry inline CEL *or* a named symbol (both pure). The
> load-bearing core of this record survives intact in the new one: the
> transition–handler seam remains central, and the named-symbol escape hatch
> guarantees ordinary code is always available, so the "bypass our DSL" concern
> stays answered.

## Question

The cross-source analysis surfaced two related forks: velocitron centers the design on arcs carrying CEL predicates (sandbox-safe, cross-language expressions), while hermes/Petrus keep arc inscriptions minimal and put cross-token logic in guards and handlers. Where does logic live, and in what form?

## Decision

- **Arcs are first-class but not the center.** What made Petrus work in production was that **transitions decouple from their side-effect implementations (handlers)** — that seam is what glued Temporal activities to the net, and it is the seam Impetus builds around.
- **Transitions, handlers, and guards own the logic**, written as ordinary, ideally reusable, code.
- **No CEL (or similar expression language) initially.** Matt is interested in CEL; the Navigator's position: "if we don't give people an imperative structure to bypass our design or DSL limitations, they just won't use the tool."

## Rationale

Production evidence over elegance: the handler-binding seam is the proven extension point (Petrus → Temporal activities; velocitron itself says "net = coordination, handlers = behavior"). An expression language on arcs adds a second, sandboxed place where logic lives — power users will hit its ceiling and leave. Code-first guards/handlers keep the escape hatch built in. This is also consistent with hermes ADRs 0003 (transitions have bindings, not kinds), 0018/0019 (inscriptions carry type+cardinality only; guards own cross-token logic), and 0021 (schema declares symbols, implementations bind).

## Options Considered

- CEL predicates on arcs (velocitron) — deferred, not rejected forever: valuable for cross-language portability and sandboxing when nets travel between runtimes.
- Hybrid (inscriptions minimal + optional predicate handlers) — effectively what hermes 0018/0019 already decided; adopted.

## Consequences

- The binding layer (symbol → implementation mapping) is a core design surface, not an integration detail.
- The spec must keep predicates/guards as *named symbols* so a CEL adapter could bind them later without schema changes (velocitron's ADR 0010 adapter-protocol idea remains compatible).
- This position should be discussed with Matt as part of the upstream spec alignment.

## Review Trigger

Revisit when nets need to travel between heterogeneous runtimes (cross-language guard portability) or when a sandboxing requirement appears.
