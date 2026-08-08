---
status: Decided
raised: 2026-07-21
decided: 2026-07-22
deciders:
  - henrique (Navigator)
supersedes:
  - ES-033 Option C assignment of Engine to the reusable recipe/factory
  - DEC-034 Option 3 naming hypothesis
related:
  - docs/project/decisions/records/2026-07-21T0809Z-concept-first-ontology-boundaries.md
---

# Engine is one live composition around one durable Instance

## Question

What does `Engine` own, how many durable Instances does one Engine advance,
where do reusable construction inputs and fleet concerns belong, and how
should the current PostgreSQL/Absurd `AuthoritySession` shape evolve?

## Decision

Adopt the ownership separation established by ES-033, but reject its Option C
naming assignment. **Engine is not the reusable recipe/factory.** An **Engine**
is one live, motion-producing composition around exactly one durable
`Instance`.

One Engine owns or exclusively composes that Instance's:

- canonical-writer fence;
- History Store access;
- checked-out transaction and its rollback/poison fate;
- clock;
- Candidate Selection policy state;
- Dispatch integration/session; and
- advancement lane.

A process may host many Engines. Fleet registration, selection and fairness
across Engines, discovery, and supervision belong to a higher layer; they are
not Engine ownership.

Reusable construction inputs—Net definitions and binding, backend, store,
clock, Dispatch, and policy factories or pools—may be shared through ordinary
composition. Do not introduce a public recipe/factory concept now. If repeated
implementation later justifies one, `EngineFactory` is an honest possible
construction mechanism, but it is not the Engine and is not adopted ontology
by this decision.

Do not introduce or adopt `InstanceSession`; “session” conflicts with the
project's agent-session and transcript vocabulary.

Retire `AuthoritySession` as the target name. The current PostgreSQL/Absurd
one-Instance composition is the concrete precursor of an `AbsurdEngine`.
Whether it becomes a concrete structurally compatible Engine or a factory
returning a backend-neutral Engine remains an implementation/API experiment;
this decision does not choose between those shapes. The current class may
remain temporarily while that experiment preserves its established atomicity,
fencing, reconstruction, and poison behavior.

`create` and `load` are distinct lifecycle doors. `close` releases hosting and
runtime resources; it does not semantically complete, cancel, retire, or
terminate the durable Instance. Reconstruction may remain an internal detail
of `load` rather than a separate public `resume` door unless later evidence
requires one.

Migration is out of scope. Nothing has been deployed, and no migration
facility or lifecycle is planned. `load` refuses incompatible durable data
rather than silently reinterpreting it.

There is no cross-Instance atomicity. Engine composition must not silently
fuse with Process Fabric or process spawn.

## Rationale

The mutable and failure-coupled resources identified by ES-033 already share
one fate per durable Instance. Naming that live composition Engine makes its
cardinality and responsibility direct: an Engine produces motion for one
Instance, while the Instance remains the durable semantic thing.

Assigning Engine to a reusable recipe/factory would make the motion-producing
object a secondary handle and obscure the ownership boundary. Assigning Engine
to a fleet would invite shared transactions, clocks, policy state, and writer
fate across isolated Instances. Ordinary construction composition is enough
until repeated code proves a dedicated factory earns a public name.

Avoiding `Session` keeps execution hosting distinct from the unresolved agent
session/transcript domain. Distinct `create`, `load`, and `close` semantics
also prevent resource lifecycle from becoming semantic Instance lifecycle.

## Options Considered

- **One live Engine per Instance — chosen.** Gives every mutable/durable
  hosting concern one explicit fate and permits many Engines per process.
- **Fleet-owning Engine.** Rejected: fleet fairness, discovery, registration,
  and supervision are a higher layer and must not own per-Instance semantics.
- **Recipe/factory Engine plus a per-Instance handle (ES-033 Option C).** Its
  ownership separation is retained, but its naming is rejected: the live
  one-Instance composition is Engine. A future `EngineFactory` is possible
  only if implementation repetition earns it.
- **`InstanceSession` for the live composition.** Rejected because Session is
  already load-bearing agent-session/transcript vocabulary.
- **Keep `AuthoritySession` as the target name.** Rejected with the previously
  rejected Authority ontology; its concrete guarantees remain evidence for an
  `AbsurdEngine` experiment.

## Consequences

- A bounded Engine API/composition experiment may test `create`, `load`,
  `close`, one-Instance advancement, and the two possible Absurd construction
  shapes without adding migration or fleet semantics.
- Candidate Selection state is Engine-local and therefore Instance-scoped in
  effect; DEC-035 subsequently ruled its immutable commit/replay semantics and
  bounded initial policy family.
- DEC-039 subsequently ruled the authority/Instance-side canonical terminal
  append. This record did not settle it; the later ruling now governs.
- The existing private `_coordination` placement remains temporary until an
  Engine implementation story moves behavior without changing semantics.
- Process Fabric, spawn, Workers, provider sessions, and fleet control remain
  separate identities and ownership planes.

## Review Trigger

Review if the bounded API experiment cannot preserve current
PostgreSQL/Absurd atomicity and poison fate, if a second backend proves the
Engine boundary wrong, if repeated constructors justify `EngineFactory`, or
if a real deployment introduces migration requirements.
