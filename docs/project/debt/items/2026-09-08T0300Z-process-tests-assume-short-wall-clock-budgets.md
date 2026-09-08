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
