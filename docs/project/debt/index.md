# 1 Technical debt

Debt items describe costs or limitations the project is carrying, why they
remain, and what should trigger another look. Search for `status: Carried` or
`status: Paying` to find unresolved items. A `Paid` item records how a cost
was resolved; its earlier description is historical evidence.

Store one item under `items/` for a limitation that should outlive the current
work. Keep smaller findings in the owning story or review. Each item needs a
carrying reason, revisit trigger, and closure condition. The filename stem is
its stable identifier unless the project has assigned another explicit ID.

## 1a Structure

```text
docs/project/debt/
  index.md
  items/
    YYYY-MM-DDTHHMMZ-short-slug.md
```

Use the filename stem as the stable reference when no shorter project-specific debt ID exists. If the project uses short IDs such as `D-001`, store the ID in frontmatter, but avoid central counters unless the team has a coordination rule for assigning them.

## 1b Status values

Use these values in frontmatter:

```text
Carried   known and accepted for now
Paying    currently being reduced by active work
Paid      resolved or reduced enough to close
Dropped   no longer relevant or replaced by another item
```

State belongs in the item metadata, not in the directory path. Do not move debt items between status directories to represent lifecycle state.

## 1c How to use

- Create an item when debt should survive beyond the current story's review checkpoint.
- Keep small local imperfections in the story review or follow-up list instead of creating debt noise.
- Record the source story, carrying reason, revisit trigger, and closure condition.
- Do not maintain a complete list of debt items in this ledger index.
- Find current debt by searching for `status: Carried` or `status: Paying`.

## 1d Item template

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
