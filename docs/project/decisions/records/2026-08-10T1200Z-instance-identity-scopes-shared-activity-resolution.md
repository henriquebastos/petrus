---
status: Decided
raised: 2026-08-10
decided: 2026-08-10
deciders:
  - Driver recommendation, accepted under project checkpoint policy
related:
  - ES-050
  - CV8
  - docs/project/decisions/records/2026-08-10T0555Z-one-logical-activity-execution-owns-durable-operational-retries.md
---

# Instance identity scopes shared Activity resolution

## Question

What is the smallest provider-neutral contract that lets isolated Engine
Instances share durable Dispatch and Worker infrastructure while retaining
host-composed, optionally scoped Activity implementations?

## Decision

Worker-facing `ActivityAttempt` and synchronous/asynchronous Activity execution
contexts carry the durable Instance identity that authorized the invocation.
The field is nullable only for custody arrangements without an Instance, such
as inline or custom process-local attempts. First-party Local and Durable
Dispatch preserve a non-empty exact identity through claim, heartbeat,
retry/reassignment, transport, and terminal report.

`Worker` and `AsyncWorker` accept an optional host callable with the contract:

```python
resolve(instance: str, activity: str) -> Activity | None
```

A returned implementation overrides the ordinary Activity mapping for that
Attempt. An explicit `None` falls back to the mapping. Resolution errors and
invalid implementations are Attempt failures under the frozen execution
policy; Petrus does not add an unfenced abandon/requeue operation. The resolver
is available through synchronous, bridged-async, and native-async Worker paths.

Activity modules remain ordinary host-composed objects or mappings. A host can
construct a default module, decorate or replace it, overlay selected operation
implementations, and reconstruct Instance-scoped overrides from durable
identity plus process configuration. Petrus does not serialize or durably bind
modules, closures, clients, credentials, Engines, markings, or mutable ambient
context.

The synchronous Worker also exposes `run_available(limit=...)`: one bounded,
non-waiting pump over immediately claimable Attempts. It does not close the
provider; the host explicitly closes it. `run()` remains the long-lived form,
and concurrent driving of one Worker is refused.

ZeroMQ Worker protocol v2 carries the required nullable Instance field and
rejects v1 rather than silently widening a strict wire. Local custody checks
the detached field against its opaque identity. Absurd recovers it strictly
from the existing durable Petrus publication key. Raw provider tasks remain
unscoped for compatibility with the provider boundary; a Worker configured
with scoped resolution refuses any Attempt missing scope rather than falling
back to a possibly wrong default implementation.

## Rationale

Instance identity is the one fact Dispatch already stores durably and the
Worker lacks. Exposing only that fact closes the routing gap without turning
scope into a service locator. The existing Activity name remains the durable
symbolic implementation binding; adding another binding/profile identity now
would solve an unobserved deployment-version problem and require migrations.

A richer `ActivityScope` would currently contain one field and invite live
capabilities into durable custody. Context-only scope would force every
Activity or host wrapper to rebuild resolution. Host-only composition cannot
recover an identity hidden by the Worker boundary. A Worker resolver completes
the minimum contract while leaving the simple mapping path unchanged.

Pumping is scheduling mechanics, not Instance authority or scope. Petrus's
Engine still advances exactly one Instance and reports immediate readiness and
`next_maturation`; a multi-Instance runnable index and wake scheduler remain
host responsibilities. Their wake records are reconstructible hints, while
History, ingress custody, and Dispatch terminals remain canonical.

## Options Considered

- **Expose only Instance in context.** Rejected as incomplete because every
  implementation would need to route internally.
- **Introduce `ActivityScope`.** Deferred until a second safe durable field is
  demonstrated.
- **Add durable `ActivityBinding`.** Deferred until multiple implementation
  profiles must coexist durably for one Instance/activity symbol.
- **Create a Petrus Activity-module container.** Rejected; ordinary language
  composition already supports defaults, decorators, replacements, and
  overlays.
- **Put scope/routing in Activity input.** Rejected because infrastructure
  identity is not business input.
- **Use one Worker thread per Instance.** Rejected; one advancing owner per
  Instance does not imply one resident executor.
- **Require PostgreSQL.** Rejected; PostgreSQL is a storage/coordination choice,
  not the missing scope abstraction.

## Consequences

- Shared Workers can serve many isolated Instances without application payload
  routers or per-Instance Worker threads.
- Scoped registries must be reconstructible after restart. Ephemeral closures
  are suitable only where the host controls their complete lifetime.
- Resolver failures consume Attempts like other host execution failures; safe
  external operations still require stable idempotency and lookup-first
  reconciliation.
- ZeroMQ Worker clients and servers must move together from protocol v1 to v2.
- A host scheduler may wake Instances from durable ingress, Activity terminals,
  Petri maturations, and restart repair, but must enforce one advancing owner
  per Instance independently of Worker concurrency.
- Application Nets retain authorization, operation ownership, current-authority
  acceptance, supersession, and an honest terminal-exhaustion latch or explicit
  recovery authorization. They remove Attempt, delay, lease, due, and reissue
  topology already owned by Motus.

## Review Trigger

Revisit when one Instance/activity symbol must durably select among multiple
implementation profiles across deployment, when a second provider-neutral
scope field is proven, or when a concrete multi-Instance host demonstrates a
universal scheduler responsibility Petrus should own.
