---
status: Decided
raised: 2026-06-21
decided: 2026-06-21
deciders:
  - henrique (Navigator, via grill-with-docs in the hermes notebook)
supersedes:
related:
  - hermes ADR 0017
  - docs/project/decisions/records/2026-07-06T1505Z-absorb-hermes-adrs-into-ariad.md
---

> Migrated from the Hermes design notebook.

# ADR 0017: Arc mode applies only to input arcs

## Status

Accepted

## Context

Petrus supports consume, read, and inhibitor arcs. These modes describe how tokens in a place participate in transition enablement and firing.

However, arcs are represented generically with `from` and `to` endpoints, and valid arcs may be either:

- place → transition;
- transition → place.

Consume, read, and inhibitor modes only make sense for place → transition arcs. Transition → place arcs describe produced output tokens, not input token consumption or absence checks.

## Decision

Arc mode applies only to input arcs: arcs where `from` is a place and `to` is a transition.

Output arcs, where `from` is a transition and `to` is a place, do not have consume/read/inhibit modes. They have output inscriptions describing produced tokens.

The primitive arc model can still use `from` and `to`, but validation should classify arcs by endpoint kinds:

```ts
InputArc {
  from: PlacePath
  to: TransitionPath
  mode: 'consume' | 'read' | 'inhibit'
  inscription: InputInscription
}

OutputArc {
  from: TransitionPath
  to: PlacePath
  inscription: OutputInscription
}
```

## Consequences

- Input token semantics remain separate from output production semantics.
- Validation can reject modes on transition → place arcs.
- Documentation should avoid implying that output arcs consume, read, or inhibit anything.
- The arc model remains simple while preserving Petri-net direction semantics.
