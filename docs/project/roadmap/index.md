# Roadmap

Roadmap items carry their own status and preserve durable technical direction.
There is currently no active working session. This is distinct from incomplete
work: CV10 retains blocked or planned boundaries that require a newly bounded
story before work resumes.

## Retained Values

- CV1–CV6: language-neutral foundations, Python kernel, runtime topology,
  Ariad/runtime integration, Fabric, and first-version runtime convergence.
- CV8: production local Activity execution, optional ZeroMQ transport, async
  Activities, and async-native Worker custody.
- CV10: composable execution. Retained blocked and incomplete technical truth
  is not a current authorization or working session.
- CV11–CV15: semantic observation, durable captures, long-History navigation,
  canonical Net inspection, and bounded simulation.
- CV16: Agenticus infrastructure and one supported scripted Pi A2 Local host
  lifecycle. Live-provider profiles remain qualification-only or unsupported.
- CV17–CV18: hosted bounded simulation and portable canonical Net definitions.

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
