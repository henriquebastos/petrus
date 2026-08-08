---
status: Superseded
raised: 2026-07-08
decided: 2026-07-08
deciders:
  - henrique (Navigator)
supersedes: docs/project/decisions/records/2026-07-07T1610Z-purity-invariant-and-projection.md
superseded_by: docs/project/decisions/records/2026-07-14T1806Z-source-delivery-projection-and-identity.md
related:
  - docs/project/decisions/records/2026-07-08T1540Z-termination-instance-status-rule.md
  - docs/project/decisions/records/2026-06-21T0842Z-hermes-adr-0010-no-handler-default-behavior-is-passthrough-only.md
  - docs/project/decisions/records/2026-07-07T1700Z-output-production-per-arc-contract-handler-supplies-tokens.md
  - docs/project/decisions/records/2026-06-21T1417Z-hermes-adr-0012-separate-net-runtime-from-execution-runtime.md
  - docs/project/decisions/records/2026-07-08T1113Z-time-projection-virtual-clock-watermark.md
---

# External events enter through source transitions, not runtime place-seeding

## Question

[DR purity-invariant-and-projection] modeled discrete external-event ingress
as the runtime **seeding a token directly into an ingress place**, and
explicitly **rejected** environment/source transitions (no-input transitions)
as "vacuously always enabled." Revisiting Petrus showed source transitions are
actually the natural mechanism: token production is the *return of a handler*
on the source transition, and the transition is a first-class, addressable,
typed net element — better than an out-of-band poke at the marking. What is the
ingress mechanism?

## Decision

This record **supersedes** [DR purity-invariant-and-projection], carrying its
invariants forward unchanged and replacing only the ingress *mechanism*.

**Carried forward, unchanged:**

- **Purity invariant.** Arc filters and transition guards are pure; **all
  impurity lives in transition handlers**; a handler's observed result is
  recorded and reintroduced as tokens so replay never re-runs it.
- **Projection (principle).** External world state and events enter a net
  **only as tokens in the marking**; gating on external conditions is
  structural (pure filter, inhibit arc, control place), because the condition
  is already a token.
- **State projection (pattern).** A standing external condition is a token in
  a place, refreshed by repeated ingress when the world changes.

**Changed — the ingress primitive:**

- **A source transition is the entry point for external events.** A **source
  transition** has no input arcs. A discrete external event (webhook, signal,
  poll result, human decision, child-instance message) is delivered by the
  runtime to a specific source transition; the transition's **handler** turns
  the delivered payload into typed token(s); its **output arcs route** those
  tokens by color/destination into places [DR output-production...]. From
  there, ordinary net flow. This puts the impure external read in a handler —
  where the purity invariant says it belongs — instead of an out-of-band
  runtime place-seed.
- **Source transitions are excluded from the scheduler's enabled-candidate
  set.** They are *not* auto-scheduled and never fire spontaneously; they fire
  **only on external delivery** [ADR 0008]. This removes the "vacuously always
  enabled" objection that motivated the earlier rejection: the outside world
  gates *when* a source transition fires by delivering (or not), so no
  control/inhibitor place is needed to gate it.
- **General ingress + typed output arcs demultiplex for free.** One general
  source transition whose handler emits mixed event tokens routes them to
  different places by the output arcs' color contracts; tokens no arc admits
  are leftover [DR permissive-flow-defaults]. No new machinery.

**Environment-transition ingress is no longer rejected** — it is the ingress
model, under the scheduler-exclusion discipline above.

## Interaction with termination [DR termination-instance-status-rule]

The termination rule's machinery is unchanged; only what a registration is
armed on changes. An **event-projection registration** now records that the
runtime may still **deliver an external event to a source transition** of this
instance (was: seed a token into an ingress place). An armed registration is
the *AWAITING* marker. This is strictly better: the awaiting marker is now a
first-class net element (an unsealed source transition with an armed
registration), a **structural** property — not a place role — so it honors
[ADR 0027] the same way, while being more grounded than "the runtime may seed
some place." Status stays a four-valued derived projection; re-evaluated on any
history append including registration close.

## Consequences

- Time ingress is unaffected: continuous time enters via the clock watermark
  [DR time-projection-virtual-clock-watermark], not a source transition — two
  distinct projection mechanisms, both recorded, both replay-deterministic.
- `spec/net-schema.md` gains **source transition** (structural: no input arcs;
  external-triggered; scheduler-excluded). `spec/firing-semantics.md`
  enabledness/scheduling note the exclusion; the §Termination registration
  wording changes to "deliver to a source transition." `spec/event-history.md`
  and `CONTEXT.md` (Event projection, Event-projection registration, new Source
  transition entry) updated. [DR termination-instance-status-rule] gains an
  amendment note (mechanism only; its decision stands).
- The `environment_signal` golden fixture (oracle `fire_env`) already sits in
  the oracle-divergence debt; a source-transition ingress fixture is designable
  once a kernel exists.
- The source transition's handler is impure (reads the delivered event) and its
  result is recorded (external event → source-transition firing → handler result
  → tokens produced), keeping replay deterministic.

## Review Trigger

Revisit when the kernel implements the delivery/registration API — specifically
how a delivered payload reaches the source transition's handler, and how a
source transition is sealed (registration closed) to let the net terminate.
