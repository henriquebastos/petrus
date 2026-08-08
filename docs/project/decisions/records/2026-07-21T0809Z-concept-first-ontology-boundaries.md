---
status: Decided
raised: 2026-07-21
decided: 2026-07-21
deciders:
  - henrique (Navigator)
supersedes:
  - docs/project/decisions/records/2026-07-06T1505Z-net-instance-is-a-process.md
related:
  - CV2
  - CV3
  - CV5
amended: 2026-07-22
amendment_reason: Navigator rejected Authority as public ontology after the AFK build review; DEC-040 later removed the pre-release compatibility promise
---

# Ratify concept-first ontology boundaries

## Question

What concepts and dependency laws should govern the established Python surface
before its modules are reorganized, without letting current file placement or
compatibility names decide the architecture?

## Decision

The architecture is concept-first. The following boundaries and names are
ratified as one decision; current modules are evidence to map and migrate, not
the authority that defines the concepts.

### Petrinet Kernel and Instance

The semantic core is **Petrinet Kernel**. Its public namespace target is
`impetus.petrinet`, and **Net** is the canonical net-definition term and public
symbol. `Engine` remains a possible future running component that creates,
loads, and advances many Instances, but its ownership model is unresolved and
there is no production `impetus.engine` package or abstraction in this work.

Transition facets are derived structural facts, not kinds: **initiation** is
**marking** when input arcs exist and **source** when none exist; **completion**
is **Direct** for the default or another pure deterministic projection and
**Activity** for an `ActivityHandler` boundary. `Direct` is the canonical
terminology; do not use “Immediate.”

An **Instance** is the formal durable **Petrinet Instance** and its public name
is `Instance`. The current root `NetInstance` export remains only as a
temporary compatibility alias during migration. An Instance owns one marking
and one canonical semantic history and is isolated from other Instances. Its
history has one writer; Instances coordinate by identified messaging rather
than shared marking or shared semantic history. This preserves the useful
invariants of the superseded “net instance is a process” decision while
retiring the process metaphor as formal identity.

Candidate Selection is outside Petrinet Kernel and is applied per Instance.
The current `DrivingPolicy` whole-action semantics are retained: policy sees
the available action surface and chooses a whole action; the kernel does not
embed a scheduler or candidate-selection policy.

### Activity and binding

The **activity** leaf owns `Activity`, `ActivityInvocation`, `ActivityFailure`,
`ExecutionPolicy`, and activity-result conventions. It imports neither Petri
concepts nor history concepts.

The **binding** concept owns the Petri-aware bridge:
`ActivityHandler`, its `prepare` and `project` phases, `Handler`, and
`HandlerResult`. Binding may depend on both Petrinet Kernel and activity; the
activity leaf must never depend back on binding or Petrinet Kernel.

### History and storage

The **history** concept owns semantic records, record value types, replay,
and the canonical codec for one unified semantic stream. There is no split
canonical correctness/observability history.

The **history_store** concept owns I/O and conditional composition around that
stream: durable append/load implementations, files, PostgreSQL, transactions,
and optional-backend wiring. Storage policy does not own record meaning,
replay, or the canonical codec.

### Dispatch, workers, temporary coordination, and infrastructure

**Dispatch** owns execution dispatch contracts and operational attempt state.
**Worker** owns worker lifecycle and execution of Petri-agnostic activities.
Neither queue mechanics nor attempts enter canonical history.

DEC-036 subsequently extinguished Worker capability vocabulary: one live
Engine composes an operational default queue plus optional per-Activity
overrides; Workers subscribe to queues and register Activities; DevOps owns
resource, service, environment, authority, and capacity provisioning. Queue
identity remains outside canonical History.

**Authority is not a ratified public package or ontology concept.** The
current `Runner`, `Coordinator`, unchanged whole-action `DrivingPolicy`, action
vocabulary, `Clock`, `Sensor`, and `PostgresAuthorityFence` are quarantined in
the private temporary implementation package `impetus._coordination`. Root
compatibility exports remain, but `_coordination` is not a canonical import
surface. Its eventual ownership and vocabulary are deferred to ES-033; this
decision neither places it under Instance nor introduces Engine.

`AuthoritySession` remains a whole enforcing composition boundary. Absurd and
PostgreSQL integration must preserve their atomic integration and transaction-
fate guarantees; the migration may decompose implementation homes but must not
split the invariant. Infrastructure implementations and optional dependencies
remain outside core concepts.

Generic Session protocols are deferred. Provider sessions, application
sessions, and future attach/session protocols must not be inferred from
`AuthoritySession` or introduced as Petrinet Kernel concepts during this move.

### Dependency laws

The allowed concept graph is directional:

```text
activity                         (leaf; no Petri/history imports)
petrinet                         (independent semantic kernel)
history -> petrinet, activity
binding -> petrinet, activity
selection -> petrinet
instance -> petrinet, history, binding, activity
dispatch -> activity
worker -> activity, dispatch
history_store -> history
infrastructure -> the public ports of the concepts it implements
```

`history` depends on Petrinet value vocabulary required by semantic records and
on the Petri-agnostic activity values carried by activity records. It must not
depend on binding, selection, instance, dispatch, worker, private coordination,
history-store implementations, or infrastructure. Petrinet Kernel does not
import History: pure net definition, marking, enabledness, Direct projection,
and firing transforms remain independently usable without History, storage,
Instance, Dispatch, Absurd, PostgreSQL, or Workers.

Process Fabric and process lifecycle remain optional higher layers. They may
enter an Instance only through public delivery/activity seams and may not be
imported by Petrinet Kernel, activity, history, binding, candidate selection,
dispatch, worker, or history_store. Telemetry is an orthogonal leaf and must
not reverse any dependency. Applications and providers compose from public
surfaces above these concepts.

## Rationale

The existing source grew in behavioral slices, leaving concepts co-located by
delivery chronology. Naming and dependency direction before moving files
prevents a mechanical package split from merely preserving accidental
coupling. Retaining compatibility aliases separately from canonical names
allows migration without letting compatibility become ontology.

## Options Considered

- Keep `NetInstance` and “instance is a process” as formal ontology. Rejected:
  process is useful analogy but conflates durable Petri state with hosting and
  lifecycle protocols.
- Put selection, activities, binding, history I/O, and workers in Kernel.
  Rejected: each has an independent policy, portability, or infrastructure
  boundary.
- Introduce an `Engine` or Session abstraction during the move. Rejected:
  neither is a ratified production concept; generic Session protocols remain
  deferred.

## Consequences

- A symbol/module/import map and structural coverage gate precede production
  moves.
- Public `Instance` and `impetus.petrinet` are targets; root `NetInstance` is a
  time-bounded compatibility alias, not a second canonical name.
- Existing whole-action `DrivingPolicy`, per-Instance history/isolation,
  messaging, single-writer, AuthoritySession, and Absurd/PostgreSQL atomicity
  behavior must survive moves unchanged.
- Whole-action coordination remains private implementation at
  `impetus._coordination`; its root compatibility symbols do not ratify a
  public package or decide Engine–Instance ownership.
- Current firing and runtime modules temporarily mix Petrinet transforms,
  History emission, binding, and Instance ownership. They may violate the
  target graph only while the move map names that debt and a stop condition
  prevents accidental expansion.

## Amendment — Pre-release compatibility posture (2026-07-22)

[DEC-040](2026-07-22T2005Z-pre-release-apis-carry-no-compatibility-promise.md)
supersedes this decision's compatibility-window commitment, not its concept
packages, names, or dependency laws. Impetus is pre-release and makes no
backward-compatibility promise for `NetInstance`, root re-exports, or temporary
implementation vocabulary. Ready surfaces may be removed atomically with
updates to production, tests, scripts, and every executable experiment plus
full behavioral verification. Names without implemented replacements remain
only for sequencing; they receive no deprecation window, and private
`impetus._coordination` does not become public as a cleanup shortcut.

## Review Trigger

Review when the Planned pre-release compatibility cleanup reaches its Plan
Checkpoint, when a demonstrated Session protocol or shared Petrinet/history
value leaf needs a formal home, or when the first public release needs an
actual compatibility policy.
