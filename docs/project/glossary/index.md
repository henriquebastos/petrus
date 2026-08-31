# Glossary

This directory is the current owner for accepted project-specific domain language whose ambiguity affects reasoning, behavior, boundaries, validation, or product meaning. It is not a history file, worklog, specification replacement, or decision ledger.

Store one term per Markdown file named after the canonical term in lowercase kebab-case, so definitions can grow and change independently instead of contending for one document. Keep the directory flat until real scale proves another level helps. The term files are the inventory; do not maintain a term list in this index.

Keep tentative terminology in `docs/project/exploration/`. Add or redefine canonical terminology here only after Navigator acceptance, and update the affected term files in the same work cycle as accepted changes in code, specifications, or project documentation. Surface conflicts among those sources instead of silently choosing one.

Store each definition once. Link here from briefing, specifications, decisions, and work records; link from an entry to a detailed owning specification when one exists. Let Git preserve ordinary definition history. Use a decision record only when consequential terminology rationale must remain independently discoverable.

## Entry form

Use the canonical term as the file's heading. Include the definition and both boundaries. Add the other lines only when relevant; remove unused lines rather than leaving empty fields.

```markdown
# Canonical term

Direct definition.

- Use when: boundary where this term applies.
- Do not use for: nearby concept this term excludes.
- Avoid: competing term, when naming it prevents ambiguity.
- Example: concrete example or counterexample that clarifies the boundary.
- Related: [Nearby term](nearby-term.md)
- Detail: [Owning specification](../../specifications/example.md)
```
