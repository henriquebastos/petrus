# Event History

This document specifies the Impetus **event history**: the durable,
append-only record of how a net instance evolves. The steps it records are
defined in `firing-semantics.md`; the structures it references are defined in
`net-schema.md`; handler and activity execution is defined in
`handler-contract.md`.

## Terminology

The working term is **event history** [DR 2026-07-06 event-history-is-the-term].
Avoid "firing journal", "audit trail", or "event log" as the canonical name.
The naming disagreement with velocitron is about scope, not taste: a firing
journal records firings; an event history records everything that explains
process evolution [DR 2026-07-06 event-history-is-the-term].

**VELOCITRON-DIVERGENCE:** velocitron's "firing journal" records firings and
its glossary explicitly avoids "event log/history" / the Impetus event history
records the broader scope — external events, timer maturation, scheduler
decisions, activity requests and results — per the record
model below [ADR 0031, DR 2026-07-06 event-history-is-the-term] / status:
deliberate runtime-profile distinction; a narrow firing-outcome projection is
deferred until a concrete cross-runtime conformance consumer exists [DR
2026-07-23 Impetus-owned Net-definition protocol].

## One unified history per net instance

Every transition firing is semantically part of **one unified event history**
— passthrough, deterministic/internal, handled, side-effecting, and
worker-routed transitions alike [ADR 0030]. Transitions differ by execution
requirements, not by whether they belong to history [ADR 0030].

The event history is **per net instance**, like a Temporal workflow's history:
appends serialize within one instance (single writer), and there is no global
log requiring cross-machine merge [DR 2026-07-06 net-instance-is-a-process].
Instances communicate by spawning children, signals, and updates — messages,
not shared state — so cross-instance coordination appears in each instance's
own history [DR 2026-07-06 net-instance-is-a-process].

The queue remains distinct from history: queues deliver work; history records
durable truth [ADR 0030].

## The canonical log is uncompacted

The canonical event history is an **append-only, uncompacted tracing log**
[ADR 0033]. Derived projections, indexes, snapshots, summaries, materialized
views, and rollups are allowed — current marking by place, active firing
attempts, latest status, latency histograms — but they are derived,
disposable, and rebuildable from the canonical log; they never replace it
[ADR 0033, ADR 0030]. Performance is improved with projections and indexes,
not by destroying the canonical log [ADR 0033]. Storage growth is an explicit
operational concern; retention/export/archive policy is separate from semantic
compaction [ADR 0033].

## No correctness/observability split

Impetus does not classify history records into "correctness" versus
"observability" categories [ADR 0032]. If a record explains how the process
evolved, it participates in correctness, replay, fork, audit, debugging, and
observability at the same time. The meaningful distinction is **semantic event
history** (the conceptual timeline) versus **physical storage representation**
(how an implementation persists, indexes, projects, and snapshots it)
[ADR 0032]. APIs expose history as one coherent process timeline, not separate
correctness and telemetry streams [ADR 0032].

## The minimal record model

The working semantic record categories are [ADR 0031]:

1. **External event recorded** — a webhook, user message, poll result, human
   decision, imported file, or other outside signal entered the history.
2. **Timer matured** — a time-based enablement condition became true.
3. **Firing candidate selected** — Candidate Selection chose an enabled
   transition/Binding to proceed. The transition fact supports initial policy
   replay; the firing's movement records explain the actual Binding without a
   separate scheduler-decision record [DR 2026-07-22
   candidate-selection-is-instance-scoped-immutable-policy].
4. **Firing begun** — the runtime durably recorded the attempt boundary.
5. **Tokens consumed/read/accounted** — how input arcs interacted with
   selected tokens.
6. **Activity requested** — a handled transition required semantic
   side-effect work; the exact immutable activity invocation is frozen in the
   firing's begin batch before dispatch and acts as the authoritative outbox
   [DR 2026-07-14 activity-invocation-runtime-seam].
7. **Activity completed/failed** — the terminal activity fact: a typed
   external result frozen before deterministic handler projection, or the
   exhausted-policy failure [DR 2026-07-14 activity-invocation-runtime-seam].
8. **Firing completed** — success/failure semantics and marking evolution
   committed.
9. **Tokens produced** — output tokens recorded into places.
10. **Firing failed/cancelled/compensated** — non-success terminal semantics.

These are semantic categories. **Token consumption, read, accounting, and
production are explicit records, not deltas** folded inside a firing record, so
the marking is derivable by replaying explicit token movements
[DR 2026-07-08 explicit-token-records-and-replay-by-reapplication].
ADR 0031's original list carried two further categories — "activity attempt
recorded" and "handler result recorded" — both superseded [DR 2026-07-14
activity-invocation-runtime-seam]: operational attempts and retries belong to
the execution adapter, and the handler is a deterministic bridge, not a third
durable lifecycle — its projection is represented directly by the token and
registration effect records. The earlier CV3 schema-2 migration shipped the ruled
vocabulary: records correlate by `occurrence`, the delivery-registration
family and `ExternalEventDelivered` carry their ruled names, and begin
batches record read selections (`TokensRead`). The activity seam then
shipped the activity record family — `ActivityRequested` in the begin batch,
`ActivityCompleted` frozen before projection, `ActivityFailed` beside
`FiringFailed`. Canonical schema 3 removes Worker capability and queue-routing
facts from `ActivityRequested`; schema 2 is refused before interpretation and
has no migration. Operational queue identity never enters canonical History.
**DEFERRED (kernel):** exact payload fields per category and whether "firing
candidate selected" is durable before "firing begun" are kernel-revealed
record-schema details [ADR 0031, DR 2026-07-08 kernel-deferred-spec-details].
Retry grouping is no longer deferred: operational retries are activity
attempts against one frozen activity invocation, outside canonical history
[DR 2026-07-14 activity-invocation-runtime-seam].

**Event-projection registration lifecycle is recorded.** Opening or closing
a registration — the runtime's standing capability to deliver an external
event to a **source transition** of this instance [DR 2026-07-08
source-transition-ingress] — is a process fact and appears in the canonical
history, because the derived instance status can flip on a registration close
with zero net activity [DR 2026-07-08 termination-instance-status-rule]. Whether open/close records are payloads
of existing categories or a category of their own folds into the payload
deferral above [ADR 0031].

External events MUST be recorded as facts when they arrive, even when no
transition consumes them yet — recording precedes and is independent of
consumption ("recorded and then used to advance the net" [CONTEXT.md],
category 1 above [ADR 0031]). This encodes the production lesson from the
Temporal-hosted Petri-net predecessor: external results enter durable history
first, and the net advances deterministically from recorded history
[ADR 0004, docs/project/briefing.md].

## Lifecycle scopes

A lifecycle scope is a named, explicit ownership boundary for one generation
of process work. Its durable identity is exactly `(name, generation)`, where
generation is a positive, monotonically increasing integer for that name.
`ScopeOpened` activates one generation; `ScopeClosed` closes one exact active
generation; and `ScopeReset` atomically closes that generation and opens its
immediate successor. There is no intermediate unscoped state during reset
[DR 2026-08-11 history-first-lifecycle-scopes].

Lifecycle order is canonical append order, never `instant`. Closing records
carry the complete exact set of scoped queue-entry identities discarded and
in-flight firing occurrences cancelled at their append position. Replay MUST
refuse an omitted, additional, or differently scoped identity rather than
repairing it. Equal-valued tokens remain distinct queue occurrences, so cleanup
removes exactly the listed entries. Consumed firing inputs stay consumed;
close/reset performs no implicit restoration. Any compensation is a later,
explicit domain fact.

Scope provenance propagates from scoped ingress or scoped queued tokens into
the firing occurrence, its produced queue entries, and an Activity request.
The firing `occurrence` remains the owner of same-generation execution:
generation identity never replaces invocation correlation or idempotency.
Lifecycle scope values contain only name and generation; credentials, clients,
closures, Activities, Engines, and other live capabilities are forbidden.

Canonical close/reset MUST commit before any cancellation instruction becomes
visible to Dispatch. History is the business truth; cancellation is a
recoverable operational projection that Dispatch repairs from History after a
restart. Cancellation fences future accepted execution and terminal delivery,
but cannot prove that an ambiguous external effect did not already happen.
Pending custody may be retired, claimed/running custody is fenced, and an
already terminal custody state is observed; none of these dispositions changes
the canonical close. Providers unable to install a recoverable fence MUST be
refused before closing a scope that has an in-flight Activity.

An Activity terminal already committed before close is projection-pending, not
cancellable. Its deterministic projection MUST complete before the generation
can close or reset; recovery therefore loads and reconciles projection before
attempting lifecycle closure.

The first terminal Activity fact still wins. Exact redelivery of an already
accepted terminal is acknowledged and a conflicting value fails loud. A
terminal arriving after its generation was closed is recorded as
`ActivityTerminalQuarantined` and cannot alter that generation. An identified
delivery proven to target a closed generation is recorded as
`ScopedDeliveryDropped`, acknowledged, and never fired. A delivery carrying
only a scope name, or an exact generation the History cannot prove open or
closed, is recorded as `ScopedDeliveryQuarantined`; it is never silently
retargeted to the current generation. Exact duplicate disposition is
acknowledged, while conflicting identity reuse fails loud.

Quarantine is a durable audit disposition, not an operational reprocessing
queue. Petrus supplies no generic release, retarget, or retry operation for a
quarantined ingress or terminal; a host inspects History and performs explicit
domain reconciliation when required.

Every canonical record uses schema 5. Token movement records always carry
`entries` and `scope`: an unscoped movement has `entries: []` and `scope:
null`; a scoped movement has one positive, unique queue-entry identity per
token and its exact lifecycle scope. Nonempty queue identities without a scope
are invalid. The current pre-release protocol has no schema-4 decode or
migration path.

## Deterministic records vs activity records

The canonical log distinguishes — within one unified history, not as separate
logs — **deterministic net/runtime records** from **activity records**
[ADR 0034]:

- *Deterministic records* describe replayable net evolution: external event
  accepted, timer matured, firing candidate selected, firing begun, tokens
  consumed/read/accounted, tokens produced, firing completed, marking/state
  boundaries. Replay reconstructs state from these without re-running side
  effects [ADR 0034].
- *Activity records* describe non-deterministic or externally executed work:
  the frozen activity request and the terminal activity completion or failure
  [DR 2026-07-14 activity-invocation-runtime-seam]. During replay these are
  observed facts, never side effects to re-run [ADR 0034].

The exact requested input and the terminal result of external work must be
visible in the canonical log itself, not only in derived projections
[ADR 0034]. Operational attempts, retries, and their timing live in the
execution adapter's reconstructible store, correlated by invocation identity —
this refines ADR 0034's original clause that attempts and retries appear in
the canonical log [DR 2026-07-14 activity-invocation-runtime-seam].

The terminal failure is a standalone freeze boundary, not merely a field in
the later firing halt. `ActivityFailed` preserves the safe classified failure
before either deterministic `project_failure` effects or legacy
`FiringFailed`. A durable prefix ending at that record is recoverable: reload
repeats projection only and never creates another Attempt. Intermediate
retryable failures remain Dispatch state and never enter canonical History;
only the accepted first terminal value does. Identical terminal redelivery is
acknowledged and a conflicting terminal value is rejected [DR 2026-08-10
one-logical-activity-execution].

## Activities, not worker mechanics

The event history records semantic **activities** and process facts — not
worker/queue mechanics [ADR 0035]. Queue publication, polling, claims,
lease/ack/nack and lease generations, heartbeats, backoff, worker
startup/shutdown, sandbox/container details, stdout/stderr, resource usage,
and delivery failures belong in **worker operational logs**, correlated back
to the canonical history by IDs such as `activityId`, `activityAttemptId`,
`firingOccurrenceId`, `netInstanceId`, `eventId`, `queueMessageId`, and
`workerId` [ADR 0035, CONTEXT.md].

The attempt boundary is decided [DR 2026-07-14
activity-invocation-runtime-seam], resolving both ADR 0035's open question
and the former kernel deferral: canonical history carries exactly the frozen
activity request and its terminal completion or failure. Every activity
attempt — each operational try of the same frozen invocation — stays in the
execution adapter's store, which may be durable for coordination but is
reconstructible machinery: it can be rebuilt by finding requested activities
without terminal activity records.

A **pure** handler (`passthrough`, `unpack`, any pure stdlib shaping handler)
produces **no activity records** — there is no external activity to schedule,
attempt, or observe — but its firing **is** recorded as deterministic records
(firing begun, tokens consumed, tokens produced, firing completed), including
the concrete produced tokens [DR 2026-07-08
explicit-token-records-and-replay-by-reapplication, ADR 0034]. Because every
firing's produced tokens are recorded — pure or impure — **replay re-applies
recorded token movements in recorded order and never re-executes a handler**,
making replay uniform and independent of the live scheduling strategy. Activity
records exist only for impure work; the pure/impure distinction never affects
whether a firing appears in history.
