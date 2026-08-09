---
id: guard-symbols-net-scoped-not-transition-local
status: Paid
kind: design
severity: low
source: CV2 slice 3 (guards) review, gpt-5.5 spec-fidelity lens
revisit_trigger: Canonical arc-filter declaration identities land, or a net needs same-name filter declarations with different implementations.
closure_condition: Filter implementation mappings key by resolved arc-filter declaration identity, with validation and tests covering same-name-different-implementation. Handler and guard scope is paid.
---

# Filter implementation mappings remain net-scoped

## Description

The ratified contract makes behavior symbols **owner-local
names, subnet-qualified on resolution** — resolving to declaration URIs such as
`transition:/review/start#guard:isReady` [ADR 0022, ADR 0026, DR 2026-07-08
handler-symbols-guards-and-nominal-color-matching]. The slice-3/4 kernel keys
both implementation mappings by bare symbol string (`NetInstance(guards=
{"isReady": fn}, handlers={"prepare": fn})` in the historical runtime): one
flat namespace each per net. Two transitions declaring the same local name
with different implementations cannot be expressed; they silently share one
function. This gap originally covered handlers, guards, and filters.

Handler and guard scope was paid on 2026-07-28. Canonical `NetUri` occurrence
indexes now address every handler and guard declaration; `Instance` resolves
exact URI bindings once, supports bare named fallback deliberately, rejects
ambiguous overlap, and tests same-name declarations with different exact
implementations. Only arc-filter implementation scoping remains carried.

## Carrying Reason

Canonical transition behavior addressing now exists, but canonical arc-filter
occurrence identities—including parallel-arc fragments—do not. Creating a
separate partial filter identity scheme would preempt that owning design, so
the filter remainder stays explicit rather than hidden.

## Impact

Low until a flat or composed net reuses one filter symbol while expecting
different implementations. Handler and guard reuse no longer carries this
risk.

## Revisit Trigger

Composition/subnets or canonical arc-filter identities arrive; or a real net
needs same-name-different-implementation filters.

## Closure Condition

Filter implementation mappings target resolved arc-filter declaration
identities, validated fail-fast, with same-name/different-implementation and
parallel-arc coverage.

## Notes

**Handler-slice revisit (2026-07-08, slice 4):** the named trigger fired when
handlers adopted the same mapping contract. The Navigator re-adjudicated:
carry — the carrying reason is unchanged (flat single-scope net, no
subnets/NetUri; a `(transition, symbol)` key is still a half-structure ADR 0025
replaces). Handler mappings now share this debt explicitly.

**Filter-slice extension (2026-07-08, slice 5):** arc filter symbols
(`NetInstance(filters={...})`) adopted the same flat net-scoped mapping. Their
ratified resolution is arc-anchored rather than transition-anchored
(`arc:...#filter` declaration URIs), but the gap and the carrying reason are
identical, so filter mappings share this debt rather than a new item.

Related taste finding accepted deliberately in the same review: `Transition.guards`
(declared symbols) and `NetInstance(guards=...)` (implementation mapping) share a
name; the concepts separate naturally when mappings key by declaration identity.
See `src/petrus/impetus/instance/__init__.py` (current validation) and
`docs/process/engineering-conventions.md`.

**Transition behavior payment (2026-07-28):** handler and guard occurrence
indexes, exact `NetUri` implementation bindings, ambiguity validation, and
same-name/different-implementation tests landed with the production Python DSL.
The item remains `Carried` only for its filter-scope remainder.

**Revisited 2026-08-09:** reusable authored definitions and canonical
transition behavior identities have shipped, but flattened arcs still have no
canonical occurrence/declaration index or parallel-arc fragment identity.
Composition alone therefore cannot pay the filter remainder without inventing
a partial addressing scheme. The debt stays `Carried`; its trigger is narrowed
to the missing canonical arc-filter identity or a demonstrated same-name need.

## Filter payment

Paid on 2026-08-09. Every filter occurrence now resolves through its exact
arc-filter declaration URI. Exact URI mappings can bind equal local names
independently; bare names deliberately share one implementation; exact plus
bare overlap fails before execution; and inline CEL declarations reject exact
overrides. Parallel-arc coverage proves distinct occurrence ownership.
