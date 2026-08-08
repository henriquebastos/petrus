---
status: Decided
raised: 2026-07-07
decided: 2026-07-07
deciders:
  - henrique (Navigator)
supersedes: docs/project/decisions/records/2026-07-07T1710Z-passthrough-identity-and-homogeneous-broadcast.md
related:
  - docs/project/decisions/records/2026-07-07T2118Z-permissive-flow-defaults.md
  - docs/project/decisions/records/2026-06-21T0842Z-hermes-adr-0010-no-handler-default-behavior-is-passthrough-only.md
  - docs/project/decisions/records/2026-07-07T1700Z-output-production-per-arc-contract-handler-supplies-tokens.md
  - docs/project/decisions/records/2026-07-07T1620Z-aggregate-token-type-single-type-per-token.md
---

# Passthrough is a default handler; it routes each consumed token by color

## Question

The ratified passthrough (identity + homogeneous broadcast, everything else a
validation error) taxed four common patterns (permit moves, distinct-color
AND-joins, correlation joins, deferred choice) with trivial one-line handlers.
And architecturally: is "transition with no handler" a special case in the
engine, or just a default binding?

## Decision

1. **Passthrough is a handler, not an engine special case.** The engine always
   invokes the transition's handler; a transition with no handler symbol is
   **default-bound to the library's `passthrough` handler** by the binding
   layer. This reframes [ADR 0010]'s "default behavior" as a default *binding*
   (Petrus production precedent: passthrough was implemented as a default
   handler and "at that time I just needed one").
2. **Color-routed passthrough semantics** (superseding the identity +
   homogeneous-broadcast rule): the `passthrough` handler forwards **each
   consumed token, unchanged, through every output arc that admits it** — a
   typed output arc admits its color, an untyped output arc admits anything
   [DR permissive-flow-defaults]. The same token flowing through N admitting
   arcs is deposited into N places (broadcast generalizes). Never merges,
   never splits, never retypes [ADR 0010, DR output-production,
   DR aggregate-token-type]. Consumed tokens admitted by no arc are simply
   consumed [DR permissive-flow-defaults]. Read and inhibit arcs contribute
   nothing to output.
3. **A family of pure shaping handlers may grow beside it.** `passthrough` is
   the first of a small library of **pure, side-effect-free default handlers**
   for shaping flow — splitting, combining/aggregating, type composition —
   selectable by name like any handler symbol. Only `passthrough` is a
   *default*; the others are opt-in stdlib. Users' own handlers remain the
   home of side effects and everything else.

## Rationale

Avoiding special cases twice over. In the engine: one code path — every firing
runs a handler — instead of a special no-handler branch. In the user model:
the permit move, distinct-color join, correlation join (guard correlates,
passthrough forwards), and deferred choice all become zero-handler topology +
arc types, eliminating the trivial-handler tax without weakening the rule that
shaping beyond routing needs an explicit (possibly stdlib) handler.

## Consequences

- `spec/firing-semantics.md` §Default behavior and `spec/handler-contract.md`
  amended; CONTEXT.md passthrough entry updated.
- Pure stdlib handlers open an event-history question: a pure default handler
  needs no activity round-trip, so its firing could be recorded as
  deterministic records only — folded into the existing OPEN on "activity
  completed vs handler result recorded for in-process handlers"
  (`spec/event-history.md`). (Resolved 2026-07-14 by
  `2026-07-14T2016Z-activity-invocation-runtime-seam.md`: pure firings are
  deterministic records only, and there is no handler-result record at all —
  the terminal activity fact plus effect records carry impure work.)
- **Output-arc weight (TF-41) stays deferred**, with the Navigator's leaning
  recorded: prefer *no special case* for output weights (most arcs are weight
  one; multiplicity wants can often be an aggregate type — "a tuple of two
  types" — rather than weight semantics). Revisit only against concrete need.
- ES-004 requires a final cascade: TF-11/24/30/35 return to zero-handler CORE,
  TF-20 (sink) is ruled structural, r3 of the support recommendation follows.

## Review Trigger

When the stdlib shaping-handler family grows beyond ~3 members, revisit
whether it is becoming a hidden expression language (the thing
[DR arc-filters-and-guards] deliberately bounded).
