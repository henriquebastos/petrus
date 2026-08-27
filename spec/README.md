# Impetus Specification

This directory is the language-agnostic contract for Impetus, the agentic Petri
net runtime. The spec, its schemas, and its traces are language-neutral
artifacts; every implementation — starting with the Python reference binding —
is a *binding* of this contract [DR 2026-07-06 implementation-language-python-first].
Bindings are validated against the golden trace corpus in `spec/traces/`
(generated from the public Python reference binding through canonical Net and
History schemas).

This is a layered conformance claim, not a promise that every prose sentence is
mechanically checked. Golden replay covers the normative Impetus-native corpus;
focused semantic tests cover broader and newer semantics. Known unsupported and
deferred areas are named in `spec/traces/README.md`. A
normative behavior without executable evidence is a visible coverage gap, not
verified behavior. `CONTEXT.md` supplies reviewed ubiquitous language and
orientation; it is not mechanically proven line by line against the binding.

## Documents

- `OVERVIEW.md` — narrative design overview; read this first.
- `net-schema.md` — structure of a net definition: nodes, places, transitions, arcs, tokens, markings, addressing.
- `net-definition-v3.md` — canonical flat, Pydantic-backed cross-system Net-definition file and compiler contract.
- `net-document-v1.md` — the one portable Petrus file format: required definition plus optional view and direct-marking lineage.
- `firing-semantics.md` — enabledness, the firing pipeline, scheduling, timers, replay.
- `event-history.md` — the per-instance append-only event history and its record model.
- `handler-contract.md` — how declared symbols bind to guards and handlers, and what handlers promise.
- `observation-protocol-v1.md` — coherent Engine snapshots and positioned History pages; its canonical producer fixture lives in `observation/`.
- `simulation-http-v1.md` — strict synchronous transport that returns a Petrus Net document over one fixed implementation-free simulation build.

Each document is self-contained enough to read alone and cross-references the others.

## Sources and citation convention

This spec is **assembled from already-made decisions, not invented**. Every
normative statement cites its source inline:

- `[ADR NNNN]` — a hermes ADR, migrated into `docs/project/decisions/records/`
  as `*hermes-adr-NNNN-*.md` (35 records, the backbone of this spec).
- `[DR <date> <slug>]` — an Ariad decision record in the same folder, e.g.
  `[DR 2026-07-06 net-instance-is-a-process]`.
- `[CONTEXT.md]` — the ubiquitous-language glossary at the repository root.
- `[Petrus oracle]` — production-proven behavior of the Petrus Python engine,
  semantics, not as a decision; where this spec deliberately differs from
  Petrus, the difference is stated explicitly.

## Marker conventions

- `**OPEN:** <question>` — a genuinely unresolved point. The spec never
  silently resolves an open question; readers and implementers must treat
  these as gaps, not defaults.
- `**VELOCITRON-DIVERGENCE:** <what velocitron does> / <what Impetus does> /
  <status>` — an explicit difference from Matt Scott's velocitron spec
  alignment conversation rather than silently forked.
