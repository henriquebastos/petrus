---
code: CV19.DS4.TS3
level: Technical Story
status: Done
status_reason: One bounded repository-owned operation now executes all six exact owner routes and reports their distinct claims, correspondence, limits, and unmodeled authority-process cut
updated: 2026-08-19
related:
  - index.md
  - cv19-ds4-campaign-and-production-boundary-qualification.md
  - cv19-ds4-ts1-bounded-campaign-tiers.md
  - cv19-ds4-ts2-failure-retention-and-promotion.md
---

# CV19.DS4.TS3 — Production-boundary qualification

## Intent

Make the real storage, process, Worker, and transport evidence which bounds
DST's claims one explicit repeatable operation without moving those behaviors
into the simulator or duplicating their owner tests.

## Scope

- Run the existing deterministic Dispatch-refusal crash/load story beside the
  exact existing real PostgreSQL/Absurd authority, Worker SIGKILL, and ZeroMQ
  process-restart nodes.
- Retain a bounded payload-free report naming each selected/deselected route,
  executed cut, recovery, evidence kind, justified claim, runtime/repository
  identity, and unmodeled boundaries.
- State the correspondence and non-equivalence between deterministic World
  generation loss and the real post-commit authority reconstruction.
- Bound concurrency, wall time, termination escalation, diagnostic output, and
  report bytes. Refuse an empty, duplicate, unknown, timed-out, skipped, failed,
  or oversized qualification as success.
- Keep test orchestration under `tests/dst`; real fault mechanics remain in
  their PostgreSQL, Motus Worker, and ZeroMQ owner tests.

## Acceptance / Done Condition

1. One repository-root command runs all six exact routes without hidden
   credentials beyond the ordinary ephemeral PostgreSQL harness and writes a
   bounded report.
2. Real evidence includes an open joined-transaction server abort and fresh
   authority recovery, post-commit provider reconstruction, Worker SIGKILL and
   lease redelivery, uncertain terminal redelivery across dispatch-server
   death, and lease/detail recovery across server restart.
3. The report does not call connection drop an authority OS kill and preserves
   actual authority SIGKILL during an open transaction as an explicit blind
   spot.
4. The simulated/real comparison names their shared stable-invocation contract
   and why their mechanisms are not equivalent.
5. Focused, ordinary DST, full, and release checks pass.

## Delivered evidence

- `python -m tests.dst.boundaries` ran all six profiles in one serial child and
  wrote a 5,397-byte report in 7.1 seconds. Every exact owner node passed with
  no skips or deselection.
- Real cuts covered joined PostgreSQL/Absurd server abort after connection
  drop, fresh post-commit authority reconstruction, Worker SIGKILL after one
  external-effect commit, ZeroMQ death after uncertain terminal commit, and
  ZeroMQ death/restart with a live lease and retained checkpoint details.
- The report compares deterministic Dispatch-refusal crash/load with real
  post-commit PostgreSQL/Absurd reconstruction only at their shared stable-
  invocation contract. It explicitly states that neither authority route uses
  OS process kill and retains authority SIGKILL during an open transaction as
  unmodeled.
- A focused independent acceptance review concluded that DS4's transaction
  cut, actual process restart, and Worker/transport obligations are distinct
  routes; requiring authority SIGKILL during the transaction would strengthen
  the accepted contract rather than enforce it.
- The complete ordinary DST suite passed 218 tests with skips forbidden. Full
  qualification passed 2,406 tests, and release qualification passed 2,406
  tests in both bounded-parallel and fixed-serial orders.

No production runtime, provider adapter, process behavior, supported DST API,
artifact schema, or replay behavior changed. This Technical Story only selects
existing evidence owners and reports their bounded claims.

## Correctness sketch

- **Authority:** each existing owner test remains authority for its behavior;
  the operation only selects nodes and reports static claim metadata after a
  complete pytest pass.
- **Safety:** a failed, skipped, partial, timed-out, or unrecognized cohort
  cannot produce a passing route or per-profile qualification.
- **Liveness:** each child cohort has a wall deadline and bounded terminate/kill
  escalation; this is harness containment, not deterministic convergence.
- **Bounds:** six profiles, one serial child, 120 seconds, 5-second termination
  grace, 8 KiB failure-output tails, and a 256 KiB report are fixed ceilings.
- **Nondeterminism:** operating-system, PostgreSQL, Worker, and ZeroMQ timing is
  intentionally real evidence and is not serialized as a replay artifact.
- **Crash cuts:** only the Worker and dispatch server are actually killed;
  authority transaction loss uses real connection drop/server abort and
  post-commit authority loss abandons process-local objects.
- **Independent judgment:** owner tests query canonical History, Absurd tasks,
  effect rows, leases/details, and collected terminal facts; the report does
  not infer those outcomes itself.

## Out of Scope

- Adding a new authority subprocess solely to SIGKILL it during an open
  transaction.
- Database server kill, power loss, replication/failover, or storage faults.
- Network partitions, live providers, credentials, or application authority.
- Moving production-boundary mechanisms into World or claiming deterministic
  replay for nondeterministic process evidence.
