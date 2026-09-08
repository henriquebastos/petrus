# 1 Petrus specification

This directory contains the language-neutral contracts for Impetus net
semantics and Petrus interoperability. The Python implementation is the
reference binding [DR 2026-07-06 implementation-language-python-first].
The [golden trace corpus](traces/README.md) is generated from the Python
reference binding through canonical Net and History schemas. Replay checks
that corpus; focused semantic tests cover broader and newer behavior. The
trace guide names unsupported and deferred areas.

Conformance evidence has that scope. A normative behavior without an executable
check remains a coverage gap. The [glossary](../docs/project/glossary/index.md)
provides accepted terminology; its prose is not mechanically verified line by
line against the implementation.

## 1a Documents

- [OVERVIEW.md](OVERVIEW.md): narrative design overview; read this first.
- [net-schema.md](net-schema.md): structure of a net definition: nodes, places, transitions, arcs, tokens, markings, addressing.
- [net-definition-v3.md](net-definition-v3.md): canonical flat, Pydantic-backed cross-system Net-definition file and compiler contract.
- [net-document-v1.md](net-document-v1.md): the one portable Petrus file format: required definition plus optional view and direct-marking lineage.
- [firing-semantics.md](firing-semantics.md): enabledness, the firing pipeline, scheduling, timers, replay.
- [event-history.md](event-history.md): the per-instance append-only event history and its record model.
- [handler-contract.md](handler-contract.md): how declared symbols bind to guards and handlers, and what handlers promise.
- [observation-protocol-v1.md](observation-protocol-v1.md): coherent Engine snapshots and positioned History pages; its canonical producer fixture lives in `observation/`.
- [simulation-http-v1.md](simulation-http-v1.md): strict synchronous transport that returns a Petrus Net document over one fixed implementation-free simulation build.

Each document is self-contained enough to read alone and cross-references the others.

## 1b Sources and citation convention

Source labels connect design statements to their original rationale. Read
current decision status and later review outcomes when following them:

- `[ADR NNNN]`: a Hermes ADR, migrated into `docs/project/decisions/records/`
  as `*hermes-adr-NNNN-*.md`. Hermes was a predecessor design notebook.
- `[DR <date> <slug>]`: an Ariad decision record in the same folder, e.g.
  `[DR 2026-07-06 net-instance-is-a-process]`.
- `[glossary]`: the ubiquitous-language glossary at `docs/project/glossary/`,
  one file per term (formerly the repository-root `CONTEXT.md`).
- `[Petrus oracle]` identifies historical reference-implementation behavior
  considered during design. The label is provenance, not proof that a current
  test exercises the statement. Consult the current traces and semantic tests
  for executable conformance evidence.

## 1c Marker conventions

- `**OPEN:** <question>` marks an unresolved point. Treat it as a gap that
  needs a decision before relying on a default.
- `**VELOCITRON-DIVERGENCE:** <what velocitron does> / <what Impetus does> /
  <status>` records an explicit difference discussed during specification
  alignment with Matt Scott's Velocitron project.
