---
status: Decided
raised: 2026-07-08
decided: 2026-07-08
deciders:
  - henrique (Navigator)
supersedes:
related:
  - docs/project/decisions/records/2026-07-06T0325Z-hermes-adr-0031-minimal-event-history-record-model.md
  - docs/project/decisions/records/2026-07-06T1128Z-hermes-adr-0034-event-log-distinguishes-deterministic-and-activity-records.md
  - docs/project/decisions/records/2026-07-07T2119Z-passthrough-is-a-default-handler-color-routed.md
  - docs/project/decisions/records/2026-07-07T1610Z-purity-invariant-and-projection.md
---

# Token movements are explicit records; replay re-applies history, never re-executes

## Question

Two related event-history OPENs: are token consumption/production **explicit
records** or deltas folded inside firing records? And for a **pure** handler
(the `passthrough`/`unpack` stdlib), does its firing need any activity record —
or should it not appear as work at all?

## Decision

- **Token movements are explicit records, not deltas.** Tokens consumed, read,
  accounted, and produced are recorded as their own history records, not
  reconstructed as deltas implied by a firing record [ADR 0031 categories 5,
  10]. The marking at any point is derivable by replaying explicit token
  movements.
- **Every firing is recorded, including pure ones.** A pure handler
  (`passthrough`, `unpack`, any pure stdlib shaping handler) produces **no
  activity records** — there is no external activity to schedule, attempt, or
  observe [ADR 0034]. But its firing **is** recorded as **deterministic
  records** (firing begun, tokens consumed, tokens produced, firing completed),
  including the concrete produced tokens.
- **Replay re-applies recorded history; it never re-executes a handler.**
  Because every firing's produced tokens are recorded — pure or impure —
  replay reconstructs state by re-applying recorded token movements in recorded
  order, and never re-runs handler code (pure or impure) [ADR 0004, ADR 0034].

## Rationale

The Navigator's point: recording pure-handler firings makes replay "really
straightforward without having to compensate for different scheduling
strategies." A pure handler's output *could* be recomputed, but recording it
means replay is a **uniform re-application** of recorded firings in recorded
order — independent of the live scheduling policy, and requiring **no handler
code at replay time**. This is the strongest form of "history is the source of
truth": replay is re-application, not re-execution. The pure/impure distinction
survives only in **activity records** (impure work leaves observed-fact activity
records; pure work does not), never in whether the firing appears in history.

## Consequences

- `spec/event-history.md`: the "explicit records vs deltas" OPEN resolves to
  explicit records; the "pure handlers and activity records" OPEN resolves as
  above (recorded as deterministic records, no activity records).
- Storage cost of recording derivable pure outputs is accepted for replay
  simplicity, scheduler-independence, and code-free replay.
- The remaining ADR 0031 payload-field details (exact schemas, candidate-
  selected durability ordering, retry grouping) stay kernel-deferred
  [DR kernel-deferred-spec-details].

## Review Trigger

Revisit if recording derivable pure-handler outputs proves a real storage
problem at scale, or when the kernel fixes record payload schemas.
