# DST executable World version 1

**Status:** Supported cross-project test-kit contract. This is not a Petrus
runtime product API and is not re-exported from the `petrus` package root.

This document specifies the `petrus.testing.dst/v1` defining-module contract
and its `petrus-dst-world` version 1 expanded replay artifact. The accepted
[test-kit decision](../project/decisions/records/2026-08-17T2249Z-ship-a-supported-cross-project-dst-test-kit.md)
owns the compatibility promise; the broader correctness obligations remain in
the [DST owner](deterministic-simulation-testing.md).

The test kit is an executor around application-owned runtime generations. It
does not implement Petri-net semantics, readiness semantics, provider truth,
or an application oracle. Petrus's proof profile uses only public `Engine`
construction, advance, snapshot, record, load, and close doors. An application
profile may instead own a complete host graph without exposing it to the
kernel.

## Compatibility identities

Four pins evolve independently and fail closed:

| Concern | Version 1 identity |
| --- | --- |
| Python test-kit API | `petrus.testing.dst/v1` |
| Expanded artifact | `petrus-dst-world`, version `1` |
| Scenario profile | exact name, positive version, and `sha256` implementation digest |
| Checker | exact name, positive version, and `sha256` implementation digest |

Changing a supported method's meaning, required profile door, value shape, or
interpreter policy requires a new API compatibility identity. Adding or
changing an artifact field or operation requires a new artifact version.
Changing application command, observation, fault, construction, or checking
semantics requires a new profile or checker identity/digest. Replay resolves
all three component identity fields exactly through `ScenarioRegistry`.

This contract is separate from:

- public hosted simulation's `implementation-free-v1` result;
- internal [`petrus-dst-scenario` version 1](dst-scenario-v1.md); and
- the internal `engine-coordinator-v1` replay profile.

None of those contracts is widened, renamed, or accepted as an alias.

## One interpreter, three inputs

There is one normalized execution path:

```diagram
┌──────────────────┐
│ Authored Timeline│──┐
└──────────────────┘  │
┌──────────────────┐  │   ┌──────────────────┐   ┌─────────────────────┐
│ Generated commands│─┼──▶│ World interpreter│──▶│ Application profile │
└──────────────────┘  │   └────────┬─────────┘   └─────────────────────┘
┌──────────────────┐  │            │
│ Artifact replay  │──┘            ▼
└──────────────────┘       ┌──────────────────┐
                           │ Journal/checkers │
                           └──────────────────┘
```

`Timeline` is an imperative authoring facade. Python control flow, helpers,
assertions, and `run_until` predicates remain ordinary test code. They are not
serialized. Every state-affecting operation still crosses `World`; the
artifact retains the normalized command, queue choice, logical instant,
observation, checker result, lifecycle operation, and final disposition that
actually occurred. Replay executes those expanded operations through the same
interpreter without importing the originating scenario or consulting a seed.

## Profile contract

A `ScenarioProfile[Generation]` owns one opaque generation and these doors:

| Door | Obligation |
| --- | --- |
| `validate(command)` | Fail loud on an unknown name, payload, or profile identity before application. Return the exact normalized `Command`. |
| `validate_fault(fault)` | Fail loud on an unsupported fault name, target, occurrence, disposition, or payload before activation. Return the exact normalized `Fault`. |
| `create(context)` | Construct a fresh generation and return `GenerationStart` with only currently eligible detached follow-up proposals. |
| `load(context)` | Reconstruct a fresh generation from retained configuration, durable stores, and modeled external truth. Return eligible detached follow-ups. |
| `apply(generation, command, context)` | Perform one application-defined atomic operation and return strict detached `ApplyResult` data plus eligible follow-up proposals. |
| `observe(generation, request, context)` | Validate the named request and return detached strict JSON. Never return a live generation or mutable runtime handle. |
| `drop(generation)` | Abruptly dispose volatile resources without semantic settlement. |
| `close(generation)` | Gracefully release the final live generation; application hosts may perform their documented graceful settlement here. |

`GenerationStart.scheduled` is an exact tuple of `ScheduledCommand` values.
`ApplyResult.scheduled` is an exact list of those values. A profile may propose
work but cannot enqueue or execute it. `ScenarioContext` exposes only the
current logical instant, deterministic namespace-scoped stable IDs, and faults
consumed at a named application cut. It has no scheduling, submission, replay,
or live-runtime door, and recursive interpreter entry fails loud.

`Command`, `Fault`, scheduled work, apply results, observations, checker
details, journals, and artifacts accept strict JSON only. They reject Python
extensions, non-string object keys, duplicate artifact keys, non-finite
numbers, unknown model fields, and implicit Pydantic coercion.

## Deterministic scheduling and bounds

The World starts at logical instant `0`. It orders queued commands by
`(logical instant, insertion order)`. Profile-proposed work and authored
commands receive their queue order only from the World. Commands cannot be
scheduled in the past or beyond the logical-instant ceiling. A command at a
future instant advances time directly; simulated execution never sleeps.

`Budget` explicitly bounds:

- normalized actions, including observations and predicate polls;
- simultaneously queued commands;
- logical-time advances and the maximum logical instant;
- fresh reloads;
- `run_until` predicate polls; and
- canonical artifact bytes.

Exhaustion sets `Disposition.BUDGET_EXHAUSTED`, records the exact bound and
limit, and raises `BudgetExhausted`. No queue or artifact is silently
truncated. Version 1 does not provide a wall-clock watchdog around application
profile calls; profiles admitted to this deterministic executor must return
synchronously, while the repository test runner owns process-level timeout
operation.

`run_until(name, predicate)` repeatedly records the named detached
observation and executes the next profile-declared command. It succeeds when
the Python predicate accepts that observation. If no work remains, it raises
`RunUntilFailed` classified as `external_wait` with the last observation,
pending queue, budget, and recent journal.

## Runtime generations and fairness

Every Timeline is bound to one monotonically numbered generation. Crash
handling is strictly ordered:

1. capture detached checker observations at the cut;
2. revoke the current generation and clear its queued volatile work;
3. call the profile's non-settling `drop`; and
4. permit reconstruction only through `load`.

The stale Timeline refuses every later use. Graceful `World.close()` is
distinct and invokes `close` only for a currently live generation. A profile
whose create/install path fails after yielding a generation is closed by the
World before the constructor propagates the failure.

`begin_fair` is a journaled one-way boundary. It requires all activated faults
to have been consumed. Afterward, the World refuses new authored commands,
faults, process crashes, repeated fair entry, and an `external_wait` ending.
Profile-declared queued work can only be drained in deterministic order, and
no ending disposition can overtake queued work. Fairness never manufactures a
provider response or human decision: a profile must disclose every eligible
runtime/environment action as scheduled work before fair convergence is
claimed.

## Checker cadence

Each `Checker` has an exact identity and one closed `ObservationRequest`.
Checkers receive only detached observations. They run:

- after generation creation;
- after every accepted command;
- after fault activation;
- at an abrupt crash cut before non-semantic disposal;
- after every successful fresh load; and
- when the fair phase begins.

They do not run inside an application operation or inspect the live generation.
Every verdict is journaled. A failed result sets
`Disposition.INVARIANT_FAILURE` and raises `InvariantViolation` at that atomic
boundary.

## Artifact and replay contract

A version 1 artifact contains exactly:

- format, artifact version, API identity, and scenario identity;
- exact profile and ordered checker manifest identities;
- the complete `Budget`;
- dense zero-based expanded operations; and
- expected authored ending disposition, exact checker journal entries, and a
  canonical digest of the complete journal.

Operations form a closed discriminated union: command execution, fault
activation, observation, crash, restart, fair entry, and finish. Replay
reconstructs a World from the exact registered profile/checkers, applies each
operation through the same methods, compares every expanded result, checker
entry, disposition, and journal digest, and always gracefully closes a live
generation. Any mismatch raises `ReplayMismatch`; success returns one strict
`petrus-dst-world-replay-result` version 1 value.

Version 1 artifacts retain authored endings (`converged`, `quiescent`,
`external_wait`, or `quarantined`). The live World reports budget exhaustion
and invariant failure explicitly, but version 1 refuses to emit a misleading
artifact for those interpreter failures because it does not yet serialize the
failed attempted operation. Retaining and replaying generated failure
attempts is remaining CV19.DS2/DS3 work and requires an explicit artifact
evolution.

The first retained proof is
[`projection-crash-recovery-world-v1.json`](../../tests/dst/fixtures/projection-crash-recovery-world-v1.json).
It is generated by an imperative pytest story under `tests/dst`, activates a
named projection cut, abruptly drops its public-Engine generation, loads fresh
objects from retained JSONL History, and converges through projection-only
recovery without redispatch. Run the data-only replay from the repository
root:

```bash
UV_FROZEN=1 uv run python -m tests.dst.replay_world \
  tests/dst/fixtures/projection-crash-recovery-world-v1.json
```

Success emits one deterministic JSON line with `outcome` equal to `pass`.
All scenario authoring support, proof profiles, replay adapters, retained
fixtures, and pytest assertions remain self-contained under `tests/dst/`;
there is no parallel `scripts/` DST implementation.
