---
code: ES-050
status: Completed
opened: 2026-08-10
related:
  - CV8
  - docs/project/decisions/records/2026-08-10T0555Z-one-logical-activity-execution-owns-durable-operational-retries.md
  - docs/project/decisions/records/2026-08-10T1200Z-instance-identity-scopes-shared-activity-resolution.md
---

# Shared Activity execution scope

## 1 Closure, 2026-09-08

The candidate was delivered under the linked Instance-identity decision.
The findings and application size estimates below describe the August 2026
investigation. Current Worker usage lives in the [runtime guide](../../../runtime-guide.md);
the [decision](../../decisions/records/2026-08-10T1200Z-instance-identity-scopes-shared-activity-resolution.md)
owns the accepted scope and resolver behavior. Revisit broader binding or
scheduling proposals only when a concrete host needs more than this contract.

## Inquiry

What is the smallest provider-neutral execution-scope, instance-scheduling,
and Activity-module contract that lets isolated Engine Instances share durable
Dispatch and Worker infrastructure while keeping Activity implementations
host-composed and producing the smallest Petri Net that still records every
durable business decision?

The pressure case is Hamsterdan publication readiness: authorize one immutable
operation, let Motus own operational Attempts and reconciliation, return one
typed terminal to the owning Instance, and accept it only while authority and
operation ownership remain current. Attempt, retry, due, and reissue mechanics
must not remain in the Net. Terminal exhaustion must leave an explicit business
latch or require explicit recovery authorization; merely clearing the operation
would authorize an unbounded new logical execution above Motus.

## Current story

The initial gap was that `LocalDispatch` durably stored `(instance, occurrence)`
while its Worker-facing claim exposed only an opaque Local `attempt_id`.
`ActivityAttempt` and `ActivityExecutionContext` now expose Instance identity;
Local validates it against custody identity, Absurd recovers canonical Petrus
publication scope while preserving unscoped raw-provider tasks, and ZeroMQ v2
transports it. Terminal collection remains isolated because every Engine-facing
`LocalDispatch` session is Instance-bound.

Hamsterdan's HTTP webhook ingress is already durable-only. Its current global
serialization happens later, where one service worker calls reconciliation and
drains an Engine inline. The actual invariant is one advancing owner per
Instance, not one thread or permanent lock per Instance. Engine already reports
`next_maturation`; a host scheduler can persist non-canonical wake hints for
observations, Activity terminals, Petri timers, and restart repair while
History, ingress custody, and Dispatch remain canonical. A filesystem sweep is
then repair, not the primary scheduler.

The estimated Hamsterdan topology reduction is 46/161/477 to approximately
40/139/415 places/transitions/arcs by removing publication lease, retry, due,
reissue, and obsolete retirement mechanics while retaining immutable request,
operation ownership, current authority, typed terminal acceptance, terminal
exhaustion, and supersession.

## Alternatives under test

| Candidate | Benefit | Main leak or cost | Current reading |
| --- | --- | --- | --- |
| Expose `instance` only | Makes durable workflow identity provider-neutral | Does not itself choose an implementation | Necessary carrier |
| `ActivityScope` value | Can grow beyond Instance identity | Invites credentials, clients, or mutable ambient state | Too broad without a second proven field |
| Durable `ActivityBinding` | Pins implementation profile across deployment | Adds versioning and migration before coexistence is demonstrated | Defer |
| Worker-level resolver | Selects a host-composed implementation without payload routing | New optional Worker seam | Smallest composition completion |
| Scope only in execution context | Activity can route internally | Makes every Activity or host wrapper reimplement resolution | Insufficient alone |
| Host composition outside Petrus | Keeps the runtime small | Cannot recover the Instance currently lost at the Worker seam | Valid only after Petrus carries identity |
| Public bounded Worker pump | Lets a host scheduler execute available work without a Worker thread | Scheduling mechanics, not scope or Instance authority | Independently useful |
| Shared long-lived Worker | Existing operational model and async concurrency | Host must supervise lifecycle; still needs scoped resolution | Remains valid |

An Activity module is currently expected to remain ordinary host-composed code:
a cohesive object or mapping of named effects that can be copied, decorated,
replaced, or overlaid with normal Python composition. Durable custody carries
only Instance identity plus the existing symbolic Activity name. Live modules,
closures, clients, credentials, Engines, markings, and mutable ambient context
remain process configuration and are never serialized. A scoped resolver must
be reconstructible from durable identity and host configuration after restart.

## Experiments and acceptance evidence

Completed executable probes:

1. `[E]` Two Instances shared one Local custody domain and Worker. One selected
   its scoped module, one fell back explicitly to the default, and each
   Engine-facing session collected only its own terminal.
2. `[E]` A delayed retry retained Instance identity and selected the same
   scoped operation after Worker reconstruction, using only durable epoch and
   scope rather than process-local closure state.
3. `[E]` Synchronous, bridged-async, native-async, Local, Absurd, and ZeroMQ v2
   paths preserve scope. A configured resolver fails closed on a missing scope;
   only an explicit `None` answer for a scoped Attempt selects the default.
4. `[E]` The ordinary default Worker and unchanged `InlineDispatch({...})`
   path remain green and Inline/Local produce byte-identical canonical History.
5. `[E]` `run_available(limit=...)` honors its bound, never waits or implicitly
   closes custody, refuses concurrent driving, and releases its guard even when
   provider cleanup fails.
6. `[E]` `scripts/check full` passed 2,125 tests. `scripts/check release`
   passed the same 2,125 tests in parallel and then 2,125 tests with 17 explicit
   external qualification routes deselected in fixed order. Those external
   routes are not claimed green.
7. `[E]` Existing Engine coverage continues to prove one live advancement lane,
   frozen-terminal projection without effect replay, and `next_maturation` as
   a host scheduling output. Multi-Instance scheduling remains host
   composition.

## Conclusion

The accepted candidate is first-class Instance identity on provider-neutral
Attempts and execution contexts, plus an optional Worker resolver that can
override the existing default Activity mapping by `(instance, activity)`.
An explicit `None` resolution falls back to the unchanged default mapping;
missing scope fails closed whenever a resolver is configured. This is an
additive composition seam, not a durable service locator.

The delivered synchronous Worker also exposes a bounded `run_available` pump
for host-owned scheduling. Petrus will not add a multi-Instance scheduler,
runnable index, webhook custody, per-Instance thread, PostgreSQL requirement,
or Activity-module container in this story.

## Decision state

Delivered by
[`Instance identity scopes shared Activity resolution`](../../decisions/records/2026-08-10T1200Z-instance-identity-scopes-shared-activity-resolution.md).
Adversarial review approved the implementation after strict ZeroMQ versioning,
Absurd raw-task compatibility, native-async parity, Worker cleanup, and this
coherence update were verified.
