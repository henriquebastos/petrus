---
status: Decided
raised: 2026-06-21
decided: 2026-06-21
deciders:
  - henrique (Navigator, via grill-with-docs in the hermes notebook)
supersedes:
related:
  - hermes ADR 0002
  - docs/project/decisions/records/2026-07-06T1505Z-absorb-hermes-adrs-into-ariad.md
---

> Migrated from the Hermes design notebook.

# ADR 0002: Reusable components separate net, bindings, and process convenience

## Status

Accepted

## Context

Petrus should support reusable components such as GitHub PR review, Slack monitoring, human approval, sandbox provisioning, and code review flows.

A reusable component may need to expose:

- the pure process structure;
- default handlers for common implementations;
- an ergonomic high-level entry point.

If these are collapsed together, the component becomes framework-like and makes it hard to replace implementation details without changing process topology.

## Decision

Reusable Petrus components should expose three layers separately:

```ts
githubPrReviewNet()
githubPrReviewBindings(...)
githubPrReviewProcess(...)
```

Where:

- `*Net()` returns only the declarative net or subnet definition.
- `*Bindings(...)` returns default transition handlers for that net.
- `*Process(...)` is a convenience composition of net + default bindings + optional runtime/configuration.

## Consequences

- A user can reuse a net with custom handlers.
- A user can reuse handlers with a modified net when contracts still match.
- A user can swap local execution for remote execution.
- A user can replace a Slack, GitHub, browser, sandbox, or agent library without changing the process topology.
- Nets can be tested independently from external side effects.
- Process helpers can remain ergonomic without hiding the separation between process meaning and implementation choice.

## Rejected alternatives

### Publish only raw nets

This keeps purity but provides too little practical value for users who want useful defaults.

### Publish only high-level processes

This is too framework-like and hides the important separations.

### Encode handler kinds into transition types

Rejected because a transition is just a transition. Behavior belongs to bindings and handlers, not transition kinds in the net definition.
