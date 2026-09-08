# 1 Worklog

Worklog entries preserve dated milestones and the checks performed at the
time. For current direction, read the [briefing](../../project/briefing.md).
For current behavior, follow the relevant specification or usage guide.
A historical passing run does not establish the status of today's checkout.

Use one file per meaningful milestone under `entries/`, with a UTC timestamp
and author in its name. Keep this index as a guide; discover entries by their
filenames or by searching their metadata. Routine session narration belongs
in neither the worklog nor a duplicate summary file.

## 1a Structure

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

## 1b How to use

- Create a new entry file for each meaningful completed milestone.
- Do not maintain a complete list of entries in this index.
- Find recent work by listing `entries/` by filename.
- Search entry frontmatter or body text for related stories, decisions, or verification evidence.
- Record meaningful milestones, not every edit.

## 1c Entry template

Copy this template into a new file in `entries/`.

```markdown
---
date: YYYY-MM-DDTHH:MM:SSZ
author: name-or-agent
kind: milestone
related:
  - CVX.DSY.USZ
verification:
  - command, executed behavior route, or evidence artifact
---

# Milestone title

## What changed

Describe what changed.

## Why it matters

Describe why this matters to the project, product, or process.

## Verification

Describe what the Driver executed and observed. Include commands, expected and
observed results, screenshots, video, operation evidence, confidence limits, or
review notes when relevant. Record Navigator judgment separately from Driver QA;
do not assign routine verification back to the Navigator.

## Follow-up

Mention important follow-up work or conscious exclusions when relevant.
```
