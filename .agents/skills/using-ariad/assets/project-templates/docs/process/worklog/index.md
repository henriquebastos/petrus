# Worklog

Operational progress for the project.

The Worklog uses a conflict-resistant file layout. Do not append milestones to this index. Create one file per meaningful milestone under `entries/`.

## Structure

```text
docs/process/worklog/
  index.md
  entries/
    YYYY-MM-DDTHHMMZ-author-slug.md
```

Use UTC timestamps so filenames sort chronologically. Include the author, agent, or runtime name when it helps distinguish concurrent work. Keep the slug short and descriptive.

Examples:

```text
entries/2026-06-17T1545Z-henrique-read-project.md
entries/2026-06-17T1612Z-agent-validation-guide.md
```

## How to Use

- Create a new entry file for each meaningful completed milestone.
- Do not maintain a complete list of entries in this index.
- Find recent work by listing `entries/` by filename.
- Search entry frontmatter or body text for related stories, decisions, or verification evidence.
- Record meaningful milestones, not every edit.

## Entry Template

Copy this template into a new file in `entries/`.

```markdown
---
date: YYYY-MM-DDTHH:MM:SSZ
author: name-or-agent
kind: milestone
related:
  - CVX.DSY.USZ
verification:
  - command or manual validation route
---

# Milestone title

## What changed

Describe what changed.

## Why it matters

Describe why this matters to the project, product, or process.

## Verification

Describe how it was verified. Include commands, manual validation, screenshots, operation evidence, or review notes when relevant.

## Follow-up

Mention important follow-up work or conscious exclusions when relevant.
```
