# Roadmap

Roadmap items carry their own status and preserve durable technical direction.
CV10.DS4 completed one hermetic single-host retained-territory custody and
reconciliation route. CV10.DS1–DS4 now cover one Episode-owned Gondolin
lifecycle, Local Activity and Worker borrowing, terminal replay, and exact
retained lease reclaim or retirement. Activity never owns territory lifecycle,
and no live provider or multi-host support is claimed.

## Retained Values

- CV1–CV4 and CV6: language-neutral foundations, Python kernel, runtime
  topology, Ariad/runtime integration, and first-version runtime convergence.
- CV5/Fabric: unfinished prototype call/spawn demonstrations retained as
  evidence only. Fabric is subject to rewrite and is not a completed or
  supported capability.
- CV8: production local Activity execution, optional ZeroMQ transport, async
  Activities, async-native Worker custody, and one provider-neutral logical
  execution with bounded durable retries, deadlines, and terminal-failure
  projection/recovery. Shared Workers preserve authorizing Instance scope and
  may resolve host-composed scoped implementations without changing the simple
  default or Inline paths. First-class lifecycle scopes canonically close or
  atomically reset exact work generations, then install recoverable operational
  cancellation fences while preserving unscoped behavior.
- CV10: composable execution. CV10.DS1–DS4 qualified one hermetic,
  Episode-owned Gondolin lifecycle, host-local Activity execution, Local
  Worker terminal replay, and private single-host retained lease
  reconciliation. Live-provider and network/multi-host work remains blocked or
  unbounded.
- CV11–CV15: semantic observation, durable captures, long-History navigation,
  canonical Net inspection, and bounded simulation.
- CV16: Agenticus infrastructure and one supported scripted Pi A2 Local host
  lifecycle. Live-provider profiles remain qualification-only or unsupported.
- CV17–CV18: hosted bounded simulation and portable canonical Net definitions.

## Planned Values

- [CV19 — Deterministic simulation testing](cv19-deterministic-simulation-testing/index.md):
  DS1 has frozen the correctness and strict replay contracts and proved one
  production projection-crash recovery from portable data. DS2 is next: turn
  Petrus's replayable History, injected clock and Dispatch seams, bounded
  simulation, property tests, and explicit crash-cut evidence into a seeded,
  replayable fault-simulation discipline over production runtime logic. Petrus
  owns the reusable substrate; applications such as Hamsterdan own their domain
  models and provider fault worlds.

Application-specific and site-operation plans are not part of this source
tree.

## Structure and states

Use the simplest Ariad hierarchy that fits: Value (`CV<N>`), Delivery Story
(`DS<N>`), User Story (`US<N>`), Technical Story (`TS<N>`), Task, or
Maintenance. Item status is one of `Planned`, `Active`, `Blocked`, `Validated`,
`Done`, `Deferred`, or `Dropped` and belongs in the item's own metadata.

Find work by searching item metadata. `Active` means an actual current working
session; `Blocked` and `Planned` remain visible even when no session is active.

## Item template

```markdown
---
code: CVX.DSY.USZ
level: Value | Delivery Story | User Story | Technical Story | Maintenance
status: Planned
status_reason:
updated: YYYY-MM-DD
related: []
---

# Item title

## Intent
## Scope
## Acceptance / Done Condition
## Driver QA and Evidence Plan
## Out of Scope
## Notes
```
