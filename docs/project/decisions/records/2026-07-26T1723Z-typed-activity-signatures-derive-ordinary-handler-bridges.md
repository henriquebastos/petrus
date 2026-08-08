---
status: Decided
raised: 2026-07-25
decided: 2026-07-26
deciders:
  - henrique (Navigator)
supersedes:
related:
  - ES-045
  - docs/project/decisions/records/2026-07-14T2016Z-activity-invocation-runtime-seam.md
---

# Typed Activity signatures derive ordinary handler bridges

## Question

Why must application authors repeatedly hand-write `prepare` and `project`
for Activities whose arguments and result already correspond directly to the
net's typed arcs, and where should typed-object conversion happen without
moving Petri semantics into Dispatch or Worker?

## Decision

Keep `prepare` and `project` as the semantic durability phases around an
Activity, but derive their ordinary implementation when the net shape is
unambiguous.

`@activity` produces a Petri-agnostic `ActivityDefinition`: the callable's
resolved named-parameter and return annotations, its `ActivityDeclaration`,
and a structural `PayloadConverter`. Operational execution decodes canonical
parameter values immediately before calling the typed function and encodes
its typed result back to a detached JSON-faithful value before returning to
Dispatch. Dispatch providers continue to own transport/wire encoding.

`DerivedActivityHandler` belongs to the Petri-aware binding layer. At explicit
composition time it matches each Activity parameter type name one-to-one with
one weight-one consume/read input arc color and matches the return type name
with every output arc color. It prepares a parameter-name mapping from the
selected tokens and projects the frozen canonical result once per matching
output arc. It leaves correlation and idempotency unspecified so the existing
writer-derived occurrence identity remains the ordinary default.

Derivation refuses missing annotations, unresolved or non-nominal types,
missing/ambiguous/reused input matches, weighted inputs, unmatched outputs,
and selected-cardinality disagreement. It does not guess using parameter,
place, or transition names.

The existing explicit `ActivityHandler` remains the escape hatch for joins or
reshaping, business-specific correlation and idempotency, conditional or
multi-color routing, delivery-registration effects, and any other behavior
the typed arc shape cannot express.

## Rationale

The net already carries ordinary dataflow shape, while the Activity signature
carries the Python object contract. Repeating that same mapping in handwritten
bridges creates ceremony and opportunities for the bridge, annotations, and
arc colors to drift. Derivation removes repetition without deleting the
durability boundary: canonical invocation input is still frozen before
execution, and canonical completion is still frozen before deterministic
projection.

Keeping conversion inside the Petri-agnostic Activity definition gives local
and remote execution the same typed authoring behavior while keeping token
selection and output routing server-side. A pluggable converter also avoids
making dataclasses, Pydantic, or any provider serialization format part of the
kernel contract.

## Options Considered

- **Keep every bridge handwritten.** Rejected for ordinary one-to-one typed
  flow because it duplicates information already present in the signature and
  arcs.
- **Delete `prepare` and `project`.** Rejected because they are distinct
  semantic durability phases and remain necessary for non-ordinary mappings.
- **Perform object conversion in Dispatch or Worker provider code.** Rejected
  because conversion is Activity authoring semantics, while provider wire
  encoding and custody are operational substrate concerns.
- **Have Engine derive every handler automatically.** Deferred: this slice
  proves explicit composition without adding registry inspection or a second
  Engine construction policy.
- **Infer through parameter/place-name heuristics.** Rejected because ambiguous
  shapes must fail loud rather than acquire hidden routing rules.

## Consequences

- Ordinary typed Activities can be authored without handwritten Petri-aware
  `prepare`/`project` classes.
- Canonical History remains JSON-faithful and replay boundaries are unchanged.
- Explicit handlers continue to coexist with derived handlers transition by
  transition.
- Pydantic conversion, weighted collections, unions and dynamic routing,
  automatic Engine-wide derivation, and reusable net-body composition remain
  separate work.
- Worker, Coordinator, and Dispatch protocols do not change.

## Review Trigger

Revisit when a maintained example needs collection parameters, union or
multi-result routing, typed access to execution context, or repeated explicit
composition demonstrates that Engine-wide derivation has one safe universal
rule.
