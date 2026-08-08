---
status: Decided
raised: 2026-07-28
decided: 2026-07-28
deciders:
  - Navigator
related:
  - CV8.DS4
  - docs/project/decisions/records/2026-07-28T2100Z-async-worker-lane-ownership.md
  - docs/project/decisions/records/2026-07-28T1223Z-zeromq-mediates-worker-dispatch-without-owning-custody.md
---

# Async Worker custody stays private after the first native transport

## Decision

`AsyncWorker` uses one private awaitable Worker-custody contract. Synchronous
providers adapt through stable provider-owner lanes; ZeroMQ may implement the
contract natively with bounded event-loop-owned operation sockets. The contract
does not become public until two materially different native providers agree on
its cancellation, uncertainty, concurrency, and ownership semantics.

Absurd remains production-supported through the synchronous bridge. Impetus
will not build native Absurd custody from private SDK orchestration or copied
stored-function behavior. A separate exploration may exercise the boundary and
seek an upstream detached Worker-driver SPI before a fork is considered.

Topology equivalence is semantic rather than raw History sequence identity.
Each execution's canonical History remains exact; comparisons across
independently scheduled arrangements normalize only scheduling interleaving and
run-derived identifiers after lifecycle, causal payloads, final marking, and
external effect equivalence are established.

## Rationale

ZeroMQ demonstrates that Activity concurrency need not imply one helper thread
or provider instance per slot, but one transport does not establish a neutral
public provider extension. Absurd's async SDK executes registered handlers
itself and does not expose the detached claim, heartbeat, complete, and fail
operations an Impetus Worker must own. Depending on private mechanics would
create a semantic fork at the custody boundary.

Concurrent arrangements can legally allocate occurrence identifiers and accept
independent results in different orders. An application policy that manufactures
one order for test equality changes scheduling semantics and hides the design
tension. Strict semantic occurrence-bundle comparison proves the meaningful
contract without requiring byte-identical histories from distinct executions.

## Options Considered

- Publish the protocol after native ZeroMQ alone: rejected as premature.
- Recreate Absurd Worker behavior over raw SQL or private APIs: rejected because
  Impetus would own an undocumented semantic fork.
- Keep the application-specific DrivingPolicy: rejected because it existed only to make
  concurrent histories share one incidental order.
- Compare only record counts or final markings: rejected as too weak to prove
  causal and effect equivalence.

## Consequences

Native ZeroMQ selection remains explicit and optional. Local SQLite and Absurd
continue through the bounded synchronous bridge without being described as
async-native. Provider-specific transport, connection, and retry mechanics stay
out of the private neutral Attempt lifecycle. Every application arrangement
owns only topology composition; the shared application uses ordinary
`choose_throughput`.

## Review Trigger

Revisit public promotion when a second materially different native custody
provider is implemented, or when Absurd exposes a documented detached
Worker-driver boundary. Revisit topology comparison only if the runtime gains a
business ordering guarantee that should become canonical across executions.
