---
code: CV19.DS4
level: Delivery Story
status: Done
status_reason: Three completed Technical Stories now provide bounded campaigns, exact safe failure retention/promotion, and claim-limited complementary real transaction/process/transport qualification
updated: 2026-08-19
related:
  - index.md
  - cv19-ds3-stateful-generation-and-independent-checkers.md
  - cv19-ds4-ts1-bounded-campaign-tiers.md
  - cv19-ds4-ts2-failure-retention-and-promotion.md
  - cv19-ds4-ts3-production-boundary-qualification.md
---

# CV19.DS4 — Campaign and production-boundary qualification

## Intent

Turn the deterministic harness into a dependable engineering capability with
explicit cost, cadence, replay, triage, and complementary real-boundary
evidence—without converting probabilistic exploration into a false support or
correctness claim.

## Scope

- Establish bounded campaign tiers:
  - ordinary changes run the stable regression corpus and a small fixed
    deterministic campaign;
  - scheduled or explicitly requested campaigns rotate seeds/profiles under a
    larger time/event budget; and
  - release qualification states exactly which deterministic and real-boundary
    evidence it includes.
- On failure, preserve the minimized expanded scenario, discovery metadata,
  exact replay command, failing property, commit/runtime identity, and concise
  semantic coverage. Secret, credential, raw provider, and unrestricted payload
  data never enters an artifact.
- Define retention and promotion: a failure first replays, then shrinks, then
  becomes an ordinary stable regression before the fix is accepted.
- Qualify the claim boundary for in-memory, JSONL, SQLite, PostgreSQL, Local,
  pinned Absurd, and ZeroMQ paths as applicable. Simulation checks Petrus logic
  at contract seams; focused real adapters, actual transactions, process death,
  and transport tests check behavior the simulator does not represent.
- Include back-of-the-envelope campaign capacity sketches: events and state per
  run, run count, CPU/memory/storage budget, artifact size, expected PR latency,
  and scheduled-campaign throughput. Enforce the accepted budgets.
- Add the focused command/documentation surface and update project-level Ariad
  routing accepted in DS1. A future Driver can discover, run, replay, and triage
  DST progressively without loading all historical analysis.
- Record known blind spots and periodically review profiles that stop finding
  bugs instead of assuming they are complete.

## Acceptance / Done condition

1. A fresh checkout can run the ordinary deterministic gate and one documented
   larger bounded campaign without hidden infrastructure or credentials.
2. A deliberately failing scenario produces a credential-refused,
   data-minimized useful artifact and exact replay; the retained minimized
   regression fails before and passes after the corresponding legitimate fix.
3. Campaign timeout, event, memory/state, artifact, and concurrency limits fail
   visibly with no silent truncation presented as success.
4. Real-backend/process routes cover at least one transaction crash cut, one
   actual process restart, and one transport/Worker recovery path, with their
   evidence separated from simulated claims.
5. CI and release documentation says which profiles ran, what semantic reach
   was observed, what was deselected, and what remains unmodeled.
6. Hamsterdan can consume the accepted reusable test surface without importing
   private Petrus runtime internals or duplicating its scheduler.
7. Full and release qualification pass, and independent review finds no
   correctness claim broader than the executed evidence.

## Driver QA and evidence plan

- Rehearse green, deterministic failure, shrink, replay, artifact promotion,
  and fixed-regression paths on a clean checkout.
- Compare at least one simulated crash scenario with its focused real-backend
  equivalent and document both correspondence and non-equivalence.
- Measure campaign budgets on supported CI resources rather than choosing
  arbitrary seed counts.
- Run `scripts/check full`, `scripts/check release`, the documented scheduled
  campaign, and the selected real-boundary routes with unexpected skips
  forbidden.

## Delivery plan

1. [CV19.DS4.TS1 — Bounded campaign tiers](cv19-ds4-ts1-bounded-campaign-tiers.md)
   is Done. It keeps ordinary generation in pytest and adds the larger bounded,
   seed-addressed campaign plus detached semantic reporting.
2. [CV19.DS4.TS2 — Failure retention and promotion](cv19-ds4-ts2-failure-retention-and-promotion.md)
   is Done. It retains and rehearses failed-artifact triage, credential
   refusal, minimization, exact replay, and ordinary regression promotion.
3. [CV19.DS4.TS3 — Production-boundary qualification](cv19-ds4-ts3-production-boundary-qualification.md)
   is Done. It assembles focused PostgreSQL transaction, real process-kill/
   restart, pinned Absurd Worker, and ZeroMQ transport evidence without
   presenting those owner tests as simulated evidence.
4. Accepted capacity, release guidance, claim limits, full/release
   qualification, and the focused independent overclaim review are complete.

## Delivered evidence

- Ordinary generated profiles remain normal pytest tests. The current
  scheduled cohort targeted 304 accepted examples, recorded 457 generated or
  shrink candidates under exact profile seeds, selected all four profiles,
  wrote an 8,051-byte payload-free report, and completed in 37.7 seconds.
- The deliberate liveness mutation completed reproduce, exact replay,
  minimization, bounded two-file retention, retained replay, and verification
  of the existing ordinary unmutated regression. Credential-like data,
  tampering, unknown schema, extra files, and overage fail closed.
- The six-profile complementary cohort selected all routes, completed in 7.1
  seconds, and wrote a 5,397-byte claim report. Its real transaction,
  reconstruction, Worker, and transport evidence remains explicitly distinct
  from deterministic World evidence.
- Ordinary DST passed 218 tests with skips forbidden. Full passed 2,406 tests;
  release passed 2,406 tests in bounded-parallel and fixed-serial orders.
- Focused independent review found no need to merge the transaction cut and
  actual process-restart obligations. Authority SIGKILL during an open
  transaction remains named as stronger unmodeled evidence, not implied proof.

No bounded campaign or test establishes exhaustive schedules, real provider
authority, exactly-once external effects, database power-loss behavior, or
absence of bugs.

## Out of scope

- Blocking every pull request on an unbounded swarm.
- Uploading secrets or private provider payloads as replay artifacts.
- Replacing performance/load, security, Jepsen-like external, or real-provider
  tests.
- Automatic publication of a stable public simulation-testing API.
- Claiming bug absence, exactly-once effects, or exhaustive coverage.
