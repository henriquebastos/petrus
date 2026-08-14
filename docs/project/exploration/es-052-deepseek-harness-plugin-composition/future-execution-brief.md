# Customer Value candidate and exploration execution brief

## Purpose

This document is the durable restart surface for ES-052. It preserves enough
product, architecture, experiment, and delivery shape that a future Driver can
resume the inquiry without reconstructing this conversation or repeating the
DeepSeek Harness and upstream Cordis paper analyses.

Read this brief after the [source-grounded exploration](index.md). Before
changing production code, also re-read:

- [`CV16 — Agenticus composable agent infrastructure`](../../roadmap/cv16-agenticus-composable-agent-infrastructure/index.md);
- [`Installations own authority; Agenticus owns reusable machinery`](../../decisions/records/2026-08-03T0430Z-installations-own-authority-agenticus-owns-machinery.md);
- [`Petrus is a library, not a lifecycle-owning framework`](../../../product/principles.md); and
- the current Agenticus support matrix in [`README.md`](../../../../README.md#agenticus-support-matrix).

This is **Exploration Documentation**, not an accepted roadmap plan. Names,
interfaces, stages, and candidate stories below are working shapes. Promotion
remains a Navigator decision.

## Classification recommendation

Keep ES-052 paused in Exploration with a formed
**Value/Capability Value hypothesis using a Customer Value framing**. Do not
create a CV folder or code yet. Reactivation begins with Experiment 1; the
result determines whether the story returns to the Candidate Gate.

The distinction matters:

- The **mechanism hypothesis** is an authority-aware owned mount between a
  `ResolutionSnapshot` and a live runtime composition.
- The **Customer Value hypothesis** is that installation authors can compose,
  inspect, operate, and close supported Agenticus runtimes without duplicating
  provider-specific lifecycle orchestration.
- A successful mechanism spike does not prove the Customer Value. It may close
  as a Technical Story, refinement, or rejected abstraction if no second use
  demonstrates a meaningful installation-author outcome.

Petrus uses CV to mean Capability Value by default. If promoted, the candidate
can preserve the Navigator's Customer Value intent inside that established
taxonomy: the capability matters because it changes what an installation author
can safely do.

## Current story

### Initial signal

DeepSeek Harness appears to make every product subsystem a plugin. Its Cordis
substrate can mount model adapters, registries, persistence, tools, policies,
UI contributions, transports, and the agent loop itself while retaining one
small bootstrap kernel.

### Confirmed reading

Harness's decisive technique is not dynamic package discovery. It is a
dependency-aware Fiber that owns everything one mount contributes and retracts
those effects together. Its product capabilities are replaceable because
their executable lifetime, dependencies, and cleanup share a common substrate.

The upstream Cordis paper makes that mechanism more precise. It calls the two
goals temporal composability (tracked acquisitions can be withdrawn) and
spatial composability (dependency topology is declared and reactive). One live
Fiber records provider incarnation identity, drains dependents before providers,
and owns cleanup for tracked context transformations. The same paper bounds
the claim: external writes/sends are emissions outside automatic recovery;
inverse correctness is an author obligation; dependency visibility is not a
sandbox; key compatibility/versioning remains open; and confluence assumes
independent steps, quiescence, and no failed Fiber. Self-evolving agent
harnesses are proposed as future validation, not presented as established
evidence.

Agenticus already has the stronger semantic and authority model:

- typed, versioned descriptors and requirements;
- explicit host selection with no implicit substitution;
- immutable Episode resolution snapshots;
- installation-owned authority and Connection custody;
- scoped Hands, grants, Attachment epochs, effect fences, and honest cleanup;
- provider-specific runtime profiles and adapters; and
- an explicit rule that Agenticus composes Impetus and Motus without becoming
  a foundational dependency or lifecycle-owning application framework.

What Agenticus does not yet generalize is the executable passage after exact
resolution. Today a host-specific composition root creates storage, custody,
adapters, providers, ledgers, rollback, and close ordering by hand.

The paper therefore strengthens the same attractor rather than creating a
second candidate: Agenticus may need an operational composition owner, while
Petrus's append-only History, Petri causality, immutable Episode plans,
provider-specific cleanup evidence, and external-effect uncertainty remain the
governing semantics.

### Tension

The opportunity can be read too broadly:

- **Too narrow:** add a disposable helper around one Pi constructor, creating
  no reusable ownership semantics.
- **Too broad:** turn every descriptor into a dynamically loaded plugin,
  introduce a service locator, and weaken Agenticus's authority boundaries in
  pursuit of framework flexibility.
- **Product-shaped center:** give installation authors one exact, inspectable,
  authority-preserving way to materialize and own a selected composition while
  retaining domain-specific component semantics.

### Confirmed attractor

**Owned, inspectable Agenticus installations.**

The center is not “everything is a plugin.” It is that a resolved plan should
have an executable owner with explicit provenance, readiness, authority,
incarnation, rollback, and settlement.

## Customer Value hypothesis

### Primary beneficiary

An **installation author**: the developer or team embedding Petrus Agenticus in
a concrete host application and owning provider/model enablement, credentials,
configuration, process lifecycle, support claims, and user experience.

Hamsterdan is current evidence of this role, not the definition of it. The
design must remain reusable by another installation without importing
Hamsterdan concepts.

### Secondary beneficiaries

- **Operator:** needs to know what exact composition is selected, why it is or
  is not ready, which incarnation is live, and whether cleanup is proven.
- **Capability/provider integrator:** needs a bounded extension contract that
  cannot silently claim support, obtain ambient authority, or corrupt another
  domain's lifecycle.
- **Petrus maintainer:** needs one place to pin composition rollback,
  inspection, and lifecycle behavior instead of auditing bespoke host wiring.

### Job to be done

> When I enable an Agenticus runtime profile in my Petrus installation, I want
> to resolve and inspect the exact composition, materialize only that approved
> composition, operate it through its public contract, and close it with an
> honest cleanup result, so that adding or replacing a supported runtime does
> not require rebuilding security-sensitive lifecycle machinery in my host.

### Candidate value statement

> Agenticus turns an installation-selected compatible capability plan into an
> owned, inspectable runtime composition while the installation retains
> authority and product policy.

### Observable outcomes

A promoted Value should eventually make these statements true through public
or operator-inspectable behavior:

1. An installation author can ask for an **effective composition plan** and see
   exact selected identities, versions, provenance, requirements, readiness,
   and support classification without requesting credentials or starting work.
2. A compatible supported plan can be mounted through one host-facing
   composition contract rather than a new provider-specific acquire/rollback/
   close loop in each application.
3. Startup failure names the failed entry or responsibility and reports whether
   already acquired resources were cleanly withdrawn.
4. An active mount exposes a detached inspection view with plan identity,
   incarnation, lifecycle state, and bounded diagnostics—never credentials,
   clients, callbacks, mutable stores, or authority handles.
5. Close is explicit, idempotent at the public boundary, and distinguishes
   verified cleanup from uncertainty. Uncertainty cannot be presented as
   success.
6. Catalog or provider changes affect future resolution/readiness but never
   mutate or transparently hot-reload an active Episode.
7. Support remains evidence-based. Registering a composer or descriptor does
   not make a profile supported.

### Structural success signals

Do not use line-count reduction as the main proof. The useful signature is
mechanical:

- installation hosts no longer duplicate collaborator acquisition,
  reverse-order rollback, and aggregate close loops for each adopted profile;
- one public operation/report surface explains plan, readiness, mount, and
  cleanup states;
- direct construction tests are supplemented by tests through the real
  registration → resolution → mount route;
- existing Connection, Hands, Attachment, runtime, and effect fences remain
  the enforcing boundaries; and
- a second composition or host can reuse the mount semantics without one-use
  branches in the substrate.

## What this Value is not

The candidate does not promise:

- an open third-party plugin marketplace;
- automatic discovery or installation of Python packages;
- hot module replacement;
- transparent provider substitution;
- one universal Agent, Session, Runtime, Tool, or Provider abstraction;
- a global service locator;
- in-process isolation or a sandbox merely because dependencies are declared;
- support for every existing Agenticus descriptor or adapter;
- live-provider, model-quality, or credential qualification;
- exactly-once external effects;
- automatic migration of active Episodes to replacement components;
- ownership of the host application's process lifecycle; or
- movement of Agenticus composition into Impetus or Motus.

These are separate possible inquiries. They must not ride silently on this
candidate.

## Settled constraints to carry forward

These are current project truths, not experiment variables.

### Ownership and dependency direction

1. The installation remains the security principal and supplies concrete
   authority, provider/model enablement, policy, workflows, and UX.
2. Agenticus may own reusable composition machinery but not installation
   authority or product policy.
3. Impetus and Motus remain usable without Agenticus and never depend on it.
4. Motus continues to own execution territory and Activity custody. A mount may
   own a reference or lease lifecycle only through the Motus-owned contract
   available to the selected profile; it never makes that territory an
   Agenticus responsibility.
5. Agenticus does not own canonical History. Composition topology and mount
   state are operational views unless an existing domain boundary records a
   real process fact.

### Plan and identity

6. `Catalog` remains a descriptor and compatibility authority, not an
   executable object registry unless later evidence explicitly overturns that
   boundary.
7. The host explicitly selects exact descriptors. Resolution never searches
   for a more convenient provider, account, runtime, territory, or
   Continuation.
8. A successful `ResolutionSnapshot` is immutable. Later registration,
   disablement, replacement, or readiness changes do not rewrite it.
9. Package/source identity, descriptor identity, registration identity, mount
   incarnation, Agent Connection, Thread, Episode, Turn, territory lease, and
   provider session remain distinct.

### Authority and secrecy

10. Composition planning and dry-run inspection request no credentials and
    materialize no provider authority.
11. A mount receives only the authority explicitly supplied by the host for
    the selected composition. Dependency declaration is not itself authority.
12. Credentials, raw provider state, clients, callbacks, and mutable stores do
    not enter snapshots, reports, canonical History, or portable inspection
    data.
13. Stale Connection, Attachment, grant, execution, and effect authority
    remain fail-closed at their existing enforcing seams.

### Lifecycle and recovery

14. Partial startup deterministically attempts withdrawal of every owned
    acquisition completed before failure and records the resulting cleanup
    evidence.
15. Close does not claim more than collaborators prove. Cleanup uncertainty is
    represented explicitly and prevents a clean verdict.
16. An active Episode is never transparently rebound. Replacement requires an
    explicit lifecycle boundary and a newly resolved composition.
17. Recovery preserves stable logical work identity separately from
    process-scoped mount incarnation and fences.
18. No generic mount can manufacture exactly-once execution from at-least-once
    external effects.
19. Every composed capability is classified as **owned acquisition**,
    **borrowed capability**, or **external emission**. Only owned acquisitions
    receive mount cleanup obligations; borrowed capabilities are not closed by
    the mount, and external emissions are never described as automatically
    reversed.
20. Dependency withdrawal is dependent-first. A provider remains available
    while admitted consumers drain, then its own cleanup runs. Flat
    reverse-registration order is acceptable only where the dependency graph
    proves it equivalent.
21. A cleanup callback initiating without error is not proof of cleanup.
    Verified/uncertain judgment comes from the existing domain/provider
    contract, and independent cleanup attempts continue after one failure.

### Product and support

22. Descriptor/catalog presence, factory registration, installation probing,
    and support status are separate facts.
23. The first production-facing route remains the supported scripted Pi A2
    Local lifecycle. Existing experimental/qualification-only labels do not
    widen because a mount exists.
24. Petrus remains a composable library. The host calls plan/mount/close; the
    substrate does not seize the host's event loop, process, or configuration
    system.

## Architecture hypothesis

### Proposed passage

```text
host policy and registrations
            │
            ▼
       Agenticus Catalog
            │ exact explicit request
            ▼
 immutable ResolutionSnapshot
            │
            ▼
  composition preflight / plan view ────▶ blocked report (no authority)
            │ ready and explicitly mounted
            ▼
     owned mount incarnation
       ├─ exact public runtime/operation surface
       ├─ detached inspection view
       ├─ owned children and leases
       └─ rollback / close / cleanup evidence
```

The mount does not replace Catalog, Episode Attachment, Hands, Connection
custody, Motus territory, or provider adapters. It owns their composition and
operational lifetime for one approved installation plan.

### Three lifecycle zones

The Cordis paper makes one additional boundary mandatory. “Rollback” is too
coarse unless the operation is classified first:

| Zone | Examples | Required semantics |
| --- | --- | --- |
| Plan/preflight | Descriptor compatibility, provenance, provider readiness | Detached and authority-free; no cleanup needed |
| Composition acquisition | Child mounts, listeners, local stores, registrations, explicitly owned leases | Register cleanup immediately; on failure withdraw dependents first and preserve verified/uncertain evidence |
| Domain execution/emission | Activity invocation, provider mutation, message/send, accepted History fact | Existing custody, fencing, idempotency, terminal, and compensation semantics; never silently “rolled back” by the mount |

A collaborator can move between the first two classifications only through an
explicit mount act. Nothing moves from the emission zone back into a tracked
composition acquisition merely because one Fiber or mount initiated it.

### Candidate ownership topology

The disposable model should represent a small tree, not start with a general
dependency-injection framework:

```text
mount incarnation (exact snapshot + registration + provider identity)
├── borrowed host authority                 [never mount-closed]
├── owned provider/runtime acquisition
│   ├── owned child registration/task
│   └── borrowed domain gateway             [domain settlement owns truth]
└── detached inspection projection
```

Construction records an owned cleanup only after acquisition succeeds.
Withdrawal first closes admission, then drains and disposes dependents, and
finally asks providers to settle. Independent siblings should all receive a
cleanup attempt even if one fails. The terminal mount report aggregates the
strongest honest evidence; it does not turn callback completion into verified
provider cleanup.

### Candidate identities

Working vocabulary should preserve at least these identities:

| Identity | Answers | Must not be confused with |
| --- | --- | --- |
| Source/package | Where did executable code and metadata come from? | Descriptor compatibility |
| Descriptor | What exact versioned capability contract is offered? | A live implementation |
| Registration/entry | What did this host make available under policy? | Package or descriptor identity |
| Resolution snapshot | What exact plan was accepted for this Episode/composition? | Current mutable Catalog state |
| Mount incarnation | Which live materialization owns current resources? | Durable Thread, Episode, or provider session |
| Domain identities | Which Connection, Episode, Turn, grant, territory, and operation are involved? | Mount incarnation |

Names are provisional. The separations are not.

### Candidate lifecycle

The experiment may use a small state model, but should not publish it before
evidence:

```text
registered
    │ exact resolution
    ▼
planned ───────────────▶ blocked
    │ explicit mount
    ▼
mounting ──failure─────▶ failed-clean | failed-unverified
    │ success
    ▼
active
    │ explicit close
    ▼
closing ───────────────▶ closed-clean | closed-unverified
```

Required semantic points:

- `blocked` is a pre-authority planning result, not a half-started runtime;
- every owned acquisition completed before startup failure receives its
  cleanup attempt and the result remains honest about uncertainty;
- close can be retried or re-observed without minting a second clean claim;
- cleanup uncertainty is terminal evidence, not a warning that an ordinary
  replacement may ignore; and
- provider/catalog changes may invalidate future plans but do not create an
  `active → active` hot-reload edge.

## Mount granularity alternatives

The first experiment must compare these alternatives explicitly.

| Alternative | Shape | Benefit | Main risk | Current recommendation |
| --- | --- | --- | --- | --- |
| A. Per-descriptor factories | Connection, Program, Runtime, Hands, Territory, Continuation, and Effect each mount independently | Maximum apparent composability | Turns domain values and authority into generic services; dependency order and cleanup become a new framework | Reject as starting point |
| B. Exact runtime-profile composer | One host registration materializes one exact compatible snapshot/profile | Smallest bridge over current composition roots; preserves profile-specific truth | May duplicate collaborators across future composers | **Start here** |
| C. Grouped composition bundle | A bundle contributes descriptors plus one or more typed composers | Can share coherent families without per-leaf plugin fiction | Bundle identity and overlay policy may become premature packaging | Keep as fallback if two profiles prove grouping |
| D. Status quo host constructor | Every host calls provider-specific constructors directly | No new abstraction | Repeats rollback, inspection, and lifecycle ownership; snapshots remain disconnected from execution | Control case |

Alternative B is deliberately conservative. The current Pi A2 composer already
knows the correct acquisition and cleanup order for storage, materialization,
custody, body store, operation ledger, adapter, and environment. The experiment
should first determine whether one exact profile composer can expose that
ownership consistently. Only concrete duplication across a second profile may
justify factoring smaller mountable components.

### Why not put factories directly in `CapabilityDescriptor`?

Descriptors are portable, serializable, provider-neutral data. An executable
factory would introduce imports, closures, host resources, and process identity
into the compatibility surface. It would also make a descriptor's presence look
like executable readiness and support. Keep these separate unless evidence
shows a typed registration cannot preserve the relation honestly.

### Why not put implementations directly in `Catalog`?

Catalog currently answers exact registration, enablement, compatibility, and
snapshot questions without importing adapters. Making it an implementation
container would mix policy facts with live collaborators and complicate
inspection, serialization, recovery, and testing. A separate host-owned
registration/composition surface is the safer initial boundary.

## Hypotheses and falsifiers

### H1 — Owned mounts remove repeated lifecycle machinery

**Hypothesis:** one profile composer plus common mount ownership removes the
need for each installation to write its own partial-start rollback, detached
inspection, and aggregate close protocol.

**Falsified when:** the “common” layer merely wraps one constructor, delegates
all meaningful ownership back to profile code, or adds more state transitions
than it makes universal.

### H2 — Exact-profile granularity is sufficient initially

**Hypothesis:** the useful reusable unit is one exact runtime-profile composer,
not each descriptor kind.

**Falsified when:** two qualified profile composers duplicate the same
independently meaningful acquisition/withdrawal unit and cannot share it
without component-level registration.

### H3 — Inspection is a real product capability

**Hypothesis:** plan/readiness/mount/cleanup inspection lets installation
authors and operators make decisions they cannot safely make from current
descriptor snapshots and provider-specific errors.

**Falsified when:** the report only restates the snapshot, exposes no actionable
readiness or cleanup distinction, or requires private handles to be useful.

### H4 — Active immutability and future readiness can coexist

**Hypothesis:** registrations can change future plan readiness while active
mounts remain pinned and explicitly settled.

**Falsified when:** maintaining both truths requires hidden mutation of a
snapshot, silent rebinding, or a second canonical state that can contradict
History/custody.

### H5 — Authority can remain host-owned without ambient context

**Hypothesis:** a composer can receive narrowly typed host-supplied authority
and capabilities without a global service locator or credential-bearing
configuration graph.

**Falsified when:** real profiles require arbitrary context lookup, descriptors
must carry secrets, or the mount must bypass existing custody/Hands boundaries.

### H6 — The capability deserves a Value boundary

**Hypothesis:** at least two concrete composition/adoption routes share the
mechanism and the public plan/mount/close experience changes how Petrus can
describe Agenticus.

**Falsified when:** only one route benefits, the result is invisible to an
installation author, or the change is adequately described as local
refactoring/refinement.

### H7 — A small ownership tree is enough

**Hypothesis:** parent/child ownership plus explicit provider identity is
sufficient to guarantee dependent-first withdrawal without introducing a
general reactive runtime.

**Falsified when:** correct teardown requires hidden service lookup, arbitrary
graph mutation, or a scheduler that duplicates Impetus/Motus responsibilities.

### H8 — Internal reversal and external recovery remain separable

**Hypothesis:** the mount can provide useful partial-construction rollback while
classifying Activities and provider Effects as non-revertible domain
executions governed by their current evidence protocols.

**Falsified when:** a generic cleanup result must erase or reinterpret History,
claim an ambiguous emission did not occur, or flatten verified and uncertain
provider settlement into one status.

## Experiment program

Every experiment remains under ES-052 until promotion. Disposable code, test
fixtures, reports, and conclusions must be committed with the Exploration; no
untracked spike branch is authoritative evidence.

### Experiment 0 — Source and fit analysis

**State:** complete.

**Question:** what does Harness actually make pluggable, what remains kernel,
and where does that pattern fit or conflict with Agenticus?

**Result:** the reusable center is lifecycle-owned, dependency-aware
composition.
The upstream paper refines this to dependency-aware ownership of **tracked
acquisitions**, not reversal of external emissions. Agenticus should retain
typed exact resolution, authority fences, History, and provider cleanup
evidence rather than copy Cordis injection or Loader behavior. See [the main
exploration](index.md).

### Experiment 1 — Disposable exact-profile mount model

**Learning intent:** determine whether one exact-profile composer plus common
mount ownership has a coherent responsibility independent of Pi A2 internals.

**Method:** create an Exploration-only model using fake typed profile
composers and inert resources. Do not edit Agenticus production APIs yet.

**Required probes:**

1. exact selected snapshot maps to one and only one registration;
2. unregistered, disabled, incompatible, stale, or ambiguous plans fail before
   authority acquisition;
3. a provider incarnation change is visible even when descriptor and provided
   values remain equal, but never mutates an active snapshot;
4. every collaborator is explicitly classified as owned, borrowed, or an
   external emission boundary;
5. acquisition order is explicit, admission closes before drainage, and
   dependents withdraw before their providers;
6. failure at every acquisition position leaves either a proven-clean or
   explicit unverified result;
7. a cleanup callback that returns unverified evidence does not become clean
   merely because the callback completed;
8. cleanup exceptions do not prevent later independent cleanup attempts;
9. borrowed collaborators are never closed by the mount;
10. one fake external emission remains an observed/uncertain domain outcome
    after mount close and is never labeled reversed;
11. close is idempotent and returns the same bounded terminal judgment;
12. inspection values are detached, immutable, deterministic, and secret-free;
13. changing the Catalog after mount changes future resolution only;
14. cycles and mandatory missing dependencies produce bounded blocked reports
    instead of permanent hidden inactivity;
15. independent sibling acquisition/withdrawal permutations produce
    observationally equivalent terminal reports while dependent order remains
    fixed; and
16. two simultaneous mount incarnations cannot accidentally share mutable
   ownership unless the host explicitly registered a shared collaborator.

**Pass condition:** the model has one clear responsibility—own materialization
and withdrawal of an exact plan—and its generic code contains no Pi, provider,
credential, Hands-tool, Motus-private, or host-application branching.
Independent composition actions may commute, but no test should infer replay
determinism or failure confluence from that result.

**Stop condition:** if generic code cannot own meaningful rollback or inspection
without learning profile internals, reject the mount abstraction or narrow it
to a report-only capability.

### Experiment 2 — Scripted Pi A2 parity through the mount

**Learning intent:** prove that the abstraction can carry one real supported
composition without weakening behavior or support claims.

**Method:** adapt the public `compose_pi_a2_scripted_runtime` route behind one
exact profile composer in Exploration or an unpromoted internal branch. Keep
the direct public route intact as the behavioral oracle.

**Required probes:**

1. planning and mount readiness request no installation authority;
2. the mounted route runs the same public scripted Episode operation,
   workspace, Hands, output, Continuation, replay, acknowledgement, and close
   behavior as the direct route;
3. all current stale Connection, Attachment, grant, execution, and effect
   publication tests remain green;
4. real process-death classification remains restart-indeterminate with no
   redispatch;
5. the mounted path introduces no credentials into snapshots, reports,
   operation ledgers, bodies, workspaces, or History;
6. aggregate cleanup and host close preserve current fail-closed behavior; and
7. direct construction remains available until the mounted path proves a
   strictly clearer public composition contract.

**Pass condition:** both routes have equivalent supported behavior and the
mount owns a real lifecycle/reporting responsibility rather than only renaming
the constructor.

**Stop condition:** any authority request moves earlier, any cleanup claim
widens, replay changes, or the mount needs private mutable escape hatches.

### Experiment 3 — Adversarial lifecycle and replacement matrix

**Learning intent:** test the exact places where Cordis-style reactivity would
conflict with Agenticus snapshot and authority semantics.

**Required cases:**

- registration disabled before planning;
- registration disabled after planning but before mount;
- registration changed after mount;
- provider incarnation replaced with an equal descriptor/provided value;
- attempted replacement while an Episode is active;
- dependency cycle or missing mandatory provider at preflight;
- startup failure before and after authority materialization;
- provider withdrawal while a dependent is draining;
- child cleanup verified, refused, raised, or timed out;
- external Effect outcome indeterminate while mount close proceeds;
- close called concurrently or repeatedly;
- process restart with a prior active/uncertain incarnation;
- same descriptor identity registered with conflicting composer provenance;
- two entries claiming one exclusive authority/territory; and
- inspection during mounting, active operation, closing, and uncertainty.

**Pass condition:** every case has one bounded, deterministic, fail-closed
outcome and none silently mutates an active snapshot or accepted domain fact.

### Experiment 4 — Second-use and host-adoption test

**Learning intent:** determine whether the mechanism deserves Delivery and
possibly a Value boundary.

**Preferred evidence order:**

1. a second hermetic Agenticus profile or composition inside Petrus reuses the
   mount without type-erasing special cases; then
2. a real host such as Hamsterdan adopts the public plan/mount/close surface and
   removes its own lifecycle orchestration while keeping host policy,
   operation-route custody, and user experience.

Cross-repository adoption is a separate coordinated story and must not be
silently performed from this Exploration.

**Pass condition:** reuse is structural, not merely both callers invoking a
large conditional factory. The second adopter retains its authority and policy
and gains an inspectable behavior route.

**Stop condition:** the second route needs incompatible lifecycle semantics,
or shared machinery forces provider-specific types through neutral contracts.

### Experiment 5 — Packaging and external extension inquiry

**State:** deliberately unopened.

Only open this inquiry after mount semantics and two uses are proven. Questions
about entry points, package metadata, external plugins, config overlays, process
isolation, signing, trust, or compatibility distribution are not prerequisites
for owned composition and would otherwise dominate the exploration too early.

## Evidence plan

A promotion-quality evidence package should include:

- exact tests for each state transition and failure position;
- property/permutation tests for deterministic registration, resolution, and
  observationally equivalent independent cleanup ordering where appropriate;
- dependency-order tests proving dependents drain before providers;
- owned/borrowed/emission classification fixtures, including an external
  outcome that mount close does not reinterpret;
- real public composition tests, not only direct factory unit tests;
- one inspectable plan/readiness report fixture with secret-field denial tests;
- one complete supported scripted Pi A2 operation route;
- restart and cleanup-uncertainty evidence;
- package-boundary/static checks proving Impetus/Motus do not depend on
  Agenticus and provider-specific types do not leak;
- a second-use fit map or adoption result;
- explicit support-matrix review showing no profile was promoted by inference;
  and
- `scripts/check full` at any production-code checkpoint.

The report should compare expected and observed behavior for each Customer
Value outcome. It should not claim value from green unit tests alone.

## Promotion gate

### Promote toward Delivery when all are true

1. Experiment 1 proves a coherent mount responsibility and no one-use wrapper.
2. Experiment 2 preserves the complete supported scripted Pi A2 behavior and
   all authority/recovery/cleanup invariants.
3. Inspection exposes at least one actionable readiness or cleanup judgment
   unavailable from a bare `ResolutionSnapshot`.
4. Experiment 4 provides a credible second use or installation-author adoption
   path.
5. The candidate can name one public capability promise without claiming a
   plugin ecosystem or unsupported providers.
6. Experiment evidence proves that composition-acquisition rollback never
   broadens History, Activity, external Effect, or cleanup-certainty claims.
7. The smallest Delivery boundaries and concrete validation routes are clear.

Promotion is still a Navigator decision after these conditions are met.

### Keep in Exploration when

- the owned mount is coherent but second-use/customer evidence is missing;
- mount granularity remains unresolved;
- the only demonstrated benefit is internal cleanup consolidation; or
- a provider qualification or host-adoption dependency has not yet been
  authorized.

### Narrow to a Technical Story or Refinement when

- only deterministic rollback/close reuse is valuable;
- inspection has no public/operator decision value;
- one existing composer can be simplified without changing the Agenticus
  capability promise; and
- no broader roadmap arc is needed.

### Archive or reject when

- profile-specific composition is more truthful and less code than the common
  mount;
- meaningful authority requires ambient context or bypassing existing fences;
- mount state competes with canonical History or custody;
- active snapshots cannot remain immutable;
- useful mount cleanup requires claiming that external emissions were undone;
- cleanup cannot be generalized honestly; or
- no second composition or host benefits.

## Candidate roadmap handoff if promoted

Do not create these roadmap items until promotion. This is a handoff seed, not
a commitment or numbering decision.

### Suggested Value/CV seed

**Working title:** Owned, inspectable Agenticus installations

**Intent:** Let Petrus installation authors select, explain, materialize, and
close supported Agenticus runtime compositions through one
authority-preserving host contract instead of rebuilding provider-specific
lifecycle orchestration.

**Potential done boundary:** Agenticus can publicly describe one stable
plan/readiness/mount/close capability, the supported scripted Pi A2 route uses
it without weaker semantics, and a second composition or host proves reuse.
No dynamic plugin ecosystem or wider provider support is implied.

### Candidate Delivery Stories

1. **Owned mount semantics.** Prove exact-plan materialization, incarnation,
   rollback, close, cleanup uncertainty, and active-snapshot immutability.
2. **Inspectable composition planning.** Give installation authors a detached,
   secret-free effective plan and readiness/failure report.
3. **Supported Pi A2 adoption.** Carry the scripted Pi A2 lifecycle through the
   mount with direct-route parity and full restart/cleanup evidence.
4. **Second composition or host adoption.** Prove the mechanism is reusable and
   remove duplicated lifecycle orchestration from one independent route.
5. **Public contract and support coherence.** Document extension boundaries,
   support semantics, operator behavior, licensing, and migration without
   implying package discovery or provider qualification.

### Candidate User Stories

- As an installation author, I can inspect the exact selected composition and
  why it is ready or blocked before authority is requested.
- As an installation author, I can explicitly mount a supported composition
  and receive only its public runtime/operation surface.
- As an operator, I can inspect lifecycle incarnation and cleanup outcome
  without seeing secrets or mutable internal handles.
- As an installation author, I can change future enablement without silently
  changing active Episode execution.
- As a host adopter, I can use the common composition contract while retaining
  my product policy, operation custody, and process lifecycle.

### Candidate Technical Stories

- typed host registration and exact-profile composer contract;
- deterministic mount ownership and construction-withdrawal state machine;
- detached plan/readiness/mount inspection values;
- authority-safe composition context without a service locator;
- parity fixture between direct and mounted Pi A2 routes;
- adversarial restart/replacement/cleanup matrix; and
- package and dependency-direction enforcement.

### Version intent

No version target is assigned in Exploration. If promoted as a public
installation-author capability, this would likely warrant a pre-release minor
capability boundary rather than a patch. If narrowed to internal lifecycle
consolidation, ordinary technical/refinement versioning applies.

## Open questions

These remain real decisions for experiments, not gaps to fill by assumption:

1. Is the first public unit an exact runtime-profile composer, a grouped
   composition, or another domain name that avoids “plugin” entirely?
2. Does one mount correspond to a host installation, one selected profile, one
   Agent Connection, one Episode family, or another bounded ownership unit?
3. Which collaborators are mount-owned versus borrowed from the host or an
   Episode? Borrowed collaborators must not be closed by the mount.
4. Is startup/close synchronously bounded, async-native, or expressed through
   an operation protocol? Existing profile behavior should decide, not Cordis.
5. What exactly makes a registration ready before authority materialization?
6. How should a plan prove that runtime installation facts still match the
   selected descriptor without treating mutable probe state as snapshot truth?
7. What state, if any, must survive process restart? A reconstructed mount
   incarnation must not pretend to be the old process.
8. Can cleanup uncertainty block only replacement of the affected registration,
   or the whole installation? The authority/custody boundary should decide.
9. What detached diagnostic vocabulary is universal enough to expose without
   erasing provider-specific failure codes?
10. How does a host register shared stores or providers without accidental
    double ownership and double close?
11. Is configuration data part of the portable plan, host policy, or a private
    composer input? Secrets are never plan data.
12. Does the current one-per-`DescriptorKind` selection constrain future
    composition bundles, and is that constraint valuable or merely current?
13. What second use provides honest evidence without promoting an unsupported
    provider profile?
14. Is external package discovery ever a user need, or only architectural
    fascination from the Harness comparison?
15. Is a strict ownership tree sufficient, or does a real profile contain
    shared/exclusive dependencies that require a bounded directed acyclic
    graph? Cycles must be reported, not left inactive indefinitely.
16. Which provider-incarnation identity can readiness observe without placing
    a live object in the portable descriptor or snapshot?
17. Can all composition actions be classified as owned, borrowed, or emission,
    or is a fourth category needed for transferred custody? If so, which domain
    contract proves the transfer?
18. Which cleanup outcomes are universally `verified`/`unverified`, and which
    provider-specific dispositions must remain intact in nested reports?
19. Does reactivity need a background reconciler at all, or can explicit host
    plan/mount/close calls provide the useful value with less framework
    ownership?

## Risk register

| Risk | Failure signature | Mitigation / experiment |
| --- | --- | --- |
| Framework gravity | Agenticus starts owning host config, process, event loop, or arbitrary services | Keep explicit plan/mount/close calls and test host ownership |
| False security | Declared dependencies are described as permissions while code retains ambient access | Keep authority in typed host-supplied custody/Hands contracts |
| Identity collapse | Descriptor, registration, incarnation, Episode, or provider session IDs become interchangeable | Separate value types/views and test mismatch refusal |
| Second truth | Mount state contradicts History, route custody, or Connection state | Keep operational view derived/bounded; record domain facts only at existing doors |
| Premature per-component plugins | Connection/Hands/Territory become generic services | Start with exact-profile composer; demand two-use evidence before extraction |
| Silent support expansion | Registered composer is read as supported provider | Preserve support matrix and qualification gates independently |
| Hidden hot reload | Catalog update mutates active work | Pin snapshot and reject replacement until explicit settlement |
| Cleanup optimism | reverse disposal logs an error but reports closed | Aggregate verified/unverified evidence and fail closed |
| Rollback overclaim | external emission or History fact is described as reverted | Classify actions before mount; test an indeterminate emission through close |
| Teardown inversion | provider closes while consumers still need it to drain | Encode ownership dependencies and test dependent-first withdrawal |
| Reactive-runtime creep | readiness starts a background scheduler or mutates active work | Prefer explicit host operations; keep observations detached and future-facing |
| Formal-assumption drift | Cordis confluence is cited as proof under failure or external effects | Record assumptions; test only independent local composition permutations |
| Vocabulary collision | Context, Effect, Scope, Event, or transaction is mistaken for an existing Petrus concept | Use Petrus-specific names and document the semantic boundary in public contracts |
| Loader topology gaps | direct factory tests pass while real composition fails | Require real registration → resolution → mount tests |
| API/name bloat | many new generic types appear before one route proves value | Keep experiment vocabulary provisional and production surface minimal |
| Packaging distraction | entry points, overlays, signing, or marketplace precede lifecycle proof | Defer Experiment 5 |
| License drift | Cordis implementation or paper text is translated without a valid reuse basis | Independently implement; review Harness's MIT provenance and the paper repository's lack of an explicit license at the pinned revision before any copied material |

## Carry Forward Notes

Preserve these implementation-relevant findings if the candidate promotes:

1. The Harness/Cordis pattern worth carrying is **provider-identity-aware
   dependency topology plus Fiber-owned tracked acquisitions**, not npm,
   export-shape inference, or a universal rollback claim.
2. Agenticus `Catalog` and `ResolutionSnapshot` are already more expressive for
   compatibility and safer for active work than Cordis string injection.
3. Cordis provider replacement reloads dependents; Agenticus must instead pin
   active Episode plans and apply changes to future composition readiness.
4. Domain-specific registries are a feature. Shared lifecycle does not justify
   one universal contribution interface.
5. Mount lifecycle is operational host state. Do not reuse Impetus
   `LifecycleScope`, which is canonical workflow-generation truth.
6. The existing Pi A2 host composition root is both the first pressure case and
   the behavioral oracle; preserve its ordered authority, replay, and cleanup
   semantics before refactoring.
7. Hamsterdan demonstrates real installation-owned descriptor selection and
   route custody. Adoption should reduce infrastructure duplication without
   moving Hamsterdan product policy into Petrus.
8. Inspection must shape down: detached values and bounded codes only, no live
   collaborators.
9. Test the mechanism's semantic signature—ownership, rollback, identity,
   readiness, and cleanup—not source-line ratios.
10. Clean architectural reimplementation needs no Harness source copy. Any
    substantial source reuse requires MIT notice/provenance review for both
    Cordis/Shigma and DeepSeek modifications.
11. The upstream paper repository is a changing preprint and has no explicit
    license at the pinned revision. Cite its claims, re-check newer versions
    deliberately, and do not treat it as an implementation reuse grant.
12. Cordis's inverse is author-supplied and cannot recover external emissions.
    Agenticus should trust provider cleanup only to the degree its existing
    evidence contract verifies it.
13. Provider identity—not merely equal descriptor/value—is the useful trigger
    for future readiness; it is not permission to mutate active Episodes.
14. Dependent-first withdrawal is a distinct invariant from LIFO cleanup. Test
    both where a profile mixes dependency edges and independent siblings.
15. Cordis confluence excludes failure and depends on independence and
    quiescence. Never cite it as Impetus replay or external-effect safety.

## Exact resume route

When this exploration is reactivated:

1. Read project instructions, current briefing, product principles, and this
   ES in the normal Ariad orientation order.
2. Confirm ES-052 is still `Paused` and that no later decision or roadmap
   item superseded it.
3. Read current CV16 status and Agenticus support matrix. Do not infer that
   additional profiles became supported.
4. Inspect the current implementations of:
   - `petrus.agenticus.catalog.descriptor`;
   - `petrus.agenticus.catalog.resolution`;
   - `petrus.agenticus.runtime.profiles`;
   - `petrus.agenticus.runtime.pi_a2_host`; and
   - current Connection, Attachment, Hands, and effect cleanup/fence contracts.
5. Run the then-current focused Catalog/profile/Pi A2 host suites before
   designing the experiment. The historical baseline was 102 passing tests on
   2026-08-13; test count is not a future target, but changed failures or
   contracts are evidence.
6. Use the pinned DeepSeek commit and pinned Cordis paper commit
   `948a07b369c62adb3b12e102458be5c18dfb69b9` for historical claims. The paper
   is an actively revised preprint; inspect a newer version only as a clearly
   separated evolution check and never silently rewrite the baseline.
7. Re-read Impetus event-History lifecycle scope and firing semantics before
   using “context,” “event,” “effect,” “scope,” “transaction,” “rollback,” or
   “replay” in the experiment. Preserve their Petrus meanings.
8. Render a new Plan Checkpoint for **Experiment 1 only**. Keep its code and
   fixtures inside the Exploration until the learning result supports
   production work.
9. Compare exact-profile composer, grouped bundle, and status quo. Do not begin
   with per-descriptor factories.
10. Include the owned/borrowed/emission classification, provider-incarnation
    change, dependent-first drainage, unverified inverse, cycle, and
    non-revertible emission probes in Experiment 1.
11. Record experiment observations, refutations, and disposition in ES-052.
12. Return to the Promotion Gate. Create roadmap files only after explicit
    Navigator promotion.

## Reactivation triggers

Bring ES-052 back into attention when any of these occurs:

- a second Agenticus profile or installation repeats acquire/rollback/close
  machinery;
- a host needs an operator-visible explanation of composition readiness;
- support work needs to distinguish registered, installed, qualified, ready,
  mounted, and cleanly closed states;
- cleanup or replacement bugs reveal missing common ownership;
- Hamsterdan or another host requests a reusable composition contract;
- a provider-extension proposal starts introducing a service locator or
  ambient capability context; or
- the Navigator explicitly promotes the candidate or asks to run Experiment 1.

## Driver recommendation

Preserve this as a strong Value hypothesis but execute it later as a sequence
of Exploration experiments. Start with exact-profile mount ownership, not a
plugin framework. Promote only when a real installation-author behavior and a
second use prove that the abstraction changes Petrus's public capability rather
than merely reorganizing one constructor.
