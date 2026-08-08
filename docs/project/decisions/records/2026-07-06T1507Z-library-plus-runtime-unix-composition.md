---
status: Decided
raised: 2026-07-06
decided: 2026-07-06
deciders:
  - henrique (Navigator)
supersedes:
related:
---

# Library AND runtime, composed Unix-style; never a framework

## Question

Hermes ADR 0001 says "layered library, not framework"; the Impetus kickoff vision includes workers on multiple machines, which implies something runnable. Which is Impetus?

## Decision

Both, as separate composable artifacts — and definitely not a framework:

- **Library**: the engine packages (core semantics, schema, binding, net runtime) usable inside any host application.
- **Runtime**: a runnable, opinionated composition of those packages (server/daemon/workers) — the "tool with a runtime opinion."
- **Unix mindset**: small packages that compose; every underlying package independently recombinable. The model is the pi coding agent's package design: an opinionated tool at the top, recombinable packages underneath (others have built their own tools/frameworks from those same packages).

## Rationale

The Navigator: "For sure I am trying to build a library, but also I need to build a runtime. I don't think they are the same thing. It's definitely not a framework." This preserves hermes ADR 0001 (the library never owns the host's lifecycle) while making the distributed runtime a first-class *product of composition* rather than a framework obligation.

## Consequences

- Package boundaries are architecture: core semantics must not import runtime/server concerns.
- The runtime is one consumer among several (host apps, tests, editors, agents).
- Code-organization references to study: the pi coding agent monorepo, and the framework the Navigator mentioned built on similar composition (name to confirm — captured in ES-001).

## Review Trigger

Revisit package boundaries when the first runtime package appears and tries to reach into core internals.
