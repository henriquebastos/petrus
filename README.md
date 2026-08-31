# Petrus

Petrus is a Python runtime for durable, distributed agentic processes modeled
as Petri nets. Explicit net state and one append-only History per Instance make
coordination replayable and inspectable, while Activity infrastructure can run
work locally or remotely. Petrus remains useful without agents: deterministic
code and human work use the same runtime model.

The project has three component boundaries:

- **Impetus** (`petrus.impetus`) owns Petri-net semantics, Instance state, and
  canonical History.
- **Motus** (`petrus.motus`) owns Activity execution, Dispatch, transports, and
  Workers.
- **Arx** is a separately maintained editor, inspector, debugger, and simulator
  that consumes Petrus protocols.

The neutral `petrus.engine.Engine` composes one live Instance. Fabric adds
addressed communication between independently authoritative Instances without
creating shared semantic state. External effects are at-least-once; only an
Instance authors canonical terminal History.

## Status

Petrus is pre-release software. The package metadata currently reports
`0.0.0`; no PyPI publication is claimed. The language-neutral specification,
Python kernel, durable History Stores, Engine, production local Activity
execution, optional providers, observation, bounded simulation, and portable
Net definitions are implemented and tested. Petrus also ships a supported
deterministic-simulation test kit under `petrus.testing.dst`. Fabric is an
unfinished prototype and is subject to rewrite; its existing call/spawn
demonstrations are not a support or completion claim. See
[`spec/OVERVIEW.md`](spec/OVERVIEW.md), the [project briefing](docs/project/briefing.md),
and the [roadmap](docs/project/roadmap/index.md).

Python 3.14 or newer and [uv](https://docs.astral.sh/uv/) are required.

```sh
uv sync
scripts/check full
```

Use `scripts/check quick [PATH ...]` for static feedback and
`scripts/check release` for the zero-skip release gate.

## Deterministic simulation testing

`petrus.testing.dst` is a supported, pytest-independent testing contract—not a
Petrus runtime product API. It supplies one deterministic World interpreter,
logical scheduling, bounded fault/crash operations, detached checker cadence,
strict artifacts, exact replay, and process-level hang containment. A profile
still owns its opaque host generation, application commands and observations,
external-world truth, and independent domain oracle; the kit does not expose
private Petrus runtime handles or replace production semantics.

The current authoring contract is `petrus.testing.dst/v4`; strict artifacts
from versions 1 through 3 remain replayable. See the
[DST contract and operating routes](docs/process/deterministic-simulation-testing.md)
and the self-contained [`tests/dst`](tests/dst/) examples.

## Agenticus support matrix

Agenticus is an optional Petrus composition subsystem. Its current pre-release
support boundary is deliberately narrower than its catalog of runtime profile
descriptors:

| Surface | Current status | Evidence boundary |
| --- | --- | --- |
| **Pi A2 Local host lifecycle — scripted runtime conformance** | **Supported** | Public Python composition, credential-free scripted runtime client, `LocalProcessEnvironment`, scoped Hands, workspace archive, cleanup-gated bodies, terminal replay, and real process-restart classification. |
| Codex A3 Gondolin Episode territory and Local Worker replay — hermetic conformance | Experimental, qualification-only | Fake Gondolin SDK and Codex protocol witness one exact Episode-owned lease across runtime replacement/resume and a real Local Worker loss/replacement route. Activity executes through the pre-existing Attachment; a fenced host service stores terminal before reply and replays it without redispatch. The Episode host alone provisions, exports, and destroys the territory. No network/multi-host Worker, live provider, model, or credential support is claimed. |
| `pi.native.a2.local` with the exact external Pi installation and a live model/provider | Experimental, qualification-only | Opt-in installation/provider tests only; excluded from routine and release checks. No authenticated Pi, model, or provider support is claimed. |
| Other Agenticus binding-target descriptors | Experimental, qualification-only | Descriptor and adapter contracts exist, but catalog presence is not a product support claim. |
| Profile-table cells marked `unqualified` | Unavailable as supported profiles | No qualifying support evidence. |
| Profile-table cells marked `unsupported` | Unsupported | The current architecture excludes the composition. |

The supported scripted route is
`compose_pi_a2_scripted_runtime(...)` in
`petrus.agenticus.runtime.pi_a2_host`. It exposes composition/readiness,
operation start/wait/close, body loading, acknowledgement, and host close through
Python. Operator failures use bounded `RuntimeProtocolError` and settlement
codes. Authority remains installation-owned and one-shot; credentials never
enter durable operation, body, or workspace state. The route qualifies local
host lifecycle only—not Pi behavior, model quality, provider authentication, or
power-loss durability.

The `agenticus-amp` and `agenticus-claude` extras below install exact optional
SDK dependencies; installing an extra does not promote its runtime profile to
supported status.

## Python net authoring

`petrus.impetus.dsl` compiles concise Python declarations into the canonical,
language-neutral Petrinet Kernel schema:

```python
from petrus.impetus.dsl import NetBuilder, NetSpec, arc, direct, typed_guard

@direct
def approve(request: "Request") -> "ApprovedRequest":
    ...

net = NetSpec("approval")
pending = net.p.pending("Request")
approved = net.p.approved("ApprovedRequest")
transition = net.t.approve(handler=approve)
pending >> arc.read() >> transition >> approved

built = NetBuilder(net).build()
```

`NetSpec` is the authored definition; `BuiltNet.net` is the immutable canonical
`Net`. `@direct` marks a pure local transformation. External effects use the
separate `@activity` contract. Filters and guards are pure, while handlers
bridge Petri-aware bindings to Petri-agnostic Activities.

An ordinary callable guard uses `DataclassPayloadConverter`. When typed guard
inputs need another hydration contract, use `typed_guard(function,
converter=...)` or `@typed_guard(converter=...)` with any `PayloadConverter`.
The converter decodes each selected typed input; the predicate must still
return an exact `bool`.

## Graphviz

Deterministic DOT rendering needs only Python. Rendering SVG, PNG, or PDF also
requires the Graphviz `dot` executable.

```python
from petrus.impetus.petrinet.dot import render, to_dot

source = to_dot(built.net, theme="dark", direction="top-down")
render(built.net, "net.svg", theme="light", direction="left-right")
```

## Optional dependencies

Install only the providers a host needs:

```sh
uv sync --extra postgres       # PostgreSQL History Store
uv sync --extra absurd         # Absurd durable Dispatch
uv sync --extra zeromq         # authenticated Worker transport
uv sync --extra github-app     # GitHub App signing support
uv sync --extra agenticus-amp
uv sync --extra agenticus-claude
```

The canonical specification is under [`spec/`](spec/), including golden traces
in [`spec/traces/`](spec/traces/). Project terminology is defined in
[`docs/project/glossary/`](docs/project/glossary/), one file per term.
Development and architecture conventions are in
[`docs/process/`](docs/process/).

## Shared Activity workers

Durable Dispatch implementations preserve the authorizing Instance on each
Worker-facing Attempt. A shared Worker can keep an ordinary default Activity
mapping and optionally resolve a scoped implementation without putting routing
fields in business input:

```python
worker = Worker(
    provider,
    default_activities,
    resolver=lambda instance, activity: scoped_modules.get(instance, {}).get(activity),
)
```

The resolver and its modules are host configuration: reconstruct them after a
process restart; never serialize closures, clients, credentials, Engines, or
mutable context. Returning `None` selects the default mapping. Synchronous
hosts may call `worker.run_available(limit=100)` to process only immediately
claimable Attempts, then explicitly `worker.close()`; the long-lived `run()`
path remains available. `InlineDispatch({...})` is unchanged.

ZeroMQ Worker transport protocol v2 carries Instance scope. Clients and
servers must upgrade together; v1 peers are rejected explicitly.

## Lifecycle scopes

Lifecycle scopes let a host replace one exact generation of queued and
in-flight work without making Dispatch or a scheduler canonical. The durable
identity is `(name, generation)`; retain the exact value returned by the
Engine and provide it with generation-targeted ingress:

```python
from petrus.impetus.scope import LifecycleScope

scope: LifecycleScope = engine.open_scope("conversation")
engine.deliver("ingress", token, identity="provider-event-42", scope=scope)
next_scope = engine.reset_scope(scope)
```

`close_scope(scope)` and `reset_scope(scope)` commit exact queue cleanup and
in-flight cancellation to canonical History before Dispatch sees any
cancellation instruction. Reset closes generation N and opens N+1 atomically.
Consumed inputs are not restored; compensation is explicit domain work.
Cancellation fences future accepted execution but does not claim that an
ambiguous external effect did not happen.

An Activity terminal already accepted into History must finish deterministic
projection before its generation can close or reset. Local Dispatch can accept
an exact late report from a fenced claimant for canonical quarantine. Absurd
rejects a post-cancellation Worker report as stale and may eventually clean its
provider tombstone; applications using durable providers still need stable
downstream idempotency, lookup-first reconciliation, retention aligned with the
recovery window, and explicit compensation for ambiguous effects. Inline and
In-Memory Dispatch retain only process-local cancellation/result state.

An identified delivery targeting a generation proven closed is durably
acknowledged and dropped. Passing only a scope name means the generation is
uncertain, so Petrus quarantines the delivery rather than silently targeting
the current generation. Quarantine is an audit fact, not a reprocessing queue;
applications reconcile or compensate explicitly from History. Observation
snapshot v1 does not expose `active_scopes`, so scope-aware observers fold the
complete History prefix. Unscoped deliveries and execution remain unchanged.
Hosts still own scheduling and provider/webhook custody. Durable scope values
must never contain credentials, clients, closures, Activities, or Engines.

## License

Petrus-authored content is licensed under Apache-2.0. See
[`LICENSE-SCOPE.md`](LICENSE-SCOPE.md) and
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) for exact boundaries.
