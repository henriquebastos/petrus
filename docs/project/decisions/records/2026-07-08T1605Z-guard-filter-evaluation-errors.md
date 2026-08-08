---
status: Decided
raised: 2026-07-08
decided: 2026-07-08
deciders:
  - henrique (Navigator)
supersedes:
related:
  - docs/project/decisions/records/2026-07-07T1600Z-arc-filters-and-guards-cel-or-named-both-pure.md
  - docs/project/decisions/records/2026-07-07T2118Z-permissive-flow-defaults.md
  - docs/project/decisions/records/2026-06-23T0312Z-hermes-adr-0021-schema-declares-guard-and-handler-symbols.md
---

# Guard/filter evaluation errors: skip the binding, surface the diagnostic

## Question

The Petrus oracle treats a `TypeError` raised while extracting guard
arguments from peeked tokens as "not enabled" rather than a crash —
deliberate, but it conflates programming errors with disabled state
(`firing-semantics.md` §Enabledness OPEN). Must Impetus reproduce this?

## Decision

The Petrus behavior is mostly an artifact of its architecture and does not
transfer: Petrus arcs carried no types, so the guard's Python signature was
the *only* place types existed — the guard was the type filter, checked
per-marking at enablement time. Impetus moved type knowledge into the net
(arc inscriptions carry color and filter; candidate computation selects
tokens from arcs *before* guards run), so the failure class splits in two:

1. **Declared mismatch — validation error, never runtime.** Where types are
   declared (typed arcs, named guard/filter symbols with contracts), a
   guard or filter that requires something no arc can supply is a
   **structural mismatch**: an instantiation-time validation-run error
   [ADR 0021; DR permissive-flow-defaults posture], and an edit-time warning
   in tooling. The expression is never evaluated against an impossible
   binding.
2. **Evaluation error on a concrete token — binding not satisfied.** Under
   permissive defaults, untyped arcs may admit tokens whose shape a CEL
   expression cannot read (missing field, wrong nesting). An evaluation
   error in a filter or guard means **that binding is not satisfied**: the
   candidate is skipped, enablement computation continues, nothing crashes.
   Because filters and guards are pure [DR arc-filters-and-guards], the
   error is a deterministic function of the token data — replay reproduces
   the same skip.
3. **Never silently.** Every runtime evaluation error is **surfaced as a
   diagnostic** naming the expression (by NetUri), the token, and the error.
   Petrus's real defect was not returning false — it was returning false
   *indistinguishably from a healthy false*, hiding typos (`data.amuont`)
   behind a transition that mysteriously never fires. Whether diagnostics
   live in the canonical event history or a derived diagnostics channel is
   an implementation-revealed detail folded into the ADR 0031 payload opens;
   the requirement here is only: recorded and inspectable, not swallowed.

Filters and guards are one pure enablement pipeline (inscription → filter →
guard) evaluated before any handler involvement; an evaluation error is an
enablement fact about one binding, never an execution failure of the
instance.

## Rationale

The Navigator: the guard should never fire against tokens the arcs did not
admit — declared impossibilities belong to edit/instantiation-time checks;
if evaluation is reached and fails, "it's like returning false." The added
guard-rail (rule 3) preserves debuggability under the permissive default,
where static checks cannot see undeclared shapes.

## Consequences

- `spec/firing-semantics.md` §Enabledness OPEN is closed; the oracle's
  TypeError-means-not-enabled is recorded as reproduced in *effect* (skip)
  but not in *silence* (diagnostic required).
- Validation run gains the guard/filter-vs-arc-contract mismatch check where
  declarations permit it; untyped flows remain legal and un-warned by
  default ("adding types restores the proofs").
- Kernel enablement evaluation must catch expression errors per-binding, not
  per-transition: one unreadable token must not mask other valid bindings of
  the same transition.

## Review Trigger

Revisit when the kernel implements the diagnostics channel (placement of
evaluation-error records vs canonical history), or if a named-symbol guard
contract system emerges that could make more mismatches statically
checkable.
