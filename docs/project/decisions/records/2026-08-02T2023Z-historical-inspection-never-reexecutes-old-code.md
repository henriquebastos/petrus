---
status: Decided
raised: 2026-08-02
decided: 2026-08-02
deciders:
  - henrique (Navigator)
supersedes:
  - any interpretation that historical inspection or forking should locate and execute an Instance's obsolete code version
related:
  - docs/project/decisions/records/2026-07-23T1614Z-impetus-owns-versioned-net-definition-protocol.md
---

# Historical inspection never re-executes old code

## Question

When Arx or another current Petrus tool opens an old Instance History, should
Petrus recover and execute the historical Net's old Python code and Activity
implementations? If a future user forks from a historical position, which Net
and code govern the new execution?

## Decision

Historical inspection is read-only. It reads canonical History records,
recorded values, and derived historical markings. If the exact serialized Net
definition is available, a tool may use it to make that old structure legible.
Inspection never loads, locates, or executes obsolete handlers, Activities,
guards, filters, packages, containers, credentials, or provider integrations.

Petrus will not build a historical-code resurrection system. It will not
archive arbitrary executable implementations merely so an old execution can
be started again after its code and supported deployment have moved on.

Operational crash continuation is distinct from historical inspection. It
continues the same supported Instance under the deployment and definition that
currently own it; it is not a user-selected return to an arbitrary old code
version. This decision does not remove current crash recovery and does not
claim the current implementation already proves an exact definition identity.

A future **fork** creates a new Instance governed by the **current Net and
current code**. Directly deriving a new starting marking from a historical
position requires the historical and current structural definitions to align
under the future ruled definition-identity contract. If they do not align,
Petrus must not reinterpret old places, transitions, tokens, or declarations
under the changed Net. Moving historical data into the current Net then
requires an explicit application-authored migration or import that creates the
new Instance's initial state.

Forking, definition persistence, and migration are not part of the first Arx
observation slice. For that slice, a currently hosted Engine supplies the exact
canonical Net it is running. If the original definition artifact later
disappears, its old History may still be inspected as records and values, but
the first slice does not promise complete old-Net visualization from History
alone.

## Rationale

History records observed semantic facts; implementations are code supplied by
the current host. Treating an old History as authority to execute whatever old
code once surrounded it would require retaining and trusting complete software
and infrastructure environments indefinitely. That is outside Petrus's value
and would conflate durable process truth with deployment archaeology.

Read-only historical understanding remains valuable without executable
resurrection. A future fork is useful precisely because it creates a new
current execution from selected prior state; making the current definition
explicit and refusing structural mismatch prevents silent corruption.

## Options Considered

- **Archive and resurrect exact historical code.** Rejected: Petrus does not
  promise indefinite executable environment preservation or execute obsolete
  implementations for inspection.
- **Replay old History through current code regardless of definition.**
  Rejected: changed topology and declarations can reinterpret old data and
  produce false state.
- **Inspect old facts read-only; fork only into aligned current structure or
  explicit migration — chosen.** This preserves historical understanding and
  makes every new execution current and intentional.

## Consequences

- Arx historical mode never calls handlers or Activities.
- A serialized historical Net, when preserved, is a structural inspection
  artifact rather than an executable deployment bundle.
- The first observation slice may expose the live Engine's exact Net without
  first solving durable Net-definition retention.
- Future direct fork semantics require an exact ruled definition-alignment
  check.
- A mismatched definition requires explicit application migration/import; no
  generic place-name or token-shape guessing is allowed.
- Crash continuation, historical inspection, fork, and migration remain four
  distinct operations and must not share ambiguous “resume” language.

## Review Trigger

Revisit when a concrete story implements durable Net-definition retention,
historical structural visualization, fork-at-position, or application-authored
state migration. Do not revisit merely because an old package or container can
technically still be located.
