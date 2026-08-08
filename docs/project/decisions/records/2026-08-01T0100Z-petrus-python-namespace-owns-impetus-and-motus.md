---
status: Decided
raised: 2026-08-01
decided: 2026-08-01
deciders:
  - Henrique (Navigator)
supersedes:
  - the earlier conclusion that physical distribution and import boundaries were undecided
related:
  - docs/project/decisions/records/2026-07-29T2316Z-petrus-is-project-over-impetus-motus-and-arx.md
---

# Petrus Python namespace owns Impetus and Motus

## Decision

Petrus is one Python distribution with source under `src/petrus` and the
top-level `petrus` namespace.

- `petrus.impetus` owns Binding, DSL, History, History Store, Instance,
  Petrinet, and Selection.
- `petrus.motus` owns Activity, Dispatch, transport, and Worker behavior.
- `petrus.engine` composes Impetus and Motus for one live Instance and owns
  provider-specific construction doors.
- `petrus.fabric` provides addressed inter-Instance communication and depends
  on Impetus; Impetus does not depend on Fabric.
- `petrus.processes` owns lifecycle composition above Fabric.
- `petrus.telemetry` is a Petrus-level concern.

Public concepts are imported from their defining ownership modules rather than
from broad root facades. Persisted and wire identities change only through an
explicit migration protocol.

Tests mirror these boundaries under `tests/petrus`; cross-component tests live
under `tests/integration`, and project gates under `tests/project`.

## Rationale

One distribution preserves coherent installation while component subpackages
make dependency direction reviewable. Ownership-module imports avoid facades
that obscure concepts and create accidental compatibility commitments.

## Consequences

Source, imports, tests, rules, and packaging follow this hierarchy. A component
becomes a separate distribution only after it demonstrates an independently
installable contract.

## Review Trigger

Review if an independently installable boundary is demonstrated or a durable
identity needs a separately designed migration.
