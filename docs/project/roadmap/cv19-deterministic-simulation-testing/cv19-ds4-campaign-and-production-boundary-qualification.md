---
code: CV19.DS4
level: Delivery Story
status: Planned
status_reason: DST does not yet have bounded CI operations, retained failure artifacts, or a qualified relationship with real Petrus backends and transports
updated: 2026-08-17
related:
  - index.md
  - cv19-ds3-stateful-generation-and-independent-checkers.md
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
2. A deliberately failing scenario produces a redacted useful artifact and
   exact replay; the retained minimized regression fails before and passes
   after the corresponding legitimate fix.
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

## Out of scope

- Blocking every pull request on an unbounded swarm.
- Uploading secrets or private provider payloads as replay artifacts.
- Replacing performance/load, security, Jepsen-like external, or real-provider
  tests.
- Automatic publication of a stable public simulation-testing API.
- Claiming bug absence, exactly-once effects, or exhaustive coverage.
