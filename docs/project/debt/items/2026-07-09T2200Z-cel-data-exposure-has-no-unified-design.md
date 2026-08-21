---
id: cel-data-exposure-has-no-unified-design
status: Carried
kind: design
severity: medium
source: Navigator, 2026-07-09, on completing the expression tier's third consumer (CV2 slice 7)
revisit_trigger: A fourth expression slot appears, authors demonstrate a concrete need for color-sensitive inline filters, a successor Net-definition protocol is planned, cross-language CEL execution is commissioned, or the Navigator reschedules the comparison.
closure_condition: A decision record ratifies one deliberate data-exposure design across the tier — either a unified environment shape or an explicitly justified per-slot divergence — after comparing all implementations side by side; kernel and tests aligned to the ruling.
last_reviewed: 2026-08-21
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

Navigator (2026-08-21) revisited the comparison and explicitly deferred the
work again. Keep this as carried design debt, not a planned CV: no current
delivery commitment exists, and promoting it would turn a future design choice
into roadmap intent prematurely.

## Impact

Medium: each slot works and is pinned by tests, so nothing mis-executes. The
cost is author-facing coherence — expression-writing knowledge does not
transfer between slots — and it compounds with every net authored and every
future slot added before a unified ruling. A later redesign is a breaking
change to declared expressions, so the price of deferral grows with adoption.

## Revisit Trigger

A fourth expression slot; a demonstrated need for color-sensitive inline arc
filters that inscriptions and named filters do not serve well; planning a
successor Net-definition protocol; commissioned cross-language CEL execution;
or a Navigator-scheduled design comparison.

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

The 2026-08-21 reconstruction from `origin/main` found no fourth CEL slot.
Arc filters still expose bare token-data fields (`amount >= 100`); guards expose
consume/read selections by place as lists of `{color, data}` tokens; completion
exposes whole place queues in that same token shape. Since this debt was first
recorded, those expressions became part of canonical Net-definition v3,
inspection, and bounded-simulation surfaces; the maintained simulation fixture
uses the bare-field filter `priority >= 1`. Python APIs remain pre-release, but
changing bare-field filters to require `token.data.amount` would narrow the set
of executable v3 definitions and should therefore be considered with a
successor protocol rather than silently reinterpreting v3.

The Driver recommendation at that review was to ratify the existing per-slot
shapes: each answers a different scope question, bare fields keep the common
single-token filter concise, and even a unified inner token envelope would not
make expressions directly movable between a scalar filter and place-keyed
lists. This is retained context, not a decision. A future review should still
compare that option against an explicit `{color, data}` filter token and make
the Navigator choice before changing behavior. Archived thread
`T-019fe95f-0503-77f5-9e3e-b03f79bf6292` and its unreachable local commit are
historical evidence only and must not be recovered or treated as the ruling.
