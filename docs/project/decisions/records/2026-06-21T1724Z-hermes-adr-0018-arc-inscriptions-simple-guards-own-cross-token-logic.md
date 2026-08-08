---
status: Decided
raised: 2026-06-21
decided: 2026-06-21
deciders:
  - henrique (Navigator, via grill-with-docs in the hermes notebook)
supersedes:
related:
  - hermes ADR 0018
  - docs/project/decisions/records/2026-07-06T1505Z-absorb-hermes-adrs-into-ariad.md
---

> Migrated from the Hermes design notebook.

> Note: the original hermes status is "Partially superseded by ADR 0019" — see docs/project/decisions/records/2026-06-21T1729Z-hermes-adr-0019-arc-inscriptions-do-not-bind-argument-names.md. Kept as Decided here.

# ADR 0018: Arc inscriptions stay simple and cross-token logic lives in transition guards

## Status

Partially superseded by ADR 0019

## Context

Colored Petri nets require arcs to specify which tokens they require or produce. Petrus needs arc inscriptions that are expressive enough for typed tokens and cardinality, while remaining simple enough for users and implementers.

Input arcs may need to select tokens by color/type. Multiple input arcs may then need cross-token conditions such as ensuring a `Worktree` belongs to the same pull request as a `PullRequest` token.

Such correlation logic could live inside arc inscriptions, but that would make arcs more complex and distribute transition-level logic across multiple arcs.

This ADR originally said arc inscriptions also include binding names. ADR 0019 supersedes that part: arcs do not bind handler argument names.

## Decision

Arc inscriptions should stay simple.

Input arc inscriptions should express:

- token color/type required;
- cardinality required.

Cross-token conditions and correlation logic should live in transition guards.

For example, arcs declare candidate token requirements:

```txt
/review/requests -> /review/start
  mode: consume
  color: PullRequest
  count: 1

/review/worktrees -> /review/start
  mode: read
  color: Worktree
  count: 1
```

The transition guard expresses correlation:

```txt
worktree.prId == pr.id
```

However, the names `worktree` and `pr` are not arc-level bind names. They come from the transition/handler contract used to resolve selected tokens for invocation.

Output inscriptions describe produced token color/type and mapping from handler/default behavior results to output tokens. More complex output shaping should be handled by explicit typed handlers rather than hidden inscription inference.

## Consequences

- Arc inscriptions remain understandable.
- Cross-token logic is centralized at the transition.
- Enabled firing candidate computation can first enumerate token selections from arcs, then filter them with guards.
- The model avoids turning arc inscriptions into a complex query language.
- Handler inputs are resolved by the transition/handler contract, not by arc-level argument names.
