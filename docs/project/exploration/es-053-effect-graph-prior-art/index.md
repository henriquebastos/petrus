---
code: ES-053
status: Completed
status_reason: The source comparison answered the inquiry and supports bounded maintenance and future analysis guidance, not a new runtime substrate or current Delivery candidate.
opened: 2026-08-15
related:
  - docs/project/decisions/records/2026-07-29T2303Z-libpetri-is-prior-art-not-runtime-substrate.md
  - docs/project/decisions/records/2026-07-08T1541Z-analysis-three-tier-commitment.md
  - docs/project/decisions/records/2026-08-09T1700Z-canonical-arc-filter-occurrence-identities.md
  - docs/project/decisions/records/2026-07-28T1917Z-canonical-net-graphviz-rendering-is-presentation-only.md
research_source:
  - https://github.com/Effect-TS/effect/blob/6eebd0a618308a91f95947bae6e0fb206ae3939d/packages/effect/src/Graph.ts
---

# Effect Graph as generic topology prior art

## Inquiry

What should Petrus copy, adapt, or reject from Effect's generic `Graph` module
without weakening canonical Petri-net identity, topology, arc semantics,
execution, or the ratified analysis boundary?

The answer turns on one category distinction:

> Effect models a generic indexed adjacency-list multigraph. Petrus `Net`
> models a canonical, typed Petri-net definition whose topology participates in
> execution semantics.

Effect is strong prior art for generic graph mechanics and tests. It is the
wrong canonical model, runtime dependency, or semantic oracle for Petrus. The
best transfer is a small read-only topology projection derived from canonical
`Net` when T2 analysis or inspection needs it—not a second graph truth.

## Research baseline

- `[D]` Effect was inspected at
  [`6eebd0a`](https://github.com/Effect-TS/effect/tree/6eebd0a618308a91f95947bae6e0fb206ae3939d),
  the head of `main` on 2026-08-15. The primary source is the
  [5,832-line `Graph.ts`](https://github.com/Effect-TS/effect/blob/6eebd0a618308a91f95947bae6e0fb206ae3939d/packages/effect/src/Graph.ts),
  with focused
  [`Graph.test.ts`](https://github.com/Effect-TS/effect/blob/6eebd0a618308a91f95947bae6e0fb206ae3939d/packages/effect/test/Graph.test.ts)
  and
  [`Pathfinding.test.ts`](https://github.com/Effect-TS/effect/blob/6eebd0a618308a91f95947bae6e0fb206ae3939d/packages/effect/test/Pathfinding.test.ts)
  evidence.
- `[D]` Effect source is MIT-licensed under Effectful Technologies Inc
  ([license](https://github.com/Effect-TS/effect/blob/6eebd0a618308a91f95947bae6e0fb206ae3939d/LICENSE)).
  Petrus should independently implement the few domain-fitting ideas. A future
  literal translation or substantial source copy would require preserving the
  MIT notice and recording provenance.
- `[E]` Petrus claims below come from the current canonical schema, DSL,
  definition projection, enabledness, firing, DOT renderer, focused tests, and
  retained decisions. One disposable runtime probe tested the public
  immutability and missing-node query claims directly.
- `[R]` The retained libpetri and analysis decisions are authoritative over
  any new architectural attraction created by this comparison.

## What Effect Graph actually provides

Effect stores nodes and edges separately by generated numeric indexes, with
forward and reverse adjacency lists plus monotonic next-index counters
([representation](https://github.com/Effect-TS/effect/blob/6eebd0a618308a91f95947bae6e0fb206ae3939d/packages/effect/src/Graph.ts#L210-L224)).
Every `addEdge` allocates a distinct edge index, so parallel edges and
self-loops are first-class. A graph-wide kind selects directed or undirected
behavior
([edge insertion](https://github.com/Effect-TS/effect/blob/6eebd0a618308a91f95947bae6e0fb206ae3939d/packages/effect/src/Graph.ts#L2281-L2335)).

The module then builds a broad graph toolkit over that representation:

- immutable graphs and scoped mutable copies;
- indexed node/edge lookup, neighbors, predecessors, successors, degrees, and
  externals;
- lazy DFS, BFS, postorder, direction controls, and radius limits;
- cycle detection, bipartiteness, connected components, strongly connected
  components, and topological order;
- Dijkstra, Bellman-Ford, A*, and Floyd-Warshall pathfinding;
- filtering, mapping, reversal, neighborhoods, complement, composition, sum,
  difference, intersection, and symmetric difference; and
- Mermaid projection.

This breadth is useful as a catalog. It should not be mistaken for one
coherent Petrus ownership boundary: topology storage, mutation, algorithms,
pathfinding, graph algebra, and rendering all live in one large module.

## Model comparison

| Concern | Effect Graph | Petrus `Net` | Consequence |
| --- | --- | --- | --- |
| Purpose | General relationships between indexed nodes and edges | Canonical executable Petri-net definition | Graph is supporting machinery, not a replacement model |
| Node identity | Allocated graph-local `NodeIndex` | Authored/scoped `NetPath` and typed canonical `NetUri` | Dense indexes may be disposable internals only |
| Edge identity | Allocated graph-local `EdgeIndex` | Ordered semantic `Arc` occurrence with endpoint-derived URI | Preserve occurrences and recover canonical identity in every result |
| Endpoint shape | Arbitrary endpoints; self-loops allowed | Strict place↔transition bipartite shape | Bipartiteness remains a constructor invariant, not an analysis result |
| Direction | Graph-wide directed or undirected kind | Direction is always present and semantically meaningful | No undirected canonical-net mode |
| Multiplicity | Parallel edges are first-class | Parallel arcs can differ by mode, weight, color, or filter | Never coalesce by equal payload or endpoints |
| Edge data | Opaque generic payload | Input/output inscriptions used by enabledness and routing | Generic edge algorithms cannot interpret arc meaning |
| Mutability | Immutable value plus scoped mutable full copies | Authored DSL lowers snapshots into a conceptually immutable canonical net | Learn from ownership; do not add canonical mutation |
| Equality | Includes numeric IDs and next-allocation counters | Canonical definition and identity should not depend on discarded allocator history | Do not import Effect equality semantics |
| Algorithms | Generic topology and weighted paths | T1 validation, T2 structural Petri analysis, T3 bounded behavior | Use generic algorithms only inside explicitly named projections |
| Rendering | Generic Mermaid graph | Domain Graphviz from canonical `Net`, presentation-only | Keep the existing renderer boundary |

## What Petrus is already doing better for this domain

### 1. Identity expresses the modeled system

`NetPath` is an immutable authored/scoped address and `NetUri` names typed
places, transitions, declarations, and directed arc occurrences
([schema](../../../../src/petrus/impetus/petrinet/schema.py#L55-L156)). Effect's
indexes are useful process-local handles, but they do not survive reconstruction
as semantic identity. Even Petrus's generated parallel-arc occurrence is based
on endpoints and pair-local semantic order rather than unrelated allocation
history.

### 2. Invalid graph shapes cannot enter the canonical model

Petrus validates unique node paths, place/transition disjointness, strict
bipartite endpoints, output-arc restrictions, source-transition restrictions,
and several semantic livelock/timer mistakes at one construction boundary
([`Net`](../../../../src/petrus/impetus/petrinet/schema.py#L396-L550)). A generic
`isBipartite()` boolean after construction would be a weaker contract.

### 3. Arcs are declarations, not generic weighted edges

An input arc's consume/read/inhibit mode, selection weight, color, and filter
change enabledness. Output arcs govern token routing
([`Arc`](../../../../src/petrus/impetus/petrinet/schema.py#L242-L309),
[`_survey`](../../../../src/petrus/impetus/petrinet/enabledness.py#L254-L329),
[`complete_firing`](../../../../src/petrus/impetus/petrinet/firing.py#L55-L78)).
Effect sees only `E` and an optional caller-supplied numeric cost function.

This distinction prevents a particularly dangerous false analogy: Petrus
`Arc.weight` is selection cardinality on input arcs, not a shortest-path cost,
and current output routing does not interpret it as production multiplicity.

### 4. Authored composition has a canonical lowering boundary

Petrus DSL specifications stamp reusable scopes and compile into one flattened
canonical `Net`; the language-neutral definition projection has a separate
deeply immutable wire model. Effect's mutable graph editor does not provide
composition identity, source declarations, executable binding separation, or
canonical interchange.

### 5. Execution and presentation do not redefine topology

Enabledness and firing consume semantic declarations. Graphviz is a pure,
deterministic projection from canonical `Net`
([renderer](../../../../src/petrus/impetus/petrinet/dot.py#L259-L305)). This
already realizes the strongest part of Effect's exporter design while keeping
presentation outside the model.

## Copy as a pattern

These patterns generalize without changing what a Petri net means.

### 1. Edge-occurrence table plus forward and reverse incidence

Effect's separate edge table and two adjacency indexes are the right generic
multigraph representation. For Petrus, the equivalent future analysis index
would use dense node numbers and global arc positions internally while retaining
lossless maps back to `NetPath` and `NetUri`.

Do this only when a real T2, Arx inspection, or measured runtime consumer needs
repeated bidirectional topology queries. Current `Net` already indexes
transition inputs and outputs; adding a generalized index before a consumer
exists would duplicate truth without value.

### 2. Scoped mutability with a hard freeze boundary

Effect clones an immutable graph into a mutable handle, invalidates the handle
when finalized, and finalizes even if the callback fails
([mutation](https://github.com/Effect-TS/effect/blob/6eebd0a618308a91f95947bae6e0fb206ae3939d/packages/effect/src/Graph.ts#L596-L710)).
Its tests explicitly cover use-after-finalize and exception cleanup
([tests](https://github.com/Effect-TS/effect/blob/6eebd0a618308a91f95947bae6e0fb206ae3939d/packages/effect/test/Graph.test.ts#L981-L1047)).

Petrus already follows the architectural version: mutable authoring belongs in
the DSL and canonical `Net` is the frozen output. Copy the enforcement
discipline, not Effect's mandatory full copy on both entry and exit.

### 3. Iterative, stack-safe topology algorithms

Effect implements traversal, cycle, and SCC work with explicit stacks rather
than recursive depth
([SCC and components](https://github.com/Effect-TS/effect/blob/6eebd0a618308a91f95947bae6e0fb206ae3939d/packages/effect/src/Graph.ts#L3633-L3958)).
Any Petrus traversal over user-authored nets should do the same. Python BFS
should use `collections.deque`, not copy Effect's JavaScript `Array.shift()`
queues.

### 4. Explicit traversal dimensions

Starts, outgoing/incoming/ignore-direction traversal, and bounded radius are
good orthogonal controls
([walkers](https://github.com/Effect-TS/effect/blob/6eebd0a618308a91f95947bae6e0fb206ae3939d/packages/effect/src/Graph.ts#L5080-L5338)).
Petrus should express them in domain vocabulary—preset, postset, ancestors,
descendants, structural neighborhood—and return canonical paths and arc
occurrences rather than generated indexes.

### 5. Adversarial graph tests

Effect's strongest transferable asset is test discipline: empty and
disconnected graphs, parallel edges, loops, stale mutable handles, reversed
orientation, invalid weights, deterministic ties, negative cycles, and deep
stack-safety cases are all explicit. Petrus analysis should add the
domain-specific matrix: strict alternation, parallel equal arc occurrences,
read/inhibit/consume distinctions, deterministic witnesses, permutation
independence where promised, projection transfer labels, and paths that retain
both node and arc identity.

## Adapt behind a Petrus semantic façade

### 1. Structural reachability and neighborhoods

Directed/undirected traversal can support inspector neighborhoods, impact
views, and structural “can topology connect A to B?” questions. Every result
must say that this is **topological reachability**, never marking reachability
or an executable firing sequence.

### 2. Weak components, SCCs, cycle witnesses, and condensation

These algorithms can identify disconnected islands and feedback regions on the
uncolored skeleton. They fit T2 as diagnostics, with limits:

- disconnected components may be legal;
- a structural cycle says nothing by itself about liveness;
- SCC membership is not a proof that transitions can keep firing; and
- acyclicity is not deadlock freedom or workflow soundness.

Topological ordering is useful only on an explicitly acyclic projection or on
the SCC condensation graph. Cycles are ordinary Petri-net structure, not a
validation failure.

### 3. Read-only projected views

One future internal boundary could look like this:

```text
canonical Net
    │
    ├── full bipartite occurrence projection ── traversal / SCC / components
    ├── place dependency projection ─────────── domain-specific T2 analysis
    ├── transition dependency projection ────── inspection / explanation
    └── incidence representation ────────────── invariants / state equations
             │
             └── report: canonical identities + projection + transfer label
```

The projection contract must name:

1. whether direction is respected;
2. whether parallel arc occurrences are preserved;
3. how consume, read, and inhibit arcs are represented;
4. whether nodes are places, transitions, or both;
5. whether results concern static structure or markings; and
6. which conclusions transfer to the real colored net.

This is the concrete point where Effect ideas fit Petrus's ratified T2 rule:
every verdict carries a transfer label, and analysis never gates expressiveness.

### 4. Deterministic witnesses

Effect preserves insertion order and uses discovery sequence to break equal
path priorities
([iteration](https://github.com/Effect-TS/effect/blob/6eebd0a618308a91f95947bae6e0fb206ae3939d/packages/effect/src/Graph.ts#L5636-L5729),
[path ties](https://github.com/Effect-TS/effect/blob/6eebd0a618308a91f95947bae6e0fb206ae3939d/packages/effect/test/Graph.test.ts#L3112-L3131)).
Petrus should go further where reproducibility crosses builds: use documented
canonical path/URI ordering rather than accidental construction order, and
state whether components are ordered or mathematically unordered.

### 5. Transformations only with an identity contract

Filtering to an induced diagnostic subnet may be useful. It must preserve
canonical identity or return an explicit mapping. Effect's in-place
filter/map/reverse operations preserve surviving numeric indexes, while many
set and neighborhood operations allocate a fresh graph and silently renumber
everything
([transformations](https://github.com/Effect-TS/effect/blob/6eebd0a618308a91f95947bae6e0fb206ae3939d/packages/effect/src/Graph.ts#L1838-L2212)).
That distinction must be explicit in any Petrus equivalent.

## Do not copy

### 1. Do not make generic Graph canonical or add Effect as a dependency

The retained libpetri decision already sets the correct rule: dense indexes,
reverse dependencies, and specializations may be disposable derivatives of
canonical `Net`; they never become semantic truth or durable state. Effect is
even less suitable as a substrate because it has no Petri semantics, History,
marking, binding, firing, Activity custody, or language-neutral definition.

### 2. Do not replace canonical identity with allocation history

Effect graph equality includes node/edge IDs and the *next allocation
counters*. Two currently empty graphs can therefore be unequal because one
previously contained a deleted node
([equality](https://github.com/Effect-TS/effect/blob/6eebd0a618308a91f95947bae6e0fb206ae3939d/packages/effect/src/Graph.ts#L322-L397),
[tests](https://github.com/Effect-TS/effect/blob/6eebd0a618308a91f95947bae6e0fb206ae3939d/packages/effect/test/Graph.test.ts#L170-L235)).
That may be exact representation equality, but it is surprising value
semantics and wrong for canonical Petrus definition equality.

If Petrus needs equality families, name them: exact definition equality,
canonical semantic equality, or an explicit isomorphism relation. Do not let a
discarded dense allocator decide any of them.

### 3. Do not import generic graph set algebra into net composition

Effect's sum/intersection/difference family projects identity from node and edge
payloads. Duplicate node identities can coalesce, redirected edges can become
self-loops, and equal parallel edges can collapse or all disappear
([set identity](https://github.com/Effect-TS/effect/blob/6eebd0a618308a91f95947bae6e0fb206ae3939d/packages/effect/src/Graph.ts#L764-L878),
[multiplicity tests](https://github.com/Effect-TS/effect/blob/6eebd0a618308a91f95947bae6e0fb206ae3939d/packages/effect/test/Graph.test.ts#L409-L494)).

Those are valid generic set choices and invalid canonical Petri composition.
Petrus scoped stamping must keep exhaustive endpoint shape, semantic arc
multiplicity, declaration identity, and implementation separation. A future
definition diff can be inspired by explicit identity projection without
becoming executable “graph union.”

### 4. Do not conflate graph algorithms with Petri behavior

- Static graph reachability is not marking reachability.
- A shortest node path is not a legal firing sequence.
- SCC membership is not liveness.
- DAG status is not deadlock freedom or soundness.
- Weak connectivity is not completeness.
- Generic bipartiteness says nothing about arc modes or firing semantics.

T2 additionally needs Petri-specific incidence, invariants, state-equation
refutations, siphons/traps, conflict sites, reductions, and subclass results.
Effect supplies none of those. T3 explores states whose nodes are markings;
the nodes of canonical `Net` are not that state graph.

### 5. Do not use arc declarations as path costs

Effect pathfinding is technically broad but not a present Petrus need. Its
`PathResult.costs` actually contains edge payloads rather than evaluated
numeric costs, Dijkstra and A* validate every graph edge even when unreachable,
and A* requires a consistent heuristic without validating it or reopening
closed nodes
([path result](https://github.com/Effect-TS/effect/blob/6eebd0a618308a91f95947bae6e0fb206ae3939d/packages/effect/src/Graph.ts#L3964-L3995),
[Dijkstra](https://github.com/Effect-TS/effect/blob/6eebd0a618308a91f95947bae6e0fb206ae3939d/packages/effect/src/Graph.ts#L4070-L4150),
[A*](https://github.com/Effect-TS/effect/blob/6eebd0a618308a91f95947bae6e0fb206ae3939d/packages/effect/src/Graph.ts#L4463-L4628)).

If an inspector later needs a shortest structural explanation path, unweighted
BFS is probably enough. A weighted path story must define a new diagnostic cost
explicitly, preserve arc occurrence identities in the result, and keep that
cost separate from `Arc.weight` and arc payload.

### 6. Do not copy inconsistent missing-node contracts

Effect mixes optional lookup, false, empty neighbors, silent mutation no-ops,
and thrown `GraphError` depending on the operation
([lookup and neighbors](https://github.com/Effect-TS/effect/blob/6eebd0a618308a91f95947bae6e0fb206ae3939d/packages/effect/src/Graph.ts#L1518-L1559),
[neighbor behavior](https://github.com/Effect-TS/effect/blob/6eebd0a618308a91f95947bae6e0fb206ae3939d/packages/effect/src/Graph.ts#L2623-L2767)).
An unknown node and a known isolated node should not become indistinguishable
by accident. Petrus should define one missing-identity policy per operation
family and test it.

### 7. Do not copy the monolith or Effect-specific API machinery

Effect's `Option`, `Scope`, structural `Equal`/`Hash`, `dual` data-first/data-last
calls, pipeability, TypeScript variance, and one 5,832-line module fit its own
ecosystem. Petrus should keep canonical schema, topology projection, traversal,
T2 analysis, bounded behavior, and presentation in distinct owners. Add only
the algorithms a Petrus consumer proves it needs.

## Petrus gaps exposed by the comparison

### 1. Canonical `Net` is conceptually, but not mechanically, immutable

The `Net` documentation says “built and validated once, then immutable,” and
its maps are read-only views. The object itself is not frozen: public
`completion`, `name`, `places`, `transitions`, and `arcs` attributes can be
reassigned, and private list-valued incidence indexes remain mutable
([construction](../../../../src/petrus/impetus/petrinet/schema.py#L396-L510)).
Current strict-projection tests deliberately exploit reassignment to inject an
invalid value
([observation test](../../../../tests/petrus/engine/test_observation.py#L359-L363),
[definition test](../../../../tests/petrus/impetus/test_net_definition.py#L257-L261)).

The direct probe confirmed that `net.arcs = ()` changes `repr(net)` from
`Net(1p, 1t, 1a)` to `Net(1p, 1t, 0a)`. Before any cached analysis or compiled
projection relies on immutability, Petrus should either enforce the stated
contract after construction or explicitly weaken the claim. Enforcing it is
the recommended maintenance direction; malformed-boundary tests can construct
adversarial values without making normal canonical values mutable.

### 2. `is_source()` conflates a missing transition with a source transition

`inputs()` and `outputs()` return empty tuples for unknown paths, and
`is_source()` is implemented as absence from the input index
([queries](../../../../src/petrus/impetus/petrinet/schema.py#L552-L586)). The
probe confirmed `net.is_source(NetPath("missing")) is True`.

All current runtime callers appear to supply known transitions, so this is not
evidence of a runtime failure. It is still a misleading public semantic
judgment. A bounded maintenance change should make unknown and known-isolated
identity observably distinct—preferably by validating that the path names a
transition—before expanding the topology-query surface.

### 3. Current indexes are runtime-specific, not a reusable topology view

`Net` indexes only arcs entering and leaving transitions and returns fresh tuple
copies on query. T2 and inspection will eventually want node-kind-neutral
forward/reverse incidence and arc occurrence identity. That pressure should
create one read-only derived projection, not more ad hoc scans and not broader
mutation inside `Net`.

No current evidence justifies a compiled execution plan. The simulation
profile's repeated whole-arc incidence scans illustrate a possible future
consumer, but the retained decision correctly requires profiling before dense
runtime compilation.

## Recommended sequence

1. **Adopt no dependency and create no generic public Graph.** Record Effect as
   prior art only.
2. **Harden the existing canonical boundary as Maintenance.** Mechanically
   freeze `Net` after construction, freeze its internal indexes, and make
   missing-path query behavior explicit. This is valuable without any analysis
   roadmap expansion.
3. **When a T2 or inspector story is pulled, introduce the smallest read-only
   topology projection it needs.** Use disposable dense IDs and arc positions
   internally; every result recovers `NetPath`/`NetUri` and names projection,
   direction, multiplicity, arc-mode treatment, and transfer label.
4. **Implement only the first proven structural kernels.** Iterative traversal,
   weak components, SCC/condensation, and structural path witnesses are the
   likely small set. Domain-specific T2 incidence and invariant machinery
   remains a separate owner.
5. **Defer pathfinding, graph algebra, generalized transformations, Mermaid,
   and compiled runtime topology.** Pull each only for a concrete consumer,
   explicit semantics, and a testable benefit.

## Verification

- `[D]` `git ls-remote https://github.com/Effect-TS/effect.git HEAD
  refs/heads/main` pinned the researched source at
  `6eebd0a618308a91f95947bae6e0fb206ae3939d`.
- `[E]` A disposable Python probe constructed a one-place, one-transition,
  one-arc `Net`, confirmed that a missing path is classified as a source, and
  confirmed that public `arcs` and `name` can be reassigned after validation.
- `[E]` `UV_FROZEN=1 uv run pytest -q
  tests/petrus/impetus/petrinet/test_schema.py
  tests/petrus/impetus/dsl/test_petrinet_dsl.py
  tests/petrus/impetus/petrinet/test_petrinet_dot.py
  tests/project/test_exploration_identity.py` passed all 139 tests in 1.70
  seconds.
- `[E]` Every local relative Markdown link in this artifact resolves, and
  `git diff --check` reports no whitespace errors.

## Disposition

The inquiry is complete without a Delivery candidate. Effect confirms the
value of indexed bidirectional incidence, scoped mutation, stack-safe
traversal, explicit traversal controls, and adversarial multigraph tests. It
does not justify a Graph dependency, generic canonical model, broad algorithm
surface, or roadmap expansion.

The only present action recommended with high confidence is bounded canonical
`Net` hardening. The topology projection and structural kernels remain design
guidance for the already-ratified T2/inspection boundary when a concrete story
pulls them.
