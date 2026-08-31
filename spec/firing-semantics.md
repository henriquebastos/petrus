# Firing Semantics

This document specifies how an Impetus net instance evolves: enabledness, the
firing pipeline, the begin/end firing lifecycle, scheduling, default behavior,
timers, replay, and termination. Structure is specified in `net-schema.md`;
every step described here is recorded per `event-history.md`; handler
execution obeys `handler-contract.md`.

## Enabledness

A transition is **enabled** when, under the current marking [glossary]:

1. every **consume** input arc has matching token(s) satisfying its
   inscription's color/type, cardinality, and optional filter [ADR 0006,
   ADR 0018, DR 2026-07-07 arc-filters-and-guards-cel-or-named-both-pure];
2. every **read** input arc has matching token(s) satisfying its filter, which
   participate in the firing binding but are not consumed [ADR 0006];
3. every **inhibit** input arc finds *no* token matching its color/filter
   [ADR 0006];
4. every declared guard returns true when evaluated over the selected tokens
   **without consuming them** (guards evaluate on peeked tokens)
   [ADR 0021, Petrus oracle];
5. all declared transition timers have matured (see Timers) [ADR 0005].

Candidate computation first enumerates token selections from arcs — each arc's
optional filter pruning its per-arc token set — then filters the assembled
bindings with guards [ADR 0018, DR 2026-07-07
arc-filters-and-guards-cel-or-named-both-pure]. A filter is a pure single-token
boolean (CEL or named symbol); a guard is a pure boolean over the full binding,
where cross-token correlation lives — never in an arc filter [ADR 0018]. Filters
and guards are pure: every process side effect lives behind a handler, and
external state a net
gates on enters the marking by projection, so enablement stays replay-
deterministic [DR 2026-07-07 purity-invariant-and-projection].

Evaluation errors in this pipeline are ruled [DR 2026-07-08
guard-filter-evaluation-errors]: a **declared mismatch** (a guard/filter
requiring what no arc can supply, where types are declared) is an
instantiation-time validation error and never evaluates; a **runtime
evaluation error** on a concrete token (possible under permissive untyped
arcs) means that **binding is not satisfied** — the candidate is skipped
per-binding, deterministically (the expressions are pure), and enablement
computation continues; and every runtime evaluation error is **surfaced as
a diagnostic** (expression NetUri, token, error), never silently swallowed.
For reference, the Petrus oracle treated a `TypeError` while extracting
guard arguments from peeked tokens as "not enabled" rather than a crash
[Petrus oracle] — an artifact of Petrus keeping type knowledge only in
guard signatures; Impetus reproduces the *skip*, rejects the *silence*.

## Firing pipeline

The pipeline, in the ubiquitous language [glossary]:

```txt
enabledness
→ firing binding            (a concrete assignment satisfying all input arcs + guards)
→ enabled firing candidate  (transition + firing binding, valid but not selected)
→ Candidate Selection       (per-Instance policy chooses at most one Binding
                             within the BeginCandidate action class)
→ DrivingPolicy             (chooses among whole action classes)
→ selected firing occurrence (durable record when BeginCandidate commits)
→ begin firing              (input token accounting; an impure transition's
                             prepared activity request freezes in this batch)
→ activity execution        (via the execution runtime)
→ activity result           (durable observed terminal fact)
→ handler projection        (deterministic, server-side)
→ end firing                (commit: output tokens or failure semantics)
```

A pure transition skips the activity steps and projects locally. The shipped
seam separates preparation, execution, and projection exactly so: an
`ActivityHandler`'s prepared request freezes in the begin batch, the
execution adapter runs the activity, the frozen result projects
deterministically [DR 2026-07-14 activity-invocation-runtime-seam].

A transition may be enabled under many firing bindings at once [glossary].
The distinction between "enabled firing candidate" and "selected firing
occurrence" is where scheduling policy enters [ADR 0008].

## Begin/end firing lifecycle

Handled transitions cannot fire as instantaneous token movements: the
activities handlers prepare may perform side effects, wait for humans, invoke
agents, retry, or run on other
workers. Impetus models this as a durable **firing occurrence** lifecycle
[ADR 0007]:

1. a transition is enabled under a specific firing binding;
2. the runtime creates a durable firing occurrence;
3. **begin firing** records the occurrence and consumes or otherwise accounts for
   input tokens according to arc modes — accounting at begin prevents
   duplicate workers from processing the same consumed token [ADR 0007];
4. the prepared activity executes on the execution runtime — the server-side
   handler prepares before dispatch and projects after the terminal activity
   fact [ADR 0012, DR 2026-07-14 activity-invocation-runtime-seam];
5. the activity returns a typed result or the adapter reports terminal
   failure after exhausting its resolved policy;
6. **end firing** commits: produces output tokens per the output arc
   inscriptions, records failure semantics, or applies runtime policy
   [ADR 0007].

The runtime is not limited to one handled firing at a time; adapters may
schedule multiple enabled firing occurrences concurrently when policy allows
[ADR 0007]. Retry, timeout, lease, claim, and activity-attempt tracking remain
execution runtime responsibilities, outside canonical history [ADR 0006,
ADR 0007, DR 2026-07-14 activity-invocation-runtime-seam].

Operational retries reuse the exact frozen invocation, correlation, and
idempotency identities. Retryable failures may schedule another Attempt only
within the bounded policy and aggregate deadline; non-retryable failures and
exhausted policies produce one terminal `ActivityFailed`. A heartbeat renews
the current Attempt's liveness lease but cannot extend its start-to-close or
the logical execution's schedule-to-close deadline. Delayed retry belongs to a
durable execution adapter and is never implemented by blocking Inline
execution [DR 2026-08-10 one-logical-activity-execution].

Terminal failure follows the same freeze-before-projection boundary as
success. The runtime first records `ActivityFailed`; then an explicitly
failure-projecting handler deterministically ends the firing through ordinary
effects, while a legacy handler records `FiringFailed` and halts. If a crash
separates those boundaries, reload resumes only projection or fail-and-halt
from the frozen failure and does not dispatch another Attempt [DR 2026-08-10
one-logical-activity-execution].

## Token production

Output tokens are produced at end firing per output arc. Each output arc's
inscription is a **routing contract** naming the color/type it accepts into its
target place; the **handler supplies the actual tokens**, keyed by destination,
and the runtime deposits only handler tokens whose color and destination match an
output arc [ADR 0017, ADR 0007, DR 2026-07-07
output-production-per-arc-contract-handler-supplies-tokens]. Different output arcs
therefore carry different payloads from one firing (heterogeneous fan-out); a
token factory is never inferred from shapes [ADR 0010]. When a transition
declares no handler, output follows the passthrough rule below.

This differs explicitly from the Petrus oracle, which deposits one merged token
to ALL output places (`Token.merge`, last-wins per type) — flagged in the
reference as an outlier versus per-arc output contracts [Petrus oracle]. Impetus
adopts the per-arc contract; the normative `per_arc_passthrough` and
`heterogeneous_fanout` golden fixtures record that model positively.

## Scheduling

Petrinet Kernel, Candidate Selection, and whole-action policy have distinct
jobs [ADR 0008, DR 2026-07-21 concept-first-ontology-boundaries, DR 2026-07-22
candidate-selection-is-instance-scoped-immutable-policy]:

- the **kernel** evaluates the marking and Net to enumerate enabled
  firing candidates;
- **Candidate Selection**, outside the kernel and composed per Instance by its
  Engine, chooses at most one already-enabled Binding within the
  `BeginCandidate` action class;
- whole-action **`DrivingPolicy`** still chooses whether accepting an outcome
  or delivery, beginning a candidate, advancing time, waiting, or stopping
  takes precedence;
- begin firing applies the one chosen Binding;
- Candidate Selection configuration is snapshotted by the one-Instance Engine,
  never hard-coded into the Net or inherited from ambient fleet policy.

**Source transitions are excluded from the enabled-candidate set.** A source
transition (no input arcs, the external-event entry point — see `net-schema.md`)
is never auto-scheduled and never fires spontaneously; it fires **only when the
runtime delivers an external event** to it [DR 2026-07-08
source-transition-ingress]. Quiescence — the trigger for the termination status
rule below — is therefore "no *non-source* transition enabled": a source
transition with an armed registration does not keep an instance out of
quiescence, it makes the instance *awaiting* (see §Termination).

The initial Candidate Selection policies are **First**, **Priority**, and
**transition-level Round-Robin**. Each documents its behavior; the base
contract promises no universal fairness grain. Every policy uses a fixed
filters → stable rankers → one strategy pipeline and preserves deterministic
Petrinet candidate order as the final tie-breaker. If filters admit none of a
non-empty enabled set, selection returns `None` to `DrivingPolicy`; declining
to act appends no semantic History. If no Bindings are enabled, selection is
not invoked [DR 2026-07-22
candidate-selection-is-instance-scoped-immutable-policy].

Selection proposes immutable next policy state. It installs only after the
Instance selection/begin append commits; replay folds existing committed
`CandidateSelected` transition facts only when the occurrence has a matching
committed `FiringBegun`; an orphan selection from a partial durable prefix does
not advance policy state. One Engine turn selects at most one Binding.
Concurrency comes from repeated turns and in-flight occurrences;
conflict-free batch selection and partial commits are deferred. Firing movement
records explain the actual Binding without a new durable Binding key or record
[DR 2026-07-22 candidate-selection-is-instance-scoped-immutable-policy].

One Engine advancement turn applies at most one normal whole Action after
finite first-load reconciliation, then returns control to its host.
`DriveOutcome.ready` asks the host to re-drive immediately (the conservative
re-drive may discover quiescence); `waiting` means conservative policy is
holding for an outstanding Activity; `next_maturation` reports the earliest
timer deadline. Waiting and timer scheduling are host-owned: Engine
advancement never sleeps, and clock observation is nonblocking [glossary].

Both shipped `DrivingPolicy` implementations alternate already-buffered
ingress with eligible internal work; a custom policy owns its own fairness.
If a custom policy first chooses an immature wall-clock action, it may be
called once more with only that unavailable action removed from the same
Snapshot; the turn still applies no more than one Action [glossary].

For reference, the Petrus oracle prioritizes immediates (input arcs, no
handler) over handled transitions when picking the next fireable — "resolving
all routing before committing to an activity ensures the marking is stable" —
and excludes timed transitions from that pick [Petrus oracle].

**VELOCITRON-DIVERGENCE:** velocitron's default firing policy is first-found
in net declaration order, with policies as pluggable handlers / Impetus
uses per-Instance Candidate Selection with First, Priority, and
transition-level Round-Robin initial policies, immutable state advancing only
after begin commits, and deterministic Petrinet candidate order as final
tie-breaker [DR 2026-07-22 candidate-selection-is-instance-scoped-immutable-policy]
/ status: deliberate runtime-profile distinction; shared successful-flow
conformance must name the selected profile rather than assume one default [DR
2026-07-23 Impetus-owned Net-definition protocol].

## Default behavior: the passthrough default handler

Passthrough is **a handler, not an engine special case**: the engine always
invokes the transition's handler, and a transition with no handler symbol is
default-bound to the library's pure `passthrough` handler by the binding layer
[DR 2026-07-07 passthrough-is-a-default-handler-color-routed], reframing
[ADR 0010]'s "default behavior" as a default *binding*.

`passthrough` is **color-routed forwarding**: each consumed token is forwarded,
unchanged, through **every output arc that admits it** — a typed output arc
admits its color, an untyped output arc admits anything
[DR 2026-07-07 permissive-flow-defaults]. One token admitted by N arcs is
deposited into N places (broadcast generalizes). Consumed tokens admitted by
no output arc are simply consumed — allowed, not an error
[DR permissive-flow-defaults]. A transition with zero output arcs is a legal
**sink**: it consumes and produces nothing. The runtime never merges, splits,
or retypes tokens by default [ADR 0010, DR 2026-07-07 output-production...,
DR 2026-07-07 aggregate-token-type...]; Impetus MUST NOT infer packing,
unpacking, filtering, projection, or type transformation from input/output
shapes — shaping beyond routing requires an explicit handler [ADR 0010].

A small family of **pure stdlib shaping handlers** grows beside `passthrough`,
selectable by name like any handler symbol; only `passthrough` is a default
[DR passthrough-is-a-default-handler-color-routed]. Decided members:

- **`unpack`** (structural projection): given one aggregate token, projects its
  named fields to the output arcs that admit them — type-driven when a color is
  unambiguous, an explicit field path (CEL projection) when several fields share
  a color. Pure, single-input, no construction; unmatched fields are leftover,
  allowed [DR 2026-07-08 unpack-stdlib-handler-projection,
  DR permissive-flow-defaults].

There is deliberately **no stdlib `pack`** (constructing an aggregate from
several inputs): it is type *construction* — a binding/runtime concern the pure
net must not carry — and the side that would drift into a hidden expression
language. Aggregation is a user or reusable-component handler
[DR 2026-07-08 pack-aggregation-deferred, ADR 0012]. Reopen only on a clear
future need.

Read and inhibit arcs participate in enablement but contribute nothing to
passthrough output. This resolves the earlier passthrough OPEN (first as
identity + homogeneous broadcast, now superseded by color routing).

## Timers

Timers are **transition enablement semantics**: a transition may declare that
its enablement is delayed by a duration or until a specific time [ADR 0005].
Timer declarations belong in the net definition, attached to transitions;
places have no time-related behavior [ADR 0005]. The runtime adapter owns
actual clocks, durable timer scheduling, wakeups, and replay-safe delivery of
time events [ADR 0005]. Timer maturation is recorded in the event history
[ADR 0031].

A timer declares either a duration (`delay Δ`) or an absolute instant
(`until D`) [ADR 0005], and is **evaluated per firing binding**
[DR 2026-07-08 timers-keyed-per-firing-binding-age-anchored]: a duration
timer matures a binding at `anchor(binding) + Δ`, where the anchor is the
youngest recorded entry instant among the binding's consume/read-bound tokens;
an absolute timer matures every binding at `D`. Inhibitor arcs contribute no
anchor — a duration timer on an all-inhibitor transition is a validation
error. Timer state is **derived, never stored**: maturation is a pure
function of net definition, marking, and recorded history, evaluated at
candidate computation; the adapter's only durable obligation per instance is
a wakeup at the derived `nextMaturation`
[DR 2026-07-08 time-projection-virtual-clock-watermark].

"Now" is the per-instance **clock watermark** — the adapter-assigned,
monotone instant of the latest appended event history record; semantic time
advances only at appends [DR time-projection...]. On wakeup the adapter
appends a **timer matured** record (category 2, deterministic [ADR 0031,
ADR 0034]); any record's instant advances the clock, and replay re-derives
every maturation from the log with no clock read (see `event-history.md`).
There is **no urgency**: maturation enables; Candidate Selection and
whole-action `DrivingPolicy` choose whether a Binding begins [ADR 0008, ADR
0009, DR 2026-07-22 candidate-selection-is-instance-scoped-immutable-policy]
— deadline pressure is modeled as racing timeout transitions.

For reference, the Petrus oracle implements two timer semantics — absolute-
deadline "not-before" (remaining time recomputed from the same instant on
re-enable) and delay-after-enable (full duration restarts each enablement
epoch), with deadline taking priority — honors matured timers only if the
transition is still enabled, and keys timers by transition path, explicitly
scoping concurrent independent timers for one transition out [Petrus oracle].
Impetus diverges deliberately: per-binding keying makes concurrent timers
work; matured-only-if-still-enabled falls out as derived behavior; and delay
does **not** restart per enablement epoch — restart semantics is expressed
structurally via a refresh transition (production mints a new entry instant)
[DR timers-keyed-per-firing-binding-age-anchored]. This resolves the earlier
instance-scoping OPEN (ES-007).

## Deterministic replay

The runtime model aims for deterministic replay: given the same external
events, activity results, and timer events in the same order, a net instance
reaches the same state [ADR 0004, glossary]. Net execution advances
deterministically from recorded history; side effects occur through the
activities handlers prepare, and their observed results are recorded durably
and reintroduced as tokens, failure records, or events — replay never re-runs
side effects [ADR 0004, ADR 0034]. ADR 0004 was never accepted as written: its
separate handler-result record model is superseded by the Activity invocation
runtime seam, while deterministic replay and non-reexecution of recorded
external work are settled by the event-History and Activity decisions [ADR
0030–0035, DR 2026-07-14 activity-invocation-runtime-seam].

## Termination

An instance's status is a **derived, four-valued projection over recorded
history** — never stored as independent truth [ADR 0033, DR 2026-07-08
termination-instance-status-rule]:

- An instance is **quiescent** when no firing candidate is enabled under the
  current marking, no firing occurrence has begun without ending [ADR 0007],
  and no firing binding has a derived future timer maturation
  [DR 2026-07-08 timers-keyed-per-firing-binding-age-anchored]. Quiescence
  is the trigger for status, never the verdict.
- The optional **completion condition** — a pure marking predicate declared
  on the net (`#completion`; inline CEL or named pure symbol, same tier as
  guards) — supplies the *done* judgment. It never affects enabledness or
  firing (the [ADR 0027] discipline applied to a net-level declaration); see
  `net-schema.md`.
- The binding/runtime layer's **event-projection registrations** — records
  that the runtime may still deliver an external event to a **source
  transition** of this instance [DR 2026-07-08 source-transition-ingress] —
  supply the *waiting* judgment. A runtime connection counts iff it can still
  deliver (an armed registration on a source transition); open/close
  are recorded process facts (see `event-history.md`).
- **Status**: RUNNING if not quiescent; else COMPLETED if the declared
  condition holds; else AWAITING if any registration is armed; else STUCK
  (condition declared) or TERMINATED (neutral collapse when none is
  declared — validators MAY warn). Status is re-evaluated on any history
  append, including registration close. Finalization or halt-on-complete is
  runtime policy, never net semantics [ADR 0008].

Place roles play no part [ADR 0027]. For reference, the Petrus oracle used
place interfaces (`input|output|awaiting|control`) and defined
`is_terminated()` as: a token in a sink place AND no `awaiting` place holds a
token AND nothing enabled [Petrus oracle]. Impetus re-derives each ingredient
without roles — declared predicate for the sink token, runtime registrations
for the awaiting mirror — per the boundary scenarios in ES-006. The
`awaiting_termination` golden fixture pins the oracle rule and is tracked as
oracle-divergence debt.
