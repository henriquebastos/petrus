---
status: Decided
raised: 2026-07-16
decided: 2026-07-23
deciders:
  - henrique (Navigator)
supersedes:
  - DEC-018's unresolved Dex and 12-factor-agents routing questions
  - the hypothesis that agent context projection needs a separate generic exploration now
  - the claim that all evergreen documentation is mechanically verified against the kernel
  - the proposal to ratify a generic back-pressure or verify-transition chip before a concrete consumer earns it
  - the proposal to maintain HumanLayer as an active standing watch item
related:
  - docs/process/development-guide.md
  - docs/process/engineering-conventions.md
  - spec/README.md
  - CONTEXT.md
---

# Agent context and verification stay concrete

## Question

How should Impetus route the five open questions raised by the Dex Horthy /
12-factor-agents analysis: generic agent-context projection, delayed
maintainability failure, evergreen-document parity, back-pressure as a reusable
convention, and HumanLayer as a watch item?

## Decision

Close all five questions while preserving concrete-first ownership.

### Context projection stays with concrete consumers

Do not open a generic context-projection exploration now. DEC-027 already
settles session placement and requires History-derived context to be
materialized through ordinary Net/Activity composition before it reaches a
history-blind `ActivityHandler.prepare(binding)` boundary.

ES-022, ES-023, and ES-025 provide working consumer-specific projections.
When ES-011 is explicitly reactivated, it owns the context selection, ordering,
budgeting, and provider-shaping behavior required by its heart-transplant
experiment. Provider-specific representation may remain adapter policy. Extract
a shared stdlib chip only after concrete reuse demonstrates a stable common
contract; do not predesign a recursive context-policy language.

This ruling does not reactivate ES-011.

### Long-horizon failure limits gate shrinking

Add an explicit slow-failure limitation to the future attention-gate doctrine
for code-producing nets. Immediate success, test results, and approval rates
cannot by themselves justify eliminating human review when important
maintainability or architectural failures emerge only over months.

Gate reduction remains possible, but code-producing nets must retain periodic
human review or an explicit long-horizon maintainability probe appropriate to
the claimed risk. No scheduler, metric, or maintainability subsystem is
commissioned by this ruling; §4.3 remains future direction.

### Documentation parity is layered and honestly bounded

Define the standing parity claim precisely:

- normative runtime behavior belongs in executable tests and conformance
  fixtures;
- `spec/` is supported by golden replay plus Impetus-native behavior tests,
  with unsupported and deferred coverage stated explicitly;
- `CONTEXT.md` is an orientation and ubiquitous-language surface maintained by
  review and the project coherence check, not mechanically proven line by
  line; and
- a normative spec statement without executable evidence is a visible coverage
  gap, not verified behavior.

Keep the existing full tests, Ruff, format, and ast-grep commands as standing
gates. Do not build a generic prose-to-code checker merely to claim total
parity.

### Back-pressure waits for implementation evidence

Do not ratify a generic back-pressure or verify-transition chip convention now.
`nets-as-evals` remains a captured design signal. A concrete consumer such as
ES-011 or another code-producing application net may implement ordinary verify
transitions, guards, and completion predicates. Extract and ratify a reusable
convention only after implementation and review demonstrate recurrence, as the
engineering-conventions book already requires.

### HumanLayer remains a static reference

Keep the HumanLayer material as external evidence, not an active watch item,
dependency, rubric, or scheduled monitoring obligation. Revisit it only when a
current Impetus story needs a refreshed comparison or a deliberately reviewed
new artifact supplies material evidence.

## Rationale

Later Impetus experiments answer much of the original context-placement gap
without requiring a generic layer. The remaining behavior is consumer policy,
so ES-011 is the honest place to discover its reusable boundary.

The slow-failure evidence exposes a real mismatch between immediate approval
signals and delayed maintainability outcomes. Recording that limit now prevents
future automation doctrine from claiming more than its evidence can support,
without inventing premature machinery.

The repository already has meaningful but partial executable specification
coverage. Naming its layers and gaps is more trustworthy than either claiming
total mechanical parity or attempting to parse prose into false certainty.
The same concrete-first discipline argues against both a preemptive verify chip
and a standing external-watch process without an owner or consumer.

## Options Considered

- **Open a generic context story and fold the other questions into new work.**
  Rejected: existing consumers already supply the evidence, and most remaining
  calls need doctrine or honest boundaries rather than implementation.
- **Answer context placement only and defer the rest.** Rejected: the audit and
  later evidence are sufficient to close all five stale pending questions.
- **Keep context consumer-owned, record the slow-failure and layered-parity
  limits, and leave verify/HumanLayer capture-only — chosen.**

## Consequences

- No new exploration, production package, context-policy API, scheduler,
  maintainability subsystem, or generic verify chip is commissioned.
- ES-011 remains Paused until separately planned; when it wakes, it owns its
  concrete context projection.
- The harness vision now states the long-horizon limit on gate reduction.
- Development and spec docs state exactly what the standing parity evidence
  proves and what remains human-reviewed or uncovered.
- `nets-as-evals` remains capture-only.
- The Dex/HumanLayer analysis is distilled and its pending marker closes.

## Review Trigger

Revisit a shared context or verify abstraction after at least two concrete
consumers expose a stable common mechanism. Revisit slow-failure machinery when
a code-producing net claims gate reduction and can define a falsifiable
long-horizon signal. Revisit document parity when a normative behavior lacks a
test or a new binding needs conformance evidence beyond the current corpus.
