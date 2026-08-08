---
status: Decided
raised: 2026-07-27
decided: 2026-07-27
deciders:
  - henrique (Navigator)
supersedes:
  - docs/project/decisions/records/2026-07-08T1726Z-places-are-never-typed.md
related:
  - ES-045
  - docs/project/decisions/records/2026-07-07T2118Z-permissive-flow-defaults.md
  - docs/project/decisions/records/2026-07-08T1726Z-handler-symbols-guards-and-nominal-color-matching.md
---

# Place colors compile to effective arc inscriptions

## Question

When every arc incident to a place repeats the same nominal color, should the
place declare that ordinary token domain once without adding a second runtime
admission check or limiting heterogeneous routing?

## Decision

A place MAY declare one language-neutral nominal `Color` name. An untyped place
remains unrestricted. During flattened `Net` construction, the place color is
resolved once onto every otherwise-untyped incident arc. An explicit arc color
remains the narrowing mechanism for a heterogeneous untyped place; an explicit
color conflicting with a typed place is a construction error.

The canonical flattened net exposes effective arcs. Enabledness, routing,
filter ordering, passthrough, and typed handler derivation continue reading
only arc inscriptions, with no per-binding place lookup. Color admission still
precedes an input filter. A typed place's initial marking is validated before
initial History is written.

`Color` is a string alias in the language-neutral schema. Python authoring
layers may project a domain class to its nominal name before constructing the
schema, but class objects are not schema values.

## Rationale

Maintained package authoring provided the review trigger for the superseded
ruling: all 29 connected places held exactly one color, repeated over all 66
incident arcs. The repetition obscured topology and created many opportunities
for drift without expressing heterogeneous routing. Declaring the stable token
domain on the holder makes state legible while construction-time compilation
preserves the simpler, already-proven arc-only execution machinery.

This is not a return to an independent `accepts` constraint checked beside each
arc. The place declaration is an authoring source compiled into the one
effective arc contract. Permissiveness remains: authors may leave both places
and arcs untyped, and heterogeneous places retain explicit colored arcs.

## Options Considered

- **Keep all colors on arcs.** Rejected for homogeneous workflow places because
  it repeats state-domain information on every connection.
- **Check place and arc contracts independently at runtime.** Rejected because
  it complicates the binding hot path and duplicates admission semantics.
- **Remove arc colors.** Rejected because heterogeneous queues, ingress
  demultiplexing, and selective routing require arc-local narrowing.
- **Accept Python classes as schema colors.** Rejected because the flattened
  net is language-neutral; language bindings or DSLs can project classes to
  portable nominal names.
- **Infer place colors from Activity signatures.** Rejected as unnecessary;
  topology remains explicit and Activities validate against effective arcs.

## Consequences

- Ordinary homogeneous workflow nets declare a token domain once per place.
- Existing `Place(path)` and explicit colored arcs retain their behavior.
- `DerivedActivityHandler`, Engine, Coordinator, Worker, Dispatch, Token
  encoding, and canonical History records do not change.
- Initial marking validation gains a typed-place mismatch error before writes.
- Multi-color/union place declarations and signature-driven inference remain
  out of scope.

## Review Trigger

Revisit if a maintained net needs a declared union-colored place, if effective
arc materialization loses authoring information tooling requires, or if a
second language binding cannot represent the nominal-name compilation rule.
