# Project briefing

Petrus is a developer-facing, Apache-2.0 Python project for durable,
distributed agentic Petri nets. Impetus owns event History and Petri-net
semantics; Motus owns Activity execution; Arx is the separately maintained
human-facing companion. The `petrus` distribution contains the Impetus and
Motus implementations plus their Engine, Fabric, observation, simulation, and
portable-definition surfaces.

The language-neutral design and Python reference kernel are delivered. Current
runtime capabilities include durable in-memory, JSONL, SQLite, and optional
PostgreSQL History Stores; provider-neutral Engine composition; Local and
optional Absurd Dispatch; Workers and optional ZeroMQ transport; Python DSL
authoring and Graphviz rendering; read-only observation and capture protocols;
bounded simulation; and portable canonical Net definitions. Fabric's existing
call and spawn demonstrations are unfinished prototype evidence, not a
completed capability or support claim; Fabric is subject to rewrite.

CV10.DS1–DS4 qualified one Episode/operation-owned Gondolin territory lifecycle
through hermetic Codex A3 runtime-protocol evidence, host-local Inline Activity
execution, a real Local Worker process-loss/replacement route with host-stored
terminal replay, and one private single-host retained-territory reconciliation
route. A reconstructed host can reclaim only the exact retained lease or retire
it with verified cleanup. The Activity, Worker, and request service only borrow
an existing Episode Attachment; provisioning, retention, reconciliation,
export, and settlement remain orthogonal host responsibilities. The evidence
does not claim live Gondolin, authenticated model/provider, network or
multi-host custody, provider-side fencing, power-loss durability, or recovery
of work that was active when its host died.
CV16 remains complete at one deliberately narrow support boundary: scripted Pi
A2 Local host lifecycle, not authenticated Pi/model/provider execution.

## Architecture premises

- One durable Instance owns one marking, writer, and append-only canonical
  History. Projections and snapshots are rebuildable views.
- Distribution is routing, not shared semantic state. Fabric coordinates
  independently authoritative Instances through identified delivery and
  Activity effects.
- Filters and guards are pure. Handlers bridge Petri-aware bindings to
  Petri-agnostic Activities, where external effects live.
- Impetus semantics are independent of Dispatch. Motus preserves operational
  custody and reports outcomes; external effects are at-least-once.
- Petrus is a composable library and runtime, not a framework that owns an
  application's lifecycle.
- The specification and golden traces are language-neutral; Python is the
  reference implementation.

## Operating notes

Use Python 3.14+, `uv`, and frozen routine commands. Run exact pytest nodes for
red/green work, `scripts/check quick` for static feedback,
`scripts/check full` for checkpoint confidence, and `scripts/check release`
for zero-skip release qualification. The deterministic Fabric routes are:

```sh
UV_FROZEN=1 uv run python scripts/cv5-fabric-demo.py
UV_FROZEN=1 uv run python scripts/cv5-lifecycle-demo.py
```

The ubiquitous language is in [`CONTEXT.md`](../../CONTEXT.md). Decisions,
roadmap items, technical debt, and process documents are self-contained under
`docs/`.
