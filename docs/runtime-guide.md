# 1 Runtime guide

Start with the [small runnable net](../README.md#1b-run-a-small-net). This guide
collects the additional Python examples and support boundaries. The
[specification](../spec/README.md) owns the detailed runtime contracts.

## 1a Python net authoring

`petrus.impetus.dsl` compiles concise Python declarations into the canonical,
language-neutral Petrinet Kernel schema:

```python
from dataclasses import dataclass

from petrus.impetus.dsl import NetBuilder, NetSpec, direct

@dataclass(frozen=True)
class Request:
    id: str

@dataclass(frozen=True)
class ApprovedRequest:
    id: str

@direct
def approve(request: Request) -> ApprovedRequest:
    return ApprovedRequest(request.id)

net = NetSpec("approval")
pending = net.p.pending("Request")
approved = net.p.approved("ApprovedRequest")
transition = net.t.approve(handler=approve)
pending >> transition >> approved

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

## 1b Graphviz

Deterministic DOT rendering needs only Python. Rendering SVG, PNG, or PDF also
requires the Graphviz `dot` executable.

```python
from petrus.impetus.petrinet.dot import render, to_dot

source = to_dot(built.net, theme="dark", direction="top-down")
render(built.net, "net.svg", theme="light", direction="left-right")
```

## 2 Agenticus support matrix

Agenticus composes optional agent runtimes with Petrus. Its supported route
currently tests a local host lifecycle with a scripted runtime client. Live
model and provider integrations require separate qualification; the presence
of a profile descriptor does not establish support.

| Surface | Current status | Evidence boundary |
| --- | --- | --- |
| Pi A2 Local host lifecycle | Supported with a scripted runtime client | Local host composition, workspace and cleanup lifecycle, terminal replay, and process-restart classification. No credentials are needed for this route. |
| Codex A3 Gondolin and Local Worker replay | Experimental, qualification-only | Hermetic runtime-replacement and Worker-loss tests over an Episode-owned lease. No live provider or multi-host support. |
| `pi.native.a2.local` with the exact external Pi installation and a live model/provider | Experimental, qualification-only | Opt-in installation/provider tests only; excluded from routine and release checks. No authenticated Pi, model, or provider support is claimed. |
| Other Agenticus binding-target descriptors | Experimental, qualification-only | Descriptor and adapter contracts exist, but catalog presence is not a product support claim. |
| Profile-table cells marked `unqualified` | Unavailable as supported profiles | No qualifying support evidence. |
| Profile-table cells marked `unsupported` | Unsupported | The current architecture excludes the composition. |

The Pi scripted route uses `LocalProcessEnvironment`, scoped Hands, a workspace
archive, and bodies made available only after cleanup. The Codex A3 evidence
uses a fake Gondolin SDK and a simulated Codex protocol. An Activity borrows an
existing Attachment; the host alone provisions, exports, and destroys the
Episode's territory. A fenced host service stores the terminal result before
replying and can replay it without redispatch after Local Worker replacement.
That evidence excludes network or multi-host Workers, live models and providers,
and credential handling.

The supported scripted route is
`compose_pi_a2_scripted_runtime(...)` in
`petrus.agenticus.runtime.pi_a2_host`. It exposes composition/readiness,
operation start/wait/close, body loading, acknowledgement, and host close through
Python. Operator failures use bounded `RuntimeProtocolError` and settlement
codes. Authority remains installation-owned and one-shot; credentials never
enter durable operation, body, or workspace state. The route qualifies local
host lifecycle. Pi behavior, model quality, provider authentication, and
power-loss durability remain outside that evidence.

The `agenticus-amp` and `agenticus-claude` extras below install exact optional
SDK dependencies; installing an extra does not promote its runtime profile to
supported status.

## 3 Shared Activity workers

Durable Dispatch implementations preserve the authorizing Instance on each
Worker-facing Attempt. A shared Worker can keep an ordinary default Activity
mapping and optionally resolve a scoped implementation without putting routing
fields in business input. The application supplies `provider`,
`default_activities`, and `scoped_modules` in this composition fragment.

The provider implements `WorkerDispatch`, such as `LocalWorkerDispatch` from
`petrus.motus.dispatch.local`. The Engine-facing `LocalDispatch` publishes
work to the same database; it is a different interface.

```python
from petrus.motus.worker import Worker

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
path remains available. `InlineDispatch({...})` executes its Activity mapping
directly and does not need a Worker.

ZeroMQ Worker transport protocol v2 carries Instance scope. Clients and
servers must upgrade together; v1 peers are rejected explicitly.

## 4 Lifecycle scopes

Lifecycle scopes let a host replace one exact generation of queued and
in-flight work without making Dispatch or a scheduler canonical. The durable
identity is `(name, generation)`; retain the exact value returned by the
Engine and provide it with generation-targeted ingress. This fragment assumes
an open `engine`, a source transition named `ingress`, and an application `token`:

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

## 5 Optional dependencies

Install only the providers a host needs:

```sh
uv sync --frozen --extra postgres       # PostgreSQL History Store
uv sync --frozen --extra absurd         # Absurd durable Dispatch
uv sync --frozen --extra zeromq         # authenticated Worker transport
uv sync --frozen --extra github-app     # GitHub App signing support
uv sync --frozen --extra agenticus-amp
uv sync --frozen --extra agenticus-claude
```

## 6 Deterministic simulation testing

`petrus.testing.dst` is a supported, pytest-independent testing contract.
It supplies one deterministic World interpreter,
logical scheduling, bounded fault/crash operations, detached checker cadence,
strict artifacts, exact replay, and process-level hang containment. A profile
still owns its opaque host generation, application commands and observations,
external-world truth, and independent domain oracle; the kit does not expose
private Petrus runtime handles or replace production semantics.

The current authoring contract is `petrus.testing.dst/v4`; strict artifacts
from versions 1 through 3 remain replayable. See the
[DST contract and operating routes](process/deterministic-simulation-testing.md)
and the self-contained [`tests/dst`](../tests/dst/) examples.
