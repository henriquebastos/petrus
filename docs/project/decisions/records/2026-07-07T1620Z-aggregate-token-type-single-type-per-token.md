---
status: Decided
raised: 2026-07-07
decided: 2026-07-07
deciders:
  - henrique (Navigator)
supersedes:
related:
  - docs/project/decisions/records/2026-07-07T1600Z-arc-filters-and-guards-cel-or-named-both-pure.md
---

# A token has exactly one type, which may be an aggregate

## Question

An arc filter sees "one token". But a colored token can carry rich data — an
invoice, a payment, source/destination accounts. Does a filter receive a *bag*
of typed parts it must inspect ("does this token contain a Payment?"), as in the
Petrus multi-payload token? Or a single typed value?

## Decision

- **One token, one type.** A colored token has exactly one token color/type. It
  is never a type-less bag of multiple payload types.
- **The type may be an aggregate.** A color may be a composite/aggregate type
  (e.g. `PaymentOrder`) whose data structurally contains other typed fields
  (an invoice, a payment, accounts). The token's type is still exactly one:
  `PaymentOrder`.
- **Filters/guards read the aggregate directly.** A filter over a `PaymentOrder`
  reads nested fields (`data.invoice.amount`) — ordinary structured access, with
  no runtime type-dispatch and no "which type is in this token?" inspection. This
  is what makes the single-token filter of [DR arc-filters-and-guards] clean.
- **Aggregation is a handler's job.** Assembling several inputs into a
  `PaymentOrder` is done by a transition handler upstream; by the time the token
  flows on an arc it is a single well-typed value.

## Rationale

This is equivalent to velocitron's `{type, data}` model (type = the aggregate
name, data = its structured contents), and it deliberately rejects the Petrus
token that holds `{type(obj): obj}` — multiple payload types per token — which
forces `Token.merge` last-wins-per-type reconciliation and exactly the
inspect-the-bag pattern the Navigator wants to avoid
keeps colors meaningful, filters simple, and the CEL/named evaluation context
unambiguous.

## Consequences

- The token/color model specifies a single type per token; aggregate colors are
  first-class and their structure is part of the color's schema.
- The CEL/named filter evaluation context is "this token's data", with nested
  field access — no type-selection semantics needed.
- Downstream simplification: no per-type merge to reconcile, which also clarifies
  the output-production discussion (separate from this record).
