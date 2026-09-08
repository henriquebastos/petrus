# 1 ES-052 execution brief

## 1a Resume boundary

ES-052 is paused before Experiment 1. The [exploration](index.md) owns the
pinned source findings. This file owns the experiment plan. The candidate is
that installation authors can resolve, inspect, mount, and close an exact
Agenticus composition without repeating provider lifecycle machinery.

No CV, public API name, release version, or host-adoption work is accepted.
A successful mechanism experiment may justify a local Technical Story rather
than a Value. Public capability promotion needs a useful inspection decision,
real supported behavior, a second use, and explicit Navigator acceptance.

Before reactivation, read [CV16](../../roadmap/cv16-agenticus-composable-agent-infrastructure/index.md),
[installation authority](../../decisions/records/2026-08-03T0430Z-installations-own-authority-agenticus-owns-machinery.md),
[product principles](../../../product/principles.md), and the
[Agenticus support matrix](../../../runtime-guide.md#2-agenticus-support-matrix).
Recheck current Catalog/profile/Pi A2 host code and its focused tests. The
historical baseline of 102 passing tests is evidence, not a target count.
Render a Plan Checkpoint for Experiment 1 only and keep prototype code,
fixtures, and reports under ES-052.

## 1b Alternatives and falsifiers

| Alternative | Experiment treatment |
| --- | --- |
| Current host constructor | Control. It already expresses provider-specific acquisition and cleanup. |
| Exact runtime-profile composer | First candidate. Materializes one already selected snapshot under common ownership and inspection. |
| Grouped bundle | Consider if two profiles need shared composition without per-leaf factories. |
| Per-descriptor factories | Reject as the starting point. They risk mixing domain values, authority, and services before any repeated ownership is demonstrated. |

| Hypothesis | Evidence that would refute it |
| --- | --- |
| H1: common ownership removes repeated lifecycle work | The layer delegates every useful responsibility back to one constructor or adds more state than it shares. |
| H2: exact-profile granularity is sufficient | Two qualified profiles duplicate an independently useful acquisition unit that requires smaller registration. |
| H3: inspection changes an operator decision | Reports only repeat the snapshot or need private handles to be useful. |
| H4: future readiness preserves active immutability | Changes require hidden snapshot mutation, rebinding, or state contradicting History/custody. |
| H5: authority remains host-owned | Real profiles require arbitrary context lookup, secrets in descriptors, or bypassed custody/Hands contracts. |
| H6: a Value is justified | Only one route benefits or the result is adequately described as internal cleanup. |
| H7: a small ownership tree is sufficient | Correct teardown needs a general reactive scheduler or duplicates Impetus/Motus duties. |
| H8: cleanup and external recovery stay separate | A clean report must erase History, deny an ambiguous emission, or flatten uncertain settlement into verified cleanup. |

## 1c Constraints

These are current project truths, not experiment variables.

### 1c1 Ownership and dependency direction

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

### 1c2 Plan and identity

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

### 1c3 Authority and secrecy

10. Composition planning and dry-run inspection request no credentials and
    materialize no provider authority.
11. A mount receives only the authority explicitly supplied by the host for
    the selected composition. Dependency declaration is not itself authority.
12. Credentials, raw provider state, clients, callbacks, and mutable stores do
    not enter snapshots, reports, canonical History, or portable inspection
    data.
13. Stale Connection, Attachment, grant, execution, and effect authority
    remain fail-closed at their existing enforcing seams.

### 1c4 Lifecycle and recovery

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
19. Every composed capability is classified as owned acquisition,
    borrowed capability, or external emission. Only owned acquisitions
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

### 1c5 Product and support

22. Descriptor/catalog presence, factory registration, installation probing,
    and support status are separate facts.
23. The first production-facing route remains the supported scripted Pi A2
    Local lifecycle. Existing experimental/qualification-only labels do not
    widen because a mount exists.
24. Petrus remains a composable library. The host calls plan/mount/close; the
    composition code does not seize the host's event loop, process, or configuration
    system.


## 1d Experiment 1: disposable exact-profile mount model

Learning intent: determine whether one exact-profile composer plus common
mount ownership has a coherent responsibility independent of Pi A2 internals.

Method: create an Exploration-only model using fake typed profile
composers and inert resources. Do not edit Agenticus production APIs yet.

Required probes:

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

Pass condition: the model owns materialization and withdrawal of an exact plan.
Its generic code contains no Pi, provider,
credential, Hands-tool, Motus-private, or host-application branching.
Independent composition actions may commute, but no test should infer replay
determinism or failure confluence from that result.

Stop condition: if generic code cannot own meaningful rollback or inspection
without learning profile internals, reject the mount abstraction or narrow it
to a report-only capability.

## 1e Later experiments, contingent on the preceding evidence

### 1e1 Experiment 2: Scripted Pi A2 parity through the mount

Learning intent: prove that the abstraction can carry one real supported
composition without weakening behavior or support claims.

Method: adapt the public `compose_pi_a2_scripted_runtime` route behind one
exact profile composer in Exploration or an unpromoted internal branch. Keep
the direct public route intact as the behavioral oracle.

Required probes:

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

Pass condition: both routes have equivalent supported behavior and the
mount owns a real lifecycle/reporting responsibility rather than only renaming
the constructor.

Stop condition: any authority request moves earlier, any cleanup claim
widens, replay changes, or the mount needs private mutable escape hatches.

### 1e2 Experiment 3: Adversarial lifecycle and replacement matrix

Learning intent: test the exact places where Cordis-style reactivity would
conflict with Agenticus snapshot and authority semantics.

Required cases:

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

Pass condition: every case has one bounded, deterministic, fail-closed
outcome and none silently mutates an active snapshot or accepted domain fact.

### 1e3 Experiment 4: Second-use and host-adoption test

Learning intent: determine whether the mechanism deserves Delivery and
possibly a Value boundary.

Preferred evidence order:

1. a second hermetic Agenticus profile or composition inside Petrus reuses the
   mount without type-erasing special cases; then
2. a real host such as Hamsterdan adopts the public plan/mount/close surface and
   removes its own lifecycle orchestration while keeping host policy,
   operation-route custody, and user experience.

Cross-repository adoption is a separate coordinated story and must not be
silently performed from this Exploration.

Pass condition: reuse is structural, not merely both callers invoking a
large conditional factory. The second adopter retains its authority and policy
and gains an inspectable behavior route.

Stop condition: the second route needs incompatible lifecycle semantics,
or shared machinery forces provider-specific types through neutral contracts.

### 1e4 Experiment 5: Packaging and external extension inquiry

State: deliberately unopened.

Only open this inquiry after mount semantics and two uses are proven. Questions
about entry points, package metadata, external plugins, config overlays, process
isolation, signing, trust, or compatibility distribution are not prerequisites
for owned composition and would otherwise dominate the exploration too early.

## 1f Evidence for promotion

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


## 1g Promotion gate

### 1g1 Promote toward Delivery when all are true

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

### 1g2 Keep in Exploration when

- the owned mount is coherent but second-use/customer evidence is missing;
- mount granularity remains unresolved;
- the only demonstrated benefit is internal cleanup consolidation; or
- a provider qualification or host-adoption dependency has not yet been
  authorized.

### 1g3 Narrow to a Technical Story or Refinement when

- only deterministic rollback/close reuse is valuable;
- inspection has no public/operator decision value;
- one existing composer can be simplified without changing the Agenticus
  capability promise; and
- no broader roadmap arc is needed.

### 1g4 Archive or reject when

- profile-specific composition is more truthful and less code than the common
  mount;
- meaningful authority requires ambient context or bypassing existing fences;
- mount state competes with canonical History or custody;
- active snapshots cannot remain immutable;
- useful mount cleanup requires claiming that external emissions were undone;
- cleanup cannot be generalized honestly; or
- no second composition or host benefits.


## 1h Questions to resolve through the experiments

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


## 1i Reactivation triggers

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
