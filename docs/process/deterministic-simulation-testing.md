# Deterministic Simulation Testing

**Status:** CV19 correctness contract. The strict internal DS1 artifact and the
supported DS2 executable-World vertical slice are shipped, including exact
budget/checker-failure replay, seeded choice provenance, and a pre-commit
terminal History refusal. A lifecycle-reset race now also proves crash/load,
late-terminal quarantine, exact duplicate acknowledgement, and cancellation
repair after refusal at the durable reset fence. Focused profiles also prove
deterministic Engine timer reconstruction and zero-backoff
LocalDispatch retry reconstruction/exhaustion. A separate provider-clock
profile proves delayed retry refusal immediately before availability and claim
at the exact deadline across process loss. A complementary LocalDispatch
profile proves successful-terminal custody and recollection across process loss;
an identified-ingress profile proves source redelivery and identity conflict
recovery. A delayed external-terminal profile proves volatile queue loss,
external-truth reconstruction, and logical-time delivery. Broader fault
adapters now include paired pre-commit refusal and post-commit acknowledgement
loss plus refusal at the public Dispatch acceptance door after the canonical
Activity request commits. Real Absurd/PostgreSQL profiles additionally prove
paired identified-delivery refusal and acknowledgement loss, joined begin
rollback and acknowledgement loss, paired completed-terminal refusal and
acknowledgement loss, paired failed-terminal refusal and acknowledgement loss,
paired projection refusal and acknowledgement loss, paired canonical reset
refusal and post-commit acknowledgement loss, repair of a refused post-reset
cancellation-tombstone transaction, and idempotent reconstruction after an
accepted tombstone acknowledgement is lost. Initial source-registration
creation is now qualified separately from token-bearing initialization through
paired refusal and acknowledgement-loss profiles. Handler-result registration
close/open effects now have the same paired qualification at the projection
transaction boundary. Runtime-policy `seal` now proves a refused close-all
leaves both armed keys canonical and an accepted-but-unacknowledged close-all
reconstructs an empty delivery door without another seal attempt.
Version 4 adds deterministic profile-retained-data and hidden-pending-work
accounting, while outer runner version 1 adds process-isolated wall-clock
containment with acknowledged-prefix diagnostics. Generation and campaign
qualification remain. DS3's first generated slice now runs broad and focused
identified-delivery Hypothesis state machines directly under `tests/dst`; every
successful expanded World schedule replays from fresh profile, checker, and
Engine objects. Its second generated slice now composes one production public
Engine with JSONL History and LocalDispatch, spanning identified delivery and
redelivery, logical timers, Activity retry/terminal projection, lifecycle
reset and late-terminal fencing, abrupt reload, and paired Dispatch/History
faults. Broad and focused state machines continuously exercise all eight
applicable safety families and replay current-v4 artifacts from fresh objects.
DS3 now separately qualifies fair quiescence, external prerequisites,
inadequate fair declarations, bounded exhaustion, quarantine, and
safety-preserving livelock. A test-only rescheduling mutation produces an exact
v4 budget-failure artifact which Hypothesis reduces and replay reproduces; the
same unmutated expanded schedule is retained as a green regression. A versioned
semantic-coverage report records reached, broad-only, unreachable, and
intentionally ungenerated dimensions. DS4 now exposes the ordinary generated
profiles and a larger seed-addressed campaign through pytest, with a bounded
payload-free report. Failure promotion and production-boundary qualification
remain.

This document owns Petrus's deterministic simulation testing (DST) contract.
DST drives the production `Engine`, `Coordinator`, `Instance`, `HistoryStore`,
and `Dispatch` doors under a bounded, serializable schedule and checks their
recorded semantics after every accepted event. It is not a second engine, an
application runtime, or a provider emulator.

The first internal implementation profile is named `engine-coordinator-v1`.
The strict scenario and replay artifact which pin that profile are specified by
[`dst-scenario-v1`](dst-scenario-v1.md) and tracked by
[CV19.DS1.TS2](../project/roadmap/cv19-deterministic-simulation-testing/cv19-ds1-ts2-strict-scenario-replay-contract.md).
The separately accepted supported kernel and its current artifact are specified
by [`dst-world-v4`](dst-world-v4.md); versions 1 through 3 remain supported for
strict decode and replay under [`dst-world-v1`](dst-world-v1.md),
[`dst-world-v2`](dst-world-v2.md), and [`dst-world-v3`](dst-world-v3.md). This
document remains the authority for the cross-profile correctness properties,
cuts, bounds, and evidence limits. Nondeterministic wall-clock containment is
specified separately by [`dst-process-runner-v1`](dst-process-runner-v1.md).

## Driver route for correctness-sensitive work

Use this route only when a change is durable, concurrent, stateful, or
externally effectful. Ordinary work gains no additional artifact or lifecycle.
Before implementing a non-trivial qualifying change, put this compact
correctness sketch in the work's existing plan or owning roadmap artifact:

1. **Authoritative state** — name the durable or live owner and what can be
   reconstructed.
2. **Safety invariants** — state what must never become observable.
3. **Liveness assumptions** — name the fair environment under which progress
   is required and the external waits that suspend the claim.
4. **Bounds and overflow** — bound work, queues, retries, payloads, time, and
   retained state that the change can grow; name each exhaustion,
   backpressure, refusal, or quarantine behavior.
5. **Nondeterministic inputs** — list time, identities, scheduling, delivery,
   storage outcomes, provider outcomes, and randomness; identify the owned
   seam or explicit exclusion for each.
6. **Consequential crash cuts** — name the before/after durable boundaries
   where interruption could change authority, duplication, loss, or recovery.
7. **Independent judgment** — name the checker or exact model that can judge
   recorded behavior independently of the implementation, or state why one is
   impractical and what weaker evidence substitutes for it.

The sketch scales to risk and reuses the story's existing surfaces; do not
create a correctness document merely to copy this list. If the work changes
the shared DST profile, update this owner and the strict artifact contract
together.

For a replayable defect, reproduce before fixing: run the exact retained
scenario or smallest existing crash/property node, preserve its expanded
schedule and failing observation, then change the production owner rather than
special-casing the fixture. After the fix, replay from fresh runtime objects,
run the focused real-boundary nodes whose claims matter, and compare the same
property and durable facts.

Promote a counterexample to `tests/dst/fixtures/` only after minimizing it
without removing the failing property or consequential cut. Retain strict
profile/version, commit/runtime/dependency provenance, original seed, shrink
lineage, expanded schedule, bounds, and exact expectations; pair it with an
ordinary deterministic replay test. The expanded artifact is replay authority.
When the active strict format does not carry all discovery lineage, preserve
the missing commit, dependency, property, and before/after shrink metadata in
the story's tracked promotion/worklog record rather than widening the format
silently. Generated shrinking is now qualified by DS3, and promoting an
internal artifact does not change the public `implementation-free-v1`
contract.

Production correctness must never depend on Python `assert`, which optimized
Python may remove. Use explicit validation, refusal, or failure paths for
runtime obligations. Test assertions and Hypothesis invariants remain the
appropriate way to state executable test expectations.

## Evidence language

- **[E] executable evidence** — the cited test or probe has exercised the
  behavior.
- **[D] decision** — an accepted project decision constrains the behavior.
- **[I] inference** — a conclusion from cited evidence, with the inference
  named rather than presented as observation.

The inventory checked the cited decision corpus and executable evidence on
2026-08-17. A unit or property test is evidence for its tested contract, not
proof that all schedules are correct. DST adds bounded schedule exploration;
it does not promote bounded evidence into a universal proof.

## Ownership and compatibility boundaries

The harness owns only schedule control, scripted collaborator outcomes,
fault placement, artifact production, and independent checks over observable
production facts. Production components retain their existing ownership:

| Concern | Owner | DST rule |
| --- | --- | --- |
| Net enablement, binding, firing, marking, status, and history replay | Impetus `Instance` | Call production doors; never compute substitute semantics. |
| Ingress, activity orchestration, commit ordering, lifecycle repair, and reconstruction | `Engine` / `Coordinator` | Drive existing public or owned test seams; observe their results and History. |
| Retry and custody mechanics | Motus `Dispatch` and Worker | Script outcomes through the `Dispatch` contract in the simulated profile; qualify real adapters separately. |
| External activity effects and application fault worlds | Activity/provider/application | Do not execute or emulate them generically; model only their reported protocol outcome. |
| Durable truth | the configured `HistoryStore` | Fault its existing append/transaction boundary; never maintain a harness-owned semantic log. |
| Correctness claims | independent DST checkers | Derive from portable scenario inputs, History records, snapshots, and dispositions; do not inspect private mutable state to decide pass/fail. |

The existing hosted simulation profile and result contract remain unchanged:

- [`implementation-free-v1`](../../spec/simulation-result-v1.md) is the public,
  bounded, no-handler/no-Dispatch projection implemented by
  [`petrus.simulation`](../../src/petrus/simulation.py).
- `engine-coordinator-v1` is an internal DST scenario/replay profile. It may
  exercise handlers and a scripted `Dispatch`, but it does not add fields,
  interpretations, or capabilities to `implementation-free-v1`.
- `petrus.testing.dst/v4` is the current supported cross-project **test-kit**
  API with a distinct `petrus-dst-world` artifact. Its compatibility contract
  is [`dst-world-v4`](dst-world-v4.md); strict version 1 through 3 decode/replay
  remain supported by [`dst-world-v1`](dst-world-v1.md),
  [`dst-world-v2`](dst-world-v2.md), and [`dst-world-v3`](dst-world-v3.md). None
  is a hosted-simulation product API or re-exported from the Petrus package
  root.
- A supported test-kit API is not implied by an internal replay fixture. Every
  future profile still requires an exact identity/digest, and any new supported
  surface requires its own compatibility decision.

This keeps [the hosted profile's strict owner fixture](../../tests/petrus/engine/test_simulation.py)
and `petrus-simulation-result` version 1 byte-compatible [E].

## Evidence types stay distinct

| Evidence type | What it establishes | What it does not establish |
| --- | --- | --- |
| Hand-authored example/unit test | A named input follows an expected path. | Coverage of unenumerated schedules. |
| Existing property test | A generated invariant holds over the generated domain. | Crash/fault interleavings outside that domain. |
| Hosted `implementation-free-v1` simulation | A bounded, implementation-free net reaches an exact portable result. | Engine/Coordinator/Dispatch recovery correctness. |
| DST scenario replay | The production runtime obeys the checkers under one exact bounded schedule and fault script. | Correctness outside its profile and bounds. |
| Generated DST campaign | Many seed-addressed schedules satisfy the profile's checkers and replay exactly. | Real transport/provider conformance or a mathematical proof. |
| Real-adapter qualification | A named History/Dispatch/transport combination obeys its contract under real timing and failure controls. | Every implementation of the abstract contract. |

## Current generated safety campaign

[`generated_runtime_world.py`](../../tests/dst/generated_runtime_world.py) is
the first one-run cross-layer DS3 profile. It is intentionally test-owned and
contains one opaque production `Engine`; it does not compose multiple Worlds
or expose Coordinator, Instance, History, or Dispatch handles to generators or
checkers. Its imperative scenario, broad state machine, focused state machine,
and artifact replay all submit the same normalized commands to one supported
World interpreter.

The profile's closed commands are scope open/reset, identified source deliver,
Engine drive, and Worker claim/fail/complete. Its qualified faults refuse
Dispatch custody after the canonical `ActivityRequested` prefix and refuse a
work projection History batch after `ActivityCompleted` freezes. Abrupt drop
revokes the generation and fresh `Engine.load` either republishes the stable
request or projects the frozen terminal without Worker re-execution.

Every atomic action and fresh load runs a detached checker over:

- live marking/watermark versus canonical History replay;
- a small independent occurrence/terminal/reset fold versus live in-flight and
  lifecycle state;
- dense correlated occurrences and unique firing terminal families;
- request, Dispatch, and Worker invocation identity plus one preparation;
- stateful proof that execution counts cannot increase after terminal freeze;
- authored delivery identity and exact-redelivery acknowledgement authority;
- lifecycle reset, cancellation, and late-terminal quarantine;
- refused projection versus accepted firing completion; and
- retry/timer/History/external-fact bounds.

Current v4 budgets cap 96 World actions, 8 queued commands, one advance to
logical instant 5, 4 reloads, 24 predicate polls, a 512 KiB artifact, one live
Worker claim, 2 pending Dispatch tasks, 2 in-flight occurrences, 32 logical
Dispatch facts, 64 modeled external facts, 128 History records, 64 KiB of
History bytes, 8 marking tokens, and 8 KiB of detached marking data. Focused
generation runs 10 examples with 4 post-spine steps; broad generation runs 16
examples with 5 steps and fewer global ordering constraints. Every successful
example finishes explicitly and replays its expanded operations,
checker/resource samples, disposition, and journal digest from fresh Engine,
History, Dispatch, profile, and checker objects.

This is bounded safety evidence, not the fair-liveness or shrink/promotion
claim. Those remain owned by CV19.DS3.TS3. Real Absurd/PostgreSQL transactional
cuts remain separately qualified DS2 evidence and a DS4 campaign boundary.

## Ordinary and scheduled campaign tiers

Generated DST remains a self-contained pytest world under `tests/dst`; there
is no second runner semantics or separate scripts-owned test tree. The
ordinary gate is:

```sh
uv run pytest -q tests/dst --forbid-skips
```

That complete corpus includes retained replay, failure, process-containment,
and real joined PostgreSQL/Absurd profiles, so it uses the repository's pinned
Docker PostgreSQL harness. The four generated state-machine tests themselves
are credential-free Local/JSONL/SQLite tests and run on every normal full and
release gate.

The larger credential-free operation is:

```sh
uv run python -m tests.dst.campaign \
  --tier scheduled \
  --campaign-id "$(date -u +%G-W%V)" \
  --report /tmp/petrus-dst-campaign.json
```

Run it weekly against current main, before release qualification, or on demand
for a generated profile change. The explicit campaign id derives one isolated
32-bit Hypothesis seed per profile with SHA-256. The report retains each seed,
so a profile can be rerun with the same campaign id; expanded World artifacts,
not those seeds, remain execution/replay authority. Hypothesis's example
database is disabled. Every case enters the existing World interpreter, runs
the profile's independent checker cadence, finishes explicitly, and replays
from fresh profile/checker/runtime objects before contributing a report row.

| Profile family | Ordinary target / steps | Scheduled target / steps |
| --- | ---: | ---: |
| identified delivery, broad | 30 / 8 | 120 / 10 |
| identified delivery, focused | 20 / 6 | 80 / 8 |
| cross-layer runtime, broad | 16 / 5 | 64 / 7 |
| cross-layer runtime, focused | 10 / 4 | 40 / 6 |

`max_examples` is a Hypothesis accepted-example target, not an absolute count
of machine constructions: rejected candidates and shrink work may construct
additional cases. The operation therefore requires at least the target and
caps recorded case summaries at ten times it. It also caps each payload-free
summary at 16 KiB, the final report at 1 MiB, artifacts at their exact World
budget (and the 4 MiB format ceiling), selected profile execution at 120
seconds, the four-profile operation at 510 seconds, and concurrency at one.
Profile resource ceilings remain exact in each artifact and are copied into
the report; scenario payloads, results, external facts, and provider data are
not.

The report states selected and deselected profiles, exact repository/runtime
identity, elapsed time, actual case count, maximum artifact size, commands,
fault cuts, crash cuts, checker triggers, operation and action dispositions,
and explicit unmodeled boundaries. A timeout, nonzero pytest result, too few
cases, case-log/report overage, unknown selection, or duplicate selection is a
visible failure; no partial run is labeled pass. Campaign process timeout is
harness containment, never a deterministic liveness disposition.

On the 2026-W34 reference orb, the complete scheduled tier targeted 304
accepted examples, recorded 452 generated/shrink cases, and completed serially
in 34.8 seconds. The largest artifact was 288,032 bytes and the report was
8,039 bytes; observed command maximum resident set was about 105 MiB. These
measurements are a capacity sketch for this commit and environment, not a
performance guarantee or substitute for the enforced semantic/resource
bounds.

## Runtime nondeterminism inventory

`engine-coordinator-v1` is single-writer and step-driven. “Controlled” means
the scenario or a profile-pinned deterministic production policy supplies the
choice; “recorded” means durable History freezes it before replay can depend
on it. “External” means the generic harness substitutes only at an existing
contract seam and a real profile owns qualification. “Blocker” means DS2 must
not proceed until an owned seam exists.

| Source | Classification in `engine-coordinator-v1` | Control or evidence |
| --- | --- | --- |
| Instance identity | Controlled | The harness supplies a strict scenario-derived `instance_id`; it never invokes the default UUID7 minting in [`Instance`](../../src/petrus/impetus/instance/__init__.py). Reconstruction takes identity from `InstanceCreated` [E: `TestResumeDerivesIdentity` in [`test_instance_identity.py`](../../tests/petrus/impetus/instance/test_instance_identity.py)]. |
| Occurrence, accepted-ingress, and event identity | Recorded and deterministic | Writer counters and durable positions derive identities; stores use `<instance>:<position>` and Instance reserves `occurrence-<id>` [E: [`test_instance_replay_properties.py`](../../tests/petrus/impetus/instance/test_instance_replay_properties.py), [`test_history_backends.py`](../../tests/petrus/impetus/history_store/test_history_backends.py)]. |
| Logical time and timer sensing | Controlled | The harness advances the injected `SimulatedClock`; `Engine` senses through its injected `Sensor` and records `TimerMatured` [D: [time projection decision](../project/decisions/records/2026-07-08T1113Z-time-projection-virtual-clock-watermark.md); E: [`test_timers.py`](../../tests/petrus/impetus/instance/test_timers.py)]. |
| Candidate enumeration and built-in selection | Deterministic production behavior | Candidate order and the shipped selectors are deterministic for one recorded state. A scenario pins the selector; a custom random selector is an application profile and must expose or record its choice before admission [E: [`test_selection.py`](../../tests/petrus/impetus/selection/test_selection.py)]. |
| Drive ordering and action limit | Controlled | Each explicit `drive` step supplies its bounded action budget and calls production `Engine.run_once()` / `Coordinator.advance()`; no background loop races the schedule [E: [`test_engine.py`](../../tests/petrus/engine/test_engine.py)]. |
| Source delivery ordering, identity, and redelivery | Controlled then recorded | Scenario steps choose arrival order and stable source identity; accepted identity and payload enter unified History before acknowledgement. Real Absurd/PostgreSQL profiles prove both rollback before acceptance and exact redelivery after accepted acknowledgement loss [D: [source delivery decision](../project/decisions/records/2026-07-14T1806Z-source-delivery-projection-and-identity.md); E: retained [`joined-delivery-commit-refusal-world-v3.json`](../../tests/dst/fixtures/joined-delivery-commit-refusal-world-v3.json) and [`joined-delivery-ack-loss-world-v3.json`](../../tests/dst/fixtures/joined-delivery-ack-loss-world-v3.json), plus `TestDeliveryIdentity` in [`test_ingress.py`](../../tests/petrus/impetus/instance/test_ingress.py)]. |
| Activity invocation preparation and projection | Production behavior under an application profile | The harness calls registered `ActivityHandler.prepare` / `project`; the contract requires deterministic projection. Hidden wall-clock/random reads in application code make that application profile ineligible until controlled; DST does not monkeypatch them [D: [activity seam decision](../project/decisions/records/2026-07-14T2016Z-activity-invocation-runtime-seam.md); E: [`test_activity_seam.py`](../../tests/integration/test_activity_seam.py)]. |
| Activity execution, retry, heartbeat, timeout, and custody | External through `Dispatch` | A scripted `Dispatch` presents protocol outcomes at scenario instants while production Coordinator retains request/result/projection semantics. Retained refusal stories prove accepted History outruns refused dispatch/cancellation custody, and fresh load republishes the same invocation or cancellation instruction without `prepare`. Separately identified real-provider profiles qualify commit refusal, task-spawn failure, and post-reset cancellation repair in the stronger Absurd/PostgreSQL transaction shapes; other Local, Absurd, Worker, and ZeroMQ mechanics remain Motus-owned and require their own real-adapter qualification [E: [`test_dispatch_refusal_world.py`](../../tests/dst/test_dispatch_refusal_world.py), [`test_lifecycle_cancellation_world.py`](../../tests/dst/test_lifecycle_cancellation_world.py), [`test_joined_world.py`](../../tests/dst/test_joined_world.py), [`test_local_dispatch.py`](../../tests/petrus/motus/dispatch/test_local_dispatch.py), [`test_zeromq_dispatch_transport.py`](../../tests/petrus/motus/transport/test_zeromq_dispatch_transport.py)]. |
| History append and transaction outcome | Controlled fault at an owned seam | The scenario can refuse or crash around `HistoryStore.append`/`extend` and joined Engine transactions. The production store decides what committed; reload is the oracle for durable truth. The retained joined profiles wrap only the public provider connection's token-bearing or source-registration initial creation, later semantic commit acknowledgement, task-spawn call, identified-delivery commit, or post-reset cancellation commit/acknowledgement, then use independent PostgreSQL reads to prove the accepted or rolled-back History and Dispatch custody [E: [`test_joined_creation_world.py`](../../tests/dst/test_joined_creation_world.py), [`test_joined_world.py`](../../tests/dst/test_joined_world.py), [`test_history_backends.py`](../../tests/petrus/impetus/history_store/test_history_backends.py), [`test_engine.py`](../../tests/petrus/engine/test_engine.py)]. |
| Process crash and restart | Controlled | A crash discards all live Engine, Coordinator, Instance, and collaborator objects. Restart constructs fresh objects from scenario configuration and the retained History/Dispatch facts, then calls production load/reconcile doors [E: `test_an_outstanding_invocation_is_redispatched_never_re_prepared` and `test_a_projection_pending_occurrence_completes_by_projection_alone` in [`test_coordinator.py`](../../tests/petrus/engine/test_coordinator.py)]. |
| Scope close/reset and late outcomes | Controlled then recorded | Scenario steps request lifecycle operations; History records the semantic fence and quarantine/repair facts [E: [`test_engine.py`](../../tests/petrus/engine/test_engine.py), [`test_lifecycle_scopes.py`](../../tests/petrus/impetus/instance/test_lifecycle_scopes.py)]. |
| `Engine.wait()` host sleep | External and forbidden | The profile never takes the no-resource-waiter `time.sleep` fallback. Time advances only through `advance_time`; real wait behavior belongs to integration qualification [I from [`Engine.wait`](../../src/petrus/engine/__init__.py)]. |
| Backend lock waits, SQLite bootstrap sleeps, telemetry clocks, asyncio scheduling, UUID4 transport ids, network delay | External | These affect real adapters and telemetry, not accepted semantic choices in the simulated profile. They are not patched or claimed as simulated [I from [`sqlite.py`](../../src/petrus/impetus/history_store/sqlite.py), [`zeromq.py`](../../src/petrus/motus/transport/zeromq.py), and [`telemetry.py`](../../src/petrus/telemetry.py)]. |
| OS, process, and execution-provider behavior, including Gondolin | External | The generic simulator reports scripted provider outcomes only. Provider-specific fault worlds and irreversible side effects require provider-owned qualification [D: [Dispatch leases and provider ownership](../project/decisions/records/2026-07-22T1816Z-dispatch-leases-attempts-devops-operates-workers.md); E: [`test_gondolin_environment.py`](../../tests/petrus/motus/test_gondolin_environment.py)]. |

**Inventory result:** no semantic nondeterminism blocker exists for DS2 when it
uses a supplied instance id, injected logical clock, built-in deterministic
policies, scripted ingress/Dispatch/store outcomes, and explicit drive steps.
If DS2 discovers a semantic choice that bypasses those doors or is neither
controlled nor durably recorded, that discovery is a blocker: add an owned
production seam or narrow the profile; do not hide it with a harness-side
reimplementation.

## Durable and irreversible cuts

The schedule can stop, fault, crash, or resume only at the named cuts below.
“After commit” means the configured durable store has accepted the complete
semantic batch, not merely that Python constructed a record. The harness must
not invent finer cuts inside a production atomic batch.

| Cut id | Production boundary and required fact | Recovery obligation | Evidence |
| --- | --- | --- | --- |
| `instance_created` | `InstanceCreated` and the net's initial durable state—initial marking or source-delivery registration—are accepted as one creation boundary. | A refused transaction leaves no canonical instance, marking, or registration; an accepted-but-unacknowledged creation loads the exact identity and initial state without recreating. | [E: retained [`joined-creation-commit-refusal-world-v3.json`](../../tests/dst/fixtures/joined-creation-commit-refusal-world-v3.json), [`joined-creation-ack-loss-world-v3.json`](../../tests/dst/fixtures/joined-creation-ack-loss-world-v3.json), [`joined-source-creation-commit-refusal-world-v3.json`](../../tests/dst/fixtures/joined-source-creation-commit-refusal-world-v3.json), and [`joined-source-creation-ack-loss-world-v3.json`](../../tests/dst/fixtures/joined-source-creation-ack-loss-world-v3.json), plus [`test_instance_identity.py`](../../tests/petrus/impetus/instance/test_instance_identity.py) and [`test_instance_replay_properties.py`](../../tests/petrus/impetus/instance/test_instance_replay_properties.py)] |
| `delivery_accepted` | Source acceptance and the selected delivery/projection facts, or one terminal scoped disposition, are committed before acknowledgement. | Same identity/payload/target is idempotent; different content conflicts; uncommitted delivery or disposition is not acknowledged. | [D: source delivery decision; E: retained [`joined-delivery-commit-refusal-world-v3.json`](../../tests/dst/fixtures/joined-delivery-commit-refusal-world-v3.json), [`joined-delivery-ack-loss-world-v3.json`](../../tests/dst/fixtures/joined-delivery-ack-loss-world-v3.json), [`joined-scoped-drop-commit-refusal-world-v3.json`](../../tests/dst/fixtures/joined-scoped-drop-commit-refusal-world-v3.json), [`joined-scoped-drop-ack-loss-world-v3.json`](../../tests/dst/fixtures/joined-scoped-drop-ack-loss-world-v3.json), [`joined-scoped-quarantine-commit-refusal-world-v3.json`](../../tests/dst/fixtures/joined-scoped-quarantine-commit-refusal-world-v3.json), and [`joined-scoped-quarantine-ack-loss-world-v3.json`](../../tests/dst/fixtures/joined-scoped-quarantine-ack-loss-world-v3.json), plus `TestDeliveryIdentity` in [`test_ingress.py`](../../tests/petrus/impetus/instance/test_ingress.py)] |
| `activity_requested` | The firing prefix and `ActivityRequested` become durable as one accepted boundary. Backend-owned/split Dispatch compositions commit that prefix before `Dispatch.dispatch`; the Absurd provider instead joins the prefix and task spawn in one transaction. Invocation id, input, and policy are frozen only after that boundary accepts. | A split composition reload may redispatch the identical invocation without recomputing it. A refused joined commit or task spawn reloads the prior marking with no installed selection or task, then may prepare and begin the work anew. | [E: retained [`dispatch-refusal-crash-recovery-world-v3.json`](../../tests/dst/fixtures/dispatch-refusal-crash-recovery-world-v3.json), [`joined-begin-commit-refusal-world-v3.json`](../../tests/dst/fixtures/joined-begin-commit-refusal-world-v3.json), and [`joined-dispatch-refusal-world-v3.json`](../../tests/dst/fixtures/joined-dispatch-refusal-world-v3.json), `test_selection_installs_only_after_the_begin_commit_returns` in [`test_engine.py`](../../tests/petrus/engine/test_engine.py), and `test_an_outstanding_invocation_is_redispatched_never_re_prepared` in [`test_coordinator.py`](../../tests/petrus/engine/test_coordinator.py)] |
| `external_effect` | The provider may have performed an irreversible effect after accepting an invocation, whether or not Petrus observed the result. | Redelivery is at-least-once; stable invocation id is the idempotency key. DST scripts the ambiguity but cannot prove application idempotence. | [D: activity seam decision; E: `test_backend_owned_dispatch_failure_installs_the_already_durable_begin` in [`test_coordinator.py`](../../tests/petrus/engine/test_coordinator.py)] |
| `activity_terminal_frozen` | `ActivityCompleted` or `ActivityFailed` is committed before result projection mutates the marking. Exactly one terminal family member may exist per occurrence; a refused terminal transaction accepts no canonical fact even when provider custody is already terminal. | Reload recollects a durable provider terminal after refusal or performs projection-only recovery after terminal acceptance; redelivery of the same terminal is idempotent and a conflicting terminal refuses loud. | [E: retained [`joined-terminal-commit-refusal-world-v3.json`](../../tests/dst/fixtures/joined-terminal-commit-refusal-world-v3.json), [`joined-failure-commit-refusal-world-v3.json`](../../tests/dst/fixtures/joined-failure-commit-refusal-world-v3.json), and [`joined-failure-ack-loss-world-v3.json`](../../tests/dst/fixtures/joined-failure-ack-loss-world-v3.json), `test_terminal_result_freezes_before_projection_failure_and_fresh_load_retries_projection_only` in [`test_engine.py`](../../tests/petrus/engine/test_engine.py), and kill-window tests in [`test_history_backends.py`](../../tests/petrus/impetus/history_store/test_history_backends.py)] |
| `projection_committed` | Token movement, handler-authored delivery-registration closes/opens, and the firing terminal complete the occurrence in one semantic batch; acceptance may precede loss of the commit acknowledgement. | Reload reproduces marking, armed registrations, status, occurrence indexes, and accepted identity without rerunning the handler or projecting again. | [E: retained [`joined-projection-ack-loss-world-v3.json`](../../tests/dst/fixtures/joined-projection-ack-loss-world-v3.json), [`joined-registration-projection-commit-refusal-world-v3.json`](../../tests/dst/fixtures/joined-registration-projection-commit-refusal-world-v3.json), and [`joined-registration-projection-ack-loss-world-v3.json`](../../tests/dst/fixtures/joined-registration-projection-ack-loss-world-v3.json), plus [`test_instance_replay_properties.py`](../../tests/petrus/impetus/instance/test_instance_replay_properties.py)] |
| `source_sealed` | Runtime policy closes every currently armed registration of one source in one key-ordered semantic batch; acceptance may precede loss of the commit acknowledgement. | Refusal leaves every key armed after reload and permits one explicit host retry. Accepted acknowledgement loss reloads the empty delivery door and terminal status without another seal attempt. | [E: retained [`joined-seal-commit-refusal-world-v3.json`](../../tests/dst/fixtures/joined-seal-commit-refusal-world-v3.json) and [`joined-seal-ack-loss-world-v3.json`](../../tests/dst/fixtures/joined-seal-ack-loss-world-v3.json), plus `test_seal_closes_every_armed_registration` in [`test_registrations.py`](../../tests/petrus/impetus/instance/test_registrations.py)] |
| `semantic_batch_refused` | Encode/append/commit refusal leaves no accepted semantic batch. A joined transaction rollback poisons the live Engine until reload. | Discard live state and rebuild from durable History; memory must not outrun durability. | [E: transaction and poisoned-engine tests in [`test_engine.py`](../../tests/petrus/engine/test_engine.py); refusal tests in [`test_history_backends.py`](../../tests/petrus/impetus/history_store/test_history_backends.py)] |
| `scope_fenced` | Close/reset semantic facts commit before best-effort Dispatch cancellation. The reset or cancellation-tombstone transaction may itself commit before its acknowledgement is lost. | A refused reset creates no fence: reload retains the old generation and Worker authority. After an accepted fence, reload/reconcile repairs an absent tombstone or recognizes an accepted one idempotently; late terminal delivery is quarantined or provider-fenced rather than projected across the fence. | [E: retained [`joined-reset-commit-refusal-world-v3.json`](../../tests/dst/fixtures/joined-reset-commit-refusal-world-v3.json), [`joined-reset-ack-loss-world-v3.json`](../../tests/dst/fixtures/joined-reset-ack-loss-world-v3.json), [`lifecycle-cancellation-refusal-world-v3.json`](../../tests/dst/fixtures/lifecycle-cancellation-refusal-world-v3.json), [`joined-cancellation-commit-refusal-world-v3.json`](../../tests/dst/fixtures/joined-cancellation-commit-refusal-world-v3.json), and [`joined-cancellation-ack-loss-world-v3.json`](../../tests/dst/fixtures/joined-cancellation-ack-loss-world-v3.json), `test_close_commits_before_retiring_pending_dispatch_and_late_terminal_is_quarantined`, and `test_restart_repairs_a_committed_cancellation_instruction_idempotently` in [`test_engine.py`](../../tests/petrus/engine/test_engine.py)] |
| `terminal_acknowledged` | Dispatch/provider custody is acknowledged only after Petrus accepts the terminal fact or durable quarantine disposition. | Crash before acknowledgement permits redelivery; repeated delivery cannot produce a second terminal or projection. | [E: redelivery tests in [`test_coordinator.py`](../../tests/petrus/engine/test_coordinator.py) and [`test_local_dispatch.py`](../../tests/petrus/motus/dispatch/test_local_dispatch.py)] |

Backend posture remains explicit. SQLite and PostgreSQL provide transactional
whole-batch commits. JSONL makes a complete-line prefix observable after an OS
failure and replay refuses a torn semantic batch loud; DST must report this as
a backend failure, not silently “repair” it into a valid schedule [E:
`test_a_torn_tail_fails_loud_naming_the_line` in
[`test_persistence.py`](../../tests/petrus/impetus/history_store/test_persistence.py)].

## Executable correctness properties

Every accepted event runs all applicable safety checkers immediately and once
again after a fresh reload. A checker consumes only strict artifact values and
observable production results. DS3 may optimize execution, but may not weaken
these property meanings.

| Id | Safety property | Executable checker |
| --- | --- | --- |
| `S1-replay-agreement` | Durable History is the semantic source of truth. | Reload a fresh Engine from the retained store; compare canonical snapshot, status, watermark, occurrence indexes, accepted identities, in-flight invocations, and next counters with the pre-crash observable state at the same durable frontier. |
| `S2-history-validity` | History is dense, strictly decodable, causally legal, and contains at most one firing terminal and one activity terminal per occurrence. | Strictly encode/decode every record; verify positions/ids, record prerequisites, batch boundaries, unique terminal families, and monotone occurrence/time/watermark facts. |
| `S3-stable-invocation` | An activity occurrence has one frozen invocation across dispatch refusal, crash, retry, and reconstruction. | Group dispatch observations and `ActivityRequested` by occurrence; require byte-equivalent activity/input/policy and one stable invocation id. |
| `S4-terminal-before-projection` | A terminal result is durable before its projection and projects at most once. | For each projected activity, find exactly one preceding durable `ActivityCompleted`/`ActivityFailed`; compare projected marking delta after reload and reject any second completion/projection family. |
| `S5-delivery-identity` | Source identity is accepted exactly once with one payload and acknowledged only after a durable accepted/quarantined disposition. | Group deliveries by source identity; require equal redeliveries to preserve one accepted occurrence, unequal payloads to refuse, and each acknowledgement to point at an existing durable disposition. |
| `S6-lifecycle-isolation` | A close/reset fence prevents pre-fence or late work from mutating the post-fence marking. | Partition occurrences at lifecycle records; require pending work to be cancelled/repaired, late terminals to be quarantined, and post-reset state to derive only from the reset baseline and later facts. |
| `S7-commit-authority` | A refused or rolled-back semantic batch changes neither durable state nor the accepted replay state. | Snapshot the durable frontier before injection, force refusal, discard live objects, reload, and require equality with that frontier; a poisoned live Engine must reject further use. |
| `S8-profile-bounds` | No action, event, payload, retained state, or artifact silently exceeds the pinned profile. | Count and size inputs and outputs before admission and after every step; exceeding a ceiling produces the exact `bounded_exhaustion` disposition, never truncation or an unbounded loop. |

### Liveness under a fair environment

Liveness applies only to the replay suffix explicitly marked `fair`. The
suffix is fair when all of these strict facts hold:

1. no further injected History or Dispatch refusal remains;
2. logical time may advance to every finite declared timer, retry, lease, or
   timeout instant without exceeding the profile ceiling;
3. the retained History remains readable and writable;
4. Dispatch accepts every pending request/cancellation and eventually reports
   each scripted terminal outcome; and
5. no application-owned event, human decision, or real external effect is a
   prerequisite for the eligible runtime work.

`L1-fair-convergence` repeatedly performs the profile's canonical fair step —
reconcile, deliver ready scripted collaborator outcomes, sense the current
logical instant, and drive one production action — until one of these exact
dispositions occurs:

| Disposition | Meaning | Liveness judgment |
| --- | --- | --- |
| `quiescent` | No enabled runtime-owned action, due timer, pending repair, or ready scripted outcome remains. | Pass. |
| `terminal` | The production Instance reports its recorded terminal status. | Pass. |
| `quarantined` | All remaining late/ambiguous outcomes have a durable quarantine disposition and no eligible work remains. | Pass, with quarantine evidence retained. |
| `bounded_exhaustion` | A declared ceiling prevents another canonical step. | Bounded result, not a liveness pass or failure. |
| `external_wait` | A named application/human/external prerequisite remains. | Outside the fair suffix; classified evidence, not a liveness pass or failure. |
| `stalled` | Eligible work remains but a canonical fair step changes neither durable state nor controlled collaborator state. | Liveness failure. |

The checker emits the first stalled observable state and eligible work set.
Wall-clock waiting is never evidence of progress.

## Event vocabulary

The scenario's closed event vocabulary must map to existing production doors.
An event is applied once at its schedule position; redelivery is a repeated
event with the same protocol identity, not a hidden loop.

| Event kind | Production door | Required strict operands | Relevant dispositions |
| --- | --- | --- | --- |
| `deliver` | `Engine.deliver` | source path, payload, optional stable source identity | accepted, idempotent, refused, acknowledged |
| `drive` | `Engine.run_once` / `Coordinator.advance` | positive action budget at most the profile ceiling | progressed, quiescent, terminal, bounded exhaustion |
| `advance_time` | injected `SimulatedClock` then Engine sensing | non-negative target instant, monotone from current time | advanced, refused, bounded exhaustion |
| `dispatch_terminal` | make a strict scripted outcome ready for production `Dispatch.collect` | invocation id plus strict completion or failure payload | accepted, idempotent, conflicting, quarantined |
| `close_scope` | Coordinator lifecycle door | strict scope path | closed, already closed, refused |
| `reset_scope` | Coordinator lifecycle door | strict scope path and reset input required by production | reset, refused |
| `crash` | harness process boundary | named cut id | crashed |
| `restart` | `Engine.load` and reconciliation | retained store/collaborator labels; no live object reference | loaded, refused, quarantined |
| `begin_fair` | harness liveness checker | empty operands | fair or refused with unmet condition names |

Creation is scenario initialization, not a repeatable event. Worker execution,
heartbeat, network packet, filesystem, process, and Gondolin events are absent:
the scripted Dispatch reports their contract-level consequence. A new event
kind changes the closed scenario contract and requires a version/profile
decision.

## Fault taxonomy and injection cuts

Faults are finite scenario values. Each occurrence identifies one fault kind,
one named cut, and one remaining application count. Exhausting the count
disables it. An unbounded/permanent failure is inadmissible in a fair suffix.

| Fault kind | Allowed cuts | Observable effect |
| --- | --- | --- |
| `history_refuse` | immediately before `instance_created`, `delivery_accepted`, `activity_requested`, `activity_terminal_frozen`, `projection_committed`, or `scope_fenced` append/extend | Configured store raises without accepting the semantic batch. |
| `history_commit_refuse` | joined transaction commit after production has prepared a semantic batch, or the separate operational cancellation commit after `scope_fenced` | Transaction rolls back; live Engine is poisoned and must be discarded. An already committed scope fence remains canonical authority. |
| `dispatch_refuse` | before dispatch acceptance or cancellation acceptance, including a task spawn inside a joined begin | A split composition retains its canonical request/fence for repair; a joined composition rolls the uncommitted semantic batch and task custody back together. |
| `dispatch_delay` | after dispatch acceptance and before a scripted terminal becomes ready | Terminal remains unavailable until a named logical instant. |
| `dispatch_duplicate` | after `activity_terminal_frozen`, `projection_committed`, or `terminal_acknowledged` | The exact same terminal is delivered again. |
| `dispatch_conflict` | after `activity_terminal_frozen` | A different terminal for the same invocation is delivered and must refuse/quarantine according to the production door. |
| `ack_refuse` | after `instance_created`, `delivery_accepted`, `activity_terminal_frozen`, `scope_fenced` cancellation acceptance, or durable quarantine, before collaborator acknowledgement | Durable fact remains and the same item may redeliver or be recognized idempotently after reconstruction. |
| `process_crash` | after any named durable cut and at `external_effect` | All live runtime/collaborator wrapper objects are discarded; only configured durable/script facts survive. |
| `history_unreadable` | before `restart` | Construction/load refuses loud; no safety or liveness claim is made beyond retained failure evidence. |
| `projection_raise` | after `activity_terminal_frozen`, before projection records commit | A registered deterministic test-application projection raises the strict recorded error; the frozen terminal remains authoritative for fresh-load projection-only recovery. |

Fault adapters wrap the existing collaborator contract and may only refuse,
delay, duplicate, or crash at these cuts. They may not edit records, markings,
invocations, or production return values.

## Profile bounds

All bound values are exact non-negative integers, never booleans. Scenarios may
choose smaller values; these `engine-coordinator-v1` ceilings are absolute:

| Bound | Ceiling |
| --- | ---: |
| Scheduled events, including fair steps | 512 |
| Injected fault occurrences | 64 |
| Crash/restart pairs | 32 |
| Actions requested by one `drive` event | 256 |
| Total accepted production actions | 4,096 |
| Logical instant and finite duration, seconds | 1,000,000,000 |
| History records | 50,000 |
| Strict encoded History payload bytes | 4,194,304 |
| Retained tokens | 4,096 |
| Strict encoded retained token bytes | 4,194,304 |
| Pending scripted collaborator outcomes | 256 |
| In-flight activity invocations | 64 |
| Strict encoded scenario or replay artifact bytes | 4,194,304 |
| Wall-clock watchdog per replay | 30 seconds |

The History/token ceilings align with `implementation-free-v1`, and the time
ceiling aligns with Motus's provider-neutral duration maximum. Version 4 lets
each exact profile map these retained and pending ceilings to named gauges and
replays an overage as `budget_exhausted`. The watchdog is a harness-failure
guard, never a simulated timeout. The process-isolated
[`runner/v1`](dst-process-runner-v1.md) enforces the ceiling, terminates and
reaps a hung child, and reports its acknowledged prefix plus unfinished
attempt. Crossing the ceiling is never fabricated as a deterministic artifact
failure for a call which did not return.

Every scheduled event has one of these terminal application dispositions:
`applied`, `idempotent`, `refused_expected`, `quarantined`,
`bounded_exhaustion`, or `harness_failure`. A scenario may expect only the
first five. An unexpected exception, malformed production observation, live
object in a portable value, or schedule/artifact mismatch is always
`harness_failure`, not a runtime correctness failure. Checker outcomes are
separate: `pass`, `safety_failure`, `liveness_failure`, or `not_applicable`.

## Semantic coverage

DST coverage is semantic and schedule-addressed, not line coverage. A campaign
reports the following finite matrix, including zero-count cells:

| Dimension | Required cells |
| --- | --- |
| Event kind | every closed event kind × each reachable application disposition |
| Fault | every fault kind × allowed cut × consumed/not-consumed |
| Durable cut | arrived before crash, arrived after crash, recovered, refused |
| History fact | each production record type admitted by the selected net/profile |
| Occurrence | offered, begun, handler-completed, activity-requested, terminal-frozen, projected, failed, cancelled, quarantined |
| Lifecycle | open, closing/closed, reset, late result across fence, repaired cancellation |
| Delivery identity | anonymous-derived, stable accepted, equal redelivery, conflicting redelivery |
| Recovery | no-op load, projection-only, redispatch, cancellation repair, terminal redelivery, unreadable store refusal |
| Time | no timer, before due, exactly due, after due, multiple due candidates, ceiling |
| Checker | every safety property after normal progress and after reload; liveness in fair/not-fair suffixes |
| Bound | below, exactly at, and one-over admission for every ceiling |
| Result | quiescent, terminal, quarantined, bounded exhaustion, external wait, safety/liveness/harness failure |

A passing campaign with a missing required cell is incomplete, not evidence
that the absent behavior passed. DS3 owns generation and shrinking while the
profile and checker ids above remain the coverage vocabulary.

## Qualification split

The deterministic simulated profile is sufficient for production semantic
ordering, replay, identity, commit, recovery, lifecycle, and bound checks
because it uses the production Engine/Coordinator/Instance code. It is not
sufficient for backend power-loss posture, database isolation, Worker retry
leases, ZeroMQ routing, host process scheduling, network failure, real provider
side effects, or Gondolin process/filesystem behavior. DS4 must therefore
publish claims in two columns:

1. **simulated semantic qualification** — scenario/profile version, seeds,
   matrix coverage, checker results, and exact minimized replay artifacts; and
2. **real-boundary qualification** — named HistoryStore/Dispatch/transport/
   provider implementations, environment, induced fault, and observed durable
   evidence.

Neither column substitutes for the other. “DST passed” without the profile,
bounds, semantic matrix, and replay artifact is not a release claim.

The retained joined-provider artifacts deliberately occupy both columns
without merging their claims: the World supplies deterministic fault,
generation, checker, and replay mechanics, while the exact profiles run the
public Absurd Engine provider against disposable PostgreSQL. Two qualify the
pinned commit-refusal and task-spawn-failure paths through the begin+spawn
commit-or-vanish boundary. A third loses the joined transaction's
acknowledgement after acceptance and proves that fresh load retains exactly one
semantic begin and task. A fourth uses a real Absurd Worker, refuses the
semantic terminal commit after provider completion, and proves recollection
and projection after fresh load. A fifth loses the accepted terminal commit's
acknowledgement and proves projection-only recovery. A sixth refuses the
semantic `ActivityFailed` commit after a non-retryable Worker failure, then
proves fresh-load recollection and exactly one `FiringFailed`. A seventh loses
the accepted `ActivityFailed` commit's acknowledgement and proves fresh load
records exactly one `FiringFailed` without recollecting provider custody. An
eighth refuses the later projection commit and proves the same fresh-load
projection without another Worker completion or handler preparation. A ninth
loses the accepted projection commit's acknowledgement and proves fresh load
preserves convergence without another projection. A tenth refuses the
canonical `ScopeReset` commit, then proves fresh load retains lifecycle
generation 1 and accepts the still-authoritative Worker result exactly once. An
eleventh commits that canonical reset but loses its acknowledgement before
cancellation starts, then proves fresh load reconstructs generation 2, repairs
one tombstone, and fences the stale Worker. A twelfth commits the canonical
reset, refuses the separate real cancellation-tombstone transaction, then
proves fresh-load repair and stale-Worker fencing. A thirteenth loses the
acknowledgement after that tombstone transaction commits, then proves fresh
load recognizes the existing tombstone without a second custody mutation and
again fences the stale Worker. A fourteenth refuses an identified source-delivery
transaction and proves fresh load can accept it exactly once. A fifteenth loses
that transaction's acknowledgement after acceptance and proves fresh load
returns the prior acknowledgement on exact redelivery without another event,
source firing, or output token. A sixteenth refuses canonical `ScopeClosed`
before acceptance and proves fresh load retains the active scope and its
Worker authority. A seventeenth loses the accepted close acknowledgement and
proves fresh load reconstructs terminal scope authority, repairs one task
tombstone, and fences stale completion. A further pair refuses canonical
`ScopeOpened` before acceptance or loses its accepted acknowledgement, proving
fresh load respectively retains absence for a generation-1 retry or
reconstructs exactly generation 1 without opening generation 2. Another pair
refuses `FiringFailed` before acceptance or loses its accepted
acknowledgement, proving fresh load respectively appends the failed firing once
or recognizes the existing projection without recollecting failed provider
custody. A final pair in this slice refuses a stale-scope
`ScopedDeliveryDropped` before acceptance or loses its accepted
acknowledgement, proving fresh load respectively records the drop once or
returns the prior dropped disposition without another transaction. A paired
future-scope route refuses `ScopedDeliveryQuarantined` before acceptance or
loses its accepted acknowledgement, proving fresh load respectively records
the quarantine once or returns the prior quarantined disposition without
another transaction. They do not simulate or claim PostgreSQL power loss,
transport, or provider-wide fidelity.

## Correctness position

Petrus's correctness evidence rests on four composable facts:

1. production decisions and irreversible boundaries are frozen in unified
   History before later behavior relies on them [D, E];
2. the runtime is reconstructible from those facts and profile-pinned
   collaborators rather than retained live objects [E];
3. independent checkers compare each bounded execution and fresh replay to
   safety and fair-liveness obligations [contract above]; and
4. exact expanded artifacts turn discovered counterexamples into deterministic
   regressions rather than transcripts; seeds remain discovery metadata, not
   replay authority [E].

This is an evidence program, not a claim that arbitrary application code,
external providers, or unbounded executions are correct. The confidence grows
with relevant semantic coverage, adversarial schedules, and real-boundary
qualification while remaining explicit about those limits.
