---
status: Decided
raised: 2026-07-28
decided: 2026-07-28
deciders:
  - henrique (Navigator)
supersedes:
related:
  - CV8.DS2
  - docs/project/decisions/records/2026-07-28T1052Z-local-dispatch-and-worker-provider-boundary.md
---

# ZeroMQ mediates Worker Dispatch without owning custody

## Question

How should separately placeable Workers access Local Activity custody without
turning ZeroMQ into a competing authority, leaking database paths to Workers,
or making a transport dependency mandatory for Impetus?

## Decision

Ship ZeroMQ as the optional `impetus.dispatch_transport` extension. Transport
depends one-way on the provider-neutral Worker Dispatch contract; Dispatch,
Worker, History, Engine, and core remain independent of ZeroMQ.

`ZeroMQDispatchServer` exposes only Worker-facing claim, heartbeat, complete,
and fail operations backed by `LocalWorkerDispatch`. The hosted application's
Engine remains directly composed with `LocalDispatch`, and SQLite remains the
sole operational authority. Workers receive endpoint, queue, and identity
configuration, never a custody or History path.

Support same-host `ipc://` with cooperative POSIX endpoint ownership fencing.
Support `tcp://` only with CURVE: server secret identity, client secret
identity, pinned server public key, and an explicit server-side client-key
allowlist. Allowed identities are authorized for the server's complete queue
allowlist in this first contract.

Use a strict versioned, bounded, one-frame application protocol. Every
operation starts with fresh socket state. Do not treat routing identity,
queued frames, or in-memory deduplication as correctness state. An uncertain
claim, heartbeat, or failure is surfaced and recovered through custody leases;
only exact completion is automatically redelivered because Local custody can
durably recognize the same fenced Attempt and result.

External process supervisors own role health and restart. Impetus supplies
runnable server and Worker roles, explicit readiness, finite waits, graceful
drain, and clean resource shutdown, not a fleet manager.

## Rationale

This preserves one Activity-custody concept while permitting a hosted
application to separate execution placement from its Engine and local
database. Package integration tests prove direct Local, served IPC, and
simulated separately placed TCP arrangements with one unchanged Process core.

Fresh operation sockets and custody-based recovery avoid inventing a second
durability protocol inside ZeroMQ. CURVE supplies an appropriate first
authenticated TCP floor, while explicit refusal of plaintext prevents a
development convenience from silently becoming a production topology.

Keeping the extension optional preserves the zero-service Local floor and the
existing Absurd/PostgreSQL route. It also leaves room for later transport or
provider combinations to earn a broader abstraction from evidence rather than
from a speculative generic service API.

## Options Considered

- **Workers open SQLite directly.** Retained as direct Local topology, but it
  does not support separately placeable Workers without sharing local storage.
- **ZeroMQ becomes a Dispatch provider.** Rejected because transport neither
  owns leases nor stores authoritative operational state.
- **Generic public Dispatch RPC service.** Rejected because only Local Worker
  mediation is currently qualified; Engine and arbitrary-provider transport
  would overstate the contract.
- **Plaintext TCP for trusted networks.** Rejected because network placement
  must not silently omit peer and server identity.
- **Transparent retry of every request.** Rejected because claim and arbitrary
  terminal failure reports do not have the exact idempotency proof required
  for blind replay.
- **Embed a launcher or supervisor.** Rejected because deployment tools own
  process policy and this story only needs stable runnable roles.

## Consequences

- Remote Local Workers connect to a service role; they never open Local
  custody or History themselves.
- A Local deployment may mix direct and transported Workers against the same
  SQLite custody authority, subject to ordinary queue configuration.
- Authenticated clients and host-local IPC peers are trusted not to mount
  out-of-protocol multipart resource-exhaustion attacks below the bounded
  application frame. IPC locking coordinates conforming Impetus servers only.
- Async Workers, Absurd mediation, per-key queue subsets, key lifecycle,
  real-host qualification, supervision, and exactly-once external effects
  remain separate work.

## Review Trigger

Revisit the service boundary when a second custody provider or Engine-facing
transport is qualified. Revisit security when a real multi-host deployment
needs key issuance, rotation/revocation, per-identity queue policy, or defense
against malicious authenticated transport peers.
