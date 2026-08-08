---
status: Decided
raised: 2026-06-21
decided: 2026-06-21
deciders:
  - henrique (Navigator, via grill-with-docs in the hermes notebook)
supersedes:
  - docs/project/decisions/records/2026-06-21T1619Z-hermes-adr-0013-net-path-is-first-class-static-address-object.md
related:
  - hermes ADR 0014
  - docs/project/decisions/records/2026-07-06T1505Z-absorb-hermes-adrs-into-ariad.md
---

> Migrated from the Hermes design notebook.

# ADR 0014: Net path addresses place and transition nodes

## Status

Accepted

## Context

Petrus needs stable addresses for nodes inside hierarchical Petri nets. Earlier discussion considered whether net paths should address many schema objects such as arcs, subnets, token types, bindings, and exports.

The refined model is that a net path is the address of a node in the Petri-net hierarchy. In this model, the nodes that need net paths are places and transitions.

Arcs are connections between nodes. They require references to a source and destination, but they do not need their own net path unless a future use case introduces arc-level processing that requires identity beyond the connection itself.

## Decision

A `NetPath` addresses only Petri-net nodes:

- places;
- transitions.

A net path describes the node's position in the hierarchical structure of the composed Petri net.

Internally, all resolved net paths should be absolute. Petrus may also support relative net path references for authoring and composition, but those references must resolve against a root path or net context into absolute net paths during validation/compilation.

The root net path may be represented as an empty/root path object. Child paths are resolved from that root.

Arcs should not have net paths for now. An arc is a connection from one node path to another node path, with direction and arc semantics. Tooling can find incoming or outgoing arcs for a given net path by indexing arcs by endpoint.

## Consequences

- Net path becomes equivalent to node address for places and transitions.
- Handler bindings reference transition net paths.
- Arc definitions reference endpoint net paths rather than having identities as paths themselves.
- The schema/compiler must resolve relative authoring references to absolute net paths.
- Diagnostics can still report arcs by their endpoints.
- If future arc-level behavior requires identity, arc IDs can be revisited without making arcs part of the net path model now.

## Open questions

- What is the canonical string representation of the root net path?
- What is the canonical separator for path segments?
- Are place and transition names in the same namespace under a parent path, or separate namespaces?
- What are the best names for arc endpoints: source/destination, from/to, input/output, or place/transition endpoint?
- Should relative paths be allowed in persisted schema, or only in authoring APIs before validation?
