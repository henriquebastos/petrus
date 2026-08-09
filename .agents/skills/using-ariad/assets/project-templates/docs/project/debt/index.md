# Technical Debt Ledger

The Technical Debt Ledger records structural cost the project is consciously carrying.

Do not record every imperfection. Record debt that may affect future delivery, safety, maintainability, validation, operation, or product coherence.

This is a conflict-resistant ledger structure. Do not maintain a central debt table in this index. Create one debt item file under `items/` for each debt item that should outlive one story's review notes.

The **Technical Debt Ledger** is the project memory surface. A **debt item** is one record inside that ledger.

## Structure

```text
docs/project/debt/
  index.md
  items/
    YYYY-MM-DDTHHMMZ-short-slug.md
```

Use the filename stem as the stable reference when no shorter project-specific debt ID exists. If the project uses short IDs such as `D-001`, store the ID in frontmatter, but avoid central counters unless the team has a coordination rule for assigning them.

## Status Values

Use these values in frontmatter:

```text
Carried   known and accepted for now
Paying    currently being reduced by active work
Paid      resolved or reduced enough to close
Dropped   no longer relevant or replaced by another item
```

State belongs in the item metadata, not in the directory path. Do not move debt items between status directories to represent lifecycle state.

## How to Use

- Create an item when debt should survive beyond the current story's review checkpoint.
- Keep small local imperfections in the story review or follow-up list instead of creating debt noise.
- Record the source story, carrying reason, revisit trigger, and closure condition.
- Do not maintain a complete list of debt items in this ledger index.
- Find current debt by searching for `status: Carried` or `status: Paying`.

## Item Template

Copy this template into a new file in `items/`.

```markdown
---
id:
status: Carried
kind: design | test | docs | architecture | operations | process
severity: low | medium | high
source: CVX.DSY.USZ
revisit_trigger:
closure_condition:
---

# Debt item title

## Description

Describe the structural cost being carried.

## Carrying Reason

Explain why the project is accepting this debt for now.

## Impact

Describe the delivery, safety, maintainability, validation, operation, or product coherence risk.

## Revisit Trigger

Name the event that should bring this debt back into active work.

## Closure Condition

Describe what would make this debt paid or safe to drop.

## Notes

Add supporting evidence, links, or related follow-up work.
```
