---
status: Decided
raised: 2026-06-21
decided: 2026-06-21
deciders:
  - henrique (Navigator, via grill-with-docs in the hermes notebook)
supersedes:
related:
  - hermes ADR 0011
  - docs/project/decisions/records/2026-07-06T1505Z-absorb-hermes-adrs-into-ariad.md
---

> Migrated from the Hermes design notebook.

# ADR 0011: Core requires explicit net schema

## Status

Accepted

## Context

A typed-handler-first onboarding API was considered, where a simple pipeline of handlers could derive a net definition. This might make Petrus easier for beginners, but it risks drifting the core toward imperative programming and hiding the Petri-net structure.

The current priority is not onboarding ergonomics. The priority is getting the core model, layers, and boundaries correct.

Petrus may later provide higher-level APIs that generate or compile to net schemas. Those APIs should sit above the core and should not define the core semantics.

## Decision

The Petrus core requires a well-defined explicit net schema.

The core should not derive the net from handlers. Handlers bind to transitions in an already-defined net schema.

Higher-level handler-first or pipeline-style APIs may be explored later as optional layers that produce explicit net definitions, but they are not part of the core model now.

## Consequences

- The core remains centered on Petri-net semantics rather than imperative step composition.
- Net structure stays visible, inspectable, and durable.
- Handler definitions do not secretly become the process topology.
- Layer boundaries remain clearer while the project is still being modeled.
- Onboarding convenience is deferred until the formal layers are stable.

## Rejected alternative

### Handler-derived core net

Rejected for now because it could make Petrus feel easier initially while weakening the central Petri-net model. The system should not hide the net as an implementation detail of imperative handlers.
