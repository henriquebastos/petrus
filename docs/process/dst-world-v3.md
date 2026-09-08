# 1 DST World version 3 compatibility

A World using `Budget` still authors v3 artifacts, with optional seeded
provenance. `BudgetV4` authors v4 and measures profile resources. Read the
complete [World reference](dst-world.md) for both authoring paths.

<a id="compatibility-change"></a>
## 1a Compatibility change


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

<a id="seeded-authorities"></a>
## 1b Seeded authorities

The [seeded-choice contract](dst-world.md#seeded-authorities) pins the exact
`sha256-counter-v1` algorithm, isolated counters, ranges, and golden vectors.

<a id="provenance-and-replay"></a>
## 1c Provenance and replay

The [provenance contract](dst-world.md#provenance-and-replay) defines `origin`
and expanded-operation replay. Replay uses no seed or generator.

<a id="retained-proofs"></a>
## 1d Retained proofs

Each fixture contains the exact profile/checker identities, operations,
expectations, and journal digest. The tests own the executable assertions;
[CV19.DS2](../project/roadmap/cv19-deterministic-simulation-testing/cv19-ds2-deterministic-event-and-fault-harness.md)
records delivery evidence. Earlier prose and run counts remain in Git history.

| Boundary | Retained fixtures |
| --- | --- |
| <a id="seeded-choice-provenance"></a>Seeded choice provenance | [seeded-projection-crash-recovery-world-v3.json](../../tests/dst/fixtures/seeded-projection-crash-recovery-world-v3.json) |
| <a id="pre-commit-terminal-refusal"></a>Pre-commit terminal refusal | [history-refusal-crash-recovery-world-v3.json](../../tests/dst/fixtures/history-refusal-crash-recovery-world-v3.json) |
| <a id="dispatch-acceptance-refusal"></a>Dispatch acceptance refusal | [dispatch-refusal-crash-recovery-world-v3.json](../../tests/dst/fixtures/dispatch-refusal-crash-recovery-world-v3.json) |
| <a id="joined-begin-transaction-commit-refusal"></a>Joined begin-transaction commit refusal | [joined-begin-commit-refusal-world-v3.json](../../tests/dst/fixtures/joined-begin-commit-refusal-world-v3.json) |
| <a id="joined-initial-creation-commit-refusal"></a>Joined initial-creation commit refusal | [joined-creation-commit-refusal-world-v3.json](../../tests/dst/fixtures/joined-creation-commit-refusal-world-v3.json) |
| <a id="joined-initial-creation-acknowledgement-loss"></a>Joined initial-creation acknowledgement loss | [joined-creation-ack-loss-world-v3.json](../../tests/dst/fixtures/joined-creation-ack-loss-world-v3.json) |
| <a id="joined-initial-source-registration-transaction-pair"></a>Joined initial source-registration transaction pair | [joined-source-creation-commit-refusal-world-v3.json](../../tests/dst/fixtures/joined-source-creation-commit-refusal-world-v3.json)<br>[joined-source-creation-ack-loss-world-v3.json](../../tests/dst/fixtures/joined-source-creation-ack-loss-world-v3.json) |
| <a id="joined-dispatch-refusal-before-commit"></a>Joined Dispatch refusal before commit | [joined-dispatch-refusal-world-v3.json](../../tests/dst/fixtures/joined-dispatch-refusal-world-v3.json) |
| <a id="lifecycle-reset-and-late-terminal"></a>Lifecycle reset and late terminal | [lifecycle-reset-late-terminal-world-v3.json](../../tests/dst/fixtures/lifecycle-reset-late-terminal-world-v3.json) |
| <a id="timer-reconstruction"></a>Timer reconstruction | [timer-crash-recovery-world-v3.json](../../tests/dst/fixtures/timer-crash-recovery-world-v3.json) |
| <a id="localdispatch-retry-reconstruction"></a>LocalDispatch retry reconstruction | [retry-crash-exhaustion-world-v3.json](../../tests/dst/fixtures/retry-crash-exhaustion-world-v3.json) |
| <a id="localdispatch-delayed-retry-reconstruction"></a>LocalDispatch delayed-retry reconstruction | [delayed-retry-crash-recovery-world-v3.json](../../tests/dst/fixtures/delayed-retry-crash-recovery-world-v3.json) |
| <a id="lifecycle-cancellation-refusal-reconstruction"></a>Lifecycle cancellation-refusal reconstruction | [lifecycle-cancellation-refusal-world-v3.json](../../tests/dst/fixtures/lifecycle-cancellation-refusal-world-v3.json) |
| <a id="localdispatch-successful-terminal-recollection"></a>LocalDispatch successful-terminal recollection | [local-terminal-redelivery-world-v3.json](../../tests/dst/fixtures/local-terminal-redelivery-world-v3.json) |
| <a id="identified-source-delivery-and-redelivery"></a>Identified source delivery and redelivery | [identified-delivery-redelivery-world-v3.json](../../tests/dst/fixtures/identified-delivery-redelivery-world-v3.json) |
| <a id="delayed-external-terminal-reconstruction"></a>Delayed external terminal reconstruction | [delayed-terminal-recovery-world-v3.json](../../tests/dst/fixtures/delayed-terminal-recovery-world-v3.json) |
| <a id="post-commit-history-acknowledgement-loss"></a>Post-commit History acknowledgement loss | [history-ack-loss-recovery-world-v3.json](../../tests/dst/fixtures/history-ack-loss-recovery-world-v3.json) |
| <a id="joined-identified-delivery-commit-refusal"></a>Joined identified-delivery commit refusal | [joined-delivery-commit-refusal-world-v3.json](../../tests/dst/fixtures/joined-delivery-commit-refusal-world-v3.json) |
| <a id="joined-identified-delivery-acknowledgement-loss"></a>Joined identified-delivery acknowledgement loss | [joined-delivery-ack-loss-world-v3.json](../../tests/dst/fixtures/joined-delivery-ack-loss-world-v3.json) |
| <a id="joined-stale-scope-drop-transaction-pair"></a>Joined stale-scope drop transaction pair | [joined-scoped-drop-commit-refusal-world-v3.json](../../tests/dst/fixtures/joined-scoped-drop-commit-refusal-world-v3.json)<br>[joined-scoped-drop-ack-loss-world-v3.json](../../tests/dst/fixtures/joined-scoped-drop-ack-loss-world-v3.json) |
| <a id="joined-future-scope-quarantine-transaction-pair"></a>Joined future-scope quarantine transaction pair | [joined-scoped-quarantine-commit-refusal-world-v3.json](../../tests/dst/fixtures/joined-scoped-quarantine-commit-refusal-world-v3.json)<br>[joined-scoped-quarantine-ack-loss-world-v3.json](../../tests/dst/fixtures/joined-scoped-quarantine-ack-loss-world-v3.json) |
| <a id="joined-begin-acknowledgement-loss"></a>Joined begin acknowledgement loss | [joined-begin-ack-loss-world-v3.json](../../tests/dst/fixtures/joined-begin-ack-loss-world-v3.json) |
| <a id="joined-terminal-commit-refusal"></a>Joined terminal commit refusal | [joined-terminal-commit-refusal-world-v3.json](../../tests/dst/fixtures/joined-terminal-commit-refusal-world-v3.json) |
| <a id="joined-terminal-acknowledgement-loss"></a>Joined terminal acknowledgement loss | [joined-terminal-ack-loss-world-v3.json](../../tests/dst/fixtures/joined-terminal-ack-loss-world-v3.json) |
| <a id="joined-failed-terminal-commit-refusal"></a>Joined failed-terminal commit refusal | [joined-failure-commit-refusal-world-v3.json](../../tests/dst/fixtures/joined-failure-commit-refusal-world-v3.json) |
| <a id="joined-failed-terminal-acknowledgement-loss"></a>Joined failed-terminal acknowledgement loss | [joined-failure-ack-loss-world-v3.json](../../tests/dst/fixtures/joined-failure-ack-loss-world-v3.json) |
| <a id="joined-failed-firing-projection-transaction-pair"></a>Joined failed-firing projection transaction pair | [joined-failure-projection-commit-refusal-world-v3.json](../../tests/dst/fixtures/joined-failure-projection-commit-refusal-world-v3.json)<br>[joined-failure-projection-ack-loss-world-v3.json](../../tests/dst/fixtures/joined-failure-projection-ack-loss-world-v3.json) |
| <a id="joined-terminal-and-refused-projection-commit"></a>Joined terminal and refused projection commit | [joined-projection-commit-refusal-world-v3.json](../../tests/dst/fixtures/joined-projection-commit-refusal-world-v3.json) |
| <a id="joined-projection-acknowledgement-loss"></a>Joined projection acknowledgement loss | [joined-projection-ack-loss-world-v3.json](../../tests/dst/fixtures/joined-projection-ack-loss-world-v3.json) |
| <a id="joined-handler-registration-projection-transaction-pair"></a>Joined handler-registration projection transaction pair | [joined-registration-projection-commit-refusal-world-v3.json](../../tests/dst/fixtures/joined-registration-projection-commit-refusal-world-v3.json)<br>[joined-registration-projection-ack-loss-world-v3.json](../../tests/dst/fixtures/joined-registration-projection-ack-loss-world-v3.json) |
| <a id="joined-runtime-policy-source-seal-transaction-pair"></a>Joined runtime-policy source seal transaction pair | [joined-seal-commit-refusal-world-v3.json](../../tests/dst/fixtures/joined-seal-commit-refusal-world-v3.json)<br>[joined-seal-ack-loss-world-v3.json](../../tests/dst/fixtures/joined-seal-ack-loss-world-v3.json) |
| <a id="joined-lifecycle-reset-commit-refusal"></a>Joined lifecycle reset commit refusal | [joined-reset-commit-refusal-world-v3.json](../../tests/dst/fixtures/joined-reset-commit-refusal-world-v3.json) |
| <a id="joined-lifecycle-reset-acknowledgement-loss"></a>Joined lifecycle reset acknowledgement loss | [joined-reset-ack-loss-world-v3.json](../../tests/dst/fixtures/joined-reset-ack-loss-world-v3.json) |
| <a id="joined-lifecycle-cancellation-commit-refusal"></a>Joined lifecycle cancellation commit refusal | [joined-cancellation-commit-refusal-world-v3.json](../../tests/dst/fixtures/joined-cancellation-commit-refusal-world-v3.json) |
| <a id="joined-lifecycle-cancellation-acknowledgement-loss"></a>Joined lifecycle cancellation acknowledgement loss | [joined-cancellation-ack-loss-world-v3.json](../../tests/dst/fixtures/joined-cancellation-ack-loss-world-v3.json) |
| <a id="joined-lifecycle-close-transaction-pair"></a>Joined lifecycle close transaction pair | [joined-close-commit-refusal-world-v3.json](../../tests/dst/fixtures/joined-close-commit-refusal-world-v3.json)<br>[joined-close-ack-loss-world-v3.json](../../tests/dst/fixtures/joined-close-ack-loss-world-v3.json) |
| <a id="joined-lifecycle-open-transaction-pair"></a>Joined lifecycle open transaction pair | [joined-open-commit-refusal-world-v3.json](../../tests/dst/fixtures/joined-open-commit-refusal-world-v3.json)<br>[joined-open-ack-loss-world-v3.json](../../tests/dst/fixtures/joined-open-ack-loss-world-v3.json) |

The fixture families make different claims:

1. JSONL and split Dispatch cases distinguish custody refusal, terminal
   commit refusal, and acknowledgement loss after durable acceptance.
   Recovery preserves recorded invocation identity and avoids re-preparation.
2. Joined PostgreSQL/Absurd cases distinguish refused transactions from
   accepted transactions whose acknowledgement is lost. Begin records and
   task spawn commit together; terminal and projection commit separately.
   A refused begin may prepare again because no invocation became durable.
3. Lifecycle cases distinguish canonical open/reset/close from later
   cancellation repair. A refused reset leaves the old Worker authoritative;
   an accepted reset fences its completion. Terminal close opens no successor
   generation. Dropping an Engine does not kill the external Worker.
4. Identified delivery preserves prior acknowledgement across reload.
   Stale-scope drop and future-scope quarantine have separate transaction pairs.
   A poisoned Engine is never read or reused; observations use detached durable
   truth or the last legal snapshot and disclose unavailable live views.
5. The zero-backoff retry fixture makes no delayed-time claim. Delayed retry
   uses the public LocalDispatch provider clock, with SQLite retaining custody.
   Timer reconstruction and delayed external delivery are separate cases.
6. Independent checkers compare authored external/transaction facts with
   detached production observations. Their deliberate-failure tests exercise
   refusal; this inventory does not claim exhaustive adapter fault coverage.

Replay Local/JSONL/SQLite fixtures through `tests.dst.replay_world`, for example:

```sh
uv run --frozen python -m tests.dst.replay_world \
  tests/dst/fixtures/seeded-projection-crash-recovery-world-v3.json
```

Joined fixtures need the Docker PostgreSQL harness. Their replay tests are in
[test_joined_world.py](../../tests/dst/test_joined_world.py). For example:

```sh
uv run --frozen pytest -q \
  tests/dst/test_joined_world.py::test_retained_joined_begin_fixture_replays_without_the_authored_scenario \
  --forbid-skips
```

The shared World and local-profile checks are in
[test_world.py](../../tests/dst/test_world.py). Replaying a retained failure
returns `outcome: "pass"` only when its failure is reproduced exactly.

<a id="compatibility-boundary-and-completed-evolution"></a>
## 1e Compatibility boundary and completed evolution

[CV19](../project/roadmap/cv19-deterministic-simulation-testing/index.md) owns
the completed generator, shrinking, campaign, and qualification work. These
compose the v3 contract. Resource accounting requires v4; wall-clock containment
uses [runner v1](dst-process-runner-v1.md). The accepted
[LocalDispatch provider-clock decision](../project/decisions/records/2026-08-18T1417Z-local-dispatch-accepts-an-explicit-provider-clock.md)
keeps provider time separate from Engine time and preserves SQLite as custody
and serialization authority. Its default clock remains SQLite time.
