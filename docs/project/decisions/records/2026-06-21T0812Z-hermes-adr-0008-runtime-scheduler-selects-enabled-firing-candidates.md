---
status: Decided
raised: 2026-06-21
decided: 2026-06-21
deciders:
  - henrique (Navigator, via grill-with-docs in the hermes notebook)
supersedes:
related:
  - hermes ADR 0008
  - docs/project/decisions/records/2026-07-06T1505Z-absorb-hermes-adrs-into-ariad.md
---

> Migrated from the Hermes design notebook.

# ADR 0008: Runtime scheduler selects from enabled firing candidates

## Status

Accepted

## Context

Given a net state, many transitions may be enabled under many firing bindings. Some candidates may conflict because they require the same consumable tokens. If one candidate begins firing and consumes or accounts for those tokens, another candidate may become disabled.

A naive deterministic policy such as selecting candidates by transition/node name ascending can be replayable, but may starve some transitions. Other policies, such as round-robin among competing transitions or scheduling all non-conflicting candidates, may be more appropriate for different runtimes and workloads.

This makes scheduling partly policy-like even though the formal net semantics can still define which firing bindings are candidates.

## Decision

> **Scoped refinement — 2026-07-22:** DEC-035 preserves the
> enabledness-versus-policy boundary but narrows clause 2's initial production
> scope to at most one `Binding` per Engine turn; conflict-free set selection
> and partial commits are deferred. Clause 4 is refined from generic runtime
> adapter/process configuration to Candidate Selection configuration composed
> into and snapshotted by the one-Instance Engine. Existing
> `CandidateSelected` transition facts plus firing movements suffice initially;
> no durable Binding key or separate scheduler-decision record is added. See
> `2026-07-22T1413Z-candidate-selection-is-instance-scoped-immutable-policy.md`.

Petrus should distinguish candidate enablement from scheduling selection:

1. The core evaluates the current marking and net definition to enumerate enabled firing candidates.
2. The runtime scheduler chooses which candidate or conflict-free set of candidates should begin firing now.
3. `beginFiring` applies the chosen candidate(s), consuming or accounting for input tokens according to arc modes.
4. Scheduling policy belongs to the runtime adapter or process configuration, not hard-coded into the net definition.

Different runtime adapters may provide different scheduling policies, including:

- one-at-a-time deterministic selection;
- all currently non-conflicting candidates;
- round-robin among competing transitions;
- priority-based scheduling;
- fairness-aware scheduling;
- budget-aware scheduling;
- queue/capability-aware scheduling;
- deadline-aware scheduling.

If priority, fairness, budget, or exclusion is part of the domain process itself, it may also be modeled explicitly with tokens, guards, arcs, and inhibitors.

## Consequences

- The initial production Candidate Selection contract chooses at most one
  Binding per Engine turn; concurrency comes from repeated turns and existing
  in-flight semantics, not conflict-free batch selection.
- The core remains responsible for Petri-net enablement semantics.
- The runtime owns the policy of which enabled candidate(s) actually begin.
- Starvation is recognized as a scheduling-policy risk, not a hidden bug in the net core.
- Deterministic replay requires recording the selected firing candidates and their order/set in history.
- Local debugging runtimes can prefer simple deterministic policies.
- Distributed runtimes can prefer parallel scheduling of non-conflicting candidates.

## Notes

The phrase "what can fire" should be used carefully. There are at least two layers:

- **Enabled firing candidate**: a transition plus firing binding that is valid under the current marking.
- **Selected firing attempt**: a candidate chosen by the runtime scheduler to begin now.

The transition from candidate to attempt is where policy enters.

DEC-035 names that policy boundary Candidate Selection and keeps broad
whole-action precedence in `DrivingPolicy`.
