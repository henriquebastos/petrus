---
date: 2026-09-08T15:08:00Z
author: codex
kind: milestone
related:
  - ES-062
verification:
  - scripts/check quick
  - Focused project, DSL, and portable-document suite
  - Executed README and runtime-guide examples
  - Local Markdown target and fragment checks
  - Ariad manifest and historical-text preservation checks
---

# 1 Make current guidance readable without session history

The Navigator requested a coherence pass for readers unfamiliar with Petrus,
using Ariad's memory process and plain prose.
This is the reader-facing portion of ES-062 WS3. It changes documentation
through ordinary commits and does not qualify a runtime release.

# 2 Findings and changes

| Finding | Current owner or correction |
| --- | --- |
| The README led with internal terminology and an incomplete typed example | A runnable token-flow example in the README; detailed APIs and support limits in the runtime guide |
| The briefing and roadmap described completed lineage work as pending | Overviews now follow the owning CV20.DS3 story |
| AGENTS.md denied the installed method and retained experiments | Corrected local-package and historical-gap guidance |
| Engineering practice required reading a long review chronology | A short engineering guide links to all 89 preserved review cases |
| Historical counts, code names, and test results could read as current truth | Reading guidance in the documentation and record indexes; dated dispositions in ES-062 |
| Source labels implied stronger conformance evidence than they provided | Specification index distinguishes design provenance from executable validation |
| Current product guidance used personal anecdotes and rhetorical claims | Principles now state the same constraints in contributor-facing prose |

Ariad Memory Closure was applied to existing owners. Current usage, process,
status, and historical evidence each have a reading path. The installed skill
was not edited or replaced, and no personal-memory database was used as an
alternative project authority.

# 3 Verification

1. `scripts/check quick` passed Ruff, formatting for 320 Python files, type
   checks, and structural checks.
2. `uv run --frozen pytest -q tests/project tests/petrus/impetus/dsl/test_petrinet_dsl.py tests/petrus/impetus/test_net_document.py tests/petrus/impetus/test_net_document_lineage.py --forbid-skips`
   passed 125 tests with no skips.
3. The README example printed `['Hello, Petrus!']`. The typed authoring example
   built two places and one transition. The Graphviz example produced an SVG.
   The Worker fragment ran with a Local Worker provider, and the lifecycle
   fragment reset its exact generation. The latter fragments used explicit
   host setup, as their documentation states.
4. A repository-wide scan of maintained Markdown found no missing local link
   targets or unresolved local heading fragments outside fenced examples.
   Frontmatter was parsed across decision, roadmap, exploration, and debt
   records. External URLs and historical bare path/commit mentions were not
   treated as live local links.
5. All 54 installed Ariad manifest entries matched their hashes. The 89
   numbered engineering review cases are preserved verbatim. Decision records,
   experiment artifacts, source code, tests, fixtures, and package configuration
   are unchanged.

The previous hosted full-suite result remains 2,594 passed and one async-worker
failure, with the serial release phase unexecuted. That failure is recorded in
[the existing debt item](../../../project/debt/items/2026-09-08T0300Z-process-tests-assume-short-wall-clock-budgets.md).
This prose-only pass did not repeat the full runtime suite or turn its failed
release result into a passing claim. Live providers, Arx, and external websites
were not requalified.

# 4 Review and remaining work

The Driver recommends accepting the documentation changes with the existing
runtime-validation reservation. No runtime refactoring or compatibility change
was needed. The source and package version remain unchanged.

[ES-062](../../../project/exploration/es-062-consolidation-and-coherence-baseline/index.md)
retains the uncompleted terminology, architecture, and DST workstreams.
Retiring older replay formats or deleting experiment evidence needs a separate
compatibility and retention decision. Historical records retain their dated
claims; this pass reviewed their navigation, metadata, and relationship to
current owners rather than re-performing every historical experiment.

