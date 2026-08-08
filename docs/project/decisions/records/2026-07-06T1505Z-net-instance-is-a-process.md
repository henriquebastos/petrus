---
status: Superseded
raised: 2026-07-06
decided: 2026-07-06
deciders:
  - henrique (Navigator)
supersedes:
superseded_by:
  - docs/project/decisions/records/2026-07-21T0809Z-concept-first-ontology-boundaries.md
related:
  - ES-001
---

# A net instance is a process; the event history is per instance

## Question

The cross-source analysis flagged "concurrent multi-worker append to one event history" as the one problem no prior source solves, and the briefing left the scope of the "single" event history unconfirmed (per instance, per deployment, or global).

## Decision

The Navigator's mental model, now adopted as a core architecture premise:

- **An agentic Petri net instance is like a Temporal workflow instance — a process.** Like OS processes of one program, many instances of the same net definition run independently, each with its own credentials, integration bridges, and configuration. There is no "huge Petri net to rule them all."
- **The event history is per instance**, like Temporal's per-workflow event history. Appends serialize within one instance; there is no global log requiring cross-machine merge.
- **Instances communicate**: spawning child instances, sending signals, sending updates — messaging between processes, not shared state.
- **Distribution = decoupling state from execution + routing.** Because an instance's state (event history + marking) is not coupled to the executing process/machine, execution can be placed and re-placed across a grid — this machine, another machine, a home server bridged to a production server. Where side effects run becomes a routing problem.

## Rationale

This is exactly what worked in production: Petrus serialized each workflow's state through one Temporal workflow instance while activities executed elsewhere. The Navigator's Temporal experience is the model: per-instance event history "feels like a call stack, a log, a trace — inputs and outputs accessible — very good for debugging, very good for replaying."

It also dissolves the analysis's hardest problem: the unsolved "concurrent append/merge" (which Beans also never solved) is not a requirement. What remains is the tractable version: guaranteeing a single writer per instance history, plus routing and delivery semantics between instances and workers.

## Consequences

- Engine design centers on: instance lifecycle, per-instance history append protocol (single-writer), inter-instance messaging (spawn/signal/update), and work routing to workers/servers.
- "Single event history" in the briefing means single *per net instance*.
- Multi-server topologies (production + home lab, bridged) are a first-class scenario for the routing layer, not an afterthought.

## Review Trigger

Superseded by the concept-first ontology decision. Its per-instance history,
isolation, messaging, and single-writer invariants remain ratified there; only
the equation of an instance with a process is retired.
