# Documentation and Project Memory

Update documentation in the same cycle as the change when project truth changes. Common surfaces include:

- `README.md`
- `docs/project/briefing/`
- `docs/project/decisions/`
- `docs/project/roadmap/`
- `docs/project/debt/`
- `docs/process/worklog/`
- `docs/product/principles/`

## Conflict-Resistant Memory

Use one file per durable artifact when a surface may be edited by multiple people or agents.

- Worklog milestones live in `docs/process/worklog/entries/`.
- Decision records live in `docs/project/decisions/records/` and use `status` for lifecycle state.
- Debt items live in `docs/project/debt/items/`.
- Roadmap items own their current `status` in their own metadata or file, not in a central table.

Index files explain structure, naming, and templates. Do not turn them into complete mutable ledgers unless the project explicitly accepts that coordination cost.

Prefer status metadata over directory moves for lifecycle state. Use directory moves only for deliberate archival or reorganization, and keep state explicit in the artifact.

Keep current truth in the focused current document that owns it. Put rationale for consequential changes in a decision record. Let Git preserve ordinary textual history; do not add append-only policy history or version-suffixed current documents.

Promote durable meaning during normal lifecycle closure. When ending, pausing, compacting, interrupting, or handing off a session, follow the installed skill's canonical `method/memory-closure` protocol. Fold it into an existing closure surface when they coincide; do not emit a second receipt. Promote meaning once into its smallest owner, report dirty state truthfully, and do not preserve transcripts or create generic session-summary files by default. Record a worklog entry only for a meaningful milestone.
