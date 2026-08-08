---
status: Decided
raised: 2026-07-29
decided: 2026-07-29
deciders:
  - henrique (Navigator)
supersedes:
  - earlier provisional Petrus naming and package boundaries
related:
  - docs/project/decisions/records/2026-08-01T0100Z-petrus-python-namespace-owns-impetus-and-motus.md
  - docs/project/decisions/records/2026-07-24T2217Z-apache-governs-petrus-authored-material-with-explicit-exceptions.md
---

# Petrus is the project over Impetus, Motus, Arx, and optional Agenticus composition

## Decision

Petrus is both the project and the Python distribution. Its component
responsibilities are:

- **Impetus** owns Petri-net semantics, Instance state, and canonical History.
- **Motus** owns Activity execution, Dispatch, transports, and Workers.
- **Arx** is a separate human-facing companion for editing, inspection,
  debugging, and simulation; it consumes Petrus contracts without owning
  runtime state.
- **Agenticus** is an optional Petrus-level composition over Impetus and Motus.
  It is not a fourth foundational component.

This supersedes earlier provisional naming and package-boundary conclusions.
The physical Python ownership is defined by the related namespace decision.

## Rationale

The names make dependency direction and responsibility visible. Petrus gives
the installed system one coherent identity while Impetus and Motus retain
separate semantic and operational ownership. Arx remains independently
maintained because presentation must not become runtime authority. Agenticus
can compose the runtime for agent infrastructure without forcing agent
concepts into the core.

## Consequences

- Runtime semantics and canonical History remain Impetus-owned.
- Operational Activity custody remains Motus-owned.
- Arx follows current Petrus contracts and does not define them.
- Agenticus remains optional and depends inward on Impetus and Motus; those
  components do not depend on Agenticus.

## Review Trigger

Revisit only if an independently installable component boundary is proven or
the dependency direction can no longer preserve these responsibilities.
