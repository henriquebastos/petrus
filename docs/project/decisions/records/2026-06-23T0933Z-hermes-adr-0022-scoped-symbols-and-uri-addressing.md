---
status: Decided
raised: 2026-06-23
decided: 2026-06-23
deciders:
  - henrique (Navigator, via grill-with-docs in the hermes notebook)
supersedes:
related:
  - hermes ADR 0022
  - docs/project/decisions/records/2026-07-06T1505Z-absorb-hermes-adrs-into-ariad.md
---

> Migrated from the Hermes design notebook.

# ADR 0022: Guard and handler symbols are scoped and need URI-like addressing

## Status

Accepted

## Context

Petrus net schemas may declare guard and handler symbols on transitions. Reusable subnets should be able to use simple local names such as `prepare`, `isReady`, or `validate` without forcing globally unique names across the whole composed net.

At the same time, after composition Petrus needs unique addresses for subtle schema elements, including a transition's declared handler symbol or guard symbols. Earlier `NetPath` discussion focused on addresses for place and transition nodes only. That remains useful, but guard/handler declarations live inside transition nodes and also need stable, qualified references for validation, diagnostics, and implementation mappings.

A dotted path may be insufficient. A URI-like representation may better support unique addressing while allowing references to internal parts of a net object.

## Decision

Guard and handler symbols are scoped to the net/subnet or transition context that declares them. During composition and validation, these scoped symbols resolve to absolute, fully qualified symbol addresses.

Petrus should explore URI-like addressing for fully qualified schema references, so it can address:

- place nodes;
- transition nodes;
- a transition's handler declaration;
- a transition's guard declarations;
- possibly other internal schema elements later.

A transition with no handler symbol declared uses default passthrough behavior.

## Consequences

- Reusable subnets can use local guard/handler names without global collisions.
- Composed nets can still validate all declared behavior references precisely.
- Implementation mappings can target fully qualified symbol addresses after composition.
- `NetPath` as node address may become part of a broader schema-reference/address model.
- URI-like addressing should be explored before locking a concrete string format.
- Passthrough behavior is represented by absence of a handler declaration, not by mapping to a special handler symbol.

## Example

A reusable subnet may declare:

```txt
transition start
  guard: isReady
  handler: prepare
```

When mounted under a review subnet, the fully qualified references might conceptually become:

```txt
petrus:/review/start
petrus:/review/start#guard:isReady
petrus:/review/start#handler
```

Exact syntax is not decided. The important point is that addresses should be structured, unique after composition, and capable of referring to internals of a transition.

## Open questions

- Is `NetPath` only a node path, with a separate `SchemaRef` or `NetUri` for internals?
- Should implementation mappings key by transition path plus local symbol, or by fully qualified URI-like references?
- What URI scheme and fragment syntax should Petrus use, if any?
- Are guard symbols scoped to the transition, the containing subnet, or both?
- Can multiple guards on one transition share the same function but have distinct local symbols/configuration?
