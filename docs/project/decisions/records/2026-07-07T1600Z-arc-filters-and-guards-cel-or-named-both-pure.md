---
status: Decided
raised: 2026-07-07
decided: 2026-07-07
deciders:
  - henrique (Navigator)
supersedes: docs/project/decisions/records/2026-07-06T1506Z-handlers-own-logic-no-cel-initially.md
related:
  - docs/project/decisions/records/2026-06-21T1724Z-hermes-adr-0018-arc-inscriptions-simple-guards-own-cross-token-logic.md
  - docs/project/decisions/records/2026-06-21T1729Z-hermes-adr-0019-arc-inscriptions-do-not-bind-argument-names.md
  - docs/project/decisions/records/2026-07-06T1506Z-handlers-own-logic-no-cel-initially.md
  - docs/project/decisions/records/2026-07-07T1610Z-purity-invariant-and-projection.md
  - docs/project/decisions/records/2026-07-07T1620Z-aggregate-token-type-single-type-per-token.md
---

# Arc filters and guards carry CEL or a named symbol; both are pure

## Question

ES-003 compared arc-inscription semantics across academic CPN, Petrus,
velocitron, and the Impetus spec. Two forks were live: how expressive should an
input arc be (velocitron's `{type, predicate, mode}` with inline CEL vs Impetus
"type + cardinality only, all logic in guards"), and in what form does logic
live? [DR handlers-own-logic-no-cel-initially] had deferred CEL. This record
revisits that after the comparison.

## Decision

- **Arcs gain an optional `filter`.** An input arc inscription expresses token
  color/type and cardinality *plus* an optional **filter**: a pure, single-token
  boolean that selects which tokens of the declared color the arc admits. The
  filter sees exactly **one** token — the one passing through the arc — which
  may itself be an aggregate color carrying nested typed data
  [DR aggregate-token-type]. This narrows [ADR 0018]'s "type + cardinality —
  nothing more" to "type + cardinality + optional pure single-token filter".
- **Filters and guards share encodings: inline CEL or a named symbol.** Either
  slot may be written as an inline CEL expression (Common Expression Language,
  `google/cel-spec` — non-Turing-complete, sandboxed, ported across languages)
  or bound to a **named symbol** resolved by the binding layer. CEL is the
  inline sugar for trivial cases; named symbols carry reuse and logic too complex
  for CEL. This reverses the "no CEL initially" clause of
  [DR handlers-own-logic-no-cel-initially] while keeping that DR's load-bearing
  core intact: the named-symbol escape hatch (ordinary reusable code) remains in
  both slots, so power users never hit a DSL ceiling with no way out.
- **The filter/guard distinction is scope, not encoding.** A **filter** is
  arc-level and sees one token (it prunes each arc's token selection *before* the
  binding cross-product). A **guard** is transition-level and sees the full
  binding across all arcs (it gates *after* selection); cross-token correlation
  and joins live here, in both Impetus and velocitron — a single-token filter
  cannot express a join. This preserves [ADR 0018]'s "correlation lives in
  guards" boundary unchanged.
- **Both filters and guards are pure.** They read tokens and return a boolean
  with no side effects and no external calls. CEL is pure by construction; named
  filter/guard symbols must be pure by contract. All impurity lives in handlers;
  external state enters the net only by projection
  [DR purity-and-projection]. This is a deliberate divergence from velocitron,
  which permits impure guards.
- **Filter and weight apply to all input arc modes.** consume, read, and inhibit
  arcs all accept a filter and a weight, for consistency over special-casing. An
  **inhibit** filter gates on the *absence of a matching token* (weighted
  inhibitors match the Petrus `is_satisfied` "count < weight" rule; this diverges
  from velocitron, which rejects weight on inhibit arcs).
- **Argument names still do not live on arcs** [ADR 0019] is untouched — a
  filter is a selection predicate, not an argument binding.

## Rationale

The comparison (`artifacts/2026-07-07-arc-semantics-comparison.md`) showed the
input divergence is narrower than it looked: all three runtimes push
correlation to a transition guard, so CEL buys nothing for joins. What CEL *does*
buy is declarative, statically-analyzable, visualize-able, cross-language
single-token filtering — real value the Navigator judged worth adopting, given
the named-symbol escape hatch keeps the imperative bypass that
[DR handlers-own-logic] insisted on. Making both slots pure removes the one
replay hazard velocitron carries (impure guards re-evaluated during enablement),
which matters for Impetus's distributed deterministic replay where velocitron's
single-process model does not.

## Consequences

- The net schema adds an optional `filter` to input arc inscriptions and allows
  CEL-or-named in filter and guard positions. A CEL adapter binds inline
  expressions (velocitron's `CelAdapter` protocol, ADR 0010, is a compatible
  path); the schema stays language-agnostic because it carries only the
  expression string or the symbol name.
- Enablement gains a per-arc filtering step *before* guard evaluation, pruning
  the candidate binding space earlier (`firing-semantics.md` §Enabledness).
- The binding layer must distinguish filter/guard symbols (pure) from handler
  symbols (may be impure) so tooling can enforce/warn on the purity contract.
- Divergences to align with Matt: pure-guards (vs velocitron impure guards) and
  filter/weight on inhibit arcs.
- This is an **input-side** decision only; output production (per-arc
  inscriptions [ADR 0017] vs the Petrus merged-token oracle) is unchanged here.

## Supersedes

Supersedes the "no CEL (or similar expression language) initially" clause of
[DR 2026-07-06 handlers-own-logic-no-cel-initially]. That DR's core — the
transition–handler decoupling seam and logic-as-reusable-code — remains in force;
CEL is additive, and named symbols remain the escape hatch.
