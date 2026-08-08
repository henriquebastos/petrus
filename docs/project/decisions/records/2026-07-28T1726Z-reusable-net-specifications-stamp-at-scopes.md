---
status: Decided
raised: 2026-07-28
decided: 2026-07-28
deciders:
  - henrique (Navigator)
supersedes:
  - docs/project/decisions/records/2026-07-28T0133Z-python-dsl-compiles-authored-specifications-to-canonical-nets.md only where it deferred in-memory reusable-definition stamping
related:
  - ES-045
  - docs/project/decisions/records/2026-06-21T1417Z-hermes-adr-0012-separate-net-runtime-from-execution-runtime.md
  - docs/project/decisions/records/2026-06-23T0933Z-hermes-adr-0022-scoped-symbols-and-uri-addressing.md
  - docs/project/decisions/records/2026-07-28T0000Z-transition-behavior-declarations-have-occurrence-identities.md
  - docs/project/decisions/records/2026-07-28T0133Z-python-dsl-compiles-authored-specifications-to-canonical-nets.md
---

# Reusable net specifications stamp at destination scopes

## Question

How should the Python DSL reuse one authored net body several times, customize
each occurrence, preserve flat inline authoring, and still lower into the one
canonical flattened `Net` without importing Petrus loaders, serialization, or
Python class/instance semantics?

## Decision

`NetSpec` owns one mutable authored definition. The same type may be the root
definition or a reusable definition stamped inside another `NetSpec`.
`ScopeSpec` remains a path-local authoring view; `destination.stamp(source)` is
the explicit operation that gives a scope reusable-definition semantics.

Stamps are live authoring relationships until build. A later build sees
the source's current topology and configuration, but every prior `BuiltNet`
remains immutable. `NetSpec.copy()` instead captures an independent flattened
authored snapshot and retains no source relationship.

Each stamp owns destination-specific node configuration overrides.
Calling an unconfigured inherited node completes its declaration;
`node.override(...)` changes selected inherited fields. Neither operation
mutates the source or a sibling stamp. Restamping another source at the
same destination replaces the complete inherited body and clears destination
overrides. Stamping into a scope with directly authored content fails instead
of silently erasing or merging two owners.

The containing definition wires boundary arcs explicitly to destination node
handles. Stamped internal nodes and arcs rebase beneath the destination path;
parallel arcs, declaration order, and callable associations remain authored
occurrences. `NetBuilder(root).build()` recursively resolves nested
stamps, rejects cycles and child completion declarations, creates one
destination-owned effective authored graph, and then delegates topology
validation, place-color resolution, and canonical declaration identity to
`Net`.

`NetSpec.name` is optional metadata, not reusable-definition identity. `None`
is the only unnamed representation; empty strings fail. Diagnostics may render
an unnamed spec as `<anonymous>` without persisting a fabricated name.

`NodeSpec` remains a construction-time value. Its relative path is private;
`abs(node)` explicitly projects a `NetPath` relative to the owning `NetSpec`.
A reusable source node therefore does not identify any stamped destination.
Canonical post-build identity remains the composed `NetPath`/`NetUri`. A
schema-derived navigation object similar to Petrus `NetNav` is a later
candidate, not part of this decision.

## Rationale

Repeated package review supplied concrete reuse pressure.
An explicit stamp graph keeps one inspectable authored schema, supports
localized customization, and lets one source evolve before build. Destination
overlays preserve the field-selective semantics already accepted for future
reuse. Recursive composition recomputes handler and guard declaration URIs from
final paths rather than copying stale implementation-map keys.

Using `NetSpec` for roots and reusable bodies avoids a premature `SubnetDef`
type: whether a definition is a subnet is contextual. Keeping stamps in
the Python authored layer avoids a loader, registry, definition version, or
serialized reference protocol before those have consumers.

## Options Considered

- **Construction callbacks.** Rejected as the composition model because they
  re-execute Python instructions rather than reuse an inspectable authored
  definition. Ordinary helper functions remain allowed.
- **Clone any implicit path prefix.** Rejected because dynamic scopes do not
  declare boundaries, ownership of crossing arcs, or whether a node exactly at
  the prefix belongs to the clone.
- **Eager copy when stamping.** Rejected as the default because it prevents
  several stamps from observing one source definition's later authored
  changes. `NetSpec.copy()` provides deliberate snapshot behavior.
- **A distinct subnet/template class.** Rejected because root and reusable
  definitions have the same authored semantics.
- **Retained serialized refs and provenance layers.** Deferred because no
  loader, editor, source-map, or persisted-definition consumer requires them.
- **Expose authored `.path` as runtime navigation.** Rejected because one
  reusable source node may have several canonical destination paths. Explicit
  `abs(node)` remains an owner-relative authoring convenience.

## Consequences

- Flat root and scoped authoring remain available without `stamp`.
- Reusable source edits affect subsequent builds of every live stamp.
- Destination overrides are independent and restamping is complete rather
  than a structural merge.
- Stamped transition paths naturally include their destination scope, such as
  `review.correctness.review`.
- A domain scope named `apply` remains ordinary attribute navigation. A child
  scope literally named `stamp` uses bracket navigation while `.stamp(...)`
  retains its composition meaning.
- Canonical `Net` remains the only runtime schema and semantic validation
  boundary.
- Ports, place fusion, node renaming, structural deletion, inherited arc
  replacement, per-stamp arc overrides, serialization, loaders,
  registries, source maps, generated navigation, and immutable-definition APIs
  are not introduced.

## Review Trigger

Revisit when a second maintained reusable component demonstrates repeated
boundary wiring that may earn ports; when serialized definitions need reference
identity or source provenance; when structural specialization cannot be
expressed by ordinary destination wiring and field overrides; or when a
runtime-facing consumer earns schema-derived `NetPath` navigation.
