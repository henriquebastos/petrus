---
status: Decided
raised: 2026-06-23
decided: 2026-06-23
deciders:
  - henrique (Navigator, via grill-with-docs in the hermes notebook)
supersedes:
related:
  - hermes ADR 0021
  - docs/project/decisions/records/2026-07-06T1505Z-absorb-hermes-adrs-into-ariad.md
---

> Migrated from the Hermes design notebook.

# ADR 0021: Net schema declares guard and handler symbols

## Status

Accepted

## Context

Petrus needs guards and handlers to be type-aware functions without embedding concrete function implementations directly into the net schema.

A previous question considered whether guards belong to the pure net schema or the binding layer. The refined answer is that the net schema should declare symbolic guard and handler names, while the implementation layer maps those declared names to concrete functions.

This gives the schema stable references while keeping executable code outside the schema.

## Decision

The net schema may declare guard names and handler names on transitions.

Concrete guard and handler functions are provided separately through an implementation mapping / binding set.

A guard is a function that declares the input types it needs and returns boolean.

A handler is a function that declares the input and output types it needs and performs the transition behavior.

The binding/validation layer must verify that every guard and handler symbol declared by the net schema has a corresponding implementation mapping before the process can run.

The mapping does not need to be one-to-one at the code-function level. Multiple schema-declared symbols may map to the same reusable function implementation with different names or configuration.

## Consequences

- The net schema can refer to stable, unique guard/handler symbols without containing executable code.
- Guard and handler implementation functions remain reusable.
- Validation can catch missing implementations early.
- A schema can be inspected to know which guards and handlers it expects.
- The same net schema can run with different implementation mappings.
- Type validation belongs at the boundary between schema-declared symbols and concrete implementations.

## Example

Conceptual schema declaration:

```txt
transition /review/start
  guard: samePullRequest
  handler: prepareReview
```

Conceptual implementation mapping:

```ts
implementations({
  guards: {
    samePullRequest: samePullRequestGuard,
  },
  handlers: {
    prepareReview: prepareReviewHandler,
  },
})
```

Multiple names can map to reusable code:

```ts
implementations({
  guards: {
    samePullRequestForWorktree: samePullRequestGuard,
    samePullRequestForSlackThread: samePullRequestGuard,
  },
})
```

## Open questions

- Are guard and handler symbols local to a net path scope or global within a net definition?
- What is the exact shape of a guard's type contract?
- Does a guard consume the same selected token set as the handler, or can it request a smaller/different typed subset?
- Can a transition have multiple guards? If yes, are they ordered or conjunctive by default?
- Can guard/handler mappings be parameterized per schema symbol?
