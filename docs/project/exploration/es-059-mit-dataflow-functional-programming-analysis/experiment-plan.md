# Typed functional flow vertical-slice experiment plan

## Purpose

This is the durable clean-session restart surface for ES-059's executable
experiment. It should let a future Driver implement, run, explain, and close
the experiment without reconstructing the originating conversation.

Read the [source-grounded exploration](index.md) first. It explains the MIT
dataflow lineage, why instruction-grain dataflow lost, why Petrus is a
different bet, and why a typed functional authoring layer is the bounded next
question. This document does not reopen that research. It specifies the
safe-to-learn intervention that tests its recommendation.

This remains **Exploration Documentation and an experiment**, not a public API
plan, runtime change, Hamsterdan migration, or accepted roadmap story. The
prototype, tests, generated evidence, and report all live under ES-059. A
successful result can thicken [ES-056](../es-056-progressive-disclosure-developer-experience/index.md)
and inform its AX28/AX29 evidence gates; promotion remains a Navigator
decision.

## Experiment question

Can one Hamsterdan-shaped durable workflow be authored as a small typed,
functional value and lowered deterministically into the **current** canonical
Petrus Net v3 while preserving:

- every durable decision, wait, effect request, effect acceptance, and
  generation boundary;
- normal `Engine` execution, append-only History, replay, and resume;
- byte-stable canonical topology;
- source-to-generated-node and source-to-History attribution;
- errors localized to the authored composition before motion;
- coarse transition grain; and
- deliberate descent to one low-level Petri fragment without a second
  execution model?

The experiment distinguishes two explanations of Hamsterdan's developer
friction:

1. **The canonical Petri model is wrong for the product.** Even coarse durable
   behavior remains distorted, unexplainable, or operationally expensive after
   compositional lowering.
2. **The current authoring surface is too low-level.** A typed compositional
   source substantially improves locality while canonical Net and History
   remain useful runtime truth.

It must be possible for the evidence to support either result.

## Smallest useful completion condition

The experiment is complete only when one command executes the exact fixture
below and writes an evidence bundle, and focused tests establish all of these
claims:

1. compiling the same source value twice produces byte-identical canonical Net
   v3 and source-map sidecar bytes;
2. the canonical Net parses, compiles, validates, and renders through current
   Petrus APIs;
3. clean CI publishes exactly once;
4. the first exact-head failure requests one rerun and a duplicate observation
   spends nothing;
5. a strictly newer matching failure requests repair, not another rerun;
6. confirmed repair movement preserves retry lineage while advancing the
   lifecycle generation;
7. unrelated branch movement advances the lifecycle generation and starts a
   fresh retry lineage;
8. a delivery to a closed generation is durably dropped and a delivery to an
   unproven future generation is durably quarantined;
9. reconstructing the History Store, compiled flow, Dispatch, and `Engine`
   through `Engine.load` resumes an `ActivityRequested` occurrence without
   executing any prior completed handler;
10. uninterrupted and restarted execution end with equal canonical History,
    marking, active scope, and domain outcome;
11. every generated place and transition and every observed firing maps to an
    authored source block;
12. at least two deliberate composition mistakes fail before any History file
    exists and name both the authored block and source location;
13. one inhibitor-based publication gate is authored through the explicit
    low-level descent seam, still passes `NetSpec.build()` and Net v3
    validation, and visibly prevents two publications from being admitted at
    once; and
14. helper calculations such as evidence ordering, fingerprint comparison,
    retry-key construction, and operation-ID formatting create no transitions
    or History rows.

Passing tests without an explanation/report artifact is incomplete. This
experiment tests developer understanding, not only runtime behavior.

## Read first

### Petrus project and method

Read these before editing the experiment:

1. [ES-059 source-grounded analysis](index.md), especially **Grain rule for
   Petrus**, **Recommended authoring direction**, and **Bounded next
   experiment**.
2. [ES-056 progressive-disclosure developer experience](../es-056-progressive-disclosure-developer-experience/index.md),
   especially **Target experience contract**, **Hamsterdan complexity test**,
   **Candidate evidence probes and order**, and **Candidate gate**.
3. [Progressive disclosure preserves runtime power](../../decisions/records/2026-08-13T1740Z-progressive-disclosure-preserves-runtime-power.md).
4. [The Python DSL compiles authored specifications to canonical nets](../../decisions/records/2026-07-28T0133Z-python-dsl-compiles-authored-specifications-to-canonical-nets.md).
5. [Four spec details are intentionally deferred to kernel time](../../decisions/records/2026-07-08T1727Z-kernel-deferred-spec-details.md),
   specifically the source-map deferral.
6. [Development guide](../../../process/development-guide.md), including its
   TDD and correctness-sensitive-work routes.
7. [Product principles](../../../product/principles.md).

The Petrus source/API baseline inspected for this brief is commit
[`55bacce0b99854b5147ce1ec721859842aee9a1a`](https://github.com/henriquebastos/petrus/tree/55bacce0b99854b5147ce1ec721859842aee9a1a).
The implementation session uses its current checkout, but if any defining API
below has changed it must update this brief or the experiment report with the
new source of truth rather than silently preserving stale calls.

### Current Petrus contracts and APIs

Read the language-neutral contracts before their Python definitions:

- [`spec/OVERVIEW.md`](../../../../spec/OVERVIEW.md) for Net, History,
  Activity, and lifecycle separation;
- [`spec/net-schema.md`](../../../../spec/net-schema.md) for canonical topology
  and the explicit source-map deferral;
- [`spec/net-definition-v3.md`](../../../../spec/net-definition-v3.md) for flat
  canonical interchange, fixed-point laws, and explicit exclusion of source,
  bindings, and History;
- [`spec/event-history.md`](../../../../spec/event-history.md) for replay by
  reapplication, Activities, and exact lifecycle scopes; and
- [`spec/firing-semantics.md`](../../../../spec/firing-semantics.md) and
  [`spec/handler-contract.md`](../../../../spec/handler-contract.md) for firing
  and binding behavior.

Then inspect these defining modules and focused tests:

| Concern | Defining source | Focused evidence |
| --- | --- | --- |
| Authored `NetSpec`, `BuiltNet`, `direct`, `petri_handler`, arcs, stamping, canonical build | [`src/petrus/impetus/dsl.py`](../../../../src/petrus/impetus/dsl.py) (`direct`/escape hatches around lines 97–138, `BuiltNet` 281–291, `NetSpec` 353–541, `NetBuilder` 710–803) | [`tests/petrus/impetus/dsl/test_petrinet_dsl.py`](../../../../tests/petrus/impetus/dsl/test_petrinet_dsl.py) |
| Typed pure and Activity binding | [`src/petrus/impetus/binding/__init__.py`](../../../../src/petrus/impetus/binding/__init__.py) (`ActivityHandler` 35–48, `DerivedActivityHandler` 58–150, typed transforms 316–361) | [`tests/petrus/engine/test_execution.py`](../../../../tests/petrus/engine/test_execution.py) |
| Canonical Net v3 projection, admission, and bytes | [`src/petrus/impetus/net_definition.py`](../../../../src/petrus/impetus/net_definition.py) (`parse` 239–257, `serialize` 260–270, `compile` 289–326, `project` 360–409) | [`tests/petrus/impetus/test_net_definition.py`](../../../../tests/petrus/impetus/test_net_definition.py) |
| Engine create/load/deliver/advance and lifecycle doors | [`src/petrus/engine/__init__.py`](../../../../src/petrus/engine/__init__.py) (`create` 206–246, `load` 248–284, observations 332–365, motion 367–394, scopes 396–435) | [`tests/petrus/engine/test_engine.py`](../../../../tests/petrus/engine/test_engine.py) |
| Canonical firing and Activity records used for attribution | [`src/petrus/impetus/history/__init__.py`](../../../../src/petrus/impetus/history/__init__.py) (`CandidateSelected` 168–175, source delivery 178–212, firing and Activity records 336–533) | [`tests/petrus/impetus/history/test_history.py`](../../../../tests/petrus/impetus/history/test_history.py) and codec coverage in [`tests/petrus/impetus/history_store/test_persistence.py`](../../../../tests/petrus/impetus/history_store/test_persistence.py) |
| Durable credential-free History | [`src/petrus/impetus/history_store/jsonl.py`](../../../../src/petrus/impetus/history_store/jsonl.py) (`JsonlHistoryStore` 112–196) | [`tests/petrus/impetus/history_store/test_persistence.py`](../../../../tests/petrus/impetus/history_store/test_persistence.py) |
| Typed Activities and inline custody | [`src/petrus/motus/activity/__init__.py`](../../../../src/petrus/motus/activity/__init__.py) (`ActivityDeclaration` 45–60, payload conversion 63–120, `activity` 175–194) and [`src/petrus/motus/dispatch/__init__.py`](../../../../src/petrus/motus/dispatch/__init__.py) (`InlineDispatch` 89–155) | `tests/petrus/engine/test_execution.py::TestEngineDrivesTheSeam::test_an_activity_invocation_executes_through_inline_dispatch` |
| Exact generation identity | [`src/petrus/impetus/scope.py`](../../../../src/petrus/impetus/scope.py) | [`tests/petrus/impetus/instance/test_lifecycle_scopes.py`](../../../../tests/petrus/impetus/instance/test_lifecycle_scopes.py) |
| Deterministic DOT artifact | [`src/petrus/impetus/petrinet/dot.py`](../../../../src/petrus/impetus/petrinet/dot.py) | [`tests/petrus/impetus/petrinet/test_petrinet_dot.py`](../../../../tests/petrus/impetus/petrinet/test_petrinet_dot.py) |

Do not copy private Engine coordination internals. The experiment should consume
`Engine`, `NetSpec`, canonical Net v3 functions, `JsonlHistoryStore`,
`InlineDispatch`, current public Petri values, and—where the maintained Python
DSL itself requires it—the defining binding types named above.

### Hamsterdan grounding

The application evidence baseline is the clean Hamsterdan `main` checkout at
[`a14c77825d9616fe0e3f9102cd3476a597fc7da7`](https://github.com/henriquebastos/hamsterdan/tree/a14c77825d9616fe0e3f9102cd3476a597fc7da7),
inspected on 2026-08-26. Use pinned links; never cite moving `main` as the
experiment's authority.

Read only the focused behavior needed for this slice:

- domain identities and outcomes in
  [`contracts/readiness_v5.py`](https://github.com/henriquebastos/hamsterdan/blob/a14c77825d9616fe0e3f9102cd3476a597fc7da7/src/hamsterdan/contracts/readiness_v5.py#L21-L193);
- CI admission and evidence ordering in
  [`readiness/net_v5/ci.py`](https://github.com/henriquebastos/hamsterdan/blob/a14c77825d9616fe0e3f9102cd3476a597fc7da7/src/hamsterdan/readiness/net_v5/ci.py#L54-L139);
- the one-rerun/one-repair ladder in
  [`readiness/net_v5/esc.py`](https://github.com/henriquebastos/hamsterdan/blob/a14c77825d9616fe0e3f9102cd3476a597fc7da7/src/hamsterdan/readiness/net_v5/esc.py#L44-L139);
- incarnation and lineage behavior in
  [`readiness/net_v5/life.py`](https://github.com/henriquebastos/hamsterdan/blob/a14c77825d9616fe0e3f9102cd3476a597fc7da7/src/hamsterdan/readiness/net_v5/life.py#L76-L196);
- the all-gates publication rule and acknowledgement edge in
  [`readiness/net_v5/readiness.py`](https://github.com/henriquebastos/hamsterdan/blob/a14c77825d9616fe0e3f9102cd3476a597fc7da7/src/hamsterdan/readiness/net_v5/readiness.py#L66-L130)
  and
  [`readiness/net_v5/readiness.py`](https://github.com/henriquebastos/hamsterdan/blob/a14c77825d9616fe0e3f9102cd3476a597fc7da7/src/hamsterdan/readiness/net_v5/readiness.py#L315-L322);
- stable typed Activity gates in
  [`readiness/net_v5/gating.py`](https://github.com/henriquebastos/hamsterdan/blob/a14c77825d9616fe0e3f9102cd3476a597fc7da7/src/hamsterdan/readiness/net_v5/gating.py#L67-L264);
- History-based reconstruction in
  [`host/v5/runtime.py`](https://github.com/henriquebastos/hamsterdan/blob/a14c77825d9616fe0e3f9102cd3476a597fc7da7/src/hamsterdan/host/v5/runtime.py#L127-L227);
- ES-003's
  [one-file first-motion probe](https://github.com/henriquebastos/hamsterdan/blob/a14c77825d9616fe0e3f9102cd3476a597fc7da7/docs/project/exploration/es3-workflow-ast-authoring-model/experiments/ax28-first-motion/ax28_one_file.py#L22-L102)
  and
  [descent-seam probe](https://github.com/henriquebastos/hamsterdan/blob/a14c77825d9616fe0e3f9102cd3476a597fc7da7/docs/project/exploration/es3-workflow-ast-authoring-model/experiments/ax29-descent-seam/index.md); and
- ES-010's credential-free
  [workflow-shape proof](https://github.com/henriquebastos/hamsterdan/blob/a14c77825d9616fe0e3f9102cd3476a597fc7da7/docs/project/exploration/es10-composable-hamsterdan-architecture/experiments/spikes/03-workflow-shape/prove.py#L117-L172).

The experiment may learn from these artifacts. It must not import, vendor, or
modify Hamsterdan.

## Classification and repository boundary

This is an Ariad **Experiment inside ES-059 Exploration**. It is not a Delivery
Story because the unknown is whether the proposed authoring shape preserves
the behavior and improves explanation. Disposable code is evidence here, not
a production feature.

All new files belong under:

```text
docs/project/exploration/
  es-059-mit-dataflow-functional-programming-analysis/
    experiment-plan.md
    experiments/
      typed-flow-vertical-slice/
        README.md
        domain.py
        algebra.py
        lowering.py
        source_map.py
        scenario.py
        harness.py
        explain.py
        run_experiment.py
        test_algebra.py
        test_lowering.py
        test_scenario.py
        test_resume_and_attribution.py
        golden/
          readiness.net-v3.json
          readiness.source-map-v1.json
          readiness.explained-history-v1.json
        artifacts/
          readiness.net.dot
          experiment-report.json
        report.md
```

The implementation may collapse two tiny modules when that is clearly simpler,
but it must not create additional package layers or move code outside ES-059.
The final report must list the actual tree if it differs.

Explicitly out of bounds:

- `src/petrus/**`;
- ordinary `tests/**` and `spec/**`;
- Petrus roadmap, decisions, debt, release, or product-principle changes;
- `/home/user/workspace/repos/hamsterdan/**`;
- a Haskell frontend, Haskell runtime, SKI evaluator, or second source syntax;
- external services, GitHub calls, credentials, agents, subprocess Workers, or
  production data;
- a second scheduler, event log, checkpoint store, workflow interpreter,
  generator/coroutine continuation, or call-stack-based workflow truth; and
- a generalized public package hidden under an exploration path.

If the current Petrus API cannot support a required claim without a production
change, stop at the relevant red test and document the exact missing seam. Do
not cross the boundary to make the spike green.

## Settled interpretation of the Hamsterdan slice

The fixture is intentionally smaller than V5. It preserves the ladder and
lifecycle semantics under test while pre-satisfying unrelated readiness gates.

### Behavior retained

- One immutable exact-head CI observation at a time.
- CI evidence identity is `(run_id, attempt)` and freshness is lexicographic
  within the current head.
- Retry budget is keyed by `(lineage, fingerprint)`, not only fingerprint.
- First current failure requests exactly one rerun.
- An equal or older observation is absorbed and spends no budget.
- A strictly newer matching failure after the rerun requests exactly one
  repair.
- A later matching failure after repair produces `HumanNeeded` rather than an
  unbounded retry/repair loop.
- Clean current CI creates a publication request.
- Publication becomes accepted only after a typed Activity terminal crosses a
  separate durable acceptance transition.
- A confirmed repair head advances generation but retains lineage.
- An unrelated branch head advances generation and receives a fresh lineage.
- Process reconstruction uses canonical Petrus History and the same compiled
  definition; no private workflow state is deserialized.

### Simplifications that must be named in source and report

- Full V5 does **not** mean “CI success alone publishes.” Review, findings,
  approval, requested changes, unresolved threads, mergeability, strict base,
  mutation state, and fault state also gate publication. The fixture records
  these as pre-satisfied assumptions rather than reproducing their loops.
- Rerun, repair, and publication are fake typed Activities backed by an
  in-memory idempotency ledger. They do not contact GitHub, invoke an agent,
  create commits, or publish comments.
- Provider moved/faulted/deferred classifications are omitted. Infrastructure
  failure is not converted into a business outcome.
- The experiment models one readiness state baton **per lifecycle generation**,
  not all nine V5 concern loops. Scoped ingress propagates scope provenance in
  current Petrus; reset therefore discards the old baton and the successor
  scoped head observation seeds the next one. The experiment must not mix an
  unscoped long-lived state token with scoped CI evidence.
- `generation` corresponds to V5's lifecycle incarnation, while `lineage`
  separately owns rerun/repair budget. They must not be collapsed.

## Proposed source experience

The concrete spelling is experimental, but the implementation should aim for a
source surface no lower-level than this:

```python
def readiness_flow() -> Machine[ReadinessState]:
    return machine(
        "readiness",
        lifecycle=lifecycle("branch"),
        handlers=(
            on(await_event("head", HeadObserved))
            .project("admit_head", admit_head),

            on(await_event("ci", CIObserved))
            .decide("route_ci", route_ci)
            .choose(
                {
                    PublishRequested: low_level(
                        "publish_once",
                        publication_gate,
                        returns=PublishAcknowledged,
                    ),
                    RerunRequested: effect("rerun", rerun),
                    RepairRequested: effect("repair", repair),
                    HumanNeeded: terminal("human_needed"),
                    Ignored: drop(),
                }
            ),

            on(PublishAcknowledged)
            .fold("accept_publish", accept_publish)
            .to(terminal("published")),
        ),
    )
```

This is not permission to create a fluent framework. The bounded algebra needs
only the constructs exercised here:

| Construct | Meaning | Lowering responsibility |
| --- | --- | --- |
| `await_event` | Typed external ingress with an optional lifecycle-scope name | One source transition and one typed output place, unless a following pure `project` is fused into that firing |
| `project` | Pure typed source-event projection | Fuse with its source transition and emit the first generation-scoped state; no connector firing |
| `fold` | Pure durable update of the state baton | One transition consuming event + state and reproducing state |
| `decide` | Pure update plus one tagged outcome | One transition consuming event + state, reproducing state, and routing zero or one outcome token |
| `choose` | Exhaustive typed routing by outcome type | Composition validation and wire unification; no dispatch transition of its own |
| `effect` | One typed Activity request/result boundary | One Activity transition using current Activity/Dispatch contracts |
| `terminal` | Named observable output | One typed place; no transition by itself |
| `drop` | Deliberate no-output outcome | No generated node; still represented in the decision's exhaustive case table |
| `lifecycle` | Names the exact Engine lifecycle scope used by ingress | Sidecar ingress binding and History attribution; never an invented Net v3 field |
| `low_level` | Explicit Petri descent under one stable authored scope | Callback declares raw `NetSpec` nodes/arcs and returns typed ports; the same compiler validates and builds them |

Do not implement parallel, general recursion, resource algebra, timers, retries,
or syntax sugar merely because the broader ES-059 direction mentions them.
This slice tests the minimum vocabulary that can disprove the hypothesis.

## Domain model

Use frozen dataclasses and closed enums/unions. All values that enter tokens,
Activity payloads, or History must encode to JSON-faithful data.

The exact names below are recommended so a clean session and the final report
share vocabulary:

```python
@dataclass(frozen=True)
class Evidence:
    run_id: int
    attempt: int

@dataclass(frozen=True)
class HeadObserved:
    head: str
    relation: Literal["new", "confirmed", "superseded"]
    generation: int
    lineage: str

@dataclass(frozen=True)
class CIObserved:
    head: str
    evidence: Evidence
    conclusion: Literal["success", "failure"]
    fingerprint: str | None = None

@dataclass(frozen=True)
class Ladder:
    lineage: str
    fingerprint: str | None
    rerun_used: bool
    repair_used: bool
    watermark: Evidence | None

@dataclass(frozen=True)
class ReadinessState:
    head: str
    generation: int
    lineage: str
    ladder: Ladder
    publication_operation: str | None  # set when requested; prevents duplicate authorization

@dataclass(frozen=True)
class PublishRequested:
    operation: str
    head: str
    generation: int

@dataclass(frozen=True)
class RerunRequested:
    operation: str
    head: str
    lineage: str
    fingerprint: str
    evidence: Evidence

@dataclass(frozen=True)
class RepairRequested: ...
@dataclass(frozen=True)
class HumanNeeded: ...
@dataclass(frozen=True)
class Ignored: ...

@dataclass(frozen=True)
class RerunAccepted: ...
@dataclass(frozen=True)
class RepairLanded: ...
@dataclass(frozen=True)
class PublishAcknowledged: ...
@dataclass(frozen=True)
class Published: ...
```

`Evidence` should either be flattened before durable encoding or converted by
a small explicit payload converter. Do not assume the current top-level
`DataclassPayloadConverter` recursively reconstructs nested dataclasses; it
does not. The simplest correct option is an experiment-local converter that
uses explicit `to_data`/`from_data` functions for these known values. Keep it
in `domain.py`; do not create a generic serialization framework.

Pure domain functions belong in `scenario.py` and remain ordinary functions:

```python
def admit_head(event: HeadObserved) -> ReadinessState:
    """Seed the successor generation from an explicit head/lineage fact."""

def route_ci(
    state: ReadinessState,
    event: CIObserved,
) -> Decision[
    ReadinessState,
    PublishRequested | RerunRequested | RepairRequested | HumanNeeded | Ignored,
]:
    """Update the state baton and choose exactly one domain outcome."""

def accept_publish(
    state: ReadinessState,
    event: PublishAcknowledged,
) -> tuple[ReadinessState, Published]:
    """Record publication only after the effect terminal is accepted."""
```

The practical implementation may return a small `Decision[State, Outcome]`
value from `route_ci` so state and outcome are emitted together. That
`Decision` is algebra machinery, not a durable domain color; the lowering
handler serializes its `state` and selected domain outcome to separate tokens.

Evidence comparison, fingerprint equality, operation-ID formatting, and retry
key creation are called from these functions. They must remain ordinary code.

Stable operation IDs are:

```text
publish:{head}:g{generation}
rerun:{lineage}:{fingerprint}
repair:{lineage}:{fingerprint}
```

The same logical request must retain the same operation ID after restart.

## Algebra and composition contract

`algebra.py` owns immutable source values only. It performs no motion and holds
no mutable runtime state.

Use Python 3.14 type parameters where they improve the source:

```python
@dataclass(frozen=True)
class SourceRef:
    id: str
    file: str
    line: int
    symbol: str

@dataclass(frozen=True)
class Port[T]:
    value_type: type[T]
    source: SourceRef

@dataclass(frozen=True)
class Flow[I, O]:
    node: FlowNode
    input: Port[I] | None
    outputs: Mapping[type[object], Port[object]]
```

The implementation does not have to preserve this exact class factoring if a
smaller immutable ADT is clearer. It must preserve these rules:

1. Every authored construct has an explicit stable local `id` and `SourceRef`.
2. Source file paths are normalized relative to the experiment root; absolute
   orb paths never enter goldens.
3. `SourceRef` may inspect a function's `__code__.co_firstlineno` for tooling
   attribution. No frame, generator, coroutine, or call stack is retained or
   consulted during execution or resume.
4. Nominal port identity is the concrete dataclass type, with its `__name__`
   becoming the Petrus color. Refuse two distinct classes with the same nominal
   name in one flow.
5. Composition checks exact producer/consumer type equality. Do not infer
   global wiring from matching types.
6. `choose` is exhaustive over the decision's declared outcome types. Missing,
   duplicate, or extra branches fail before lowering.
7. IDs are unique within their authored scope. Duplicate IDs fail with both
   source references.
8. The AST contains functions and Activity definitions as implementation
   bindings, but those never enter canonical Net v3 bytes.
9. Creating or compiling a flow performs no History write, Activity, provider
   call, or Engine construction.

Localized refusal examples should look like:

```text
CompositionError: scenario.py:84 [route_ci.failed] produces RerunRequested,
but scenario.py:91 [repair] accepts RepairRequested
```

and:

```text
CompositionError: scenario.py:76 [route_ci] has no branch for HumanNeeded
```

Tests should assert the consequential fragments, not Python traceback text.

## Lowering contract

`lowering.py` owns one pure compilation passage:

```python
@dataclass(frozen=True)
class CompiledFlow:
    built: BuiltNet
    handlers: Mapping[NetUri, Handler | ActivityHandler]
    guards: Mapping[NetUri, Guard]
    activities: tuple[ActivityDefinition, ...]
    initial_marking: Marking  # empty; the first scoped head seeds state
    ingress: Mapping[str, IngressBinding]
    source_map: SourceMapV1
    definition_bytes: bytes

def compile_flow(machine: Machine[ReadinessState]) -> CompiledFlow: ...
```

`definition_bytes` is exactly:

```python
serialize_net_definition(project_net_definition(compiled.built.net))
```

and must round-trip through `parse_net_definition`. `CompiledFlow` is an
experiment assembly value, not a new runtime authority. The existing `Net` is
canonical topology; `handlers`/`guards` are live bindings; History is created
only by the harness.

Lower in this order:

1. validate IDs, nominal types, source references, branch exhaustiveness, and
   lifecycle declarations;
2. allocate deterministic node paths and record their authored owner;
3. declare places, transitions, and arcs into one `NetSpec`;
4. let low-level fragments declare their nodes/arcs under their assigned scope;
5. call `NetSpec.build()` once, retaining its `BuiltNet` bindings;
6. derive typed Activity handlers against the resulting canonical `Net` and
   merge them with `BuiltNet.handlers` by the transition's canonical handler
   URI;
7. project/serialize/strictly parse Net v3;
8. finish and serialize the source-map sidecar using the definition hash; and
9. return immutable snapshots.

### Stable naming

Generated names are a contract of this experiment. They derive only from the
root name, explicit authored IDs, and fixed semantic roles—never object IDs,
Python hashes, UUIDs, set iteration, registration order, or callable names.

Use these exact paths unless `NetPath` validation forces a documented spelling
change:

```text
ingress.head
ingress.ci
events.ci
readiness.state
readiness.route_ci.fire
commands.publish
commands.rerun
commands.repair
terminal.human_needed
effects.rerun.fire
facts.rerun_accepted
effects.repair.fire
facts.repair_landed
effects.publish.pending
effects.publish.done
effects.publish.work
effects.publish.authorize
effects.publish.execute
effects.publish.ack
effects.publish.accept
facts.publish_acknowledged
readiness.accept_publish.fire
terminal.published
```

The compiler should allocate in deterministic source traversal order; Net v3
itself canonicalizes path collections. Arc order is semantic in v3, so lowering
must emit arcs from fixed role tables, never unordered mappings.

### Pure decisions

The state folds need multiple differently colored outputs, so their compiler
bridge is Petri-aware and wrapped with current `petri_handler(...)`. Authored
domain code remains typed and Petri-agnostic; only compiler-owned projection
code reads `Binding`, chooses output arcs, and creates `Token`s.

Use `direct(...)` where its existing one-result-color contract fits naturally.
Do not contort the scenario solely to maximize use of `direct`.

### Activities and stable identity

Activity transitions should declare a stable symbolic handler in `NetSpec`,
then bind an `ActivityHandler` by `net.handler_uri(path)` after canonical build.
The current DSL does not directly lower an `ActivityDefinition` supplied as a
transition callable.

Compose current `DerivedActivityHandler` with one tiny experiment-local wrapper
that replaces the prepared invocation's `correlation` and `idempotency` with
the request's `operation`. Delegate result projection to the derived handler.
Do not reimplement typed arc matching or Activity payload conversion.

All Activities use `ExecutionPolicy(attempts=1)`. The **domain** decides whether
to request rerun or repair; Motus operational retries must not manufacture
another business rung.

### Low-level descent

`low_level("publish_once", publication_gate, ...)` receives a bounded
`FragmentContext` for `effects.publish`. The callback declares:

```text
commands.publish ──▶ authorize ──▶ work ──▶ execute(Activity) ──▶ ack
                          │                                  │
                          └────────▶ pending ────────────────┘

pending ── inhibit ──▶ authorize
done    ── inhibit ──▶ authorize

pending + ack ──▶ accept ──▶ facts.publish_acknowledged + done
```

The inhibitor is the expression that justifies descent. The fragment returns
its typed input/output ports and any handler-binding requests. The compiler
must verify after `NetSpec.build()` that:

- every returned path exists with the declared kind and color;
- every created node remains inside `effects.publish` except the explicitly
  supplied input/output places;
- the fragment's nodes all have source-map ownership;
- its Activity handler is bound by canonical URI; and
- the final whole Net still round-trips through Net v3.

Do not add a generic graph-import API. One callback protocol is enough to test
the descent seam.

## Expected canonical topology

The first green lowering should contain exactly **14 places, 9 transitions,
and 28 arcs** under the names above:

| Transition | Durable meaning | Inputs | Outputs |
| --- | --- | --- | --- |
| `ingress.head` | Accept one identified head observation and seed its generation state | source delivery | state |
| `ingress.ci` | Accept one identified CI observation | source delivery | `events.ci` |
| `readiness.route_ci.fire` | Accept current CI evidence and commit one ladder decision | state + CI | state + zero/one command or terminal |
| `effects.rerun.fire` | Request/observe fake rerun effect | rerun request | rerun accepted |
| `effects.repair.fire` | Request/observe fake repair effect | repair request | repair landed |
| `effects.publish.authorize` | Admit one publication while none is pending or done | publish request + pending/done inhibitors | work + pending |
| `effects.publish.execute` | Request/observe fake publication effect | work | ack |
| `effects.publish.accept` | Accept effect terminal, release pending, and latch done | pending + ack | publication acknowledgement + done |
| `readiness.accept_publish.fire` | Commit acknowledged publication into state | state + acknowledgement | state + published terminal |

The route transition has one output arc for state and one for each of
`PublishRequested`, `RerunRequested`, `RepairRequested`, and `HumanNeeded`.
`Ignored` deliberately produces only the updated/unchanged state.

`ingress.head` uses a compiler-owned typed source projection for `admit_head`.
This fuses event acceptance and successor-state seeding into one durable source
firing. It is not a hidden transition optimization: the accepted head fact and
its produced state remain explicit in canonical History and map to the
authored `await_event(...).project(...)` block.

The topology count is deliberate and mechanically checkable:

- 14 places: CI event, readiness state, three command places, human terminal,
  two effect-result facts, publication pending/done/work/ack, accepted
  publication fact, and published terminal;
- 9 transitions: two ingress, route, rerun, repair, publication authorize,
  publication execute, publication accept, and publication-state accept; and
- 28 arcs: `1 + 1 + 7 + 2 + 2 + 5 + 2 + 4 + 4` in that transition order,
  where publication authorization's five include its two inhibitor arcs.

Every token produced from scoped ingress—including state, commands, Activity
results, and terminals—retains that exact generation. `reset_scope` therefore
cleans the old generation completely. The next head must be delivered under
the newly opened exact scope before any CI event can advance.

`route_ci` records `publication_operation` in state when it emits the first
request, so repeated clean evidence does not intentionally enqueue duplicate
work. The fragment's `pending` and `done` inhibitors are still tested against
two directly supplied request tokens as a structural descent property: even a
misbehaving upstream cannot admit two publications concurrently or serially in
one generation.

If the exact count cannot be achieved because an existing Petrus contract
requires an additional honest node, document the requirement before changing
the golden. Do not optimize away a durable boundary to preserve the count.
Conversely, a compiler-only connector, dispatch, map, or format transition is a
failure of coarse grain and should be removed.

## Source-map sidecar

Canonical Net v3 intentionally excludes implementation bindings, Python
source, and repository provenance. Do not add experimental fields to it.

`source_map.py` owns an experiment-only deterministic sidecar:

```json
{
  "format": "petrus-experiment-source-map",
  "version": 1,
  "definition_sha256": "<sha256 of exact Net v3 bytes>",
  "sources": [
    {
      "id": "readiness.route_ci",
      "file": "scenario.py",
      "line": 120,
      "symbol": "route_ci"
    }
  ],
  "elements": [
    {
      "kind": "transition",
      "path": "readiness.route_ci.fire",
      "source": "readiness.route_ci",
      "role": "durable decision"
    }
  ],
  "lifecycle_scopes": [
    {
      "name": "branch",
      "source": "readiness.branch_generation"
    }
  ]
}
```

Requirements:

- `sources` sort by `id`;
- elements sort by `(kind, path-or-uri)`;
- source paths are experiment-relative POSIX paths;
- every canonical place and transition has exactly one element;
- handler declaration URIs may also be mapped, but never replace transition
  mapping;
- scope names map lifecycle History records that have no Net node;
- bytes use UTF-8, `ensure_ascii=False`, `allow_nan=False`, two-space indent,
  and one final newline;
- repeated lowering yields byte-equal sidecars; and
- the hash must match the exact retained Net v3 golden.

The sidecar is not described as canonical Petrus protocol. Its job is to test
whether enough attribution can be preserved outside runtime semantics to
justify later source-map design.

## History attribution

`explain.py` joins immutable History records to the source-map sidecar without
changing either:

- records with `transition` map by transition path;
- movement records with `place` map by place path;
- external-delivery records with `source` map by source-transition path;
- scope open/reset/close and scoped disposition records map by scope name; and
- `InstanceCreated` maps to the root authored machine.

Group firing records by `occurrence`. A concise explained firing should show:

```text
occurrence 7
  source: scenario.py:120 route_ci [readiness.route_ci]
  transition: readiness.route_ci.fire
  accepted: CIObserved(head=h2, evidence=(20, 1), failure=build)
  produced: RerunRequested(operation=rerun:L2:build)
```

Tests must fail if any `CandidateSelected`, `ExternalEventDelivered`,
`FiringBegun`, `ActivityRequested`, `ActivityCompleted`, `FiringCompleted`, or
`FiringFailed` record lacks attribution. They should also verify movement and
scope attribution, while allowing explicitly enumerated neutral records only
if no authored owner exists.

The golden explained History is a detached JSON projection, not a second
semantic log. It is always regenerated from canonical History plus the source
map.

## Runtime and restart route

`harness.py` is test/application assembly around the current runtime. It may
provide only:

- `create(compiled, history_path, provider_ledger) -> Engine`;
- `load(compiled, history_path, provider_ledger) -> Engine`;
- a bounded `drain(engine, limit=...)` loop over `Engine.advance()`;
- typed `deliver_head` and `deliver_ci` helpers that call `Engine.deliver`
  using the compiled ingress binding and exact `LifecycleScope`; and
- deterministic extraction of one state/terminal value from `engine.marking`.

This is not a workflow runner proposal. It contains no semantic branch,
retry, repair, or publication decision; those remain in the compiled Net. The
bounded drain is ordinary host driving of the existing Engine.

Use `JsonlHistoryStore` in a temporary directory for every runtime test. Use
`InlineDispatch` with three typed fake Activities and an independently supplied
`FakeProviderLedger` keyed by operation ID. The ledger records invocation count
and returns the same typed result for an already-seen operation. It is not
canonical workflow state; it simulates an external provider's idempotency
boundary.

Restart evidence should exercise the hard useful boundary:

1. run until `effects.repair.fire` has appended `ActivityRequested` and
   `InlineDispatch` has executed/buffered the terminal;
2. discard/close that Engine before another `advance()` can append
   `ActivityCompleted`;
3. reconstruct the source value and compile it again;
4. construct a new `JsonlHistoryStore` over the same path;
5. construct a fresh `InlineDispatch` and `Engine.load` with the same
   independent fake-provider ledger;
6. call `advance()`; replay must recover the in-flight request and redispatch
   it with the same recorded correlation/idempotency;
7. assert the fake ledger observed two delivery attempts but one logical
   repair operation/effect; and
8. continue to the same canonical outcome as an uninterrupted control run.

This proves Engine/History reconstruction and at-least-once Activity
redispatch in one process using reconstructed objects. Do not claim OS-process
kill, power-loss durability, remote Worker recovery, or exactly-once effects.

## Exact fixture trace

Use deterministic strings and integer time zero. No wall clock, random value,
UUID, temporary absolute path, or environment-dependent field may enter a
golden.

```text
1.  Create Instance with an empty marking; no generation state exists yet.
2.  Open LifecycleScope("branch", 1).
3.  Deliver HeadObserved(h1, new, generation=1, lineage=L1), id=head-h1-g1.
    Its scoped source firing seeds the generation-1 ReadinessState token.
4.  Deliver CIObserved(h1, evidence=(10,1), success), id=ci-10-1-g1.
5.  Drain.
    Expect publication operation publish:h1:g1 exactly once and Published(h1,g1).

6.  Reset branch scope g1 -> g2 atomically.
7.  Deliver HeadObserved(h2, superseded, generation=2, lineage=L2), id=head-h2-g2.
8.  Deliver CIObserved(h2, evidence=(20,1), failure, fingerprint=build),
    id=ci-20-1-g2.
9.  Drain.
    Expect one rerun operation rerun:L2:build and no repair.

10. Redeliver the same CI identity and payload.
    Expect Petrus prior acknowledgement, no new firing, and no new budget.
11. Deliver the same evidence under a different ingress identity.
    Expect the domain decision to produce Ignored and no effect request.

12. Deliver CIObserved(h2, evidence=(20,2), failure, fingerprint=build),
    id=ci-20-2-g2.
13. Advance only until repair ActivityRequested is durable; interrupt before
    its terminal is accepted.
14. Reconstruct compiled source, JSONL store, Dispatch, and Engine.load.
15. Drain.
    Expect repair operation repair:L2:build, one logical fake-provider effect,
    and RepairLanded(h2 -> h2r).

16. Reset branch scope g2 -> g3.
17. Deliver HeadObserved(h2r, confirmed, generation=3, lineage=L2),
    id=head-h2r-g3.
18. Deliver CIObserved(h2r, evidence=(21,1), success), id=ci-21-1-g3.
19. Drain.
    Expect publish:h2r:g3 and lineage still L2.

20. Reset branch scope g3 -> g4.
21. Deliver HeadObserved(h3, superseded, generation=4, lineage=L4),
    id=head-h3-g4.
22. Deliver a stale g3 CI event to exact closed scope g3.
    Expect ScopedDeliveryDropped and no source firing.
23. Deliver a g5 CI event to exact unproven future scope g5.
    Expect ScopedDeliveryQuarantined and no source firing.
24. Reload once more from the final History.
    Expect active scope g4, head h3, lineage L4, fresh ladder, identical marking,
    and both scoped dispositions preserved.
```

Run the same semantic trace without the interruption at step 13. Apart from
the fake provider's operational attempt count, canonical History bytes,
History records, final marking, active scopes, and explained semantic trace
must equal the restarted run. `Engine.close()` itself writes no semantic
record, so restart must not create a canonical difference.

## Acceptance tests

Use the names below or preserve their exact claims if local naming changes.

### `test_algebra.py`

1. `test_flow_values_are_immutable_and_construction_performs_no_motion`
2. `test_composition_refuses_mismatched_ports_at_both_source_locations`
3. `test_choose_refuses_a_missing_outcome_before_lowering`
4. `test_duplicate_authored_ids_name_both_sources`
5. `test_distinct_types_with_the_same_nominal_name_are_refused`

### `test_lowering.py`

1. `test_repeated_lowering_is_byte_stable_and_matches_net_v3_golden`
2. `test_net_v3_round_trips_through_current_parser_and_compiler`
3. `test_expected_topology_has_only_durable_transitions`
4. `test_every_place_transition_and_handler_has_source_ownership`
5. `test_source_map_is_stable_hash_bound_and_matches_golden`
6. `test_low_level_publication_gate_uses_an_inhibitor_and_canonical_validation`
7. `test_activity_bindings_use_canonical_handler_uris_and_stable_operation_identity`

### `test_scenario.py`

1. `test_clean_ci_publishes_once_after_typed_acknowledgement`
2. `test_first_failure_reruns_once_and_duplicate_evidence_spends_nothing`
3. `test_newer_persistent_failure_repairs_without_a_second_rerun`
4. `test_failure_after_repair_surfaces_human_needed`
5. `test_confirmed_repair_head_keeps_lineage_and_unrelated_head_resets_it`
6. `test_publication_inhibitor_allows_only_one_pending_operation`
7. `test_closed_generation_drops_and_future_generation_quarantines_ingress`

### `test_resume_and_attribution.py`

1. `test_activity_requested_restart_redispatches_one_logical_operation`
2. `test_restarted_and_uninterrupted_runs_have_identical_canonical_history`
3. `test_engine_load_rebuilds_marking_scope_and_ladder_without_reexecuting_completed_handlers`
4. `test_every_observed_firing_explains_back_to_authored_source`
5. `test_explained_history_matches_golden_and_is_not_execution_authority`

The scenario tests should inspect canonical records and marking, not only the
fake Activity ledger. Where possible assert the exact record class and
transition path that establish a durable boundary.

## Red/green experiment sequence

Keep the experiment describable after every phase. Do not write the whole
prototype and test it only at the end.

### Phase 0 — baseline and skeleton

1. Confirm the Petrus checkout and Hamsterdan pinned revision.
2. Run the exploration identity test and the focused existing Petrus tests
   named in **Read first**.
3. Create the experiment tree, README, and empty report with the boundary and
   commands.
4. Record the exact starting Petrus commit in the report.

### Phase 1 — immutable algebra and local errors

1. Write the mismatched-port and missing-branch tests first.
2. Confirm each fails because the composition check is missing, not because of
   imports or syntax.
3. Implement only the source values and bounded constructors needed by those
   tests.
4. Add duplicate-ID and nominal-collision refusals.
5. Run `ty` on the experiment's valid source files as an additional check; the
   behavioral contract remains the explicit pre-motion composition refusal.

Checkpoint question: does the source read in domain terms, or is it already a
thin spelling of places/transitions/arcs? Stop and simplify if it is the latter.

### Phase 2 — deterministic lowering and source map

1. Write a red topology/byte-stability test from a minimal head + CI source.
2. Lower through `NetSpec`, `BuiltNet`, and canonical Net v3.
3. Add source ownership as nodes are allocated; do not reverse-engineer source
   ownership from generated names afterward.
4. Add exact source-map serialization and hash binding.
5. Add the expected topology invariant and verify pure helper functions have
   no nodes.
6. Generate initial goldens only after the in-memory equality assertions pass.

Checkpoint question: can a generated identity remain stable under a fresh AST
construction without relying on object/callable identity? If not, stop.

### Phase 3 — pure Hamsterdan-shaped semantics

1. Write unit tests for `admit_head` and `route_ci` as ordinary functions.
2. Add Engine tests for clean, first-failure, duplicate, persistent-failure,
   confirmed-head, unrelated-head, and human-needed behavior.
3. Keep review and other gates explicit as fixture assumptions.
4. Assert state-token and command-token data remain JSON-faithful through
   JSONL reconstruction.

Checkpoint question: does one domain decision lower to one transition, or has
the compiler introduced bookkeeping firings? Remove bookkeeping before
continuing.

### Phase 4 — Activities and low-level descent

1. Add typed fake Activities and the URI-bound derived handlers.
2. Test stable correlation/idempotency from domain operation IDs.
3. Add the publication fragment through `low_level`, initially without its
   inhibitor to establish the counterfactual.
4. Show that two ready tokens can become concurrently pending without the arc.
5. Add the inhibitor and show peak pending occupancy is one.
6. Keep both fragment and whole-Net validation green.

Checkpoint question: did descent preserve source ownership, port checks, and
canonical validation? If any were bypassed, the experiment fails until the
seam is redesigned.

### Phase 5 — restart, replay, and attribution

1. Run the exact uninterrupted fixture to a temporary JSONL History.
2. Add the interruption after `ActivityRequested` and reconstruct every live
   runtime object through public doors.
3. Compare encoded records, JSONL bytes, marking, scopes, and outcomes.
4. Add closed/future generation dispositions and reload again.
5. Generate explained History only from canonical records plus source map.
6. Fail on unattributed firings and compare the stable explanation golden.

Checkpoint question: is any semantic continuation stored only in the harness,
fake ledger, Python closure, or source AST? If yes, the runtime-resume claim
fails.

### Phase 6 — evidence and closure

1. Run all focused experiment tests.
2. Run formatting/lint/type checks on experiment Python.
3. Run the relevant existing Petrus focused tests.
4. Run `scripts/check full`.
5. Run `run_experiment.py` into a temporary directory, inspect every generated
   artifact, then deliberately update retained goldens/artifacts.
6. Complete `report.md` with expected vs observed behavior, source/topology
   comparison, limits, surprises, and recommendation.
7. Update ES-059's status and disposition according to the result. Do not
   promote ES-056 or open Delivery without Navigator direction.

## Commands for a clean session

From the Petrus repository root:

```bash
git status --short --branch
git rev-parse HEAD

UV_FROZEN=1 uv run pytest -q tests/project/test_exploration_identity.py

EXP=docs/project/exploration/es-059-mit-dataflow-functional-programming-analysis/experiments/typed-flow-vertical-slice

# Smallest loop: replace NODE with the current red/green test node.
UV_FROZEN=1 uv run pytest -q "$EXP/test_algebra.py::NODE"

# Complete experiment.
UV_FROZEN=1 uv run pytest -q "$EXP"

# Static and style feedback for the disposable Python source.
UV_FROZEN=1 uv run ruff check "$EXP"
UV_FROZEN=1 uv run ruff format --check "$EXP"
UV_FROZEN=1 uv run ty check \
  "$EXP/domain.py" "$EXP/algebra.py" "$EXP/lowering.py" \
  "$EXP/source_map.py" "$EXP/scenario.py" "$EXP/harness.py" \
  "$EXP/explain.py" "$EXP/run_experiment.py"

# Existing contract regression points.
UV_FROZEN=1 uv run pytest -q \
  tests/petrus/impetus/dsl/test_petrinet_dsl.py \
  tests/petrus/impetus/test_net_definition.py \
  tests/petrus/engine/test_execution.py \
  tests/petrus/impetus/instance/test_lifecycle_scopes.py

# Evidence bundle: temporary first, retained only after inspection.
rm -rf /tmp/petrus-es-059-typed-flow
UV_FROZEN=1 uv run python "$EXP/run_experiment.py" \
  --output /tmp/petrus-es-059-typed-flow

scripts/check full
```

If pytest import resolution does not include the experiment directory, add one
small `conftest.py` beside the experiment tests that prepends only that
directory. This follows the retained Hamsterdan AX29 precedent. Do not modify
the repository's root `conftest.py` or install the experiment as a package.

`run_experiment.py` should default to a caller-supplied output directory and
refuse to overwrite retained goldens accidentally. An explicit
`--update-goldens` mode may update files under `golden/` only after all in-memory
checks pass. Tests never rewrite tracked artifacts.

## Evidence bundle and report

Retain only reviewable deterministic evidence:

- canonical Net v3 JSON;
- source-map v1 JSON;
- deterministic DOT source (not PNG/SVG unless a visual issue requires it);
- canonical History JSONL for the accepted fixture;
- explained History projection;
- a machine-readable experiment report with hashes/counts/results; and
- `report.md`, the human-readable Experience Report.

If History JSONL duplicates a golden exactly, retain one copy and record both
uninterrupted/resumed hashes in `experiment-report.json` rather than keeping
duplicate files.

`report.md` must contain:

1. **Verdict:** promising, mixed, or refuted.
2. **Source experience:** the complete authored flow and how many concepts a
   maintainer needs before understanding the ladder.
3. **Generated topology:** place/transition/arc counts and every durable
   transition's meaning.
4. **Acceptance matrix:** each completion condition, expected result, observed
   result, pass/fail, and evidence link.
5. **Restart route:** exact interruption point, reconstructed objects,
   redispatch observation, and claims deliberately not made.
6. **Attribution:** examples from source → generated node → History firing and
   the unattributed-record count.
7. **Error locality:** exact deliberate mistakes and diagnostics.
8. **Descent:** why the inhibitor required low-level expression and which
   validations remained active.
9. **Grain assessment:** ordinary functions not lowered, transitions retained,
   and any suspected bookkeeping firing.
10. **Comparison with direct authoring:** concepts, explanation steps, change
    locality, and topology visibility. Line counts are supporting data only.
11. **Limits and surprises.** Distinguish simulated provider behavior from
    Petrus-executed evidence.
12. **Driver recommendation and next route.** No automatic promotion.

Grade evidence per the development guide: `[E]` for executed observations,
`[D]` for checked contracts/source, `[R]` for unverified reports, and `[X]` for
refutations.

## Stop conditions

Stop implementation and record the finding instead of widening scope when any
of these occurs:

1. A required acceptance claim needs a change under `src/petrus`, `spec`, or
   normal tests.
2. The source AST or harness must be consulted to resume semantic execution.
3. A generator frame, coroutine, callback stack, or mutable builder becomes
   workflow truth.
4. The harness starts deciding clean/rerun/repair/publish paths or polling
   marking to implement semantics rather than to assert/stop a test.
5. Canonical Net v3 must be extended with source fields for the sidecar to
   work.
6. Source attribution cannot survive fresh source construction or cannot map
   all observed firings.
7. Stable node IDs require object identity, hashing, registration order, or
   absolute paths.
8. Low-level descent bypasses composition checks, source ownership,
   `NetSpec.build()`, or canonical Net validation.
9. One ordinary calculation becomes a transition solely because the compiler
   is graph-shaped.
10. The slice needs Hamsterdan imports, GitHub authority, credentials, agent
    execution, or a production fixture.
11. The fake provider is mistaken for exactly-once proof, or process-object
    reconstruction is mislabeled as OS/power-loss testing.
12. The source is no easier to explain than the generated topology.

A stop-condition result can be a successful experiment if it precisely
refutes the hypothesis and identifies the boundary.

## Result classification and promotion gate

### Promising

Classify as promising only if every mechanical completion condition passes and
the report shows a material explanation/change-locality improvement without
hiding a durable boundary. The follow-up is to attach the report to ES-056's
AX28/AX29 evidence and ask the Navigator whether the candidate should move
toward Delivery. Do not move code from Exploration yet.

### Mixed

Classify as mixed when canonical execution works but one authoring property is
weak—for example source mapping is brittle, error locality is poor, or the
algebra is a disguised graph builder. Preserve the spike and open a narrower
inquiry/experiment inside ES-059 only if the Navigator wants more learning.

### Refuted

Classify as refuted when coarse behavior cannot lower without semantic
distortion, History attribution fails fundamentally, descent creates another
execution model, or runtime overhead dominates even at this grain. Record the
counterevidence and return to ES-059's architectural conclusion. Do not rescue
the prototype by broadening it into a runtime rewrite.

### Promotion requirements beyond this experiment

Even a promising result does not select public syntax or package ownership. A
future promoted authoring capability still needs:

- Navigator acceptance of the source experience;
- a public source-map/evolution decision rather than this sidecar format;
- AX28's honest first-motion profile and run-surface ownership;
- AX29's maintained low-level descent contract;
- a larger Hamsterdan benchmark for unsupported constructs; and
- a Delivery plan with compatibility, documentation, and migration boundaries.

## Exact resume route

A new clean session should:

1. read ES-059 `index.md` and this file completely;
2. inspect ES-059 status and any existing `experiments/typed-flow-vertical-slice`
   files before creating or replacing anything;
3. run `git status --short --branch` and preserve unrelated work;
4. verify the defining APIs and pinned Hamsterdan references still match the
   brief;
5. start at the first incomplete phase and first red test—not by redesigning
   the whole algebra;
6. keep every edit under ES-059 unless a stop condition is reached;
7. render the normal Ariad experiment/checkpoint surfaces as evidence changes;
8. run the complete validation route and inspect generated artifacts;
9. complete the report and update ES-059's status/disposition; and
10. commit the exploration artifacts locally under Petrus's commit policy,
    then ask before any push.

The experiment's purpose is to learn whether Petrus should keep going with a
better source language over its current semantics. Its purpose is not to make
the prototype permanent.
