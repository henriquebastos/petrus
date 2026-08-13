---
code: ES-003
status: Candidate
opened: 2026-08-13
related:
  - CV16
  - docs/project/decisions/records/2026-08-03T0430Z-installations-own-authority-agenticus-owns-machinery.md
research_source:
  - https://github.com/deepseek-ai/deepseek-harness/tree/47f943859bef60e4160492346772ded9b24f765a
---

# DeepSeek Harness plugin composition

## Inquiry

What does DeepSeek Harness actually mean by making every product capability a
plugin, and which parts of that architecture should Agenticus copy, adapt, or
reject without weakening installation-owned authority, immutable Episode
resolution, canonical History, or provider-specific honesty?

The motivating hunch is sound but needs one correction: Harness is not a
system with no privileged core. It is a small Cordis microkernel plus a
configuration-driven tree in which almost every **product capability** is a
reversibly mounted component.

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
- `[E]` Petrus's focused Agenticus catalog, profile, and Pi A2 host suites were
  executed against the current source after this comparison was written. The
  result is recorded under Verification.

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

## Comparative fit

| Concern | Harness | Agenticus | Reading |
| --- | --- | --- | --- |
| Dependency contract | Live string-key service presence | Versioned typed exact requirements | Keep Agenticus semantics |
| Selection | Availability activates dependents | Host explicitly selects; Catalog never substitutes | Keep Agenticus policy |
| Active-plan stability | Provider change reloads dependent Fiber | Episode snapshot and operation route are immutable | Never hot-rebind an active Episode |
| Executable ownership | Fiber owns all mount effects | Host composer manually owns collaborators | Learn from Fiber |
| Authority | Trusted ambient Node process | Installation-owned authority, custody, grants, fences | Never replace with injection |
| Composition data | Layered entry tree with stable IDs | Static profiles and host Python tuples | Add inspectability before configurability |
| Contribution semantics | Domain registries above Cordis | Typed Agenticus concepts and provider protocols | Share lifecycle, not one registry policy |
| Failure | Failed/Pending plus rollback and disposal | Bounded protocol codes and verified/unverified cleanup | Adapt rollback to fail-closed settlement |
| Durable truth | Configuration/runtime topology | History, snapshots, custody, route stores | Mount graph remains non-canonical operational state |

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

## Candidate formed: mounted Agenticus installation

The evidence supports a bounded **Technical Story candidate**, not a general
plugin platform:

> Prove that one exact Agenticus `ResolutionSnapshot` can materialize through
> host-registered typed factories into an inspectable, authority-aware mount
> whose partial startup rolls back and whose close settles every owned
> collaborator, without changing an active Episode when the Catalog changes.

A disposable design experiment should use only the supported scripted Pi A2
Local host lifecycle and test these discriminating behaviors:

1. resolution succeeds before any authority is requested;
2. only factories matching the exact selected descriptors can mount;
3. a later factory failure withdraws all earlier owned effects in reverse
   order;
4. close reports verified or unverified aggregate cleanup without hiding
   uncertainty;
5. inspection exposes source, descriptor, entry, dependency, state, and live
   incarnation but no credential, client, closure, or raw provider object;
6. disabling/replacing a Catalog entry blocks or changes **future** mounts but
   neither mutates nor hot-reloads the active Episode snapshot; and
7. the existing direct `compose_pi_a2_scripted_runtime` route remains unchanged
   until the experiment demonstrates less host code and no weaker invariant.

Out of scope are package installation, config-file syntax, HMR, provider
ranking, a universal service locator, live-provider qualification, and public
API naming. Those decisions would be premature before one mount proves useful.

## Verification

- `[D]` `git ls-remote https://github.com/deepseek-ai/deepseek-harness.git HEAD
  refs/heads/master` pinned the researched source at
  `47f943859bef60e4160492346772ded9b24f765a`.
- `[E]` `UV_FROZEN=1 uv run pytest -q
  tests/petrus/agenticus/catalog/test_resolution.py
  tests/petrus/agenticus/runtime/test_profiles.py
  tests/petrus/agenticus/runtime/test_pi_a2_host.py` passed all 102 tests in
  4.47 seconds.
- `[E]` Every relative Markdown link in this artifact resolves in the current
  source tree, and `git diff --check` reports no whitespace errors.

## Disposition

The original hunch is confirmed with a narrower center: Agenticus should not
copy Harness's “everything” slogan or Loader. It should explore Cordis's
**owned reversible mount** as the missing executable complement to Agenticus's
already stronger descriptor, authority, and immutable-resolution model.

The candidate remains in Exploration until the Navigator chooses whether to
promote it. No roadmap item or implementation commitment has been created.
