---
status: Decided
raised: 2026-06-21
decided: 2026-06-21
deciders:
  - henrique (Navigator, via grill-with-docs in the hermes notebook)
supersedes:
related:
  - hermes ADR 0006
  - docs/project/decisions/records/2026-07-06T1505Z-absorb-hermes-adrs-into-ariad.md
---

> Migrated from the Hermes design notebook.

# ADR 0006: Support consume, read, and inhibitor arcs in the core

## Status

Accepted

## Context

Petrus needs to model colored-token dataflow explicitly without falling back to hidden global context. Transitions should become enabled based on tokens available through explicit input arcs, arc inscriptions, guards, and token/firing bindings.

Some tokens represent work items that should be consumed when a transition fires. Other tokens represent stable facts, policies, credentials, or configuration that must participate in enablement but should not be consumed. Petrus also needs a way to prevent transitions from firing when certain tokens exist, which is important for avoiding races and representing absence-based constraints.

A possible reserve arc mode was discussed, but current thinking is that reservation, retries, timeouts, and side-effect execution tracking belong to the runtime adapter rather than the formal net model.

## Decision

Petrus core should support these input arc modes from the beginning:

- **Consume arc** — requires matching token(s) and consumes them when the transition fires.
- **Read arc** — requires matching token(s) for enablement and token/firing binding, but does not consume them.
- **Inhibitor arc** — requires that no matching token exists for the transition to be enabled.

Petrus should not add reserve arcs to the core at this stage. Handler execution claims, retries, timeouts, leases, and side-effect tracking are runtime adapter responsibilities.

## Consequences

- Shared facts such as engineering conventions, active credentials, repository policy, and project configuration can be modeled explicitly without being consumed.
- Absence constraints and race-prevention rules can be represented in the net through inhibitor arcs.
- Dependencies remain visible in the net instead of hidden behind global lookup.
- Runtime adapters still need robust execution tracking once a transition firing invokes a handler.
- The design keeps the formal net smaller while leaving room to revisit reservation semantics if concrete cases require them.

## Rejected or deferred alternatives

### Global latest-by-type lookup

Rejected as a core mechanism because it creates invisible dependencies and ambiguous behavior when many tokens of the same type exist.

### Reserve arcs

Deferred. Reservation appears to be more about runtime execution, leases, retries, and side-effect safety than about Petri-net enablement semantics.
