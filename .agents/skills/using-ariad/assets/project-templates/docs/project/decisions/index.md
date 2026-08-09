# Decisions

Decision records preserve choices and unresolved questions that should shape future agent sessions.

**Completed Decisions** are decided records. **Open Discussions** are unresolved decision records. This template stores both as one file per record under `records/` and uses `status` to show the lifecycle.

This is a conflict-resistant structure. Do not keep open discussions in a separate directory and do not append every decision to this index.

## Structure

```text
docs/project/decisions/
  index.md
  records/
    YYYY-MM-DDTHHMMZ-short-slug.md
```

A record may start as an open question and later become a decided record. Update that record when the decision is made.

## Status Values

Use these values in frontmatter:

```text
Open        unresolved Open Discussion important enough to preserve
Decided     Completed Decision that future work should respect
Superseded  replaced by a newer decision record
Dropped     no longer relevant or intentionally abandoned
```

State belongs in the record metadata, not in the directory path. Do not move records between status directories to represent lifecycle state.

## How to Use

- Create a record when forgetting the question or decision would cause rework, repeated debate, or product/process drift.
- Use `status: Open` for unresolved decision records.
- Use `status: Decided` once the Navigator or project accepts a decision.
- Do not maintain a complete list of records in this index.
- Find recent records by listing `records/` by filename.
- Find unresolved records by searching for `status: Open`.

## Record Template

Copy this template into a new file in `records/`.

```markdown
---
status: Open
raised: YYYY-MM-DD
decided:
deciders:
  - name-or-role
supersedes:
related:
  - CVX.DSY.USZ
---

# Decision or question title

## Question

For open records, describe the unresolved question and why it matters.

## Decision

For open records, write `Pending`.

For decided records, state the decision directly.

## Rationale

Explain why this decision was made, or what evidence is still needed before deciding.

## Options Considered

List meaningful alternatives when relevant.

## Consequences

Name what future work should respect.

## Review Trigger

For open, superseded, or risky decisions, describe what event should bring this record back into attention.
```
