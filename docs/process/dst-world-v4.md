# DST executable World version 4

**Status:** Current supported cross-project test-kit contract. This is not a
Petrus runtime product API and is not re-exported from the `petrus` package
root.

This document specifies `petrus.testing.dst/v4` and `petrus-dst-world`
artifact version 4. It adds deterministic accounting for profile-owned
retained data and hidden pending work to the seeded choices, exact operations,
and terminal-failure retention specified by the supported
[version 3](dst-world-v3.md), [version 2](dst-world-v2.md), and
[version 1](dst-world-v1.md) contracts.

The replay-result shape remains `petrus-dst-world-replay-result` version 2.
Artifact, API, profile, checker, and eventual process-runner protocols evolve
independently and fail closed.

## Compatibility change

| Concern | Previous | Current |
| --- | --- | --- |
| Python test-kit API | `petrus.testing.dst/v3` | `petrus.testing.dst/v4` |
| Expanded artifact | `petrus-dst-world`, version 3 | `petrus-dst-world`, version 4 |
| Replay result | `petrus-dst-world-replay-result`, version 2 | unchanged, version 2 |

Version 4 adds `BudgetV4.profile_resources`, detached `ResourceUsage`, the
`ResourceScenarioProfile.resource_usage` door, and `resource` journal entries.
The legacy `Budget` shape remains exact for versions 1–3. A World using that
legacy shape never invokes the new profile door and still authors a strict
version 3 artifact; decode and replay retain all four artifact versions.

## Profile-resource contract

The generic kernel cannot infer what an application profile retains. The exact
profile owns the definitions; the World owns enforcement and replay:

```python
class BudgetV4:
    # The version 1–3 deterministic fields remain exact here.
    profile_resources: dict[str, int]

class ResourceUsage:
    values: dict[str, int]

class ResourceScenarioProfile(ScenarioProfile[Generation]):
    def resource_usage(self, generation: Generation | None) -> ResourceUsage: ...
```

The contract is strict:

1. Gauge names are normalized and values and limits are nonnegative
   JSON-portable integers, never booleans.
2. The usage keys equal the budget keys at every sample. Missing, additional,
   malformed, or changing keys are profile contract failures rather than
   simulated budget exhaustion.
3. The exact profile identity and digest pin the meaning and completeness of
   every gauge. A conforming profile reports every retained store and hidden
   pending-work collection which its operations can grow; the kernel does not
   assign application semantics to those names.
4. `resource_usage` is side-effect-free, receives no `ScenarioContext`, cannot
   consume faults or schedule work, and returns only detached `ResourceUsage`.
5. `generation=None` means that no runtime generation is live. Durable
   profile-owned state remains measured; live-only gauges remain present with
   value zero.
6. A value is legal through its declared limit. If multiple gauges exceed
   together, the lexicographically first name deterministically exhausts
   `profile_resources:<name>`.

The Petrus proof profile reports these exact gauges:

- `retained.history_records` and `retained.history_bytes`;
- `retained.marking_tokens` and `retained.marking_bytes`; and
- `pending.in_flight` and `pending.dispatch`.

Applications use names appropriate to their complete host graph and external
world. Exact-key enforcement proves only that the profile reported its pinned
manifest; profile conformance tests remain responsible for proving that the
manifest covers every growing store and pending collection.

## Sampling and failure semantics

The World samples before initial construction, after successful create, after
every accepted command/fault/observation/fair/finish boundary, after successful
fresh load, and after abrupt drop with `generation=None`. Follow-up proposals
are installed before the command's sample. A resource sample is journaled with
its trigger, generation, logical instant, and sorted detached gauges, so exact
replay includes every observed value in the journal digest.

Resource enforcement precedes checker evaluation at an accepted boundary. A
resource overage after an operation therefore retains that operation followed
by a terminal `FailureOperation` with `accepted_operations=1`; replay must
reproduce the same gauge, limit, operation boundary, journal, and
`budget_exhausted` disposition. Initial pre-create/create resource exhaustion
fails construction and, like other constructor failures, is not
artifact-retainable because no complete World exists.

The profile door must not raise the reserved `BudgetExhausted` exception to
report its own policy. Only the World compares a valid `ResourceUsage` with the
artifact's exact `BudgetV4` limits.

## Retained proofs

[`resource-bounded-recovery-world-v4.json`](../../tests/dst/fixtures/resource-bounded-recovery-world-v4.json)
uses only public Engine construction, drive, snapshot, records, abrupt close,
and fresh load doors. It measures retained History/marking and pending
Activity/Dispatch state before and after a crash, reconstructs the pending
Activity, accepts one terminal, and converges. Its data-only replay returns
`pass` / `converged`, 14 operations, 39 journal entries, and digest
`sha256:0e1ffac28729a33fe7bb19e4ec52869c150a6a5e8312018419be53c4f2d69baf`.

[`history-record-budget-exhaustion-world-v4.json`](../../tests/dst/fixtures/history-record-budget-exhaustion-world-v4.json)
sets `retained.history_records` to 5. The first Engine drive atomically appends
four records after the two-record initial History, so the artifact retains the
accepted drive and then the exact resource failure. Replay returns `pass` /
`budget_exhausted`, 3 operations, 10 journal entries, and digest
`sha256:845e62259ae1e18b1ab92f1a2f5c16b1757cea29181bda6e6cd767ce0857b451`.

Replay either route from the repository root:

```bash
UV_FROZEN=1 uv run python -m tests.dst.replay_world \
  tests/dst/fixtures/resource-bounded-recovery-world-v4.json

UV_FROZEN=1 uv run python -m tests.dst.replay_world \
  tests/dst/fixtures/history-record-budget-exhaustion-world-v4.json
```

## Wall-clock containment boundary

Version 4 does **not** claim a wall-clock watchdog. Logical budgets cannot
interrupt a production/profile call which never returns. A thread timeout
cannot kill that call safely, and signal injection is not a portable runtime
contract.

Honest hang containment belongs to the independently versioned
[`petrus.testing.dst.runner/v1`](dst-process-runner-v1.md). It starts the
complete World in a killable process, owns a monotonic deadline, terminates and
reaps on expiry, and reports the last acknowledged operation boundary. The
child streams each attempt before entering a profile call and each committed
operation/journal boundary before the next attempt. A killed run retains an
exact prefix and unfinished attempt but never fabricates a deterministic
`FailureOperation` for a call that did not return.

## Completed CV19 boundary

Version 4 closes generic profile-retained-data and hidden-pending-work
accounting, and the separate runner v1 closes wall-clock process containment.
The broader delivery/Dispatch/lifecycle/transaction fault matrix and
deterministic LocalDispatch provider-time design are delivered by DS2;
stateful generation, shrinking, broad independent models/checkers, and semantic
coverage by DS3; and campaign/failure-promotion/real-boundary qualification by
DS4. The [completed CV19 owner](../project/roadmap/cv19-deterministic-simulation-testing/index.md)
retains their evidence. Those application profiles and operations compose the
version 4 kernel without becoming additional generic API obligations.
