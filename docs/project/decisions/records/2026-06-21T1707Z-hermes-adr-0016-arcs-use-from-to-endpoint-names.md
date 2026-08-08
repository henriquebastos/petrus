---
status: Decided
raised: 2026-06-21
decided: 2026-06-21
deciders:
  - henrique (Navigator, via grill-with-docs in the hermes notebook)
supersedes:
related:
  - hermes ADR 0016
  - docs/project/decisions/records/2026-07-06T1505Z-absorb-hermes-adrs-into-ariad.md
---

> Migrated from the Hermes design notebook.

# ADR 0016: Arcs use from/to endpoint names

## Status

Accepted

## Context

Petrus arcs are connections between node paths. Arcs do not currently have net paths. Since a Petri-net arc may connect either place-to-transition or transition-to-place, endpoint terminology needs to be clear.

Possible naming options included:

- `from` / `to`;
- `source` / `target`;
- Petri-specific constructors such as `inputArc(place, transition)` and `outputArc(transition, place)`.

## Decision

The primitive arc endpoint names should be `from` and `to`.

An arc should be modeled as a directed connection:

```ts
Arc {
  from: NetPath
  to: NetPath
  inscription?: ArcInscription
  mode?: ArcMode
}
```

Validation must enforce that arcs only connect valid Petri-net node pairs:

- place → transition;
- transition → place.

Validation should reject:

- place → place;
- transition → transition.

Convenience constructors may exist above the primitive model, such as:

```ts
inputArc(place, transition)
outputArc(transition, place)
```

But these compile to the same `from` / `to` arc representation.

## Consequences

- The primitive arc model stays simple and graph-like.
- Direction is always explicit.
- Petri-net correctness is enforced by validation rather than encoded in separate arc object shapes.
- Tooling can index incoming/outgoing arcs by `from` and `to` endpoints.
