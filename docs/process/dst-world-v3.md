# DST executable World version 3

**Status:** Supported legacy cross-project test-kit contract. Version 4 is the
current artifact-authoring contract; version 3 decode and replay remain
supported unchanged. This is not a Petrus runtime product API and is not
re-exported from the `petrus` package root.

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

New scenarios which account for profile-owned retained state use the
[`petrus.testing.dst/v4` contract](dst-world-v4.md).

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

### Dispatch acceptance refusal

[`dispatch-refusal-crash-recovery-world-v3.json`](../../tests/dst/fixtures/dispatch-refusal-crash-recovery-world-v3.json)
targets the existing public `Dispatch.dispatch` contract after the production
Engine has committed `ActivityRequested`. The test adapter refuses custody,
and the profile observes six canonical records, no pending Dispatch work, and
a poisoned live Engine. Abrupt process loss then discards the generation.

Fresh `Engine.load` reconstructs the outstanding Activity solely from History
and republishes the byte-equivalent occurrence, activity, input, execution
policy, correlation, and idempotency through a new Dispatch. The total handler
`prepare` count remains one. An independent checker continuously bounds
terminal authority by accepted Dispatch attempts and rejects re-preparation or
a changed invocation.

```bash
UV_FROZEN=1 uv run python -m tests.dst.replay_world \
  tests/dst/fixtures/dispatch-refusal-crash-recovery-world-v3.json
```

The route returns `outcome: "pass"`, `converged`, 14 operations, 24 journal
entries including 9 checker evaluations, and digest
`sha256:63301ff867ae1c9950d0307e9ad74952e4c10105e3d60d24cd00a5e0496f733a`.

### Joined begin-transaction commit refusal

[`joined-begin-commit-refusal-world-v3.json`](../../tests/dst/fixtures/joined-begin-commit-refusal-world-v3.json)
uses the public `petrus.engine.absurd` provider over disposable PostgreSQL.
Unlike the split Dispatch-refusal profile, Absurd places
`CandidateSelected`, the firing prefix, `ActivityRequested`, and task spawn in
one joined transaction. A connection-boundary adapter refuses that commit
before acceptance; production Engine rollback and poison handling run
unchanged. Independent PostgreSQL observations then find only the two-record
construction prefix and no Absurd queue task.

The World revokes and drops the poisoned generation. Fresh public provider
load reconstructs the original marking, prepares the candidate again because
no invocation was ever durable, and accepts exactly one four-record begin plus
one pending task. The checker continuously equates durable candidate, firing,
request, and task counts with the adapter's accepted joined-transaction ledger
and rejects a phantom post-rollback task. The scenario ends in the legitimate
external wait for a Worker result; it does not invent one.

This profile is real-boundary qualification, not a claim that the generic
World simulates PostgreSQL or Absurd. Its data-only concrete replay route uses
the ordinary pytest PostgreSQL harness:

```bash
UV_FROZEN=1 uv run pytest -q \
  tests/dst/test_joined_world.py::test_retained_joined_begin_fixture_replays_without_the_authored_scenario
```

The route returns `outcome: "pass"`, `external_wait`, 9 operations, 16 journal
entries including 6 checker evaluations, and digest
`sha256:0b2129eaf3802d174a5526f5e32b0e6de8f923cd2d8ce3e05bd89c2904c930c7`.

### Joined Dispatch refusal before commit

[`joined-dispatch-refusal-world-v3.json`](../../tests/dst/fixtures/joined-dispatch-refusal-world-v3.json)
uses a separate profile identity over the same public Absurd/PostgreSQL
composition. Its one-shot adapter raises at the provider's task-spawn call,
after production has prepared the four semantic begin records but before task
insertion or transaction commit. Production rollback again leaves only the
construction prefix and no task, but this cut proves the Dispatch-failure path
rather than a refused commit acknowledgement.

After abrupt drop, fresh public provider load prepares from the original
marking and commits exactly one begin plus one pending task. The same detached
transaction-authority checker rejects partial prefixes and phantom tasks; the
scenario again stops at the legitimate external wait for a Worker result.

```bash
UV_FROZEN=1 uv run pytest -q \
  tests/dst/test_joined_world.py::test_retained_joined_dispatch_fixture_replays_without_the_authored_scenario
```

The route returns `outcome: "pass"`, `external_wait`, 9 operations, 16 journal
entries including 6 checker evaluations, and digest
`sha256:e9bc6574670b3c2d55c8659c3ba9b0bea826544502bd174cd4d5885577483a7a`.

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
time, delayed backoff, and lease expiry remain separate in that retained
profile. Its independent checker bounds terminal authority by authored
failures and preserves logical invocation identity across epochs. The retained
route returns `outcome: "pass"`, `quarantined`, 18 operations, 30 journal
entries including 11 checker evaluations, and digest
`sha256:8158a70525b02afd7fb705ddec9ffc62a66d8c4ec6c9c0872062d36a05402392`.

### LocalDispatch delayed-retry reconstruction

[`delayed-retry-crash-recovery-world-v3.json`](../../tests/dst/fixtures/delayed-retry-crash-recovery-world-v3.json)
uses the separately accepted LocalDispatch provider clock while leaving SQLite
as custody and serialization authority. Epoch 1 fails at World instant 0 with
a five-second retry interval. The process drops after retry admission; fresh
public `Engine.load` and LocalDispatch construction preserve the durable
availability deadline without another handler `prepare`.

The World executes one public Worker claim at instant 4 and observes no work,
then executes the same door at instant 5 and receives epoch 2 with unchanged
activity, input, policy, correlation, and idempotency. An independent checker
rejects any claim sequence other than first claim → unavailable-before-deadline
→ available-at-deadline while retaining the original retry/exhaustion bounds.
The retained route returns `outcome: "pass"`, `quarantined`, 22 operations, 35
journal entries including 12 checker evaluations, and digest
`sha256:339da88d51c682641b7e8fc8fbf8964622c2c031dd6c373f327b94464e26a6c1`.

### Lifecycle cancellation-refusal reconstruction

[`lifecycle-cancellation-refusal-world-v3.json`](../../tests/dst/fixtures/lifecycle-cancellation-refusal-world-v3.json)
targets the public Dispatch cancellation door after `ScopeReset` has committed.
The first generation retains the exact cancellation instruction but refuses
custody, leaving the live Engine poisoned while canonical History already owns
generation 2. The World revokes and drops that generation without settlement.

Fresh `Engine.load` reconstructs the reset and submits the byte-equivalent
occurrence, Activity invocation, policy, correlation, idempotency, and History
position to a new Dispatch. The reset remains terminal authority; the accepted
tombstone proves operational repair before the authored late delivery. The
cancelled result never becomes an ordinary terminal or projection. The
independent checker derives lifecycle and terminal bounds from authored facts
and rejects changed repair instructions. The retained
route returns `outcome: "pass"`, `quiescent`, 19 operations, 32 journal entries
including 12 checker evaluations, and digest
`sha256:0b4ccbadb61d020c28ea3f330fbd2a7bf27b1af9157db2a375e25f6bcbb3da69`.

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

### Post-commit History acknowledgement loss

[`history-ack-loss-recovery-world-v3.json`](../../tests/dst/fixtures/history-ack-loss-recovery-world-v3.json)
is the accepted side of the History ambiguity pair. Its adapter delegates the
terminal append to production `JsonlHistoryStore`, observes durable acceptance,
then raises as if the acknowledgement were lost. The writing Engine poisons;
the World reads only the adapter's durable detached records at that boundary,
drops the generation, and resumes through public `Engine.load`. Projection then
completes without terminal redelivery or handler preparation.

The checker treats the adapter's post-delegate callback as independent durable
acceptance evidence and bounds canonical terminal/projection records by the
authored external delivery. The retained route returns `outcome: "pass"`,
`converged`, 15 operations, 25 journal entries including 9 checker evaluations,
and digest
`sha256:b69cd6760d3a1818f4cbfcc5f531d7ad3c970b0e383c5b5ba0abd62a0ff47c92`.

### Joined begin acknowledgement loss

[`joined-begin-ack-loss-world-v3.json`](../../tests/dst/fixtures/joined-begin-ack-loss-world-v3.json)
proves the accepted side of the real Absurd/PostgreSQL joined-begin boundary.
Production commits `CandidateSelected`, the firing prefix,
`ActivityRequested`, and one task in the same transaction; the test connection
then raises as if that commit acknowledgement were lost. Detached PostgreSQL
truth shows exactly one semantic begin and one pending task while the writing
Engine poisons.

Fresh public `load_engine` drives to the legitimate Worker wait without another
handler `prepare`, semantic append, or task. The checker derives authority from
accepted transaction attempts and detached PostgreSQL History/task custody; it
rejects an acknowledgement-loss claim without that durable truth. The retained
route returns `outcome: "pass"`, `external_wait`, 9 operations, 15 journal
entries including 6 checker evaluations, and digest
`sha256:e335a248d18103ea1e19e1843bb1666d760a19296cca35c7a5363ddde692466e`.

### Joined terminal acknowledgement loss

[`joined-terminal-ack-loss-world-v3.json`](../../tests/dst/fixtures/joined-terminal-ack-loss-world-v3.json)
proves the accepted side of the real Absurd/PostgreSQL terminal boundary. A
real Worker completes one task and production commits `ActivityCompleted`; the
test connection then raises as if that terminal commit acknowledgement were
lost. Detached provider truth shows one completed task and one canonical
terminal while the writing Engine poisons.

Fresh public `load_engine` projects the accepted terminal exactly once without
another Worker completion, terminal delivery, or handler `prepare`. The checker
derives terminal authority from accepted PostgreSQL transaction attempts,
completed provider custody, and recorded Worker completion; it independently
requires an accepted projection transaction for canonical projection. The
retained route returns `outcome: "pass"`, `converged`, 12 operations, 21 journal
entries including 9 checker evaluations, and digest
`sha256:77698d04b4827861bf7f090606b37a576bdee4cb558d644147f9c34891b4f6b8`.

### Joined terminal and refused projection commit

[`joined-projection-commit-refusal-world-v3.json`](../../tests/dst/fixtures/joined-projection-commit-refusal-world-v3.json)
qualifies the generic projection-recovery cut against the public Absurd Engine
and Worker providers over disposable PostgreSQL. A real Worker claims and
completes the pending task. Production first commits `ActivityCompleted`, then
a connection-boundary fault refuses the separate `TokensProduced` and
`FiringCompleted` transaction. The live Engine is poisoned and abruptly
dropped; fresh public `load_engine` accepts that exact projection once without
another Worker completion or handler `prepare`.

The independent checker derives terminal authority from completed provider
custody and recorded Worker completion, and projection authority from accepted
or refused PostgreSQL transaction attempts. It rejects a canonical projection
after the refused attempt. The retained route returns `outcome: "pass"`,
`converged`, 12 operations, 21 journal entries including 9 checker evaluations,
and digest
`sha256:a4670deb5ec8841f29c8e6f716488c22cb7c91ffe3084867ae54704a8fe2ec6b`.

### Joined lifecycle cancellation commit refusal

[`joined-cancellation-commit-refusal-world-v3.json`](../../tests/dst/fixtures/joined-cancellation-commit-refusal-world-v3.json)
qualifies the lifecycle cancellation-repair cut against the same public Absurd
Engine and Worker providers. Production first commits `ScopeReset`, then the
test connection refuses the separate transaction which would cancel the real
running task. Detached PostgreSQL truth retains generation 2 and the running
task while the live Engine poisons.

The World revokes and drops only that Engine generation; the real external
Worker remains alive. Fresh public `load_engine` replays the canonical reset,
commits one tombstone against the same idempotency key, and leaves History at
the reset frontier without another handler `prepare`. The old Worker's late
completion is refused as stale at the provider boundary, so no
`ActivityCompleted` or business projection enters History. The independent
checker derives authority from authored lifecycle/Worker facts, accepted or
refused transaction attempts, and detached History/task custody. The retained
route returns `outcome: "pass"`, `quiescent`, 19 operations, 31 journal entries
including 12 checker evaluations, and digest
`sha256:1c49f2de218e8579894a9f55248e81b3e058a977a2ebffecd82b19880661dbf0`.

### Joined lifecycle cancellation acknowledgement loss

[`joined-cancellation-ack-loss-world-v3.json`](../../tests/dst/fixtures/joined-cancellation-ack-loss-world-v3.json)
proves the accepted side of that real Absurd/PostgreSQL cancellation boundary.
Production commits `ScopeReset`, turns the real running task into a durable
cancellation tombstone in the following transaction, and then loses that
transaction's acknowledgement. Detached PostgreSQL truth shows generation 2,
exactly one cancelled task, and no semantic terminal or projection while the
writing Engine poisons.

The World revokes and drops only the Engine generation while preserving the
external Worker. Fresh public `load_engine` recognizes the existing tombstone
without another `cancel_task`, handler `prepare`, semantic append, or task.
The old Worker's completion remains fenced as stale. The independent checker
requires one accepted reset and one accepted cancellation transaction, then
compares those facts with detached History and task custody at every legal
boundary. The retained route returns `outcome: "pass"`, `quiescent`, 19
operations, 31 journal entries including 12 checker evaluations, and digest
`sha256:c369eda31394c6de8287f23ea462c448fd2a7fb4e894a9ad163fd8b99c44630b`.

## Remaining CV19 scope

Version 3 supplies deterministic choice mechanics and provenance, not a
generator. Seven joined-provider profiles now prove real joined-transaction
commit refusal, pre-commit task-spawn failure, post-commit begin and terminal
acknowledgement loss, accepted-terminal/refused-projection recovery, and
both refused and accepted-but-unacknowledged post-reset cancellation-tombstone
recovery without widening the World contract; the broader delivery, Dispatch,
lifecycle, and transaction fault matrix remains in CV19.DS2. Version 4 subsequently adds
profile-retained-data and hidden-pending-work bounds without changing version 3
replay, and runner v1 contains complete Worlds under a separate wall-clock
process budget. Stateful generation, shrinking, broad independent
models/checkers, and semantic coverage remain in DS3; campaign and real-boundary
qualification remain in DS4.

Nonzero LocalDispatch retry time crosses the explicit optional provider-clock
contract accepted in the
[LocalDispatch provider-clock decision](../project/decisions/records/2026-08-18T1417Z-local-dispatch-accepts-an-explicit-provider-clock.md).
SQLite remains custody and serialization authority, and the default provider
clock remains SQLite time. DST supplies provider milliseconds only through the
public constructor, without substituting the Engine clock, mutating private
rows, or sleeping.
