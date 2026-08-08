---
status: Decided
raised: 2026-06-21
decided: 2026-06-21
deciders:
  - henrique (Navigator, via grill-with-docs in the hermes notebook)
supersedes:
related:
  - hermes ADR 0005
  - docs/project/decisions/records/2026-07-06T1505Z-absorb-hermes-adrs-into-ariad.md
---

> Migrated from the Hermes design notebook.

# ADR 0005: Timers are transition enablement semantics

## Status

Accepted

## Context

Petrus needs to represent time-based behavior such as polling intervals, delayed retries, deadlines, scheduled work, and waiting until a specific time.

Earlier discussion considered modeling timers as timer tokens, delayed token availability, schedule sources, or place-level behavior. That would put time-related semantics on places or tokens.

The corrected model is that transitions are the things that fire. Therefore, time should affect whether a transition is enabled, not whether a place is active or whether a token is available.

## Decision

Timers are declared on transitions as enablement semantics.

A transition may declare timer constraints such as:

- delay enablement by a duration;
- delay enablement until a specific time.

Time-related semantics belong in the net definition, attached to transitions. The runtime adapter controls actual clocks, durable timer scheduling, wakeups, and replay-safe delivery of time events.

There should be no time-related behavior on places.

## Consequences

- Places remain typed token locations, not schedulers or delayed queues.
- Transitions remain the only things that fire.
- Runtime adapters must provide durable support for transition timer enablement.
- The same net definition can run on different runtime adapters while preserving time semantics.
- Documentation should avoid phrases like "timer token" or "delayed place" unless explicitly discussing rejected alternatives.

## Rejected alternatives

### Timer tokens

Rejected because it makes time feel like data flowing through places rather than an enablement constraint on transitions.

### Delayed token availability on places

Rejected because it puts time semantics on places. The domain model should keep places as typed token locations.

### Runtime-only schedules outside the net

Rejected because time-based process behavior should be visible in the net definition, not hidden in the runtime adapter.
