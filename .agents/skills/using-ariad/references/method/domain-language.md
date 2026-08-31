# Domain Language

Domain language gives a project one current meaning for terms whose ambiguity would change how people or agents reason about the product. Ariad's default owner is `docs/project/glossary/`, a directory beside the project briefing that stores one canonical term per Markdown file behind a small `index.md` that explains structure and entry form.

The glossary is not an append-only history file, worklog, specification replacement, or decision ledger. It records accepted language as it applies now. Git preserves ordinary definition history. Use a decision record only when a terminology choice has consequential rationale that future contributors must find without reconstructing it from diffs.

Project contracts, explicit local overrides, and Navigator direction retain their normal [precedence](contracts-and-preferences.md#how-the-driver-should-resolve-conflicts). A local project may name another glossary owner deliberately. The Driver must follow that owner and surface consequential differences from this default rather than creating a second glossary.

## What belongs in the glossary

Include a term only when all of these are true:

- it has project-specific meaning;
- confusing it with a nearby concept would affect reasoning, behavior, boundaries, validation, or product meaning;
- the project has accepted one canonical term and definition.

Do not add ordinary implementation vocabulary merely because it appears in the code. Framework classes, helper names, protocol fields, and common engineering terms stay out unless the project gives them a special meaning that changes work. For example, `RetryPolicy` does not need a glossary entry when it is only the name of a class. `Member` may need one when the product distinguishes a billable Member from an invited but inactive person.

Give each concept one canonical term. State when it applies and when it does not. Add an avoided competing term only when naming it prevents real confusion. Use a concrete example or counterexample when a boundary would otherwise remain abstract.

## Lean entry form

Store one term per file, named after the canonical term in lowercase kebab-case, so definitions can grow and change independently instead of contending for one document. Keep the directory flat and do not maintain a term list in the index; the term files are the inventory.

Use the canonical term as the file's heading, then a direct definition and the two boundaries. Add the remaining lines only when they carry information; do not create empty fields. Link related terms when the relationship helps retrieval.

```markdown
# Member

A person with an active seat in a Workspace.

- Use when: the person can use Workspace capabilities under an active seat.
- Do not use for: someone who has been invited but has not activated a seat.
- Avoid: user, when the distinction between an account and an active seat matters.
- Example: Ana becomes a Member when she accepts the invitation and activates her seat. A pending invite is not a Member.
- Detail: <link to the owning Membership specification>
```

The glossary owns the definition and boundary. A linked specification may own detailed behavior, state transitions, validation rules, or data contracts. Briefing, specifications, decisions, work records, and code documentation should link to that owner instead of copying the definition.

## Operating protocol

### Read and retrieve

Start from the project briefing index. Read the glossary when the task uses unfamiliar project-specific terms or when terminology could affect scope, behavior, validation, or product meaning. Then follow only links relevant to the task. Do not preload unrelated specifications, decisions, worklogs, or glossary history.

When a term is absent, search the relevant code, specifications, project docs, and active work before assuming ordinary usage. Absence from the glossary means the term is not established there; it does not prove that no local contract exists.

### Propose

The Driver may propose a new canonical term or a redefinition. A proposal should show:

- the concept and proposed canonical term;
- the definition, use-when boundary, and do-not-use-for boundary;
- competing terms, examples, and a detailed owner when relevant;
- observed conflicts with existing language or artifacts;
- which glossary entry and linked owners would change if accepted.

Tentative terminology belongs in the owning Exploratory Story while its meaning is still being discovered. It may appear there as a hypothesis, candidate term, tension, or finding, but it must not appear in the current glossary as accepted truth. Promotion from Exploration into the current glossary happens only after Navigator acceptance.

### Accept

Navigator acceptance is required before adding a canonical term or changing an accepted term's name, definition, or boundary. This applies to redefinitions even when code or a specification already uses the proposed meaning. The Driver may prepare a patch for review, but must label it proposed until the Navigator accepts the language.

Acceptance of terminology does not silently accept unrelated behavior, architecture, or delivery scope. If the rationale is consequential and must remain independently discoverable, record a decision and link it from the glossary. Otherwise the glossary update and Git history are enough.

### Update

When the Navigator accepts a domain-language change, update the glossary in the same work cycle as the code, specification, or project documentation that adopts it. Replace current wording rather than appending definition history. Update links and affected owners, but store the definition once.

If all affected artifacts cannot be reconciled in that cycle, keep the work open or record the unresolved conflict in its active-work owner. Do not publish one source as settled while knowingly leaving another source to assert a competing current meaning without an explicit, discoverable conflict.

### Surface conflicts

Compare the glossary with relevant code, specifications, project docs, and current Navigator language. When they disagree, name each source and the conflicting meanings. Do not silently choose the glossary, code, specification, documentation, or latest phrasing as the winner.

Instruction precedence still governs how the Driver conducts the work. It does not erase a domain-language conflict. The Navigator decides the intended canonical language; the Driver then updates the glossary and affected owners together or keeps the conflict visible in active work.

### Close

At work closure and [Memory Closure](memory-closure.md), check accepted terminology changes like any other project-truth change:

- accepted current language is in the configured glossary owner;
- tentative language remains in Exploration;
- definitions are linked rather than copied;
- affected code, specifications, and project docs agree, or their conflict has a durable active owner;
- Navigator acceptance and any consequential decision rationale are discoverable.

Do not close a terminology change as coherent while accepted language exists only in conversation or while a known conflict has no owner.
