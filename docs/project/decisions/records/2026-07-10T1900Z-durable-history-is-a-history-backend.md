---
status: Superseded
raised: 2026-07-10
decided: 2026-07-10
deciders:
  - henrique (Navigator, in-tab sign-off on the persistence-seam design)
supersedes:
related:
  - docs/project/decisions/records/2026-07-21T0809Z-concept-first-ontology-boundaries.md
  - docs/project/decisions/records/2026-07-06T1506Z-event-history-is-the-term.md
  - docs/project/decisions/records/2026-07-06T0325Z-hermes-adr-0031-minimal-event-history-record-model.md
---

# The durable history is a history backend, and its record schema is ratified

> Superseded by the concept-first ontology for ownership and composition:
> History owns semantic values and the canonical codec; a History Store stores
> History rather than inheriting from it. The schema and durability behavior
> ratified here remain preserved.

## Question

The kernel grew its persistence seam (debt 2026-07-10T0600Z), which forced
three coupled naming/schema calls at once:

1. What is the durable artifact called — a "journal" (velocitron's *firing
   journal*), or something else — without overturning the ratified
   "event history is the term" decision?
2. What is the public per-category record serialization schema
   `history.py` deferred?
3. Does ratifying that schema execute the parked convention-40 rename — the
   source-only records' `transition` field to `source` — family-wide, or
   ratify the uniform `transition` spelling permanently?

## Decision

1. **The durable artifact is not a new concept: it is the one event history,
   persisted by a backend.** "Event history" remains THE term, in memory and
   on disk; the seam is an injectable `EventHistory` on `NetInstance`, and a
   durable backend is an `EventHistory` implementation that writes every
   append through (`impetus.persistence.JsonlEventHistory` is the first).
   "Journal" stays on the avoid-list for kernel surface — naming the file a
   journal while the in-memory object is the history would be a synonym pair
   for one concept. Glossary mapping for the velocitron conversation:
   velocitron's *firing journal* ≈ a durable event history narrowed to firing
   records; Impetus keeps the ratified wider scope, now with the durability
   half realized.

2. **The public record serialization schema is ratified as the J1 spike's
   encoding**, proven by the first real consumer and now owned by
   `impetus.persistence` (`encode_record`/`decode_record`): envelope
   `{"record": <type name>, ...fields}` with the class name as discriminator;
   node fields as dotted strings; `Token` as `{color, data}`; `Registration`
   as `{source, key}`; tuples as lists; `attempt: None` as `null`; `instant`
   and `Token.data` pass through as JSON values (durable instants and token
   data must be JSON-serializable, fail-loud). **No version field**: the
   discriminator plus each record type's constructor rejection is the drift
   detector; a future breaking change introduces versioning at that moment.

3. **The convention-40 rename executes now, family-wide at the schema moment,
   exactly as the deferral ruled:** the source-only records —
   `ExternalEventRecorded`, `RegistrationOpened`, `RegistrationClosed` — spell
   their node `source`. The record family names a node by its role (`place`
   on movement records, `transition` on firing records, `source` on
   source-only records); this matches `Registration.source` and the ratified
   `deliver(source)`/`seal(source)` signatures, and freezing the imprecise
   uniform spelling into a permanent public schema was the worse trade.

## Rationale

- A write-through backend dissolves the terminology tension instead of
  adjudicating it: with no separate journal artifact, there is nothing to
  (mis)name. One concept, one name, one home (convention 4).
- Injection over an append-listener: resume composes into one object (load
  the backend, hand it to the resume constructor, keep appending to the same
  file), durability rides the append path itself (retiring the J1 spike's
  durability lag and ingress lag by construction), and future backends —
  SQLite when concurrency demands — slot in additively.
- The schema was not designed, it was *harvested*: the J1 spike's encoding
  round-tripped the whole `Record` union value-equal under test in the first
  real net. Ratifying the proven spelling is consumer-first.

## Consequences

- `impetus/persistence.py` owns the codec and the JSONL backend; layering is
  enforced (kernel modules never import persistence; persistence imports only
  history/marking/schema).
- CONTEXT.md swept: the net-instance entry's "durable journal state" now
  speaks the event history; the unified-event-history entry names durable
  backends.
  pins the retired costs' absence instead.
- Durability posture of the first backend: process-crash durable (no fsync);
  a torn tail fails loud at load. Concurrent append stays out of scope
  (debts 2026-07-09T2330Z / 2026-07-09T2110Z carry the T5 question).
- Bring the backend framing (journal = one durable spelling of the history)
  to the naming conversation with Matt, alongside the original scope argument.

## Review Trigger

The naming conversation with Matt (shared with the 2026-07-06 decision); or a
second backend (SQLite / concurrent append) stressing the no-version-field
choice or the JSONL framing.
