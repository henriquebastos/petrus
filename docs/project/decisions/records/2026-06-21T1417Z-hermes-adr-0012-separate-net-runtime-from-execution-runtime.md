---
status: Decided
raised: 2026-06-21
decided: 2026-06-21
deciders:
  - henrique (Navigator, via grill-with-docs in the hermes notebook)
supersedes:
related:
  - hermes ADR 0012
  - docs/project/decisions/records/2026-07-06T1505Z-absorb-hermes-adrs-into-ariad.md
  - docs/project/decisions/records/2026-07-14T2016Z-activity-invocation-runtime-seam.md
---

> Migrated from the Hermes design notebook.

> Partially superseded 2026-07-14 by
> `2026-07-14T2016Z-activity-invocation-runtime-seam.md`: the core separation
> stands, but the execution runtime executes Petri-agnostic activity
> invocations, not handlers. The handler stays server-side, preparing the
> activity before dispatch and projecting its frozen result before end firing;
> the Notes flow below ("execution runtime runs handler → handler result")
> describes the shipped synchronous compatibility seam.

# ADR 0012: Separate net runtime from execution runtime

## Status

Accepted

## Context

Earlier layer descriptions used a single broad "runtime" term. That is too vague.

Petrus needs a runtime responsible for Petri-net semantics and state progression, and it also needs execution substrates that run handlers, activities, workers, retries, timeouts, and distributed work. Temporal is an example of an execution runtime, but the Petri-net runtime remains a Petrus concept.

A previous implementation also found several core infrastructure concepts useful:

- **marking** as a first-class representation of token distribution;
- **net path** as a dotted/address-like way to identify nodes inside nested nets or grouped subnets;
- **flattened net** as an optimized internal representation where nested/subnet structure is compiled into a flat set of addressed places, transitions, and arcs.

## Decision

Petrus should distinguish:

- **Net runtime** — Petrus-owned runtime for validating net definitions and bindings, managing net instances and markings, computing enabled firing candidates, applying scheduler decisions, and performing begin/end firing semantics.
- **Execution runtime** — substrate for executing handlers and activities, such as local inline/concurrent execution, Temporal, worker queues, distributed workers, or other external execution systems.

The formal/core model should include marking as a first-class concept.

Petrus should include a concept of net path for addressing nodes in nested/composed nets, and may compile composed nets into a flattened net for efficient execution and simpler internal lookup.

## Consequences

- "Runtime" should be qualified in documentation as net runtime or execution runtime when precision matters.
- Temporal should be modeled as an execution runtime or execution adapter, not as the Petrus net runtime itself.
- The net runtime remains responsible for Petri-net correctness even when handler execution is delegated elsewhere.
- Net path enables reusable components, subnets, stable binding addresses, arc construction, diagnostics, and tooling.
- Flattening allows ergonomic nested composition while preserving efficient execution.

## Notes

The net runtime may call into an execution runtime when a selected firing attempt requires a handler. The execution runtime reports handler results back; the net runtime then performs `endFiring` and advances the marking.

```txt
net definition + bindings
→ net runtime validates/instantiates
→ marking
→ enabled firing candidates
→ scheduler selects candidates
→ beginFiring
→ execution runtime runs handler
→ handler result
→ endFiring
→ new marking
```
