---
status: Decided
raised: 2026-07-08
decided: 2026-07-08
deciders:
  - henrique (Navigator)
supersedes:
related:
  - docs/project/decisions/records/2026-07-08T0043Z-unpack-stdlib-handler-projection.md
  - docs/project/decisions/records/2026-07-08T0044Z-pack-aggregation-deferred.md
---

# Token-flow support line: ES-004 r3 is ratified

## Question

ES-004 catalogued the token-flow pattern space and proposed a supported /
handler-delegated / unsupported line, iterated to r3. Is r3 the ratified line?

## Decision

**Yes. The r3 support recommendation is the ratified token-flow support line.**
Future kernel and roadmap work respects these three sets:

- **CORE (22)** — structurally supported in the kernel: linear flow, duplication
  / homogeneous broadcast, type-routed outputs, arc-filter selection, sinks,
  accumulators, deferred choice, semaphore, and the rest of the r3 CORE set,
  under the permissive-flow-defaults and color-routed-passthrough semantics.
- **HANDLER-DELEGATED (16)** — expressible only via a handler (user, stdlib, or
  scheduler policy), deliberately not structural: aggregation/combine
  (AND-join, correlation join — user handler, since there is no stdlib `pack`
  [DR pack-aggregation-deferred]), fold/collection construction, and the
  scheduler-policy patterns (round-robin, etc.).
- **UNSUPPORTED-deferred (3)** — reset arc (TF-40), cancelling discriminator
  (TF-33, depends on reset), output-arc weight contract (TF-41). Admitted only
  against a concrete future need.

Refinements already recorded on top of r3: `unpack` moves deaggregation
patterns from user-handler to stdlib in a future r4 pass (set placement
unchanged) [DR unpack-stdlib-handler-projection]; no stdlib `pack`
[DR pack-aggregation-deferred].

## Consequences

- ES-004 is Promoted; its r3 sets are the reference for what the kernel must
  support structurally vs delegate to handlers.
- The two UNSUPPORTED-deferred items each need their own decision if ever
  admitted (reset arc changes boundedness analysis; output weight was
  Navigator-leaned against as a special case).

## Review Trigger

Revisit a set placement only when a concrete pattern cannot be expressed within
its assigned tier, or when an UNSUPPORTED-deferred item gains a concrete need.
