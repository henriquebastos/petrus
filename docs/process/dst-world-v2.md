# 1 DST World version 2 compatibility

This file records the version 2 differences. Start with the complete
[World reference](dst-world.md) for authoring and the shared interpreter rules.
The versioned artifact and replay contracts remain supported.

<a id="compatibility-change"></a>

## 1a Compatibility change

API `petrus.testing.dst/v2`; artifact `petrus-dst-world` version 2;
replay result `petrus-dst-world-replay-result` version 2. Version 2 adds exact
failed-attempt retention to v1. It has no `origin` field or profile-resource
accounting. Profile methods and exact identity resolution are unchanged.
The loader preserves v1 results without adding a `failure` field.

<a id="exact-failed-operation"></a>

## 1b Exact failed operation

See [exact failed operation](dst-world.md#exact-failed-operation) for the shared rules.

<a id="capture-semantics"></a>

## 1c Capture semantics

See [capture semantics](dst-world.md#capture-semantics) for the shared rules.

<a id="replay-semantics"></a>

## 1d Replay semantics

See [replay semantics](dst-world.md#replay-semantics) for the shared rules.

<a id="retained-proofs"></a>

## 1e Retained proofs


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

<a id="compatibility-boundary-and-completed-evolution"></a>

## 1f Compatibility boundary and completed evolution

The [completed CV19 record](../project/roadmap/cv19-deterministic-simulation-testing/index.md)
owns generated testing, campaigns, and real-boundary qualification. Those
profiles compose the World contract without changing this version.
