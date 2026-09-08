# 1 Roadmap

Each item owns its status, scope, and acceptance evidence. Start with the
[project briefing](../briefing.md) for an overview. Read the linked item before
using an older milestone as evidence of current support.

## 1a Current work

| Work | Owning record |
| --- | --- |
| Developer experience and the remaining live-understanding work | [CV20: Approachable Petrus](cv20-approachable-petrus/index.md) |
| Execution work beyond the qualified hermetic, single-host routes | [CV10: Composable execution](cv10-composable-execution/index.md) |
| Documentation coherence, terminology, and architecture review | [ES-062](../exploration/es-062-consolidation-and-coherence-baseline/index.md), an exploration rather than a delivery commitment |

CV20's direct-marking timeline foundation is complete. The remaining DS3 work
is application-bound targeted simulation and live correlation, as recorded in
[Live understanding](cv20-approachable-petrus/cv20-ds3-live-understanding.md).

## 1b Delivered work and historical evidence

[CV19](cv19-deterministic-simulation-testing/index.md) records completion of
the deterministic-simulation test kit and its explicit qualification limits.
[CV16](cv16-agenticus-composable-agent-infrastructure/index.md) records
Agenticus infrastructure and the supported scripted local-host route.

Earlier records cover the language-neutral foundations, Python kernel,
History Stores, Activity execution, observation, simulation, and portable Net
definitions. Search item metadata for their disposition. CV5/Fabric remains
unfinished prototype evidence and is subject to rewrite. Application-specific
and site-operation plans are maintained outside this source tree.

## 1c Structure and states

Use the simplest Ariad hierarchy that fits: Value (`CV<N>`), Delivery Story
(`DS<N>`), User Story (`US<N>`), Technical Story (`TS<N>`), Task, or
Maintenance. Item status is one of `Planned`, `Active`, `Blocked`, `Validated`,
`Done`, `Deferred`, or `Dropped` and belongs in the item's own metadata.

Find work by searching item metadata, then read `status_reason` and the
recorded next action. `Blocked` and `Planned` work remains discoverable
alongside `Active` work.

## 1d Item template

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
