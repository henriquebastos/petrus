# Exploration

Canonical Exploration meaning, lifecycle, states, and defaults come from the installed skill's packaged Exploration references. Load them through `using-ariad/SKILL.md`, or open the installed `SKILL.md` manually. This index defines the project's local artifact and metadata schema; record deliberate method adaptations in the local development guide.

This index explains the structure and template. Do not use it as the mutable state surface for active Exploratory Stories. Each Exploratory Story owns its state in its own directory.

## Structure

```text
docs/project/exploration/
  index.md
  es<N>-<story-slug>/
    index.md
    experiments/
      YYYY-MM-DDTHHMMZ-<experiment-slug>.md
    artifacts/
      <supporting-artifact>.md
```

Create the `experiments/` and `artifacts/` directories only when the Exploratory Story needs them. Small stories can live entirely in their own `index.md`.

## Status Values

Use a canonical or explicitly locally adapted value in the Exploratory Story `status` frontmatter. State belongs in story metadata, not in this top-level index or primarily in the directory path.

## How to Use

- Create one directory per Exploratory Story under `docs/project/exploration/`.
- Use the story directory's `index.md` as the durable story anchor.
- Keep the top-level `docs/project/exploration/index.md` as this guide and template.
- Find active Exploration by searching story indexes for `status: Thickening`, `status: Paused`, or `status: Candidate`.
- Link promoted stories to the Delivery Story, child story, Change Request, or Refinement Story that received the handoff.
- Put the concise Delivery or Refinement summary beside the receiving work item; keep the full Exploration Documentation in the story directory.

## Exploratory Story Template

Create a new directory such as `es-001-short-slug/`, then copy this template into that directory's `index.md`.

```markdown
---
id: ES-001
status: Thickening
opened: YYYY-MM-DD
updated: YYYY-MM-DD
source:
  - signal-or-context
attractor:
promoted_to:
refinement_request:
related:
  - decision-or-roadmap-link
---

# Exploratory Story title

## Current Story

Describe the current thickened story. This should read as the accumulated narrative, not only the latest note.

## Initial Signal

Describe the signal or signals that opened the Exploratory Story.

## Thickening Timeline

Add meaningful changes to the story as dated notes. Do not record every turn; record material that changes meaning, weight, or direction.

### YYYY-MM-DD — Short note title

What changed in the story?

Why does it matter?

## Attractors and Tensions

Name confirmed attractors, rejected attractors, contradictions, or tensions that shape the story.

## Experiments

Link experiments when they exist. If an experiment is small, summarize it here. If it needs detail, create a file under `experiments/` and link it.

## Carry Forward Notes

Preserve implementation-relevant findings only when the Navigator accepts carrying them forward.

## Candidate / Promotion

Describe candidate readiness, Navigator decision, Delivery or Refinement handoff, roadmap or Workbench placement, validation seeds, and links to Delivery or Refinement summaries when relevant.

## Kept-for-Later Signals

Link nearby signals that remain outside this story's scope.

## Archive Notes

If archived, explain why the story is preserved but inactive.
```
