# 1 Project briefing

Petrus is a pre-release Python runtime for Petri-net processes. The
[README](../../README.md) provides a runnable introduction; the
[specification overview](../../spec/OVERVIEW.md) explains the architecture.
Package metadata reports `0.0.0`.

## 1a Current direction

[CV20: Approachable Petrus](roadmap/cv20-approachable-petrus/index.md) is the
active developer-experience work. Its goal is one readable flow file that a
developer can compile, inspect, validate, and run while retaining access to
the lower-level APIs and explicit durability choices.

[CV20.DS3](roadmap/cv20-approachable-petrus/cv20-ds3-live-understanding.md)
records completed portable definition/layout and direct-marking timeline
foundations, plus the paired Arx arrangement, manual-fork, and bounded
simulation evidence. Application-bound targeted simulation and live
correlation remain open. The other CV20 Delivery Stories remain Planned.
The owning story carries the acceptance details and next work.

[ES-062](exploration/es-062-consolidation-and-coherence-baseline/index.md)
holds the ongoing coherence review, terminology rulings, and deferred
architecture questions. Its dated surveys are historical observations;
its dispositions identify what remains unresolved.

## 1b Implemented capabilities and limits

Impetus owns net semantics and one append-only History per Instance. Motus
owns Activity execution. The Engine composes one live Instance; Arx is a
separately maintained editor and inspector that consumes Petrus protocols.

The implementation includes in-memory, JSONL, SQLite, and optional PostgreSQL
History Stores; Inline, In-Memory, Local, and optional Absurd Dispatch;
Workers and optional ZeroMQ transport; Python net authoring and Graphviz;
observation, capture, bounded simulation, and portable Net documents. Store
and execution profiles have different failure guarantees. See the
[runtime guide](../runtime-guide.md) for usage and support boundaries.

[CV19](roadmap/cv19-deterministic-simulation-testing/index.md) completed the
supported deterministic-simulation test kit. Its
[current contract](../process/deterministic-simulation-testing.md) owns
artifact compatibility, replay, campaigns, and qualification limits.

Agenticus supports one scripted Pi A2 Local host lifecycle. Live model and
provider integrations remain qualification-only or unsupported. The
[Agenticus support matrix](../runtime-guide.md#2-agenticus-support-matrix)
owns the exact boundary. CV10's retained-territory and Worker-replacement
evidence is hermetic and single-host; further execution work remains
[Blocked](roadmap/cv10-composable-execution/index.md).

Fabric is an unfinished coordination prototype, subject to rewrite. Its
call/spawn demonstrations remain historical evidence rather than a supported
distributed application layer.

## 1c Working on the repository

Use the [development guide](../process/development-guide.md) for setup,
validation, checkpoints, and commit policy. The
[documentation guide](../README.md) explains current owners and historical
records. Product constraints live in [principles](../product/principles.md);
accepted terminology lives in the [glossary](glossary/index.md).
