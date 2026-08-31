# Documentation and Project Memory

Update documentation in the same cycle as the change when project truth changes. Common surfaces include:

- `README.md`
- `docs/project/briefing/`
- `docs/project/glossary/`
- `docs/project/decisions/`
- `docs/project/roadmap/`
- `docs/project/debt/`
- `docs/process/worklog/`
- `docs/product/principles/`

## Optional Personal Memory

A separately configured personal, cross-repository memory companion is optional and advisory. The repository and its project-owned work surfaces remain authoritative. Continue normally when the companion is absent or unavailable, and verify recalled claims against the current repository before acting.

Do not mirror this project's vision, explorations, decisions, principles, tasks, or delivery history into a personal store. A horizontal lesson may point back to project meaning with repository identity, the Ariad artifact path or stable ID, and the source revision; follow the pointer to the current artifact rather than trusting or copying a stale snapshot. Personal capture or recall does not satisfy Memory Closure, validation, or a history checkpoint.

Document any repository-visible personal-memory configuration, privacy constraints, or capture exceptions under project constraints and environment. Ariad adoption itself requires no personal-memory command, service, database, or marker file.

## Conflict-Resistant Memory

Use one file per durable artifact when a surface may be edited by multiple people or agents.

- Worklog milestones live in `docs/process/worklog/entries/`.
- Decision records live in `docs/project/decisions/records/` and use `status` for lifecycle state.
- Debt items live in `docs/project/debt/items/`.
- Roadmap items own their current `status` in their own metadata or file, not in a central table.

Index files explain structure, naming, and templates. Do not turn them into complete mutable ledgers unless the project explicitly accepts that coordination cost.

Prefer status metadata over directory moves for lifecycle state. Use directory moves only for deliberate archival or reorganization, and keep state explicit in the artifact.

Keep current truth in the focused current document that owns it. Put rationale for consequential changes in a decision record. Let Git preserve ordinary textual history; do not add append-only policy history or version-suffixed current documents.

The configured glossary owner, by default `docs/project/glossary/`, owns accepted project-specific domain definitions. Keep tentative terminology in Exploration. Require Navigator acceptance before adding or redefining a canonical term, update accepted language in the same work cycle, and link to the definition from specifications, decisions, briefing, and work records instead of copying it. Surface conflicts with code, specifications, project docs, or Navigator language rather than silently choosing a winner.

Promote durable meaning during normal lifecycle closure. When ending, pausing, compacting, interrupting, or handing off a session, follow the installed skill's canonical `method/memory-closure` protocol. Fold it into an existing closure surface when they coincide; do not emit a second receipt. Promote meaning once into its smallest owner, report dirty state truthfully, and do not preserve transcripts or create generic session-summary files by default. Record a worklog entry only for a meaningful milestone.
