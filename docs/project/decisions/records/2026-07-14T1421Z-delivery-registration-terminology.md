---
status: Decided
raised: 2026-07-14
decided: 2026-07-14
deciders:
  - henrique (Navigator)
supersedes:
related:
  - docs/project/decisions/records/2026-07-14T1806Z-source-delivery-projection-and-identity.md
---

# Prefer delivery registration over bare registration

## Question

Should the runtime keep the generic term `Registration` for the recorded
permission to deliver external events to a source transition, or adopt a name
that distinguishes this mechanism from an open firing occurrence and from an
async `Future`?

## Decision

Use **delivery registration** as the preferred term. A future deliberate
wire-format change should rename the public/kernel `Registration` family to the
`DeliveryRegistration` family, with the exact serialized record names settled
as part of that migration.

Do not perform the code and wire rename as an isolated cleanup. The current
`Registration`, `RegistrationOpened`, and `RegistrationClosed` names remain the
serialized compatibility surface until a schema-version change provides a
migration boundary.

## Rationale

Session 3 of ES-012 exposed a recurring conceptual collision. A firing
occurrence is the durable one-outcome lifecycle closest to an async task or
future. The
current registration is different: it records that the runtime may deliver
zero, one, or many external events, identified by a source transition and key.
It behaves more like an open receive route than a future.

The bare word "registration" hides what is registered and made the two kinds
of waiting easy to conflate. "Delivery registration" names the capability it
controls without claiming that a live subscription connection exists or that
exactly one result is expected.

## Options Considered

- **Delivery registration — chosen.** Directly names the authorized operation
  and works for webhooks, pollers, human decisions, child signals, and streams.
- **Event-projection registration — prior full glossary term.** Accurate but
  too long for the routine API and discussion surface; the bare shortened form
  caused the confusion.
- **Future / expectation.** Rejected as the kernel primitive because it implies
  a one-shot result. A higher-level one-shot authoring API may still lower to a
  delivery registration.
- **Subscription.** Rejected as the kernel term because it suggests a healthy
  live external connection. The recorded fact authorizes delivery; connection
  health remains operational state.
- **Ingress registration / receive route.** Accurate alternatives, but less
  direct or less natural for the open/close lifecycle.

## Consequences

- Use "delivery registration" in new discussion and design work so it stays
  distinct from a firing occurrence and activity invocation.
- A later migration must update the glossary, specs, code/API names, history
  record discriminators, persistence compatibility, tests, and user-facing
  documentation coherently.
- Higher-level authoring concepts such as a one-shot awaitable or recurring
  subscription may compile to delivery registrations without replacing the
  kernel primitive.

## Review Trigger

The next deliberate event-history wire-format version bump, or a dedicated
terminology/migration session commissioned earlier by the Navigator.
