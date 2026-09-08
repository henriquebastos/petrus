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

# 1 Effect Graph prior art

## 1a Conclusion and scope

Effect supplies useful graph storage, traversal, and testing patterns. The
comparison completed without a Delivery candidate or dependency adoption.
Petrus keeps canonical `Net` identity, semantic arc occurrences, and Petri
execution. A generic graph can be a disposable projection when a concrete
analysis or inspection consumer needs it.

The [analysis decision](../../decisions/records/2026-07-08T1541Z-analysis-three-tier-commitment.md)
owns the validation, structural-analysis, and bounded-behavior tiers. The
[libpetri decision](../../decisions/records/2026-07-29T2303Z-libpetri-is-prior-art-not-runtime-substrate.md)
already establishes the prior-art boundary. This exploration adds evidence and
maintenance recommendations, without accepting implementation work.

## 1b Research baseline

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
- `[E]` Petrus observations come from the then-current canonical schema, DSL,
  definition projection, enabledness, firing, DOT renderer, focused tests, and
  retained decisions. One disposable runtime probe tested the public
  immutability and missing-node query claims directly.
- `[R]` The retained libpetri and analysis decisions are authoritative over
  any new architectural attraction created by this comparison.


## 1c Patterns worth retaining

| Pattern in the pinned source | Petrus application and limit |
| --- | --- |
| Separate edge table and forward/reverse incidence | Use dense IDs and arc positions internally only when repeated queries justify an index. Results retain `NetPath` and `NetUri`; equal parallel arcs remain distinct occurrences. |
| Scoped mutable copy with handle invalidation | Keep mutation in authoring and enforce the canonical freeze boundary. Avoid mandatory full copies unless needed. |
| Iterative DFS/BFS, SCC, components | Use explicit stacks and Python `deque` for deep authored nets. Return deterministic witnesses under documented ordering. |
| Direction and radius controls | Name the projection, node kinds, direction, arc modes, multiplicity, and whether conclusions transfer to the colored net. |
| Adversarial multigraph tests | Cover empty/disconnected graphs, equal parallel arcs, missing identities, deep traversal, deterministic ties, and stale mutable handles. Add consume/read/inhibit distinctions. |

Effect allocates numeric node/edge identities; its equality includes allocation
counters. Petrus identities describe authored/scoped definitions. Effect's set
operations can merge nodes or parallel edges and renumber results, so they
cannot become canonical net composition. A diagnostic transformation must
preserve identity or return an explicit mapping.

Topology answers structural questions. A graph path does not establish an
executable firing sequence; SCCs do not prove liveness, and acyclicity does not
prove deadlock freedom. Cycles and disconnected components can be legal nets.
T2 Petri analysis still needs its own incidence, invariant, siphon/trap,
state-equation, and subclass reasoning; T3 explores markings rather than the
nodes of the definition.

`Arc.weight` selects input cardinality, not path cost or output multiplicity.
A later shortest-explanation feature must define its own diagnostic cost and
preserve arc identity. Effect's `PathResult.costs` holds payloads; Dijkstra/A*
validate even unreachable edges, and A* assumes a consistent heuristic without
reopening closed nodes. Those API choices are cautions, not proposed Petrus
behavior. Missing and known-isolated identities also need distinct contracts.

## 1d Historical maintenance findings

The August 2026 probe found two concrete issues in
[schema.py](../../../../src/petrus/impetus/petrinet/schema.py):

1. Canonical `Net` claimed immutability while public attributes remained
   assignable and private incidence lists mutable. Assigning `net.arcs = ()`
   changed its representation from one arc to none. Some strict-projection tests
   used reassignment to construct malformed values.
2. `net.is_source(NetPath("missing"))` returned `True` because absence from the
   input index also described a source transition. Runtime callers appeared to
   pass known transitions, so the probe did not establish a runtime failure.

The recommendation was bounded hardening of construction and missing-path
queries before relying on cached topology. It remains a recommendation in this
completed exploration. Recheck the current code and tests before accepting a
maintenance change. New analysis indexes require a real consumer; compiled
runtime topology additionally requires profiling.

## 1e Historical verification

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


## 1f Revisit conditions

Resume these findings when a maintenance task addresses canonical immutability
or missing-path queries, or when an accepted T2/Arx story needs repeated topology
queries. Introduce only the projection and algorithms that consumer needs.
Generic Graph APIs, broad graph algebra, weighted pathfinding, new rendering,
and dense runtime compilation remain uncommitted possibilities. This closure
did not rerun the historical probe or promote its recommendations.
