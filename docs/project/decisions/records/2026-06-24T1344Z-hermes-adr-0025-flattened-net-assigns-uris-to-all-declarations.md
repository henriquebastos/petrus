---
status: Decided
raised: 2026-06-24
decided: 2026-06-24
deciders:
  - henrique (Navigator, via grill-with-docs in the hermes notebook)
supersedes:
related:
  - hermes ADR 0025
  - docs/project/decisions/records/2026-07-06T1505Z-absorb-hermes-adrs-into-ariad.md
---

> Migrated from the Hermes design notebook.

# ADR 0025: Flattened net assigns URIs to all declarations

## Status

Accepted

## Context

ADR 0024 established the working vocabulary:

- `Node` means place or transition only.
- `Arc` connects nodes.
- `Declaration` means an addressable schema element attached to a net or node.
- `NetPath` addresses nodes.
- `NetUri` addresses any addressable part of the composed net.

The next question is whether declarations must always be addressable, or whether only externally referenced declarations need addresses.

Authoring ergonomics and runtime uniformity pull in different directions. During editing, a user may only want to name the handler or guard they care about. During composition and flattening, however, the runtime benefits from a complete dictionary of uniquely identifiable net parts.

## Decision

Every declaration must have a canonical `NetUri` in the composed/flattened net.

Authoring APIs may allow anonymous or minimally named declarations. During composition/flattening, Petrus assigns deterministic canonical `NetUri` values to every declaration.

User-named declarations should keep stable, readable URIs. Anonymous declarations should receive deterministic generated URIs.

The flattened net should expose lookup structures that make addressable parts explicit, such as:

- a node dictionary keyed by `NetPath`;
- a declaration dictionary keyed by `NetUri`;
- binding-oriented indexes for handler, guard, timer, and initial marking declarations.

## Consequences

- The authoring model can stay ergonomic.
- The runtime model is uniform: every declaration is uniquely identifiable.
- Diagnostics, validation errors, source maps, editor tooling, and binding lookups can point to precise `NetUri` values.
- Implementation mappings can bind by declaration URI or by indexes derived from declaration URIs.
- Flattening/composition becomes the boundary where informal authoring references become canonical runtime addresses.
- The net runtime can filter and qualify declarations through dictionaries instead of repeatedly walking nested source schemas.

## Examples

Possible canonical declaration URIs:

```txt
petrus:/review/start#handler
petrus:/review/start#guard:isReady
petrus:/review/start#timer:retryDelay
petrus:/review/pending#initial
```

If an authoring API permits an anonymous declaration, the flattened net may generate a deterministic URI such as:

```txt
petrus:/review/start#guard:$0
```

Exact URI syntax remains undecided.
