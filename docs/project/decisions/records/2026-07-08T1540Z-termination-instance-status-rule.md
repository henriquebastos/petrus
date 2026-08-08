---
status: Decided
raised: 2026-07-08
decided: 2026-07-08
deciders:
  - henrique (Navigator)
supersedes:
related:
  - docs/project/decisions/records/2026-07-02T0843Z-hermes-adr-0027-place-roles-are-optional-annotations.md
  - docs/project/decisions/records/2026-07-07T1610Z-purity-invariant-and-projection.md
  - docs/project/decisions/records/2026-07-06T1505Z-net-instance-is-a-process.md
  - docs/project/decisions/records/2026-07-07T2118Z-permissive-flow-defaults.md
  - docs/project/decisions/records/2026-07-08T1112Z-timers-keyed-per-firing-binding-age-anchored.md
---

# Termination: derived instance status (RUNNING / AWAITING / COMPLETED / STUCK)

> **Amended 2026-07-08** by [DR source-transition-ingress] — mechanism only, the
> decision stands. Wherever this record says a registration means the runtime
> "may seed tokens into an ingress place," read "may **deliver an external event
> to a source transition**." The AWAITING marker is an armed registration on an
> unsealed source transition; all four-valued status machinery is unchanged.

## Question

When a net instance is quiescent (nothing enabled), is it DONE or WAITING for
an external event not yet seeded? The Petrus oracle answered with a semantic
`awaiting` place interface; ADR 0027 made place roles non-semantic, so the
rule must be re-derived without them (`firing-semantics.md` §Termination
OPEN).

## Decision

An instance's status is a **derived, four-valued projection over recorded
history** — never stored as independent truth [ADR 0033]:

- **Quiescent** (the trigger, not a verdict): no enabled firing candidate;
  no firing attempt begun but not ended [ADR 0007]; no firing binding with a
  derived future timer maturation
  [DR timers-keyed-per-firing-binding-age-anchored].
- **Completion condition**: an optional net-level declaration — a **pure
  marking predicate** (inline CEL or named pure symbol, same tier as guards
  [DR arc-filters-and-guards]), canonical NetUri `#completion` on the net.
  It **never affects enabledness or firing** (ADR 0027 discipline applied to
  a net declaration); validation run checks resolvability/embodiment.
- **Event-projection registration**: a binding/runtime-layer record that the
  runtime may still seed tokens into an ingress place of this instance
  (webhook subscription, poller, human-task handle, child-instance signal).
  A runtime connection counts **iff it can seed a token**; anything else
  (credentials, pools, leases) is operational [ADR 0035] and irrelevant to
  status. Registration open/close are recorded process facts in the event
  history.
- **Status**: RUNNING if not quiescent; else COMPLETED if the declared
  condition holds; else AWAITING if any registration is armed; else STUCK
  (condition declared) or TERMINATED (neutral collapse when no condition is
  declared — permissive default; validators MAY warn that done-vs-stuck is
  then indistinguishable).

Place roles play no part. The Petrus awaiting-place idiom remains legal
ordinary structure; the engine's status rule never reads it.

## Rationale

The `awaiting` knowledge Petrus mirrored into the marking already exists at
its source: the runtime's registration set — per-instance, semantic,
validated, and required anyway to deliver events [DR
net-instance-is-a-process]. Completion is declared, not inferred (Temporal
precedent; structural inference is the role/shape trap). Eleven boundary
scenarios (ES-006 `a6`) show each ingredient failing alone and the
composition covering all cases, including status flips driven purely by
registration lifecycle (S11).

## Consequences

- `spec/firing-semantics.md` §Termination OPEN is closed; `net-schema.md`
  gains the `#completion` declaration; `event-history.md` notes registration
  open/close records (payload shape folds into the ADR 0031 opens).
- Status must be re-evaluated on **any** history append, including
  registration close — not only marking changes.
- Halt-on-complete / finalization are runtime policy, never net semantics
  [ADR 0008].
- The `awaiting_termination` golden fixture pins the oracle's role-based
  rule and joins the tracked oracle-divergence debt.

## Review Trigger

Ratified with a partial picture — the Navigator expects implementation to
reveal details. Revisit when the kernel implements any of: (1) the
registration lifecycle/API shape; (2) a concrete case where an adapter-level
fact that cannot seed tokens still deserves status influence (e.g. "source
drained"); (3) a need for a FAILED status distinct from STUCK; (4)
cross-instance status composition (parent/children). None of these may
silently extend the rule — each returns here.
