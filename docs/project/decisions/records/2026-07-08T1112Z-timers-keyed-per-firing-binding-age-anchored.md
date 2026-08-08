---
status: Decided
raised: 2026-07-08
decided: 2026-07-08
deciders:
  - henrique (Navigator, via ES-007 review)
supersedes:
related:
  - docs/project/decisions/records/2026-06-21T0630Z-hermes-adr-0005-timers-are-transition-enablement-semantics.md
  - docs/project/decisions/records/2026-07-08T1113Z-time-projection-virtual-clock-watermark.md
---

# Timers are keyed per firing binding, anchored to recorded token entry

## Question

ADR 0005 declares timers on transitions but leaves their scoping undefined.
The Petrus oracle keys timers by transition path — one clock per timed
transition — explicitly acknowledging that concurrent independent timers for
the same transition are out of scope. That breaks when a transition is
enabled under multiple concurrent firing bindings, each needing its own
maturation (three offers in `pending`, each expiring 24h after *its*
arrival). What is the correct keying: per transition path, per enablement
epoch, per firing binding, or per token age?

## Decision

- **Keying.** A transition timer is declared on the transition [ADR 0005] but
  **evaluated per firing binding**. Its identity is (timer declaration
  NetUri, firing binding); a binding's identity is its per-arc token
  assignment. In the Time Petri net literature's terms this is
  multiple-server **age semantics** (ES-007 sources: Bérard et al. 2005;
  Boucheneb et al. 2015), with the clock basis borrowed from Timed-Arc nets'
  per-token ages — recast so tokens carry no live clocks, only ordinary
  recorded history.
- **Anchor.** A duration timer (`delay Δ`) matures a binding at
  `anchor(binding) + Δ`, where `anchor(binding)` is the **youngest recorded
  entry instant** among the binding's consume/read-bound tokens (the instant
  each token entered its arc's source place, already a recorded fact — token
  production, ingress seed, or initial marking). An absolute timer
  (`until D`) matures every binding at `D`. Inhibitor arcs contribute no
  anchor; a duration timer on a transition whose input arcs are all
  inhibitors is a validation error (absolute timers remain legal there).
- **Derived, never stored.** The net runtime keeps no durable per-binding
  timer objects: maturation instants are a pure function of net definition,
  marking, and recorded history, evaluated during candidate computation as
  enabledness condition 5. The adapter's only durable obligation per
  instance is a wakeup at the derived `nextMaturation` (see the companion
  time-projection record).
- **No urgency.** Maturation *enables*; Candidate Selection chooses at most one
  enabled Binding within `BeginCandidate`, while whole-action `DrivingPolicy`
  decides whether that action proceeds [ADR 0008, ADR 0009, DR 2026-07-22
  candidate-selection-is-instance-scoped-immutable-policy]. There is no
  Merlin-Farber-style latest-firing-time obligation; deadline pressure is
  modeled structurally (racing timeout transitions).

## Rationale

Enabledness, candidates, scheduling, and firing attempts are already
per-binding; per-binding timers make time just another enabledness condition
instead of a stateful side-mechanism. Anchoring to recorded token entry makes
maturation replay-derivable with no clock-reset (memory-policy) bookkeeping —
the I/A/PA machinery exists precisely to manage mutable per-transition
clocks, and dissolves when there are none. Full analysis of the rejected
options (transition path, enablement epoch, arc/token ages) in ES-007's
proposal artifact.

## Consequences

- **Deliberate divergence from the Petrus oracle:** delay does **not**
  restart per enablement epoch. A binding matures Δ after its tokens
  arrived, regardless of guard/inhibitor flapping in between. Restart
  semantics is expressible structurally: route the token through a refresh
  transition (production mints a new entry instant). Deadline-mode
  recompute-from-the-same-instant behavior survives exactly.
- **Dependency surfaced:** tokens need stable identity in the event history
  (binding keys and entry-instant anchors require it) — carried to the
  ADR 0031 payload-schema OPEN.
- Aggregate tokens compose trivially (one token, one entry instant);
  same-multiset assignment permutations derive identical instants, so their
  aliasing is harmless.
- Timed golden-trace fixtures for concurrent bindings pin Impetus contract,
  not oracle fidelity (Petrus cannot express them).

## Review Trigger

Revisit if a use case genuinely needs continuous-enablement (threshold)
delay semantics that the refresh-transition pattern cannot express cleanly,
or if token identity proves unavailable in the history record model.
