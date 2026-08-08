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
Python kernel, durable History Stores, Engine, Fabric, production local
Activity execution, optional providers, observation, bounded simulation, and
portable Net definitions are implemented and tested. See
[`spec/OVERVIEW.md`](spec/OVERVIEW.md), the [project briefing](docs/project/briefing.md),
and the [roadmap](docs/project/roadmap/index.md).

Python 3.14 or newer and [uv](https://docs.astral.sh/uv/) are required.

```sh
uv sync
scripts/check full
```

Use `scripts/check quick [PATH ...]` for static feedback and
`scripts/check release` for the zero-skip release gate.

## Python net authoring

`petrus.impetus.dsl` compiles concise Python declarations into the canonical,
language-neutral Petrinet Kernel schema:

```python
from petrus.impetus.dsl import NetBuilder, NetSpec, arc, direct

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
[`CONTEXT.md`](CONTEXT.md). Development and architecture conventions are in
[`docs/process/`](docs/process/).

## License

Petrus-authored content is licensed under Apache-2.0. See
[`LICENSE-SCOPE.md`](LICENSE-SCOPE.md) and
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) for exact boundaries.
