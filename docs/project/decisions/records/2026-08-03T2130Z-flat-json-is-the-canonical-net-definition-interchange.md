---
status: Decided
raised: 2026-08-03
decided: 2026-08-03
deciders:
  - henrique (Navigator)
supersedes:
related:
  - docs/project/decisions/records/2026-07-23T1614Z-impetus-owns-versioned-net-definition-protocol.md
  - spec/net-definition-v3.md
---

# Flat JSON is the canonical Net-definition interchange

## Question

What representation should Petrus, Arx, Python authoring, tests, agents, and
other systems exchange and edit, and how should reusable Nets or independently
encapsulated runnable systems compose?

## Decision

Use one versioned JSON document as the canonical cross-system Net definition.
Represent its exact shape with strict frozen Pydantic models and compile it
through the immutable current-Petrus `Net`, which remains the semantic
validation and runtime-index boundary.

Python source is not an interchange format and Arx does not rewrite it. The
Python DSL remains one useful frontend for humans, agents, and tests; Arx and
other frontends may produce the same canonical JSON. An in-process frontend
need not serialize and parse its own model merely to construct a `Net`, but its
projected definition must converge on the same canonical document.

Every exchanged definition is complete and flat. Places, transitions, and arcs
carry full canonical paths. Reusable authored definitions are templates:
frontends may stamp, copy, or merge them before producing one flattened
document. Multi-file refs and mount resolution are not part of the canonical
format.

A Net bundled with Activities, handlers, credentials, deployment, and host
policy is not an authoring subnet. It is a separately bound runnable
application/Instance. Independently encapsulated Instances communicate through
Fabric rather than sharing one executable schema.

## Rationale

The public predecessor proved that Pydantic file models, typed paths, a
separate compiler boundary, and globally flat executable structure work well.
It also proved that recursive refs, mount identity, shared template view state,
and multi-file resolution impose substantial complexity without improving the
runtime's flat semantic model.

The current canonical inspection projection already carries nearly all current
implementation-free Net structure. Promoting an independently versioned,
strictly loadable definition avoids Python coupling and gives Arx an honest
future write boundary while retaining current Petrus semantic authority.

## Consequences

- Net-definition file schema v3 is a changed successor to predecessor v2, not a
  compatibility mode.
- Pydantic owns wire shape and strict field validation; `Net` owns semantic
  topology and executable indexes.
- Observation, capture, and simulation keep their own frozen envelopes while
  nesting the exact pinned structural projection.
- Layout, state, History, implementation bindings, source provenance, package
  custody, and deployment remain separate artifacts.
- Arx editing and file custody follow only after Petrus pins v3 producer and
  compiler conformance.
- Current place roles and the separately decided correlated-inhibitor semantic
  are not invented as inert v3 fields; they require matched runtime and
  successor-protocol delivery.

## Review Trigger

Return when Arx plans its first v3 write/open story; a second frontend needs
portable conformance; correlated inhibitors or place roles enter runtime; or a
real authoring case demonstrates that one complete flat document is
insufficient.
