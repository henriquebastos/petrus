---
status: Decided
raised: 2026-07-08
decided: 2026-07-08
deciders:
  - henrique (Navigator)
supersedes:
related:
  - docs/project/decisions/records/2026-07-07T2119Z-passthrough-is-a-default-handler-color-routed.md
  - docs/project/decisions/records/2026-07-07T1620Z-aggregate-token-type-single-type-per-token.md
  - docs/project/decisions/records/2026-07-08T0044Z-pack-aggregation-deferred.md
  - docs/project/decisions/records/2026-06-21T1417Z-hermes-adr-0012-separate-net-runtime-from-execution-runtime.md
---

# Unpack is a pure stdlib shaping handler (structural projection)

## Question

AND-join and correlation join still needed a handler only because they
*construct* a new aggregate color. Could aggregation/deaggregation be done
without a user handler — via a pure stdlib shaping handler, the family
[DR passthrough-is-a-default-handler-color-routed] left room for? And if so,
does pack (aggregate) and unpack (deaggregate) belong equally in that family?

## Decision

**Add `unpack` as a pure stdlib shaping handler now; defer `pack`**
(see [DR pack-aggregation-deferred]).

- **`unpack` is structural projection.** Given one aggregate token, `unpack`
  projects its named fields to the output arcs that admit them: an output arc
  typed `Invoice` receives the aggregate's `Invoice`-typed field. It is a pure,
  deterministic, single-input shaping handler — the second named member of the
  stdlib family beside `passthrough`.
- **Type-driven by default; field-path only for ambiguity.** When the aggregate
  has exactly one field of an output arc's color, projection is unambiguous and
  needs no configuration. When several fields share a color, the output arc
  carries an explicit field path (the CEL projection form already admitted for
  filters/guards, e.g. `data.corrected_invoice`) to disambiguate.
- **Permissive, per [DR permissive-flow-defaults].** A field with no admitting
  output arc is simply not projected (leftover, allowed). An output arc whose
  color matches no field produces nothing to that arc; a clearly unsatisfiable
  projection is caught at the instantiation-time validation run when statically
  detectable.
- **No construction, no retyping-by-computation.** `unpack` lifts an
  already-typed sub-value out of the aggregate and tags it as a token of that
  field's declared color [DR aggregate-token-type]. It never builds a new type
  and never computes a value.

## Rationale

The load-bearing distinction is **projection vs construction**. Unpack reads
fields that already exist inside the aggregate and works on the data shape
alone — language-neutral, no constructor invoked — so it belongs in the pure
net layer. Pack must *build* a new typed value, which means invoking the target
type's constructor: binding/runtime knowledge. Exposing construction in the
pure net would couple net semantics to type construction, exactly the coupling
[ADR 0012] (net runtime vs execution runtime) and the library-not-framework
stance keep out. Symmetry between pack and unpack is aesthetic; the
projection/construction boundary is architectural, so the two are split
deliberately rather than shipped together.

Unpack is also nearly free: [DR aggregate-token-type] already established
structured tokens with projectable nested fields, so unpack is "project each
field to its admitting arc" over data that already exists. Like `passthrough`
it is pure and may need only deterministic event records, no activity
round-trip.

## Consequences

- `spec/firing-semantics.md` §Default behavior and `spec/handler-contract.md`:
  name `unpack` as a Decided stdlib shaping handler; note `pack` deferred.
- ES-004: unpack-shaped patterns (deaggregation / type-routed scatter of an
  aggregate's fields) can move from user-handler to stdlib `unpack` in a future
  catalog pass; correlation/AND-join (TF-30/TF-35) remain handler-delegated
  because their combine step is *pack*, which is deferred. Recorded as a
  follow-up on ES-004; r3 is not reopened.
- Stdlib family size is now 2 (passthrough, unpack). The
  [DR passthrough-is-a-default-handler-color-routed] review trigger (watch for a
  hidden expression language past ~3) is one step closer; unpack stays inside
  the bound because projection is not Turing-complete and reuses CEL projection.

## Review Trigger

If unpack's disambiguation grows beyond simple field paths (e.g. computed
selection among fields), it is drifting toward construction — revisit against
the pack deferral.
