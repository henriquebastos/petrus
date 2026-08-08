---
status: Decided
raised: 2026-07-23
decided: 2026-07-23
deciders:
  - henrique (Navigator)
supersedes:
related:
  - docs/project/decisions/records/2026-07-22T1816Z-dispatch-leases-attempts-devops-operates-workers.md
  - docs/project/decisions/records/2026-07-22T2005Z-pre-release-apis-carry-no-compatibility-promise.md
---

# History Store and Dispatch profiles name capabilities, not substrates

## Question

Which History Store and Dispatch profiles, guarantees, structural contracts,
and exact Python names should CV6.TS6 expose after ES-038 removed the incumbent
joined PostgreSQL transaction? Which provider and substrate names remain
legitimate concrete implementation names without becoming product ontology?

## Decision

Adopt the ES-038 ruling surface's R1–R6 recommendations exactly.

### History Store

The product profiles are **In-Memory History Store**, **Local History Store**,
and **Transactional History Store**. “Local Durable” is not a profile name;
the actual process, crash, and power-loss boundary must remain explicit.

The common structural protocol is `HistoryStore`. Exact concrete renames are:

- `EventHistory` → `InMemoryHistoryStore`;
- `JsonlEventHistory` → `JsonlHistoryStore`; and
- `PostgresEventHistory` → `PostgresHistoryStore`.

The protocol and implementations remain under `impetus.history_store`, with
substrate modules where optional dependencies require them. Semantic records
and codecs remain under `impetus.history`.

### Dispatch

The product profiles are **Inline Dispatch**, **In-Memory Dispatch**, **Local
Dispatch**, and **Durable Dispatch**. Each preserves operational Activity
custody at a different failure or topology boundary. Absurd is the current
Durable Dispatch provider implementation, built on PostgreSQL; PostgreSQL is
not the capability.

The common contract is: Dispatch preserves operational Activity custody and
reports operational terminal outcomes to one Engine/Instance. It does not
author canonical History, own Worker process lifecycle, or guarantee
exactly-once external effects. Instance alone accepts terminal outcomes and
authors canonical Activity and firing terminal facts.

Profile guarantees are bounded as follows:

- Inline starts execution synchronously and buffers terminal outcomes in the
  process. It carries no operational restart state; canonical outbox recovery
  may execute again after a crash.
- In-Memory decouples publication and collection in RAM. Process loss drops
  custody, canonical outbox recovery republishes, and effects are at-least-once.
- Local provides exact-idempotent publication and persistent terminal reports
  in one local substrate. It recovers across local process restart; lease/retry
  liveness may require an active poller and effects are at-least-once.
- Durable provides provider-backed queues, Attempts, leases,
  heartbeat/checkpoint state, and terminal persistence for separately placed
  Workers. Recovery is at-least-once. Joined History+Dispatch publication is
  an optional implementation/composition guarantee, not a universal
  prerequisite.

For current coordinator consumers, `collect()` remains session-scoped and
drains each report once per session. Dispatch must not durably mark a terminal
“consumed” merely because collection returned it; a crash before canonical
acceptance must permit redelivery.

`Dispatch` becomes the public structural protocol for the Engine-facing seam:

```python
class Dispatch(Protocol):
    def dispatch(self, occurrence: int, invocation: ActivityInvocation) -> None: ...
    def collect(self) -> Sequence[tuple[int, object]]: ...
```

The guarantees above remain documented contracts rather than speculative type
hierarchies. Worker-side claim, heartbeat, reporting, and lease operations do
not enter this protocol. A second implementation or concrete shared consumer
must earn a later Worker-facing protocol.

Exact concrete renames are:

- `InlineAdapter` and `InlineDispatcher` collapse into `InlineDispatch` unless
  TS6's maintained-consumer inventory proves independent synchronous execution
  needs a separate `InlineActivityExecutor` composition;
- `PendingPoolAdapter` → `InMemoryDispatch`;
- `AbsurdExecutionAdapter` → `AbsurdDispatch`; and
- `ExecutionRuntime` is removed after consumer migration, without a pre-release
  compatibility shim.

ES-038's SQLite `LocalDispatch` remains exploration evidence and receives no
production target in TS6. Eventual package promotion remains a goal for a
separate story so the design tensions stay executable and simple, quick
Impetus applications have an honest local profile.

The Navigator also requires a deferred exploration of concrete scenarios for
Worker-facing Dispatch ergonomics. Workers and Activities should be easy to
build, allowing developers to focus on business logic rather than Impetus
plumbing; this goal does not justify broadening the Engine-facing protocol by
assumption.

## Rationale

ES-038 recovered every required split-commit crash window using separate JSONL
History and SQLite custody. Canonical `ActivityRequested` was a sufficient
outbox, operational terminals survived until Instance accepted them, and Local
and Inline arrangements produced byte-identical schema-4 History in controlled
success and failure runs. The effect-before-terminal window also executed
twice, making the at-least-once limit observable.

The evidence distinguishes capability from implementation. A joined
PostgreSQL+Absurd transaction is a valuable stronger composition but not the
definition of either History Store or Dispatch. Likewise, SQLite, filesystem,
RAM, PostgreSQL, and Absurd describe concrete substrates/providers rather than
the complete product capability.

The existing coordinator already has one real polymorphic dependency on
`dispatch`/`collect`. It does not consume Worker-side provider operations, so a
small public structural protocol is earned while a broad protocol is not.

## Options Considered

- **One undifferentiated History Store concept with per-implementation prose.**
  Rejected because the three demonstrated failure/transaction profiles are
  meaningful product vocabulary.
- **Profile protocol hierarchies.** Rejected because no polymorphic consumer
  earns those additional types.
- **Retain `History`/`EventHistory` as the semantic timeline value.** Rejected
  because Engine's injected I/O seam needs the common capability name while
  semantic records/codecs already have their own package.
- **Keep `ExecutionAdapter` and make Dispatch docs-only.** Rejected because the
  primary name would continue to emphasize execution rather than custody.
- **Expose no Dispatch protocol.** Rejected because the coordinator dependency
  is real across Inline, in-memory, Local, and Absurd arrangements.
- **Publish one broad Worker/Engine protocol.** Rejected as speculative because
  current providers do not share those doors.
- **Promote SQLite Local Dispatch during TS6.** Deferred to a separate
  production promotion story; ES-038 established evidence, not readiness.

## Consequences

- CV6.TS6 may perform the ruled coherent pre-release renames without aliases or
  compatibility shims, updating every maintained executable consumer in the
  same unit.
- Canonical History schema remains 4 with exact bytes and no migration.
- Absurd SQL, pins, lockfile, terminal authorship, and at-least-once posture
  remain unchanged.
- Provider-neutral Engine construction, universal Engine doors, and any earned
  construction helper remain CV6.TS7 decisions.
- Fabric terminology and integration remain outside Engine and outside TS6.
- ES-040 tracks Worker-facing Dispatch ergonomics without commissioning an API.

ES-040 originally opened as ES-039. It was administratively renumbered after an
independently created ES-039 for PostgreSQL packaging merged from
`origin/main`; the ruling and exploration scope did not change.

The submitted ruling targeted `ES-038-history-dispatch-convergence` revision
`es38-evidence-v1`. The frozen submission digest is
`386ed3046498bc9a3b2d63f8dae5feeda2c1efd2e492f159c9e3e8cea085b440`;
all four pinned source hashes verified unchanged before this record was made.

## Review Trigger

Revisit the Engine-facing protocol only if TS6 finds a maintained consumer
outside `dispatch`/`collect`. Revisit Worker-facing shape when a second
implementation or concrete shared consumer exists. Route Local Dispatch
promotion through its own plan and production evidence rather than treating
the ES-038 experiment as package-ready.
