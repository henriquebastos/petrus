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
  registration, returns the prior acknowledgement for a duplicate, and appends
  no second semantic record or token.

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

## Consequences

- `Delivery` needs stable identity and an idempotent acknowledgement contract in
  the CV3 ingress slice.
- Source projection must express typed tokens and delivery-registration effects
  atomically without requiring a remote worker.
- The current rule that every explicitly named handler is impure is too coarse
  for deterministic source projection and must be refined deliberately.
- Broker acknowledgement occurs only after durable acceptance. Ack loss may
  cause redelivery, which the delivery identity safely absorbs.
- The broader purity statement becomes precise: ingress impurity belongs to
  ingress adapters; process side effects belong to handled transitions; every
  accepted external observation becomes recorded fact before it affects flow.

## Review Trigger

The CV3 delivery protocol design, especially delivery-id scope, retention and
indexing, acknowledgement replay, and whether the local projection surface is a
handler subtype or a distinct binding concept.
