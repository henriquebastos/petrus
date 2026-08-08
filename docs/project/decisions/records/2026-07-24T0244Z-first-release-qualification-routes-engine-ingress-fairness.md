---
status: Decided
raised: 2026-07-24
decided: 2026-07-24
deciders:
  - henrique (Navigator)
supersedes:
  - DEC-003's open ingress-starvation qualification question
  - DEC-013's open provider retry-reconciliation qualification question
related:
---

# First-release qualification routes resident-Engine ingress fairness

## Question

Do the two bounded release probes close with current behavior, or do they earn
new runtime/provider work? If ingress work is required, what architecture may
its Technical Story assume before choosing an exact API?

## Decision

Accept the completed first-release qualification evidence and its **NO-GO**
release conclusion. DEC-003's maintained standing-cadence probe demonstrates
consequential starvation: an armed identified delivery remains unconsulted and
absent from every Snapshot while recurring timer work remains available. Route
the smallest separate Engine ingress-fairness Technical Story and keep the
release qualification NO-GO until that story and the affected gates
pass.

Close DEC-013 for the bounded idempotent-effect or lookup-first provider
contract. Its real PostgreSQL/Absurd SIGKILL trace proves one external effect
and one canonical terminal outcome across two at-least-once provider runs. It
does not earn a universal result cache, qualify nondeterministic model results,
or claim exactly-once effects.

The Engine story starts with these Navigator-ratified constraints:

- Engine remains the concrete resident composition around one Instance in its
  host process. Do not introduce an Engine Worker or universal Engine-task
  queue by analogy with Temporal.
- One serialized advancement lane continues to own canonical state mutation.
  Advancement must return control rather than monopolize a standing host.
- Keep the deterministic core synchronous. An asynchronous host shell may
  multiplex HTTP, broker input, result notifications, timers, and several
  distinct Engines; do not convert the repository wholesale to asyncio or
  permit awaits inside deterministic projection or an open canonical
  transaction.
- Direct delivery is a fast canonical acceptance door, not necessarily the
  complete external operation. A webhook may deliver only an identifier whose
  resulting token enables a separately dispatched Activity to fetch details.
- Scheduled polling remains explicit author-owned net structure initially:
  the author defines the control/cursor place, timer, Activity transition,
  rearm, inhibition, and stop behavior. Do not add timed-source syntax, hidden
  cadence places, or first-class recurring source semantics in this story.

The exact bounded-turn unit, Clock/wake contract, Sensor disposition,
`Engine.wait` disposition, default `DrivingPolicy` fairness, and public API
changes remain unresolved until the story's Plan Checkpoint.

## Rationale

The qualification threshold was fixed before execution. The Liaison trace
meets it on maintained structure, not on a synthetic loop: the Coordinator
consults Sensor only after all other actions disappear, while the polling
cadence always provides another maturation action. Candidate Selection and
`DrivingPolicy` cannot repair an ingress action that never enters the
Snapshot.

Navigator discussion separated canonical acceptance from subsequent external
work. A resident Engine can commit a small pushed envelope and dispatch any
blocking fetch as an Activity. Pull polling is already expressible honestly by
a timed transition consuming and reproducing an explicit cursor/control token.
This avoids hidden recurrence state and leaves the cadence's anchor, overlap,
pause, cursor, and termination visible in the Net.

Coroutine syntax does not itself provide fairness: an async advancement loop
without a yield can monopolize a host exactly like synchronous code. The
behavioral requirement is bounded, non-waiting advancement. Asyncio is an
optional host implementation strategy, not Petrinet or Engine semantics.

## Options Considered

- **Reclassify Sensor as intentionally quiescence-only and require direct
  delivery for standing hosts.** Rejected for this release because it would
  redirect the precommitted consequential threshold after maintained evidence
  met it.
- **Consult a potentially blocking Sensor before every firing.** Rejected:
  external waiting must not occur inside each deterministic Engine turn.
- **Introduce Temporal-like Engine Workers and activation queues.** Rejected:
  Impetus Engine already owns deterministic net advancement and canonical
  authorship in the resident host; Activity Workers remain the separate
  external-execution role.
- **Convert Engine and kernel APIs wholesale to asyncio.** Rejected because it
  neither guarantees yielding nor preserves a simple embeddable deterministic
  core.
- **Add timed source transitions now.** Deferred. Repeated real authoring must
  first prove stable desugaring beyond the explicit control-token pattern.
- **Add a universal Activity-result ledger.** Rejected by the DEC-013 provider
  evidence and the prior portfolio ruling.

## Consequences

At decision time, first-release qualification was Done as an assessment but
release qualification remained NO-GO. The routed Technical Story had to
present a separate Plan Checkpoint before production mutation, preserve
History schema 4 and exact bytes, and rerun the DEC-003 probe plus integrated
qualification gates.

The story may revise the earlier `Engine.wait`/blocking-Clock implementation
only as evidence requires; it does not reopen provider-neutral Engine identity,
one-Instance ownership, writer-fence privacy, Dispatch's Activity-custody
boundary, or Fabric separation.

## Implementation outcome — 2026-07-24

The Navigator accepted the correction and its evidence. Engine/Coordinator now
apply at most one normal Action per turn after finite first-load
reconciliation, observe already-available Sensor ingress without blocking,
return `ready` and `next_maturation` for host-owned pacing, and use shipped-
policy alternation to preserve bounded ingress and internal progress. The
positive standing-cadence witness passes, as do the complete frozen suite and
maintained CV3/CV5, ES-014, and ES-043 demonstrations. History schema 4 and
bytes, provider SQL, dependencies, and lockfile remain unchanged.

The DEC-003 starvation blocker is therefore resolved. A subsequent maintained-
host audit earned a distinct pre-deployment blocker: every operational host
must converge on public Engine doors without exposing private coordination.
owns the remaining API evidence and does not retroactively expand this
decision or the validated fairness story.

## Review Trigger

Revisit the architecture constraints only if the story's executable pressure
tests show that a resident serialized Engine cannot provide bounded ingress
progress without a different host topology. Revisit timed-source convenience
only after repeated authored polling nets exhibit one stable explicit pattern
whose lifecycle can be desugared without hidden semantic state.
