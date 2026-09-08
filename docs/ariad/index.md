# 1 Ariad in Petrus

Ariad is the method Petrus uses to keep direction, decisions, validation, and
unfinished work recoverable across contributors and coding-agent sessions.
The human is the Navigator and owns direction, trade-offs, and acceptance.
The agent is the Driver and reads, implements, tests, and records the work.

The [development guide](../process/development-guide.md) is the local operating
contract. Explicit Navigator direction and project-local rules take precedence
over the installed method. Surface consequential differences during review.

## 1a Read the relevant owners

For a first visit, start with the [documentation guide](../README.md). For
agent work, follow [AGENTS.md](../../AGENTS.md) and load the installed
[using-ariad skill](../../.agents/skills/using-ariad/SKILL.md). Follow its
reference links for the work at hand; the method is available locally.

| Needed context | Owner |
| --- | --- |
| Project identity and current direction | [README](../../README.md), [briefing](../project/briefing.md) |
| Accepted domain language | [Glossary](../project/glossary/index.md) |
| Process and implementation practice | [Development guide](../process/development-guide.md), [engineering guide](../process/engineering-conventions.md) |
| Product trade-offs | [Principles](../product/principles.md) |
| Runtime behavior and interoperability | [Specification](../../spec/README.md) |
| Current work or rationale | [Roadmap](../project/roadmap/index.md), [exploration](../project/exploration/index.md), [decisions](../project/decisions/index.md) |
| Known costs and dated evidence | [Debt](../project/debt/index.md), [worklog](../process/worklog/index.md) |

Read indexes before focused records. The exploration index explains identifier
continuity. Use current specifications and executable evidence to establish
behavior; historical reviews record what was known at their date.

## 1b Keep memory small and recoverable

Use the installed [Memory Closure protocol](../../.agents/skills/using-ariad/references/method/memory-closure.md)
when work or context reaches a closure, pause, or handoff. Fold it into the
existing work record and checkpoint:

1. Inspect the branch, working tree, active work, and actual validation results.
2. Put changed behavior, accepted decisions, and unresolved work in their
   existing owners. Link to evidence already recorded elsewhere.
3. Replace stale current guidance and repeated narration. Preserve dated
   outcomes and supersession so readers can distinguish history from policy.
4. Check links, status, terminology, and agreement between process, project,
   and product. Record an ordinary commit under the local policy when ready.
5. State what is verified, what remains unresolved, and where the next
   contributor should resume.

Personal AI memory is optional advisory context. It does not replace repository
records, and its absence cannot block contribution. Memory Closure needs no
separate service, transcript export, or generic session-summary file.

Keep the installed Ariad package intact. Update its version and manifest as a
whole when adopting a new release; edit Petrus-owned guidance for local needs.
If the skill is unavailable, continue with the local contract: read before
editing, bound scope, verify the concrete behavior, preserve decisions and
unfinished work, and follow commit and push policy.
