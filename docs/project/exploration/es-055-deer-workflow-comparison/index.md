---
code: ES-055
status: Completed
opened: 2026-08-13
related:
  - docs/product/principles.md
  - docs/project/decisions/records/2026-07-28T0133Z-python-dsl-compiles-authored-specifications-to-canonical-nets.md
  - docs/project/decisions/records/2026-08-03T0430Z-installations-own-authority-agenticus-owns-machinery.md
  - docs/project/decisions/records/2026-08-03T2130Z-flat-json-is-the-canonical-net-definition-interchange.md
  - docs/project/decisions/records/2026-08-05T0923Z-net-owned-pi-loop-mirrors-a-bounded-public-seam.md
source_repository: https://github.com/deerwork-ai/deer-workflow
source_revision: b20823012eeec15d41f4969f09964401e00f56e0
---

# Deer Workflow comparison

## Inquiry

What does Deer Workflow implement, how does its architecture compare with
Petrus, and which parts should Petrus copy, adapt, use as inspiration, avoid,
or ignore?

This comparison inspected Deer Workflow's documentation, source, tests,
examples, package metadata, and repository history at revision
`b20823012eeec15d41f4969f09964401e00f56e0` on 2026-08-13. It compares shipped
behavior rather than product labels. Claims use the project evidence grades:
`[E]` executable local evidence, `[D]` source/docs verified, `[R]` reported, and
`[X]` refuted.

## Executive reading

Deer Workflow and Petrus overlap at the product-story level—both coordinate
agent work—but they are not alternate implementations of the same runtime.

- `[D]` Deer Workflow is a Bun/TypeScript structured-concurrency library around
  complete coding-agent CLI subprocesses. Workflow topology and state live in
  ordinary TypeScript control flow, lexical values, Promises, and one process.
- `[D]` Deer has no explicit graph representation, Petri-net semantics,
  scheduler, durable state, checkpoint, replay, resume, first-class human wait,
  workflow retry, workflow timeout, or workflow cancellation protocol.
- `[E]` Petrus is an explicit durable state-transition runtime: a canonical Net,
  one append-only History and marking per Instance, durable firing occurrences,
  provider-neutral Activity custody, replay, timers, retries, lifecycle scopes,
  observation, simulation, and independently placed Workers.
- `[D/E]` Deer is dramatically easier to start and see working. Petrus is
  dramatically stronger when work outlives one call stack, crosses a process
  boundary, fails ambiguously, waits, retries, or must be explained later.

The architectural lesson is therefore not to replace Petrus semantics with
Deer's workflow model. It is to bring Deer's authoring immediacy, event-fed
presentation, CLI stream discipline, and adapter ergonomics to projections and
frontends that compile to or host Petrus's existing durable model.

## Architecture map

### Deer Workflow

`[D]` The implemented system is small and direct:

```text
TypeScript workflow module
  ordinary await / conditionals / loops
  parallel([...thunks])
  pipeline(items, ...stages)
  nested workflow() call (one level)
            |
            v
AsyncLocalStorage context + one mutable phase
            |
            +--> Agent.run(prompt, options)
            |      Codex CLI / Claude Code / Pi subprocess
            |
            +--> synchronous typed lifecycle emitter
                   JSONL / print mode / terminal TUI
```

Primary implementation boundaries:

- [`src/flow/workflow.ts`](https://github.com/deerwork-ai/deer-workflow/blob/b20823012eeec15d41f4969f09964401e00f56e0/src/flow/workflow.ts)
  dynamically imports a workflow module, creates process-local context, emits
  lifecycle events, invokes the handler, and emits success or failure.
- [`src/flow/parallel.ts`](https://github.com/deerwork-ai/deer-workflow/blob/b20823012eeec15d41f4969f09964401e00f56e0/src/flow/parallel.ts)
  and
  [`src/flow/pipeline.ts`](https://github.com/deerwork-ai/deer-workflow/blob/b20823012eeec15d41f4969f09964401e00f56e0/src/flow/pipeline.ts)
  are `Promise.all` convenience combinators with unbounded fan-out.
- [`src/events/types.ts`](https://github.com/deerwork-ai/deer-workflow/blob/b20823012eeec15d41f4969f09964401e00f56e0/src/events/types.ts)
  defines seven workflow/phase/log event variants.
- [`src/agents/types.ts`](https://github.com/deerwork-ai/deer-workflow/blob/b20823012eeec15d41f4969f09964401e00f56e0/src/agents/types.ts)
  defines a small complete-agent-loop interface; Codex, Claude, and Pi adapters
  implement it through subprocesses.
- [`src/runner/workflow-runner.ts`](https://github.com/deerwork-ai/deer-workflow/blob/b20823012eeec15d41f4969f09964401e00f56e0/src/runner/workflow-runner.ts)
  is the host-facing in-process facade.
- `src/tui/` projects the same event stream used by JSONL automation.
- `skills/workflow-creator/` gives an agent enough API and pattern context to
  generate a workflow source file without automatically executing it.

### Petrus

`[E]` Petrus separates semantic truth from operational custody and presentation:

```text
Python DSL / canonical Net definition v3
            |
            v
Impetus: Net + marking + enabled bindings + one canonical History
            |
            v
Engine: one serialized Instance advancement lane
            |
            +--> pure transition projection
            |
            +--> ActivityRequested (canonical outbox)
                         |
                         v
Motus Dispatch --> Worker --> external effect / agent program
                         |
                         v
Activity terminal --> deterministic projection --> new marking

Observation / telemetry / Arx are projections; none is semantic authority.
```

The shipped ownership boundaries are visible in
[`spec/OVERVIEW.md`](../../../../spec/OVERVIEW.md),
[`src/petrus/engine/__init__.py`](../../../../src/petrus/engine/__init__.py),
[`src/petrus/impetus/instance/__init__.py`](../../../../src/petrus/impetus/instance/__init__.py),
and [`src/petrus/motus/dispatch/__init__.py`](../../../../src/petrus/motus/dispatch/__init__.py).
Agent-specific composition remains above those foundations in
[`src/petrus/agenticus/`](../../../../src/petrus/agenticus/).

## Capability comparison

| Capability | Deer Workflow | Petrus | Reading |
| --- | --- | --- | --- |
| Definition | Executable TypeScript module | Canonical flat Net JSON plus Python DSL frontend | Deer favors immediate expression; Petrus favors stable inspectable semantics |
| Topology | Implicit call graph and Promise structure | Explicit places, transitions, arcs, guards, filters, timers | Deer has no graph runtime to copy |
| State | Lexical variables and AsyncLocalStorage | Marking rebuilt from canonical History | Different durability class |
| Parallelism | Immediate unbounded `Promise.all` | Token-enabled firings; one writer, concurrent Activity substrate | Deer is simple but operationally unsafe at scale |
| Scheduling | JavaScript/Bun event loop | Explicit candidate enumeration and pluggable Instance-scoped selection; host owns multi-Instance scheduling | Petrus keeps semantic choice recorded |
| Failure | Top-level throw, but combinators convert every branch failure to `null` | Structured Activity failure and explicit firing terminal records | Petrus must not adopt failure-as-null |
| Retry | Workflow-authored loops only | Frozen bounded Activity execution policy with Attempts and deadlines | Petrus is substantially ahead |
| Persistence | Optional output JSONL only; no reader or store | In-memory, JSONL, SQLite, and PostgreSQL History Stores | Deer output is not durable execution state |
| Replay/resume | None; adapters request ephemeral agent sessions | Handler-free deterministic replay and Engine load/recovery | Core Petrus differentiator |
| Cancellation | Per-agent `AbortSignal`; no workflow cancellation state | History-first lifecycle scopes and post-commit Dispatch fences | Petrus is stronger but deliberately does not claim hard interruption |
| Human wait | No first-class support | Source transitions and durable delivery registrations can model identified human decisions | Petrus still needs a polished human-facing host/Arx surface |
| Events | Seven typed synchronous lifecycle events | Rich canonical History plus separate best-effort operational telemetry and observation protocol | Deer has the simpler presentation contract; Petrus has the stronger truth model |
| UI | First-party terminal dashboard | Arx is separate; this repository has HTTP observation/simulation but no general workflow TUI | Largest visible adoption gap |
| Agent integration | Tiny common complete-loop interface; three subprocess adapters | Agenticus descriptors, custody, Hands, Attachments, four runtime adapters, and a Net-owned agent loop | Petrus is more honest about non-equivalent program ownership, but much harder to approach |
| Tools | Owned opaquely by each coding-agent CLI | Agenticus Hands and separate Activities make capability and effect boundaries explicit | Deer cannot uniformly observe or authorize tools |
| Security | Provider-specific sandbox mapping; Pi adds path and raw-flag defenses | Installation-owned authority, capability profiles, lifecycle fencing, explicit support matrix, execution-territory contracts | Both teach provider-specific hardening; Petrus should retain stronger vocabulary |
| Deployment | Local Bun package/CLI/TUI/JSONL | Library, Engine, local/durable Dispatch, Workers, ZeroMQ, optional PostgreSQL/Absurd | Deer is a local tool; Petrus is runtime infrastructure |
| Testing | Good hermetic adapter, event, TUI, and CLI tests | Larger semantic, persistence, crash/replay, provider, property, and golden-trace coverage | Both test at their actual boundaries |

## What Deer does well

1. **The code/agent responsibility split is crisp.** `[D]` Exact sequencing,
   branching, aggregation, validation, and file handling stay in code; agents
   receive semantic tasks. Petrus already agrees through its principle “useful
   with zero agents” and its pure-handler/Activity split.
2. **The first success path is short.** `[D]` A developer can generate one
   source file, inspect it, run it, and watch progress. Petrus's README explains
   a Net definition but does not present an equally small complete create/run/
   inspect path.
3. **Presentation consumes a protocol.** `[D]` JSONL and TUI are projections of
   the same typed events rather than direct callbacks into flow internals.
4. **CLI channels are disciplined.** `[D]` Progress and final result are kept
   separable; print mode emits machine-readable JSONL.
5. **The adapter boundary is small.** `[D]` A complete coding-agent loop fits
   behind `run(prompt, options)`, keeping provider subprocess mechanics out of
   workflow source.
6. **Process handling is careful.** `[D]` Prompts travel over stdin, commands use
   argument arrays, temporary files are cleaned, missing binaries produce useful
   errors, and cancellation is tested.
7. **Pi receives specific defense-in-depth.** `[D]` The adapter blocks raw flags
   that would bypass its harness, canonicalizes paths, checks symlink escape,
   and says when OS-level isolation is still required.
8. **Documentation, examples, generator context, and tests move together.**
   `[D]` This is valuable contract discipline even though Deer manually mirrors
   too much of the same material.

## What Deer does poorly or does not do

1. **“Agent graph” is marketing, not implementation.** `[X]` There is no graph
   object, node lifecycle, edge semantics, marking, enabled set, or graph
   validation. The call stack is the graph.
2. **Failure-as-`null` destroys causality.** `[D]` `parallel()` and `pipeline()`
   swallow every exception—including cancellation—and conflate failed work with
   a valid `null` result.
3. **Concurrency is unbounded.** `[D]` Every thunk or item chain starts
   immediately. There is no admission control, provider quota, resource budget,
   queue, backpressure, or per-workflow concurrency policy.
4. **The mutable phase model does not compose.** `[D]` One workflow-global phase
   races under concurrent branches; documentation asks callers not to do that.
5. **Events are coupled to execution.** `[D]` Synchronous listeners run on the
   critical path. A slow listener delays work; a throwing listener can break the
   lifecycle it observes.
6. **Observability is not durability.** `[D]` JSONL has no reader, replay,
   checkpoint, schema migration, or state reconstruction contract.
7. **Cancellation and timeout stop at individual agent calls.** `[D]` There is
   no workflow signal, sibling cancellation, deadline, durable cancellation
   state, or process-tree guarantee.
8. **The provider abstraction leaks.** `[D]` Sandbox labels map to materially
   different provider capabilities. Structured output is cast to the requested
   generic type without runtime validation. The convenience `agent()` remains
   hard-wired to Codex even though generation can use Claude or Pi.
9. **Arbitrary imported code is fully trusted.** `[D]` Running a workflow means
   executing arbitrary local TypeScript in the host process with inherited
   environment. Agent subprocesses inherit most of that environment too.
10. **The package is a young Bun-specific pilot.** `[D]` Version `0.2.0`, source-
    only TypeScript publication, recent concentrated history, and external CLI
    dependencies make it useful evidence, not a mature runtime baseline.

## Petrus strengths revealed by the comparison

1. **The net—not the agent or call stack—is durable truth.** `[E]` Replay can
   rebuild marking and runtime state without executing historical handlers.
2. **Semantic and operational records are separated.** `[E]` Activity Attempts,
   leases, heartbeats, and queue mechanics stay in Dispatch while accepted
   Activity and firing facts enter one Instance History.
3. **Ambiguity is modeled rather than hidden.** `[E]` At-least-once effects,
   terminal quarantine, scoped-ingress disposition, and cancellation fences do
   not pretend that an interrupted external effect never happened.
4. **Parallel flow is explicit structure.** `[E]` Fan-out, joins, inhibition,
   reads, correlation guards, timing, and completion are Net semantics rather
   than incidental Promise behavior.
5. **Execution scales without changing semantics.** `[E]` Inline, in-memory,
   local, and durable Dispatch profiles preserve the same Activity/History
   boundary; Workers may be placed separately.
6. **Inspection is truth-backed.** `[E]` Definition, snapshot, History paging,
   Graphviz, capture, and bounded simulation project canonical structures.
7. **Agent differences are not flattened into a false universal object.** `[E]`
   Agenticus distinguishes provider-, harness-, and Net-owned programs,
   Continuations, Threads, Hands, territory, and installation authority.
8. **Test depth matches the risk.** `[E]` The repository has approximately
   40,930 source lines, 44,127 test lines, 10 language-neutral trace fixtures,
   and broad crash/replay/provider coverage. On 2026-08-13,
   `scripts/check quick` passed Ruff lint/format, production typing, and
   structural ast-grep checks.

## Petrus weaknesses revealed by the comparison

1. **The adoption path is too long.** `[E]` There is no general `petrus run`
   experience, generated starter, or first-party live TUI in this repository.
   A new reader must compose Net, bindings, History Store, Dispatch, Engine, and
   a host loop before seeing a durable process move.
2. **Conceptual precision has a cognitive price.** `[E]` Approximately 41k
   source lines, 125 decision records, several component vocabularies, and many
   provider/support distinctions make the system difficult to evaluate quickly.
   This precision is often justified, but the progressive-disclosure surface is
   not yet equally developed.
3. **The public-product surface trails the kernel.** `[E]` Petrus is `0.0.0`,
   claims no PyPI release, and delegates the human-facing companion to separately
   maintained Arx. Strong runtime capability is not yet an easy product.
4. **Agenticus breadth exceeds its supported boundary.** `[E]` Amp, Claude,
   Codex, and Pi adapters and profiles exist, but the README supports only the
   scripted Pi A2 Local host lifecycle; other routes remain qualification-only.
   Catalog presence must not be mistaken for product support.
5. **Hosts still own fleet orchestration.** `[E]` One Engine owns one Instance;
   multi-Instance scheduling, wake indexing, supervision, and application
   lifecycle remain outside. This is architecturally coherent but leaves a lot
   for adopters to assemble.
6. **Fabric is not ready to answer workflow composition.** `[E]` Existing
   call/spawn demonstrations are explicitly unfinished and subject to rewrite.
7. **Human cooperation is structurally possible but not packaged.** `[E]`
   Identified source delivery and registrations can model human decisions, but
   there is no Deer-like visible interaction surface in this repository.
8. **There is no single simple event story for application authors.** `[E]`
   Canonical History, best-effort telemetry, snapshot/history HTTP protocols,
   and future Arx each have correct distinct roles, but a user who only wants
   “show this run live and stream it to a supervisor” faces several surfaces.

## What Petrus should copy

Copy the product contracts and engineering discipline, not the runtime model:

1. **One event-fed presentation architecture.** A CLI/TUI/supervisor projection
   should consume a versioned read-only stream derived from History plus clearly
   identified operational telemetry. A presentation failure must never affect
   Engine motion.
2. **Strict process channel behavior.** If Petrus gains a one-shot host CLI,
   reserve stdout for the declared result, stderr for human progress, and offer
   one pure versioned JSONL mode.
3. **Agent-adapter process hygiene.** Retain argument arrays, stdin prompts,
   bounded diagnostics, temporary-file cleanup, early missing-installation
   checks, cancellation tests, and provider-specific security analysis.
4. **Generate, inspect, validate, then run.** A future authoring assistant should
   emit a canonical Net definition and binding skeleton, render/validate them,
   and never auto-execute generated code.
5. **An immediately runnable worked example.** The first Petrus example should
   demonstrate create, advance, wait, resume, inspect, and final result without
   requiring the reader to discover every extension profile first.

Substantial code copied from Deer would require preserving its MIT notice and
updating Petrus's license-scope/third-party notices. The recommendations above
do not require copying implementation code.

## What Petrus should adapt

1. **Code-first ergonomics, compiled to explicit semantics.** Keep the Python DSL
   and canonical JSON as authoring frontends. Add convenience only where it
   compiles to a Net that can be rendered, validated, replayed, and resumed.
2. **`parallel` and `pipeline` as patterns, not primitives.** Offer documented
   Net templates or Arx authoring gestures for fan-out, independently advancing
   item flow, bounded worker admission, and explicit joins. Do not implement
   them as hidden `Promise.all` equivalents.
3. **A small complete-loop convenience at the right boundary.** Deer proves the
   usefulness of a tiny harness interface. Petrus should preserve Agenticus's
   ruled absence of one universal `Agent`, but profile-specific application
   composition can expose a small callable facade after ownership,
   Continuation, Hands, and authority have already been resolved.
4. **Phases as views.** A user-facing phase can group Net nodes for presentation,
   but it must never become a second mutable execution truth.
5. **Structured result schemas.** Keep provider schema hints, then validate at a
   Petrus-owned retry-side boundary and record structured validation failures;
   never trust a provider response plus a static type cast.
6. **Live run UX through Arx or a thin host.** Reuse Petrus observation contracts
   and preserve Arx ownership rather than coupling a TUI directly to Engine
   internals.

## What should inspire Petrus

- A “one file to first motion” experience can coexist with a deep runtime if the
  file is a frontend, not canonical state.
- The same read-only event protocol can power a human dashboard, CI output, and
  supervisor integration.
- Workflow generation is useful when generated output is reviewable source or
  canonical IR, validated before execution, and separated from credentials.
- Provider abstractions should advertise capability differences rather than
  force false equivalence. Deer's Pi adapter and Petrus's profile tables both
  support this direction.
- Compact final results plus durable, provenance-rich artifacts are a better
  agent-workflow contract than returning an unbounded transcript.
- Excellent examples can teach orchestration patterns before every underlying
  concept is explained.

## What Petrus should avoid

- Making arbitrary host-language control flow the only workflow topology.
- Representing branch failure or cancellation as `null`.
- Unlimited fan-out by default.
- Synchronous observers on the semantic execution path.
- A shared mutable workflow phase.
- Treating JSONL output as replayable state without a store and reader contract.
- Hard-wiring a default provider behind an allegedly neutral convenience API.
- Treating sandbox labels as equivalent across providers.
- Inheriting the complete host environment into agent subprocesses by default.
- Publishing metadata as an “execution plan” when the runtime neither executes
  nor validates it.
- Manually duplicating the same API contract across many docs, generator files,
  and templates when one generated projection can preserve coherence.
- Copying upstream private loops. Petrus's bounded public-seam mirror remains the
  stronger precedent.

## What Petrus should not spend time studying

1. Deer's “agent graph” language: there is no graph implementation beneath it.
2. Its durability, scheduler, retry, resume, or human-wait architecture: those
   capabilities are absent.
3. The one-level nested-workflow restriction: it is an implementation shortcut,
   not a design insight.
4. The example-specific HTML report renderer: useful product polish, unrelated
   to core runtime design.
5. Source-only Bun packaging: it is a pilot constraint, not a portability model.
6. The global phase race and failure-swallowing combinators except as negative
   examples.
7. Manual bilingual and generator-reference duplication: preserve the coherence
   intent, not the maintenance shape.

## Recommended order of influence

1. **First-motion and inspection path:** design one minimal complete Petrus
   example or thin host that proves local create/run/resume/inspect.
2. **Presentation projection:** define the narrow consumer need across History,
   telemetry, observation, and Arx before adding another event authority.
3. **Authoring assistance:** let an agent produce canonical Net v3 plus binding
   code, then validate and render before execution.
4. **Provider UX:** retain Agenticus's honest ownership/capability model while
   making one supported profile much easier to compose.
5. **Only then evaluate convenience patterns:** fan-out, pipelines, artifact
   outputs, and progress grouping should emerge from real Petrus examples.

No implementation candidate is promoted by this exploration. Each direction
crosses existing Arx, Agenticus, Engine, and canonical-definition boundaries and
needs a separately bounded Navigator choice when concrete adoption work begins.

## Disposition

Completed as comparative architecture evidence. Deer Workflow is useful prior
art for Petrus's adoption and presentation layers, not for Petrus's execution
semantics. The durable conclusion is:

> Preserve Petrus's explicit Net, History, Activity, and authority model. Learn
> from Deer how quickly a user can author, run, observe, and understand a small
> workflow, then deliver that immediacy through compiled frontends and read-only
> projections rather than hidden control flow.
