---
artifact: exploration
code: ES-059
title: MIT dataflow, Petri nets, and functional authoring for Petrus
status: Completed
status_reason: >-
  The inquiry is answered: the MIT dataflow-machine history does not make
  Petri nets a dead end for Petrus, and the executed experiments support
  "the authoring surface is too low-level" over "the Petri model is wrong".
  The typed functional vertical slice is promising (all fourteen completion
  conditions passed; canonical execution, replay, resume, byte-stable
  lowering, and full source-to-History attribution held). The
  decision-structure comparisons closed with verdicts: the single-transition
  algebraic case table is promising, the one-guarded-transition-per-rung net
  is mixed, and the inscription net is promising with priced costs. The
  remaining open question — what notation delivers the expressive authoring
  surface — is handed to ES-060 as a dedicated design story. ES-056 later
  promoted separately as CV20, carrying this evidence into CV20.DS2; no kernel
  rewrite or Haskell migration follows from this story.
opened: 2026-08-26
updated: 2026-09-08
related:
  - ES-056
  - ES-060
  - CV20.DS2
  - docs/product/principles.md
  - docs/project/decisions/records/2026-08-13T1740Z-progressive-disclosure-preserves-runtime-power.md
source_context:
  - Petrus commit a5badb98aaa0d891645a802f2a4924b4f76e1cbb
  - Hamsterdan commit a14c77825d9616fe0e3f9102cd3476a597fc7da7
research_sources:
  - https://doi.org/10.1007/3-540-06859-7_145
  - https://doi.org/10.1145/642089.642111
  - https://csg.csail.mit.edu/CSGArchives/memos.html
  - https://csg.csail.mit.edu/CSGArchives/memos/Memo-278.pdf
  - https://csg.csail.mit.edu/CSGArchives/memos/Memo-292.pdf
  - https://csg.csail.mit.edu/CSGArchives/memos/Memo-306.pdf
  - https://csg.csail.mit.edu/CSGArchives/memos/Memo-316.pdf
  - https://csg.csail.mit.edu/CSGArchives/memos/Memo-330.pdf
  - https://doi.org/10.1109/12.48862
  - https://doi.org/10.1145/27633.28055
  - https://engineering.unt.edu/cse/research/labs/csrl/files/IEEE-TSE-1987.pdf
  - https://doi.org/10.1002/spe.4380090105
  - https://www.cs.tufts.edu/comp/150FP/archive/simon-peyton-jones/spineless-jfp.pdf
  - https://arxiv.org/abs/1808.05415
  - https://doi.org/10.1145/3323923
promotes_to: []
promoted_to: []
promoted_at:
---

# 1 Dataflow history and functional authoring

## 1a Conclusion and handoff

The completed experiments support a typed, compositional authoring layer over
Petrus's existing Net and History. They do not establish a production authoring
API. [ES-060](../es-060-expressive-authoring-notation-design/index.md) owns the
paused notation design; [CV20.DS2](../../roadmap/cv20-approachable-petrus/cv20-ds2-expressive-flow-authoring.md)
owns the promoted delivery scope. The
[progressive-disclosure decision](../../decisions/records/2026-08-13T1740Z-progressive-disclosure-preserves-runtime-power.md)
preserves access to lower-level runtime capabilities.

This inquiry closed on 2026-08-26, with later experiment verdicts retained
below. ES-056 subsequently promoted to CV20. That promotion did not complete
its AX28 or AX29 evidence gates. No kernel rewrite or Haskell migration was
accepted here.

## 1b Question and research baseline

The inquiry asked which MIT dataflow-computer project matched the Navigator's
description, why that architecture did not replace conventional computers, and
what Petrus should learn from it and from functional-language implementation.
Sources were checked on 2026-08-26; the exact URLs and application revisions
remain in frontmatter. `[D]` denotes a checked primary source, `[E]` observed
code or executed evidence, and `[I]` this exploration's inference.

The likely reference is the MIT Computation Structures Group's lineage from
Dennis's static dataflow through tagged-token machines, Monsoon, and P-RISC.
Identifying the reported project is an inference. `[I]` Those systems pursued
instruction-grain parallel computation; Petrus coordinates durable domain
work on conventional Python, operating systems, stores, and Workers. `[D/E]`

| Reading | Finding retained for Petrus |
| --- | --- |
| [Dennis and Misunas, 1975](https://doi.org/10.1145/642089.642111) | The original goal was direct execution of a Fortran-level dataflow form on specialized hardware. `[D]` |
| [Veen, 1986](https://doi.org/10.1145/27633.28055) | Token matching, metadata, sparse memory occupancy, locality, and resource throttling made fine-grain parallelism expensive. `[D]` |
| [The Price of Asynchronous Parallelism](https://csg.csail.mit.edu/CSGArchives/memos/Memo-278.pdf) | Dynamic instruction counts were commonly two to three times equivalent IBM 370 programs. These historical measurements are not Petrus benchmarks. `[D]` |
| [MIT tagged-token architecture](https://doi.org/10.1109/12.48862) | Id compilation had to manage tags, I-structures, placement, and bounded parallelism. Available concurrency still needed resource control. `[D]` |
| [Monsoon](https://csg.csail.mit.edu/CSGArchives/memos/Memo-306.pdf) | Compiler-assigned activation-frame slots replaced costly global matching. `[D]` |
| [P-RISC](https://csg.csail.mit.edu/CSGArchives/memos/Memo-292.pdf), [evolution](https://csg.csail.mit.edu/CSGArchives/memos/Memo-316.pdf), [multithreading](https://csg.csail.mit.edu/CSGArchives/memos/Memo-330.pdf) | Later designs retained synchronization and split-phase operations around efficient sequential threads. `[D]` |
| [Turner](https://doi.org/10.1002/spe.4380090105), [STG](https://www.cs.tufts.edu/comp/150FP/archive/simon-peyton-jones/spineless-jfp.pdf) | A high-level functional language can lower through explicit intermediate forms to conventional hardware. Raw SKI would discard useful domain names and hierarchy. The Petrus application is an inference. `[D/I]` |
| [Kavi, Buckles, and Bhat](https://engineering.unt.edu/cse/research/labs/csrl/files/IEEE-TSE-1987.pdf) | The dataflow/Petri-net mapping covers an uninterpreted, unit-disjunctive, unit-selective class. The timed free-choice result adds a one-input condition for selective actors. It does not equate arbitrary colored nets and dataflow graphs. `[D]` |
| [Open Petri Nets](https://arxiv.org/abs/1808.05415) | Input/output places support compositional semantics. Typed ports are a design lead, not a requirement to adopt the paper's formalism. `[D/I]` |

Availability-driven dataflow fires when inputs exist. Demand-driven lazy
reduction evaluates a result when needed. Petrus's host and selection policy
choose the next enabled durable action. These scheduling rules remain distinct.
The useful functional techniques are algebraic data types, pure decisions and
folds, explicit effects, composition laws, and property tests. `[D/I]`

## 1c The application pressure

At the pinned Hamsterdan revision, `readiness/net_v5` had 4,403 Python lines
across 13 files and nine concern loops. Its
[ownership review](https://github.com/henriquebastos/hamsterdan/blob/a14c77825d9616fe0e3f9102cd3476a597fc7da7/docs/project/exploration/es9-human-codebase-ownership/index.md)
and [composition inquiry](https://github.com/henriquebastos/hamsterdan/blob/a14c77825d9616fe0e3f9102cd3476a597fc7da7/docs/project/exploration/es10-composable-hamsterdan-architecture/index.md)
found useful runtime boundaries alongside high authoring and navigation costs.
Those counts describe the inspected revision. `[E/D]`

The experiment therefore tested one process: admit a CI observation for the
exact branch head, publish when clean, request a rerun on failure, request
repair if failure persists, treat branch movement as a new generation, and
resume from History. It compared explanation, source attribution, and change
locality as well as topology size.

```mermaid
flowchart LR
    source[Typed application source] --> net[Canonical Net]
    net --> engine[Engine and History]
    source -. source map .-> engine
```

The source-map arrow is an experiment result and authoring requirement. This
diagram does not claim that the prototype is a supported frontend.

## 1d Executed experiments

The [original experiment plan](experiment-plan.md) owns the detailed acceptance
conditions. Prototype code, tests, goldens, and reports remain in this story.
None was removed or reclassified as production code by Memory Closure.

| Experiment | Verdict and evidence | Cost or unresolved limit |
| --- | --- | --- |
| [Typed flow vertical slice](experiments/typed-flow-vertical-slice/report.md), [run instructions](experiments/typed-flow-vertical-slice/README.md) | Promising. All fourteen conditions passed. Repeated lowering produced the same Net v3 bytes: 14 places, 9 transitions, 28 arcs. Real Engine execution, JSONL replay, scoped generations, and interrupted resume preserved canonical History; all 147 facts mapped to source blocks. `[E]` | Absorbed decisions lacked a named durable firing. An inhibitor publication gate needed explicit low-level descent. |
| [Algebraic decision table](experiments/algebraic-decision-table/report.md) | Promising. An ordered first-match table retained the same single transition, Net bytes, and History. A 10,368-point sweep matched `route_ci`; `otherwise` checked totality and each rung had attribution. `[E]` | Sequential state dependence still required the shared `normalize` classify/commit step. |
| [Guarded decision net](experiments/guarded-decision-net/report.md) | Mixed. Named absorption became visible as a durable firing. `[E]` | 9 to 13 transitions, 28 to 40 arcs, about tenfold guard evaluation. Overlapping guards delegated business choice to Engine selection; missing rungs stranded observations. A 576-point grid tested exclusivity/exhaustiveness without proving them generally. |
| [Inscription net](experiments/inscription-net/report.md) | Promising with costs. Seven combinators, eleven pure token methods, ten derived transitions, fifty arcs, and eight guards preserved fixture behavior. One firing per observation used 108 History records instead of 147. `[E]` | Behavior equivalence was deliberate; byte equivalence was not claimed. See the limits below. |

The inscription prototype's limits are material to any follow-up:

1. Ordered choice needs a compile-time cover proof over Boolean latch occupancy.
   A naive NOT chain is unsound because guards cannot test absence. Token
   multiplicity lies outside that proof.
2. Latches encode the rung budget and reset with the scope, but cannot encode
   a budget keyed by `(lineage, fingerprint)`. Dropping that key is a known
   behavioral divergence outside the fixture. Head identity, watermark order,
   and operation IDs remained data.
3. The prototype carries folded state while an Activity is in flight and
   evaluates eighteen predicates per decision. A terminal Activity failure
   destroys the folded watermark and blocks the decision group. Promotion must
   address that failure through `FailureProjectingActivityHandler`.
4. One CEL arc filter reaches canonical Net bytes. CEL guards remain blocked
   by dotted-place addressing, as the experiment test records.

## 1e Meaning to carry forward

Use a durable transition for a domain commitment, synchronization, custody or
resource fence, external-effect outcome, timer or human wait, or a choice that
belongs in the process record. Ordinary parsing, arithmetic, mapping, and
formatting can remain local pure code unless their results are durable facts.
This is the exploration's grain recommendation. `[I]`

For authoring, the evidence favors enriching one durable decision's source
with a case table. Multiplying transitions exposes more history but can also
change choice semantics and cost. Preserve typed composition, stable lowering,
authored hierarchy, error locality, and explicit low-level descent in the next
comparison. Bounded tests of these properties do not prove exhaustive
reachability of arbitrary colored nets.

## 1f Closure and next movement

The research and four experiment verdicts are complete. The remaining syntax
question belongs to paused ES-060; current delivery status belongs to CV20.DS2.
Resume there instead of repeating the historical inquiry or these experiments.
Revisit a verdict if a new notation changes its lowering, failure, identity,
multiplicity, or source-attribution assumptions. Historical measurements remain
in the linked reports; this closure did not rerun the prototypes.
