# Typed functional flow vertical slice — Experience Report

## 1. Verdict

**Promising.** One Hamsterdan-shaped durable workflow was authored as a small
typed, functional value and lowered deterministically into the current
canonical Petrus Net v3 with every durable boundary preserved, normal Engine
execution/replay/resume intact, byte-stable topology, complete
source-to-History attribution, pre-motion error locality, coarse transition
grain, and one deliberate low-level descent that never left the canonical
validation path. All fourteen mechanical completion conditions passed
(section 4). The evidence supports explanation 2 of the plan's dichotomy:
**the current authoring surface is too low-level; the canonical Petri model
itself lowered the coarse behavior without distortion.**

Baseline: Petrus `main` at `fdf7acfc059f308af57dc3fc149b21e78d17d32d`;
`git diff 0123f6cb..HEAD -- src/ spec/ tests/` is empty, so every defining
API cited by the brief was unchanged `[E]`. Hamsterdan grounding remained the
pinned revision `a14c77825d9616fe0e3f9102cd3476a597fc7da7` (links only, never
imported) `[D]`.

## 2. Source experience

The complete authored flow ([scenario.py](scenario.py)) is:

```python
def readiness_flow() -> Machine[ReadinessState]:
    return machine(
        "readiness",
        lifecycle=lifecycle("branch"),
        handlers=(
            on(await_event("head", HeadObserved)).project("admit_head", admit_head),
            on(await_event("ci", CIObserved))
            .decide("route_ci", route_ci)
            .choose(
                {
                    PublishRequested: low_level("publish_once", publication_gate,
                                                returns=PublishAcknowledged),
                    RerunRequested: effect("rerun", rerun),
                    RepairRequested: effect("repair", repair),
                    HumanNeeded: terminal("human_needed"),
                    Ignored: drop(),
                }
            ),
            on(PublishAcknowledged).fold("accept_publish", accept_publish).to(terminal("published")),
        ),
    )
```

Concepts a maintainer needs before understanding the ladder: the frozen
domain values plus **thirteen authoring constructs** — `machine`,
`lifecycle`, `on`, `await_event`, `project`, `decide`, `choose`, `effect`,
`terminal`, `drop`, `low_level`, `fold`, and `.to` (an adversarial review
corrected an earlier undercount of eight). The whole ladder semantics live in
one ordinary pure function (`route_ci`, ~60 lines) whose outcome union is
checked exhaustively before any lowering. No place, transition, arc, token,
binding, marking, or handler-URI concept is required until the reader
deliberately opens the descent fragment.

## 3. Generated topology

Exactly **14 places, 9 transitions, 28 arcs**, matching the plan's expected
counts and paths ([golden/readiness.net-v3.json](golden/readiness.net-v3.json),
sha256 `f5e4a91f…537a19`). Every transition is a durable boundary:

| Transition | Durable meaning |
| --- | --- |
| `ingress.head` | Accept one identified head observation and seed its generation state (fused projection) |
| `ingress.ci` | Accept one identified CI observation |
| `readiness.route_ci.fire` | Accept current CI evidence and commit one ladder decision |
| `effects.rerun.fire` | Request/observe the fake rerun effect |
| `effects.repair.fire` | Request/observe the fake repair effect |
| `effects.publish.authorize` | Admit one publication while none is pending or done (two inhibitors) |
| `effects.publish.execute` | Request/observe the fake publication effect |
| `effects.publish.accept` | Accept the effect terminal, release pending, latch done |
| `readiness.accept_publish.fire` | Commit the acknowledged publication into state |

Arc order is a contract: the 28 arcs group contiguously per transition in the
order above with counts `1+1+7+2+2+5+2+4+4`
(`test_expected_topology_has_only_durable_transitions` `[E]`). No compiler
connector, dispatch, map, or format transition exists.

## 4. Acceptance matrix

All evidence `[E]` (executed) unless noted. Tests live beside this file;
`UV_FROZEN=1 uv run pytest -q <this directory>` runs all 27.

| # | Completion condition | Evidence | Result |
| --- | --- | --- | --- |
| 1 | Same source compiles to byte-identical Net v3 + sidecar twice | `test_repeated_lowering_is_byte_stable_and_matches_net_v3_golden`, `test_source_map_is_stable_hash_bound_and_matches_golden` | pass |
| 2 | Canonical Net parses/compiles/validates/renders through current APIs | `test_net_v3_round_trips_through_current_parser_and_compiler` (strict `parse_net_definition`, `compile_net_definition`, deterministic `to_dot`) | pass |
| 3 | Clean CI publishes exactly once | `test_clean_ci_publishes_once_after_typed_acknowledgement` | pass |
| 4 | First exact-head failure → one rerun; duplicate spends nothing | `test_first_failure_reruns_once_and_duplicate_evidence_spends_nothing` (both Petrus `PriorAcknowledgement` and domain `Ignored` absorption) | pass |
| 5 | Strictly newer matching failure → repair, not a second rerun | `test_newer_persistent_failure_repairs_without_a_second_rerun` | pass |
| 6 | Confirmed repair keeps lineage, advances generation | `test_confirmed_repair_head_keeps_lineage_and_unrelated_head_resets_it` — established at the level of state and operation identity derived from the admitted head fact; the confirmed/unrelated classification itself (`relation`) is the head producer's input, not an in-slice decision (see §11) | pass |
| 7 | Unrelated branch → new generation, fresh retry lineage | same test, second half, same evidence basis | pass |
| 8 | Closed generation drops; unproven future quarantines | `test_closed_generation_drops_and_future_generation_quarantines_ingress` | pass |
| 9 | `Engine.load` over reconstructed store/flow/Dispatch resumes an `ActivityRequested` occurrence without re-executing completed handlers | `test_activity_requested_restart_redispatches_one_logical_operation` | pass |
| 10 | Uninterrupted and restarted runs end with equal canonical History, marking, scope, outcome | `test_restarted_and_uninterrupted_runs_have_identical_canonical_history` (JSONL bytes equal: sha256 `a75880c0…d3e22d` both) | pass |
| 11 | Every generated node and observed firing maps to an authored block | `test_every_place_transition_and_handler_has_source_ownership`, `test_every_observed_firing_explains_back_to_authored_source` (0 unattributed of 147 records) | pass |
| 12 | ≥2 deliberate composition mistakes fail pre-motion naming block + location | `test_composition_refuses_mismatched_ports_at_both_source_locations`, `test_choose_refuses_a_missing_outcome_before_lowering` (plus duplicate-id and nominal-collision refusals) | pass |
| 13 | Inhibitor gate authored through descent, still canonical, visibly prevents double publication | `test_low_level_publication_gate_uses_an_inhibitor_and_canonical_validation`, `test_publication_inhibitor_allows_only_one_pending_operation` (with counterfactual open gate: 2 authorized without the arcs, 1 with) | pass |
| 14 | Helper calculations create no transitions or History rows | exact-set topology assertion (any helper-grown node fails it) + `route_ci`/helpers exercised in every scenario test | pass |

Additional gates: `ruff check`/`format` clean, `ty check` on all eight source
modules clean, `ast-grep scan` clean, the focused existing Petrus contract
suites (219 tests) pass unchanged, and the full deterministic repository
suite was run (see Limits for the macOS `flock` note).

## 5. Restart route

Exact interruption point: after the step-12 delivery (`ci-20-2-g2`), the
Engine advanced only until `ActivityRequested` for `effects.repair.fire` was
durable; the run asserts no `ActivityCompleted` exists for that occurrence,
then closes the Engine. Reconstructed through public doors only: the source
value (`readiness_flow()` re-authored), `compile_flow` re-run, a new
`JsonlHistoryStore` over the same path, a fresh `InlineDispatch`, and
`Engine.load`. The first `advance()` reconciled and redispatched the recorded
outbox with the recorded correlation/idempotency `repair:L2:build`.

Observed: the independent fake-provider ledger counted **two delivery
attempts and one logical repair operation/result**; canonical History bytes,
records, final marking, active scopes, and the explained trace equal the
uninterrupted control run exactly.

Claims deliberately **not** made: OS-process kill or power-loss durability,
remote Worker recovery, or exactly-once effects. This is in-process
object-reconstruction evidence over the real durable JSONL store, and the
fake ledger simulates a provider idempotency boundary — it is not proof about
real providers.

## 6. Attribution

Chain example (from [golden/readiness.explained-history-v1.json](golden/readiness.explained-history-v1.json)):
authored `route_ci` at `scenario.py` → generated transition
`readiness.route_ci.fire` (source-map element, role "durable decision") →
occurrence group in the explained History showing the accepted
`CIObserved` and the produced `RerunRequested(operation=rerun:L2:build)`
tokens. Unattributed-record count: **0 of 147**, enforced by
`unattributed_records()` and pinned by test. Scope records attribute to the
authored `lifecycle("branch")` declaration; `InstanceCreated` attributes to
the authored machine root. The sidecar is hash-bound to the exact Net v3
bytes and is regenerated byte-identically from a reloaded Engine's records —
it is never execution authority.

## 7. Error locality

Deliberate mistakes and their diagnostics (asserted on fragments, not
tracebacks), all raised before any History file exists:

- Port mismatch: `CompositionError: test_algebra.py:89 [route_failed]
  produces RerunRequested, but test_algebra.py:53 [repair] accepts
  RepairRequested` — both source locations named.
- Missing branch: `… [route] has no branch for HumanNeeded`.
- Duplicate authored ids name both call sites; two distinct classes sharing
  one nominal name are refused with both classes named.

## 8. Descent

The publication gate needs *absence* — "no publication pending or done" —
which the typed algebra deliberately has no vocabulary for; the inhibitor arc
is exactly that expression, so `low_level` is honest descent rather than a
workaround. The fragment declares raw nodes/arcs through a bounded
`FragmentContext` that (a) keeps every created node inside `effects.publish`,
(b) records source-map ownership per node, (c) routes its Activity through
the same URI-bound `DerivedActivityHandler` composition, and (d) is
re-verified after `NetSpec.build()`; the whole net still round-trips strict
Net v3. The counterfactual (same fragment minus the two inhibit arcs) admits
both directly supplied requests; the authored gate admits one concurrently
(`pending`) and one per generation (`done` latch).

## 9. Grain assessment

Ordinary functions that never became nodes: operation-id formatting, evidence
ordering (`evidence_key`/`is_newer`), retry-key construction, and the
`Ladder` bookkeeping — all called inside `route_ci`'s single firing. One
domain decision lowers to exactly one transition; the 147-record fixture
History contains only durable facts (deliveries, scope lifecycle, firings,
token movements, Activity boundary records). No bookkeeping firing was found;
the exact-topology test makes one impossible to introduce silently.

The one fusion worth naming: `await_event("head").project("admit_head", …)`
fuses event acceptance and state seeding into one source firing. This is not
a hidden transition: the accepted head fact and the produced state are both
explicit in canonical History and map to the authored block.

## 10. Comparison with direct authoring

Qualitative (line counts are supporting data only):

- **Concepts before understanding:** direct `NetSpec` authoring of this net
  requires places/transitions/arcs/colors/handlers/`Binding`/`Token`
  selection order and handler-URI plumbing up front (the compiler bridges in
  `lowering.py` show exactly the Petri-aware code a direct author would
  write by hand — ~570 lines of it). The typed source needs the eight
  constructs of section 2, and the Petri vocabulary only inside one fragment.
- **Explanation steps:** the ladder is explained by reading `route_ci` top to
  bottom; in direct authoring the same explanation crosses the route
  handler, five output arcs, and three effect transitions.
- **Change locality:** adding a ladder rung is one branch in `route_ci` plus
  one case in `choose` — the compiler grows the command place, transition,
  and arcs; the port check refuses a forgotten branch before motion.
- **Topology visibility:** unchanged — the canonical Net, DOT rendering, and
  Net v3 bytes remain first-class inspectable artifacts, byte-stable.
- Supporting data `[E]`: authored surface (`scenario.py` + `domain.py`) ≈
  520 lines including the descent fragment and naming-required simplification
  notes; disposable compiler machinery (`algebra.py` + `lowering.py` +
  `source_map.py` + `explain.py`) ≈ 1,500 lines. Hamsterdan's comparable
  hand-authored `readiness/net_v5` package is 4,403 lines for nine loops
  `[D]` — as measured by ES-059's source-grounded analysis against the
  pinned Hamsterdan revision; no Hamsterdan checkout exists in this
  repository to re-measure.
- **Comparison limit (named honestly):** no executed direct-authoring twin of
  this exact slice was built, so the reading-improvement judgment is
  qualitative — grounded in the Petri-aware bridge code a direct author would
  hand-write (visible in `lowering.py` and the descent fragment) and in
  Hamsterdan's retained V5 package, not in a side-by-side artifact. The
  mechanical completion conditions do not, by themselves, prove the surface
  reads better; adversarial review flagged this and the verdict weighs it as
  the main residual judgment call for the Navigator.

## 11. Limits and surprises

- **Simulated vs Petrus-executed:** rerun/repair/publish are fake typed
  Activities behind an in-memory idempotency ledger; only their
  request/acceptance boundaries are Petrus-executed evidence. Review,
  findings, approval, mergeability, mutation, and fault gates are
  pre-satisfied fixture assumptions, named in `scenario.py`.
- **One baton per generation:** scope reset discards the old state and the
  successor head seeds a fresh ladder, so rerun/repair budget does not carry
  across generations; the retained lineage keeps operation ids stable, which
  is where cross-generation idempotency actually lives.
- A failure without a fingerprint is absorbed as `Ignored` (no ladder rung to
  spend) — a fixture decision, not V5 semantics.
- **Surprise (good):** the current `Engine`/`Instance` scope propagation,
  idempotent delivery, and reconcile-then-drive behavior needed no adaptation
  at all; the whole runtime slice worked against public doors on the first
  green run.
- **Surprise (friction):** `DerivedActivityHandler` cannot be attached
  through the DSL's transition-callable path, so Activity transitions declare
  symbolic handlers and bind by canonical URI after build — exactly the seam
  the plan predicted; a promoted authoring layer would want this fused.
- Value-only constructs (`await_event`, `terminal`, `lifecycle`, `machine`,
  `effect`) capture their call-site file/line at construction for
  attribution; only plain strings/ints are retained and nothing consults
  frames during execution or resume. Function-bearing constructs
  (`project`/`decide`/`fold`/`low_level`) use `__code__` locations. Line
  numbers make the source-map golden sensitive to `scenario.py` edits —
  acceptable for a golden that is regenerated deliberately, and the
  bundle-freshness test fails loud on a stale golden or artifact.
- **The state baton is host-disciplined, not topology-guarded** `[E]`: a
  current-Petrus source transition cannot carry guards or input arcs, so
  `ingress.head` cannot structurally refuse a second head in one generation —
  two heads delivered under one open scope would seed two batons. The fixture
  and V5 both deliver exactly one head per generation (branch movement is a
  scope reset); a promoted authoring layer wanting a structural guarantee
  would need a durable admission transition between the event and the baton,
  at the cost of one extra firing per head. Named here because the experiment
  judged the analogous single-admission property worth an inhibitor for
  publication.
- `HeadObserved.relation` is honest ingress data that no slice code branches
  on: lineage continuity is supplied by the head producer, so completion
  conditions 6/7 test faithful propagation into state and operation
  identity, not an in-slice incarnation decision.
- An `Ignored` decision is attributable in History only as a
  state-reproducing `readiness.route_ci.fire` firing with no command token —
  its `reason` never becomes a durable fact. A promoted design should decide
  whether absorption reasons deserve a durable spelling.
- The counterfactual `_open_gate` in `test_scenario.py` is a hand-authored
  copy of `publication_gate` minus its two inhibit arcs, not a derived
  variant; if the authored gate changes, the copy must be updated with it.
- `scripts/check full` refuses to run on this macOS host because `flock` is
  unavailable; the equivalent gate (quick checks plus the full deterministic
  seed-1729 suite on four workers with `--forbid-skips`) was run directly:
  **2,403 passed, 3 failed**. The three failures
  (`tests/petrus/agenticus/runtime/test_pi_a2_host.py` ×2 and
  `tests/dst/test_dst_boundaries.py::test_real_boundary_route_…`) were
  re-run on the clean baseline with this experiment's files stashed and fail
  identically there — pre-existing host-environment failures, not ES-059
  regressions `[E]`.
- Tree deviation from the plan: `artifacts/` additionally retains
  `readiness.history.jsonl` (the accepted fixture History; restarted copy is
  byte-identical so only its hash is recorded in
  [artifacts/experiment-report.json](artifacts/experiment-report.json)).
- The repository's `testpaths = ["tests"]` deliberately excludes this
  exploration directory: its 27 tests run only when invoked explicitly (the
  README's command). A future `src/petrus` change can therefore break this
  experiment silently until someone reruns it — expected for disposable
  Exploration evidence, and worth knowing before citing this report.

### Adversarial review round

Two independent adversarial reviews (one Claude, one gpt-5.6-terra via
Codex) attacked the implementation against the plan. Confirmed findings and
their resolutions, all fixed before this report's final state `[E]`:

1. `deliver_head` accepted a head observation whose domain `generation`
   disagreed with the exact delivery scope's generation → the harness now
   refuses the mismatch (`test_head_generation_must_match_its_exact_delivery_scope`).
2. A low-level fragment could draw arcs to nodes outside its scope (e.g.
   `readiness.state`) while node-creation checks passed → `FragmentContext`
   now admits arc endpoints only among fragment-owned nodes and the two
   supplied ports (`test_low_level_fragment_cannot_reach_outside_its_scope`).
3. The missing-branch refusal test did not pin the source location or the
   no-motion property → it now asserts both.
4. The inhibitor counterfactual counted pending productions, which serial
   execution could also satisfy → it now replays movement records and asserts
   peak concurrent pending occupancy (2 without the arcs, 1 with).
5. "No completed handler re-executes on load" was only evidenced through the
   fake Activity ledger → an instrumented flow now proves the pure
   projection/decision/fold functions are called zero times across
   `Engine.load` + drain.
6. The reading-improvement claim lacked a direct-authoring twin → recorded as
   the named comparison limit above rather than as established fact.

Round two (independent Claude review) confirmed further findings, all
resolved before this report's final state `[E]`:

7. Post-build verification never inspected fragment arcs (same defect as 2,
   found independently with a working escape probe) → closed by the
   endpoint admission rule plus its refusal test.
8. Two heads in one generation seed two state batons → documented as the
   host-discipline limit in §11 and in `scenario.py`'s named simplifications;
   `deliver_head` additionally refuses a generation/scope mismatch.
9. `HeadObserved.relation` is dead data making conditions 6/7 read weaker
   than the matrix suggested → evidence basis restated honestly in §4 and
   §11.
10. The retained DOT, machine-readable report, and History artifacts were
    asserted by no test → a bundle-freshness test now regenerates the whole
    evidence bundle and byte-compares every retained golden and artifact.
11. One rendering assertion was a tautology (`f(x) == f(x)`) → replaced with
    a cross-lowering canonical-render comparison; the retained DOT now
    renders the canonical parsed net rather than the authored-order net.
12. The duplicate-id refusal could be defeated by two constructs on one
    source line → ids now collide by id alone, pinned by test.
13. An Activity request type without an `operation` field failed only at
    firing time → `effect()` and the descent seam now refuse it before
    motion.
14. Effect attribution pointed at the Activity implementation's decorator
    line instead of the authored choose branch → `effect()` now captures its
    authoring call site, so change locality points at the flow.
15. The construct-count and evidence-grading gaps in this report were
    corrected (§2, §10), and the `_open_gate` copy plus `Ignored`
    invisibility limits were named (§11).

## 12. Driver recommendation and next route

Classify **promising** and attach this report to ES-056's AX28/AX29 evidence.
The bounded next questions a promotion decision needs, in order: (1) whether
the Navigator accepts this source experience shape at all; (2) a public
source-map/evolution decision to replace this sidecar format; (3) AX28's
honest first-motion profile over a real run surface; (4) AX29's maintained
descent contract (this experiment's `FragmentContext` is evidence it can be
bounded); (5) a larger Hamsterdan benchmark for constructs this slice
deliberately excluded (parallel joins, timers, resource scopes, cross-loop
composition). No code moves out of Exploration and no roadmap or Delivery
change follows from this result without Navigator direction.
