"""
The Engine's driving runtime: the execution side of the firing-occurrence seam.

The kernel below this module is pure net semantics — it derives what is
enabled, what a firing means, and when a binding matures, all from recorded
facts (the watermark, never a wall clock). This module owns the other half of
that bargain [ADR 0005, DR 2026-07-08 time-projection-virtual-clock-watermark]:
*how* instants are observed and *where* activities run. The public ``Engine``
hosts this coordination and exposes whole-action advancement without blocking.
The ``Sensor`` is the Clock's ingress twin: each observation transfers a finite
batch of already-available ``Delivery`` parcels. The coordinator durably
accepts each parcel before it runs the parcel's pure source projection.

The ``Coordinator`` is the asynchronous driver over the same seam [ES-012
session 3, §Asynchronous coordination and composable policy]: dispatch
acknowledgement and activity completion are different EVENTS — ``begin``
dispatches an occurrence and leaves it in flight, independent work continues,
and results commit in arrival order whenever they arrive — in one
deterministic loop, never different threads (real parallelism is a worker
substrate's, outside this process). Each turn the coordinator observes a
``Snapshot``, computes the invariant-preserving action vocabulary
(``AcceptResult``, ``AcceptDelivery``, ``BeginCandidate``, ``AdvanceTime``,
``Wait``, ``Stop``), a ``DrivingPolicy`` chooses exactly one action, and the
coordinator — the only component allowed to — applies it against the single
writer. Policies compose over available actions and need not replay
deterministically: ``CandidateSelected`` records the committed choice, and
replay reconstructs that fact rather than rerunning the policy [session 3].
On start the coordinator reconciles before driving (session-3 gap 4):
in-flight invocations without a frozen result are redispatched from the
recorded outbox (``prepare`` is never re-run), projection-pending occurrences
complete by projection alone, and pure in-flight occurrences are driven to
terminal.

The callable ``runtime`` is the activity-execution contract [DR 2026-07-14
activity-invocation-runtime-seam]: it is called with a Petri-agnostic
``ActivityInvocation`` and returns the activity's typed terminal result — or
raises its terminal failure, once its resolved policy is exhausted. The
``InlineDispatch`` is the first adapter: it resolves the named activity from
its own registry and executes it here, now, synchronously. Real substrates
(queues, workers, durable executors) lease and retry however they like — only
the terminal result or failure reaches the net [ADR 0007, ADR 0012]. A
terminal failure halts the drive — the fact is recorded (``ActivityFailed``
+ ``FiringFailed`` for impure work), the exception propagates, and no further
work is driven: stop-on-terminal-failure is this driver's default policy
(halting is safer than progressing with the wrong state); a softer policy is
a future driver's, never net semantics. A projection failure AFTER the
result froze is different in kind: the occurrence stays in flight,
projection-pending, and is never converted into a failed firing.
"""

from __future__ import annotations

# Python imports
from collections.abc import Callable, Sequence
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Protocol

# Internal imports
import petrus.telemetry as telemetry
from petrus.motus.activity import ActivityFailure
from petrus.impetus.binding import ActivityHandler
from petrus.motus.dispatch import (
    CancellableDispatch,
    CancellationDisposition,
    CancellationInstruction,
    Dispatch,
)
from petrus.impetus.petrinet import Binding, Selection
from petrus.impetus.instance import (
    AcceptedDelivery,
    DeliveryIdentity,
    FiringOccurrence,
    FiringOutcome,
    ScopeClosure,
    _CompletionCommitRefused,
    firing_failure_text,
)
from petrus.impetus.petrinet import Token
from petrus.impetus.instance import Instance
from petrus.impetus.petrinet import Instant, NetPath
from petrus.impetus.petrinet.schema import canonical_net_path
from petrus.impetus.history import FiringFailed, replay_cancellation_positions
from petrus.impetus.scope import LifecycleScope
from petrus.impetus.selection import (
    SelectionPipeline,
    SelectionPolicy,
    SelectionProposal,
    SelectionState,
    fold_history,
)

# The operational shadow of the driving loops [ES-020]: this layer owns real
# time, so it emits a wall-clock SPAN for each Coordinator.drive
# — whose loop counters summarize the drive; the per-fact events between the
# started/finished pair are the kernel doors' own emits. The spans also carry
# the per-phase accumulators (candidates_ms, begin_ms, handler_ms,
# activity_ms, commit_ms, observe_ms, apply_ms): the kernel is timed FROM ITS
# CALLERS — the wall clock stays on this side of the seam, and the kernel
# stays wall-clock-free. Phase fields overlap deliberately where one phase
# contains another (apply_ms includes handler_ms/commit_ms): each answers its
# own question — totals locate the loop's cost, components locate the seam's.
log = telemetry.get_logger("impetus")


def _driver_log(instance: Instance) -> telemetry.TelemetryLogger:
    """Bind driver spans and door events to the same instance identity and net kind."""
    fields: dict[str, str] = {}
    if instance.instance_id is not None:
        fields["instance"] = instance.instance_id
    if instance.net.name is not None:
        fields["net"] = instance.net.name
    return log.bind(**fields) if fields else log


def _emit_gauges(instance_log: telemetry.TelemetryLogger, instance: Instance, **extra: object) -> None:
    """
    The profile-level state gauges [ES-020], one event per drive turn: the
    sizes bottleneck analysis correlates over time — history length, queue
    depths, in-flight count, process RSS. Cheap projections of live state
    (O(places), no history fold), gathered only when the process-wide level
    admits them; ``current_rss_mb`` is None where /proc is absent (macOS).
    """
    marking = instance.marking
    occupied = [(place, tokens) for place, tokens in marking]
    instance_log.emit(
        "gauges",
        history_records=len(instance.history),
        places_occupied=len(occupied),
        tokens_total=sum(len(tokens) for _, tokens in occupied),
        in_flight=len(instance.in_flight),
        current_rss_mb=telemetry.current_rss_mb(),
        max_rss_mb=telemetry.max_rss_mb(),
        **extra,
    )


@dataclass(frozen=True)
class Delivery:
    """
    A sensor's parcel: one external delivery for a driver to accept before
    source projection — the source transition it addresses, the tokens it
    carries, and the stable ``identity`` the ingress adapter
    extracted or constructed
    [DR 2026-07-14 source-delivery-projection-and-identity]. It admits
    ``deliver``'s spellings (a dotted string
    source, a bare token) and normalizes them at construction — the
    ``DeliveryRegistration`` identity-value shape: the declared fields are the
    canonical stored forms, equal however the parcel was spelled. A ``str``
    payload is refused where the shape is decided (it is a ``Sequence`` that
    would silently explode into characters); content validation stays the
    ingress seam's, where the delivery becomes recorded fact.
    """

    source: NetPath
    tokens: tuple[Token, ...]
    identity: str
    scope: LifecycleScope | str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", canonical_net_path(self.source, "delivery source"))
        if isinstance(self.tokens, str | bytes):
            raise ValueError(
                f"delivery to {self.source}: tokens must be a Token or a sequence of Tokens, found {self.tokens!r}"
            )
        tokens = (self.tokens,) if isinstance(self.tokens, Token) else tuple(self.tokens)
        object.__setattr__(self, "tokens", tokens)
        if type(self.identity) is DeliveryIdentity:
            object.__setattr__(self, "identity", str(self.identity))
        elif type(self.identity) is not str or not self.identity:
            raise ValueError(
                f"delivery identity must be a non-empty string of the exact built-in type, got {self.identity!r}"
            )
        if self.scope is not None and type(self.scope) not in {LifecycleScope, str}:
            raise TypeError("delivery scope must be an exact LifecycleScope, exact name string, or None")
        if type(self.scope) is str and (not self.scope or "\x00" in self.scope):
            raise ValueError("delivery scope name must be non-empty and contain no NUL")


# A sensor: a nonblocking local ingress adapter for the Coordinator. Each
# observation turn while a registration is armed, it transfers a finite batch
# of deliveries already available in process memory — or an empty sequence,
# handing control back immediately. Durable transports retain custody and use
# Engine.accept_delivery directly; the Sensor itself claims no process-crash
# durability. The sensor extracts or constructs each
# parcel's stable identity; the single writer enforces idempotent acceptance at
# the delivery door — exact redelivery reconstructs an unfinished acceptance or
# acknowledges its completed occurrence, never accepting it twice
# (2026-07-14T1806Z source-delivery decision).
type Sensor = Callable[[], Sequence[Delivery]]


class Clock(Protocol):
    """
    How the driving runtime observes time. The kernel never reads a clock —
    enablement speaks the watermark — so this is where instants come from:
    ``now`` stamps the records a driver appends. ``observe`` is the
    Coordinator's nonblocking timer read: None means the requested instant is
    still future; an observed instant is never earlier than requested.
    """

    def now(self) -> Instant: ...

    def observe(self, instant: Instant) -> Instant | None: ...


class SimulatedClock:
    """
    The shipped ``Clock``: simulated time that starts at ``at`` and advances
    when observed — ``observe`` jumps straight to the requested instant (never
    rewinding), so timed advancement remains deterministic. A wall-clock adapter belongs to a real substrate,
    outside the kernel. (Named for what it does; "virtual clock" stays the
    watermark's name [glossary].)
    """

    def __init__(self, at: Instant = 0):
        self._now = at

    def now(self) -> Instant:
        return self._now

    def observe(self, instant: Instant) -> Instant:
        self._now = max(self._now, instant)
        return self._now


def _complete_pure(
    instance: Instance,
    occurrence: FiringOccurrence,
    clock: Clock,
    span: telemetry.Span | None = None,
    commit_failure: Callable[[], None] | None = None,
) -> FiringOutcome:
    """
    Drive a begun PURE occurrence to terminal, stamped from the driver's
    clock: run the bound handler here (a pure projection executes at the
    writer, by ruling — never on an execution substrate) and commit its
    terminal outcome. A raising handler, or a result the commit rejects, is
    failed and settled through ``commit_failure`` before propagation. A
    provider refusal or acknowledgement loss at that settlement takes
    precedence; fresh load decides whether the failure committed. One home
    for the coordinator's ``BeginCandidate`` and reconcile legs.
    """
    binding = occurrence.binding
    handler = instance.bound_handler(binding.transition)
    if isinstance(handler, ActivityHandler):
        raise TypeError(f"pure firing {binding.transition} is bound to an ActivityHandler")
    outputs = instance.net.outputs(binding.transition)
    # A driver with no span (the kernel's own inline step/run has none)
    # completes untimed: timing is the driving layer's, never a requirement.
    handler_timer = span.accumulate_time("handler_ms") if span is not None else nullcontext()
    commit_timer = span.accumulate_time("commit_ms") if span is not None else nullcontext()
    try:
        with handler_timer:
            result = handler(binding, outputs)
        with commit_timer:
            return instance._commit_completion(occurrence, result, at=clock.now())
    except _CompletionCommitRefused as refusal:
        raise refusal.error
    except Exception as error:
        if occurrence in instance.in_flight:
            instance.fail(occurrence, firing_failure_text(error), at=clock.now())
            if commit_failure is not None:
                commit_failure()
        raise


# ── the asynchronous coordinator ─────────────────────────────


@dataclass(frozen=True)
class AcceptResult:
    """
    Commit one arrived activity outcome for the in-flight occurrence id
    ``occurrence``: freeze the result (``record_activity_completion``) and
    project it (``complete``) — or, when ``outcome`` is an
    ``ActivityFailure``, commit ``ActivityFailed`` + ``FiringFailed`` and
    halt the drive (stop-on-terminal-failure, the driving default). The
    action carries the id, never the live occurrence: what a policy handles
    is detached, and the coordinator resolves the id back to the
    writer-owned occurrence at apply.
    """

    occurrence: int
    outcome: object


@dataclass(frozen=True)
class AcceptDelivery:
    """Accept one sensed ``delivery`` durably, then complete only its pure source occurrence."""

    delivery: Delivery


@dataclass(frozen=True)
class BeginCandidate:
    """
    Begin the enabled ``binding``: a pure occurrence runs its projection at
    the writer and completes here; an impure occurrence freezes its
    ``ActivityRequested`` and is handed to Dispatch, left
    in flight — acknowledgement, not completion.
    """

    binding: Binding
    proposal: SelectionProposal


@dataclass(frozen=True)
class AdvanceTime:
    """Observe the pending ``next_maturation`` without blocking and land the wake append when due."""

    instant: Instant


@dataclass(frozen=True)
class Wait:
    """Hand control back to the caller: dispatched results are outstanding and nothing else can progress — pump the adapter, then drive again. The deterministic spelling of the sketch's wait-for-input."""


@dataclass(frozen=True)
class Stop:
    """End the drive. Always available: durable state is safe to leave at any committed point."""


# The invariant-preserving action vocabulary the coordinator owns: everything
# a driving policy may choose is one of these, and only the coordinator
# applies one [ES-012 session 3].
type Action = AcceptResult | AcceptDelivery | BeginCandidate | AdvanceTime | Wait | Stop


@dataclass(frozen=True)
class InFlightView:
    """
    A policy's detached view of one in-flight occurrence: the ``occurrence``
    id, the ``transition``, the ``consumed`` selections (the throughput
    policy's structural-independence input), and the purity judgment —
    ``impure`` is whether it carries an activity invocation. Deliberately
    NOT the live ``FiringOccurrence``: observation hands out no path to the
    writer's canonical state (an invocation's recorded input, the begin
    records), and ids resolve back to writer-owned occurrences only inside
    the coordinator. Token values inside the selections still alias their
    ``data`` mappings — the same documented aliasing posture as token data
    everywhere else (the ``petrus.impetus.history.codec`` JSON-faithful constraint);
    payload deep-freezing is deliberately not this seam's.
    """

    occurrence: int
    transition: NetPath
    consumed: tuple[Selection, ...]
    impure: bool


@dataclass(frozen=True)
class Snapshot:
    """
    What a driving policy observes, taken by the coordinator each loop turn:
    the available ``actions`` — the vocabulary above, in deterministic order
    (arrived results in arrival order, at most one candidate selected from
    deterministic Petrinet enumeration,
    time, buffered deliveries FIFO, then ``Wait``/``Stop``) — and the
    ``in_flight`` views a policy's independence judgment reads (the
    throughput policy checks a candidate's consumed selections against them),
    and the previously applied live action used by the shipped policies for
    bounded ingress alternation. A policy chooses among ``actions`` only; the
    coordinator refuses anything else.
    """

    actions: tuple[Action, ...]
    in_flight: tuple[InFlightView, ...]
    previous: Action | None = None


# A driving policy: choose exactly one of the snapshot's available actions.
# Policies compose over available actions (admission, priority, selection,
# tie-breaking) and need not replay deterministically — CandidateSelected
# records the committed choice, and replay reconstructs the fact rather than
# rerunning the policy [ES-012 session 3].
type DrivingPolicy = Callable[[Snapshot], Action]


@dataclass(frozen=True)
class DriveOutcome:
    """
    Why one ``drive()`` returned, and what it committed: ``firings`` in
    commit order (reconciled completions included), and ``waiting`` — True
    when the loop returned on ``Wait`` (dispatched results outstanding:
    pump the adapter, drive again — a polling driver's re-drive signal),
    False when it returned on ``Stop`` (quiescence, or the policy's own
    decision). ``ready`` asks the host to re-drive after the one-action turn;
    ``next_maturation`` is the post-turn deadline on every return.
    """

    firings: tuple[FiringOutcome, ...]
    waiting: bool
    ready: bool = False
    next_maturation: Instant | None = None


# Complexity exception (11): reviewed as one ordered fairness/priority policy;
# splitting its precedence would make the public policy contract harder to audit.
def choose_conservative(snapshot: Snapshot) -> Action:  # noqa: C901
    """
    Commit each arrived result before anything else (arrival order), then give
    one pending delivery interrupt priority. After a delivery, eligible
    candidate/time work progresses before another delivery. Wait is not
    progress: buffered ingress remains acceptable while an Activity result is
    outstanding, but no second candidate begins. Stop at quiescence.
    """
    for action in snapshot.actions:
        if isinstance(action, AcceptResult):
            return action
    delivery = next((action for action in snapshot.actions if isinstance(action, AcceptDelivery)), None)
    if delivery is not None and not isinstance(snapshot.previous, AcceptDelivery):
        return delivery
    wait = next((action for action in snapshot.actions if isinstance(action, Wait)), None)
    if wait is not None:
        return delivery if delivery is not None else wait
    for kind in (BeginCandidate, AdvanceTime):
        for action in snapshot.actions:
            if isinstance(action, kind):
                return action
    if delivery is not None:
        return delivery
    for action in snapshot.actions:
        if isinstance(action, Stop):
            return action
    raise ValueError("no available action: the coordinator always offers Stop")


def choose_throughput(snapshot: Snapshot) -> Action:
    """
    The concurrency demonstrator: begin every structurally independent
    candidate before accepting results, so independent occurrences
    interleave in flight. A candidate whose consumed selections collide by
    value with an in-flight occurrence's is SKIPPED: selections are by value
    [the DS1 value-aliasing invariant], so the offered twin of a spent
    selection is evidence this policy cannot tell apart — it waits for
    results instead of forcing a begin that fails loud as stale. Then
    results in arrival order, time, ingress, wait, stop.
    """
    delivery = next((action for action in snapshot.actions if isinstance(action, AcceptDelivery)), None)
    if delivery is not None and not isinstance(snapshot.previous, AcceptDelivery):
        return delivery
    spent = [(place, token) for view in snapshot.in_flight for place, tokens in view.consumed for token in tokens]
    for action in snapshot.actions:
        if isinstance(action, BeginCandidate) and not any(
            (place, token) in spent for place, tokens in action.binding.consumed for token in tokens
        ):
            return action
    for kind in (AcceptResult, AdvanceTime, AcceptDelivery, Wait, Stop):
        for action in snapshot.actions:
            if isinstance(action, kind):
                return action
    raise ValueError("no available action: the coordinator always offers Stop")


class Coordinator:
    """
    The asynchronous coordinator over one instance [ES-012 session 3,
    §Asynchronous coordination and composable policy]: the deterministic
    drive loop where dispatch acknowledgement and completion are different
    events. Each call observes a ``Snapshot`` (collecting the adapter's
    arrived completions, enumerating candidates, deriving the pending
    maturation, and nonblockingly consulting the local ``sensor``), the
    ``policy`` chooses one available action, and the coordinator applies at
    most that one action against the single writer, stamping from its
    ``clock``. ``drive()`` returns a ``DriveOutcome`` telling its host to
    re-drive, wait for a result, schedule a maturation, or stop.

    The first drive reconciles before anything begins (session-3 gap 4,
    ruled into this slice): every in-flight invocation without a frozen
    result is redispatched from the recorded outbox — the rebuilt
    ``occurrence.invocation``, never a re-run ``prepare`` — each
    projection-pending occurrence completes by projection alone, and pure
    in-flight occurrences are driven to terminal. A terminal activity
    failure is committed (``ActivityFailed`` + ``FiringFailed``) and halts
    the drive loud — stop-on-terminal-failure, the driving default; in-flight
    siblings stay durable for the next reconcile. A projection failure
    propagates with the occurrence left projection-pending: that state is
    fix-the-code-and-resume, and this coordinator will not retry it in-loop.
    """

    def __init__(
        self,
        instance: Instance,
        dispatch: Dispatch,
        *,
        policy: DrivingPolicy = choose_conservative,
        selection: SelectionPolicy = SelectionPipeline(),
        clock: Clock | None = None,
        sensor: Sensor | None = None,
        commit: Callable[[], None] | None = None,
    ):
        self.instance = instance
        self._dispatch = dispatch
        self._policy = policy
        self._selection = selection
        self._selection_state: SelectionState = fold_history(selection, None, instance.history)
        self._clock = clock if clock is not None else SimulatedClock(at=instance.watermark)
        self._sensor = sensor
        # The joined-transaction commit point [convention 71; D11]: a backend
        # that joins a caller-held transaction (PostgresHistoryStore in join
        # mode, sharing its connection with Dispatch) needs the
        # driver to say when a fact set is whole. The hook marks BOTH ruled
        # atomicity shapes: dispatch-side, a BeginCandidate's begin batch,
        # task spawn, and dispatch doorbell commit or vanish as ONE;
        # completion-side, the freeze (record_activity_completion) and the
        # projection (complete) are TWO boundaries — the frozen result
        # commits first and survives a projection crash [DR 2026-07-14
        # activity-invocation-runtime-seam]. Source delivery likewise commits
        # acceptance before its pure projection. Also called after reconcile,
        # after a terminal-failure fail() before its halt propagates (the
        # recorded failure must outlive the raise), and before drive()
        # returns (no idle transaction is left open across a Wait). None for
        # backends that own their transactions (in-memory, JSONL, autocommit
        # Postgres), where every append is already durable at the door.
        self._commit = commit
        # Arrived-but-unaccepted completions and sensed-but-unaccepted
        # deliveries: buffered here in arrival order — collect() drains the
        # adapter, and what a policy has not chosen yet must keep being
        # offered. The dispatched map keeps every occurrence this
        # coordinator handed the adapter, ended ones included: it is how a
        # late completion resolves back to the occurrence the ended
        # acknowledgement door judges.
        self._arrived: list[tuple[int, object]] = []
        self._deliveries: list[Delivery] = []
        # Every canonical Activity occurrence is resolvable here, including
        # ended occurrences rebuilt after restart. Dispatch redelivery may
        # therefore reach Instance's exact acknowledge-or-conflict terminal
        # door without granting an old result any path back into live state.
        self._dispatched: dict[int, FiringOccurrence] = dict(instance.activity_occurrences)
        if any(occurrence.invocation is not None for occurrence in instance.cancelled) and not isinstance(
            dispatch, CancellableDispatch
        ):
            raise TypeError(
                "cannot load lifecycle-cancelled Activities with this Dispatch: it does not implement "
                "the recoverable cancellation extension"
            )
        self._reconciled = False
        self._previous: Action | None = None
        self._log = _driver_log(instance)

    def drive(self) -> DriveOutcome:
        """Reconcile once, then observe → choose → apply at most one normal action and return its host posture."""
        firings: list[FiringOutcome] = []
        with self._log.span("drive") as span:
            if not self._reconciled:
                # Flagged before the work: reconcile's legs are safe to leave
                # half-done (durable state answers the next resume) but not to
                # repeat in-process — a second pass would double-dispatch into
                # the same adapter. A failure that propagates out of reconcile
                # is operator territory: fix the code, resume fresh.
                self._reconciled = True
                self._reconcile(firings, span)
                self._committed()
                span.set(reconciled_firings=len(firings))
            with span.accumulate_time("observe_ms"):
                snapshot = self._observe()
            action = self._policy(snapshot)
            if action not in snapshot.actions:
                raise ValueError(f"the policy chose an action the coordinator did not offer: {action!r}")
            while True:
                if isinstance(action, (Wait, Stop)):
                    # Close the observation's read transaction too: nothing
                    # may idle open across a Wait the driver blocks on.
                    self._committed()
                    waiting = isinstance(action, Wait)
                    span.set(firings=len(firings), waiting=waiting, ready=False)
                    return DriveOutcome(tuple(firings), waiting, next_maturation=self.instance.next_maturation)
                before_action = len(self.instance.history)
                with span.accumulate_time("apply_ms"):
                    proposal, applied = self._apply(action, firings, span)
                if applied:
                    break
                # A wall Clock can reveal that a selected AdvanceTime is not
                # due without mutating state. It cannot consume the fairness
                # turn or hide another action that can progress now, so let
                # the policy choose once more without that unavailable offer.
                snapshot = Snapshot(
                    tuple(offered for offered in snapshot.actions if offered != action),
                    snapshot.in_flight,
                    snapshot.previous,
                )
                action = self._policy(snapshot)
                if action not in snapshot.actions:
                    raise ValueError(f"the policy chose an action the coordinator did not offer: {action!r}")
            span.increment("actions")
            if not isinstance(action, AcceptDelivery) or len(self.instance.history) != before_action:
                self._committed()
            if proposal is not None:
                self._install_selection(proposal)
            self._previous = action
            if telemetry.at_level("profile"):
                _emit_gauges(self._log, self.instance)
            span.set(firings=len(firings), waiting=False, ready=True)
            return DriveOutcome(tuple(firings), False, ready=True, next_maturation=self.instance.next_maturation)

    def _reconcile(self, firings: list[FiringOutcome], span: telemetry.Span) -> None:
        """
        Reconcile-then-drive [session-3 gap 4]: redispatch the outbox,
        complete the projection-pending by projection alone, drive pure
        in-flight to terminal — in that order, each leg over the resumed
        in-flight set in begin order. This is the coordinator's second
        writer phase, explicitly beside ``_apply``: reconcile runs before
        any action is offered, and both phases belong to the one component
        allowed to mutate the instance.
        """
        self._reconcile_cancellations()
        in_flight = self.instance.in_flight
        pending = {occurrence.id for occurrence in self.instance.projection_pending}
        for occurrence in in_flight:
            if occurrence.invocation is not None and occurrence.id not in pending:
                # The outbox scan: invocation frozen, no terminal activity
                # fact — republish the recorded request; prepare never
                # re-runs [DR 2026-07-14 activity-invocation-runtime-seam].
                self._dispatched[occurrence.id] = occurrence
                self._dispatch.dispatch(occurrence.id, occurrence.invocation)
        for occurrence in in_flight:
            if occurrence.invocation is not None and occurrence.id in pending:
                frozen = self.instance.pending_activity_outcomes[occurrence.id]
                if isinstance(frozen, ActivityFailure):
                    handler = self.instance.bound_handler(occurrence.binding.transition)
                    underlying = getattr(handler, "handler", handler)
                    if not callable(getattr(underlying, "project_failure", None)):
                        self.instance.fail(occurrence, frozen, at=self._clock.now())
                        self._committed()
                        raise RuntimeError(
                            f"activity for firing occurrence {occurrence.id} ({occurrence.binding.transition}) "
                            f"failed terminally: {frozen.error}"
                        )
                firings.append(self.instance.complete(occurrence, at=self._clock.now()))
        for occurrence in in_flight:
            if occurrence.invocation is None:
                firings.append(
                    _complete_pure(
                        self.instance,
                        occurrence,
                        self._clock,
                        span=span,
                        commit_failure=self._committed,
                    )
                )

    def _reconcile_cancellations(self) -> None:
        """Repair canonical close/reset instructions before republishing live outbox work."""
        positions = replay_cancellation_positions(self.instance.history)
        for occurrence in self.instance.cancelled:
            if occurrence.invocation is not None:
                self._cancel(occurrence, positions[occurrence.id])

    # Complexity exception: reviewed as one ordered observation/action projection.
    def _observe(self) -> Snapshot:  # noqa: C901
        """One turn's snapshot: drain the adapter, resolve each buffered completion by occurrence id at the writer, then compute the available actions in deterministic order."""
        in_flight = self.instance.in_flight
        by_id = {occurrence.id: occurrence for occurrence in in_flight}
        self._arrived.extend(self._dispatch.collect())
        # The collect resolution, by occurrence id: in-flight completions
        # become AcceptResult actions; a late RESULT for an occurrence this
        # coordinator dispatched that has since ENDED goes through the
        # result-ingress door's ended-acknowledgement — a canonical-equal
        # redelivery is acknowledged quietly and the loop continues, a
        # different one conflicts loud; anything else (never dispatched, or
        # a late failure) is a driver bug, refused loud.
        remaining: list[tuple[int, object]] = []
        actions: list[Action] = []
        for occurrence_id, outcome in self._arrived:
            if occurrence_id in by_id:
                remaining.append((occurrence_id, outcome))
                actions.append(AcceptResult(occurrence_id, outcome))
                continue
            dispatched = self._dispatched.get(occurrence_id)
            if dispatched is not None:
                if isinstance(outcome, ActivityFailure):
                    self.instance.record_activity_failure(dispatched, outcome, at=self._clock.now())
                else:
                    self.instance.record_activity_completion(dispatched, outcome, at=self._clock.now())
                continue
            raise ValueError(
                f"the Dispatch completed occurrence {occurrence_id}, which is not in flight: "
                f"a Dispatch answers only for invocations its coordinator dispatched"
            )
        self._arrived = remaining
        enabled = tuple(self.instance.candidates())
        if enabled:
            proposal = self._selection.propose(enabled, self._selection_state)
            if proposal is not None:
                if proposal.binding not in enabled:
                    raise ValueError("candidate selection proposed a binding outside the enabled offer")
                if proposal.prior_state != self._selection_state:
                    raise ValueError("candidate selection proposal does not carry the live prior state")
                actions.append(BeginCandidate(proposal.binding, proposal))
            else:
                self._log.emit("candidate_selection_declined", enabled=len(enabled))
        maturation = self.instance.next_maturation
        if maturation is not None:
            actions.append(AdvanceTime(maturation))
        arrived_ids = {occurrence_id for occurrence_id, _ in self._arrived}
        frozen = {occurrence.id for occurrence in self.instance.projection_pending}
        outstanding = any(
            occurrence.invocation is not None and occurrence.id not in arrived_ids and occurrence.id not in frozen
            for occurrence in in_flight
        )
        armed = self.instance.armed
        if not self._deliveries and self._sensor is not None and armed:
            # Coordinator sensing is an observation, not a wait: only already-
            # available local deliveries belong here. The answer is
            # snapshotted before judgment and None is refused loud.
            answer = self._sensor()
            if answer is None:
                raise ValueError(
                    "sensor returned None: a sensor answers with a sequence of deliveries — empty to decline"
                )
            parcels = tuple(answer)
            if any(type(parcel) is not Delivery for parcel in parcels):
                raise TypeError("sensor must return exact Delivery values")
            self._deliveries.extend(parcels)
        # Preserve Sensor FIFO. If an earlier action closed a buffered parcel's
        # source, hold it and everything behind it until that source re-arms
        # rather than offering an action the writer would refuse.
        for delivery in self._deliveries:
            if delivery.source not in armed:
                break
            actions.append(AcceptDelivery(delivery))
        if outstanding:
            actions.append(Wait())
        actions.append(Stop())
        views = tuple(
            InFlightView(
                occurrence.id,
                occurrence.binding.transition,
                occurrence.binding.consumed,
                occurrence.invocation is not None,
            )
            for occurrence in in_flight
        )
        return Snapshot(tuple(actions), views, self._previous)

    # Complexity exception (11): reviewed as the one single-writer Action
    # dispatcher; its cases share transaction and selection-fate boundaries.
    def _apply(  # noqa: C901
        self, action: Action, firings: list[FiringOutcome], span: telemetry.Span
    ) -> tuple[SelectionProposal | None, bool]:
        """Apply one chosen action against the single writer — the only site that does. Actions reference occurrences by id; the writer-owned occurrence resolves here, never in a policy's hands."""
        match action:
            case AcceptResult(occurrence=occurrence_id, outcome=outcome):
                occurrence = next(held for held in self.instance.in_flight if held.id == occurrence_id)
                # Unbuffered before the writer commits: if the freeze itself
                # fails (an IO refusal), the arrival is spent — recovery is
                # resume-fresh, where the durable outbox redispatches.
                self._unbuffer_arrival(occurrence_id)
                if isinstance(outcome, ActivityFailure):
                    self.instance.record_activity_failure(occurrence, outcome, at=self._clock.now())
                    self._committed()
                    handler = self.instance.bound_handler(occurrence.binding.transition)
                    underlying = getattr(handler, "handler", handler)
                    projects = callable(getattr(underlying, "project_failure", None))
                    if projects:
                        firings.append(self.instance.complete(occurrence, at=self._clock.now()))
                    else:
                        self.instance.fail(occurrence, outcome, at=self._clock.now())
                    # The recorded failure is a whole fact: on a joined
                    # transaction it must commit before the halt propagates —
                    # the raise below is the driver's policy, never a rollback.
                    self._committed()
                    if projects:
                        return None, True
                    raise RuntimeError(
                        f"activity for firing occurrence {occurrence.id} ({occurrence.binding.transition}) "
                        f"failed terminally: {outcome.error}"
                    )
                self.instance.record_activity_completion(occurrence, outcome, at=self._clock.now())
                # The freeze is its own durability boundary [DR 2026-07-14
                # activity-invocation-runtime-seam: ActivityCompleted commits
                # BEFORE deterministic projection]: on a joined transaction
                # the frozen result must survive a projection crash — one
                # merged commit would roll the freeze back with the failed
                # projection and force re-executing completed external work.
                self._committed()
                firings.append(self.instance.complete(occurrence, at=self._clock.now()))
                return None, True
            case AcceptDelivery(delivery=delivery):
                position = next(index for index, buffered in enumerate(self._deliveries) if buffered is delivery)
                del self._deliveries[position]
                before_acceptance = len(self.instance.history)
                accepted = self.instance.accept_delivery(
                    delivery.source,
                    delivery.tokens,
                    at=self._clock.now(),
                    identity=delivery.identity,
                    scope=delivery.scope,
                )
                if isinstance(accepted, AcceptedDelivery):
                    # The accepted identity and begun source occurrence are a
                    # complete durability cut. A fresh acceptance settles
                    # before projection; exact reconstruction appends nothing
                    # and therefore needs no empty provider commit.
                    if len(self.instance.history) != before_acceptance:
                        self._committed()
                    before = len(self.instance.history)
                    try:
                        firings.append(self.instance.complete_delivery(accepted, at=self._clock.now()))
                    except Exception:
                        records = self.instance.history.records
                        if (
                            len(records) == before + 1
                            and isinstance(records[-1], FiringFailed)
                            and records[-1].occurrence == accepted.occurrence
                        ):
                            self._committed()
                        raise
                return None, True
            case BeginCandidate(binding=binding, proposal=proposal):
                with span.accumulate_time("begin_ms"):
                    occurrence = self.instance.begin(binding, at=self._clock.now())
                # Backend-owned histories make begin durable at the append
                # door. Install immediately: dispatch and pure completion are
                # later operations and cannot erase that committed selection.
                # A joined backend instead keeps begin+dispatch in one caller
                # transaction; its proposal is returned for commit-then-install.
                if self._commit is None:
                    self._install_selection(proposal)
                if occurrence.invocation is None:
                    firings.append(
                        _complete_pure(
                            self.instance,
                            occurrence,
                            self._clock,
                            span=span,
                            commit_failure=self._committed,
                        )
                    )
                else:
                    self._dispatched[occurrence.id] = occurrence
                    self._dispatch.dispatch(occurrence.id, occurrence.invocation)
                return (proposal if self._commit is not None else None), True
            case AdvanceTime(instant=instant):
                observed = self._clock.observe(instant)
                if observed is None:
                    return None, False
                if observed < instant:
                    # A broken Clock contract, refused over repeatedly
                    # scheduling an instant the Clock claimed to observe.
                    raise ValueError(
                        f"clock observed {observed}, before the requested maturation {instant}: "
                        f"observe must return None or an instant at least as late as requested"
                    )
                self.instance.wake(observed)
                return None, True
            case Wait() | Stop():
                raise ValueError(f"cannot apply non-mutating host posture {action!r}")

    def _committed(self) -> None:
        """Invoke the joined-transaction commit point, when one was supplied — the one home of when a driven fact set is whole."""
        if self._commit is not None:
            self._commit()

    @property
    def supports_cancellation(self) -> bool:
        """Whether this composition can fence lifecycle-cancelled Activities."""
        return isinstance(self._dispatch, CancellableDispatch)

    def cancel(self, closure: ScopeClosure, history_position: int) -> tuple[CancellationDisposition, ...]:
        """Install exact operational fences after the caller committed the canonical close/reset."""
        cancelled = {occurrence.id: occurrence for occurrence in self.instance.cancelled}
        dispositions = []
        for occurrence_id in closure.cancelled:
            occurrence = cancelled[occurrence_id]
            if occurrence.invocation is not None:
                dispositions.append(self._cancel(occurrence, history_position))
        return tuple(dispositions)

    def _cancel(self, occurrence: FiringOccurrence, history_position: int) -> CancellationDisposition:
        if not isinstance(self._dispatch, CancellableDispatch):
            raise TypeError(
                "cannot cancel lifecycle-scoped Activity: this Dispatch does not implement the recoverable "
                "cancellation extension"
            )
        assert occurrence.invocation is not None
        self._dispatched[occurrence.id] = occurrence
        disposition = self._dispatch.cancel(
            CancellationInstruction(occurrence.id, occurrence.invocation, history_position)
        )
        self._log.emit(
            "activity_cancelled",
            occurrence=occurrence.id,
            history_position=history_position,
            disposition=disposition.value,
        )
        return disposition

    def _install_selection(self, proposal: SelectionProposal) -> None:
        """Install a proposal only at the durability boundary that earned it."""
        if self._selection_state != proposal.prior_state:
            raise RuntimeError(
                "selection state changed before its begin commit: the proposal prior state no longer matches"
            )
        self._selection_state = proposal.next_state

    def _unbuffer_arrival(self, occurrence_id: int) -> None:
        """Remove the accepted completion — the first buffered arrival for this occurrence — so the next observe offers only what is still unaccepted."""
        for index, (arrived_id, _) in enumerate(self._arrived):
            if arrived_id == occurrence_id:
                del self._arrived[index]
                return
