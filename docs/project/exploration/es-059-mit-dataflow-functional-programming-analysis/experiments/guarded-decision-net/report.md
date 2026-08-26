# Guarded decision net (Option B) — Experience Report

Experiment v2 of ES-059. It re-runs v1's question with the opposite lowering:
one guarded transition per ladder rung instead of one transition for the whole
decision. Read [v1's report](../typed-flow-vertical-slice/report.md) first;
this report only records the difference and what it cost.

A sibling session is separately testing Option A (a one-transition case table)
under `experiments/algebraic-decision-table/`. This experiment neither read nor
waited for it; any comparison across all three is the Navigator's.

## 1. Verdict

**Mixed — a real, durable visibility win bought with a real, unprovable proof
obligation.**

Everything v1 established survives the split unchanged: the same 24-step
fixture, the same domain outcomes, the same ledger operations, the same
restart/replay equality, complete source attribution, byte-stable canonical
topology, and — the claim most at risk — **exactly the same History grain**,
147 records, record type for record type, against v1's own run `[E]`.

What the split buys is one thing v1 explicitly could not do: the ladder is in
the canonical topology, and "why nothing happened" is a durably named firing
rather than an absence. That closes v1 report §11's Ignored-invisibility limit.

What it costs is three things, and the third is why the verdict is mixed, not
promising:

1. topology grew 9 → 13 transitions and 28 → 40 arcs for zero new durable
   behavior;
2. the shared sequential classification each predicate and fold must re-derive
   is real duplication (nine of the fourteen pure rung functions call it); and
3. **mutual exclusivity and exhaustiveness moved from "guaranteed by the
   language" to "the author's problem, checkable only by test."** Petrus
   selection has no case priority. Two simultaneously true guards are a genuine
   conflict, and the executed counterexample shows the *domain outcome* then
   depends on the Engine's selection policy — host configuration the authored
   flow never mentions (§7).

Baseline: Petrus `main` at `19e50e73`, the commit that landed v1; no
`src/petrus`, `spec`, or `tests` file was modified `[D]`.

## 2. Source experience

The whole difference from v1, in the authored flow
([guarded_scenario.py](guarded_scenario.py)):

```python
on(await_event("ci", CIObserved))
.branch(
    "route_ci",
    rungs=(
        rung("ignore",  when=not_actionable,   fold=absorb).drop(),
        rung("publish", when=first_clean,      fold=note_publication).emit(request_publication),
        rung("rerun",   when=fresh_failure,    fold=spend_rerun).emit(request_rerun),
        rung("repair",  when=repeated_failure, fold=spend_repair).emit(request_repair),
        rung("human",   when=ladder_exhausted, fold=exhaust).emit(surface_human_needed),
    ),
)
.route(
    {
        PublishRequested: low_level("publish_once", publication_gate, returns=PublishAcknowledged),
        RerunRequested: effect("rerun", rerun),
        RepairRequested: effect("repair", repair),
        HumanNeeded: terminal("human_needed"),
    }
),
```

Every other handler chain, every domain value, both simple Activities, the
publication gate, and all helper calculations are v1's, imported unchanged.

**Construct count, honestly counted: fourteen.** v1's thirteen (`machine`,
`lifecycle`, `on`, `await_event`, `project`, `decide`, `choose`, `effect`,
`terminal`, `drop`, `low_level`, `fold`, `.to`) minus `decide`/`choose`, plus
`branch`, `route`, `rung`, `.emit`, `.drop` — net **+1 construct**.

**Pure-function count: fourteen, up from one.** v1's ladder is one `route_ci`
(~60 lines). Here it is five predicates, five folds, four emissions, and one
shared `reading`/`normalized_ladder` classification. The rung table reads
better than `route_ci`'s nested `if` chain — each rung is one line naming its
condition, its state change, and its outcome — but the *rule* now lives in
fourteen small functions plus two shared helpers, and a reader must hold all five
predicates in mind at once to see that they partition the input space. v1's
reader did not have to.

## 3. Generated topology

**14 places, 13 transitions, 40 arcs, 5 guards**
([golden/readiness.net-v3.json](golden/readiness.net-v3.json), sha256
`fb936dd2…e789cc`). Places are unchanged from v1 — the rung split moves no
durable color.

| Transition | Durable meaning | Guard | Arcs |
| --- | --- | --- | --- |
| `ingress.head` | Accept one head observation and seed its generation state | — | 1 |
| `ingress.ci` | Accept one identified CI observation | — | 1 |
| `readiness.route_ci.ignore.fire` | Absorb an observation with no ladder answer | `not_actionable` | 3 |
| `readiness.route_ci.publish.fire` | Request the generation's first publication | `first_clean` | 4 |
| `readiness.route_ci.rerun.fire` | Spend the rerun rung | `fresh_failure` | 4 |
| `readiness.route_ci.repair.fire` | Spend the repair rung | `repeated_failure` | 4 |
| `readiness.route_ci.human.fire` | Surface the exhausted ladder | `ladder_exhausted` | 4 |
| `effects.rerun.fire` | Request/observe the fake rerun effect | — | 2 |
| `effects.repair.fire` | Request/observe the fake repair effect | — | 2 |
| `effects.publish.authorize` | Admit one publication while none is pending or done | — | 5 |
| `effects.publish.execute` | Request/observe the fake publication effect | — | 2 |
| `effects.publish.accept` | Accept the terminal, release pending, latch done | — | 4 |
| `readiness.accept_publish.fire` | Commit the acknowledged publication into state | — | 4 |

Arc order is a contract: the 40 arcs group contiguously per transition in the
order above, counts `1+1+3+4+4+4+4+2+2+5+2+4+4`
(`test_expected_topology_makes_every_ladder_rung_a_durable_transition` `[E]`).
The absorbing rung is the only one with no outcome arc — state in, event in,
state out — which is exactly what makes "nothing happened" a durable fact
rather than an absence.

The whole net round-trips strictly through `parse_net_definition` /
`compile_net_definition` / `project_net_definition` with the anonymous guards
projected canonically, and renders deterministically through `to_dot`
([artifacts/readiness.net.dot](artifacts/readiness.net.dot)): five separate
rung boxes, each badged `handler · guard`, each tooltip naming its rung path.
The ladder is in the picture. (Named limit: the DOT *label* is the path's leaf
segment, so every rung box reads "fire" until hovered — see §11.)

## 4. Acceptance matrix

All evidence `[E]` (executed) unless noted. `UV_FROZEN=1 uv run pytest -q
<this directory>` runs all **52** tests.

| # | Claim | Evidence | Result |
| --- | --- | --- | --- |
| 1 | Each rung lowers to its own guarded transition through the current `typed_guard`/`derive_typed_guard` path | `test_every_rung_carries_exactly_one_derived_typed_guard` (5 guard URIs; bound implementations evaluate the authored predicates) | pass |
| 2 | Typed guards need v1's `DomainConverter`; the DSL default cannot reconstruct nested `Evidence`/`Ladder` | `test_typed_guards_require_the_experiment_domain_converter` — refutation `[X]` of the default path | pass |
| 3 | Exact expected topology: 14/13/40, exact path set, per-transition arc counts, contiguous arc-order groups | `test_expected_topology_makes_every_ladder_rung_a_durable_transition` | pass |
| 4 | Repeated lowering is byte-stable and matches the retained Net v3 golden | `test_repeated_lowering_is_byte_stable_and_matches_net_v3_golden` | pass |
| 5 | Canonical Net v3 round-trips strictly with guards and renders via `to_dot` | `test_net_v3_round_trips_through_current_parser_and_compiler` | pass |
| 6 | Every place, transition, and handler has authored source ownership; each rung is owned by its own predicate | `test_every_place_transition_and_handler_has_source_ownership`, source-map golden | pass |
| 7 | Exactly one rung predicate holds over a systematic 576-point (state × event) grid | `test_exactly_one_rung_predicate_holds_over_a_systematic_grid` | pass |
| 8 | Each rung's fold + emission reproduces v1's `route_ci` state and outcome over that same grid | `test_each_rung_reproduces_v1_route_ci_state_and_outcome_over_the_grid` | pass |
| 9 | Overlapping guards are refused by nothing and produce two conflicting enabled candidates | `test_overlapping_rung_guards_are_refused_by_nothing_and_conflict_at_runtime` — refutation `[X]` | pass |
| 10 | An overlap's domain outcome is settled by the selection policy, not by the flow | `test_an_overlapping_conflict_is_settled_by_the_selection_policy_not_the_domain` — refutation `[X]` | pass |
| 11 | A non-exhaustive rung set silently strands the observation instead of failing | `test_a_non_exhaustive_rung_set_silently_strands_the_observation` — refutation `[X]` | pass |
| 12 | Fixture semantics preserved: `publish:h1:g1`, `rerun:L2:build`, `repair:L2:build`, `publish:h2r:g3`, same terminals, same scoped drop/quarantine | `guarded_run.run_fixture` + `test_guarded_scenario.py` (7 tests) | pass |
| 13 | One firing and one History row set per decision; History equals v1's record-for-record | `test_history_grain_equals_v1_record_for_record_over_the_same_trace` (147 = 147) | pass |
| 14 | The fired transition names the rung in canonical History, including `ignore` | `test_first_failure_reruns_once_and_the_absorbed_duplicate_names_its_rung`, `test_an_absorbed_observation_explains_why_nothing_happened` | pass |
| 15 | Uninterrupted and restarted runs are byte-identical (this experiment's own two runs) | `test_restarted_and_uninterrupted_runs_have_identical_canonical_history` (JSONL sha256 `d95e00aa…3e136f` both) | pass |
| 16 | `Engine.load` resumes an in-flight `ActivityRequested` as one logical operation and re-executes no rung function | `test_activity_requested_restart_redispatches_one_logical_operation`, `test_engine_load_rebuilds_marking_scope_and_ladder_without_reexecuting_rung_functions` | pass |
| 17 | Every observed record explains back to an authored source (0 unattributed of 147) | `test_every_observed_firing_explains_back_to_authored_source` | pass |
| 18 | Composition mistakes fail before any History file exists, naming block and location | `test_guarded_algebra.py` (10 tests: predicate return type, fold state type, event mismatch, unrouted outcome, unemitted route target, effect port mismatch, duplicate rung ids, id scoping, nominal collisions) | pass |
| 19 | Guard evaluation repeats per enabledness survey and never enters History | `test_guard_evaluation_repeats_per_enabledness_survey_and_never_enters_history` — a named cost, not a win | pass |
| 20 | The retained evidence bundle regenerates byte-identically | `test_retained_goldens_and_artifacts_match_regenerated_evidence` | pass |

Additional gates: `ruff check` and `ruff format --check` clean on all 12 files;
`ty check` clean on all six source modules; v1's 27 tests pass untouched; and
running the whole `experiments/` tree in one pytest invocation (117 tests, with
the sibling Option A slice present) shows no module-name collision `[E]`.

## 5. Restart route

Identical to v1's, re-executed over this topology: after the step-12 delivery
(`ci-20-2-g2`) the Engine advances only until `ActivityRequested` for
`effects.repair.fire` is durable, asserts no `ActivityCompleted` for that
occurrence, then closes. Reconstructed through public doors only: the source
value re-authored, `compile_guarded` re-run, a new `JsonlHistoryStore` over the
same path, a fresh `InlineDispatch`, and `Engine.load`.

Observed: two provider delivery attempts, one logical repair operation
(`repair:L2:build`), and canonical History bytes, records, marking, and active
scopes equal to the uninterrupted control run. The rung that fired before the
interruption is still the rung named after it — guards are re-derived from the
recompiled net, never replayed from History.

Claims deliberately **not** made: OS-process kill, power-loss durability,
remote Worker recovery, exactly-once effects, or byte equality with v1's
History (transition paths differ by design; byte equality is asserted between
this experiment's own two runs, and equality with v1 is asserted at the
record-type and domain-outcome level instead).

## 6. Attribution, rung-level

Each rung transition is owned by **its own predicate**, because "which rule
answered this observation" is the question the attribution has to answer. From
[golden/readiness.explained-history-v1.json](golden/readiness.explained-history-v1.json),
occurrence 13 — the duplicate CI observation at fixture step 11:

```text
occurrence 13
  transition: readiness.route_ci.ignore.fire
  role:       guarded ladder rung [ignore] — absorbing rung
  source:     guarded_scenario.py:120 not_actionable
  accepted:   ReadinessState(h2, L2, ladder=build/rerun_used, watermark=(20,1))
              CIObserved(h2, evidence=(20,1), failure, fingerprint=build)
  produced:   readiness.state   (state reproduced, no command token)
  ended:      FiringCompleted
```

This is the v1 limit closed. v1's report §11 recorded: *"An `Ignored` decision
is attributable in History only as a state-reproducing
`readiness.route_ci.fire` firing with no command token — its `reason` never
becomes a durable fact."* Here the canonical record names the rung, the sidecar
names the role, and the source map points at the exact predicate whose truth
caused the absorption. An operator asking "why did nothing happen for this CI
run?" gets `not_actionable` at `guarded_scenario.py:120` from durable data
alone.

Unattributed-record count: **0 of 147**. Scope records attribute to
`lifecycle("branch")`; `InstanceCreated` to the authored machine root; every
route firing to its rung's predicate.

## 7. The exclusivity and exhaustiveness obligation

This is the experiment's central finding.

### What was lost

v1's `route_ci` is exclusive and exhaustive **by construction**: one function,
one `return`, one tagged outcome, and `choose` checks the outcome union
exhaustively before lowering. Split into five independently guarded
transitions, neither property is expressible in the algebra and neither is
checkable by Petrus. `NetSpec.build()`, Net v3 validation, and the Engine all
accept an overlapping or incomplete rung set as a perfectly valid net.

### (a) Exclusivity by construction

The five predicates are written over one shared classification,
`reading(state, event)`, which derives freshness, cleanliness, the fingerprint,
whether a publication is pending, and the normalized ladder budget. Each
predicate then selects a disjoint region of that reading. This is discipline,
not proof.

### (b) The executable check

`test_exactly_one_rung_predicate_holds_over_a_systematic_grid` evaluates all
five predicates over a 576-point grid (12 states × 48 events, spanning ladder
fingerprints, spent and unspent rungs, watermarks, a lineage-mismatched ladder,
publication-pending states, foreign heads, and every conclusion/fingerprint
combination) and asserts **exactly one holds** at every point — and that every
rung is reached somewhere in the grid, so the check is not vacuous `[E]`.

`test_each_rung_reproduces_v1_route_ci_state_and_outcome_over_the_grid` then
asserts that the selected rung's fold and emission equal v1's `route_ci` state
and outcome at every one of those 576 points `[E]`. Semantics were preserved at
the decision level, not merely at the fixture level.

Both checks are *tests*, not properties of the source. Nothing prevents a sixth
rung, or an edited predicate, from breaking exclusivity in a region the grid
does not cover.

### (c) The counterexample, executed

[guarded_counterexample.py](guarded_counterexample.py) authors two deliberately
broken toy branches. Both compile through the algebra, lower through the same
compiler, and round-trip strictly through Net v3 — **nothing refuses them**
`[X]`.

**Overlap.** `any_failure` and `fingerprinted_failure` are both true for a
fingerprinted failure. On the same delivered observation,
`candidates(net, marking, guards)` returns **two** enabled bindings,
`overlap.route_ci.alpha.fire` and `overlap.route_ci.beta.fire` — a conflict in
the Petri sense. Then, with everything else identical:

| Selection policy | Rung that fired | Terminal reached |
| --- | --- | --- |
| `SelectionPipeline()` (the Engine default) | `alpha` | `terminal.alpha_seen` |
| `SelectionPipeline(strategy=Priority({beta: 1}))` | `beta` | `terminal.beta_seen` |

**The answer to "nondeterministic or merely policy-determined?" is: neither,
and the truth is worse than both.** It is not coin-flip nondeterminism — the
default `SelectionPipeline` proposes the first candidate in path-sorted
enumeration order, so an overlap is perfectly *reproducible*, which is exactly
why it is dangerous: a conflicting ladder passes every test, ships, and looks
like intended case priority (alphabetical-by-path priority, at that). And it is
not benignly policy-determined either, because the policy is Engine
composition — a host concern the authored flow never mentions, and one a
Navigator could change for unrelated scheduling reasons — so the *business
outcome* silently becomes a function of runtime configuration. Exactly one rung
fires either way, so the conflict is invisible in the grain: no duplicate
firing, no error, no warning, just the other rung's outcome.

**Gap.** `incomplete_flow` has one rung answering only failures. A clean
observation matches no rung: nothing fires, `candidates(...)` is empty, the CI
token sits admitted-but-unanswered at `events.ci`, and the Engine comes to rest
as if the work were done `[X]`. A missing case is a silent stall, not a
failure.

### What would close it

Nothing available today. A promoted design would need either (i) a compiler
that emits provably exclusive guards from an ordered case table — that is
Option A's shape, one transition; or (ii) an inhibitor/priority discipline
between rung transitions, which grows arcs quadratically and re-introduces
ordering into the topology; or (iii) a Petrus-level per-transition priority
recorded in canonical Net v3, which is a production change and outside this
experiment's boundary.

## 8. Grain assessment — the price

| | v1 | v2 | Δ |
| --- | --- | --- | --- |
| Places | 14 | 14 | 0 |
| Transitions | 9 | 13 | **+4 (+44%)** |
| Arcs | 28 | 40 | **+12 (+43%)** |
| Guards | 0 | 5 | +5 |
| History records, 24-step fixture | 147 | 147 | **0** |
| Firings per delivered CI observation | 1 | 1 | 0 |
| Guard evaluations, whole fixture | 0 | **50** | +50 |

The grain claim holds exactly:
`test_history_grain_equals_v1_record_for_record_over_the_same_trace` asserts
the same 147 records in the same order with the same record types and the same
ledger operations, and that every non-route firing is identical between the
experiments. Five transitions where v1 had one cost **zero** additional durable
rows. No bookkeeping firing was introduced; the exact-set topology test makes
one impossible to add silently.

The cost is not in History, it is in three other places:

- **Topology size.** +44% transitions and +43% arcs for one decision. A
  Hamsterdan V5-scale flow with nine such loops would pay that everywhere.
- **Guard evaluation.** Guards are evaluated per rung per enabledness survey
  while their arcs are satisfied, not once per decision: one decision
  evaluates **all five predicates exactly twice — ten evaluations per
  decision, a 10× amplification**, pinned exactly by
  `test_guard_evaluation_repeats_per_enabledness_survey_and_never_enters_history`
  `[E]`; over the fixture's five decisions that is ~50 evaluations by
  arithmetic, not separately measured. Each evaluation decodes both tokens through
  `DomainConverter` and re-derives the shared classification. None of it is
  recorded, so it is invisible in History and invisible in any report unless
  measured deliberately.
- **Re-derivation.** v1's `route_ci` computed the normalized ladder and the
  advanced watermark once, before choosing. Independent rungs cannot share that
  intermediate: **nine of the fourteen** pure rung functions call `reading` or
  `normalized_ladder`, and the classification is recomputed once per predicate
  evaluation and again in the fold of whichever rung wins — ten to eleven
  recomputations per decision in the fixture, against v1's one.

Ordinary helper calculations still create no nodes and no rows: operation-id
formatting, `evidence_key`/`is_newer`, `retry_key`, `reading`, and
`normalized_ladder` are all plain functions inside a single firing.

## 9. Comparison with v1

| Dimension | v1 (one transition) | v2 (one transition per rung) | Better |
| --- | --- | --- | --- |
| Constructs to learn | 13 | 14 | v1, marginally |
| Reading one rung | scan `route_ci`'s nested conditionals | one line: condition, fold, outcome | **v2** |
| Reading the whole rule | one function, top to bottom | five predicates that must be mentally intersected | **v1** |
| Exclusivity / exhaustiveness | guaranteed by the language | author's obligation, test-only | **v1, decisively** |
| Adding a rung | one branch + one `choose` case | one `rung(...)` + one `route` entry — **and re-proving exclusivity against every existing predicate** | v1 |
| Sequential state-dependence | computed once, shared | re-derived per predicate and per fold | **v1** |
| Ladder in canonical topology | invisible (one opaque transition) | five named transitions, in Net v3 and DOT | **v2** |
| "Why nothing happened" | not durable (v1 report §11) | durable, named, attributed to the predicate | **v2, decisively** |
| Attribution granularity | the whole decision | the exact rule that answered | **v2** |
| History grain | 1 firing/decision | 1 firing/decision | tie |
| Topology size | 9t / 28a | 13t / 40a | v1 |
| Runtime work per decision | 1 function call | 10 guard evaluations + 1 fold | v1 |
| Restart / replay behavior | identical | identical | tie |

**Is the price worth the visibility?** For this slice: not obviously. The
Ignored-invisibility fix is genuine and operationally valuable — it is the one
durable question v1 could not answer — but it is bought with a +44% topology, a
10× per-decision guard-evaluation amplification, duplicated classification, and an
unprovable exclusivity obligation whose failure mode is a silent wrong outcome.
A one-transition case table that *records the selected case* would plausibly
buy the same visibility at v1's price; that is precisely what Option A tests,
and this report deliberately makes no claim about it.

Supporting data `[E]` (line counts are supporting data only): the authored
delta over v1 is `guarded_scenario.py` at 281 lines (against v1's `scenario.py`
at 298, much of both being docstring and named simplifications); the disposable
compiler delta is `guarded_algebra.py` (294) plus `guarded_lowering.py` (239) —
v1's `_Lowering` supplied everything else by subclassing.

## 10. Reuse and isolation

**Imported read-only from v1** (never copied, never modified): `domain` (all
frozen values, `to_data`/`from_data`, `DomainConverter`); `algebra`
(`SourceRef`, `CompositionError`, `Machine`, `Handler` and its
`project`/`fold`/`to` chain, `lifecycle`, `await_event`, `effect`, `terminal`,
`drop`, `low_level`, `machine`, and the id/type/signature helpers); `lowering`
(`_Lowering` — subclassed — plus `CompiledFlow`, `IngressBinding`,
`FragmentContext`, `_command_base`); `source_map` (the whole sidecar);
`explain` (the whole projection); `harness` (`FakeProviderLedger`, `create`,
`load`, `drain`, `deliver_head`, `deliver_ci`, `value_at`, `values_at`);
`scenario` (`admit_head`, `accept_publish`, `publication_gate`, the three fake
Activities, every helper calculation, and `route_ci` used only as the
equivalence oracle); and `run_experiment` (v1's fixture, run side by side in
the grain test).

**Copied and adapted** (the only two): `guarded_run.py` adapts v1's
`run_experiment.py` — same 24-step trace and same expectations, plus the
per-rung grain assertions and this variant's bundle; and
`test_guarded_scenario.py` adapts v1's `test_scenario.py` assertions to the
rung transitions. Both are named here because a change to v1's fixture would
need mirroring.

**New** (nothing to copy from): `guarded_algebra.py`, `guarded_lowering.py`,
`guarded_scenario.py`'s predicates/folds/emissions, `guarded_harness.py`,
`guarded_counterexample.py`, and the exclusivity tests.

Everything lives in this one directory. Every module and test file carries a
`guarded_` prefix so both experiments share one `sys.path` without collision,
verified by running the whole `experiments/` tree in one pytest invocation
`[E]`.

## 11. Limits and surprises

- **Simulated vs Petrus-executed:** unchanged from v1. Rerun/repair/publish are
  fake typed Activities behind an in-memory ledger; only their
  request/acceptance boundaries are Petrus-executed evidence. Review, findings,
  approval, mergeability, mutation, and fault gates remain pre-satisfied
  fixture assumptions.
- **The DOT label is the path's leaf segment.** Every rung box renders as
  "fire"; the rung name is in the node's tooltip, its canonical path, its Net v3
  bytes, its source-map element, and every History record — but not in the
  rendered label. Naming the transitions `readiness.route_ci.<rung>` instead of
  `…<rung>.fire` would fix the picture at the cost of diverging from v1's
  `{machine}.{step}.fire` convention and blurring the like-for-like comparison.
  Kept `.fire`; the limit is named rather than optimized away.
- **Guards are not in History, by design.** A refused rung leaves no canonical
  trace at all. The visibility win is entirely about the rung that *did* fire;
  "these four rungs were evaluated and said no" is not durable, and cannot be
  made durable without a production change.
- **The exclusivity grid is a test, not a proof** (§7). Its 576 points cover the
  fixture's semantic space, not the type-theoretic input space.
- **The counterexample uses two selection policies, not a stress test.** It
  demonstrates that the outcome is policy-dependent; it does not enumerate every
  policy or claim anything about scheduler fairness.
- **`ingress.head` remains host-disciplined, not topology-guarded** — v1's
  limit, unchanged: a source transition cannot carry guards, so a second head in
  one generation would seed a second baton. Notably the rung split does *not*
  help here even though it is a guard-based design, because the restriction is
  on source transitions specifically.
- **The shared classification is a seam, not a guarantee.** `reading` keeps the
  five predicates consistent by convention. A future rung that read raw state
  instead would break exclusivity without touching any existing predicate — the
  grid test is the only thing that would catch it.
- **Surprise (good):** the rung split needed no production change whatsoever.
  `typed_guard` + `derive_typed_guard` bound five predicates to five transitions
  on the first green run; anonymous guards project canonically and round-trip
  byte-stably; and v1's `_Lowering` extended by subclassing with one new method
  (`guarded_transition`) and one new chain case.
- **Surprise (friction):** the DSL's default `DataclassPayloadConverter`
  silently produces a `CIObserved` whose `evidence` is a `dict`, so a guard
  fails at *evaluation* time inside enabledness rather than at derivation time.
  Pinned as `test_typed_guards_require_the_experiment_domain_converter`. A
  promoted authoring layer must not let a converter be forgotten.
- **`ty` needs `--extra-search-path` twice** because this experiment imports
  across sibling directories; `pytest` gets the same from `conftest.py`. The
  exact command is in [README.md](README.md).
- **Source-map goldens embed `guarded_scenario.py` line numbers**, so they are
  sensitive to edits in that file; they were regenerated after the final
  `ruff format` pass, and the bundle-freshness test fails loud on a stale
  golden or artifact.
- The repository's `testpaths = ["tests"]` excludes this directory: its 52 tests
  run only when invoked explicitly, so a future `src/petrus` change can break
  this experiment silently. Expected for disposable Exploration evidence, and
  worth knowing before citing this report.
- No adversarial review round was run against this variant (v1 had two). The §7
  conclusions rest on executed counterexamples; the §9 judgment calls do not.

### Adversarial review round

An independent gpt-5.6-terra review attacked this experiment after
completion; the one confirmed finding, fixed before this report's final
state `[E]`: the guard-evaluation amplification figure was stated as a
fixture-wide "50 evaluations" while the cited test asserted only a weak
lower bound. The test now pins the exact deterministic per-decision counts
(five predicates x two evaluations), and the report states the fixture-wide
figure as arithmetic extrapolation rather than measurement.

## 12. Driver recommendation and next route

Classify **mixed** and attach to ES-059 beside v1's report.

The durable finding worth carrying forward regardless of which authoring shape
wins: **"why nothing happened" deserves a durable spelling.** v1 named it as a
limit; this experiment shows it is closable, and that closing it by splitting
the transition is expensive. The cheap version of the same win — a
one-transition decision that records the *selected case* as a durable fact — is
the shape a promotion decision should evaluate next, and it is what Option A is
testing independently.

The finding that should block Option B from promotion as authored: a decision
spread across guarded transitions makes exclusivity and exhaustiveness
unprovable authoring obligations whose failure mode is a silent, reproducible,
policy-determined wrong outcome. No promoted authoring surface should ship that
without either compiler-emitted exclusive guards or a canonical priority
mechanism — and both are production decisions outside this experiment's
boundary.

No code moves out of Exploration and no roadmap, decision, or Delivery change
follows from this result without Navigator direction.
