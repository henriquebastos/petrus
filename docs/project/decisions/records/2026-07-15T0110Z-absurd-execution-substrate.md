---
status: Decided
raised: 2026-07-13
decided: 2026-07-14
deciders:
  - henrique (Navigator)
related:
  - docs/project/decisions/records/2026-07-14T2016Z-activity-invocation-runtime-seam.md
---

# Adopt Absurd as CV3's execution-adapter substrate (ES-012 D11)

## Question

Build-vs-buy on the dispatch floor: does CV3's execution adapter run on the
Impetus-owned native PostgreSQL floor, on Absurd, or on a new composition —
and where does ZeroMQ fit?

## Decision

> **Partial supersession — 2026-07-22:** DEC-039 supersedes only clause 1's
> inclusion of “the Impetus semantic append” in the Worker-held transaction.
> Workers now produce operational terminal reports only; Instance-side
> authority accepts them and Instance alone appends canonical semantic History.
> Absurd claim/handler/checkpoint/`complete_run` operational atomicity and every
> other clause below remain in force. See
> `2026-07-22T1031Z-instance-authors-terminal-history-and-shared-firing-transform.md`.

1. **Absurd 0.4.0 — hash-pinned, never forked — is the substrate CV3's
   execution adapter builds on**, running the transaction-mode loop the full
   matrix proved [E]: the unmodified SDK on a caller-provided connection, so
   claim → handler → checkpoint → `complete_run` and the Impetus semantic
   append commit or vanish as one transaction.
2. **The dispatch-latency gap closes with an adapter-side doorbell, not an
   engine change.** The Impetus adapter issues `pg_notify` inside the same
   spawning transaction (Postgres NOTIFY is delivered on commit — no phantom
   wakes); workers LISTEN and treat a notification purely as a wake hint that
   triggers an immediate `claim_task`; polling stays on as the safety net
   because NOTIFY is lossy. This is the native floor's own ratified discipline
   ("LISTEN/NOTIFY is only a wake hint: every wake and every (re)connect polls
   first" — `native-postgresql-control/worker.py`), composed with Absurd
   untouched.
3. **Impetus keeps what no substrate solved:** canonical history
   (`impetus.semantic_events`-shaped, Impetus-owned), duplicate-observation
   discipline (the K6 refinement: the engine refuses duplicate *delivery* but
   silently accepts post-terminal checkpoint upserts — it will not backstop
   observation discipline), and K4 lookup-first reconciliation against
   idempotent external targets.
4. **The native floor is the documented fallback.** Its evidence stands; its
   `semantic_events` schema, one-terminal-per-firing index, and
   verify-on-conflict acceptance discipline are the Impetus-owned layer that
   lives on top of Absurd. If Absurd must be abandoned, operational state is
   reconstructible and canonical truth is never in it — the exit is bounded by
   the activity-invocation seam's own design.
5. **ZeroMQ is deliberately deferred to the attach/Q7 layer, not rejected.**
   The doorbell need that the zmq-as-doorbell synthesis was to fill is filled
   by Postgres itself, one dependency cheaper. What zmq uniquely offers —
   attach streams, multi-client fan-out with cursor replay, mesh/multiplayer
   topologies — belongs to the attach layer, future work with its Q7 evidence
   already banked.
6. **The unit of worker concurrency is a connection, not a thread.** The SDK
   shares one psycopg connection per client, and a connection holds one
   transaction at a time, so a transactional-delivery client processes one
   delivery at a time regardless of thread count. CV3 sizes workers as
   processes/clients-times-small-pools; `SKIP LOCKED` makes concurrent
   claimers safe and the doorbell wakes them for ~nothing.

## Rationale

The full matrix (23 scenarios, 87 checks, no [X]) held every bounded-probe
posture under real mid-transaction SIGKILLs: the K1/K2/K5 boundaries dissolve
in the same-transaction shape, K3 recovers by claim-driven lease expiry in the
measured two passes, and the continue-wave — fold + N spawns + ack — commits
atomically in one Python-held transaction, the exact shape that disqualified
every queue library probed.

The choice is low-stakes by construction because of the 2026-07-14
activity-invocation ruling: execution adapters own dispatch, retries, claims,
and leases, and that operational state is "reconstructible machinery rather
than canonical net truth." Absurd sits entirely on the adapter side of that
seam. Nothing canonical ever lives in it.

The quality question dissolved on first-hand read: the native floor is a
proof — fixture vocabulary, hardcoded instance id, no retries/events/sleep/
maintenance/packaging — and exactly as good as a proof needs to be; Absurd is
a substrate product (one 3,083-line plpgsql file, function-per-operation,
explicit lock-ordering, bounded sweeps, partitioning + pg_cron lifecycle, a
2,300-line worker SDK). Ruling "build" would mean months growing the floor
into an Absurd-shaped thing — substrate work that is not Impetus's
differentiator.

Select-zero is untouched. Absurd has no worker runtime of its own — the
engine is a SQL schema and the wave transaction stays in whatever language
holds the connection — so it competes with the native floor, not with the
queue trio the ratified gate rejected.

The dominant condition is maturity (0.4.x, Alpha classifier, one primary
author, first commit 2025-10), mitigated by: the schema is hash-verified
before apply (already the harness practice), every operation is readable
plpgsql, the license is Apache-2.0, and the native floor is the documented
fallback with its evidence already committed.

## Options Considered

- **Productize the native floor (build).** Rejected: the 715 lines are a
  proof, not a product; the missing features (retry strategies, events,
  durable sleep, maintenance, SDK) are precisely what Absurd already ships and
  kill-tested green.
- **Adopt Absurd, doorbell adapter-side — chosen.**
- **Fork/patch Absurd to add LISTEN/NOTIFY.** Rejected: the moment we patch it
  we own a fork of an Alpha engine; the doorbell is naturally adapter code and
  the same-transaction shape already puts the adapter inside the spawning
  transaction.
- **ZeroMQ as the dispatch doorbell now.** Deferred: Postgres NOTIFY fills the
  need one dependency cheaper; zmq's distinct value is the attach layer.
- **Foreign-runtime substrates (Temporal, Restate, Hatchet, queue trio).**
  Already excluded by the ratified select-zero/continue-wave rationale: the
  kernel's event history must be Impetus-owned and fully recoverable, and a
  substrate whose runtime holds the kernel competes for process truth.

## Consequences

- Clause 1's worker-side semantic append is superseded as noted above;
  operational Absurd state remains distinct from canonical History.
- CV3's scope line changes from "a minimal dispatch/queue layer of our own" to
  an Impetus-owned execution adapter over Absurd (roadmap updated with this
  record).
- The Absurd fit-map row is adopted into the comparison artifact, amended with
  the matrix deltas; the ES-009 timeline records the probe, the matrix, and
  this ruling.
- The CV3 dispatch slice inherits explicit adapter obligations: the doorbell,
  the K6 observation discipline, K4 reconciliation, and
  connection-per-worker-unit sizing.
- ES-012 D11 closes; the adjudication threads it reserved (the combined
  substrate-plus-transport question) close with it.

## Deferred

- The attach/Q7 transport (ZeroMQ or otherwise) and any multi-client
  fan-out/mesh topology — future attach-layer work.
- Absurd version upgrades: each re-pin is a deliberate act with the schema
  hash re-verified and the matrix rerunnable (`absurd-full-matrix/run-proof.sh`).
- The overnight run's provisional method decisions (harness layout, latency
  assertion style, etc.) ride separately in the ES-012 log; this record rules
  the substrate only.

## Review Trigger

The CV3 dispatch slice's four-gate run; any Absurd re-pin whose schema diff
touches claim/complete/checkpoint semantics; any evidence of the engine
competing for process truth; or the attach layer forcing a transport decision.
