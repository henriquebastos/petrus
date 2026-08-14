---
code: ES-052
status: Paused
status_reason: Source grounding and a Value hypothesis are preserved; Experiment 1 is deliberately deferred and promotion evidence does not yet exist.
opened: 2026-08-13
related:
  - CV16
  - docs/project/decisions/records/2026-08-03T0430Z-installations-own-authority-agenticus-owns-machinery.md
research_source:
  - https://github.com/deepseek-ai/deepseek-harness/tree/47f943859bef60e4160492346772ded9b24f765a
  - https://github.com/cordiverse/paper/tree/948a07b369c62adb3b12e102458be5c18dfb69b9
---

# DeepSeek Harness and Cordis composition

## Inquiry

What does DeepSeek Harness actually mean by making every product capability a
plugin, what does the upstream Cordis paper claim for spatiotemporal
composition, and which parts should Agenticus copy, adapt, or reject without
weakening installation-owned authority, immutable Episode resolution,
canonical History, or provider-specific honesty?

The motivating hunch is sound but needs one correction: Harness is not a
system with no privileged core. It is a small Cordis microkernel plus a
configuration-driven tree in which almost every **product capability** is a
lifecycle-owned component.

## Current exploration state

Harness and upstream Cordis source grounding plus the first Agenticus/Petrus
fit analysis are complete. The story has formed a candidate around **owned,
inspectable Agenticus installations**, but it is paused before the first
experiment and has not crossed into Delivery.
The candidate shape is deliberately preserved at two levels:

- a potential Value/CV promise for installation authors; and
- a first disposable technical experiment that can test the mechanism without
  creating that promise.

The complete future-execution surface is the
[Customer Value candidate and exploration execution brief](future-execution-brief.md).
It contains the value hypothesis, architecture options, settled constraints,
experiment sequence, promotion gate, possible roadmap decomposition, and exact
resume route. This index remains the source-grounded architecture analysis.

## Research baseline

- `[D]` DeepSeek Harness was inspected at
  [`47f9438`](https://github.com/deepseek-ai/deepseek-harness/tree/47f943859bef60e4160492346772ded9b24f765a),
  the head of `master` on 2026-08-13. Claims below link to that revision.
- `[D]` First-party Harness code is MIT-licensed under DeepSeek's 2026
  copyright. Cordis and its Loader are vendored MIT code from Shigma/Cordiverse
  with DeepSeek modifications; copying implementation rather than independently
  reimplementing an idea requires preserving the applicable Shigma and
  DeepSeek notices. The provenance is explicit in
  [`vendor/README.md`](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/vendor/README.md#L1-L50),
  the [root license](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/LICENSE),
  and the [Cordis license](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/vendor/cordis/LICENSE).
- `[D]` The upstream Cordis design paper was inspected independently at
  [`cordiverse/paper@948a07b`](https://github.com/cordiverse/paper/tree/948a07b369c62adb3b12e102458be5c18dfb69b9),
  the head of `main` on 2026-08-14. The repository contains the
  [paper](https://github.com/cordiverse/paper/blob/948a07b369c62adb3b12e102458be5c18dfb69b9/paper.pdf),
  a short [README](https://github.com/cordiverse/paper/blob/948a07b369c62adb3b12e102458be5c18dfb69b9/README.md),
  and `.gitattributes`; it contains no explicit license file at this revision.
  The README identifies the PDF as an actively revised preprint dated
  2026-08-13. This exploration may analyze and cite it, but the repository is
  not a source-reuse license. Any future use of paper text or artifacts needs
  a fresh provenance and permission review.
- `[D]` The paper is *A Programming Paradigm for Spatiotemporal
  Composability*, by Yifan Shi, Wei Zhang, and Tianyi Cui (Peking University
  and DeepSeek-AI). Page references below use PDF page numbers from that pinned
  revision. The paper does not mention Petrus; every Petrus relation below is
  this exploration's explicitly marked **Petrus reading**, not an author claim.
- `[E]` Petrus's focused Agenticus catalog, profile, and Pi A2 host suites were
  executed against the current source after this comparison was written. The
  result is recorded under Verification.

Evidence labels follow project house style: `[D]` marks a direct
source-verified claim and `[E]` marks observed Petrus code or executed evidence.
**Petrus reading** marks synthesis from that evidence rather than a claim made
by the paper.

## How Harness makes product capabilities plugins

### 1. A non-plugin microkernel bootstraps the graph

Harness documentation says that the model adapter, tool registry, session log,
and agent loop are plugins and that there is no privileged product core
([`docs/architecture.md`](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/architecture.md#L9-L13)).
The implementation draws a narrower boundary:

- `[D]` `new Context()` directly installs root Fiber, reflection, registry,
  events, and logging machinery; these do not arrive through plugins
  ([`context.ts`](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/vendor/cordis/src/context.ts#L70-L83)).
- `[D]` Bootstrap chooses Cordis and manually mounts the Loader before the
  configured tree can load itself
  ([`vendor/cordis/bin.js`](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/vendor/cordis/bin.js#L1-L16)).
- `[D]` Browser boot is even more explicit: React root creation, module loading,
  platform seeds, the Cordis context, and the first Loader mount are machinery
  that cannot themselves be Loader entries
  ([`boot.tsx`](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/client/web/src/boot.tsx#L1-L9),
  [`AppWebEntry.run`](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/client/web/src/boot.tsx#L90-L143)).

The accurate pattern is therefore **microkernel + plugin tree**, not literal
absence of a core.

### 2. “Plugin” is an executable mount contract, not one universal contribution

`Plugin<T>` accepts a function, constructor, or object/module with `apply`.
Each form may carry `name`, synchronous Standard Schema `Config`, `inject`,
`provide`, and interception metadata
([`registry.ts`](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/vendor/cordis/src/registry.ts#L91-L185)).

This still does not make every leaf object a Cordis plugin. A tool, route, UI
slot, command, prompt section, or model adapter registration is usually a
domain contribution installed by an owning plugin. The tool plane, for
example, defines its own typed definition and duplicate/shadowing policy above
the shared lifecycle substrate
([`ToolDefinition`](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/core/tools/src/index.ts#L211-L279),
[`ToolLayer`](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/core/tools/src/index.ts#L713-L753)).

That separation is important: Cordis shares mounting, dependencies, and
cleanup; each domain retains its own conflict and selection semantics.

### 3. Package installation, composition entry, code, and live instance have
separate identities

Harness does not scan every installed package at runtime. `dsh plugin` delegates
package resolution to pnpm; packages become active composition sources only
when their manifest contributes a `dsh.bundle.patch`
([`apps/cli/src/plugin.ts`](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/apps/cli/src/plugin.ts#L30-L90)).
Ordered bundle patches plus profile/home/CLI overlays produce an entry tree.
Each entry has a stable configuration `id`, module `name`, plugin config,
enablement, grouping, and optional injected requirements
([`entry.ts`](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/vendor/loader/src/config/entry.ts#L8-L22)).

The runtime then keeps four different identities:

1. npm package/module — distribution and import;
2. executable callback — code identity;
3. Loader entry ID — configured mount identity; and
4. Fiber UID — one live incarnation.

`RegistryService.plugin()` resolves the export shape, retains a runtime keyed
by callback, and creates one Fiber per mount
([`registry.ts`](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/vendor/cordis/src/registry.ts#L216-L238),
[`plugin()`](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/vendor/cordis/src/registry.ts#L304-L335)).
This prevents package, configuration, and live-process identity from collapsing
into one overloaded “plugin ID.”

### 4. Dependencies are live service availability, not only a boot-time check

`inject` is normalized into required service names. A Fiber computes its
activation epoch from the UIDs of the providers currently satisfying those
requirements
([`fiber.ts`](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/vendor/cordis/src/fiber.ts#L597-L623)).

- `[D]` A missing service leaves the Fiber `PENDING` rather than failing it.
- `[D]` Provider appearance activates the dependent.
- `[D]` Provider withdrawal unloads it.
- `[D]` Provider replacement changes the epoch and reloads it against the new
  provider.
- `[D]` Duplicate providers for one service in one isolation realm fail loud;
  isolated subtrees may carry distinct providers
  ([`reflect.ts`](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/vendor/cordis/src/reflect.ts#L267-L304)).

Cordis dependencies are deliberately small—string service keys with no generic
version, authority, custody, multiplicity, or provider-ranking model. The web
host must add a post-quiescence audit so mandatory missing services do not
remain silently pending forever
([`boot.tsx`](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/packages/client/web/src/boot.tsx#L210-L236)).

### 5. Fiber-owned effects make composition reversible

The strongest mechanism is not module discovery; it is ownership. A Fiber owns
the services, listeners, routes, child plugins, registry contributions,
background work, and cleanup effects installed during one mount. Effects may
be synchronous or asynchronous, are disposed in reverse registration order,
and teardown waits for asynchronous cleanup
([`fiber.ts`](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/vendor/cordis/src/fiber.ts#L402-L560)).

Consequently, configuration replacement, provider disappearance, parent
disposal, and HMR all use the same withdrawal path. Startup or replacement
failure disposes partial effects and Loader entry updates attempt rollback
([`entry.ts`](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/vendor/loader/src/config/entry.ts#L194-L301)).

This is lifecycle governance, not a security boundary. A trusted in-process
Node plugin retains ambient filesystem, process, and network access regardless
of its declared `inject` list.

### 6. Type safety and tests compensate for a flexible runtime shape

- `[D]` TypeScript generics infer plugin configuration, declaration merging
  types services/events, and Standard Schema validates configuration before
  activation. Async config schemas are not supported
  ([`fiber.ts`](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/vendor/cordis/src/fiber.ts#L16-L61)).
- `[D]` The repository requires real Loader composition tests and withdrawal
  checks for registry contributions
  ([`docs/testing.md`](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/testing.md#L7-L35)).
- `[D]` This discipline came from a real miss: 178 green tests and reported
  100% coverage did not catch that default-export normalization discarded
  plugin metadata and direct mounting bypassed real service topology
  ([postmortem 0001](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/postmortem/0001-acp-default-export-drops-inject.md#L7-L13),
  [root cause](https://github.com/deepseek-ai/deepseek-harness/blob/47f943859bef60e4160492346772ded9b24f765a/docs/postmortem/0001-acp-default-export-drops-inject.md#L27-L112)).

The lesson is both positive and cautionary: flexible export inference makes
plugins convenient, but only real composition tests observe the actual
loader/topology contract.

## What the upstream Cordis paper adds

The vendored implementation explains **how** Harness composes plugins. The
paper explains the more general **why**, states the formal assumptions, and
draws boundaries that are easy to miss by reading source alone.

### 1. The target is spatiotemporal composition, not “pluginization”

`[D]` The paper names two independent requirements (section 1.1, PDF p. 4):

- **temporal composability** — withdrawing a component reverts the resource
  allocations, registrations, and state mutations that the runtime tracked for
  it; and
- **spatial composability** — a component declares dependencies and the
  runtime reacts as their providers appear, disappear, or change.

It models the first with **revertible effects**, context transformations paired
with runtime-tracked inverses, and the second with **reactive coeffects**,
observations whose changes can activate, deactivate, or leave a component
unchanged (sections 1.3 and 3, PDF pp. 6–26). The shared “context” is the
in-process state against which those mechanisms operate. **Petrus reading:**
this is evidence for a host-local composition substrate; it is not evidence
for turning all Agenticus concepts into one generic plugin type.

### 2. Component and Fiber separate declaration from incarnation

`[D]` A Cordis component is a triple of dependencies, provisions, and an
effect. A Fiber is one live instantiation with a parent, coeffect observations,
retirement state, and lifecycle (`Inactive`, `Reloading`, `Active`, or
`Unloading`) (sections 4.1–4.3, PDF pp. 28–37). Dependencies resolve to
**provider Fiber identity**, not merely an equal provided value: replacing one
provider with another therefore changes the target and re-evaluates its
dependents (section 4.2, PDF pp. 30–31; section 5.1.3, PDF pp. 59–60).

**Petrus reading:** This supports ES-052's distinction between
descriptor/registration identity and mount incarnation. It also gives a
precise test for future readiness: provider identity changes matter even if
the new provider reports the same capabilities. Agenticus must not copy the
resulting live rebinding for an active Episode; its immutable
`ResolutionSnapshot` makes provider replacement an explicit successor
composition.

### 3. Withdrawal is dependency-aware and asynchronous

`[D]` Cordis deactivates dependents before withdrawing a provider and lets
consumers retain access while their own teardown runs. Once an asynchronous
reconciliation iteration starts, it is allowed to land rather than being
discarded; the provider waits for dependent drainage before disposing (section
4.3, PDF pp. 34–37; section 5.1.3, PDF p. 60). The paper proves that consumers
start only after dependencies are provided and providers outlive consumers
during withdrawal under its transition rules (section 4.4.3, PDF pp. 45–47).

**Petrus reading:** Dependent-first drainage is stronger guidance than a flat
reverse stack alone. An Agenticus mount experiment should model an
ownership/dependency tree, close admission before drainage, and withdraw
children before providers. It must still keep existing Attachment, Hands,
Motus, and provider-specific settlement protocols as the sources of truth for
whether cleanup was verified.

### 4. “Revertible” has a strict system boundary

`[D]` Cordis can track an acquisition such as opening a descriptor because a
corresponding close can remove it. A write or send that crosses the system
boundary is an **emission**, modeled as not changing the tracked context and
therefore neither automatically tracked nor recovered (section 6.1, PDF pp.
67–68). Withholding output until commit or issuing a later compensation are
possible application strategies; they are not evidence that the emission was
undone. The implementation also cannot prove that an author-provided inverse
is correct; supplying a lawful inverse remains the component author's
obligation (section 5.1.1, PDF p. 56).

**Petrus reading:** This is the most important semantic bridge. A future mount
may roll back **composition acquisitions** that it owns—registrations, local
stores, leases with verified release, listeners, tasks, or child mounts. It may
never call an Agenticus external `Effect`, an Activity result, or a canonical
History record “rolled back.” Petrus records observed work and later
compensation as new facts; an uncertain provider effect stays uncertain.

### 5. The theory is conditional, not a blanket correctness result

`[D]` Cordis's whole-system progress argument assumes finite Fibers, bounded
iterators, and an acyclic precedence relation. Its confluence result assumes
pairwise-independent steps, provision-total components, quiescence, and no
failed Fiber; failure is explicitly excluded as a genuine divergence source
(sections 4.4.4–4.4.5, PDF pp. 47–53). Independence is defined by commuting
transformations whose inverses remain undisturbed, relaxed through
observational equivalence over coeffect values (sections 3.1.3 and 3.3.2, PDF
pp. 15–17 and 23–26).

**Petrus reading:** These results justify testing permutations of independent
mount effects, but they do not prove Petrus replay determinism, exactly-once
effects, or safe recovery after failure. Cordis converges an in-memory
composition topology under assumptions; Impetus reconstructs one durable
process from a serialized canonical History. The two properties should remain
separately named and tested.

### 6. Cordis deliberately leaves hard ecosystem concerns open

- `[D]` Dependency keys provide capability-style access control, not a
  malicious-code sandbox. Real sandboxing requires an execution boundary such
  as another runtime, process, or container (section 6.3, PDF pp. 69–70).
- `[D]` A dependency cycle leaves its components inactive. The suggested
  remedy is decomposition into unidirectional integration components, with
  acknowledged component/configuration growth (section 6.5, PDF pp. 71–72).
- `[D]` Dependency linking is by key identity. Interface drift, collisions,
  and unified structural/versioned compatibility remain open problems
  (section 6.6, PDF pp. 72–73).
- `[D]` Koishi is presented as existence-and-adoption evidence, not a
  quantitative evaluation (section 5.3, PDF p. 67). Self-evolving agent
  harnesses are named as a compelling **future validation** setting, especially
  for rapid replacement and changing topology; the paper does not claim that
  this use case has been validated (conclusion, PDF p. 79).

These limits make Agenticus's existing versioned exact requirements,
installation authority, Motus isolation, immutable resolution, and honest
external-effect evidence complementary rather than redundant.

## Agenticus today

Agenticus already has a stronger **semantic plan** than Cordis:

- `[E]` `CapabilityDescriptor` separates versioned typed identity, opaque
  offers, and typed compatibility requirements
  ([`descriptor.py`](../../../../src/petrus/agenticus/catalog/descriptor.py#L50-L176)).
- `[E]` `Catalog` requires registration and a separate exact enablement act,
  validates an explicit at-most-one-per-kind selection, never substitutes a
  convenient provider, and freezes a portable immutable `ResolutionSnapshot`
  for an Episode
  ([`resolution.py`](../../../../src/petrus/agenticus/catalog/resolution.py#L76-L267)).
- `[E]` Runtime-territory profiles are static plan/qualification data and
  explicitly do not claim installation or support
  ([`profiles.py`](../../../../src/petrus/agenticus/runtime/profiles.py#L54-L143)).
- `[E]` Concrete adapters are executable objects with exact provider-specific
  collaborators, configuration, installation probes, and cleanup contracts;
  they are not implementations stored in the Catalog
  ([`pi.py`](../../../../src/petrus/agenticus/runtime/pi.py#L978-L1038)).
- `[E]` The current Pi A2 host composition root manually creates storage,
  credential custody, body and operation stores, adapter, environment provider,
  rollback, and close ordering
  ([`pi_a2_host.py`](../../../../src/petrus/agenticus/runtime/pi_a2_host.py#L1390-L1483)).
- `[D]` A concrete installation, Hamsterdan, correspondingly owns a static
  descriptor tuple, registration/enablement, exact resolution, and later
  runtime composition
  ([`hamsterdan/host/agenticus.py`](https://github.com/henriquebastos/hamsterdan/blob/3519de7ccccfc856e2565ab0cd577badf6b83ba8/src/hamsterdan/host/agenticus.py#L46-L139)).

The gap is not capability description. It is the missing bridge from an exact
resolved plan to owned executable installation:

```text
Agenticus today
descriptor tuple → Catalog → immutable snapshot
                                  │
                                  └─ host-specific construction/rollback/close

Harness pattern
entry tree → dependency resolution → Fiber mount
                                      ├─ owned contributions
                                      ├─ owned children/work
                                      └─ deterministic withdrawal
```

Agenticus has excellent domain lifetimes and fail-closed fences, plus Impetus
`LifecycleScope` for canonical workflow generations. Neither is the same as a
host composition mount that owns executable registrations and collaborator
cleanup. Reusing those names or merging those truths would be a category
error: Cordis-style mount state is operational host state, not canonical
Petrus History.

Petrus also has stronger semantics exactly where Cordis draws its system
boundary:

- `[E]` Impetus History is one durable append-only, uncompacted process truth;
  projections are rebuildable and never replace it
  ([`event-history.md`](../../../../spec/event-history.md#the-canonical-log-is-uncompacted)).
- `[E]` Closing a first-class lifecycle scope removes exact queued work and
  fences in-flight execution, but consumed input is not restored and
  compensation is a later explicit fact. A fence cannot prove that an
  ambiguous external effect did not happen
  ([`event-history.md`](../../../../spec/event-history.md#lifecycle-scopes)).
- `[E]` Activities freeze a request before execution and a terminal fact before
  deterministic projection. Replay observes those facts and does not rerun the
  external side effect
  ([`firing-semantics.md`](../../../../spec/firing-semantics.md#firing-pipeline)).
- `[E]` Agenticus external Effects perform lookup before one fenced execution
  and report indeterminate or already-applied evidence rather than blindly
  retrying an uncertain response
  ([`effect/gateway.py`](../../../../src/petrus/agenticus/effect/gateway.py#L1-L105)).
- `[E]` Episode Attachment settlement closes admission, drains current calls,
  discards staged workspace effects, exports evidence, and consumes provider
  settlement. Unverified settlement becomes fail-closed uncertain custody
  rather than nominal success
  ([`attachment/episode.py`](../../../../src/petrus/agenticus/attachment/episode.py#L263-L362)).

These are not alternatives to Cordis's lifecycle machinery. They define the
doors through which a composition owner must operate.

## Concept mapping: Cordis to Petrus

Shared vocabulary is dangerous here. The following map names the useful
analogy and its stopping point.

| Cordis paper concept | Closest useful Petrus relation | What may transfer | False equivalence to reject |
| --- | --- | --- | --- |
| Context | Host-local Agenticus composition environment | A bounded place to resolve dependencies and register owned cleanup | An Impetus Instance, canonical History, Activity execution context, ambient authority bag, or global service locator |
| Component (`dependencies`, `provision`, `effect`) | Typed exact-profile composer registration associated with descriptors | Separate declaration from live materialization; declare provisions and requirements | Making a `CapabilityDescriptor` executable or reducing Connection, Hands, Territory, and Effect to one component type |
| Fiber | One process-scoped mount incarnation | Parent/child ownership, provider identity, lifecycle, inspection, and deterministic withdrawal | Episode, Thread, Turn, territory lease, provider session, or durable firing occurrence |
| Revertible effect | Tracked composition acquisition with a verified cleanup obligation | Register cleanup immediately after each successful acquisition; unwind partial construction | Agenticus external `Effect`, Motus Activity, token movement, or an operation that can always be undone |
| Reactive coeffect | Future-plan readiness observed from registrations/providers | Recompute detached readiness when exact provider identity changes | Mutating an accepted `ResolutionSnapshot` or hot-rebinding active Episodes |
| Provider target | Exact registration plus live incarnation identity | Treat equal capabilities from a replacement incarnation as a real topology change | Treating equivalent values or descriptor names as the same authority/resource owner |
| Parent/child hierarchy | Mount ownership tree over profile-owned collaborators | Dependents drain before providers; parent close recursively owns children | Security principal hierarchy, Petri subnet hierarchy, or implicit authority inheritance |
| Isolation realm | Host-selected composition visibility scope | Prevent accidental dependency visibility and duplicate provision inside a composition | Process/container isolation or protection from malicious code |
| Event/reactive notification | Operational lifecycle observation | Trigger readiness reconciliation and detached diagnostics | A canonical process event, Petri transition, external event ingress, or durable History record |
| Transaction/rollback | Construction transaction over tracked, internal acquisitions | Clean partial startup and preserve the original failure plus cleanup evidence | Database atomicity across providers, History rollback, exactly-once emission, or denial of an ambiguous external effect |
| Async inertia | Drain-and-settle protocol already started | Let a teardown iteration land; close admission and await dependents | Assuming cancellation retracts provider work already in flight |
| Quiescent confluence | Permutation property for independent composition effects | Property-test stable results under independent registration/acquisition order | Impetus deterministic replay or convergence in the presence of failure and external effects |
| Dynamic replacement/HMR | Explicit successor composition | Use replacement pressure to test identity and cleanup boundaries | Transparent active-Episode migration or provider substitution |
| Key-based linking | Agenticus compatibility requirements | Keep declarative dependencies and inspect missing providers | Regressing from exact kind/name/version/capabilities to unversioned strings |

### Relation by Petrus ownership boundary

- **Impetus:** no Cordis mechanism should enter Petri enabledness, firing,
  token semantics, or canonical History. Impetus lifecycle scopes remain
  durable work generations, not plugin scopes.
- **Motus:** territory creation/destruction and Activity custody remain
  provider-neutral execution responsibilities. A mount may own a Motus lease
  obligation through public contracts but cannot redefine whether destruction
  was verified.
- **Agenticus:** this is the plausible home for a reusable, optional
  composition owner because Agenticus already connects installation-selected
  descriptors to runtime profiles, Connection custody, Hands, Attachments, and
  Effects.
- **Installation/host:** authority, provider enablement, product policy,
  support claims, process lifecycle, and UX stay outside Petrus machinery. A
  Cordis-like composition context cannot silently absorb them.

**Petrus reading:** The resulting architecture is not “Petrus becomes Cordis.”
It is “Agenticus may borrow Cordis's local composition algebra while Petrus
keeps its durable process and external-effect semantics.”

## Comparative fit

| Concern | Harness/Cordis | Agenticus/Petrus | Reading |
| --- | --- | --- | --- |
| Dependency contract | Live string-key service presence | Versioned typed exact requirements | Keep Agenticus semantics |
| Selection | Availability activates dependents | Host explicitly selects; Catalog never substitutes | Keep Agenticus policy |
| Active-plan stability | Provider change reloads dependent Fiber | Episode snapshot and operation route are immutable | Never hot-rebind an active Episode |
| Executable ownership | Fiber owns all mount effects | Host composer manually owns collaborators | Learn from Fiber |
| Withdrawal order | Dependents drain before provider disposal | Attachments and hosts use explicit ordered cleanup | Test a dependency tree; retain domain settlement truth |
| Reversibility boundary | Tracked acquisitions have inverses; external emissions do not | Internal cleanup plus append-only facts and uncertain external Effects | Adopt the boundary; never market universal rollback |
| Authority | Trusted ambient Node process | Installation-owned authority, custody, grants, fences | Never replace with injection |
| Composition data | Layered entry tree with stable IDs | Static profiles and host Python tuples | Add inspectability before configurability |
| Contribution semantics | Domain registries above Cordis | Typed Agenticus concepts and provider protocols | Share lifecycle, not one registry policy |
| Failure | Failed/Pending plus rollback and disposal | Bounded protocol codes and verified/unverified cleanup | Adapt rollback to fail-closed settlement |
| Durable truth | Configuration/runtime topology | History, snapshots, custody, route stores | Mount graph remains non-canonical operational state |
| Convergence | Quiescent confluence under independence and no failure | Deterministic reconstruction from serialized History | Keep properties and proofs separate |
| Isolation | Dependency visibility; sandbox explicitly out of scope | Motus territories plus host/provider boundaries | Do not call dependency injection a sandbox |

## Copy, adapt, reject

### Copy as architecture

1. **Separate identities.** Preserve package/source identity, descriptor
   identity, configured mount identity, and live incarnation as different
   values.
2. **One owned mount scope.** Every installed executable component should
   register its children, publications, background work, and cleanup under one
   deterministic withdrawal boundary.
3. **Domain-specific registries.** Share lifecycle machinery without forcing
   Hands, runtimes, custody, effects, and territories through one generic
   conflict algorithm.
4. **Inspectable effective composition.** Expose exact selected entries,
   provenance, dependency state, mount state, and incarnation without exposing
   credentials or executable handles.
5. **Real composition tests.** Test the public installation path, not only
   factories and adapters constructed directly.
6. **Provider-identity-aware readiness.** Treat a provider incarnation change
   as a topology change even when its descriptor or provided value compares
   equal.
7. **Dependent-first withdrawal.** Close admission, drain consumers, then
   release providers; do not assume a flat cleanup stack captures every
   dependency.
8. **Explicit effect boundary.** Classify each owned action as a tracked local
   acquisition, borrowed capability, or external emission before assigning any
   rollback claim.

These ideas should be independently implemented in Petrus vocabulary. No
Harness or Cordis source needs to be copied.

### Adapt to Agenticus constraints

1. Replace string `inject` with existing typed `CompatibilityRequirement` and
   explicit readiness policy: mandatory now, deferred, optional, or degraded.
2. Let a mount own **revocable leases and cleanup evidence**, not merely
   registrations. Unverified cleanup remains a first-class fail-closed result.
3. React to catalog/provider changes only for future composition readiness.
   An active Episode remains pinned to its `ResolutionSnapshot`; replacement
   requires explicit settlement and a newly resolved Episode, never transparent
   hot reload.
4. Add stable entry/provenance data only after the host has explicitly chosen
   a plan. Ordered overlays must not silently grant authority or substitute a
   provider.
5. Keep mount topology operational and rebuildable. Only accepted domain facts
   cross existing Impetus/Motus durability boundaries.
6. Replace author-asserted “inverse succeeded” with the strongest available
   domain cleanup evidence. Cleanup callbacks may initiate withdrawal, but a
   mount reports clean only when the owning provider contract verifies it.
7. Replace Cordis's indefinite inactivity for cycles or missing mandatory
   dependencies with a bounded, inspectable preflight result. A supported
   installation must fail clearly rather than wait forever for an impossible
   topology.
8. Use effect-order independence as a property-test target only for actions
   declared independent. Serialize exclusive authority, custody, provider
   emission, and canonical History through their existing owners.

### Reject

1. Ambient in-process access as an authority model.
2. Arbitrary module export inference or private runtime-loader APIs.
3. Indefinite `PENDING` as the default fate of a mandatory production
   requirement.
4. npm-style dynamic package discovery, HMR, or out-of-tree plugins as an
   initial Agenticus goal.
5. Renaming every descriptor, Hand, tool, adapter, provider, or contribution a
   “plugin.” Their distinct domain contracts are valuable.
6. Moving the composition substrate into Impetus or Motus, or making either
   depend on Agenticus.
7. Calling dependency visibility a sandbox or granting authority merely
   because a component declares a requirement.
8. Calling component disposal a rollback of canonical History, Activities, or
   externally visible Agenticus Effects.
9. Importing Cordis's key-only compatibility, inactive dependency cycles, or
   failure-free confluence assumptions into Agenticus's support claims.

## Candidate formed: owned, inspectable Agenticus installations

The evidence supports a possible **Value/CV candidate**, while the first
learning move remains a disposable technical experiment:

> Let an installation author select an exact compatible Agenticus composition,
> inspect why it is or is not ready, mount its executable runtime under one
> authority-aware lifecycle boundary, and obtain an honest cleanup outcome—
> without recreating provider-specific bootstrap, rollback, and close logic in
> every host.

The first experiment should **not** make every descriptor executable. It should
compare mount granularity and begin with the smallest likely fit: one exact
runtime-profile composer that accepts an already selected immutable snapshot.
Within that disposable model it should test a small ownership tree rather than
only a flat cleanup list: provider identity changes, dependent-first drainage,
partial acquisition rollback, and an explicitly non-revertible external
emission. Only repeated evidence across profiles may justify component-level
factories.

The [future-execution brief](future-execution-brief.md) defines the
discriminating behaviors, alternatives, falsifiers, staged experiments,
Customer Value promotion gate, candidate Delivery Stories, and exclusions.
No package installation, config-file syntax, HMR, provider ranking, universal
service locator, live-provider qualification, or public API naming is implied.

## Verification

- `[D]` `git ls-remote https://github.com/deepseek-ai/deepseek-harness.git HEAD
  refs/heads/master` pinned the researched source at
  `47f943859bef60e4160492346772ded9b24f765a`.
- `[D]` `git clone`, exact checkout, repository-tree inspection, and PDF review
  pinned `cordiverse/paper` at
  `948a07b369c62adb3b12e102458be5c18dfb69b9`; the title/authors, preprint
  warning, formal assumptions, system-boundary limits, and absence of an
  explicit repository license were checked against that revision.
- `[E]` `UV_FROZEN=1 uv run pytest -q
  tests/petrus/agenticus/catalog/test_resolution.py
  tests/petrus/agenticus/runtime/test_profiles.py
  tests/petrus/agenticus/runtime/test_pi_a2_host.py` passed all 102 tests in
  2.12 seconds.
- `[E]` Every relative Markdown link in this artifact resolves in the current
  source tree, and `git diff --check` reports no whitespace errors.

## Disposition

The original hunch is confirmed with a narrower center: Agenticus should not
copy Harness's “everything” slogan or Loader. The upstream Cordis paper
strengthens the case for exploring an **owned, dependency-aware mount** as the
missing executable complement to Agenticus's already stronger descriptor,
authority, and immutable-resolution model. Its own limits also require a more
careful phrase than “reversible mount”: only tracked composition acquisitions
are candidates for reversal; external emissions, durable History, and
uncertain provider outcomes are not.

The candidate shape is now documented deeply enough to execute later, but the
story is paused in Exploration until Experiment 1 is reactivated. Its evidence
must return the story to the Candidate Gate before the recommended promotion
decision. No roadmap item, Customer Value promise, public API, or
implementation commitment has been created.
