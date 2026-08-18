# Deterministic Simulation Testing

**Status:** CV19 correctness contract. The strict internal DS1 artifact and the
supported DS2 executable-World vertical slice are shipped, including exact
budget/checker-failure replay, seeded choice provenance, and a pre-commit
terminal History refusal. A lifecycle-reset race now also proves crash/load,
late-terminal quarantine, and exact duplicate acknowledgement. Focused profiles
also prove deterministic Engine timer reconstruction and zero-backoff
LocalDispatch retry reconstruction/exhaustion. A separate provider-clock
profile proves delayed retry refusal immediately before availability and claim
at the exact deadline across process loss. A complementary LocalDispatch
profile proves successful-terminal custody and recollection across process loss;
an identified-ingress profile proves source redelivery and identity conflict
recovery. A delayed external-terminal profile proves volatile queue loss,
external-truth reconstruction, and logical-time delivery. Broader fault
adapters now include paired pre-commit refusal and post-commit acknowledgement
loss plus refusal at the public Dispatch acceptance door after the canonical
Activity request commits. Version 4 adds deterministic profile-retained-data
and hidden-pending-work accounting, while outer runner version 1 adds
process-isolated wall-clock containment with acknowledged-prefix diagnostics.
Generation and campaign qualification remain.

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
ordinary deterministic replay test. Generated shrinking remains DS3-owned,
and promoting an internal artifact does not change the public
`implementation-free-v1` contract.

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
| Source delivery ordering, identity, and redelivery | Controlled then recorded | Scenario steps choose arrival order and stable source identity; accepted identity and payload enter unified History before acknowledgement [D: [source delivery decision](../project/decisions/records/2026-07-14T1806Z-source-delivery-projection-and-identity.md); E: `TestDeliveryIdentity` in [`test_ingress.py`](../../tests/petrus/impetus/instance/test_ingress.py)]. |
| Activity invocation preparation and projection | Production behavior under an application profile | The harness calls registered `ActivityHandler.prepare` / `project`; the contract requires deterministic projection. Hidden wall-clock/random reads in application code make that application profile ineligible until controlled; DST does not monkeypatch them [D: [activity seam decision](../project/decisions/records/2026-07-14T2016Z-activity-invocation-runtime-seam.md); E: [`test_activity_seam.py`](../../tests/integration/test_activity_seam.py)]. |
| Activity execution, retry, heartbeat, timeout, and custody | External through `Dispatch` | A scripted `Dispatch` presents protocol outcomes at scenario instants while production Coordinator retains request/result/projection semantics. The retained Dispatch-refusal story proves accepted History outruns refused custody and fresh load republishes the same invocation without `prepare`. Local, Absurd, Worker, and ZeroMQ mechanics remain Motus-owned and require real-adapter qualification [E: [`test_dispatch_refusal_world.py`](../../tests/dst/test_dispatch_refusal_world.py), [`test_local_dispatch.py`](../../tests/petrus/motus/dispatch/test_local_dispatch.py), [`test_zeromq_dispatch_transport.py`](../../tests/petrus/motus/transport/test_zeromq_dispatch_transport.py)]. |
| History append and transaction outcome | Controlled fault at an owned seam | The scenario can refuse or crash around `HistoryStore.append`/`extend` and the joined Engine transaction. The production store decides what committed; reload is the oracle for durable truth [E: [`test_history_backends.py`](../../tests/petrus/impetus/history_store/test_history_backends.py), [`test_engine.py`](../../tests/petrus/engine/test_engine.py)]. |
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
| `instance_created` | `InstanceCreated` and initial marking accepted as one creation boundary. | Reload reproduces identity, marking, status, and next counters exactly. | [E: [`test_instance_identity.py`](../../tests/petrus/impetus/instance/test_instance_identity.py), [`test_instance_replay_properties.py`](../../tests/petrus/impetus/instance/test_instance_replay_properties.py)] |
| `delivery_accepted` | Source acceptance and the selected delivery/projection facts are committed before acknowledgement. | Same identity/payload is idempotent; different payload conflicts; uncommitted delivery is not acknowledged. | [D: source delivery decision; E: `TestDeliveryIdentity` in [`test_ingress.py`](../../tests/petrus/impetus/instance/test_ingress.py)] |
| `activity_requested` | The firing prefix and `ActivityRequested` are committed together before `Dispatch.dispatch`. Invocation id, input, and policy are frozen. | Reload may redispatch the identical invocation; it may not recompute input or project a result. | [E: retained [`dispatch-refusal-crash-recovery-world-v3.json`](../../tests/dst/fixtures/dispatch-refusal-crash-recovery-world-v3.json), `test_selection_installs_only_after_the_begin_commit_returns` in [`test_engine.py`](../../tests/petrus/engine/test_engine.py), and `test_an_outstanding_invocation_is_redispatched_never_re_prepared` in [`test_coordinator.py`](../../tests/petrus/engine/test_coordinator.py)] |
| `external_effect` | The provider may have performed an irreversible effect after accepting an invocation, whether or not Petrus observed the result. | Redelivery is at-least-once; stable invocation id is the idempotency key. DST scripts the ambiguity but cannot prove application idempotence. | [D: activity seam decision; E: `test_backend_owned_dispatch_failure_installs_the_already_durable_begin` in [`test_coordinator.py`](../../tests/petrus/engine/test_coordinator.py)] |
| `activity_terminal_frozen` | `ActivityCompleted` or `ActivityFailed` is committed before result projection mutates the marking. Exactly one terminal family member may exist per occurrence. | Reload performs projection-only recovery; redelivery of the same terminal is idempotent and a conflicting terminal refuses loud. | [E: `test_terminal_result_freezes_before_projection_failure_and_fresh_load_retries_projection_only` in [`test_engine.py`](../../tests/petrus/engine/test_engine.py); kill-window tests in [`test_history_backends.py`](../../tests/petrus/impetus/history_store/test_history_backends.py)] |
| `projection_committed` | Projection records complete the occurrence in one semantic batch. | Reload reproduces marking, status, occurrence indexes, and accepted identity without rerunning the handler. | [E: [`test_instance_replay_properties.py`](../../tests/petrus/impetus/instance/test_instance_replay_properties.py)] |
| `semantic_batch_refused` | Encode/append/commit refusal leaves no accepted semantic batch. A joined transaction rollback poisons the live Engine until reload. | Discard live state and rebuild from durable History; memory must not outrun durability. | [E: transaction and poisoned-engine tests in [`test_engine.py`](../../tests/petrus/engine/test_engine.py); refusal tests in [`test_history_backends.py`](../../tests/petrus/impetus/history_store/test_history_backends.py)] |
| `scope_fenced` | Close/reset semantic facts commit before best-effort Dispatch cancellation. | Reload/reconcile repairs pending cancellation; late terminal delivery is quarantined rather than projected across the fence. | [E: `test_close_commits_before_retiring_pending_dispatch_and_late_terminal_is_quarantined` and `test_restart_repairs_a_committed_cancellation_instruction_idempotently` in [`test_engine.py`](../../tests/petrus/engine/test_engine.py)] |
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
| `history_commit_refuse` | joined transaction commit after production has prepared any semantic batch | Transaction rolls back; live Engine is poisoned and must be discarded. |
| `dispatch_refuse` | before dispatch acceptance or cancellation acceptance | Dispatch door raises/refuses; canonical request/fence remains durable for repair. |
| `dispatch_delay` | after dispatch acceptance and before a scripted terminal becomes ready | Terminal remains unavailable until a named logical instant. |
| `dispatch_duplicate` | after `activity_terminal_frozen`, `projection_committed`, or `terminal_acknowledged` | The exact same terminal is delivered again. |
| `dispatch_conflict` | after `activity_terminal_frozen` | A different terminal for the same invocation is delivered and must refuse/quarantine according to the production door. |
| `ack_refuse` | after `delivery_accepted`, `activity_terminal_frozen`, or durable quarantine, before collaborator acknowledgement | Durable fact remains and the same item may redeliver. |
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

## Correctness position

Petrus's correctness evidence rests on four composable facts:

1. production decisions and irreversible boundaries are frozen in unified
   History before later behavior relies on them [D, E];
2. the runtime is reconstructible from those facts and profile-pinned
   collaborators rather than retained live objects [E];
3. independent checkers compare each bounded execution and fresh replay to
   safety and fair-liveness obligations [contract above]; and
4. exact seed-addressed artifacts turn every discovered counterexample into a
   deterministic regression rather than a transcript [planned by CV19.DS2/DS3].

This is an evidence program, not a claim that arbitrary application code,
external providers, or unbounded executions are correct. The confidence grows
with relevant semantic coverage, adversarial schedules, and real-boundary
qualification while remaining explicit about those limits.
