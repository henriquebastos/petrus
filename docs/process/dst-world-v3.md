# DST executable World version 3

**Status:** Current supported cross-project test-kit contract. This is not a
Petrus runtime product API and is not re-exported from the `petrus` package
root.

This document specifies `petrus.testing.dst/v3` and `petrus-dst-world`
artifact version 3. It adds seeded discovery provenance to the exact operations
and failure semantics owned by the supported [version 2 contract](dst-world-v2.md).
The replay-result shape does not change: version 3 artifacts still produce
`petrus-dst-world-replay-result` version 2. Artifact and result versions evolve
independently.

Versions 1 and 2 remain strict decode/replay contracts under
[`dst-world-v1`](dst-world-v1.md) and [`dst-world-v2`](dst-world-v2.md). The
[test-kit decision](../project/decisions/records/2026-08-17T2249Z-ship-a-supported-cross-project-dst-test-kit.md)
continues to own the support boundary.

## Compatibility change

| Concern | Previous | Current |
| --- | --- | --- |
| Python test-kit API | `petrus.testing.dst/v2` | `petrus.testing.dst/v3` |
| Expanded artifact | `petrus-dst-world`, version 2 | `petrus-dst-world`, version 3 |
| Replay result | `petrus-dst-world-replay-result`, version 2 | unchanged, version 2 |

Version 3 adds `ChoiceStreams`, the `World(seed=...)` composition door, and an
`origin` field containing either seeded provenance or `null`. Profile doors,
opaque generation ownership, checker cadence, scheduling, failure retention,
and replay meanings do not change. The defining module exports explicit v1/v2
constants and models; unknown artifact versions still fail closed.

## Seeded authorities

`ChoiceStreams` uses the pinned `sha256-counter-v1` algorithm. One integer seed
from 0 through `2^53 - 1` derives four explicit authorities:

| Authority | Intended ownership |
| --- | --- |
| `workload` | Which valid or deliberately invalid normalized external action a DS3 generator proposes. |
| `fault` | Which profile-owned fault/cut/disposition a generator proposes. |
| `identifier` | Stable generated IDs, isolated further by normalized namespace. |
| `event_order` | Which eligible external/scheduler ordering a generator proposes. |

Every authority has its own counter and hash domain. Identifier namespaces have
their own counters as well. Additional fault, identifier, or event-order draws
therefore cannot perturb the workload sequence. `index(authority, stop)` uses
deterministic rejection sampling rather than biased modulo reduction;
`identifier(namespace)` returns a seeded 128-bit hexadecimal identifier.

For draw ordinal `n` and rejection probe `p`, the algorithm hashes the UTF-8
compact JSON array `["sha256-counter-v1", seed, stream_key, n, p]`. It reads
the digest as one unsigned big-endian 256-bit integer. For `stop` from 1 through
`2^53 - 1`, index draws accept values below the largest multiple of `stop` in
the 256-bit range and return the remainder; a rejection increments only `p`,
with a fail-loud ceiling of 16 probes. Identifier draws use stream key
`identifier:<namespace>`, probe `0`, and the first 16 digest bytes. Public tests
pin seed `1729` to workload indexes `[584, 541, 292, 147]` for `stop=1000` and
identifier `scenario-4a6cb3d68a08da140c56fd1ed8bcbce2`.

The World exposes these authorities only to the scenario author/generator as
`world.choices`. A World without a seed refuses that property. Profiles and
`ScenarioContext` receive no choice door: application semantics cannot hide a
random choice inside `apply`, `observe`, or lifecycle construction. Chosen
state-affecting values must return through ordinary normalized commands,
faults, and ordering operations.

## Provenance and replay

The artifact `origin` records:

- exact algorithm identity;
- root seed; and
- a sorted map of authority/identifier-namespace draw counts.

Provenance explains discovery but does not define reproduction. The expanded
operation list remains authoritative. Replay deliberately constructs an
unseeded World, never calls `ChoiceStreams`, and executes the retained commands,
faults, observations, queue choices, lifecycle operations, and terminal failure
attempts. Changing only `origin.seed` cannot change replay output. A future
algorithm change requires a new API/artifact compatibility identity, but old
expanded artifacts remain replayable without the old generator.

Choice draws are not a second interpreter and are not serialized as executable
callbacks. DS3 owns Hypothesis state machines, generator policy, semantic
coverage, and shrinking; those generators call these authorities and submit the
result through the same World/Timeline interpreter.

## Retained proofs

### Seeded choice provenance

[`seeded-projection-crash-recovery-world-v3.json`](../../tests/dst/fixtures/seeded-projection-crash-recovery-world-v3.json)
uses seed `1729` and all four authorities around the real public Engine profile.
Two fresh authored runs produce the same 17 expanded operations. Data-only
replay reconstructs after the retained crash and converges without consulting
the seed:

```bash
UV_FROZEN=1 uv run python -m tests.dst.replay_world \
  tests/dst/fixtures/seeded-projection-crash-recovery-world-v3.json
```

The route returns `outcome: "pass"`, `converged`, 17 operations, 27 journal
entries, and digest
`sha256:ddf70617988b010a3300fc6703eb0c8f1bc1c4b0751b4156c2059f851d34a779`.

### Pre-commit terminal refusal

[`history-refusal-crash-recovery-world-v3.json`](../../tests/dst/fixtures/history-refusal-crash-recovery-world-v3.json)
uses a second exact public-Engine profile around a faulting JSONL History
delegate. The profile refuses `ActivityCompleted` before the delegate accepts
it, observes no terminal or projection beyond the prior durable frontier,
abruptly drops the poisoned generation, and reloads through `Engine.load`.
Reconciliation republishes the recorded invocation without calling `prepare`;
the retained observation proves its occurrence, activity, input, execution
policy, correlation, and idempotency identities are unchanged. An exact
external terminal redelivery then converges under the fair suffix.

The independent commit-authority checker compares canonical terminal records
with authored external terminal deliveries minus observed pre-commit refusals
after every atomic operation and fresh load. Its deliberate-failure test proves
that it rejects a terminal above that external acceptance bound.

```bash
UV_FROZEN=1 uv run python -m tests.dst.replay_world \
  tests/dst/fixtures/history-refusal-crash-recovery-world-v3.json
```

The route returns `outcome: "pass"`, `converged`, 19 operations, 31 journal
entries including 11 checker evaluations, and digest
`sha256:d8a9dec14dc40dc5a27afeaec9028ac37646695e22ff75bee2ce7f2c0f06aff1`.

### Lifecycle reset and late terminal

[`lifecycle-reset-late-terminal-world-v3.json`](../../tests/dst/fixtures/lifecycle-reset-late-terminal-world-v3.json)
uses a third exact public-Engine profile. It opens lifecycle generation 1,
delivers identified scoped input, begins one Activity, and resets the scope to
generation 2 while that Activity is in flight. After an abrupt process drop,
`Engine.load` reconstructs the reset, and the fresh generation's first public
`advance` reconciles the cancellation fence before any late terminal enters
the new Dispatch.

The exact late result is quarantined once as `ActivityTerminalQuarantined`.
Redelivering it again is acknowledged without another History append, and the
cancelled Activity never records an ordinary terminal or projection effect. A
detached lifecycle-authority checker independently compares active generation,
canonical opens/resets/quarantines, terminal deliveries, and projection bounds
against authored world facts after every atomic operation and fresh load.

```bash
UV_FROZEN=1 uv run python -m tests.dst.replay_world \
  tests/dst/fixtures/lifecycle-reset-late-terminal-world-v3.json
```

The route returns `outcome: "pass"`, `quiescent`, 22 operations, 36 journal
entries including 13 checker evaluations, and digest
`sha256:1719800ed00cfb705535b47b359d23988080b19a073f6247a995776ab7d9b194`.

### Timer reconstruction

[`timer-crash-recovery-world-v3.json`](../../tests/dst/fixtures/timer-crash-recovery-world-v3.json)
uses a public-Engine profile with the World logical clock. The first generation
returns deadline 5 and is dropped while that deadline exists only in the
World's volatile queue. Fresh `Engine.load` reconstructs the same deadline
from canonical History. The World then advances once to instant 5 and records
exactly one `TimerMatured` plus one delayed firing.

The independent checker rejects early or duplicate maturation and any delayed
firing without its canonical maturation fact. The retained route returns
`outcome: "pass"`, `converged`, 15 operations, 24 journal entries including 8
checker evaluations, and digest
`sha256:82460bacb8628c897a35e19883cb0f91e07bc1343cd5944ea22592c940fc8a69`.

### LocalDispatch retry reconstruction

[`retry-crash-exhaustion-world-v3.json`](../../tests/dst/fixtures/retry-crash-exhaustion-world-v3.json)
composes the production SQLite LocalDispatch and Worker doors. A two-attempt
Activity reports one classified zero-backoff retryable failure, the process is
dropped, and a fresh Engine/LocalDispatch generation reclaims the same logical
invocation at epoch 2 without another `prepare`. The second retryable failure
exhausts the policy and records exactly one `ActivityFailed` plus
`FiringFailed`, with no business projection.

The profile deliberately claims only zero-backoff retry semantics; provider
time, delayed backoff, and lease expiry remain separate. Its independent
checker bounds terminal authority by authored failures and preserves logical
invocation identity across epochs. The retained route returns `outcome:
"pass"`, `quarantined`, 18 operations, 30 journal entries including 11 checker
evaluations, and digest
`sha256:8158a70525b02afd7fb705ddec9ffc62a66d8c4ec6c9c0872062d36a05402392`.

### LocalDispatch successful-terminal recollection

[`local-terminal-redelivery-world-v3.json`](../../tests/dst/fixtures/local-terminal-redelivery-world-v3.json)
proves the complementary successful-terminal cut. The Worker durably reports
one result to LocalDispatch, its exact duplicate is acknowledged, and a
different report is refused while canonical History still ends at
`ActivityRequested`. The process is then dropped before Engine collection.
Fresh `Engine.load` republishes the recorded invocation without another
`prepare`, recollects the durable terminal, and records one
`ActivityCompleted` plus one `FiringCompleted` with the first result.

The independent checker derives result authority and expected duplicate/
conflict dispositions from the authored provider-report ledger, then compares
that model with detached canonical History and marking observations. Claimant
UUIDs and provider timestamps do not enter the artifact. The retained route
returns `outcome: "pass"`, `converged`, 15 operations, 26 journal entries
including 10 checker evaluations, and digest
`sha256:ff332ce259e54320354ba2006e59053d4c5fb83488482de32081b8a5503ceab9`.

### Identified source delivery and redelivery

[`identified-delivery-redelivery-world-v3.json`](../../tests/dst/fixtures/identified-delivery-redelivery-world-v3.json)
drives the public Engine source door with stable external identities. One
delivery commits before process loss; a fresh `Engine.load` acknowledges its
exact redelivery without another canonical fact. Equal data under a distinct
identity remains a distinct delivery. Reusing the first identity for changed
content is refused by production ingress and poisons that writing generation,
so the World drops it and resumes only through a second public load.

The checker independently derives accepted identities, expected dispositions,
and output values from the authored delivery-attempt ledger, then compares
them with detached canonical delivery records and the public marking. During
the refused-command boundary, observations use the last legal detached marking
plus the unchanged durable JSONL History; the poisoned Engine is never read or
reused. The retained route returns `outcome: "pass"`, `external_wait`, 15
operations, 26 journal entries including 10 checker evaluations, and digest
`sha256:e0223b0e0dd5ce6ce964cb9a72e38a9370f7f6b8a38d9571cdc1179e9a03d8bc`.

### Delayed external terminal reconstruction

[`delayed-terminal-recovery-world-v3.json`](../../tests/dst/fixtures/delayed-terminal-recovery-world-v3.json)
separates external event delay from Dispatch-owned retry time. The profile
authors one provider result for logical instant 5 and returns it to the World
as a scheduled command. A crash discards that volatile queue entry while the
profile's modeled external truth remains. Fresh public `Engine.load` re-proposes
the same command; the fair phase advances directly to 5 and records one
Activity completion, firing completion, and projection.

The checker bounds canonical terminal facts by authored external deliveries
and rejects any completion before the authored logical instant. The retained
route returns `outcome: "pass"`, `converged`, 17 operations, 27 journal entries
including 9 checker evaluations, and digest
`sha256:a89273aadcb2aeb48e60832d658e6ae37ef8a09c5dcb14298e16bdd2b398c007`.

## Remaining CV19 scope

Version 3 supplies deterministic choice mechanics and provenance, not a
generator. The broader delivery, Dispatch, delayed retry/provider-time,
lifecycle, and transaction fault matrix plus the remaining
profile-retained-data/watchdog bounds remain in CV19.DS2. Stateful generation,
shrinking, broad independent models/checkers, and semantic coverage remain in
DS3; campaign and real-boundary qualification remain in DS4.

Nonzero LocalDispatch retry time remains at an explicit compatibility
boundary: SQLite is intentionally the provider clock and serialization
authority, and no public deterministic provider-time seam currently exists.
DST must not substitute the Engine clock, mutate private SQLite rows, or sleep;
that route requires an accepted provider-time design before implementation.
