---
status: Decided
raised: 2026-07-06
decided: 2026-07-06
deciders:
  - henrique (Navigator)
supersedes:
related:
---

# "Event history" is the working term (not "firing journal")

## Question

Velocitron's glossary calls the replay record a "firing journal" and explicitly avoids "event log/history"; hermes ADRs 0030–0035 make the "unified event history" canonical. Which term — and which scope — does Impetus use?

## Decision

**Event history.** Names can still evolve, but this is the working term.

## Rationale

The disagreement is scope, not taste: a *firing journal* records firings; the Navigator's Temporal experience (which Matt doesn't share) is of an event history that records *everything* — external events, timers, scheduler decisions, activity attempts, inputs and outputs. "It feels like a call stack, a log, a trace… very good for debugging, very good for replaying." Hermes ADR 0031's record categories already encode that broader scope; "journal" would undersell it.

## Consequences

- Glossary entry with avoid-list: event history — *avoid: firing journal, audit trail, event log (as the canonical name)*.
- Bring the scope argument (not just the name) to the spec alignment with Matt.
- Per the net-instance-is-a-process decision, the history is per net instance.

## Review Trigger

The naming conversation with Matt; revisit if a better name captures the full scope.

## Review outcome (2026-08-31)

The anticipated evolution happened: practice converged on capitalized
**History** as the canonical short name (code `HistoryStore`/`HistoryRecord`,
glossary `docs/project/glossary/history.md`), and the Navigator ratified it
during ES-062 consolidation. "Event history" remains an acceptable
descriptive long form — the scope argument of this record stands unchanged;
only the short name evolved. `spec/event-history.md` keeps its filename.
