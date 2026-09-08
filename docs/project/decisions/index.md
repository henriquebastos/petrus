# 1 Decisions

Decision records explain accepted choices and the alternatives considered.
Read a record's date, status, and review notes before applying it to current
work. Follow supersession links when a later decision replaces an earlier one.
The [specification](../../../spec/README.md) and [glossary](../glossary/index.md)
provide the current behavior and terminology.

Store one record per question or decision under `records/`. Keep this index
as a reading and authoring guide; status belongs in each record's metadata.

## 1a Structure

```text
docs/project/decisions/
  index.md
  records/
    YYYY-MM-DDTHHMMZ-short-slug.md
```

A record may start as an open question and later become a decided record. Update that record when the decision is made.

## 1b Status values

Use these values in frontmatter:

```text
Open        unresolved Open Discussion important enough to preserve
Decided     Completed Decision that future work should respect
Superseded  replaced by a newer decision record
Dropped     no longer relevant or intentionally abandoned
```

State belongs in the record metadata, not in the directory path. Do not move records between status directories to represent lifecycle state.

## 1c How to use

- Create a record when forgetting the question or decision would cause rework, repeated debate, or product/process drift.
- Use `status: Open` for unresolved decision records.
- Use `status: Decided` once the Navigator or project accepts a decision.
- Do not maintain a complete list of records in this index.
- Find recent records by listing `records/` by filename.
- Find unresolved records by searching for `status: Open`.

## 1d Record template

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
