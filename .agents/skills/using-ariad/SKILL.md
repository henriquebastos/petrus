---
name: using-ariad
description: Use Ariad's runtime-independent human-agent development method when orienting, exploring, delivering, refining, or adopting its project memory templates in a software repository.
license: MIT
metadata:
  version: "0.3.0"
  source-path: "skills/using-ariad"
  method-digest: "sha256:c118e38da423a3b07de392e3000b864613e384540b6d5180cfac180426a5b323"
---

# Using Ariad

Activate this skill when a project uses Ariad or asks to adopt it. Project-local instructions and explicit Navigator direction take precedence over this package; surface consequential differences rather than silently replacing local practice.

Read [`references/method/overview.md`](references/method/overview.md) first. Route work through [`references/method/work-areas.md`](references/method/work-areas.md), then read only the relevant Exploration, Delivery, or Refinement references and local project indexes.

When project-specific terms affect reasoning, behavior, boundaries, validation, or product meaning, read the local project glossary and [`references/method/domain-language.md`](references/method/domain-language.md). Propose one canonical meaning, keep tentative terminology in Exploration, require Navigator acceptance for additions or redefinitions, and surface conflicts instead of choosing a source silently. This is base Ariad behavior; it does not depend on another skill.

Before ending, pausing, compacting, or handing off a session—and whenever context pressure threatens continuity—follow [`references/method/memory-closure.md`](references/method/memory-closure.md). Promote durable meaning into existing project owners and, when authorized, committed Git history; do not preserve the transcript or create a generic session-summary file by default.

Treat any personal, cross-repository memory as optional advisory context under that same reference. It may suggest pointers, but repository state remains authoritative; continue normally when it is absent or unavailable and verify recalled claims before acting.

For adoption, start with `scripts/adopt.py`. It previews a no-overwrite installation of the templates in `assets/project-templates/`; inspect its plan before applying.

If automatic skill discovery is unavailable, open this `SKILL.md` manually and follow the same reference routing. Templates may also be copied manually from `assets/project-templates/` without overwriting existing project files.
