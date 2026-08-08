---
status: Decided
raised: 2026-06-21
decided: 2026-06-21
deciders:
  - henrique (Navigator, via grill-with-docs in the hermes notebook)
supersedes:
related:
  - hermes ADR 0003
  - docs/project/decisions/records/2026-07-06T1505Z-absorb-hermes-adrs-into-ariad.md
---

> Migrated from the Hermes design notebook.

# ADR 0003: Transitions have bindings, not implementation kinds

## Status

Accepted

## Context

During early modeling, terms such as polling transition, webhook transition, human transition, agent transition, and activity transition were used. This polluted the Petri-net model with implementation categories.

The intended separation is stronger: the net definition should remain declarative and stable while implementation details can be swapped independently.

## Decision

A transition is just a transition in the Petri-net model.

The net definition may name a transition and describe its places, arcs, token contracts, guards, timers, and semantic role in the process. It should not classify transitions by handler implementation kind.

Implementation behavior is connected through bindings. A transition may be bound to a handler implemented with deterministic code, an agent, a human interaction, browser automation, a Temporal activity, a webhook adapter, a polling function, or any other callable mechanism.

## Consequences

- Net definitions remain portable across handler implementations.
- Changing a handler implementation should not require changing the net definition unless the process meaning changes.
- Runtime adapters can schedule and invoke handlers without requiring the core net model to know whether the handler is human, agentic, local, remote, deterministic, or side-effecting.
- Documentation should use phrases like "transition bound to a Slack polling handler" rather than "Slack polling transition" when precision matters.
