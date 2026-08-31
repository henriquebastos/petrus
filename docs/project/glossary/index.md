# Project Glossary

This directory owns the project's canonical domain language. Store one term per Markdown file so definitions can grow, move, and change independently without turning one glossary document into a shared editing bottleneck.

## Structure

```text
docs/project/glossary/
  index.md
  customer.md
  invoice.md
  order.md
```

Use a lowercase kebab-case filename based on the canonical term. Keep the directory flat until real scale proves that another level helps. A term collision usually means the language needs sharper names, not separate context directories.

## Term Format

```markdown
# Order

A customer's accepted request for goods or services.

Avoid: purchase, transaction

Related: [Customer](customer.md), [Invoice](invoice.md)
```

The definition is required. Keep it to one or two sentences and state what the term is. `Avoid` and `Related` are optional.

## Rules

- Add only project-specific domain language that the Navigator understands and accepts.
- Update a term when project language changes; let Git preserve the old definition.
- Use `Avoid` for rejected synonyms and overloaded words.
- Link related terms when the relationship helps retrieval, but do not turn a definition into a specification.
- Put domain invariants, behavior, implementation details, decisions, and session notes in their focused owners rather than glossary files.
- Check current code and documentation before accepting a definition. Surface conflicts instead of silently choosing one meaning.
- Do not maintain an exhaustive term list in this index. The files in this directory are the inventory.
