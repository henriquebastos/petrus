---
date: 2026-08-10T05:04:44Z
author: Amp Lane 3
kind: experiment
related: []
verification:
  - UV_FROZEN=1 uv run pytest -q tests/petrus/impetus/test_activity_scopes_experiment.py (7 passed)
  - scripts/check quick src/petrus/impetus/activity_scopes.py tests/petrus/impetus/test_activity_scopes_experiment.py
---

# Generation-scoped Activity close/reset experiment

## Learning intent

Test the minimum semantic shape for atomically replacing one generation of
queued tokens and Activity work without choosing a production migration or
compatibility contract.

## Executable contract

- A scope identity is `(name, generation)`. Only one generation of a name is
  active at a time.
- `close(scope)` appends one `ScopeClosed` fact containing the exact queued
  token identities dropped and pending/running Activity identities cancelled.
- `reset(scope)` appends one `ScopeReset` fact containing the same cleanup plus
  the next active generation. There is no observable closed-without-successor
  gap in semantic state.
- Tokens and Activities retain their scope identity. Completed Activity output
  tokens inherit the Activity's scope and are removed if that scope later
  closes.
- The single writer's append order decides a close/completion race, even when
  both facts use the same instant. Completion appended first is accepted and
  its output is subsequently cleaned by close. Close appended first cancels
  the Activity and a later completion is recorded as
  `ActivityCompletionQuarantined`; it never enters the token queue.
- Exact redelivery of an accepted completion or quarantined late completion is
  acknowledged without another semantic fact. A conflicting result fails
  loudly.
- Replay reconstructs active generation, queued tokens, Activity phases, and
  quarantined late outcomes. A completion that arrives after close/resume has
  the same disposition as one arriving without a process restart.
- Operational cancellation notification is represented by the cancellation
  work returned only after the close/reset fact commits. A refusing History
  leaves the scope, queue, and Activity phases unchanged.

## Exact evidence

`tests/petrus/impetus/test_activity_scopes_experiment.py` pins seven cases:

1. atomic reset, cleanup, cancellation, and generation increment;
2. no cancellation/state mutation when the close append fails;
3. pending/running cancellation and identity-precise cleanup of duplicate-valued tokens;
4. completion-before-close precedence and cleanup of accepted scoped output;
5. close-before-completion quarantine at the same timestamp;
6. replay-stable late completion quarantine and idempotent redelivery;
7. close/reset resume continuity where only the new generation remains active.

The focused suite passed: `7 passed in 0.15s`.

## Failed hypotheses and production constraints

1. **A thin Engine policy is sufficient — refuted.** Current Petrus tokens are
   values with FIFO occurrence position, no durable identity or provenance.
   Exact cleanup of duplicate-valued tokens by scope requires movement History
   to retain a scope and occurrence identity (or a first-class queue-entry
   carrier); a marking-only side index would not survive replay.
2. **Existing firing cancellation is sufficient — refuted.** `Instance.fail()`
   records `ActivityFailed` plus `FiringFailed`, meaning execution exhausted,
   and intentionally leaves consumed tokens consumed. Scope cancellation is a
   different semantic terminal cause and needs an explicit record/fold; it
   must not masquerade as infrastructure failure.
3. **Dispatch can already cancel queued/running work — refuted.** The public
   `Dispatch` contract has only `dispatch` and `collect`. Local Dispatch has no
   cancelled terminal state, pending-task retirement door, running-attempt
   cancellation signal, or late-cancelled-report disposition. Cooperative
   running cancellation and lease fencing require an operational protocol
   extension.
4. **Operational cancellation can happen before History close — refuted.** If
   Dispatch cancellation succeeds and the canonical close append fails, live
   custody and replay truth diverge. The canonical close/reset must commit
   first; cancellation is a recoverable consequence/outbox of that fact.
5. **Timestamp precedence resolves races — refuted.** Equal instants are legal
   in Petrus History. Only the single writer's append position gives a total,
   replayable close-versus-completion order.
6. **Dropping late completions operationally is enough — refuted.** A silent
   drop is not replay-stable and loses conflict evidence. The experiment uses
   a canonical quarantine fact; production could choose a distinct audited
   terminal family, but the disposition must be durable if replay and resume
   are required to agree.

## Integration shape if promoted

Hamsterdan can pin this experiment and exercise
`petrus.impetus.activity_scopes.ActivityScopeRuntime` directly; it is a
standalone semantic spike and does not alter `Engine` or existing History
codecs.

A production integration would minimally need:

1. a scope reference frozen into each `ActivityRequested`/firing occurrence;
2. scope/occurrence provenance for queued token movements so close can record
   and replay exact cleanup;
3. canonical scope-open, close/reset, Activity-cancelled, and late-outcome
   quarantine/acknowledgement records and replay folds;
4. an Engine action that commits close/reset before notifying Dispatch;
5. Dispatch pending retirement plus running Attempt cancellation/fencing, with
   cancellation replay/reconciliation after Engine restart; and
6. an explicit ruling on whether cancelled input tokens are restored,
   discarded, or replaced by compensation tokens. This experiment deliberately
   does not decide that broader firing/marking policy.

## Scope limit

This is disposable evidence, not a supported API, wire schema, compatibility
promise, or production implementation. It intentionally stops before changing
the canonical Petrus History and Dispatch protocols.
