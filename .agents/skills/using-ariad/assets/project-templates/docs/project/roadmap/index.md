# Roadmap

The roadmap describes meaningful progress, not every task.

This index explains roadmap structure and conventions. Do not use it as the mutable source of truth for every roadmap item. Roadmap items should live in their own files or folders, and each item should carry its own `status` metadata.

## Canonical Meaning

Taxonomy, states, lifecycle meaning, and defaults come from the installed skill's packaged `delivery/roadmap-taxonomy` and related Delivery references. Load them through `using-ariad/SKILL.md`, or open the installed `SKILL.md` manually. This index defines local storage, metadata, and naming only. Record any deliberate methodological adaptation in the local development guide.

## Codes and Folders

Local codes:

```text
CV<N>  Value / Capability Value
DS<N>  Delivery Story
US<N>  User Story
TS<N>  Technical Story
```

Recommended folder pattern:

```text
docs/project/roadmap/
  index.md
  cv<N>-<value-slug>/
    index.md
    cv<N>-ds<M>-<delivery-story-slug>/
      index.md
      exploration-summary.md
      cv<N>-ds<M>-us<K>-<user-story-slug>/
        index.md
        plan.md
        test-guide.md
      cv<N>-ds<M>-ts<K>-<technical-story-slug>/
        index.md
        plan.md
        test-guide.md
```

## State Representation

Put the canonical or explicitly locally adapted lifecycle state in each roadmap item's frontmatter or status section.

```yaml
---
status: Active
status_reason: pulled for current Delivery Work
updated: YYYY-MM-DD
---
```

Keep state in metadata rather than encoding routine transitions as directory moves, so paths and links remain stable.

## How to Find Work

- Find active work by searching for `status: Active`.
- Find blocked work by searching for `status: Blocked`.
- Find completed work by searching for `status: Done`.
- Find recent roadmap changes by listing files by modification time or reading linked worklog entries.
- Do not maintain a complete active/planned/done table in this index unless the project deliberately accepts that coordination cost.

## Item Template

Use this shape for a Value, Delivery Story, User Story, Technical Story, or Maintenance record. Adjust fields to the level of work.

```markdown
---
code: CVX.DSY.USZ
level: Value | Delivery Story | User Story | Technical Story | Maintenance
status: Planned
status_reason:
updated: YYYY-MM-DD
related:
  - decision-or-worklog-link
---

# Item title

## Intent

Describe the outcome this item exists to create.

## Scope

Name what belongs inside this item.

## Acceptance / Done Condition

For User Stories, prefer lightweight BDD form:

Given <relevant starting state>
When <the user, operator, command, or runtime action happens>
Then <observable behavior or capability is visible>
And <important constraint or protection still holds>

For Delivery Stories or Values, name the emergent capability or boundary that closes the parent.

## Validation Route

Describe how the Driver and Navigator can verify this item.

## Out of Scope

Name related work that should not be silently absorbed.

## Notes

Add links to Exploration summaries, decisions, debt items, worklog entries, or follow-up work.
```
