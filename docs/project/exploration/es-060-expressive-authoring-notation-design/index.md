---
code: ES-060
title: Expressive net-authoring notation for Petrus
status: Paused
status_reason: >-
  Captured as a ready-to-run design program for a future dedicated session.
  The method, round ordering, scorecard criteria, and non-goals are settled
  here; no round has been executed. The first action is blocked on one
  Navigator input this document specifies: choosing the benchmark
  feature-net. If resumed, its accepted evidence supplies CV20.DS2; no code or
  kernel change is authorized by this story.
opened: 2026-08-26
related:
  - ES-059
  - ES-056
  - CV20.DS2
  - docs/product/principles.md
  - docs/project/decisions/records/2026-08-13T1740Z-progressive-disclosure-preserves-runtime-power.md
  - docs/project/decisions/records/2026-07-28T0133Z-python-dsl-compiles-authored-specifications-to-canonical-nets.md
source_context:
  - StrangeLoop 2011 slide deck, Gerald Jay Sussman, "We Really Don't Know
    How to Compute!" (local copy analyzed on 2026-08-26)
  - ES-059 experiment verdicts at Petrus commit 42041c0
research_sources:
  - https://www.infoq.com/presentations/We-Really-Dont-Know-How-To-Compute/
  - https://dspace.mit.edu/handle/1721.1/44215
  - https://dspace.mit.edu/handle/1721.1/54635
promotes_to: []
promoted_to: []
promoted_at:
---

# Expressive net-authoring notation for Petrus

## Inquiry

What Python notation for authoring Petrus feature-nets produces the
Sussman-grade expressiveness effect — source code isomorphic to the process
diagram, every internal part addressable, domain laws stated once, one
description usable under several interpretations — without weakening the
invariants the ES-059 vertical slice proved must hold (canonical IR,
byte-stable lowering, replay/resume, full source-to-History attribution)?

The inquiry is explicitly a notation-design problem, not a semantics problem.
ES-059 concluded "the authoring surface is too low-level" over "the Petri
model is wrong"; this story designs the surface.

## Why this story exists

The Navigator watched Sussman's StrangeLoop 2011 talk and found the
common-emitter amplifier description (deck pages 11–15) mind-blowing: a
complex circuit expressed as compact, readable code, then interrogated with
`(value ...)` and `(why? ...)` answering with a proof chain. The Navigator
wants the *same effect* for authoring a Petrus feature-net, and wants it
designed iteratively with short feedback cycles rather than by large
autonomous experiment batches, because the judge of "mind-blowing" is the
Navigator's reaction to reading code — a signal no batch can simulate.

## What the Sussman expressiveness actually is

Session analysis of the deck decomposed the effect into five separable
ingredients. Only two are propagator-specific, and those two are the ones
Petrus should not adopt.

1. **Hierarchical structural composition.** `ce-amplifier` is a parameterized
   constructor; applying it grafts a fresh subnet copy into the network.
   Components (`resistor`, `infinite-beta-bjt`) are themselves constructors;
   `2-terminal-device` is an abstract component that concrete devices
   specialize. One line per component, one `node` per junction: the text has
   the shape of the schematic. This is the hardware-description-language
   idea (structural Verilog, SPICE netlists), not the propagator idea. It
   needs only closures building net fragments, fresh internal names per
   instantiation, and interface ports for wiring. **Transfers to Petrus
   wholesale.**
2. **Addressability.** `(the potential b amp bias)`, `(the emitter Q)`:
   every internal part of every instance is nameable from outside by a
   readable selector chain, shared by setup, queries, and inspection.
   **Transfers wholesale.**
3. **Laws stated once, as multidirectional relations.** A resistor is
   `(c:* i R v)` — Ohm's law with no chosen direction; the network infers
   whatever is derivable. This genuinely requires propagator semantics
   (monotone cell merge), which conflicts with linear token consumption.
   **Does not transfer**; at most, relation-style guards deserve a late,
   bounded look.
4. **Partial information with generic operators.** The same network runs on
   numbers, intervals, symbols, and provenance-carrying values because every
   operator is an extensible generic. The lattice-merge part does not
   transfer, but the "same net under several interpretations" consequence
   does: execute / simulate / explain as interpretations of one authored
   net. **Transfers in adapted form.**
5. **Provenance and worldviews.** `why?` answers with a justification chain;
   assumptions can be retracted and swapped. Petrus already owns this
   substrate: History. `why?` is a History query wearing Scheme syntax.
   **Already Petrus-native; needs surfacing, not inventing.**

Supporting background on the propagator/Petri-net relationship (from the same
session): both are bipartite graphs of passive state holders and active
units, but Petri tokens are linear consumable resources (contention and
choice are the point; runs are histories) while propagator cells accumulate
information monotonically (no consumption; all fair schedules converge; runs
are interchangeable). Adopting a propagator runtime would be a semantics
change, and is a rejected detour for this story. The prize is the linguistic
layer that happened to sit on top of one.

## Inputs from ES-059 (do not re-run)

- Typed functional vertical slice: promising; all fourteen completion
  conditions passed; established the invariants listed in the Inquiry.
- Algebraic decision table (single transition): promising; byte-identical
  canonical IR and History under a richer source. This is the leading
  decision spelling.
- One-guarded-transition-per-rung net: mixed; durable branch visibility paid
  for with unprovable exclusivity obligations and topology growth.
- Inscription net (impure = transition, pure = inscription/structure):
  promising with priced costs; seven-combinator kernel, compiler-generated
  exclusive guards with cover proof, pinned findings on fused-effect blast
  radius and the data/structure boundary.

Rounds below reuse these verdicts as settled evidence instead of
relitigating them.

## Method

Five steps, in order. Steps 1–2 happen once; step 3 is the core loop.

### 1. Freeze a benchmark — "the amplifier"

One real feature-net the Navigator actually wants Petrus to run, rich enough
to stress the design: a decision with several rungs, a retry/loop, a subnet
worth instantiating twice, a human-wait, a parallel fan-out. Every round
rewrites this same net so differences between spellings are attributable to
notation, not example. **This choice is the Navigator input the story is
blocked on.** Ask for the scenario in plain words: what it does, where it
branches, what repeats, where humans wait.

### 2. Write the scorecard before any spelling

Make "mind-blowing" falsifiable. Criteria from the deck analysis:

- the code is isomorphic to the diagram: one line per domain concept, no
  plumbing lines;
- every internal part is addressable by a readable path usable in authoring,
  tests, Arx inspection, and History queries;
- each domain law is stated once;
- the same description runs under multiple interpretations (execute,
  simulate/dry-run, explain).

Plus the frozen Petrus invariants: canonical IR, byte-stable lowering,
replay/resume, full source-to-History attribution. A spelling that reads
beautifully but breaks attribution loses.

### 3. Dream-code rounds — one design question each

Per round, the assistant writes two or three rival Python spellings of the
benchmark — no implementation, 30–60 lines each, annotated with trade-offs
and with what Python's syntax fights — and the Navigator reacts: kill, keep,
merge, or redirect. The reading experience is the experiment. Round order,
chosen so the fastest design-killers come first:

1. **Composition and instancing** — subnet constructors, fresh internal
   places per instantiation, interface ports. Nothing else matters if this
   is clumsy.
2. **Naming and paths** — the selector language (`amp.q.emitter`-style)
   shared by authoring, tests, Arx, and History queries.
3. **Interpretations** — the same net executed, dry-run, and interrogated
   (`why?` as a History query).
4. **Decision spelling** — mostly adopting the ES-059 case-table verdict;
   only notation integration is open, not the comparison.

Each round is one markdown file:
`experiments/authoring-surface/rounds/round-NN-<question>.md`, rivals side by
side. A running `experiments/authoring-surface/design-decisions.md`
accumulates what is settled so no round relitigates it.

### 4. Spike only proven-risky Python tricks

Python has no macros. When a *winning* spelling depends on an unverified
host-language trick — decorator introspection, context-manager scoping,
`__getattr__` path chains, operator overloading on inscription values — do a
throwaway TDD spike inside this exploration directory to prove feasibility
before committing the round decision. Never spike losing designs.

### 5. Vertical slice gate, then scale out

When rounds converge and the Navigator would sign the scorecard, build the
minimal kernel that runs the benchmark end-to-end under the frozen
invariants, with the same TDD-plus-adversarial-review discipline as the
ES-059 slice. Passing that gate produces a decision record; only then does
bulk building on top of the design begin.

## Working agreement

- Interactive and iterative: short cycles, one question per round, the
  Navigator judges the reading experience.
- The `annotate` skill can serve a round file for margin comments away from
  the keyboard; `grill-me` can stress-test a spelling the Navigator believes
  in before it graduates.
- All code stays inside this exploration directory until the step-5 gate.
- Surface disagreements between rival spellings; never blend them silently.

## Non-goals

- No propagator runtime, no kernel rewrite, no change to Petri-net
  execution semantics.
- No mimicry of Scheme surface syntax; the target is the effect
  (isomorphism, addressability, laws-once, multiple interpretations), not
  the spelling.
- No promotion decision inside this story; promotion remains a Navigator
  decision on the step-5 evidence.

## First action for the next session

Ask the Navigator for the benchmark feature-net (step 1 criteria above).
With that in hand, draft the scorecard and round-01's rival composition
spellings as the first cycle.
