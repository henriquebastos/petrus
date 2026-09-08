# 1 DST World version 4 compatibility

This file records the version 4 differences. Start with the complete
[World reference](dst-world.md) for authoring and the shared interpreter rules.
The versioned artifact and replay contracts remain supported.

<a id="compatibility-change"></a>

## 1a Compatibility change

API `petrus.testing.dst/v4`; artifact `petrus-dst-world` version 4;
replay result `petrus-dst-world-replay-result` version 2. Version 4 adds
`BudgetV4.profile_resources`, `ResourceUsage`,
`ResourceScenarioProfile.resource_usage`, and resource journal entries.
A World using `Budget` still authors v3 and never calls `resource_usage`.
Decode and replay support all four artifact versions.

<a id="profile-resource-contract"></a>

## 1b Profile-resource contract

See [profile-resource contract](dst-world.md#profile-resource-contract) for the shared rules.

<a id="sampling-and-failure-semantics"></a>

## 1c Sampling and failure semantics

See [sampling and failure semantics](dst-world.md#sampling-and-failure-semantics) for the shared rules.

<a id="retained-proofs"></a>

## 1d Retained proofs


[`resource-bounded-recovery-world-v4.json`](../../tests/dst/fixtures/resource-bounded-recovery-world-v4.json)
uses only public Engine construction, drive, snapshot, records, abrupt close,
and fresh load doors. It measures retained History/marking and pending
Activity/Dispatch state before and after a crash, reconstructs the pending
Activity, accepts one terminal, and converges. Data-only replay returns `pass` with disposition `converged`. The fixture
retains the exact operations, checker expectations, and journal digest.

[`history-record-budget-exhaustion-world-v4.json`](../../tests/dst/fixtures/history-record-budget-exhaustion-world-v4.json)
sets `retained.history_records` to 5. The first Engine drive atomically appends
four records after the two-record initial History, so the artifact retains the
accepted drive and then the exact resource failure. Replay returns `pass` with disposition `budget_exhausted` when it reproduces
the retained accepted operation and resource failure exactly.

Replay either route from the repository root:

```bash
UV_FROZEN=1 uv run python -m tests.dst.replay_world \
  tests/dst/fixtures/resource-bounded-recovery-world-v4.json

UV_FROZEN=1 uv run python -m tests.dst.replay_world \
  tests/dst/fixtures/history-record-budget-exhaustion-world-v4.json
```

<a id="wall-clock-containment-boundary"></a>

## 1e Wall-clock containment boundary

The independent [process runner](dst-process-runner-v1.md) contains calls
that never return. A killed run retains an acknowledged prefix and unfinished
attempt, never a fabricated deterministic `FailureOperation`.

<a id="completed-cv19-boundary"></a>

## 1f Completed CV19 boundary

The [completed CV19 record](../project/roadmap/cv19-deterministic-simulation-testing/index.md)
owns generated testing, campaigns, and real-boundary qualification. Those
profiles compose the World contract without changing this version.
