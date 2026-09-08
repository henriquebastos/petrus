---
status: Carried
kind: test
severity: medium
source: release-qualification
revisit_trigger: Full-suite process tests fail under runner contention
closure_condition: Process tests distinguish semantic deadlines from scheduling assumptions and pass on supported runners
---

# 1 Process tests assume short wall-clock budgets

The full-suite check exposed scheduling-sensitive assertions while running
unchanged code inside a Linux virtual machine. One four-worker run passed
2,594 tests and failed the large-output subprocess test in
`tests/petrus/motus/test_private_execution_substrate.py`. Several other process
and transport tests hit deadlines during more contended runs.

The large-output test requires exit code zero after truncating output. The
collector in `src/petrus/motus/_execution/providers.py` waits 50 ms before
checking an unfinished process against its output limit and terminating it.
An unfinished writer can therefore return a termination status under load.
This assertion depends on the writer finishing within the polling interval.

A focused process/provider selection passed 105 tests with one deselected on
a less contended runner. The result narrows the diagnosis but does not prove
that every observed timeout has the same cause.

The initial investigation preserves production code and test behavior. Revisit
this debt when adjusting the subprocess contract or investigating another
runner failure. Define whether truncation permits termination before changing
the assertion, and retain meaningful timeout coverage when reducing incidental
scheduling assumptions.

A hosted Linux run also passed 2,594 routine tests and failed
`test_context_close_orders_queued_heartbeats_before_terminal_without_detached_errors`
in `tests/petrus/motus/worker/test_async_worker.py`, because an expected
`RuntimeError` was not raised. This is a separate observed async-context failure;
its root cause has not been established. Reproduce the context-closing schedule
before treating it as another wall-clock failure. The release script stopped
before its serial suite.

## 1a Async Worker test correction, 2026-09-08

The async-context failure came from the test's schedule. Its outer coroutine
released the first heartbeat before the Activity had necessarily queued the
second. In that order, both heartbeats could complete before context closure,
so expecting a rejection was incorrect. Delaying the Activity's second-heartbeat
setup reproduced the hosted `DID NOT RAISE RuntimeError` failure.

The test now releases the provider only after the second heartbeat is queued,
immediately before the Activity returns. Context closure starts on the same
task before either heartbeat can resume. The existing assertions still require
one accepted heartbeat, one rejected heartbeat, one completion, and no detached
errors. Production code is unchanged. All 29 async Worker tests pass; the
controlled delayed schedule also passes 100 repetitions.

The large-output and other process-timing observations above remain carried.
This correction does not establish their root cause or change their contracts.

## 1b ZeroMQ terminal-reply setup correction, 2026-09-08

The next hosted release run passed the async Worker test and failed
`test_lost_terminal_reply_is_redelivered_exactly_until_acknowledged` during
its initial claim. That test applied a 50 ms request timeout to setup as well
as to the terminal reply it deliberately delays. An injected 100 ms claim
delay reproduced the same `ConnectionError` before completion was attempted.

Setup now uses the normal request timeout. After a successful claim, the test
sets 50 ms for completion, retaining the 200 ms injected terminal-reply delay,
one-second terminal retry budget, and exact durable-result assertion. All 30
transport tests pass. Ten controlled runs with the slower claim passed and
each submitted the same terminal report at least twice. Static checks passed;
production behavior is unchanged. The large-output and other unqualified
timing observations remain carried.
