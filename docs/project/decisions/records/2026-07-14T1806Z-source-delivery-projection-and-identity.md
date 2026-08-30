---
status: Decided
raised: 2026-07-14
decided: 2026-07-14
deciders:
  - henrique (Navigator)
supersedes:
  - docs/project/decisions/records/2026-07-08T1601Z-source-transition-ingress.md
related:
  - docs/project/decisions/records/2026-07-14T1421Z-delivery-registration-terminology.md
---

# Source transitions project identified deliveries; impure work follows downstream

## Question

Should a source transition dispatch a remote impure handler when a webhook,
broker message, human decision, sensor observation, or similar external event
arrives? Who prevents transport redelivery from creating duplicate history and
tokens?

## Decision

This record supersedes the source-transition ingress decision while preserving
its central ruling: source transitions remain scheduler-excluded, addressable
entry points that fire only when the environment delivers an external event.

Preserve its other semantic invariants unchanged:

- arc filters and transition guards are pure;
- accepted external facts affect flow only after becoming recorded tokens;
- standing external conditions are modeled as state projections in the marking;
- time enters through recorded watermark advancement, not source delivery.

Refine the execution boundary as follows:

- An **ingress adapter** interacts with the external transport: authentication,
  polling/lease mechanics, decoding, and extraction or construction of a stable
  delivery identity.
- A **source transition** locally and atomically projects the accepted external
  fact into typed tokens and delivery-registration effects.
- Recoverable impure work belongs in ordinary downstream handled transitions,
  not inside remotely executed source-transition handlers.
- The delivery door enforces idempotent acceptance by stable delivery identity.
  It checks for an already-committed identity before validating the current
  registration, returns the prior phase answer for a duplicate, and appends no
  second semantic record or token.
- The public Engine exposes identified source delivery as two bounded phases.
  `accept_delivery` validates the complete delivery before mutation, records
  `ExternalEventDelivered` and `FiringBegun` as one durable accepted boundary,
  and returns a detached `AcceptedDelivery` naming the Instance, source,
  identity, and occurrence without running the source projection.
  `complete_delivery` resolves that exact accepted unfinished occurrence and
  completes only its pure local projection. It never reconciles another
  occurrence or advances an enabled candidate. If the projection raises, the
  writer appends its `FiringFailed` terminal and the Engine asks the provider
  to commit it before propagation. After an acknowledged commit, failure text
  deterministically records the exception type plus exact scalar arguments or
  stable type markers, is non-empty and bounded, and the original projection
  exception propagates; exact redelivery then acknowledges the ended occurrence
  rather than rerunning failed projection code. If that separate failure
  transaction is refused or its acknowledgement is lost, the storage exception
  takes precedence and poisons the Engine. Fresh load is the authority: refusal
  reconstructs the unfinished occurrence for exact retry, while acknowledgement
  loss reconstructs the ended occurrence for acknowledgement. A History refusal
  of the already-prepared completion batch is not a
  projection failure: it appends no `FiringFailed`, leaves the occurrence
  unfinished, and propagates the backend's original exception so exact retry
  can complete it. The technical distinction stores but never renders that
  exception, so hostile formatting cannot replace or misclassify a storage
  refusal. Completion prepares separate History-owned and return-owned detached
  values before the append; no fallible return copying remains after durable
  acceptance of the completion batch.
- Exact redelivery of an accepted unfinished occurrence reconstructs and
  returns the same `AcceptedDelivery`; exact redelivery after the occurrence
  ended returns its prior acknowledgement. Neither answer appends nor invokes
  a provider commit hook. Identity reuse with changed source, tokens, or scope
  fails before mutation. Delivery sources admit only an exact
  base `NetPath` or built-in string; lifecycle scopes, names, and generations
  likewise admit exact protocol types. Subclass protocol methods therefore
  cannot alter durable source spelling or bypass identity and scope collision
  judgment. At acceptance, the writer snapshots token content to its
  durable JSON spelling and compares that serialized form, so caller mutation
  cannot alter accepted fact and projection, a reconstructed handler binding
  cannot rewrite History's accepted fact, JSON-lossy forms normalize once, and
  boolean/integer/float spellings do not alias.
  Sensor ingress admits exact `Delivery` parcels through the same source
  canonicalizer before reading parcel fields. Completion likewise admits only
  an exact base `AcceptedDelivery`, then refuses an ended, impure, non-source,
  foreign, or mismatched acceptance before running a handler. Replay derives
  the exact production sequence for a source using Petrus's built-in
  passthrough and refuses omissions, substitutions, or delivery-registration
  effects that handler cannot emit. Replay derives
  registration authority only from a complete construction prefix ordered as
  one exact `InstanceCreated`, all initial tokens, then exactly one
  uncorrelated `default` open for every source in canonical order, or from exact
  firing-correlated effects inside the contiguous writer-valid completion batch
  beginning at its first production. Resume snapshots one exact base-record
  tuple and validates every record before any record field participates in a
  replay fold. Initial token records must also name a declared place exactly
  once, carry at least one token at the construction instant without queue-entry
  or scope metadata, and satisfy the same typed-place color rule as live
  construction. They are valid only in the contiguous construction prefix,
  including for a net with no source registrations to delimit that prefix.
  Exact registration values and keys are
  validated before their fields can affect live authority, and `seal` uses the
  same canonical source boundary; a torn or live-impossible constructor,
  forged reopen, or hostile protocol subclass cannot authorize or disable
  delivery.
- `Engine` alone owns `deliver`, the convenient composition of those public
  identified phases; it requires the same stable identity as
  `accept_delivery`. `Instance` owns only the phase primitives. Its acceptance
  boundary commits before completion begins, so interruption after acceptance
  leaves one reconstructible unfinished occurrence rather than rolling
  acceptance back with projection. The composed call preserves exact
  redelivery acknowledgement and does not invoke broad Engine advancement.
- Sensor `Delivery` parcels and the Instance acceptance primitive likewise
  require that stable identity. There is no unidentified ingress path and no
  writer-derived delivery identity; an adapter that lacks a provider identity
  must construct and retain one before calling Petrus.

The adapter may keep a deduplication cache, but canonical enforcement belongs at
the single writer. It must not query the marking for an equal token: the token
may already have been consumed, and equality is not event identity.

Transport redelivery, repeated business events, and state coalescing remain
different concepts:

- the same delivery identity is accepted once;
- distinct event identities are preserved even when their data is equal;
- a declared sensor or net topology may merge distinct observations into a
  latest-state mirror when that is the process's intended meaning.

## Rationale

Webhooks, Pub/Sub messages, human approvals, file changes, and email receipts
first establish facts. They do not inherently require remote side effects.
Putting provider enrichment or other work inside their source transition would
hide a recoverable step inside ingress. A downstream transition makes that work
explicit and gives it the ordinary firing-occurrence lifecycle.

At-least-once transports routinely redeliver after acknowledgement loss. A
one-shot delivery registration may already have closed after the first commit,
so duplicate identity recognition must precede the armed-registration check.
Operational telemetry may retain duplicate attempts for diagnosis; canonical
history retains the accepted fact once.

For state observations such as a file watcher, a content hash or version can
identify one observation. Several notifications for that version collapse;
five real versions remain five facts. A mirror transition may consume the old
state token and produce the newest while history continues to preserve each
accepted observation.

## Options Considered

- **Remote impure source handlers.** Rejected for the initial model; they mix
  fact admission with recoverable outbound work.
- **Adapter-only deduplication.** Rejected as insufficient because adapter state
  is not canonical and may be lost or raced.
- **Query the marking for an equal token.** Rejected because marking presence is
  transient and token equality does not prove delivery identity.
- **Accept every transport attempt and let the net drain duplicates.** Rejected
  for identical delivery identities; it pollutes semantic history with a
  transport artifact. Still valid for distinct events when the domain wants an
  event ledger.
- **Expose the live `FiringOccurrence` between public phases.** Rejected because
  a caller needs a stable correlation value, not a writer-owned object graph.
  `AcceptedDelivery` is detached and can be reconstructed from History by exact
  redelivery.
- **Resume through general Engine advancement.** Rejected because first-load
  reconciliation intentionally processes every unfinished occurrence and one
  normal action may then advance unrelated work. Source-delivery completion is
  an exact operation over one accepted occurrence.

## Consequences

- `Delivery` needs stable identity and an idempotent acknowledgement contract in
  the CV3 ingress slice.
- Source projection must express typed tokens and delivery-registration effects
  atomically without requiring a remote worker.
- Handler purity is classified by the bound handler kind: deterministic local
  source projection remains pure, while `ActivityHandler` marks recoverable
  outbound work as impure.
- Broker acknowledgement occurs only after durable acceptance. Ack loss may
  cause redelivery, which the delivery identity safely absorbs.
- A host may persist the detached acceptance or reconstruct it by offering the
  exact delivery again after `Engine.load`; neither route requires private
  Instance access.
- The broader purity statement becomes precise: ingress impurity belongs to
  ingress adapters; process side effects belong to handled transitions; every
  accepted external observation becomes recorded fact before it affects flow.

## Review Trigger

Revisit if source projection ceases to be a pure local operation, or if a
future delivery protocol cannot reconstruct one exact accepted unfinished
occurrence from stable delivery identity and canonical History.
