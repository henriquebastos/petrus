# Algebraic decision table — Experience Report

## 1. Verdict

**Promising, with one named cost.**

The readiness decision was re-authored as an ordered, first-match-wins table of
eight `case(...)` constructs and lowered to **exactly one transition**. The
canonical Net v3 bytes are **byte-identical** to the v1 slice's retained
golden (sha256 `f5e4a91f…537a19`), and the canonical History JSONL for v1's
exact 24-step fixture is **byte-identical** to v1's retained artifact (sha256
`a75880c0…d3e22d`) `[E]`. The same runtime IR, the same 147 durable records,
the same grain — under a source in which the decision's structure is a value
the compiler, the source map, and the explained History can all read.

What the table won: six new pre-lowering refusals with source locations, one
source-map entry per rung, per-firing rung attribution in the explained
History for every emitting decision, statically guaranteed totality, and
change locality for adding a rung that touches one line of the table.

What it cost: the authoring vocabulary grew from thirteen constructs to
nineteen, and one genuinely sequential piece of the ladder — the
`(lineage, fingerprint)` rung reset — did **not** become a case. It moved into
a `normalize` pre-step, which is `route_ci` in miniature (§10.5, honestly).

Baseline: Petrus `main` at `19e50e7`, the commit that landed v1. Nothing under
`src/`, `spec/`, `tests/`, or `../typed-flow-vertical-slice/` was modified;
`git status` shows only this new directory `[E]`.

## 2. Source experience

The complete authored flow ([table_scenario.py](table_scenario.py)) is:

```python
def readiness_flow() -> Machine[ReadinessState]:
    return machine(
        "readiness",
        lifecycle=lifecycle("branch"),
        handlers=(
            on(await_event("head", HeadObserved)).project("admit_head", admit_head),
            on(await_event("ci", CIObserved))
            .match(
                "route_ci",
                normalize=refresh_ladder,
                cases=(
                    case("foreign",      when=other_head,           fold=keep).drop(),
                    case("stale",        when=not_newer,            fold=keep).drop(),
                    case("publish",      when=first_clean,          fold=note_publication).emit(request_publication),
                    case("published",    when=already_published,    fold=advance).drop(),
                    case("unclassified", when=unclassified_failure, fold=advance).drop(),
                    case("rerun",        when=rerun_available,      fold=spend_rerun).emit(request_rerun),
                    case("repair",       when=repair_available,     fold=spend_repair).emit(request_repair),
                    case("human",        when=otherwise,            fold=advance).emit(surface_human_needed),
                ),
            )
            .choose(
                {
                    PublishRequested: low_level("publish_once", publication_gate, returns=PublishAcknowledged),
                    RerunRequested: effect("rerun", rerun),
                    RepairRequested: effect("repair", repair),
                    HumanNeeded: terminal("human_needed"),
                }
            ),
            on(PublishAcknowledged).fold("accept_publish", accept_publish).to(terminal("published")),
        ),
    )
```

**Construct count, honestly.** v1 needed thirteen: `machine`, `lifecycle`,
`on`, `await_event`, `project`, `decide`, `choose`, `effect`, `terminal`,
`drop`, `low_level`, `fold`, `.to`. v2 needs **nineteen**: the same list minus
`decide` and minus `drop`-as-a-choose-target, plus `match`, its `normalize=`
keyword, `case`, its `when=` and `fold=` keywords, `.drop()`, `.emit()`, and
`otherwise`. That is **+6 constructs** — the honest price of making the
decision's structure part of the algebra rather than part of one function
body. Counting only the constructs a reader meets *in the flow value above*,
it is fifteen vs thirteen; the `when=`/`fold=` keywords and `normalize=` are
learned once.

**Line accounting** `[E]`. Both spellings contain **exactly 57 lines of
executable code** for the CI decision (docstrings, comments, and blank lines
excluded, measured by AST). v1 concentrates them in one 62-line `route_ci`
plus a 15-line `.decide(...).choose(...)` chain. v2 spreads them across
seventeen named single-purpose functions (one `normalize`, seven classifiers,
five commits, four emissions) plus a 14-line table and an 8-line `choose`.
Raw line counts roughly double (121 vs 62) because every rung's helper carries
its own docstring. **The logic did not grow; it got names and addresses.**

The `.drop()` spelling replaced v1's `Ignored` domain color entirely: v1 had to
invent a durable-looking type (`Ignored(reason=...)`) whose only purpose was to
give `choose` something to route to `drop()`. In v2 absorption is a property of
the rung, so `Ignored` is not referenced at all and the routed union shrank
from five colors to four — with no change to the generated net, because
`Ignored` never had a place.

## 3. Generated topology

Exactly **14 places, 9 transitions, 28 arcs** — the same paths, the same
colors, the same handler kinds, and the same arc positions as v1. The
per-transition arc counts `1+1+7+2+2+5+2+4+4` are asserted in that order
(`test_expected_topology_has_only_durable_transitions` `[E]`). Every
transition's durable meaning is v1's, unchanged; only
`readiness.route_ci.fire`'s *source* is different:

| Transition | Durable meaning | v1 source | v2 source |
| --- | --- | --- | --- |
| `readiness.route_ci.fire` | Accept current CI evidence and commit one ladder decision | one `decide` | one `match` of eight `case`s |

The stretch goal held: `first.definition_bytes == v1/golden/readiness.net-v3.json`
`[E]` (`test_repeated_lowering_is_byte_stable_and_matches_the_v1_net_v3_golden`).
Net v3 deliberately excludes source and bindings, so a richer authoring layer
is invisible to it — which is exactly the thesis this experiment set out to
test, now as an executed byte comparison rather than an argument.

## 4. Acceptance matrix

All evidence `[E]` (executed) unless noted. 38 tests;
`UV_FROZEN=1 uv run pytest -q <this directory>` runs them all in ~0.5 s.

| # | Claim | Expected | Observed | Result | Evidence |
| --- | --- | --- | --- | --- | --- |
| A1 | Eight rungs lower to v1's canonical topology | 14/9/28, same paths, same arc order | identical | pass | `test_expected_topology_has_only_durable_transitions` |
| A2 | Canonical Net v3 bytes equal v1's golden | byte-identical | byte-identical, sha256 `f5e4a91f…537a19` | pass | `test_repeated_lowering_is_byte_stable_and_matches_the_v1_net_v3_golden` |
| A3 | Repeated lowering is byte-stable (net + sidecar) | equal bytes twice | equal | pass | same test, `test_source_map_is_stable_hash_bound_and_matches_golden` |
| A4 | Net v3 parses, compiles, validates, renders | round-trip + deterministic DOT | round-trips; two independent lowerings render equal | pass | `test_net_v3_round_trips_through_current_parser_and_compiler` |
| A5 | The table decides exactly what `route_ci` decided | 0 mismatches, every rung reachable | 10,368 (state, event) pairs, 0 mismatches, all 8 rungs fired | pass | `test_the_case_table_decides_exactly_what_the_v1_decide_function_decided` |
| A6 | Canonical History for v1's fixture equals v1's artifact | byte-identical | byte-identical, sha256 `a75880c0…d3e22d` | pass | `test_canonical_history_is_byte_identical_to_the_v1_decide_function_slice` |
| A7 | Grain: one decision, one firing, v1's row set | 147 records, 5 decision firings | 147 records, 5 firings, identical bytes ⇒ identical rows | pass | A6 + `artifacts/experiment-report.json` |
| A8 | Interrupted and uninterrupted runs agree | equal History/marking/scopes | equal; 2 delivery attempts, 1 logical repair | pass | `test_restarted_…`, `test_activity_requested_restart_redispatches_one_logical_operation` |
| A9 | `Engine.load` resumes without re-running the table | marking/scope/state rebuilt, no new provider attempt | rebuilt; attempts unchanged | pass | `test_engine_load_rebuilds_marking_scope_and_ladder_without_reexecuting_the_table` |
| A10 | Every node and record still attributes | 0 unattributed of 147 | 0 | pass | `test_every_place_transition_and_handler_has_source_ownership`, `unattributed_records()` |
| A11 | Every `case` and `normalize` gets its own source entry | 8 + 1 entries, 8 distinct lines | 8 + 1, 8 distinct lines in `table_scenario.py` | pass | `test_every_authored_case_and_the_normalize_step_has_its_own_source_map_entry` |
| A12 | Explained History names the fired rung when the color identifies it | 4 of 5 named, 1 absorption reported as a candidate set | exactly that | pass (limit named) | `test_every_decision_firing_names_its_case_or_reports_the_absorbing_candidates` |
| A13 | Six new refusals fail before lowering, with source locations | all six localized | all six | pass | six tests in `test_table_algebra.py` |
| A14 | Adding a rung is a source-only change | net bytes unchanged | 9 rungs → identical 14/9/28 and identical bytes | pass | `test_one_decision_lowers_to_one_transition_regardless_of_rung_count` |
| A15 | v1's descent seam still validates under the new chain | inhibitors present, whole net round-trips | yes; fragment imported unmodified from `scenario.py` | pass | `test_low_level_publication_gate_uses_an_inhibitor_and_canonical_validation` |
| A16 | v1's own suite is untouched | 27 pass | 27 pass | pass | `pytest -q ../typed-flow-vertical-slice` |

Additional gates: `ruff check` and `ruff format --check` clean, `ty check`
clean on all seven non-test modules (with `--extra-search-path` for the v1
slice) `[E]`.

## 5. Semantic preservation

Two independent levels, both executed:

1. **Pure, near-exhaustive.** The authored table was evaluated against v1's
   `route_ci` over the cross product of 144 states (2 heads/generations/lineages
   × 3 fingerprints × 4 rung-budget combinations × 3 watermarks × 2 publication
   states) and 72 CI observations (3 heads × 4 evidence identities × 2
   conclusions × 3 fingerprints) — **10,368 pairs, 0 mismatches** in both the
   committed state and the emitted outcome, and every one of the eight rungs
   fired at least once `[E]`. The one deliberate representational difference:
   v1's `Ignored` outcome corresponds to v2 emitting nothing.
2. **Runtime, byte-level.** v1's exact fixture trace over the compiled table
   flow appends canonical History whose bytes equal v1's retained
   `artifacts/readiness.history.jsonl` `[E]`. That covers watermark advance,
   duplicate absorption, the `(lineage, fingerprint)` rung budget,
   fingerprint-change reset, `publication_operation` dedup, and
   failure-without-fingerprint absorption, plus the restart at the durable
   `ActivityRequested` boundary.

Byte equality was achievable because nothing observable changed: the same
transition produced the same token colors and the same JSON payloads in the
same order, at the same integer instants. No honest reason to fall back to
record-level equivalence arose.

## 6. Attribution

**Source map.** Each rung registers its own source id at its `case(...)` call
site, and `normalize` registers `refresh_ladder`'s definition site:

```json
{ "id": "readiness.route_ci.rerun",     "file": "table_scenario.py", "line": 217, "symbol": "rerun" }
{ "id": "readiness.route_ci.normalize", "file": "table_scenario.py", "line": 80,  "symbol": "refresh_ladder" }
```

These are `sources` entries with no `elements` row, which the v1 sidecar
format already permits (v1 used the same shape for its single
`route_ci.ignored.drop`). **No change to `SourceMapV1` was needed** to carry
eight-rung attribution — a useful negative result for a future public
source-map design: sub-node authored structure fits in the existing `sources`
array.

**Explained History.** [table_explain.py](table_explain.py) joins the case
index to v1's explained projection. For the fixture's five decision firings:

| Occurrence | Produced color | Named rung | Source |
| --- | --- | --- | --- |
| 3 | `PublishRequested` | `publish` | `table_scenario.py` `first_clean` → `note_publication` → `request_publication` |
| 10 | `RerunRequested` | `rerun` | `rerun_available` → `spend_rerun` → `request_rerun` |
| 13 | *(state only)* | **not identified** | one of `foreign`, `stale`, `published`, `unclassified` |
| 15 | `RepairRequested` | `repair` | `repair_available` → `spend_repair` → `request_repair` |
| 19 | `PublishRequested` | `publish` | as above |

**The limit, named honestly.** A `.drop()` rung produces only the state token,
so canonical History carries nothing that separates the four absorbing rungs
from one another. Occurrence 13 is the `stale` rung (the duplicate-evidence
echo), but History alone cannot say so; the projection reports
`"case": null` with the full candidate set rather than guessing `[E]`. This is
*better* than v1, where absorption was indistinguishable **and** the reason
string was invented per branch and then thrown away — but it is not resolved.
Two ways out, both out of scope here: give each absorbing rung a distinct
durable fact (one extra place per rung, which breaks the grain invariant), or
let a firing record carry a compiler-supplied label (a Petrus change, which
the plan's stop conditions forbid).

Unattributed records: **0 of 147** `[E]`, unchanged from v1.

## 7. Error locality

Six deliberate mistakes, all refused before lowering and before any History
file exists, each naming the authored construct and its source location. The
messages below are verbatim from a probe script (`errs.py` there stands in for
`table_scenario.py`) `[E]`:

```text
match [route_ci] declares duplicate case id [dup]: first at errs.py:20 and again at errs.py:21

errs.py:25 [route_ci.dead] is unreachable: errs.py:24 [route_ci.rest] already matches every observation

errs.py:27 [route_ci.rerun] emits RerunRequested, but the choose at errs.py:28 routes no target for it

errs.py:30 [route_ci.rerun] emits RerunRequested, but errs.py:31 [repair] accepts RepairRequested

errs.py:34 routes HumanNeeded to errs.py:35 [human_needed], but no case in [route_ci] emits it

errs.py:36 [route_ci] is not total: the last case must be case(..., when=otherwise, ...) so every observation reaches exactly one rung
```

Plus type-shape refusals a table makes checkable per rung: `when` and `fold`
disagreeing on `(state, event)`, `when` not returning `bool`, `fold` not
returning the state type, `emit` not returning a concrete class, and a table
whose event type does not match its trigger.

**Unreachability, precisely.** Predicates are ordinary Python; nothing can
prove statically that `rerun_available` and `repair_available` are disjoint, or
that a rung is dead because an earlier predicate subsumes it. What *is*
provable is the one case that matters in practice: `otherwise` is a sentinel,
not a function, so "a case after the total case" and "two total cases" are both
static refusals. Everything else is deliberately **not** an obligation:
ordered first-match-wins makes predicate overlap *benign* — a later rung simply
never sees an observation an earlier one claimed. The authored flow relies on
this heavily and correctly: `rerun_available` does not re-check "is this a
classified failure?", because the four rungs above it already absorbed
everything that is not one. An unordered/guarded formulation (experiment B's
shape) would have to discharge that as a proof obligation; this one gets it for
free, at the price of the reading discipline described in §10.5.

## 8. Descent

Unchanged from v1 and re-validated here. `publication_gate` is **imported
read-only** from `../typed-flow-vertical-slice/scenario.py`, passed to the same
`low_level(...)` construct, lowered by the inherited `_lower_fragment`, and
post-build-verified by the inherited `_verify_fragments`. Its two inhibitor
arcs are present at the same canonical positions (14, 15) and the whole net
still round-trips strict Net v3 `[E]`. The source map records its owner as
`file: "scenario.py"` — honest cross-experiment provenance, and a small
demonstration that the descent seam is reusable across authoring surfaces
without re-authoring.

The concurrency counterfactual (a fragment minus its inhibit arcs) is not
repeated here; it is v1's evidence and nothing in this experiment touches it.

## 9. Grain assessment

**No extra firings.** The fixture appends 147 canonical records, byte-identical
to v1's, so the History row count per decision is identical *by construction of
the comparison* — not merely equal in aggregate `[E]`. Five decision
occurrences, one per delivered CI observation that reached the transition,
exactly as in v1.

Ordinary calculations that never became nodes: the seven classifiers, the five
commits, the four emissions, `refresh_ladder`, `classified`, and v1's
`publish/rerun/repair_operation`, `evidence_key`, `is_newer`, `retry_key`
(`test_helper_calculations_and_predicates_create_no_nodes` and the exact-set
topology assertion `[E]`). **Eighteen new authored functions produced zero new
nodes.** The strongest form of this evidence is A14: adding a ninth rung to
the table leaves the Net v3 bytes unchanged.

## 10. Comparison: v1 `decide` function vs A case table

| Dimension | v1 — one `decide` function | A — ordered case table |
| --- | --- | --- |
| **Concepts** | 13 constructs; the ladder is "ordinary Python" | 19 constructs (+`match`, `normalize=`, `case`, `when=`, `fold=`, `.drop()`, `.emit()`, −`decide`, −`drop`); the ladder is a value |
| **Executable lines (decision)** | 57 | 57 (redistributed over 18 functions + a 14-line table) |
| **Explanation steps** | read one 62-line function top to bottom; the branch/outcome pairing is implicit in `return Decision(...)` calls | read the 14-line table to see *what the rungs are and in what order*; open a named function only for the rung in question |
| **Change locality: add a rung** | edit `route_ci` (insert a branch in the right place), add a `choose` entry, and — if it is a new absorption — invent another `Ignored` reason string | add one `case(...)` line in the right position and (only for a new emitted color) one `choose` entry; a forgotten route is refused by name and location |
| **Attribution of absorption (`Ignored`)** | one color, four reasons, none durable; the source map has a single `route_ci.ignored.drop` entry | four separately named, separately located rungs in the source map; still **indistinguishable in History** (§6) — better addresses, same runtime blindness |
| **Attribution of an emitting decision** | transition + produced color; the branch that ran is not identified | the fired rung is named, with its `when`/`fold`/`emit` symbols and source line, for 4 of 5 firings |
| **Static guarantees** | `choose` exhaustiveness over a declared union; totality of the function is untyped and unchecked | the same exhaustiveness, now *derived from the rungs*; plus totality, unreachable-after-`otherwise`, duplicate rung ids, and per-rung type agreement |
| **Where it fights sequential logic** | nowhere: sequential state-dependent logic is what a function is for | the `(lineage, fingerprint)` rung reset had to leave the table (§10.5) |
| **Topology visibility** | canonical net, DOT, Net v3 bytes | identical — byte-for-byte |

### 10.5 The `normalize` step: win, or `route_ci` sneaking back?

**Both, and the split is precise.**

`route_ci` mixes three things: (a) classification, (b) a *shared* state update
that several branches perform identically, and (c) per-branch commits and
outcomes. The table absorbs (a) and (c) cleanly. It cannot absorb (b): "when
the `(lineage, fingerprint)` key changes, give this observation a fresh rung
budget" is not a rung — it is a precondition several rungs share, and it must
run *before* `rerun_available` and `repair_available` can be one-liners.

So `refresh_ladder` is a 10-line pure function containing four sequential
conditionals. That is unambiguously `route_ci`-shaped code, and it is the
honest cost of this design. Three things keep it from being a rescue hatch:

1. **It is bounded by signature.** `normalize` is `(state, event) -> state`. It
   cannot emit, cannot route, cannot decide. Every routing decision is still a
   rung. The construct that could hide the whole ladder does not exist.
2. **It is one place, not eight.** The alternative — no `normalize`, each rung's
   `when` re-deriving the effective ladder — would duplicate the key-change test
   across `rerun_available` and `repair_available` and make both predicates
   longer than the function they replaced. Measured against that alternative,
   `normalize` is a win.
3. **Its boundary was forced by a real constraint, not taste.** An earlier
   design had `normalize` also advance the evidence watermark — the update
   *five* of the eight rungs share. That is impossible: `not_newer` must compare
   the arriving evidence against the watermark it is about to replace, so a
   normalize that advances the watermark makes staleness undecidable
   downstream. Keeping one uniform state through the table (normalize → `when`
   → `fold`) therefore required pushing the watermark advance back into the five
   `fold`s, where it appears as a call to one shared `advance(state, event)`
   helper.

That last point is the sharpest finding of the experiment: **a case table
splits a decision at the classify/commit seam, and any shared update that a
classifier must observe in its pre-update form cannot be hoisted.** v1's single
function had no such seam and no such constraint. The table's uniform
`normalize → when → fold` contract is worth the constraint — a two-state
contract ("`when` sees the arrived state, `fold` sees the normalized state")
was the other option and would have been much harder to explain — but it is a
real limitation on where shared logic can live.

One smaller symptom of the same seam: `publish_operation(state.head,
state.generation)` is now computed twice per publication — once in
`note_publication` (to latch it into state) and once in `request_publication`
(to put it in the outcome). v1 computed it once and used it in both. Both are
pure and deterministic so the values agree, but "compute once, use in state and
outcome" is no longer expressible.

## 11. Limits and surprises

- **Surprise (good):** byte-identical Net v3 on the *first* green lowering, with
  no tuning of arc order. The routed-color order falls out of first-appearance
  in the case table, which happened to match v1's declared union order. A
  different rung order would reorder the decision's output arcs and change the
  bytes — the byte identity is evidence about *this* pair of sources, not a
  theorem about all case tables.
- **Surprise (good):** implementation was mostly *subtraction*.
  `_TableLowering` subclasses v1's `_Lowering` and overrides one method plus
  adds one; `table_lowering.py` is 199 lines against v1's 587. The v1 lowering
  turned out to factor cleanly at exactly the seam this experiment needed.
- **Surprise (friction):** `otherwise` had to be a *sentinel object* rather than
  a predicate function, because a generic always-true predicate cannot carry
  the concrete `(state, event)` annotations `case()` requires. The sentinel is
  what makes the two static unreachability refusals possible, so the friction
  paid for itself — but a promoted design should decide whether that asymmetry
  (every `when` is a function except one) is acceptable.
- **Ordered tables need reading discipline.** `rerun_available` is correct only
  in position 6. Read out of order, four of the seven classifiers look wrong. A
  promoted design should consider whether rung documentation (or a rendered
  table in the source map) is part of the deliverable.
- **The type checker does not know the order.** `classified(event)` exists
  purely to narrow `str | None` → `str` for rungs that only run after the
  `unclassified` rung absorbed the `None` case. Its raise is unreachable
  through the authored table. Ordered first-match-wins buys runtime economy
  that the type system cannot see.
- **Cross-experiment provenance.** Reusing v1's `publication_gate`,
  `admit_head`, `accept_publish`, and Activities means this slice's source map
  and explained History legitimately reference `scenario.py` as well as
  `table_scenario.py`, and an edit to v1's `scenario.py` line numbers would
  invalidate this slice's source-map golden. v1 is committed and frozen, so
  that is acceptable here; it is worth knowing before citing the golden.
- **Simulated vs Petrus-executed:** unchanged from v1. Rerun/repair/publish are
  fake typed Activities behind an in-memory idempotency ledger; the review,
  findings, approval, mergeability, mutation, and fault gates remain
  pre-satisfied fixture assumptions. Every claim about firing, replay, resume,
  scope disposition, and History is Petrus-executed `[E]`.
- **Not retained, deliberately:** the Net v3 JSON, the History JSONL, and the
  DOT rendering are byte-identical to v1's retained files, so this directory
  asserts against v1's copies and records the hashes in
  [artifacts/experiment-report.json](artifacts/experiment-report.json) rather
  than duplicating evidence.
- **`ty` needs `--extra-search-path`.** Importing the v1 modules from a sibling
  directory is not something ty resolves from the checked file's own directory.
  Recorded in the README's command block.
- **`testpaths = ["tests"]`** still excludes this directory: these 38 tests run
  only when invoked explicitly, so a future `src/petrus` change can break them
  silently. Expected for disposable Exploration evidence.
- **Comparison limit:** this report compares two authoring surfaces over the
  same slice, which is stronger than v1's qualitative comparison against
  hand-authored `NetSpec` — but the "easier to explain" judgment in §10 is
  still a reading judgment, not a measured one. No user study, no second
  maintainer. The mechanical claims (A1–A16) do not establish it.

### Adversarial review round

An independent gpt-5.6-terra review attacked this experiment after
completion; confirmed findings, fixed before this report's final state
`[E]`:

1. `evaluate_match` accepted any truthy predicate answer although only the
   `-> bool` annotation was checked at construction — a classifier drifting
   to a category string would silently select its rung. The value is now
   enforced strictly at evaluation and pinned by
   `test_a_truthy_non_bool_predicate_answer_is_refused_at_evaluation`.
2. This report's authored-function count said seventeen while enumerating
   eighteen; corrected.

## 12. Driver recommendation and next route

Classify **promising**. The specific learning to carry forward:

1. **Decision structure can be algebraic at zero runtime cost.** Byte-identical
   Net v3 and byte-identical History under a source that exposes eight rungs is
   the strongest available evidence that Petrus's canonical layer is the right
   place to stop, and that authoring richness is free above it.
2. **The existing sidecar shape already carries sub-node structure.** A future
   public source-map decision does not need a new element kind for authored
   constructs that own no node.
3. **History cannot name an absorbing rung.** If absorption reasons matter
   operationally — and in Hamsterdan's readiness loops they plausibly do — that
   is a Petrus-level question (a labelled firing record) rather than an
   authoring-layer one. Worth a separate bounded inquiry before any promotion.
4. **`normalize` is the seam to watch.** Any promoted case-table construct
   should keep it signature-bounded to `(state, event) -> state`. The moment it
   can emit or route, the table becomes decoration.
5. **Compare against experiment B before choosing.** This experiment's central
   property — ordered first-match-wins makes predicate overlap benign — is
   exactly what a guarded/unordered formulation must pay for in proof
   obligations. The two results should be read together.

No code moves out of Exploration. No ES-056 promotion, roadmap change, or
Delivery follows from this result without Navigator direction.
