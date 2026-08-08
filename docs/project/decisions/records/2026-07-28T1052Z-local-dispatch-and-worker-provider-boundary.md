---
status: Decided
raised: 2026-07-28
decided: 2026-07-28
deciders:
  - henrique (Navigator)
supersedes:
related:
  - CV8.DS1
  - docs/project/decisions/records/2026-07-23T1356Z-history-store-and-dispatch-profile-convergence.md
  - docs/project/decisions/records/2026-07-22T1816Z-dispatch-leases-attempts-devops-operates-workers.md
---

# Local and Absurd are Dispatch providers behind one Worker contract

## Question

How should production Local Activity custody, synchronous Worker execution,
SQLite History, optional PostgreSQL/Absurd dependencies, future ZeroMQ
mediation, and application-owned process topology be named and packaged without
turning substrates or deployment arrangements into drifting product concepts?

## Decision

`Dispatch` remains the operational Activity-custody concept. Concrete
production providers remain under that concept:

- `impetus.dispatch.local.LocalDispatch` and `LocalWorkerDispatch`;
- `impetus.dispatch.absurd.AbsurdDispatch` and `AbsurdWorkerDispatch`.

Do not introduce a parallel public `DispatchCustody` concept or
`impetus.dispatch_custody` package. Engine-facing publication/collection and
Worker-facing claims are distinct contracts over the same operational custody,
not separate product capabilities.

The two real providers earn one narrow provider-neutral Worker surface:
`ActivityAttempt`, `WorkerDispatch`, `Worker`, and
`ActivityExecutionContext`. An Attempt carries only opaque identity, epoch,
claimant, queue, invocation, and latest details. Provider SQL, paths,
connections, LISTEN, reconnect, provisioning, and transport state do not cross
that boundary. Worker owns synchronous claim/execute/heartbeat/terminal/drain;
it does not own process supervision.

Local Dispatch uses SQLite with operation-scoped connections and database-owned
lease time. One configured file is one custody domain and may contain many
Instances. SQLite History and Dispatch may share a file or use separate files,
but co-residence does not create a joined transaction. Production SQLite
History hosting uses deep fenced `create_engine`/`load_engine` constructors;
direct `SqliteHistoryStore` remains an unfenced low-level or
externally-coordinated store.

PostgreSQL and Absurd remain optional dependencies. Core, Worker, SQLite
History, and Local Dispatch imports must not import them. A future optional
ZeroMQ extension belongs under `impetus.dispatch_transport`, depending one-way
on Dispatch/Worker contracts; Dispatch never depends on a transport package.

Package integration tests exercise one Process core while varying History,
Dispatch, queue routing, and application-owned Worker processes. Fabric is not
part of this provider boundary.

## Rationale

The Local and Absurd implementations demonstrate the same Worker lifecycle
without sharing substrate mechanics. That evidence earns a small protocol and
prevents the former Absurd-specific Worker from making an optional dependency
mandatory. Keeping providers under Dispatch preserves the established
capability ontology: custody is the purpose; SQLite, PostgreSQL, and Absurd are
implementations.

The integration matrix proves that one application can move from Inline to
portable and integrated Local arrangements without changing its Net,
Activities, handlers, or canonical semantics. Separate CPU and I/O queues also
show where later synchronous-process and async Worker pools can attach without
requiring a scheduler or fleet manager in the runtime now.

SQLite's ordinary-local-filesystem boundary is intentionally honest. Fenced
History constructors enforce one cooperating canonical Engine per
database/Instance, while distinct Instances remain concurrent. Worker custody
is at-least-once and external effects still require application idempotency.

## Options Considered

- **`impetus.dispatch_custody`.** Rejected because it duplicates Dispatch's
  established meaning and would split one concept by implementation door.
- **Keep Worker Absurd-specific.** Rejected because Local and package tests are
  real consumers and optional dependencies would continue leaking into core.
- **Put Local/Absurd below a generic transport package.** Rejected because
  direct SQLite and PostgreSQL providers need no transport mediation.
- **JSONL Dispatch.** Rejected because append-only History storage does not
  naturally provide concurrent claims, leases, fencing, or mutable custody.
- **Include Fabric in the matrix.** Deferred until Fabric independently earns
  the required stability and semantics.
- **Ship a supervisor/topology model.** Rejected for this story; Procfile,
  container, service, and platform supervisors already own process health, and
  the application may provide a bounded convenience launcher.

## Consequences

- Provider-neutral Worker code must remain free of psycopg, Absurd, SQLite,
  transport, and process-supervisor types.
- Provider-specific wake behavior remains polymorphic through `wait(timeout)`:
  Local polls; Absurd uses LISTEN/reconnect.
- New transports depend on the neutral contracts and remain optional package
  extensions.
- Async Workers, mixed pools, ZeroMQ mediation, real remote-host qualification,
  and fleet launch policy require separate stories and evidence.
- Fabric must not appear in the maintained topology matrix until explicitly
  qualified.

## Review Trigger

Revisit the Worker contract only when async execution or transport mediation
cannot preserve its provider-neutral Attempt and terminal semantics. Revisit
package ownership only if a second transport demonstrates that
`impetus.dispatch_transport` creates the wrong dependency direction.
