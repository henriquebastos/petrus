---
code: ES-056
status: Candidate
opened: 2026-08-13
related:
  - ES-055
  - ES-061
  - CV8
  - CV10
  - CV16
  - CV19
  - docs/product/principles.md
  - docs/project/decisions/records/2026-08-13T1740Z-progressive-disclosure-preserves-runtime-power.md
  - docs/project/decisions/records/2026-07-28T0133Z-python-dsl-compiles-authored-specifications-to-canonical-nets.md
  - docs/project/decisions/records/2026-08-03T2130Z-flat-json-is-the-canonical-net-definition-interchange.md
evidence_repository: https://github.com/henriquebastos/hamsterdan
evidence_revision: ea7784bb8a1237f223e9ffcb27598d5e39ee9e17
---

# Progressive-disclosure developer experience

## Inquiry

What single product Value should organize Petrus's developer-experience work so
that a Hamsterdan-scale process becomes radically simple to author, run, and
understand without reducing runtime power, hiding durable semantics, or closing
off lower-level Petri-net expression?

The inquiry is deliberately larger than authoring syntax. Petrus already has a
Python DSL, canonical Net interchange, Engine, History Stores, Dispatch,
Workers, observation, simulation, rendering, and Agenticus. The missing product
owner is the complete journey through those capabilities.

## Governing Navigator direction

The ruling is now retained in the product principles and its decision record:

> Preserve Petrus's full power and lower-level escape hatches. Make a
> Hamsterdan-scale system radically simple and expressive on the Petri-net
> flow-authoring side—ideally one file to first motion—while HTTP clients,
> agent machinery, and infrastructure remain behind or beside the flow.

This resolves one ambiguity and leaves several others open:

- **Resolved:** simplicity is progressive disclosure, not a smaller runtime.
- **Resolved:** the Petri net remains the durable process representation.
- **Resolved:** low-level APIs remain a supported descent path, not deprecated
  internals hidden by a new framework.
- **Open:** the default authoring spelling, run-surface owner, honest local
  profile, and live presentation contract.

“One file” means one readable flow/application source surface. It may import
domain types, HTTP clients, Activities, agent programs, and configuration from
ordinary modules. It does not mean credentials, provider clients, canonical
History, generated artifacts, and deployment configuration must be embedded in
one physical file.

“First motion” means more than successful construction: the source compiles,
validates, yields inspectable canonical topology, creates or resumes a named
Instance under an honestly described profile, accepts representative ingress,
advances, and exposes what happened. A generated file is never executed merely
because it was generated.

## Executive conclusion

Petrus does not need several new Values for authoring, CLI, TUI, examples, and
agent convenience. Those would reproduce today's ownership seams in the
roadmap. It needs **one candidate adoption Value** whose promise is the complete
developer journey and whose Delivery Stories may be worked independently.

The runtime is not “too powerful.” The current product surface is too flat:
developers meet authoring, bindings, store, Dispatch, Engine, driving, and
inspection as peer assembly concerns before the first useful feedback. A
progressive surface should choose and name one coherent local profile while
leaving every constituent replaceable underneath.

```diagram
┌──────────────────────────────────────────────────────────────────┐
│ One readable flow/application file                              │
│ domain flow + imported leaves + explicit application profile    │
└──────────────────────────────┬───────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│ Authoring compiler and validation                               │
│ source map + static advice + deterministic composition errors   │
└──────────────────────────────┬───────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│ Existing Petrus artifacts                                       │
│ canonical Net v3 + implementation bindings + rendered topology  │
└──────────────────────────────┬───────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│ Existing Petrus runtime                                         │
│ History Store + Engine + Dispatch + Workers + application host  │
└──────────────────────────────┬───────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│ Read-only understanding                                         │
│ result + History-backed state + identified operational progress │
└──────────────────────────────────────────────────────────────────┘

Deliberate descent remains possible at every authoring boundary; no second
execution model is introduced.
```

## What Petrus already owns

The portfolio is stronger than the current first-run experience suggests:

| Foundation | Existing owner | Contribution to the target | Not reopened here |
| --- | --- | --- | --- |
| Petri semantics and canonical History | Impetus; CV1–CV4/CV6 | Explicit durable process truth, replay, typed flow | Replacing History with a call stack |
| Activity execution | CV8 | Stable logical execution, bounded retries/deadlines, typed terminal projection, Workers | Putting Attempt mechanics back in the Net |
| Lifecycle replacement | CV8.DS6 | Exact generation close/reset and late-result disposition | App-authored retirement forests |
| Composable execution territory | CV10 | Honest host/effect/environment boundaries | A universal public execution object |
| Inspection and simulation | CV11–CV15, CV17–CV18 | Definition, History, rendering, capture, bounded runs, portable Net v3 | A second presentation authority |
| Agent infrastructure | CV16 | Optional Agenticus machinery with installation-owned authority | Making agents foundational or falsely universal |
| Python authoring | DSL decisions | `NetSpec`/`BuiltNet`, typed direct handlers and guards, reusable stamping | Python source as canonical interchange |
| Canonical interchange | Net-definition v3 decision | Strict flat JSON shared by Python, Arx, tests, and agents | Hidden multi-file runtime resolution |

The current public route is coherent but assembly-heavy. A developer builds a
`NetSpec`, receives `BuiltNet.net` plus implementation maps, chooses a History
Store and Dispatch, creates an Engine, supplies host time/ingress, repeatedly
calls `advance()`, drives Workers where needed, and selects an observation
surface. Each choice is legitimate. Requiring all choices before feedback is
the adoption gap.

No retained Value currently owns this full path. CV8, CV10, and CV16 end at
runtime capability boundaries; CV11–CV18 supply inspection artifacts and
protocols; Arx follows them without owning application lifecycle. An adoption
Value can compose these results without changing their ownership.

## Evidence from Hamsterdan

Hamsterdan is the right pressure test because it is neither a toy nor a generic
benchmark. At evidence revision `ea7784b` it has 11 Activities, 11 GitHub
webhook event types, 12 human intent kinds, one Engine per pull request, agent
work, durable publication, timers, lifecycle replacement, recovery, and two
world-mutation gate classes.

Its four explorations separate several questions that Petrus must not conflate:

1. **ES-001 — runtime/application ownership.** Moving operational retry and
   exact generation cleanup to Motus and lifecycle scopes removed large amounts
   of retirement topology while keeping current authority, desired state, and
   business acceptance in the application. Runtime capability can simplify the
   authored Net without weakening it.
2. **ES-002 — imperative sugar alone.** Fourteen mostly domain-specific
   fragment families added about 540 lines of machinery to reduce roughly 510
   hand-wired declaration lines to about 440. The economics were negative.
   Hiding fluent arc syntax is not the product answer.
3. **ES-003 — structured authoring.** Twenty-seven experiments found a layered
   candidate: a generic net kernel floor, function-shaped typed Blocks, a small
   composition algebra, optional sugar, and an advisory static facade. Every
   experiment compiled to the frozen runtime; zero Petrus changes were needed.
   Deterministic composition errors remain authoritative, and source mapping,
   canonical rendering, History, and replay survive lowering.
4. **ES-004 — application essence.** The production net measured 46 places, 69
   transitions, 309 arcs, including 94 read arcs; experiments classified 73%
   of those reads as displaced by executed alternatives. Every product rule
   survived a candidate model centered on three control states, per-concern
   folds, pure decisions, typed subnet exits, and two effect gates. The full
   merged model and production migration remain unproven and unapproved.

The topology counts are diagnostics, not a score. Hamsterdan previously chose
more places and arcs to expose independent business owners, a clarity gain.
Conversely, the ES-004 fragments reached about 1.1 arcs per node by eliminating
ambient reads. A good authoring surface minimizes accidental coordination while
keeping genuine ownership visible; it does not optimize blindly for the
smallest graph or fewest source lines.

The Deer Workflow comparison adds the other half of the evidence. Deer reaches
one generated file and visible progress quickly because ordinary TypeScript
control flow is the workflow. It loses the compiled artifact, durable state,
replay, resume, and explicit join/failure semantics. Petrus should copy the
first-motion discipline, generated-authoring package shape, and presentation
clarity—not the execution model.

## The target experience contract

A future promoted Value should make the following journey coherent.

### 1. Author

The developer sees domain flow first:

- imported or locally declared typed work leaves;
- explicit sequence, branch, join, wait, retry outcome, and terminal paths;
- named, typed boundaries where independent blocks compose;
- one visible selection of an application profile;
- no routine place/transition/arc plumbing when a proven higher-level pattern
  expresses the same truth.

The developer can descend in the same file to low-level nodes, arcs, guards,
and Petri-aware handlers for topology the higher layer cannot express. The
descent is explicit and retains soundness and composition checks.

### 2. Compile before execution

Compilation produces the existing canonical artifacts and refuses invalid
composition before an Instance moves. The author can inspect:

- deterministic canonical Net v3;
- implementation binding diagnostics;
- rendered topology;
- source-to-generated-node attribution;
- profile and durability choices;
- validation errors with concrete remedies.

An authoring frontend may be discarded and regenerated. Canonical History is
never derived from a live builder, generator frame, coroutine, or call stack.

### 3. Reach honest first motion

One command or equivalent Python entry point should compile and run the file
under one named local profile. The profile states whether History and Activity
custody survive process restart. It creates or resumes an identified Instance,
does not require external infrastructure for its flagship local path, and does
not conceal state files or credentials.

The recommended candidate is a **local durable** flagship profile backed by
existing SQLite-owned state, with an explicitly named ephemeral/in-memory
profile for disposable learning. This is a recommendation, not a decided
default: AX28 must measure whether local state custody remains simple and safe
enough for first motion.

### 4. Understand the run

The developer sees semantic motion and operational progress through a read-only
projection. At minimum the surface distinguishes:

- canonical facts already accepted into History;
- current marking/status and what is awaiting;
- Activity work requested, operationally running/retrying, or terminal;
- the next required input or timer;
- final result and inspectable artifact locations.

Presentation failure never delays or changes Engine motion. A TUI, JSONL mode,
CI reporter, and Arx may share a consumer contract only after that consumer is
defined against existing History, observation, and telemetry boundaries. The
contract must not become another semantic event log.

### 5. Grow without a rewrite

The same source can move from local to separately placed Workers by changing
application composition, not process semantics. Advanced authors can replace
the store, Dispatch, driving host, observation client, or selected Agenticus
profile independently. The one-file path is an on-ramp, not a framework that
captures the application's lifecycle forever.

## Hamsterdan complexity test

The decisive benchmark is not “can Hello World run?” It is:

> Can a reviewer understand Hamsterdan's durable PR-readiness decisions from
> one readable flow file while clients, agents, provider fencing, and host
> infrastructure remain in their proper modules—and can Petrus compile that
> file to canonical topology that still validates, renders, replays, resumes,
> and permits low-level descent?

The benchmark should be executed in two stages:

1. **One-PR vertical slice:** admission, CI failure, one rerun, one repair,
   branch movement, confirmed resume, finding/readiness publication, human
   wait, and terminal state. This proves the complete journey before a full
   rewrite-sized experiment.
2. **Full authored architecture:** all 11 Activities, 12 intent kinds, timers,
   concern folds, publication recovery, and both mutation gate classes. This
   measures scale and missing vocabulary; it is not production migration.

Acceptance evidence must cover five dimensions:

| Dimension | Evidence |
| --- | --- |
| First motion | Commands, authored files, concepts, and elapsed steps from source to an observed run |
| Semantic visibility | Every durable branch, wait, join, failure, recovery, and external-effect gate identifiable in source and compiled topology |
| Artifact integrity | Byte-stable canonical definition, rendering, source attribution, History replay, and resume |
| Error locality | Deliberate type, port, soundness, profile, and missing-binding mistakes fail before motion with actionable diagnostics |
| Progressive descent | One mixed high-level/low-level file compiles and runs without bypassing validation or changing semantics |

Lines of code and arcs per node remain supporting diagnostics. They never
justify hiding a domain decision, fusing distinct owners, or turning an
external effect into an unrecorded call.

## Candidate Value and delivery map

### Candidate Value — Approachable Petrus

**Intent:** let a developer author, validate, run, observe, resume, and extend a
durable Petrus process from one coherent progressive surface while retaining
canonical artifacts and full lower-level control.

This should be one Value because the user promise is end to end. Its work can
expand into independently owned Delivery Stories after the candidate gate:

This exploration originally used “CV19” as a provisional candidate label.
[CV19](../../roadmap/cv19-deterministic-simulation-testing/index.md) was later
allocated to deterministic simulation testing and is now Done. Exploration
does not reserve the candidate's eventual roadmap code; allocate that code only
if the Navigator promotes this Value.

| Candidate Delivery Story | User-visible outcome | Existing owners composed | Dependency / evidence gate |
| --- | --- | --- | --- |
| **DS1 — One-file first motion** | One flow/application file compiles, validates, runs or resumes under a named local profile, and reports its artifacts | DSL, Engine, local History/Dispatch | AX28; decide runner owner and local profile |
| **DS2 — Expressive flow authoring** | Domain blocks, typed exits, sequence/branch/join/loop/failure patterns compile to canonical topology with deliberate low-level descent | Impetus DSL and canonical Net v3 | Review ES-003 candidate; full Hamsterdan benchmark; AX29 |
| **DS3 — Live understanding** | A terminal/JSONL/Arx consumer shows semantic state and correlated operational progress without entering the execution path | CV11–CV15 observation, History, telemetry, Arx | ES-061 supplies the accepted portable definition/view/lineage semantics; DS1 supplies the concrete live consumer |
| **DS4 — Generated authoring and worked examples** | An agent or human can generate/review/repair a runnable flow using machine diagnostics; examples, API projection, templates, and evals stay coherent | DS1/DS2 compiler and diagnostics | AX27; stable default authoring surface; never auto-run |
| **DS5 — Approachable effects and agents** | Ordinary Activities and one honestly supported Agenticus profile compose as simple leaves without flattening provider differences | CV8, CV10, CV16, host-owned authority | DS1 profile; one concrete zero-agent and one agent example |

Documentation and progressive disclosure are acceptance work in every Delivery
Story, not a final documentation lane. Each story ships its runnable example,
diagnostics, canonical artifact, and lower-level explanation together.

Existing Values remain closed or blocked at their stated boundaries. This
candidate would consume their public results. A missing consumer convenience is
not permission to reopen CV8 semantics, promote private CV10 execution
contracts, broaden CV16's support matrix, or move application lifecycle into
Arx.

## Candidate evidence probes and order

Hamsterdan has retained three executable probes under its ES-003. They are
evidence, not commitments:

1. **AX28 — one file to first motion.** Run first. It tests the governing
   product promise and reveals the real assembly/profile/observation gap before
   Petrus designs a new facade.
2. **AX29 — the descent seam.** Run next or alongside authoring review. A mixed
   block/kernel file protects the low-level escape hatch before one default
   syntax becomes a public commitment.
3. **AX27 — generated authoring.** The diagnostic feedback-loop experiment is
   independently executable now, but productization should follow selection of
   the default authoring surface. Otherwise the generator may optimize a syntax
   the project later rejects.

After AX28, a bounded Petrus exploration can prototype only the missing generic
application/run composition. Arx work should begin only after that probe names
the live consumer; Agenticus convenience should begin only after the ordinary
zero-agent path is coherent.

## Ownership recommendations

- **Petrus owns the generic first-motion application runner/profile.** It is the
  project that composes Impetus and Motus; asking every application or Arx to
  rebuild that assembly would preserve the gap. The runner must remain thin and
  return control rather than becoming a framework host.
- **Impetus owns authoring compilation and canonical diagnostics.** Hamsterdan
  owns the pressure test and may keep disposable prototypes, but any promoted
  general algebra belongs upstream only after application evidence.
- **Arx owns interactive human presentation.** Petrus may own a machine-readable
  read-only projection and minimal CLI renderer; Arx does not own runtime state
  or application lifecycle.
- **Applications own clients, credentials, policy, and domain leaves.** CV8,
  CV10, and Agenticus supply reusable machinery; one-file DX does not turn
  Petrus into the application's authority principal.
- **Generated-authoring packages consume public contracts.** They do not become
  a shadow specification copied manually across docs, templates, and evals.

These recommendations are part of the candidate map, not decided package or
CLI contracts.

## Open product and architecture choices

1. **Default authoring surface.** The ES-003 block algebra is proven as a spike,
   but its final vocabulary and operator sugar remain unchosen. Radical
   simplicity requires one documented default, not several equally prominent
   styles.
2. **First-motion profile.** Choose local durable SQLite, explicit in-memory, or
   a two-step progression. The surface must state the guarantee and state
   location; “local” alone is not a durability claim.
3. **Runner lifetime.** Decide whether a command advances to terminal/awaiting
   and exits, supervises a local process, or exposes both as named modes. It may
   not quietly become the application lifecycle owner.
4. **Presentation join.** Define exactly how canonical History/state and
   best-effort operational telemetry correlate for a live consumer without
   creating one misleading stream or letting listeners block execution.
5. **Source and evolution contract.** A compiled definition is not stored in
   History today. Source mapping, definition fingerprinting, and narrowing-net
   preflight need explicit evidence before the one-file route promises safe
   evolution.
6. **Control as projection.** Hamsterdan's candidate `fold`/`decide` layer is
   valid only where its inputs are canonical facts and its outputs become
   identified work through existing doors. A host-local decision loop whose
   state cannot be reconstructed remains forbidden.
7. **Agent convenience.** Decide which one supported Agenticus profile earns a
   small application facade. Do not infer a universal `Agent` or supported
   provider from catalog presence.

## Explicit non-goals and avoid list

- Do not simplify, remove, or bypass kernel semantics merely to reduce the
  number of concepts in a tutorial.
- Do not make arbitrary Python control flow, a generator frame, coroutine, or
  agent thread canonical workflow state.
- Do not hide History Store, Dispatch, durability, retry, failure, or authority
  choices behind an unnamed “easy” profile.
- Do not treat a JSONL presentation stream as durable execution state.
- Do not couple synchronous observers to Engine motion.
- Do not represent failure, cancellation, or abandoned branches as `None`.
- Do not make unbounded fan-out a convenience default.
- Do not infer topology globally from matching Python types or payload shape.
- Do not copy Hamsterdan's domain vocabulary into Petrus as a generic DSL.
- Do not create a universal Agent, Session, environment, or effect object to
  make examples shorter.
- Do not auto-execute generated source.
- Do not optimize for source lines or graph size at the expense of visible
  business ownership and inspectable semantics.
- Do not dispatch implementation threads until the candidate Value and first
  evidence probe identify bounded contracts.

## Candidate gate

The Value is ready for Navigator promotion only when the following evidence is
available:

1. AX28 executes one source file through compile, canonical inspection, honest
   local motion, observation, and replay/resume on the frozen runtime.
2. AX29 proves deliberate descent by mixing the recommended authoring layer and
   low-level kernel topology without losing validation.
3. The default authoring candidate expresses the one-PR vertical slice and
   identifies every unsupported Hamsterdan construct without hiding it in host
   callbacks.
4. The runner owner, first-motion profile, and presentation consumer are each
   bounded by an explicit decision or experiment result.
5. A zero-agent example and one supported Agenticus example use the same
   application journey while preserving their different authority needs.

Full Hamsterdan regeneration may remain a Delivery Story acceptance target if
the vertical slice gives the Value enough form. Production migration is never
implied by successful exploration.

## Driver recommendation

Retain **one candidate Value — Approachable Petrus**, not multiple new Values.
Start with AX28 because it tests the stated dream directly and exposes which
generic assembly is actually missing. Protect the descent seam with AX29 before
promoting an authoring API. Then review the ES-003 default-surface choice; run
AX27 against the selected diagnostics contract; open live-presentation and
Agenticus convenience only from those concrete consumers.

Until those probes report, preserve every existing runtime and roadmap
boundary. The likely product is a thin progressive application surface over
Petrus, not a simpler Petrus underneath.
