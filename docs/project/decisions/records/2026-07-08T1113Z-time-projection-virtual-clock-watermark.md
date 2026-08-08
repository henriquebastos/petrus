---
status: Decided
raised: 2026-07-08
decided: 2026-07-08
deciders:
  - henrique (Navigator, via ES-007 review)
supersedes:
related:
  - docs/project/decisions/records/2026-06-21T0630Z-hermes-adr-0005-timers-are-transition-enablement-semantics.md
  - docs/project/decisions/records/2026-07-06T0325Z-hermes-adr-0031-minimal-event-history-record-model.md
  - docs/project/decisions/records/2026-07-06T1128Z-hermes-adr-0034-event-log-distinguishes-deterministic-and-activity-records.md
  - docs/project/decisions/records/2026-07-06T1505Z-net-instance-is-a-process.md
  - docs/project/decisions/records/2026-07-07T1610Z-purity-invariant-and-projection.md
  - docs/project/decisions/records/2026-07-08T1112Z-timers-keyed-per-firing-binding-age-anchored.md
---

# Time projection: the virtual clock is the per-instance record watermark

## Question

What does "now" mean during replay? Timer maturation must be a recorded fact
that replay re-delivers deterministically rather than a wall-clock re-read —
the golden-trace corpus deferred all timed traces on exactly this. And the
purity DR's open question: is a timer maturation an external event seeded
like an ingress event, or internal?

## Decision

- **Time projection.** Timer maturation is the projection principle applied
  to the clock: the wall clock is external world state and enters the net
  **only as recorded instants** — never as an imperative read inside
  enablement. Unlike event projection it seeds no token (ADR 0005 rejected
  timer tokens); its recorded fact advances the instance's virtual clock,
  and maturation is derived purely. It is external in origin (the runtime
  adapter authors it from a real clock, as it authors ingress seeds) and
  deterministic in consequence — confirming its classification as record
  category 2, a deterministic net/runtime record [ADR 0031, ADR 0034].
- **The clock watermark.** Every event history record carries an instant
  assigned by the adapter at append time; the per-instance single writer
  [DR 2026-07-06 net-instance-is-a-process] MUST enforce monotonicity
  (clamp). The instance's **clock watermark** is the instant of the latest
  appended record. "Now", everywhere the net runtime needs it — live and
  during replay — is the watermark: `matured?(binding) = watermark ≥
  mature(binding)`. Semantic time is discrete and advances only at appends;
  wall time is the adapter's private business.
- **Any record advances the clock.** An external event recorded at instant X
  also matures every binding with maturation ≤ X, with no timer-matured
  record needed — the history proves time reached X. (Rejected alternative:
  gating maturation on explicit per-binding maturation records — it turns a
  pure derivation into per-binding adapter bookkeeping and models a clock
  lagging its own log.)
- **Wakeup protocol.** After each append/marking change the net runtime
  derives `nextMaturation` (minimum maturation instant over
  enabled-but-for-timer candidate bindings) and hands it to the adapter; the
  adapter durably schedules a real-clock wakeup and, on wakeup, appends a
  **timer matured** record carrying at least `{maturationInstant,
  observedInstant}` (record instant = `observedInstant` ≥
  `maturationInstant`). Late or spurious wakeups are harmless (a stale
  record matures nothing); the adapter MAY suppress appending when nothing
  derives matured.
- **Replay** re-applies records in order, reconstructing the watermark from
  record instants; maturations re-derive identically; the adapter schedules
  no wakeups and reads no clock. Petrus's "matured honored only if still
  enabled" becomes derived behavior, and the deadline-recompute vs
  delay-restart replay distinction dissolves (both timer forms are pure
  comparisons of the watermark against recorded anchors).

## Rationale

This is the contract Temporal provided the Petrus production system silently
(timers as recorded TimerStarted/TimerFired pairs; workflow time read from
history; "Timers are recorded as events and don't 'wait' again during
replay" — ES-007 sources), made explicit and adapter-agnostic per ADR 0012:
any adapter that can stamp monotone instants and wake durably at a requested
instant can host timed nets. One piece is new rather than extracted: Impetus
timers are declared, not imperatively requested, so the net runtime derives
what to schedule instead of being told.

## Consequences

- Timed golden-trace fixtures are byte-stable scripts: instants on inputs,
  scripted timer-matured steps, category-2 expected records
  (`spec/traces/README.md` deferral lifted; corpus regeneration is follow-up
  work per ES-007 Part 3).
- The timer-matured payload sketch feeds the ADR 0031 payload-schema OPEN;
  a binding reference is deliberately not required in the record.
- ES-006 receives the derived `nextMaturation` object and the constraint
  that quiescent-with-live-timer is sleeping, not terminated.

## Review Trigger

Revisit if an adapter genuinely cannot guarantee monotone append instants,
or if a use case needs sub-append time resolution inside one instance.
