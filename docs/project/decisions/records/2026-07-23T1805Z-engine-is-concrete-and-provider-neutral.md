---
status: Decided
raised: 2026-07-23
decided: 2026-07-23
deciders:
  - henrique (Navigator)
supersedes:
  - CV6.TS7 provisional AbsurdEngine implementation shape
related:
  - docs/project/decisions/records/2026-07-22T0245Z-engine-is-one-live-instance-composition.md
  - docs/project/decisions/records/2026-07-23T1356Z-history-store-and-dispatch-profile-convergence.md
---

# Engine is concrete and provider-neutral

## Question

What exact public Engine shape, lifecycle doors, provider construction,
waiting/routing surface, and resource fate should implement the ruled live
one-Instance composition without promoting Absurd or PostgreSQL into the
Engine ontology?

## Decision

`impetus.engine.Engine` is one concrete provider-neutral class. It is the live
composition around exactly one durable Instance, not a protocol, provider
subclass, fleet, supervisor, reusable recipe, or factory. There is no
`AbsurdEngine` compatibility shim.

The neutral public construction doors are `Engine.create` and `Engine.load`
for already-bound backend-owned History Store and Dispatch compositions. The
PostgreSQL History plus Absurd Durable Dispatch provider doors are
`impetus.dispatch.absurd.create_engine` and `load_engine`; both return exactly
the neutral Engine. Provider and substrate names describe construction and
implementation, not the returned concept.

The exact public Engine inventory is `create`, `load`, `marking`, `status`,
`in_flight`, `records`, `advance`, `wait`, `deliver`, `seal`, and `close`.
`wait(timeout)` is universal advancement-lane pacing: neutral compositions use
a bounded polling fallback, while provider construction may install an
efficient wake hint. Queue resolution is not universal; `queue_for` remains a
concrete `AbsurdDispatch` operation and is not an Engine door.

Writer-fence, transaction, and hosting-resource fate remains private
first-party provider plumbing. The Absurd provider acquires the private
PostgreSQL writer fence before History load, then composes the joined History
Store, Dispatch, transaction boundary, clock, Candidate Selection, and
advancement lane. Successful construction transfers the dedicated writer and
listener connections plus fence to Engine. Construction failure rolls back,
releases the fence when acquired, and closes both connections. A writing-door
failure rolls back, releases the fence immediately, and poisons that Engine;
fresh provider `load_engine` is the only continuation. `close` is idempotent,
releases all owned hosting resources, and appends no semantic fact.

Do not publish `EngineFactory`, an Engine protocol, a resource bundle, a writer
fence protocol, or a transaction protocol. One provider and repeated local
wiring do not earn those public mechanisms.

## Rationale

The project has one Engine implementation and no polymorphic Engine consumer.
A concrete neutral class names the actual ownership boundary directly while
ordinary provider functions safely acquire substrate-specific resources.
Making Absurd the Engine subtype would let today's Durable Dispatch provider
name the whole composition. Publishing transaction or fence parts would also
permit callers to load History before obtaining writer authority, violating
the proven one-writer ordering.

`wait` is consumed by topology drivers as advancement pacing across Dispatch
profiles. Its provider-neutral bounded fallback preserves that door without
adding notification to the two-method Dispatch contract. No maintained Engine
consumer uses `queue_for`, and queue inspection remains provider-specific.

The implementation and frozen evidence preserve schema-4 History bytes,
joined begin-plus-dispatch atomicity, the terminal freeze/projection boundary,
one-writer refusal, poison/fresh-load recovery, and independent fate for
distinct Engines.

## Options Considered

- **Concrete neutral Engine with provider functions — chosen.** It matches one
  implementation, keeps provider acquisition safe, and names the returned
  capability rather than its substrate.
- **Public Engine protocol plus private base and provider subclasses.**
  Rejected because no polymorphic consumer or second implementation earns the
  hierarchy, and `AbsurdEngine` would promote a Dispatch provider into the
  whole composition.
- **Public `EngineFactory` or construction recipe.** Rejected until repeated
  implementation across real providers earns a reusable contract.
- **Expose writer fence, transaction, or resource protocols.** Rejected because
  they are unsafe ordering-sensitive implementation seams with no external
  consumer.
- **Remove `wait` or make it Dispatch API.** Rejected because pacing is an
  Engine advancement-lane concern and Dispatch remains exactly
  `dispatch`/`collect`.
- **Make `queue_for` universal.** Rejected because it is provider routing
  inspection rather than a universal one-Instance lifecycle or motion door.

## Consequences

- Maintained non-Fabric consumers use the neutral Engine type and provider
  construction functions; provider connections and private coordination
  handles do not escape.
- Several Engines may coexist only as separate one-Instance compositions.
  Fabric remains the separate communication layer between their Instances.
- The CV5 Fabric/lifecycle demos still need a separate story to replace their
  private fence imports through honest public Engine doors. Compatibility
  cleanup remains blocked on that story, not on another Engine redesign.
- Local Dispatch promotion, Worker-facing Dispatch ergonomics, fleet hosting,
  and supervision remain separate work.
- There is still no exactly-once external-effect claim, cross-Instance
  transaction, migration, or canonical History change.

## Review Trigger

Review only if a second real Engine implementation creates a polymorphic
consumer, repeated provider construction earns a factory contract, or a new
provider cannot preserve fence-before-History and poison/fresh-load guarantees
through private construction functions.
