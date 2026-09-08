# 1 Petrus

Petrus is a Python runtime for processes modeled as Petri nets. A net makes
the process state explicit: places hold data tokens, and transitions consume,
read, or produce tokens as work progresses. Each running instance records an
append-only History so its state can be inspected and reconstructed.

Use ordinary code for deterministic work and Activities for external effects,
including agent calls and human work. Activities can execute locally or through
Workers. External effects are at-least-once, so applications own idempotency
and reconciliation where repeating an effect would matter.

## 1a Status

Petrus is pre-release software, with package version `0.0.0`. Install from this
repository; there is no published package release documented here.

The runtime includes persistent History Stores, Python net authoring,
Activity execution, observation, bounded simulation, and portable Net documents.
Fabric, the cross-instance coordination prototype, is unfinished and subject
to rewrite. Agent integration has a narrower support boundary than the core
runtime; see the [Agenticus support matrix](docs/runtime-guide.md#2-agenticus-support-matrix).

## 1b Run a small net

You need Python 3.14 or newer and [uv](https://docs.astral.sh/uv/).
From a checkout of this repository:

```sh
uv sync --frozen
```

Save this as `demo.py`. The default transition passes the token from `pending`
to `done`, recording the firing in History.

```python
from petrus.engine import Engine
from petrus.impetus.dsl import NetSpec
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.impetus.petrinet import Marking, NetPath, Token
from petrus.motus.dispatch import InlineDispatch

flow = NetSpec("hello")
flow.p.pending >> flow.t.finish >> flow.p.done
built = flow.build()

engine = Engine.create(
    built.net,
    "hello-1",
    history=InMemoryHistoryStore(),
    dispatch=InlineDispatch({}),
    marking=Marking({NetPath("pending"): (Token("Message", "Hello, Petrus!"),)}),
)
try:
    while engine.advance().ready:
        pass
    print([token.data for token in engine.marking.place(NetPath("done"))])
finally:
    engine.close()
```

```sh
uv run --frozen python demo.py
```

Output:

```text
['Hello, Petrus!']
```

This example keeps History in memory. Persistent stores provide different
durability guarantees; choose a store and hosting profile before depending on
recovery across process loss. An application host also owns waiting, scheduling,
and shutdown when Activities or external input are involved.

## 1c Find the next level of detail

| What you want to do | Start here |
| --- | --- |
| Understand the architecture and guarantees | [Specification overview](spec/OVERVIEW.md) |
| Author nets, render graphs, configure Workers, or use lifecycle scopes | [Runtime guide](docs/runtime-guide.md) |
| Exchange a Net document with an editor | [Portable Net document](spec/net-document-v1.md) |
| Test deterministic schedules, faults, and replay | [Deterministic simulation testing](docs/process/deterministic-simulation-testing.md) |
| Contribute or understand earlier decisions | [Documentation guide](docs/README.md) |
| See current work and remaining limits | [Project briefing](docs/project/briefing.md) |

Impetus, under `petrus.impetus`, owns net semantics and History. Motus, under
`petrus.motus`, owns Activity execution. `petrus.engine.Engine` composes them
for one live instance. Arx is a separately maintained editor and inspector
that consumes Petrus protocols.

## 1d Development checks

```sh
scripts/check quick
scripts/check full
```

The full suite needs Docker, Node, Graphviz, `ps`, `flock`, and a system
Python interpreter in addition to the Python dependencies. See the
[development guide](docs/process/development-guide.md) for setup and test
profiles. `scripts/check release` runs the routine suite twice; separately
marked provider, guest, and installation acceptance tests are excluded.

## 1e License

Petrus-authored content is licensed under Apache-2.0. See
[LICENSE-SCOPE.md](LICENSE-SCOPE.md) and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for third-party boundaries.
