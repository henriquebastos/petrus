# DST outer-process runner version 1

**Status:** Current supported cross-project wall-clock containment contract.
This is a test-kit runner, not a Petrus runtime product API, and it is not
re-exported from the `petrus` package root.

This document specifies `petrus.testing.dst.runner/v1`,
`petrus-dst-process-runner` protocol version 1, and
`petrus-dst-process-run-result` version 1. These identities evolve separately
from `petrus.testing.dst/v4`, `petrus-dst-world` artifacts, profiles, and
checkers. The runner does not change artifact versions 1 through 4 or replay
result version 2.

## Purpose and boundary

Logical World budgets cannot interrupt a production or profile call which
never returns. A thread timeout cannot safely discard the call's live runtime,
and injecting a signal into arbitrary application code is not a portable
semantic contract. The outer runner therefore owns only nondeterministic host
containment:

1. start one complete importable scenario in a fresh process session;
2. acknowledge each normalized attempt before entering a profile operation;
3. acknowledge each complete legal World boundary before the next attempt;
4. enforce a monotonic wall-clock deadline in the parent;
5. terminate, escalate to kill after a bounded grace, and reap the child; and
6. report the exact acknowledged prefix and unfinished attempt without
   inventing a deterministic World failure.

Profiles and opaque generations are constructed entirely in the child and
never serialized. `ProcessSession.world(...)` is the sole composition door and
permits exactly one World. An entrypoint has the shape:

```python
def scenario(session: ProcessSession, payload: JsonValue) -> AnyScenarioArtifact:
    world = session.world(profile, budget, checkers=(checker,), seed=1729)
    # ordinary imperative Timeline scenario
    return world.artifact("scenario-identity")
```

`ProcessRunSpec.entrypoint` is an exact `dotted.module:function` identity. The
module and function must be importable in the fresh child. The payload is
strict detached JSON. The child validates the returned artifact and its exact
scenario identity, gracefully closes the World, then acknowledges completion.

## Bounds and acknowledgements

`ProcessBudget` is independent from deterministic World budgets:

- `wall_clock_ms` is positive and at most 30,000;
- `termination_grace_ms` is positive and at most 5,000;
- `input_bytes` is positive and at most 4,194,304; and
- `progress_bytes` is positive and at most 16,777,216.

The child writes canonical strict JSONL into a private runner directory. Each
line is flushed and synchronized before execution continues. A complete line
is therefore the unit of acknowledged progress; a partial line after process
loss is ignored. Frames carry dense sequence numbers and strict shapes:

- runner start and exact World/profile/checker/budget metadata;
- one `ProcessAttempt`, including `construct`, every normalized World attempt,
  and graceful `close`;
- boundary deltas containing dense expanded operations and full journal
  entries, including resource samples and checker results; and
- one completed artifact or a child failure code.

The parent validates frame order, dense operation/journal positions, the
artifact's expanded operations, and its exact journal digest. Malformed,
overflowing, reordered, or inconsistent progress fails closed as a process
protocol failure.

## Result semantics

`ProcessRunResult.outcome == "completed"` requires a clean child exit, no
unfinished attempt, and an ordinary strict World artifact whose operations and
journal digest equal the acknowledged prefix. Consumers replay that artifact
through the existing `replay(...)` interpreter.

A wall deadline returns `outcome == "harness_failure"` with
`WallClockFailure(kind="wall_clock_timeout", bound="wall_clock_ms", ...)`.
The result retains:

- exact World metadata, operations, and full journal through the last
  acknowledged boundary;
- the last logical instant, generation, and deterministic disposition, if one
  had already been committed; and
- the normalized unfinished attempt, when the child reached one.

`AcknowledgedPrefix` also exposes its last operation, journal entry, resource
sample, and checker result. A timeout never contains a `ScenarioArtifact` or
`FailureOperation`: wall-clock expiry is a harness containment fact, not a
replayable claim about whether the interrupted call would eventually return.
The prefix can diagnose and seed a later deterministic reproduction, but it is
not itself promoted as a replay artifact.

The current supervisor uses a fresh POSIX process group so descendants receive
the same terminate/kill escalation. The direct child is always waited and
reaped before `run_process_scenario(...)` returns. Unsupported process-group
hosts must fail loud rather than claiming containment they cannot provide.

## Executable proof

[`test_process_runner.py`](../../tests/dst/test_process_runner.py) executes two
complete routes:

1. the public-Engine resource-bounded crash/recovery World runs in a fresh
   process, returns its existing version-4 artifact, and replays exactly in a
   second fresh Engine graph; and
2. a profile call acknowledges `runtime.hang`, ignores `SIGTERM`, and is
   escalated to `SIGKILL`. The result reports the create boundary and exact
   unfinished `SubmitAttempt`, with no fabricated artifact.

All authored support stays under `tests/dst/`. The parent launches a minimal
interpreter adapter which imports the canonical `petrus.testing.dst` module and
invokes its private child operation; there is no second packaged runner module
or runtime-specific implementation. Supported operations and protocol values
remain owned by the defining module.
