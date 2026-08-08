---
id: cel-data-exposure-has-no-unified-design
status: Carried
kind: design
severity: medium
source: Navigator, 2026-07-09, on completing the expression tier's third consumer (CV2 slice 7)
revisit_trigger: A fourth expression slot appears (timers? validation-run predicates?), cross-language alignment of the CEL tier (velocitron CelAdapter / Matt), authoring documentation for expression slots is written, or the Navigator schedules the comparison exploration.
closure_condition: A decision record ratifies one deliberate data-exposure design across the tier — either a unified environment shape or an explicitly justified per-slot divergence — after comparing all implementations side by side; kernel and tests aligned to the ruling.
---

# CEL data exposure has no unified design across the tier's consumers

## Description

The expression tier is one substrate (`impetus/cel.py`, one backend, shared
parse/encoding helpers) but its three consumers expose data to expressions in
three different shapes, each ruled locally in its own slice:

| Slot | Sees | Environment | Color | Token access |
|---|---|---|---|---|
| `Arc.filter` (slice 5) | one token | the token's **bare data fields** as top-level variables (`amount >= 100`) | invisible (matched outside CEL, on the arc) | implicit — no struct, no list |
| guard (slice 7) | the binding | **place names** → list of selected tokens as `{color, data}` maps | visible (`p[0].color`) | `p[0].data.amount` |
| `#completion` (slice 6) | the marking | **place names** → whole queue as `{color, data}` maps (absent place = `[]`) | visible | `done[0].data.state` |

The divergences are not obviously wrong — each shape fits its scope (a filter
has exactly one token; a guard has per-place selections; completion has
queues) — but they were never designed *together*. Consequences already
visible: the same conceptual predicate is spelled differently per slot
(`amount >= 100` as a filter vs `pending[0].data.amount >= 100` as a guard),
an expression cannot be moved between slots without rewriting, a filter
cannot read its token's color while the other two slots can, and the
scalar-vs-list seam (filter implicit token vs guard `p[0]` even at weight 1)
is an accident of slice ordering rather than a ruling.

## Carrying Reason

Navigator (2026-07-09): "There's no unique design to figure it out. …how CEL
interacts and relates to the application, we need more clarity on that. I
don't want to solve it now. I don't think it should block the slices." The
tier just became complete across its three ratified slots — the right moment
to *name* the question, and the wrong moment to redesign it mid-plan.

## Impact

Medium: each slot works and is pinned by tests, so nothing mis-executes. The
cost is author-facing coherence — expression-writing knowledge does not
transfer between slots — and it compounds with every net authored and every
future slot added before a unified ruling. A later redesign is a breaking
change to declared expressions, so the price of deferral grows with adoption.

## Revisit Trigger

A fourth expression slot, cross-language CEL alignment, authoring docs for
the tier, or a Navigator-scheduled design exploration (ES) comparing all
implementations.

## Closure Condition

A side-by-side comparison of the three environments feeding a decision
record: one deliberate data-exposure design (unified, or per-slot divergence
each explicitly justified), kernel and tests aligned.

## Notes

Code breadcrumb: `src/petrus/impetus/binding/cel.py` module docstring. The individual
Navigator rulings being reconciled: slice 5 (bare-data-field activation,
color outside CEL), slice 6 (place-as-variable queue structs, black = nulls),
slice 7 (place-keyed binding selections, consume/read scope). Related:
DR 2026-07-07 arc-filters-and-guards-cel-or-named-both-pure (the tier);
`2026-07-09T2100Z-macro-shadowed-scope-references-escape-construction-checks.md`
(a shared-substrate seam the redesign should also visit).
