---
status: Decided
raised: 2026-07-02
decided: 2026-07-02
deciders:
  - henrique (Navigator, via grill-with-docs in the hermes notebook)
supersedes:
related:
  - hermes ADR 0028
  - docs/project/decisions/records/2026-07-06T1505Z-absorb-hermes-adrs-into-ariad.md
---

> Migrated from the Hermes design notebook.

# ADR 0028: Runtime history addresses are for tooling, not execution semantics

## Status

Accepted

## Context

The Matt end-design insight emphasized that each event should be available in history and that important parts of a Petrus process should be addressable.

Petrus has already accepted typed schema/design URIs for graph citizens:

```txt
place:/review/pending
transition:/review/start
arc:/review/pending->/review/start
```

And anchored declaration URIs:

```txt
transition:/review/start#handler
place:/review/pending#initial
```

The next question is whether runtime/history records such as events, firing attempts, tokens, markings, and handler results should also be addressable by URI.

These addresses may be useful for inspection, debugging, audit, replay visualization, traces, editor links, UI timelines, and logs. However, the core net execution algorithm should not depend on URI-shaped history references to compute enabledness or firing.

## Decision

Runtime/history addresses may exist, but they are for tooling, diagnostics, audit, replay visualization, and external references — not for core execution semantics.

Core execution should operate on explicit runtime records and indexes, such as:

- current marking;
- token records;
- event log entries;
- firing attempts;
- handler results;
- timer records;
- scheduler decisions.

A runtime/history URI can point to one of these records, but the URI itself is not the mechanism that makes the net execute.

## Consequences

- Schema URI design remains focused on places, transitions, arcs, and declarations.
- Runtime/history URI design can be postponed until tooling, traces, or audit views need it.
- Execution remains data-structure driven and deterministic rather than string-address driven.
- Tooling can still expose stable references for timeline entries, traces, logs, source maps, and debugging.
- Runtime records should still be uniquely identifiable, but their public URI form is a presentation/reference layer.

## Possible future examples

```txt
event:/review/history/000123
firing:/review/run-review/attempt/42
token:/review/pr-loaded/token/abc123
marking:/review/snapshot/17
```

These examples are illustrative, not accepted syntax.
