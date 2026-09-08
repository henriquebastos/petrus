# Inscription net (v4) — Experience Report

The fourth spelling of ES-059's readiness slice. Read
[v1's report](../typed-flow-vertical-slice/report.md) first for the shared
semantics; [A](../algebraic-decision-table/report.md) and
[B](../guarded-decision-net/report.md) are the two decision-structure spellings
this one answers. Byte parity with v1 was explicitly **not** a goal here:
topology, paths, state representation, and History bytes all differ by design.
Behaviour parity is the claim, and it is executed.

Baseline: Petrus `main` at `08779c7`. Nothing under `src/petrus`, `spec/`,
`tests/`, or the three sibling experiment directories was modified; `git status`
shows only this new directory `[E]`.

## 1. Verdict

**Promising, with one refutation and one deliberate scope cut.**

The thesis — *impure = transition, pure = inscription* — held further than
expected. The authored flow ([inet_scenario.py](inet_scenario.py)) names no
place, transition, arc, guard, token, binding, marking, or handler URI. The
compiler derived ten transitions, fifty arcs, and **eight guards** from a
combinator expression plus eleven pure token methods lifted as inscriptions
(two further methods stay ordinary helpers and create no node). Against v1 over
the same fixture:

| | v1 | A | B | **v4 (this)** |
| --- | --- | --- | --- | --- |
| History records, fixture | 147 | 147 | 147 | **108** |
| Firings, fixture | 24 | 24 | 24 | **14** |
| Scheduler-selected firings | 15 | 15 | 15 | **5** |
| Firings per delivered CI observation | 2–4 | 2–4 | 2–4 | **1** |
| Places / transitions / arcs | 14/9/28 | 14/9/28 | 14/13/40 | **10/10/50** |

Three results carry:

1. **Exclusivity and exhaustiveness are compiler properties.** Deliberately
   overlapping authored predicates still lower to at most one enabled candidate
   (section 6), and an incomplete *structural* cover is refused before lowering
   with the exact unanswered latch state. B's decisive counterexample cannot be
   authored here.
2. **Fusing the effect into the decision collapses the grain to one firing per
   observation** — and the semantic price is real, named, and executed: the
   folded state is in flight while the Activity runs, so no other observation
   can be decided until it completes (section 4).
3. **Refutation `[X]`: state-as-marking does not compose with a generated
   exclusive guard chain unless the compiler owns the structural dimension too.**
   A guard cannot test absence, so branches separated by a latch cannot negate
   each other's predicate; the fix (structural exclusivity plus a completeness
   proof over latch patterns) is the most interesting thing this experiment
   built, and it is what makes claim 1 true (sections 5 and 6).

The scope cut: v1's `(lineage, fingerprint)` ladder-budget re-arming is **not
modelled**. A latch is a black token whose whole content is its location, so it
cannot be keyed by data. That is the sharpest point where data refused to become
structure, and it is recorded rather than contorted (section 5).

## 2. The kernel

Seven combinators. Ports are not one of them: **a port is a type**, and the
compiler allocates exactly one place per token color. That is the Open Petri
Nets gluing idea spelled the cheapest way available — two nodes connect when
they agree on a type — and it removed a whole primitive.

| Combinator | Lowering | Why it earned its place |
| --- | --- | --- |
| `await_(id, T, seeds=...)` | one source transition; with `seeds`, that transition also runs the fused fork | Scoped external ingress is irreducible. `seeds` exists because a current-Petrus source transition takes no guard and no input arc, so opening a generation's structure atomically with the fact that justifies it has no other spelling. |
| `fork(id, fns..., fills=...)` | one firing, several typed outputs | The head ingress produces four values at once (head identity, sentinel watermark, two rungs). Without `fork` that is four transitions or a tuple type nobody wants. |
| `join(event, reads=..., folds=...)` | the input arc shape shared by every branch of one choice | Distinguishes the three arc modes semantically: the event is *consumed*, `reads` are read arcs (present, visible to guards, untouched), `folds` are consumed and reproduced. `reads` vs `folds` is what decides whether a value serializes decisions (section 4). |
| `choice(id, branches..., otherwise(...))` | N+1 transitions, N+1 generated guards, plus the structural cover proof | The research object. Ordered first-match-wins, and every safety property is derived here. |
| `effect(id, activity, request=fn)` | fused into the branch's own transition | The only *authored* transition kind. Everything else the compiler generates. |
| `latch(path, ThinToken)` | a place plus `takes` (consume), `without` (inhibit), `fills` (produce) | Absence. A guard sees only the binding's selected tokens and an inhibit arc contributes no selection, so absence is expressible **only** structurally. Also carries the fold-free half of the state. |
| `>>` | glues a producer's output ports into a consumer node | Sequence. Used twice, with two lowerings (`await_ >> choice` keeps two transitions; `await_(seeds=fork(...))` fuses one). Honest smell, named in section 11. |

Scaffolding that is not a combinator and is counted separately: `flow`,
`lifecycle`, `ports` (the place naming table), `branch`, `otherwise`.

**What was cut.** A `state` combinator (subsumed by `join(folds=...)`); a
`terminal` combinator (a port with no consumer needs no construct); a `drop`
combinator (a branch with no emission *is* the drop); a `map`/`project`
combinator (folds and emissions are just pure functions on a branch); an
explicit `port` constructor (one color, one place). Everything B and A needed
for `rung`/`case`/`.emit`/`.drop`/`normalize`/`otherwise`-as-sentinel collapsed
into `branch(...)` keywords.

## 3. The authored source

The complete flow, from [inet_scenario.py](inet_scenario.py):

```python
def readiness_flow() -> Flow:
    head = await_("head", HeadObserved,
                  seeds=fork("open_generation", HeadObserved.as_head_fact,
                             HeadObserved.unseen_watermark, fills=(RERUN, REPAIR)))
    ci = await_("ci", CIObserved)
    observation = join(ci, reads=(HeadFact,), folds=(EvidenceWatermark,))

    return flow("readiness", lifecycle=lifecycle("branch"), ports=PORTS,
        latches=(RERUN, REPAIR, PUBLICATION), joins=(observation,),
        nodes=(head, ci >> choice("decide",
            branch("foreign",     when=CIObserved.is_for_another_head),
            branch("stale",       when=CIObserved.is_not_newer_than),
            branch("publish",     when=CIObserved.is_clean, without=(PUBLICATION,),
                   fills=(PUBLICATION,), folds=(CIObserved.watermark,),
                   effect=effect("publish", publish, request=CIObserved.publish_request)),
            branch("republished", when=CIObserved.is_clean, takes=(PUBLICATION,),
                   fills=(PUBLICATION,), folds=(CIObserved.watermark,)),
            branch("rerun",       when=CIObserved.is_classified_failure, takes=(RERUN,),
                   folds=(CIObserved.watermark,),
                   effect=effect("rerun", rerun, request=CIObserved.rerun_request)),
            branch("repair",      when=CIObserved.is_classified_failure, takes=(REPAIR,),
                   without=(RERUN,), folds=(CIObserved.watermark,),
                   effect=effect("repair", repair, request=CIObserved.repair_request)),
            branch("human",       when=CIObserved.is_classified_failure,
                   without=(RERUN, REPAIR), folds=(CIObserved.watermark,),
                   emits=(CIObserved.human_needed,)),
            otherwise("unclassified", folds=(CIObserved.watermark,)),
        )),
    )
```

Plus three latch declarations, a seven-entry `ports` table, and three
`@activity` declarations.

**Construct count, honestly.** Twelve named constructs a reader meets in the
flow value — `flow`, `lifecycle`, `ports`, `latch`, `await_`, `fork`, `join`,
`>>`, `choice`, `branch`, `otherwise`, `effect` — plus nine keyword modifiers
(`seeds`, `reads`, `folds`, `when`, `takes`, `without`, `fills`, `emits`,
`request`): **21 on A's counting rule**, against v1's 13, A's 19, and B's 14.
This is the most vocabulary of the four spellings. What it buys is that the
vocabulary is *the whole specification*: there is no `route_ci`, no
`refresh_ladder`, no `reading` helper, and no proof obligation left over.

**Line accounting** `[E]`: the authored surface is
[inet_scenario.py](inet_scenario.py) at 184 lines (most of it the named
simplifications) plus [inet_tokens.py](inet_tokens.py) at 307, against v1's 298
plus 209. The disposable compiler is [inet_kernel.py](inet_kernel.py) 651 plus
[inet_lowering.py](inet_lowering.py) 540, against v1's ~1,500 for algebra,
lowering, source map, and explain (this experiment reuses v1's source-map and
explain modules unchanged).

## 4. Where every piece of v1's `route_ci` logic ended up

v1's whole ladder was one 60-line function. This is where each of its decisions
now lives — the one-table summary:

| v1 `route_ci` logic | Where it lives now | Kind |
| --- | --- | --- |
| `event.head != state.head` -> Ignored | `CIObserved.is_for_another_head(head: HeadFact)` | **guard (token method)**, branch `foreign` |
| `not is_newer(evidence, watermark)` -> Ignored | `CIObserved.is_not_newer_than(watermark: EvidenceWatermark)` | **guard (token method)**, branch `stale` |
| `conclusion == "success"` | `CIObserved.is_clean()` | **guard (token method)**, and the one **Cel arc filter** in the canonical bytes |
| `state.publication_operation is not None` -> Ignored | presence of a token at `publication.admitted` | **structure (marking)**, branch `republished` takes it |
| first clean -> PublishRequested | branch `publish`, `without=(PUBLICATION,)` | **structure (inhibitor)** plus fused effect |
| `event.fingerprint is None` -> Ignored | negation of every earlier predicate | **generated exclusive guard chain**, branch `unclassified` |
| `ladder.rerun_used` boolean | emptiness of `ladder.rerun` | **structure (marking)** |
| `ladder.repair_used` boolean | emptiness of `ladder.repair` | **structure (marking)** |
| `if not rerun_used` -> RerunRequested | branch `rerun`, `takes=(RERUN,)` | **structure (consume)** plus fused effect |
| `elif not repair_used` -> RepairRequested | branch `repair`, `takes=(REPAIR,) without=(RERUN,)` | **structure (consume + inhibitor)** plus fused effect |
| `else` -> HumanNeeded | branch `human`, `without=(RERUN, REPAIR)` | **structure (two inhibitors)** plus emission |
| watermark advance | `CIObserved.watermark()` as a branch `fold` | **fused fold** inside the deciding firing |
| `publish/rerun/repair_operation(...)` strings | `CIObserved.*_request(head: HeadFact)` | **inscription (token method)**, no node |
| `(lineage, fingerprint)` budget re-arm | **nothing** | **cut** — see section 5 |
| `Ignored(reason=...)` colour | four separately named absorbing transitions | **generated transition**, durable |

Nine of the fifteen rows became either structure or a generated guard; none of
them is a hand-written `if`.

**Residual non-effect transitions, with the forcing reason for each.** Effects
are supposed to be the only authored transitions; seven generated ones survive:

| Transition | Why semantics force it |
| --- | --- |
| `ingress.ci` | An external fact must enter through a source transition. Irreducible. |
| `ingress.head` | Same, and it additionally carries the fused fork (which is *not* a separate transition — that is the point of `seeds`). |
| `decide.foreign`, `decide.stale`, `decide.republished`, `decide.unclassified` | **The absorption problem.** An observation deserving no effect still needs a consumer. B proved a net without one silently strands the token; A proved a decision that merely drops it cannot say *which* rule absorbed it. Four named transitions is the price of a durable "why nothing happened". |
| `decide.human` | A terminal fact with no effect. Arguably this should be an effect (in V5 it files an issue); in this fixture it is an emission, so the compiler must generate the transition that emits it. |

No connector, dispatcher, formatter, or bookkeeping transition exists. The
exact-set topology test makes one impossible to add silently.

### The fold problem, decided

Guards cannot transform data, so the state update had to go somewhere. **Option
(a): fused into the effect transition.** The guard decides, the Activity fires,
and the projection writes the folded watermark, the filled latches, *and* the
result fact together. `ActivityRequested` is durable before dispatch, so the
decision commitment is durable at request time.

The semantic difference from v1, named and executed
(`test_fusing_the_fold_into_the_effect_serializes_decisions_while_it_is_in_flight`)
`[E]`: between `ActivityRequested` and `ActivityCompleted` the folded
`readiness.watermark` token is **consumed and not yet reproduced**, so
`candidates(...)` is empty and a second admitted observation cannot be decided
at all. v1 returned the state baton immediately and could decide the next
observation while the effect ran.

**Is that acceptable?** For this slice, yes, and arguably better: the readiness
ladder is a strictly sequential budget, and deciding observation *n+1* against a
watermark that observation *n* is about to advance is precisely the race v1
avoided only because the fixture drains between deliveries. The general answer
is *it depends on the port*: `reads` ports (here `readiness.head`) stay
available during an in-flight effect, `folds` ports do not. That distinction is
authored, one keyword apart, and visible — which is the honest version of this
trade-off rather than a hidden one.

**Cost, named:** `DerivedActivityHandler` cannot be reused for a fused branch.
It raises when any input arc's colour matches no Activity parameter *and* when
any output arc's colour is not the Activity result — a fused branch violates
both. The compiler owns a small prepare/project bridge through the public
`ActivityHandler` protocol instead
(`test_effect_branches_bind_a_compiler_owned_activity_bridge` `[E]`). A promoted
authoring layer would want a public "derive typed arguments from arcs" seam;
today that logic is private to `petrus.impetus.binding`.

## 5. State-as-marking: what became structure, what refused

**Became structure** (three latch places, zero booleans):

- the rerun rung and the repair rung — "spent" is an empty place;
- the rung *ordering* — repair is reachable only once `ladder.rerun` is empty,
  which is an inhibitor arc, not a predicate. v1 spelled this as `elif`;
- "the ladder is exhausted" — two inhibitors, no state field;
- "a publication was already admitted this generation" — one inhibitor plus one
  consuming branch;
- **the whole per-generation budget reset** — scope reset discards the
  generation's tokens and the successor head's fused fork re-arms both rungs.
  v1 needed a fresh `Ladder` value in `admit_head`; here it is free and verified
  (`test_scope_reset_discards_the_whole_generation_including_its_structural_state`) `[E]`.

**Refused to become structure** — the data/structure boundary, exhaustively:

| Fact | Why structure cannot hold it |
| --- | --- |
| Head identity (`h1`/`h2r`), generation, lineage | Values that must be *read* and compared, and that appear in operation ids. Not a location. |
| Evidence watermark ordering `(run_id, attempt)` | Strict ordering is a comparison of two token values. No marking, read arc, or inhibitor expresses "strictly greater than". This is the clearest single refusal. |
| Operation ids | Derived strings. Kept as token methods; they create no node. |
| **The `(lineage, fingerprint)` budget key** | **The sharpest refusal, and a scope cut.** v1 re-armed both rungs when a failure's fingerprint changed. A thin token carries nothing, so a latch cannot be keyed by data; re-arming would need a compiler-generated refill transition guarded on a token comparison, and "fill only if absent" is itself unstructurable without a combinatorial explosion of `without=` patterns. The fixture and V5's scope-reset discipline never change the fingerprint inside one generation, so the fixture is unaffected — but v4 is **not** behaviour-equivalent to v1 outside the fixture on this one point, and that is stated here rather than buried. |

**Against ES-059's Hamsterdan warning.** ES-059 warned that hand-writing this
shape is where V5's cost lives. This experiment *is* the hand-written V5
spelling — the marking-heavy one — and the honest answer is: **combinators plus
rich tokens made it cheap to write and expensive to compile.** The authored
delta for the whole ladder is five `branch(...)` lines carrying nine keywords;
nobody wrote an inhibitor. The compiler paid: 50 arcs against v1's 28 (+79%),
and the structural-cover proof is ~30 lines that did not need to exist in any
other spelling. That is the right side of the trade for an authoring layer, and
the wrong side for anyone hand-writing the net — which is exactly what ES-059
predicted, now with numbers.

## 6. Exclusivity by construction

### The generated forms

Branch *i*'s guard is one synthesized `typed_guard` over the whole binding:

```text
guard_i  =  pred_i  AND  NOT pred_j  for every earlier j
            minus every j that is *structurally* exclusive of i
            minus duplicate predicates
```

Structural exclusivity is decidable: branch *i* is structurally exclusive of *j*
when one `takes` a latch the other is `without`. Where an inhibitor already
separates two branches, negating the earlier predicate is unnecessary — and
often impossible, because the three ladder rungs share **one** predicate
(`is_classified_failure`) and are separated by latches alone. The generated
chains, pinned by test `[E]`:

| Branch | Own predicate | Negated |
| --- | --- | --- |
| `foreign` | `is_for_another_head` | — |
| `stale` | `is_not_newer_than` | `is_for_another_head` |
| `publish` | `is_clean` | `is_for_another_head`, `is_not_newer_than` |
| `republished` | `is_clean` | same two (`publish` excluded structurally) |
| `rerun` | `is_classified_failure` | the three above (deduped) |
| `repair` | `is_classified_failure` | same (`rerun` excluded structurally) |
| `human` | `is_classified_failure` | same (both rungs excluded structurally) |
| `unclassified` | — (otherwise) | all four distinct predicates |

### The refutation that forced this design `[X]`

A guard sees only the binding's selected tokens, and an inhibit arc contributes
no selection. Therefore **a NOT term cannot mention absence**, and two branches
distinguished only by structure cannot negate each other. A naive
"pred_i AND NOT pred_1..i-1" chain over a marking-state design is *unsound*: the
winning branch can be structurally disabled while every later branch has already
negated its predicate, and nothing fires — B's silent-stall failure mode
re-entering through the structural door. The two-dimensional rule above plus the
cover check is the repair.

### The cover check

For each group of branches sharing one predicate, expand each branch's
`(takes, without)` pattern over the group's latch set and demand an exact
partition of the 2^k assignments. For the ladder group over
{`ladder.repair`, `ladder.rerun`}: `rerun` claims (any, present), `repair`
claims (present, absent), `human` claims (absent, absent) — four of four, no
overlap. An incomplete cover is refused before lowering, naming the unanswered
latch state (`test_an_incomplete_structural_cover_is_refused_before_lowering`)
`[E]`:

```text
choice [decide] branch group [is_classified_failure] leaves ladder.rerun=absent
unanswered; a true predicate would strand its observation
```

An overlapping cover is refused naming both branches and both source locations.

### The overlap test — contrast with B

`test_overlapping_predicates_still_lower_to_exclusive_generated_guards` `[E]`
authors B's exact counterexample: `any_failure` and `fingerprinted_failure`,
both true for a fingerprinted failure. B got **two** enabled candidates and an
outcome that flipped with the Engine's selection policy. Here `candidates(...)`
returns **one** — `decide.alpha` — the observation is answered rather than
stranded, and the later branch is simply *dead*, which is the documented
semantics of an ordered choice.

### The grid

`test_exactly_one_branch_is_enabled_over_the_whole_state_grid` evaluates the
compiled net over **384 points** — 8 latch markings x 2 watermarks x 24
observations — and asserts exactly one enabled candidate at every point, with
every branch reached somewhere (not vacuous). A companion test asserts no point
strands an observation. B's grid could only cover predicates; this one covers
the marking's **Boolean latch occupancy**, which is where B's failure mode
actually lived `[E]`. The model is occupancy, not multiplicity: duplicated
tokens (two same-generation head deliveries) sit outside it, offer eight
bindings for one observation, and corrupt the structural budget — pinned by
`test_token_multiplicity_is_outside_the_cover_proofs_model` and named in §11.

### Measured guard evaluation

Guards are evaluated per enabledness survey and never recorded, so the only
honest number is a deliberately counted one. For one clean decision (two
surveys) `[E]`:

| Predicate | Evaluations |
| --- | --- |
| `is_for_another_head` | 6 |
| `is_not_newer_than` | 6 |
| `is_clean` | 4 |
| `is_classified_failure` | 2 |
| **total** | **18** |

Against B's 10 per decision and v1's single `route_ci` call. It is lower than
the chain lengths suggest because both the conjunction and the NOT chain
short-circuit, and because the Cel arc filter stops a non-matching observation
from assembling a binding for the publish branches at all. Eighteen pure
predicate calls per decision is the real, unrecorded cost of exclusivity by
construction.

## 7. Behavioural acceptance matrix

All `[E]`. 65 tests; `UV_FROZEN=1 uv run pytest -q <this directory>`.

| # | Claim | Evidence | Result |
| --- | --- | --- | --- |
| 1 | `publish:h1:g1` executes once on clean CI; a `Published` terminal fact for head h1 generation 1 | `test_clean_ci_publishes_once_and_reaches_a_terminal_published_fact` | pass |
| 2 | First exact-head failure spends one rerun (`rerun:L2:build` once) | `test_first_exact_head_failure_spends_the_rerun_rung_once` | pass |
| 3 | Identity redelivery answers `PriorAcknowledgement` and appends nothing | `test_identity_redelivery_answers_prior_acknowledgement_and_appends_nothing` | pass |
| 4 | Same evidence, new identity -> absorbed, no budget spent, branch named | `test_same_evidence_under_a_new_identity_is_absorbed_and_names_its_branch` | pass |
| 5 | Strictly newer matching failure spends repair, not a second rerun | `test_a_strictly_newer_failure_spends_repair_not_a_second_rerun` | pass |
| 6 | A further matching failure after repair -> durable `HumanNeeded`, no new operation | `test_a_further_matching_failure_after_repair_surfaces_human_needed_and_no_new_operation` | pass |
| 7 | Restart at the durable `ActivityRequested` boundary: 2 delivery attempts, 1 logical repair, 1 completion record | `test_activity_requested_restart_redispatches_one_logical_operation` | pass |
| 8 | Confirmed repair head keeps lineage L2 and publishes; unrelated head starts a fresh lineage and a fresh budget | `test_a_confirmed_repair_head_keeps_its_lineage_and_an_unrelated_head_starts_a_fresh_one`, `inet_run.run_fixture` (`publish:h2r:g3`) | pass |
| 9 | Closed-generation delivery dropped, unproven-future quarantined, both idempotent | `test_closed_generation_drops_and_unproven_future_quarantines_idempotently` | pass |
| 10 | Uninterrupted and restarted runs produce byte-identical canonical History (self-parity) | `test_restarted_and_uninterrupted_runs_have_identical_canonical_history`; both sha256 `ee48f97e...16876c` | pass |
| 11 | `Engine.load` resumes without executing any pure inscription | `test_engine_load_rebuilds_marking_and_structure_without_executing_any_pure_inscription` (instrumented: 0 calls) | pass |
| 12 | Grain: exactly one firing per delivered CI observation | `test_the_grain_is_exactly_one_firing_per_delivered_observation` (six observations, six decision firings, effects on the same occurrences) | pass |
| 13 | One publication admitted per generation | `test_one_publication_is_admitted_per_generation_by_the_inhibitor_latch`, `test_two_clean_observations_at_once_still_admit_only_one_publication` | pass |
| 14 | Repeated lowering is byte-stable and matches the retained Net v3 golden | `test_repeated_lowering_is_byte_stable_and_matches_the_net_v3_golden`, sha256 `cc602704...f80f8d` | pass |
| 15 | Net v3 parses, compiles, validates, renders | `test_net_v3_round_trips_through_the_current_parser_and_compiler` | pass |
| 16 | Every place, transition, and record attributes to an authored construct | `test_every_place_transition_and_handler_has_authored_source_ownership`, `test_every_observed_record_explains_back_to_an_authored_construct` (0 unattributed of 108) | pass |
| 17 | The retained evidence bundle regenerates byte-identically | `test_the_retained_evidence_bundle_regenerates_byte_identically` (6 files) | pass |

**Restart route.** Exact interruption point: after the fixture's step-12
delivery (`ci-20-2-g2`), advanced only until `ActivityRequested` for
`decide.repair` was durable, asserting no `ActivityCompleted` for that
occurrence, then `Engine.close()`. Reconstructed through public doors only: the
source value re-authored, `compile_flow` re-run, a new `JsonlHistoryStore` over
the same path, a fresh `InlineDispatch`, `Engine.load`. The first `advance()`
redispatched with correlation and idempotency `repair:L2:build`; the ledger
counted two delivery attempts and one logical operation; History bytes, marking,
scopes, and branch sequence equal the uninterrupted control run.

Claims deliberately **not** made: OS-process kill, power-loss durability, remote
Worker recovery, exactly-once effects. This is in-process object reconstruction
over a real durable JSONL store; the fake ledger simulates a provider's
idempotency boundary and proves nothing about real providers.

**Attribution.** Every record explains to an authored construct, and because
each branch *is* a transition, "which rule answered this observation" is in
canonical History with no projection needed. From
[golden/inscription.explained-history-v1.json](golden/inscription.explained-history-v1.json):

```text
occurrence 8  decide.stale
  role:   guarded branch [stale] — durable absorption
  source: inet_scenario.py:143 stale
```

That is v1's named `Ignored`-invisibility limit closed, and A's
"absorbing rung not identifiable in History" limit closed, at **lower** grain
than either.

## 8. Grain assessment

| | v1 | B | v4 | Delta vs v1 |
| --- | --- | --- | --- | --- |
| History records (fixture) | 147 | 147 | **108** | **-39 (-27%)** |
| `FiringBegun`/`FiringCompleted` | 24 each | 24 each | **14 each** | -10 |
| `CandidateSelected` | 15 | 15 | **5** | -10 |
| `TokensConsumed` | 24 | 24 | **12** | -12 |
| `TokensProduced` | 34 | 34 | **32** | -2 |
| `TokensRead` | 0 | 0 | **5** | +5 |
| `ActivityRequested`/`Completed` | 4 each | 4 each | 4 each | 0 |
| Firings per delivered CI observation | 2 (rerun/repair) to 4 (publish) | 2-4 | **1** | **-1 to -3** |

The publication path is where the collapse happens: v1 needed
`route_ci.fire -> authorize -> execute -> accept -> accept_publish.fire` (five
firings); v4 needs `decide.publish` (one). The 5 `TokensRead` rows are the
`readiness.head` read arcs — a record type the other three spellings never
produced, and cheaper than the consume/produce pair they replace.

**Is the extra cost paying for durable branch visibility?** There is no extra
cost in History; the cost is elsewhere and it is real:

- **Arcs: 50 vs 28 (+79%).** State-as-marking buys its structure in arcs. A
  V5-scale flow with nine loops would pay that everywhere.
- **Guard evaluations: 18 per decision vs v1's one function call.** Unrecorded
  and therefore invisible unless measured.
- **Compiler complexity:** the structural-cover proof and the two-dimensional
  chain rule are ~80 lines that no other spelling needed.

So: durable branch visibility came free in grain (it is a consequence of one
transition per branch, which was already needed), and the ladder's *structure*
cost 22 arcs and 17 extra predicate evaluations per decision. Given that B paid
+12 arcs and +10 evaluations for visibility alone and still shipped an
unprovable obligation, this is the better trade.

## 9. CEL probe

**Partial success, with a precise limit.**

**What worked** `[E]`: `CIObserved.is_clean` is registered with a `Cel`
spelling, and the compiler emits it as an arc **filter** on the `events.ci`
consume arc of both `is_clean` branches. It lands in canonical Net v3 as

```json
{"source": "events.ci", "target": "decide.publish", "mode": "consume",
 "color": "CIObserved", "filter": {"kind": "cel", "expression": "conclusion == \"success\""}}
```

and executes through the Engine — `Instance` compiles inline `Cel` filters at
construction, and the whole fixture runs with them active. Every Python-bound
guard, by contrast, projects as `{"kind": "anonymous", "uri": ...}`: the
filter's *meaning* survives into the interchange bytes, the guards' does not
(`test_one_method_derived_predicate_reaches_canonical_net_v3_as_a_cel_arc_filter`).

**What is missing, exactly** `[X]`: a Cel **guard** cannot address any place of
this net. `compile_guard` binds each consume/read input place by its **full
dotted path as a bare identifier**, and CEL parses `events.ci` as member access
on an identifier `events` — which is then rejected as out of scope:

```text
CEL guard 'events.ci[0].data.conclusion == "success"' on transition decide.publish
references name(s) outside its consume/read input places
['events.ci', 'readiness.head', 'readiness.watermark']: ['events']
```

Pinned by `test_a_cel_guard_cannot_reach_any_place_of_this_net` `[E]`. So the
CEL guard tier is reachable only by nets whose every input place has a
single-segment path — which no scoped Petrus net has. This is adjacent to the
carried debt *cel-data-exposure-has-no-unified-design*, and worth naming
separately: it is not a vocabulary gap (the watermark comparison
`a.run_id > b.run_id || (a.run_id == b.run_id && a.attempt > b.attempt)` is
perfectly expressible in CEL) but an **addressing** gap.

Not attempted, deliberately: automatic Python-to-CEL translation. The one Cel
spelling is hand-written and registered against the method; that is a probe of
the *carrying* mechanism, not of a compiler.

## 10. Comparison

| Dimension | v1 (one decide fn) | A (case table) | B (guarded rungs) | **v4 (inscription net)** |
| --- | --- | --- | --- | --- |
| Concepts | 13 constructs; the ladder is ordinary Python | 19 constructs; the ladder is a value | 14 constructs; the ladder is five rungs | **21**; the ladder is dataflow plus structure |
| Whole-rule readability | one function top to bottom | a 14-line ordered table | five predicates that must be mentally intersected | an 8-line branch table where each line names its predicate, its capability, and its effect |
| Reading one rung | scan nested `if`s | one line | one line | one line, and the *capability it spends* is on that line |
| Change locality: add a rung | edit `route_ci` plus a `choose` case | one `case(...)` plus maybe a `choose` entry | one `rung(...)` plus a `route` entry **plus re-prove exclusivity** | one `branch(...)` plus one `latch(...)`; the cover check re-proves exclusivity for you |
| Exclusivity | by construction (one `return`) | by construction (ordered, benign overlap) | **author's obligation, test-only** | **by construction, over predicates *and* marking** |
| Exhaustiveness | untyped, unchecked | `otherwise` sentinel, static | **author's obligation; a gap is a silent stall** | **compiler-proved, including the structural dimension** |
| Attribution of absorption | not durable | rung named in source map, **not** in History | durable, named, per predicate | **durable, named, per branch**, at one firing per observation |
| Topology | 14p/9t/28a | 14p/9t/28a | 14p/13t/40a | **10p/10t/50a** |
| History grain | 147 records, 24 firings | 147 / 24 | 147 / 24 | **108 records, 14 firings** |
| Guard evaluations per decision | 0 | 0 | 10 | 18 |
| Meaning in canonical bytes | none (anonymous) | none | none | **one Cel arc filter** |
| Effect boundary | separate transition; state returns immediately | same | same | **fused**; state is in flight during the effect |

## 11. Limits and surprises

- **Simulated vs Petrus-executed:** unchanged from v1. Rerun/repair/publish are
  fake typed Activities behind an in-memory ledger; review, findings, approval,
  mergeability, mutation, and fault gates remain pre-satisfied fixture
  assumptions. Every claim about firing, guards, replay, resume, scope
  disposition, and History is Petrus-executed `[E]`.
- **The `(lineage, fingerprint)` budget key is cut** (section 5). v4 is not
  behaviour-equivalent to v1 outside the fixture on that one point.
- **`>>` has two lowerings.** `await_ >> choice` keeps two transitions;
  `await_(seeds=fork(...))` fuses one. A promoted design should either unify
  them or make the fusion explicit at the call site.
- **`reads` vs `folds` is a load-bearing keyword** most authors will get wrong
  once. It decides whether an in-flight effect blocks the next decision
  (section 4). A promoted design should probably make the blocking behaviour the
  thing you name, not the arc mode.
- **The DOT label improved by accident.** B's rung boxes all rendered as "fire"
  because the label is the path's leaf segment. Here the leaf segment *is* the
  branch id, so the picture reads `foreign / stale / publish / republished /
  rerun / repair / human / unclassified`. Naming transitions
  `{choice}.{branch}` rather than `{choice}.{branch}.fire` is a free win.
- **Surprise (good):** no production change was needed anywhere. Synthesizing a
  guard function with an explicit `__signature__` and real type objects in
  `__annotations__` binds through `typed_guard`/`derive_typed_guard` on the
  first try; thin field-free dataclasses work as arc colours; `Cel` arc filters
  round-trip byte-stably.
- **Surprise (friction):** `DerivedActivityHandler` refuses a fused branch for
  two independent reasons (section 4). The refusal is correct for its contract;
  it just means the fused shape needs a compiler-owned bridge.
- **Surprise (friction):** the naive NOT chain over a marking-state design is
  unsound (section 6). The bug would have been a silent stall in production,
  found only because the grid test covers the marking.
- **The cover check is a proof, the grid is a test.** The cover check proves
  structural completeness per predicate group at compile time. It does *not*
  prove that the predicates themselves are meaningful — a predicate that is
  always false makes its branch dead, which the kernel does not refuse (A's
  unreachability limit, unchanged).
- **`ty` needs `--extra-search-path` twice** because this experiment imports
  across sibling directories; `pytest` gets the same from `conftest.py`. The
  exact command is in [README.md](README.md).
- **Source-map goldens embed `inet_scenario.py` and `inet_tokens.py` line
  numbers**, so they are sensitive to edits in either; they were regenerated
  after the final `ruff format` pass and the bundle-freshness test fails loud on
  a stale golden.
- **Reuse, stated:** [source_map.py](../typed-flow-vertical-slice/source_map.py),
  [explain.py](../typed-flow-vertical-slice/explain.py),
  `algebra.SourceRef`/`CompositionError`, and `harness.FakeProviderLedger` are
  imported from v1 read-only and unmodified. `inet_harness.py` and `inet_run.py`
  are copy-adapted from v1's `harness.py`/`run_experiment.py` because the domain
  types differ; a change to v1's fixture would need mirroring. Everything else
  is new.
- **No adversarial review round was run** against this variant (v1 had two, A
  and B had one each). The section 6 conclusions rest on executed
  counterexamples and the 384-point grid; the section 8 and 10 judgement calls
  do not.
- The repository's `testpaths = ["tests"]` excludes this directory: its 65 tests
  run only when invoked explicitly, so a future `src/petrus` change can break
  this experiment silently. Expected for disposable Exploration evidence, and
  worth knowing before citing this report.

### Adversarial review round

An independent gpt-5.6-terra review attacked this experiment after
completion; confirmed findings, pinned and documented before this report's
final state `[E]`:

1. **The fusion's failure blast radius.** No failure projection exists, so a
   terminal Activity failure on a fused branch consumes the CI event, the
   folded watermark, and the spent rung latch with no recovery path — and
   because every decision branch folds the watermark, the whole decision
   group wedges: every subsequent observation strands. Pinned by
   `test_a_failed_fused_effect_destroys_the_folded_state_and_wedges_the_decision_group`.
   v1 did not have this failure mode (its decision fired before the effect,
   so a failed effect consumed only its command token). This is the fusion's
   real price beyond in-flight serialization; Petrus's existing
   `FailureProjectingActivityHandler` seam is where a promoted design must
   project failure-survivable state, and the fixture's no-failure Activities
   kept it out of the acceptance matrix — the claim set is correspondingly
   narrower than v1's.
2. **Token multiplicity is outside the cover proof's model.** The 384-point
   grid models Boolean latch occupancy; duplicate same-generation head
   deliveries (a host-discipline violation v1 also documents) create
   duplicated watermark/latch tokens, eight enabled bindings for one
   observation, and — after the single firing — a surviving rerun latch that
   could spend the rung twice. Pinned by
   `test_token_multiplicity_is_outside_the_cover_proofs_model`; the grid
   claim in §7 is now scoped to occupancy explicitly.
3. A worklog wording issue outside this directory (the integration commit
   also touches ES-059's index, which the orchestrator owns) was corrected at
   the integration level; this experiment's own boundary held.

## 12. Driver recommendation and next route

Classify **promising** and attach beside v1, A, and B. The four reports should
be read as one comparison; this one is not a replacement for any of them.

The specific learning to carry forward:

1. **Exclusivity and exhaustiveness belong to the compiler, and the structural
   dimension is not optional.** B's obligation is closable, but only by a
   compiler that reasons about `takes`/`without` patterns as well as predicates.
   Any promoted authoring surface that mixes guards with marking-state must do
   both or it will ship silent stalls.
2. **Fusing the effect into the decision is the single biggest grain win
   available** (-27% records, one firing per observation) and its price is one
   clearly-named serialization property. That trade deserves a Navigator
   decision, not a default.
3. **State-as-marking is cheap to author and expensive to compile.** +79% arcs
   for the whole ladder. Worth it above an authoring layer; not worth it by
   hand — which is ES-059's Hamsterdan warning, now measured.
4. **A latch cannot be keyed by data.** Any budget whose key is data needs
   either a compiler-generated refill transition or a data token beside the
   latch. Worth deciding before this shape goes near V5's nine loops.
5. **The CEL guard tier is unreachable from any scoped net.** Place paths are
   bound as bare CEL identifiers, so a dotted path cannot be addressed at all.
   That is a small, concrete Petrus question, independent of everything else in
   this experiment.

No code moves out of Exploration. No ES-056 promotion, roadmap change, or
Delivery follows from this result without Navigator direction.
