# DST executable World version 2

**Status:** Current supported cross-project test-kit contract. This is not a
Petrus runtime product API and is not re-exported from the `petrus` package
root.

This document specifies `petrus.testing.dst/v2`, `petrus-dst-world` artifact
version 2, and `petrus-dst-world-replay-result` version 2. It evolves the
accepted [version 1 contract](dst-world-v1.md) only where exact interpreter
failure retention requires a new strict shape. Version 1 artifacts and replay
results remain byte-compatible and replay through the same current
interpreter.

The [test-kit decision](../project/decisions/records/2026-08-17T2249Z-ship-a-supported-cross-project-dst-test-kit.md)
continues to own the support boundary. Profiles still own opaque application
generations and semantics; the kernel still owns deterministic scheduling,
bounds, generation revocation, checker cadence, strict artifacts, and replay.

## Compatibility change

| Concern | Legacy | Current |
| --- | --- | --- |
| Python test-kit API | `petrus.testing.dst/v1` | `petrus.testing.dst/v2` |
| Expanded artifact | `petrus-dst-world`, version 1 | `petrus-dst-world`, version 2 |
| Replay result | `petrus-dst-world-replay-result`, version 1 | `petrus-dst-world-replay-result`, version 2 |

Profile and checker identities remain independent exact name/version/digest
pins. A profile written for version 1 needs no new lifecycle or execution door:
`validate`, `validate_fault`, `create`, `load`, `apply`, `observe`, abrupt
`drop`, and graceful `close` retain their meanings. `ScenarioContext` still
has no scheduling or submission door, and follow-up work still returns to the
World as detached `ScheduledCommand` values.

The defining module exports explicit legacy constants and models. The loader
selects the strict model from the exact artifact version and rejects every
unknown version. Replay returns the matching result version, so replaying a
version 1 fixture does not add a version 2 `failure` field.

## Exact failed operation

Version 2 adds one terminal `FailureOperation` to the expanded operation union.
It contains:

- its dense operation position, logical instant, and current generation when
  one remains live;
- whether that same failed interpreter call had already accepted its one
  expanded operation before a bound/checker ended it;
- the exact attempted World operation; and
- one exact failure detail.

The closed attempt vocabulary mirrors the interpreter's public operations:

| Attempt | Exact replay action |
| --- | --- |
| `submit` | Submit the normalized command through the named generation. |
| `step` | Execute the next World-scheduled profile command. |
| `activate_fault` | Activate the exact validated fault on the named generation. |
| `observe` | Execute the exact named request and preserve whether it was a predicate poll. |
| `crash` | Re-enter the exact named crash cut on the named generation. |
| `restart` | Invoke fresh reconstruction. |
| `begin_fair` | Enter the fair suffix for the named generation. |
| `finish` | Attempt the exact authored ending disposition. |

There are two failure details:

- `budget_exhausted` retains the exact bound, limit, and deterministic error;
  and
- `invariant_failure` retains the exact checker-boundary error while the
  ordinary checker journal retains every checker identity, detached
  observation, result, and trigger.

The expected section repeats the terminal failure detail beside the complete
checker entries and journal digest. Strict validation requires exactly one
failure operation, requires it to be last, requires its kind/detail to equal
the expected ending, and links any accepted operation to the exact failed
attempt that produced it. This distinction prevents replay from applying a
successful prefix operation twice when a formerly failing checker now passes.
The format refuses any failure operation in a normally ended artifact.

## Capture semantics

The World records a failure only when its normalized operation ends through
the interpreter's own `BudgetExhausted` or a checker-returned
`InvariantViolation`:

1. If an accepted command reaches a checker failure or its returned follow-up
   work crosses a World bound, the accepted command operation remains first
   and the terminal failure operation follows it.
2. If a bound refuses the attempt before an accepted operation exists, the
   terminal failure operation alone records that attempted operation.
3. The World records the budget/checker journal evidence, appends the failure
   operation and journal entry, preserves the explicit failure disposition,
   and re-raises the live exception to the authored pytest scenario.
4. The author catches the expected live exception and asks the same World for
   its strict artifact. No exception or callback is serialized.

Arbitrary profile exceptions, checker implementation exceptions, malformed
values, and replay mismatches remain harness/programmer failures; version 2
does not relabel them as runtime counterexamples. Any failure during initial
`World` construction—including an initial checker refusal or profile-supplied
work crossing a queue/time bound—occurs before an author can own the World and
is not artifact-retainable. An artifact that exceeds its byte ceiling also
cannot be made trustworthy by embedding itself.

## Replay semantics

The expanded schedule remains authoritative. Replay walks operations by dense
position through the same World methods. A failed attempt must reproduce the
same accepted operation prefix, terminal `FailureOperation`, checker journal,
ending disposition, and complete journal digest. If the operation no longer
fails, fails on a different attempt, produces a different detail, or moves the
failure boundary, replay raises `ReplayMismatch`.

Reproducing the retained failure is a successful **replay**, so the structured
result has `outcome: "pass"` and separately reports the failure disposition and
detail. It does not claim the tested runtime behavior passed its invariant or
budget.

## Retained proofs

Two fixtures prove both failure families through the public Engine profile:

- [`action-budget-exhaustion-world-v2.json`](../../tests/dst/fixtures/action-budget-exhaustion-world-v2.json)
  retains an `observe` attempt refused at the exact action ceiling; and
- [`terminal-checker-failure-world-v2.json`](../../tests/dst/fixtures/terminal-checker-failure-world-v2.json)
  retains a deliberate independent checker refusal immediately after the real
  Engine commits one terminal firing.

Replay either fixture from the repository root:

```bash
UV_FROZEN=1 uv run python -m tests.dst.replay_world \
  tests/dst/fixtures/action-budget-exhaustion-world-v2.json

UV_FROZEN=1 uv run python -m tests.dst.replay_world \
  tests/dst/fixtures/terminal-checker-failure-world-v2.json
```

The first returns `budget_exhausted` with 2 operations and 4 journal entries.
The second returns `invariant_failure` with 6 operations and 15 journal
entries. Both return `outcome: "pass"` only because replay reproduced the exact
retained failure.

## Remaining CV19 scope

Version 2 removes the failed-case replay blocker for generated schedules and
shrinking. It does not itself generate or shrink a schedule. Explicit seeded
choice streams, broader pre/post-durable fault adapters, remaining
profile-retained-data/watchdog bounds, generated semantic coverage, and
real-boundary qualification remain owned by CV19.DS2–DS4.
