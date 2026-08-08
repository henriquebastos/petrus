---
status: Decided
raised: 2026-07-21
decided: 2026-07-22
deciders:
  - henrique (Navigator)
supersedes:
  - ADR 0008 clause 2 only insofar as the initial scheduler could choose a conflict-free set; initial Candidate Selection chooses at most one Binding per Engine turn
  - ADR 0008 clause 4 only insofar as selection configuration was left generically with a runtime adapter; it is snapshotted Engine composition per Instance
  - ADR 0009's initial pluggable-scheduler scope only insofar as it combined candidate choice with all-non-conflicting, bounded-parallel, budget, deadline, queue, capability, and concurrency policy
related:
  - docs/project/decisions/records/2026-06-21T0812Z-hermes-adr-0008-runtime-scheduler-selects-enabled-firing-candidates.md
  - docs/project/decisions/records/2026-06-21T0817Z-hermes-adr-0009-default-scheduler-is-conservative-and-pluggable.md
  - docs/project/decisions/records/2026-07-21T0809Z-concept-first-ontology-boundaries.md
  - docs/project/decisions/records/2026-07-22T0245Z-engine-is-one-live-instance-composition.md
---

# Candidate Selection is per-Instance policy with immutable committed state

## Question

What exact policy boundary chooses among already-enabled Petri Bindings, where
does its configuration and state live, how does state advance durably, and what
initial fairness, composition, admission, concurrency, and History contracts
should production validate?

## Decision

Candidate Selection is an Engine-composed, per-Instance policy boundary. Within
the `BeginCandidate` action class, it chooses at most one already-enabled
production `Binding`.

Petrinet owns deterministic enabledness and remains policy-free. Candidate
Selection owns operational admission, ranking, and choice among the enabled
Bindings. The existing broad whole-action `DrivingPolicy` remains responsible
for precedence among accepting Activity outcomes, accepting deliveries,
beginning a candidate, advancing time, waiting, and stopping. Instance records
the committed selection.

The base Candidate Selection contract promises no universal fairness grain.
Initially validate and support:

- **First**, preserving deterministic Petrinet enumeration order;
- **Priority**, configured outside the Net; and
- **transition-level Round-Robin**, with per-Instance state reconstructed from
  committed selection facts.

Each implementation documents its behavior. Binding-level fairness and a
configurable fairness grain are deferred until a concrete requirement and a
safe durable Binding identity exist.

Use production `Binding` values as in-memory candidates. Do not promote the
experiment's `(transition, per-offer ordinal)` key, add a public `Candidate`
wrapper, add a durable binding key, or add a separate scheduler-decision record
now. Existing `CandidateSelected` transition facts whose occurrences have a
matching committed `FiringBegun` are sufficient to rebuild the initial
transition-grain state; firing movement records continue to explain the actual
selected Binding.

Candidate Selection state is Engine-local and Instance-scoped in effect. There
is no global or shared cursor. State changes only after the corresponding
Instance selection/begin append commits and is reconstructed on load or replay
by folding only selections with a matching committed `FiringBegun`. A
complete-line-prefix backend may retain an orphan `CandidateSelected` while
correctly treating its begin as uncommitted; that orphan still spends its
occurrence identity under existing recovery rules but must not advance
selection state.

The target design uses explicit immutable state transitions, not the
experiment's mutable `committed()` callback. Conceptually, selection returns a
proposed choice and proposed next state. Append failure discards both; append
success installs the proposed state; replay folds committed selections. The
exact type and API belong to the implementation story.

Priority belongs to Candidate Selection configuration composed into and
snapshotted by the one-Instance Engine. It is neither intrinsic Petrinet
transition semantics nor ambient fleet-host policy.

Composition is one bounded fixed pipeline:

```text
zero or more admission filters
→ zero or more stable rankers
→ one selection strategy
```

Multiple component implementations and ordinary composition are permitted.
Original deterministic Petrinet candidate order is always the final
tie-breaker. Do not create an arbitrary recursive policy language.

When Petrinet produces no enabled Bindings, Candidate Selection is not invoked.
When enabled Bindings exist but filters admit none, Candidate Selection returns
`None` to whole-action `DrivingPolicy`; it does not fail. An operational
Observation should explain the policy exclusion, but declining to act appends
no canonical semantic History. DEC-038 owns the exact future Observation shape
and remains pending.

Candidate Selection chooses at most one Binding per Engine turn. Concurrency
comes from repeated turns and established in-flight semantics, not batch
selection. Conflict-free multi-selection and partial-commit semantics are
deferred.

The selected policy state cannot advance unless beginning the offered Binding
commits. This decision changes no production code, History schema, record
payload, ordering, or behavior.

## Rationale

This split gives each layer one question. Petrinet answers what is enabled;
Candidate Selection answers which enabled Binding to offer for this
`BeginCandidate`; `DrivingPolicy` answers which action class should proceed;
Instance supplies the canonical commit boundary. Keeping selection state
immutable until append succeeds prevents a failed begin from moving fairness
ahead of History and makes replay the same fold as live commit.

Transition-level state can be reconstructed from existing `CandidateSelected`
facts whose occurrences have matching committed `FiringBegun` records, without
inventing durable identity. Firing movement records already preserve the
Binding's actual token effects. This supports the demonstrated baseline while
refusing to freeze the experiment's offer-local key or mutable callback into a
public contract.

A fixed pipeline permits useful admission, ranking, and selection composition
without creating a recursive policy language. Returning `None` for complete
policy exclusion keeps the condition operational and lets the existing
whole-action policy decide what else to do.

## Options Considered

- **Transition-grain fairness first — chosen as one implementation, not a
  universal contract.** It is reconstructible from existing facts.
- **Binding-grain or configurable fairness.** Deferred until durable Binding
  identity and a concrete requirement exist.
- **Experiment `Candidate` key/wrapper and mutable `committed()` callback.**
  Rejected for production: the key is offer-local and mutable state can advance
  before canonical commit.
- **Priority on transitions.** Rejected: it would turn operational scheduling
  configuration into Petrinet semantics.
- **Ambient fleet-host priority.** Rejected: a live Engine snapshots one
  Instance's policy configuration.
- **Arbitrary policy combinators.** Rejected in favor of the bounded fixed
  filter/rank/select pipeline.
- **Fail when filters admit none.** Rejected: return `None` and expose an
  operational Observation instead.
- **Batch all non-conflicting candidates.** Deferred: it introduces conflict
  sets and partial-commit semantics beyond the one-writer turn.

## Consequences

- A bounded Technical Story will validate the production Candidate Selection
  API and its integration; this record does not implement it.
- `Scheduler` and `select_conservative` remain temporary implementation
  vocabulary until that story provides their replacement. DEC-040 subsequently
  ruled that they receive no pre-release compatibility window.
- ADR 0008's enabledness-versus-policy boundary remains accepted. Its initial
  conflict-free-set possibility is narrowed to one Binding per Engine turn;
  multi-selection is deferred.
- ADR 0009's conservative deterministic intent and explicit pluggability remain
  accepted. Candidate Selection's initial policy family is bounded to First,
  Priority, and transition-level Round-Robin; concurrency/budget/deadline/
  capability concerns do not silently enter this boundary.
- Empty policy admission requires a future operational explanation. DEC-038
  owns Observation semantics and is not adjudicated here.
- DEC-036 subsequently extinguished Worker capability vocabulary in favor of
  operational Engine queue routing. Candidate Selection remains entirely
  separate from that routing.

## Review Trigger

Return to the Navigator if implementation needs a durable Binding identity, a
new semantic record, binding-level/configurable fairness, arbitrary recursive
composition, batch/partial commit, shared state across Engines, priority in the
Net, or an Observation contract before DEC-038 is ruled.
