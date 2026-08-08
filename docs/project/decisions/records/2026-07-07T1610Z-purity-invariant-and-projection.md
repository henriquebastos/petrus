---
status: Superseded
raised: 2026-07-07
decided: 2026-07-07
deciders:
  - henrique (Navigator)
supersedes:
superseded_by: docs/project/decisions/records/2026-07-08T1601Z-source-transition-ingress.md
related:
  - docs/project/decisions/records/2026-07-07T1600Z-arc-filters-and-guards-cel-or-named-both-pure.md
  - docs/project/decisions/records/2026-06-21T0800Z-hermes-adr-0007-handled-transitions-use-begin-end-firing-attempts.md
  - docs/project/decisions/records/2026-06-21T0617Z-hermes-adr-0004-deterministic-execution-records-external-results.md
---

# Purity invariant: impurity lives only in handlers; external state enters by projection

> **Superseded 2026-07-08** by [DR source-transition-ingress]. The purity
> invariant, the projection principle, and state projection are carried forward
> unchanged; only the ingress *mechanism* changed — external events now enter
> through a **source transition** (handler produces the tokens), not by the
> runtime seeding an ingress place, and environment/source transitions are no
> longer rejected (they are the ingress model, excluded from auto-scheduling).

## Question

If arc filters and guards are pure [DR arc-filters-and-guards], how does a net
ever depend on the outside world — "fire only if the account is verified", "only
when the git tree is clean", "when this webhook arrives"? And how is that done
without breaking deterministic replay?

## Decision

- **Purity invariant.** Arc filters and transition guards are **pure**: they
  compute a boolean from token data with no side effects and no external reads.
  **All impurity — every external call, side effect, and non-deterministic read —
  lives in transition handlers.** A handler's observed result is recorded as a
  fact and reintroduced as tokens [ADR 0007, ADR 0004], so replay never re-runs
  it. A handler may orchestrate one or many activities; that is execution-runtime
  flexibility, not net semantics.
- **Projection (principle).** External world state and events enter a net
  **only as tokens in the marking**, never as imperative reads inside filters or
  guards. Gating on external conditions is therefore structural (a pure filter,
  an inhibit arc, a control place), because the condition is already a token.
- **Event projection (primitive).** A discrete external event (webhook, signal,
  poll result, human decision) enters the net when the runtime **seeds a token
  into a designated ingress place**; a normal transition consuming that place is
  the trigger, gated by ordinary net structure (a control place for an on/off
  switch, or an inhibitor). The seed is itself an **external event** and is
  recorded, so replay re-injects it deterministically.
- **Environment-transition ingress is rejected.** A transition with no input arc
  is vacuously always enabled, so gating *when* it may fire requires bolting on a
  control/inhibitor place anyway — at which point it is just an awkward normal
  transition. Seeding an ingress place directly is simpler and keeps all gating
  in the normal net. (Confirmed by Petrus production practice: environment
  transitions were not used; the runtime seeded a place and a control place
  modeled the switch.)
- **State projection (pattern).** A standing external condition (tree-clean,
  account-verified) is kept mirrored as a token in a place, refreshed by repeated
  event projections when the world changes (a watcher/poller handler updates it).
  It is not a new mechanism — it is event projection used to maintain a mirror —
  so filters/inhibit arcs can gate on current state purely.

## Rationale

Pure filters/guards can be re-evaluated freely, any number of times, during any
scheduler pass and on replay, with no nondeterminism to journal — the one replay
hazard velocitron's impure guards carry. Projection is the generalization of the
webhook→signal→seed pattern already proven in Petrus/Temporal, extended to
standing state (velocitron/uharness ADR 0007 "projection over guards"). Together
they yield one clean invariant: **enablement is always replay-deterministic
because the world only ever enters as recorded tokens.**

## Consequences

- Named filter/guard symbols must honor a purity contract the binding layer can
  flag; impure logic must be a handler.
- Ingress is modeled as "seed a token into a place" and recorded as an external
  event (`event-history.md`); the net needs an ingress-place + control-place
  idiom rather than always-enabled environment transitions.
- Divergence from velocitron (impure guards permitted) to align with Matt; and a
  question for Matt on how uharness realizes projection (environment transition
  vs seeded place).

## Review Trigger

Revisit if a use case genuinely needs an enablement decision that cannot be
expressed as a pure function of the marking plus projected tokens.
