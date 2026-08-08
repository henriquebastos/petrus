---
status: Decided
raised: 2026-06-21
decided: 2026-06-21
deciders:
  - henrique (Navigator, via grill-with-docs in the hermes notebook)
supersedes:
related:
  - hermes ADR 0001
  - docs/project/decisions/records/2026-07-06T1505Z-absorb-hermes-adrs-into-ariad.md
---

> Migrated from the Hermes design notebook.

# ADR 0001: Petrus is a layered library stack, not a framework

## Status

Accepted

## Context

Petrus is intended to help build durable agentic processes. The design should support high-level defaults while still letting users adapt or replace individual pieces.

A framework owns the user's code and constrains execution inside its lifecycle. Petrus should instead provide composable libraries that users can assemble in their own host applications, daemons, workflows, CLIs, or services.

The project still needs more than a pure Petri-net core. Practical systems need runtime adapters, handlers, workers, integrations, human review, polling, webhooks, sandboxes, agents, and reusable subnets.

## Decision

Petrus will be designed as a layered library stack rather than a framework.

The stack should include separable layers such as:

- formal Petri-net core;
- net definition / schema DSL;
- binding layer;
- runtime adapters;
- worker / handler execution support;
- reusable integration subnets;
- default bindings and convenience process entry points.

The host application lifecycle, deployment model, HTTP server, CLI, UI, worker process, queue, storage choice, and external integration configuration remain host/application concerns unless explicitly opted into through a composable package.

## Consequences

- Petrus can provide batteries-included defaults without forcing users into a closed lifecycle.
- Users can start with local in-process execution and later move to Temporal, remote workers, or another adapter.
- The architecture must keep boundaries explicit between net definition, bindings, runtime adapter, and convenience process composition.
- Documentation must resist describing Petrus as a single app framework.
