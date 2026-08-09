---
id: remote-territory-lookup-can-delay-cancellation
status: Paid
kind: operations
severity: medium
source: CV16.DS9
revisit_trigger: before CV16.DS11 adopts Gondolin or E2B runtime operations in a long-lived host
closure_condition: remote territory currency observation is explicitly bounded or moved outside operation publication locks with race-safe cancellation and admission tests
---

# Remote territory lookup can delay runtime cancellation

## Description

Pi native A4 and application-owned A5 re-check their current Motus territory
before publishing a runtime result. An E2B currency check can call the remote
provider while the operation serializes claim against cancellation. The result
gate fails closed, but an unbounded or slow provider lookup can delay `cancel()`
or `wait()` even after the model/helper work has settled.

## Carrying Reason

The DS9 binding cells need the current provider observation and use bounded
disposable infrastructure. Changing lock boundaries or provider timeout
contracts requires a separate concurrency design and race tests; it is not
necessary to establish the current split Brain/Hands semantics.

## Impact

A provider control-plane stall can reduce host liveness and delay cleanup. It
does not authorize stale publication, put credentials in Hands, or weaken DS2
admission, but it is unsuitable as an implicit long-lived-host timeout policy.

## Revisit Trigger

Revisit before DS11 composes these remote runtime operations into a long-lived
host, or earlier if the A4 live cell observes cancellation or settlement delay
at the provider-currency check.

## Closure Condition

Either every remote lookup used by publication has an explicit bounded timeout,
or lookup occurs outside the operation condition with cancellation/grant/
deadline re-checks before publication. Deterministic concurrency tests must
prove that cancellation remains responsive and no stale result can publish.

## Notes

The condition was exposed when the formerly Local-only native Pi adapter gained
Gondolin/E2B profiles. Application-owned A5 has the same underlying provider
observation shape and should close under the same solution.

Paid on 2026-08-09. Native A4 and application-owned A5 now perform territory
currency observation outside the operation condition, then re-enter the
condition to re-check cancellation, grant epoch, and deadline before claiming
publication. Deterministic Gondolin and E2B race tests prove that `wait()` and
`cancel()` remain responsive during a stalled observation, cancellation wins
without result publication, lapsed grant/deadline authority fails closed, and
a publication claim that already won still makes later cancellation too late.
Both runtime paths also refuse a stale publication-time territory observation.

This pays the operation-lock debt without claiming provider-wide timeout
bounds: provider cancellation and final settlement may still depend on the
remote provider returning, and territory currency remains a point-in-time
observation rather than a provider-side transaction spanning result storage.
