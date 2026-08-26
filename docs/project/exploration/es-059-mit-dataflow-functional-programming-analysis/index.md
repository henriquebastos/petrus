---
artifact: exploration
code: ES-059
title: MIT dataflow, Petri nets, and functional authoring for Petrus
status: Thickening
status_reason: >-
  Primary MIT dataflow papers, contemporary surveys, the formal Petri-net
  comparison, functional-language implementation work, and current Petrus and
  Hamsterdan source establish that Petrus is not repeating the failed
  general-purpose dataflow-machine bet. The Navigator-authorized typed
  functional vertical-slice experiment has now been executed inside ES-059
  and classified promising: all fourteen mechanical completion conditions
  passed, canonical execution, replay, resume, byte-stable lowering, and
  full source-to-History attribution held, and the evidence supports "the
  authoring surface is too low-level" over "the Petri model is wrong". Two
  bounded follow-up experiments compared decision-structure spellings: the
  single-transition algebraic case table is promising (byte-identical
  canonical IR and History under a richer source), while the
  one-guarded-transition-per-rung net is mixed (durable branch visibility
  bought with unprovable exclusivity obligations and topology growth).
  Promotion remains a Navigator decision; no kernel rewrite, Haskell
  migration, or roadmap change follows from the experiments themselves.
opened: 2026-08-26
updated: 2026-08-26
related:
  - ES-056
  - docs/product/principles.md
  - docs/project/decisions/records/2026-08-13T1740Z-progressive-disclosure-preserves-runtime-power.md
source_context:
  - Petrus commit ddce00e180be37d0be5138b3987d891a18f968d3
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

# MIT dataflow, Petri nets, and functional authoring for Petrus

## Inquiry

Which old MIT dataflow-computer project most closely matches the reported
description, what did it actually attempt, why did general-purpose dataflow
machines not displace conventional computers, and does that history make Petri
nets a dead end for Petrus?

The inquiry also asks whether the Navigator's pull toward Haskell, functional
programming, graph reduction, and SKI combinators exposes a useful design
direction, and how current Hamsterdan developer-experience friction should
change the Petrus recommendation.

Sources were checked on 2026-08-26. Claims use Petrus's evidence grades: `[E]`
executable or directly inspected local evidence, `[D]` authoritative paper,
source, or documentation, `[R]` reported but not independently established, and
`[X]` refuted or materially narrowed by checked evidence.

## Executive verdict

**Petri nets are not the dead end exposed by MIT's dataflow-machine history.**
The failed economic bet was narrower: make instruction-grain data-dependency
firing the general-purpose computer's execution model, with custom hardware
matching operand tokens and discovering enormous implicit parallelism at run
time. `[D]`

Petrus uses a related local firing rule for a different job and at a radically
different grain. A transition should represent a durable domain commitment,
synchronization boundary, resource-custody change, wait, or external-effect
gate. Conventional Python, operating systems, databases, networks, and Workers
still perform the computation. Petrus does not replace registers, caches,
instruction sequencing, or the memory hierarchy. `[E]`

The MIT history does expose one serious Petrus risk:

> **A graph can be an excellent canonical execution model and a poor primary
> source language.**

Hamsterdan makes that warning concrete. Its current V5 process honestly exposes
nine concern loops and durable typed coordination, but the corresponding
`readiness/net_v5` package is 4,403 Python lines across 13 files. `[E]` The
problem is not that the behavior should become hidden control flow. The problem
is that direct low-level place/transition/arc authoring makes honest durable
semantics expensive to write, navigate, and explain.

The recommended direction is therefore:

1. keep the Petri Net and append-only History as Petrus's canonical runtime
   semantics;
2. keep process transitions coarse enough to be worth recording;
3. build a typed, functional, compositional authoring layer that lowers
   deterministically to canonical, inspectable topology;
4. preserve source maps, authored hierarchy, and deliberate low-level descent;
5. use Haskell and functional programming as design instruments, not as a
   reason to rewrite the Python runtime or expose raw SKI; and
6. test the proposition on one Hamsterdan vertical slice before committing to
   a language or broad authoring API.

This reinforces [ES-056](../es-056-progressive-disclosure-developer-experience/index.md)
and the existing
[progressive-disclosure decision](../../decisions/records/2026-08-13T1740Z-progressive-disclosure-preserves-runtime-power.md).
It does not promote that candidate, alter the current roadmap, or justify a
kernel change.

## The likely MIT project

The description most likely refers not to one isolated machine but to the MIT
Project MAC/Laboratory for Computer Science **Computation Structures Group
dataflow lineage**. `[D]` It has three useful phases:

1. **Dennis's static/basic dataflow work.** Jack Dennis's
   [first dataflow procedure language](https://doi.org/10.1007/3-540-06859-7_145)
   and Dennis and David Misunas's
   [basic data-flow processor](https://doi.org/10.1145/642089.642111)
   proposed direct execution of dataflow programs, including conditionals and
   iteration, as a route toward a practical Fortran-level machine. `[D]`
2. **Arvind's dynamic tagged-token architecture.** The MIT Tagged-Token
   Dataflow Architecture attached a dynamic context tag to each operand token.
   Hardware rendezvoused tokens with matching instruction and context tags,
   allowing recursive calls and loop iterations to overlap. The functional
   language Id compiled to these dynamic graphs. `[D]`
3. **Monsoon, P-RISC, and multithreading.** Explicit Token Store moved waiting
   operands into compiler-assigned activation-frame slots. Later work reframed
   dataflow as interacting sequential threads and proposed P-RISC, a synthesis
   that retained normal RISC execution while adding fast fork, join, start, and
   split-phase memory operations. `[D]`

The MIT
[CSG memo archive](https://csg.csail.mit.edu/CSGArchives/memos.html)
contains the unusually complete primary record, including Petri-net work from
the same group: Henry Baker's 1972 “Petri Nets and Languages,” Suhas Patil's
“Circuit Implementation of Petri Nets,” Michael Hack's decision-problem work,
the dataflow-machine line, and the later hybrid papers. `[D]` The resemblance
the Navigator noticed is historical, not accidental.

## A focused reading path

The following order answers the inquiry with the least detour:

1. **Dennis and Misunas, “A preliminary architecture for a basic data-flow
   processor” (1975).** Read the original ambition: execute a Fortran-level
   dataflow form directly and use specialized memory/interconnect to realize
   high concurrency.
2. **Arthur Veen, [“Dataflow Machine Architecture”](https://doi.org/10.1145/27633.28055)
   (1986).** This is the best contemporary survey. It defines a dataflow
   machine specifically as hardware optimized for *fine-grain*—roughly one
   conventional instruction—data-driven parallel computation and surveys the
   architectural costs.
3. **Arvind, Culler, and Ekanadham,
   [“The Price of Asynchronous Parallelism”](https://csg.csail.mit.edu/CSGArchives/memos/Memo-278.pdf)
   (1988).** This quantifies the dynamic instruction overhead rather than
   treating parallelism as free.
4. **Nikhil and Arvind,
   [“Can Dataflow Subsume von Neumann Computing?”](https://csg.csail.mit.edu/CSGArchives/memos/Memo-292.pdf)
   (1989).** Despite the title, the paper explicitly explores a synthesis:
   ordinary RISC execution plus dataflow-derived multithreading and
   synchronization.
5. **Arvind and Nikhil,
   [“Executing a Program on the MIT Tagged-Token Dataflow Architecture”](https://doi.org/10.1109/12.48862)
   (1990).** This is the most useful end-to-end account of Id, compilation,
   token matching, I-structures, parallelism control, placement, and unresolved
   resource managers.
6. **Papadopoulos and Culler,
   [“Monsoon: An Explicit Token Store Architecture”](https://csg.csail.mit.edu/CSGArchives/memos/Memo-306.pdf)
   (1990).** This shows the retreat from associative matching toward explicit
   activation frames and compiler-assigned token slots.
7. **Arvind and Brobst,
   [“The Evolution of Dataflow Architectures from Static Dataflow to P-RISC”](https://csg.csail.mit.edu/CSGArchives/memos/Memo-316.pdf)
   (1990),** followed by Papadopoulos and Traub,
   [“Multithreading: A Revisionist View of Dataflow Architectures”](https://csg.csail.mit.edu/CSGArchives/memos/Memo-330.pdf)
   (1991). These are the clearest statements of what survived: explicit frames,
   split-phase operations, cheap synchronization, and multithreading around
   efficient sequential instruction runs.

The functional branch should be read beside that lineage:

8. **D. A. Turner,
   [“A New Implementation Technique for Applicative Languages”](https://doi.org/10.1002/spe.4380090105)
   (1979).** Combinatory-logic translation removes bound variables, and a graph
   reduction machine executes the resulting program.
9. **Simon Peyton Jones,
   [“Implementing lazy functional languages on stock hardware: the Spineless
   Tagless G-machine”](https://www.cs.tufts.edu/comp/150FP/archive/simon-peyton-jones/spineless-jfp.pdf)
   (1992).** STG is the important historical correction: keep a small explicit
   functional intermediate language, but compile it efficiently to stock
   hardware using closures, stacks, heap objects, strictness information,
   unboxed values, and direct jumps.

## What the dataflow computers actually attempted

A dynamic MIT dataflow run can be simplified as:

```diagram
┌──────────────┐    ┌─────────────────┐    ┌────────────────┐
│ Id program   │───▶│ instruction-level│───▶│ tagged operand │
│ functional   │    │ dataflow graph  │    │ tokens         │
└──────────────┘    └─────────────────┘    └───────┬────────┘
                                                   ▼
                                          ┌────────────────┐
                                          │ wait / match   │
                                          │ by instruction │
                                          │ + context tag  │
                                          └───────┬────────┘
                                                   ▼
                                          ┌────────────────┐
                                          │ fire one       │
                                          │ machine op     │
                                          └────────────────┘
```

Each graph operator was approximately a conventional machine instruction.
Tokens carried operands and enough addressing/tag information to identify the
dynamic instruction instance. An operator became executable when its matching
operands arrived. I-structures supplied write-once array-like memory whose
presence bits could defer a read until its value was produced. `[D]`

This was an ambitious general-purpose computer architecture, not merely a
workflow notation. Its value proposition was raw parallel throughput,
automatic exploitation of fine-grained parallelism, and latency tolerance.
The hardware scheduler, token store, memory system, network, compiler, and
programming language all participated in that choice.

## Why the pure general-purpose bet lost

There was no single fatal result. Several costs compounded while conventional
processors and compilers improved.

### 1. Fine-grained synchronization was real work

`[D]` “The Price of Asynchronous Parallelism” found dataflow dynamic instruction
counts commonly about two to three times equivalent IBM 370 programs; the
synchronization/control work was of the same magnitude as the basic work.
For a matrix multiply, 72,344 dataflow instructions compared with 36,284 IBM
801 and 26,172 IBM 370 instructions. Parallel loop control alone accounted for
26,737 instructions. Compiler loop unrolling reduced the dataflow total to
57,577, which proves both the cost and the value of compilation.

Those numbers are period-specific and are not a direct performance comparison
with Petrus. Their durable lesson is that automatic concurrency has a grain
floor: if each useful operation is tiny, scheduling, matching, tagging, and
termination bookkeeping can rival the useful work.

### 2. The matching store fought memory economics and locality

`[D]` Tagged-token firing required a large sparsely occupied virtual matching
space addressed by destination and context tag. Veen reports that the
Manchester machine's high-speed data memory dominated hardware cost, token
metadata consumed roughly two thirds of each matching cell, and practical
occupancy had to stay below 50% to avoid overflow degradation. The effective
utilization of matching memory was below 20%, expected to reach only about 25%
with improved overflow hardware.

`[D]` Associative matching was too costly for the critical path, and hashing
added pipelines, overflow machinery, and underutilized storage. Monsoon's
explicit token store replaced global tag matching with compiler-assigned slots
inside activation frames. This was not abandonment of all dataflow semantics;
it was an admission that ordinary address calculation, locality, and explicit
resource allocation were better engineering mechanisms.

### 3. Parallelism had to be restrained, not merely discovered

`[D]` Veen identifies resource overload as a major problem: realistic programs
with irregular parallelism could flood the matching unit with intermediate
tokens. A reasonably sized Manchester multiprocessor needed average parallelism
near 1,000 to keep its pipelines occupied, while too much unbounded activity
exhausted storage. The proposed remedy was a *throttle* operating at loop or
procedure-body grain.

`[D]` The TTDA paper gives the sharper example: 100,000 loop iterations could
swamp a 256-processor machine. Inserting dependencies could throttle the loop,
but careless schemes could deadlock, and selecting the right scheme in general
was not a simple compiler decision. Resource managers introduced private state
and serialization—exactly the mechanisms pure determinate dataflow was meant
to minimize.

### 4. Data structures and state were not free-flowing scalars

`[D]` Pure copying was unacceptable for large structures. Implementations added
special structure stores, write-once I-structures, reference counting,
presence bits, deferred reads, and compiler-managed allocation. Veen concluded
that no universal structure-handling solution had emerged and that medium-grain
structure operations could be preferable.

This matters because general-purpose programs need arrays, heaps, updates,
resource managers, I/O, and critical sections. Single-assignment functional
semantics made parallel dependence clear but did not erase storage management
or external state.

### 5. Distribution and placement became coarser

`[D]` Sending every instruction/token through a network made placement and load
balance architectural concerns. TTDA moved toward placing *code blocks* rather
than individual operations to reduce per-instruction distribution cost.
Monsoon bound an activation frame and code-block activation to one processing
element so fine-grained local work could avoid network traffic.

Again the winning correction was hierarchy and grain: expose large independent
regions to distribution; execute local sequential work efficiently.

### 6. The compiler and source language carried too much burden

`[D]` Id existed partly because explicit dataflow graphs were tedious to draw.
The compiler still had to choose unrolling, partitioning, placement, storage,
throttling, and sequential regions. The TTDA authors reported that efficiently
compiling non-strict Id to conventional processors was difficult because the
compiler had to partition a fine-grained graph into sequential threads.

`[D]` Veen's Manchester figures also show the compiler gap. Straightforward
compilation produced a 3% floating-point instruction fraction for larger
programs; optimization raised it to 15%, comparable with conventional compiler
results. The semantics were not enough—the implementation needed sophisticated
normal compilation work.

### 7. The ideas survived by hybridizing

`[D]` The MIT authors themselves did not end at “dataflow failed.” Static
dataflow became tagged-token dataflow; associative matching became explicit
frames; then P-RISC and the revisionist multithreading view retained cheap
fork/join, split-phase memory, presence-bit synchronization, and latency
tolerance around sequential threads, registers, and conventional compilation.

The historical result is better described as **harvesting** than extinction.
Dataflow remains useful in streaming systems, signal processing, hardware
circuits, compiler IRs, heterogeneous accelerators, and dependency schedulers.
Modern work such as
[“Heterogeneous Von Neumann/Dataflow Microprocessors”](https://doi.org/10.1145/3323923)
continues the hybrid rather than replacement line. `[D]` What did not win was
one pure, fine-grained architecture for all computation.

## Dataflow graphs and Petri nets: related, not identical

Both models use local token-triggered firing. That is the genuine resemblance.
Veen notes that dataflow-machine terminology—nodes, tokens, enabling, firing—
partly came from Petri-net and graph theory. `[D]`

Their center of gravity differs:

| Model | First-class structure | Natural strength |
| --- | --- | --- |
| Dataflow graph | Actors/operators connected by value dependencies | Determinate computation and available parallelism |
| Petri net | Places holding a marking/multiset; transitions consume and produce | Synchronization, conflict, resource custody, cycles, and nondeterministic process evolution |
| Colored Petri net | Petri marking plus typed/value-bearing tokens | Domain process state and typed coordination |

`[D]` Kavi, Buckles, and Bhat's
[1987 isomorphism paper](https://engineering.unt.edu/cse/research/labs/csrl/files/IEEE-TSE-1987.pdf)
does **not** prove that all dataflow graphs and all Petri nets are the same. It
maps an *uninterpreted*, unit-disjunctive, unit-selective dataflow-graph class to
a timed Petri net; the timed free-choice result additionally requires each
selective actor to have one input. The transfer makes liveness, boundedness, and
timing analyses available for that class. The same paper warns that
combinatorial explosion can make Petri-net analysis inoperative.

That result supports two restrained conclusions:

1. Petrus is using a well-founded concurrency model with useful local and
   structural analysis, not an unrelated visual metaphor.
2. Petrus must not promise exhaustive whole-state analysis for arbitrary
   colored nets with guards, values, timers, inhibitor/read arcs, and external
   effects. Analysis should target bounded, relevant subclasses and explicit
   simulation campaigns.

`[D]` [Open Petri Nets](https://arxiv.org/abs/1808.05415) supplies a modern
mathematical result relevant to authoring: designate input/output places and
compose nets by gluing outputs to inputs; operational and reachability semantics
can be assigned compositionally. It supports typed ports and subnet composition
as a design direction. It does not require Petrus to expose category theory or
adopt that paper's exact implementation.

## Why Petrus is a different bet

| Dimension | MIT general-purpose dataflow machine | Current Petrus |
| --- | --- | --- |
| Goal | Maximize general computation throughput | Make long-lived agentic processes durable, recoverable, and inspectable |
| Firing grain | Arithmetic or machine-level operator | Domain transition, synchronization, wait, custody change, or effect gate |
| Tokens | Transient operands plus context tags | Typed process facts in a durable Instance marking |
| Scheduler | Custom hardware discovers instruction-level readiness | Host asks one Engine to apply at most one normal Action per turn |
| Execution | Specialized matching/token-store processor | Conventional Python and replaceable Workers/transports |
| Memory | Associative/hashed token matching, I-structures, custom frames | Conventional memory plus an append-only History Store and operational stores |
| Durability | Not the primary goal | Every firing is recorded; replay applies recorded token movement without rerunning handlers |
| Effects | Functional/single-assignment core with difficult managers and I/O | Explicit Petri-agnostic Activities, at-least-once outcomes, ambiguity, and reconciliation |
| Distribution | Route instruction/token traffic among processors | Route work between independent authorities; one Instance retains one History writer |
| Success metric | Instructions/throughput/utilization | Correct recovery, explicit authority, explainability, and useful end-to-end DX |

Petrus therefore resembles **macrodataflow** or a durable coordination IR more
than a dataflow CPU. `[E]` Its settled loop is:

```diagram
┌──────────────────┐    ┌──────────────────┐    ┌────────────────┐
│ typed application│───▶│ canonical Petrus │───▶│ Engine + one   │
│ authoring        │    │ Net topology     │    │ Instance       │
└──────────────────┘    └──────────────────┘    └───────┬────────┘
                                                       ▼
                                              ┌────────────────┐
                                              │ append-only    │
                                              │ History        │
                                              └───────┬────────┘
                                                       ▼
                                              ┌────────────────┐
                                              │ conventional   │
                                              │ Activities /   │
                                              │ Workers        │
                                              └────────────────┘
```

The net is the durable process representation, not a replacement instruction
set. [Petrus's product principles](../../../product/principles.md) summarize the
distinction as “the net is the durable thing, not the agent,” and
[`spec/OVERVIEW.md`](../../../../spec/OVERVIEW.md) fixes the separation between
Net, History, Activities, and operational execution. `[E]`

## The shared failure mode Hamsterdan is exposing

The important analogy is not hardware. It is **flat graph-shaped authoring**.

Current Hamsterdan V5 deliberately removed ambient read arcs and guards from
its readiness net and made each concern's memory, facts, requests, and results
explicit. `[E]` That improved ownership and simulation semantics. It also left
nine cohabited concern-loop modules plus topology, folding, and gating machinery
under `readiness/net_v5`; the package now totals 4,403 lines. `[E]`

Hamsterdan's [ES-009](https://github.com/henriquebastos/hamsterdan/blob/a14c77825d9616fe0e3f9102cd3476a597fc7da7/docs/project/exploration/es9-human-codebase-ownership/index.md)
found that the production seams are mostly deep and justified, not candidates
for indiscriminate flattening. The pain is navigation, reading locality, and
the amount of topology source required to state honest behavior. `[D]`

Its current [ES-010](https://github.com/henriquebastos/hamsterdan/blob/a14c77825d9616fe0e3f9102cd3476a597fc7da7/docs/project/exploration/es10-composable-hamsterdan-architecture/index.md)
therefore keeps the nine concern loops and Petrus `Engine.advance()` while
separating pure workflow definition, typed Activity contracts, readiness
effects, host supervision, and compositional deterministic simulation. `[D]`
That is evidence against a second scheduler or hidden imperative workflow; it
is also evidence that the authoring representation must preserve hierarchy.

The warning signs for Petrus are now concrete:

- transitions becoming ordinary function calls rather than durable process
  commitments;
- place/transition/arc plumbing dominating domain rules;
- generated topology losing the names and hierarchy present in source;
- raw graph renderings being the only explanation of causal behavior;
- one tiny decision becoming several recorded firings and History rows;
- global type matching or ambient reads coupling otherwise independent blocks;
- exhaustive reachability claims against value-rich unbounded state; and
- “easy” helpers hiding failure, effect ambiguity, authority, or durability.

If Petrus continues with low-level Net authoring as the default, Hamsterdan is a
credible warning that adoption will fail even if the runtime is correct. If
Petrus treats the Net as an inspectable canonical IR under a better source
language, the same application is evidence that the semantics are worth
preserving.

## The Haskell, laziness, and SKI connection

The Navigator's pull toward functional programming is technically relevant,
but several nearby ideas must remain distinct.

### Availability-driven dataflow versus demand-driven graph reduction

`[D]` Veen states the contrast directly:

- a dataflow machine schedules an operator when its input data are available;
- a reduction machine schedules computation because its result is needed.

Lazy Haskell is demand-driven. It builds/allocates closures or thunks, forces
them when demanded, and updates shared results so work is not repeated.
MIT-style dataflow is availability-driven: an enabled operator may fire even if
no downstream consumer currently demands its result.

Both use graph-shaped intermediate structure and benefit from referential
transparency, but they answer opposite scheduling questions. Neither should be
silently equated with Petrus, whose host and selection policy decide which
durable enabled Action advances next.

### What SKI teaches—and what it does not

`[D]` Turner's 1979 technique translates an applicative language into
combinatory form with bound variables removed and executes the result through
graph reduction. This makes SKI and related combinators important implementation
and semantic tools.

Raw SKI is not a good Petrus source language:

- bracket abstraction can grow terms;
- eliminating variables also eliminates useful domain names;
- primitive combinators hide authored hierarchy;
- local reductions are hard to relate to durable business causality; and
- the smallest semantic basis is not the smallest cognitive surface.

The useful lesson is **compositional algebra**, not the literal `S`, `K`, and
`I` vocabulary. A small set of typed flow combinators can give blocks a closed,
lawful meaning while preserving domain names and source locations.

### STG is the stronger analogy for Petrus

`[D]` Early functional graph reducers inspired special hardware, but the
Spineless Tagless G-machine compiles a high-level lazy language through small
explicit intermediate languages onto conventional hardware. The compiler can
recover sequential execution, direct jumps, unboxed arithmetic, stack/heap
layout, strictness, and garbage collection without giving up functional source
semantics.

The strategic analogy is:

```diagram
Haskell source ──▶ Core ──▶ STG ──▶ stock machine code

Petrus source  ──▶ typed flow algebra ──▶ canonical Net ──▶ Engine / History
```

Petrus's Net can play the role of a small explicit runtime IR: authoritative,
inspectable, and stable enough for replay, but not necessarily the spelling in
which every application author should work.

### Functional techniques that directly fit Petrus

- **Algebraic data types** for observations, concern state, terminal outcomes,
  and effect ambiguity instead of strings, flags, and nullable results.
- **Pure functions** for classification, folds, guard decisions, and projection
  from already recorded facts.
- **Pattern matching** that makes every outcome explicit and lets type checking
  expose missing branches before motion.
- **Effect separation**: pure transition meaning remains separate from Activity
  execution and external authority.
- **Composition laws** for sequence, typed choice, parallel split/join, loop,
  resource scope, wait, and open ports.
- **Property-based testing** for lowering laws, fold invariants, replay
  equivalence, and compositional simulation.

These ideas can improve a Python system. Rewriting Petrus in Haskell is not
supported by the evidence. A Haskell prototype may be useful if it isolates and
tests the authoring algebra, emits canonical Net v3, and remains disposable.
Runtime migration would add ecosystem, packaging, FFI, and operational work
without yet proving a better developer journey.

## Grain rule for Petrus

A transition belongs in the durable net when at least one of these is true:

1. it records a domain state change that must survive restart and be explained;
2. it synchronizes independently progressing owners;
3. it commits, accepts, rejects, or reconciles an external-effect outcome;
4. it acquires, releases, or fences a resource/capability;
5. it begins or resolves a timer, human wait, or other durable suspension; or
6. its nondeterministic choice is part of the process contract.

Ordinary arithmetic, parsing, mapping, validation, formatting, and local
calculation should remain ordinary pure code inside one transition or Activity
unless their result is itself a durable process fact. “Pure” alone is not a
reason to create a transition. This rule is the direct defense against
instruction-grain dataflow overhead and History bloat.

## Recommended authoring direction

The candidate surface should have three visible layers:

1. **Typed leaves.** Named pure decisions, durable state updates, waits, and
   Activities with algebraic input/output types.
2. **A small composition algebra.** Sequence, choice, parallel split/join,
   bounded loop, resource scope, and typed open ports. Combinators preserve
   hierarchy and names rather than immediately flattening to arcs.
3. **Canonical lowering and descent.** Deterministic Net v3 output, source map,
   rendered topology, validation, and a supported way to insert low-level
   places/transitions/arcs where the algebra is insufficient.

The frontend may be Haskell-like without being Haskell-specific. Its contract
matters more than syntax:

```text
Flow[Input, Output]

capture
  |> choose(classify)
       { clean   -> publish
       ; failed  -> rerun |> await_ci |> choose(...)
       ; blocked -> await_human
       }
```

This sketch is not proposed API spelling. A valid design must show where each
branch, wait, join, Activity, and durable state change lowers, and diagnostics
must point back to the authored block rather than only to generated node IDs.

## Bounded next experiment

The Navigator authorized this experiment on 2026-08-26. The detailed,
self-contained implementation and evidence route is preserved in the
[typed functional flow vertical-slice experiment plan](experiment-plan.md).
All prototype code, tests, goldens, and reports remain inside ES-059; this
thickens the existing story rather than allocating a new Exploratory Story or
opening Delivery.

**Executed.** The experiment is implemented and complete under
[experiments/typed-flow-vertical-slice](experiments/typed-flow-vertical-slice/README.md)
with its verdict, acceptance matrix, and evidence in the
[Experience Report](experiments/typed-flow-vertical-slice/report.md):
**promising** `[E]`. The Hamsterdan-shaped slice authored as one typed
functional value lowered byte-stably into current canonical Net v3 (14
places, 9 transitions, 28 arcs), executed through the real Engine, JSONL
History, replay, scoped generations, and an interrupted-restart route with
identical canonical History, and every one of its 147 recorded facts
explains back to an authored source block. Composition mistakes fail before
motion at their source expressions, and the one inhibitor-based publication
gate composed through the explicit low-level descent seam without bypassing
canonical validation.

**Two bounded follow-up experiments** probe where the decision structure
itself should live, both beside — never inside — the completed slice:

- [experiments/algebraic-decision-table](experiments/algebraic-decision-table/report.md)
  (**promising** `[E]`): the ladder authored as an ordered, first-match-wins
  case table lowered to the SAME single transition — canonical Net v3 bytes
  and the fixture's canonical History are byte-identical to the completed
  slice, a 10,368-point sweep matches `route_ci` exactly, totality is checked
  statically through an `otherwise` sentinel, and every rung gets its own
  source-map attribution. Named cost: the shared classify/commit seam
  (`normalize`) is where sequential state-dependence resists tabulation.
- [experiments/guarded-decision-net](experiments/guarded-decision-net/report.md)
  (**mixed** `[E]`): each rung as its own guarded transition makes the ladder
  visible in canonical topology and closes the slice's Ignored-invisibility
  limit (absorption is now a named durable firing), at the price of 9→13
  transitions, 28→40 arcs, ~10× guard-evaluation amplification, and — the
  decisive counterexample — overlapping guards that nothing refuses, whose
  business outcome is then reproducibly settled by the Engine's selection
  policy rather than the authored flow, while a non-exhaustive rung set
  strands observations silently. Exclusivity/exhaustiveness became an
  executable but unprovable authoring obligation (576-point grid).

Together the three spellings sharpen the grain rule's authoring corollary:
keep one durable transition per decision and enrich the *source* (the case
table), rather than multiplying transitions to make branching visible (the
guarded net) — durable visibility of absorbed decisions is the one genuine
argument the guarded variant leaves on the table.

Use one Hamsterdan vertical slice rather than a new tutorial or full rewrite:

> Admit one exact-head CI observation; publish when clean; on failure request
> one rerun; if failure persists request repair; accept branch movement as a
> new generation; resume from History; expose the final decision and every
> effect gate.

Build one typed functional source representation in Python that compiles to
current canonical Petrus Net v3. The authorized
[experiment plan](experiment-plan.md) chooses integration economy over a
second-language comparison: Haskell remains a design reference, not another
frontend or runtime in this experiment.

The experiment passes only if it demonstrates:

| Property | Required evidence |
| --- | --- |
| Semantic preservation | The slice retains every durable branch, wait, generation fence, failure, and effect-acceptance boundary |
| Canonical integrity | Repeated compilation is byte-stable and current validation, rendering, History replay, and resume still work |
| Source explanation | Every generated place/transition and observed firing maps to an authored block and domain name |
| Coarse grain | Ordinary local functions do not become transitions or History rows |
| Error locality | Port/type/composition mistakes fail before motion at their source expression |
| Progressive descent | One unusual low-level Petri fragment composes without bypassing validation or creating another execution model |
| Reading improvement | A maintainer can explain the process from the source representation without first reading generated topology plumbing |

Compare concepts, explanation steps, source attribution, and change locality—not
only line counts or graph size. Keep the generated topology available for
inspection and adversarial review.

Failure should be diagnostic:

- if the source becomes a disguised graph builder, redesign the algebra;
- if lowering cannot preserve hierarchy or explain History, add source-map and
  canonical identity support before more syntax;
- if coarse domain behavior still causes topology explosion after composition,
  reconsider the kernel boundary;
- if the runtime itself dominates latency or storage at this coarse grain,
  measure that separately rather than importing CPU-era dataflow conclusions;
- if low-level descent breaks typing or deterministic lowering, do not promote
  the authoring surface.

This is the smallest experiment that can distinguish “Petri nets are wrong for
the product” from “the current Petri-net authoring surface is too low level.”

## Disposition and coherence

The evidence supports continuing Petrus. It does not support complacency.
Petrus is differentiated by making durable coordination—not ordinary
computation—explicit, but Hamsterdan shows that the current authoring cost can
still make the product fail in practice.

No new decision record is needed: the source-grounded result strengthens the
existing progressive-disclosure decision. The Navigator-authorized experiment
has been executed under its
[durable execution plan](experiment-plan.md) and classified
[promising](experiments/typed-flow-vertical-slice/report.md). No roadmap,
debt, release, product-principle, production-runtime, or Hamsterdan change
follows from the result itself. ES-056 remains the durable owner of the
candidate adoption Value and AX28/AX29 remain the promotion evidence gates;
the report is now available evidence for them. ES-059 contributes the
historical failure model, coarse-grain rule, functional-language rationale,
and the executed bounded test of that direction.
