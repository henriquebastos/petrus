# Local Development Guide

This directory is the project-specific operating contract for agentic development.

Ariad is the canonical method. Silence here inherits the installed skill's current method and defaults; only explicit local rules override it. Load `using-ariad/SKILL.md` and its packaged method, work-area, Delivery, Exploration, and Refinement references (or open that `SKILL.md` manually when discovery is unavailable). Surface consequential local differences during coherence review.

## How to Read This Guide

Read this index first, then only the documents relevant to the current work:

- [Commands and verification](commands-and-verification.md) — setup, execution, automated checks, and acceptance evidence.
- [Documentation and project memory](documentation-and-memory.md) — documentation responsibilities and conflict-resistant records.
- [Workflow and checkpoints](workflow-and-checkpoints.md) — explicit local workflow adaptations and confirmation boundaries.
- [Navigator preferences](navigator-preferences.md) — explicit local choices about how work is conducted.
- [Release and history](release-and-history.md) — branches, commits, pushes, pull requests, versions, and releases.
- [Local exceptions](local-exceptions.md) — deliberate deviations from Ariad or normal engineering practice.

Keep current truth in the focused document that owns it. Record rationale for consequential changes in `docs/project/decisions/records/`; rely on Git for ordinary textual history. Do not append policy history here or create version-suffixed policy files.
