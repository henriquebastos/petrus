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

## 1b Decide what needs an entry

Use an entry when a completed milestone has an operational result worth finding
by date: a release, migration, qualification run, or consequential recovery.
Record the result, why it mattered, executed evidence, and remaining limits.
Routine edits and repeated validation belong in the owning story and its
commit. An exploration that already records its conclusion and checks needs
no duplicate worklog summary.

Find entries by filename or search their metadata for a related story. For the
DST delivery outcome, the existing [CV19 closing entry](entries/2026-08-19T0557Z-amp-cv19-production-boundaries-and-close.md)
collects the final evidence; individual entries retain earlier milestones.

Keep historical dates, test counts, failed attempts, and qualifications as
recorded. Correct a factual error with a dated note and a link to its evidence.
Update the current specification or story when behavior changes; a later pass
does not turn an earlier failure into a pass. Before shortening an old entry,
confirm that another linked owner preserves any unique decision or evidence.

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
