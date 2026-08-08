---
id:
status: Carried
kind: test
severity: medium
source: CV9
revisit_trigger: next ZeroMQ server/readiness test change, ZeroMQ transport change, or complete-gate reliability work
closure_condition: the lost-reply tests deterministically establish initial server readiness before the timed claim and repeated complete gates pass
---

# ZeroMQ lost-reply test can time out before initial server readiness

## Description

`tests/petrus/motus/transport/test_zeromq_dispatch_transport.py::test_lost_heartbeat_and_failure_replies_are_not_replayed`
starts a server thread and immediately issues its first claim through a client
with a 50-millisecond request timeout. Under complete-suite load, the initial
claim can time out before the server acknowledges it. That is not the
heartbeat/failure-reply loss window the test intends to exercise.

The failure appeared twice during the CV9 interactive-proposal checkpoint and
passed immediately in exact isolated reruns. The current
verification-strengthening evidence separately reports a ZeroMQ subprocess
readiness path perturbed by coverage instrumentation. These observations point
to readiness-sensitive test evidence, but do not yet decide whether the
fixture needs an explicit ready handshake or the client contract needs a
bounded initial retry.

## Carrying Reason

CV9 does not change ZeroMQ transport, server startup, or the lost-reply test.
Changing its timeout or adding retries merely to make this checkpoint green
would hide the question of which readiness contract the test should prove.

## Impact

`scripts/check full` can fail without reaching the test's intended uncertainty
window, so a red complete gate may not identify a transport regression. The
same sensitivity can distort instrumentation or slower-host qualification.

## Revisit Trigger

Revisit on the next ZeroMQ server/readiness or transport change, when this test
recurs in an unrelated complete gate, or before release qualification relies
on this route.

## Closure Condition

Establish initial server readiness deterministically—or define and test the
supported bounded initial retry—before injecting the delayed heartbeat and
failure replies. The exact test must pass repeatedly under representative load
and repeated complete gates must pass.

## Notes

CV9 evidence: two complete runs failed at the first `client.claim()` with
`ZeroMQ Dispatch request 'claim' was not acknowledged`; the exact test passed
immediately after each observed failure. Every focused CV9 test passed.
