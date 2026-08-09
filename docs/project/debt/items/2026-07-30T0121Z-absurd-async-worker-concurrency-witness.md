---
id:
status: Paid
kind: test
severity: medium
revisit_trigger: next AsyncWorker or Absurd custody change, or before relying on a green complete repository gate
closure_condition: the Absurd integration deterministically proves the supported concurrency bound and scripts/check full passes
---

# Absurd AsyncWorker concurrency witness intermittently misses three overlapping Activities

## Description

`tests/petrus/motus/dispatch/test_absurd_adapter.py::test_async_worker_integrates_distinct_absurd_lane_claimants_and_terminals`
dispatches three Activities to a concurrency-3 `AsyncWorker`. All three
Activities complete, but the test reproducibly observes only two probes inside
its 20-millisecond overlap window and fails `assert peak == 3`.

The failure reproduced both in the four-worker complete suite and as one exact
PostgreSQL test under the machine-global harness lock. It is not coupled to the
Candidate Selection experiment retirement that exposed it. A later complete
suite passed the same test without a runtime change, confirming that the
current witness is intermittent rather than continuously red.

## Carrying Reason

The approved maintenance slice removes obsolete Candidate Selection evidence;
it does not own AsyncWorker scheduling, Absurd claim latency, or CV8 execution
guarantees. Changing the sleep to manufacture overlap would weaken the witness
without deciding whether the runtime or test synchronization is wrong.

## Impact

Complete-suite outcomes can alternate between green and this failure without a
relevant runtime change. The failure may be an overly narrow timing witness, or
it may indicate that a configured concurrency of three does not reliably admit
three Activities concurrently when Absurd claim and heartbeat overhead are
included. Until diagnosed, one green run cannot provide reliable evidence for
that integration guarantee.

## Revisit Trigger

Revisit before the next AsyncWorker or Absurd custody change, or before treating
a complete repository check as release or checkpoint evidence.

## Closure Condition

Replace timing coincidence with deterministic synchronization if the runtime
still supports three admitted concurrent Activities, or correct the runtime if
the bound has regressed. The exact test must pass repeatedly and
`scripts/check full` must return green.

## Notes

Discovery evidence on 2026-07-30: the complete suite reported 2,450 passed, 5
skipped, and this one failure; the exact isolated rerun failed with the same
`peak == 2` observation while all three Activities terminalized. A subsequent
unchanged complete run during Ariadnet modernization passed all 2,446 executed
tests with 5 skips. The debt remains carried because neither outcome explains
or deterministically controls the overlap.

The witness recurred during Liaison modernization: the first complete run
reported 2,445 passed, 5 skipped, and `peak == 2`. Unlike the original
discovery, the exact isolated rerun immediately passed; a subsequent unchanged
complete run also passed all 2,446 tests with 5 skips. This alternating outcome
further supports replacing the 20-millisecond coincidence with deterministic
synchronization before the test can qualify the concurrency guarantee.

The witness recurred more persistently during Secretary modernization. Two
unchanged complete runs each reported 2,445 passed, 5 skipped, and only this
failure at `peak == 2`. The first exact isolated rerun also failed at two; a
fresh isolated harness then passed at three before the second complete run
failed again. All three Activities terminalized in every failure. This rules
out coupling to the exact-equivalent Secretary topology change and strengthens
the case that timing coincidence cannot qualify the supported concurrency
bound.

During the paired Agent Factory topology modernization, the exact isolated
test passed at three between two unchanged complete runs that each failed at
two; both complete runs otherwise reported 2,445 passed and 5 skipped. The
alternation occurred while both Agent Factory suites and exact canonical-net
comparisons passed, adding another unrelated reproduction of the same timing
witness rather than evidence against those experiments.

The witness recurred twice during the CV9 interactive-proposal checkpoint. One
complete run observed `peak == 2`; the exact isolated test immediately passed
at three. A later unchanged complete run again observed two alongside one
unrelated ZeroMQ readiness failure. Every CV9-focused test passed. The current
`origin/main` verification-strengthening milestone independently records the
same Absurd witness followed by a green complete run, reinforcing that this
carried item—not CV9 behavior—owns the unstable gate signal.

**Paid 2026-08-09:** the witness now holds all admitted Activities behind one
release event until payloads `{1, 2, 3}` have entered their Activity bodies.
This deterministically proves three-way admission before any lane can
terminalize or recycle. Ten repeated exact runs and the 108-test related
AsyncWorker/Absurd surface passed; no runtime defect was found. The integrated
`scripts/check full` and both `scripts/check release` test runs passed with
2,011 tests each.
