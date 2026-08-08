---
status: Decided
raised: 2026-07-28
decided: 2026-07-28
deciders:
  - henrique (Navigator)
supersedes:
related:
  - ES-045
  - docs/project/decisions/records/2026-07-28T0000Z-transition-behavior-declarations-have-occurrence-identities.md
  - docs/project/decisions/records/2026-07-27T2333Z-place-colors-compile-to-effective-arc-inscriptions.md
  - docs/project/decisions/records/2026-07-28T1726Z-reusable-net-specifications-stamp-at-scopes.md
---

# The Python DSL compiles authored specifications to canonical nets

## Question

What is the production boundary for fluent Python authoring, place colors, and
callable implementations?

## Decision

`impetus.dsl` is a Python authoring frontend over the canonical
language-neutral `impetus.petrinet.Net`. Its minimal authored IR uses the
`Spec` vocabulary: `NodeSpec` (`PlaceSpec` and `TransitionSpec`), `ArcSpec`,
and `ConnectionSpec`. `NetBuilder.build()` snapshots that IR and passes the
result through canonical `Net` construction for topology validation and
place-color compilation.

`PlaceSpec` and `TransitionSpec` are callable authored definitions. Calling a
place declares its color; calling a transition declares its handler, guards,
and timers. Configuration returns and belongs to the same stable node identity,
so a later bare reference retains it. Every `>>` occurrence remains an
independent arc declaration and preserves parallel-arc multiplicity. Repeated
identical configuration is idempotent, conflicting configuration fails, and
earlier immutable build snapshots do not change when the builder is configured
later.

`node.override(...)` is the field-selective customization operation for an
existing explicit or inherited configuration. Omitted fields are preserved;
`color=None`, `handler=None`, `guards=()`, and `timers=()` explicitly clear
their fields. Guard and timer collections replace as whole fields. Override is
not an upsert, validates every supplied field before changing the effective
record, returns the same stable node identity, and affects no prior build
snapshot. Later deliberate overrides win. The former whole-record
`replace_transition` API is removed rather than deprecated. A future copied or
mounted authored definition must own destination configuration mappings so an
override cannot mutate its reusable source or another copy; full subnet and
provenance-layer semantics remain deferred.

The fluent connection operator is only `>>`. Direct connections use
`place >> transition >> place`; `arc(...)`, `arc.read(...)`, or
`arc.inhibit(...)` is inserted only when a consume, read, or inhibit
inscription is needed. The DSL factory does not accept a mode parameter;
`ArcMode` remains canonical schema vocabulary rather than authoring syntax.
Python's comparison-chain semantics make `>` unsuitable for a left-associative
pipeline.

Python classes supplied as place or arc colors lower to their nominal names;
the canonical net still contains only language-neutral color strings.

`direct(...)` or `@direct` marks a pure typed transformation executed locally
as part of firing. An ordinary callable supplied as a guard is a pure typed
predicate by DSL rule and needs no decorator. External work retains the
separate `@activity` contract and may remain a named declaration for late host
binding. Existing low-level `Binding` functions use the advanced
`petri_handler(...)` and `petri_guard(...)` escape hatches. Callable specs lower
after canonical net construction to exact declaration-URI implementation maps
in an immutable `BuiltNet`; code is never stored in the canonical net and
identity is never inferred from a Python callable name.

The frontend lives outside `impetus.petrinet` because it composes the
independent Petrinet Kernel with higher binding and activity adapters.

## Rationale

The package tests and canonical specification establish that the fluent shape removes repetitive
constructor noise without changing canonical topology or behavior. A small
authored IR preserves declaration order and deliberate overrides while keeping
one semantic schema and validation boundary. Explicit callable flavor prevents
signature guessing from choosing the wrong execution seam.

## Options Considered

- **Build runtime objects continuously while authoring.** Rejected for
  production because authored declarations and canonical compiled values have
  different responsibilities, especially for class colors and callable code.
- **Put the frontend in `impetus.petrinet.dsl`.** Rejected because typed and
  Activity lowering would invert the Petrinet Kernel's dependency boundary.
- **Support both `>` and `>>`.** Rejected because chained comparison evaluation
  makes `>` unsafe and inconsistent with inscribed connections.
- **Infer callable flavor or identity from signatures or names.** Rejected
  because signatures and `__name__` cannot distinguish all supported seams or
  provide canonical declaration identity. `@direct`, guard position, and the
  advanced Petri-aware wrappers select flavor before signatures are inspected.

## Consequences

- Python authors import the public frontend from `impetus.dsl`.
- `BuiltNet.net` is suitable wherever canonical `Net` is expected; its exact
  URI maps supply handler and guard implementations to an `Instance`.
- Place-color and topology behavior remain owned by canonical `Net`.
- At this decision point, subnet cloning, refnets/templates, mounting,
  serialization, loaders, and source maps were not implied by dynamic path
  scoping and remained deferred. The review trigger later resolved in-memory
  reusable-definition stamping in DR 2026-07-28
  `reusable-net-specifications-stamp-at-scopes`; serialization, loaders, and
  source maps remain deferred.

## Review Trigger

Revisit the authored IR when concrete composition pressure produces a subnet
or refnet design, or when a serialized net-definition protocol requires source
provenance the current in-memory specifications do not retain.

Subsequent authoring review fired the first trigger. DR
2026-07-28 `reusable-net-specifications-stamp-at-scopes` separates `NetSpec`
authoring from `NetBuilder` composition and defines live stamping,
destination overrides, copy snapshots, and construction-only node paths.

The first package authoring review triggered and resolved the public naming
question: the primary vocabulary is `@direct`, an ordinary callable guard, and
the separate existing `@activity` contract. Revisit the advanced
`petri_handler` and `petri_guard` spellings only when maintained authoring—not
internal tests—demonstrates that the low-level escape hatches need promotion.
