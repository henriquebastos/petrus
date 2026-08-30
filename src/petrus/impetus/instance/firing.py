"""
Instance firing: the durable begin/end occurrence lifecycle and conservative scheduler.
The handler contract and passthrough default live in ``petrus.impetus.binding``.

A firing is a durable **occurrence** [ADR 0007; DR 2026-07-14
activity-invocation-runtime-seam — "attempt" now names the execution
adapter's operational retries, never this lifecycle]: ``begin_firing``
accounts the binding's input tokens — accounting at begin is what keeps
duplicate workers off one consumed token — and ``complete_firing`` commits the successful
outcome, depositing the handler-supplied tokens per output arc contract
(terminal failure moves no tokens; its record is the instance's). Between the
two, an execution runtime runs the handler however it likes — inline, retried,
on another worker; retries never reach the net, only the terminal result does.
Both halves are history-independent marking transforms in ``petrus.impetus.petrinet``.
The Instance narrates their movement effects as records and is the single
writer that appends them; the initiating site appends its own initiation record
(scheduler selection or external event) first. This module retains only the
Instance-owned occurrence values and replay folds.

A ``Handler`` receives the firing binding and the transition's output arcs and
returns a ``HandlerResult`` envelope — output tokens keyed by destination,
plus the delivery-registration effects the result carries — or, legal sugar for the
common all-tokens case, the bare token mapping alone; end firing deposits
only tokens whose color and destination match an output arc, and drops the
rest silently (Navigator ruling: the validation run and the type layer own
declaration typos, not end firing). A plain callable bound to a symbol is a
PURE deterministic projection — its effects ARE the projection, and its
firing carries no activity records. Impurity has exactly one spelling: an
``ActivityHandler``, the server-side Petri-aware bridge that ``prepare``s one
Petri-agnostic ``ActivityInvocation`` from the binding and later ``project``s
the frozen activity result into the same ``HandlerResult`` envelope
[DR 2026-07-14 activity-invocation-runtime-seam; DR 2026-07-14
source-delivery-projection-and-identity — the refined classification]. The
purity judgment is the binding layer's (is the bound implementation an
ActivityHandler?); it is never re-derived here.
"""

from __future__ import annotations

# Python imports
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass

# Internal imports
from petrus.motus.activity import ActivityFailure, ActivityInvocation
from petrus.impetus.history import (
    ActivityCompleted,
    ActivityFailed,
    ActivityRequested,
    ActivityTerminalQuarantined,
    CandidateSelected,
    DeliveryRegistration,
    ExternalEventDelivered,
    FiringBegun,
    FiringCompleted,
    FiringFailed,
    Record,
    ScopeClosed,
    ScopeReset,
    DeliveryRegistrationClosed,
    DeliveryRegistrationOpened,
    TokensConsumed,
    TokensProduced,
    TokensRead,
)
from petrus.impetus.binding import HandlerResult
from petrus.impetus.petrinet import Binding, Instant, Marking, Net, NetPath, Token
from petrus.impetus.petrinet import firing as _petrinet_firing
from petrus.impetus.scope import LifecycleScope


@dataclass(frozen=True)
class FiringOccurrence:
    """
    A durable firing occurrence: a binding whose begin has been recorded — its
    input tokens accounted — and whose end (completion or terminal failure)
    has not. ``records`` is the occurrence's durable begin (``FiringBegun`` +
    ``TokensConsumed`` + ``TokensRead`` and, for an impure occurrence, its
    ``ActivityRequested`` — all carrying the begin instant); the initiation
    record that minted ``id`` is the initiating site's. ``invocation`` is the
    resolved activity invocation the begin batch froze — ``None`` spells a
    pure occurrence honestly, and resume rebuilds the value from the
    ``ActivityRequested`` record, never by re-running ``prepare``. In-flight
    occurrences are a projection of the history — begun without ended — never
    independent truth.
    """

    id: int
    binding: Binding
    records: tuple[Record, ...]
    invocation: ActivityInvocation | None = None
    scope: LifecycleScope | None = None


@dataclass(frozen=True)
class FiringOutcome:
    """
    The outcome of one completed firing: what fired (and under which occurrence),
    the tokens it consumed and produced, and the firing's lifecycle records
    (begin -> consume -> read -> [activity requested] -> produce ->
    [registration closes/opens] -> complete; an impure occurrence's frozen
    ``ActivityCompleted`` sits between the batches, its own append). The
    initiation record — the scheduler's selection or a delivery's external
    event — is the initiating site's, appended before these. A source firing
    consumes nothing; its delivered tokens live in the external-event record.
    """

    transition: NetPath
    occurrence: int
    consumed: tuple[Token, ...]
    produced: tuple[tuple[NetPath, Token], ...]
    records: tuple[Record, ...]


# A scheduler policy: choose which enabled candidate begins firing now, or
# None to decline — the driver's decision, never the net's [ADR 0008].
type Scheduler = Callable[[list[Binding]], Binding | None]


def select_conservative(bindings: list[Binding]) -> Binding | None:
    """Conservative deterministic single-step: the first binding in stable order."""
    return bindings[0] if bindings else None


def begin_firing(
    marking: Marking, binding: Binding, occurrence: int, instant: Instant
) -> tuple[Marking, tuple[Record, ...]]:
    """Preserve the Instance-layer begin contract while delegating all movement semantics to Petrinet."""
    effects, marking = _petrinet_firing.begin_firing(marking, binding)
    records: list[Record] = [FiringBegun(binding.transition, occurrence=occurrence, instant=instant)]
    for effect in effects:
        if isinstance(effect, _petrinet_firing.ConsumedTokens):
            records.append(TokensConsumed(effect.place, effect.tokens, occurrence=occurrence, instant=instant))
        elif isinstance(effect, _petrinet_firing.ReadTokens):
            records.append(TokensRead(effect.place, effect.tokens, occurrence=occurrence, instant=instant))
        else:
            raise TypeError(f"unknown Petrinet begin effect: {effect!r}")
    return marking, tuple(records)


def replay_in_flight(history) -> tuple[FiringOccurrence, ...]:
    """
    Rebuild the firing occurrences begun and not ended — the in-flight
    projection over recorded facts, in begin order, as real ``FiringOccurrence``
    values a driver can ``complete()`` or ``fail()``. Four named steps: sort
    the records into the occurrence lifecycle's buckets
    (``_sorted_lifecycle``), select begun-without-ended, refuse torn commit
    batches (``_refuse_torn_batch``) and disordered begin batches
    (``_refuse_disordered_begin_batch``), rebuild each surviving
    occurrence's binding from its own records (``_rebuilt_occurrence``).

    An initiation with no begun boundary (a partially persisted batch) is
    not in flight: nothing was accounted; only its minted id remains a fact
    — which is why selection iterates the begun bucket, never the initiated
    one. A rebuilt binding carries the exact recorded read selections (the
    ``TokensRead`` records of its begin batch), so a handler observes across
    a crash exactly what it observed before it — never the live marking; an
    impure occurrence's invocation rebuilds from its ``ActivityRequested``
    record the same way — ``prepare`` is never re-run.
    """
    initiated, begun, ended, ending, _ = _sorted_lifecycle(history)
    # Select: in flight = begun without ended, in begin order.
    in_flight = {occurrence_id: records for occurrence_id, records in begun.items() if occurrence_id not in ended}
    occurrences = []
    for occurrence_id, records in in_flight.items():
        transition, delivered = initiated[occurrence_id]
        _refuse_torn_batch(occurrence_id, transition, ending)
        _refuse_disordered_begin_batch(occurrence_id, transition, records)
        occurrences.append(_rebuilt_occurrence(occurrence_id, transition, delivered, records))
    return tuple(occurrences)


def replay_firing_occurrences(history, occurrence_ids: set[int]) -> tuple[FiringOccurrence, ...]:
    """Rebuild the named begun occurrences, including ended ones, for authority validation."""
    initiated, begun, ended, ending, _ = _sorted_lifecycle(history)
    occurrences = []
    for occurrence_id, records in begun.items():
        if occurrence_id not in occurrence_ids:
            continue
        transition, delivered = initiated[occurrence_id]
        if occurrence_id not in ended:
            _refuse_torn_batch(occurrence_id, transition, ending)
        _refuse_disordered_begin_batch(occurrence_id, transition, records)
        occurrences.append(_rebuilt_occurrence(occurrence_id, transition, delivered, records))
    return tuple(occurrences)


def replay_projection_pending(history) -> dict[int, object]:
    """
    The frozen terminal activity results of in-flight occurrences —
    ``ActivityCompleted`` committed, firing not ended: the projection-pending
    shape [DR 2026-07-14 activity-invocation-runtime-seam]. A driver
    ``complete()``s these by retrying deterministic projection alone; the
    activity is never re-invoked. Deliberately NOT a torn batch:
    ``ActivityCompleted`` commits as its own append, by design, so a frozen
    result over an open firing is a resumable fact, never divergence.
    """
    _, begun, ended, _, frozen = _sorted_lifecycle(history)
    return {
        occurrence_id: result
        for occurrence_id, result in frozen.items()
        if occurrence_id in begun and occurrence_id not in ended
    }


def replay_terminal_activity(history) -> dict[int, object]:
    """
    The terminal-result index of ENDED impure occurrences — a projection of
    the ``ActivityCompleted``/``ActivityFailed`` records over occurrences
    whose firing has a terminal boundary: the frozen result for a completed
    activity, an ``ActivityFailure`` for a failed one. This is what the
    result-ingress door answers an at-least-once redelivery from after the
    firing ended [DR 2026-07-14 source-delivery-projection-and-identity, the
    K6 discipline]: acknowledge-if-equal, conflict-if-different, and a failed
    occurrence cannot retroactively succeed. A frozen result whose firing has
    NOT ended is projection-pending (``replay_projection_pending``), never
    this index's.

    The fold owns its divergence rules [convention 64: a rebuilt value is
    valid only if the live writer could have written it]: the writer appends
    exactly one terminal activity fact per occurrence — the first wins, K6 —
    so a second one, in ANY combination (completed/failed, either order,
    duplicates), refuses loud rather than overwriting; and the writer
    freezes the fact before the firing's terminal boundary, so a terminal
    activity fact ordered AFTER its firing ended is equally divergence.
    """
    ended: set[int] = set()
    terminal: dict[int, object] = {}
    for record in history:
        if isinstance(record, (FiringCompleted, FiringFailed)):
            ended.add(record.occurrence)
        elif isinstance(record, (ActivityCompleted, ActivityFailed)):
            if record.occurrence in terminal:
                raise ValueError(
                    f"replay divergence: a second terminal activity fact for firing occurrence "
                    f"{record.occurrence} ({record.transition}) — the first one wins, the writer appends no second"
                )
            if record.occurrence in ended:
                raise ValueError(
                    f"replay divergence: a terminal activity fact for firing occurrence {record.occurrence} "
                    f"({record.transition}) after its firing ended — the live writer freezes the activity "
                    f"fact before the terminal boundary"
                )
            terminal[record.occurrence] = (
                record.result
                if isinstance(record, ActivityCompleted)
                else ActivityFailure(record.error, record.kind, record.details, record.retryable, record.retry_after)
            )
    return {occurrence: value for occurrence, value in terminal.items() if occurrence in ended}


def replay_quarantined_activity(history) -> dict[int, object]:
    """The first durable late-terminal outcome per lifecycle-cancelled occurrence."""
    quarantined: dict[int, object] = {}
    cancelled: dict[int, LifecycleScope] = {}
    for record in history:
        if isinstance(record, (ScopeClosed, ScopeReset)):
            scope = record.scope if isinstance(record, ScopeClosed) else record.closed
            for occurrence in record.cancelled:
                if occurrence in cancelled:
                    raise ValueError(f"replay divergence: firing occurrence {occurrence} cancelled twice")
                cancelled[occurrence] = scope
        elif isinstance(record, ActivityTerminalQuarantined):
            if cancelled.get(record.occurrence) != record.scope:
                raise ValueError(
                    f"replay divergence: terminal quarantined for firing occurrence {record.occurrence} "
                    f"outside its lifecycle cancellation"
                )
            if record.occurrence in quarantined:
                raise ValueError(
                    f"replay divergence: a second quarantined terminal for firing occurrence {record.occurrence}"
                )
            quarantined[record.occurrence] = record.outcome
    return quarantined


def replay_cancelled(history) -> tuple[FiringOccurrence, ...]:
    """Rebuild exact firing occurrences terminalized by lifecycle close/reset."""
    initiated, begun, _, _, _ = _sorted_lifecycle(history)
    cancelled: dict[int, LifecycleScope] = {}
    for record in history:
        if isinstance(record, (ScopeClosed, ScopeReset)):
            scope = record.scope if isinstance(record, ScopeClosed) else record.closed
            for occurrence_id in record.cancelled:
                if occurrence_id in cancelled:
                    raise ValueError(f"replay divergence: firing occurrence {occurrence_id} cancelled twice")
                cancelled[occurrence_id] = scope
    occurrences = []
    for occurrence_id, scope in cancelled.items():
        if occurrence_id not in begun or occurrence_id not in initiated:
            raise ValueError(f"replay divergence: cancelled firing occurrence {occurrence_id} was not begun")
        transition, delivered = initiated[occurrence_id]
        occurrence = _rebuilt_occurrence(occurrence_id, transition, delivered, begun[occurrence_id])
        if occurrence.scope != scope:
            raise ValueError(
                f"replay divergence: firing occurrence {occurrence_id} belongs to {occurrence.scope!r}, "
                f"not closing lifecycle scope {scope!r}"
            )
        occurrences.append(occurrence)
    return tuple(occurrences)


def replay_activity_occurrences(history) -> tuple[FiringOccurrence, ...]:
    """Rebuild every occurrence carrying an Activity request, ended or live."""
    initiated, begun, _, _, _ = _sorted_lifecycle(history)
    occurrences = []
    for occurrence_id, records in begun.items():
        if not any(isinstance(record, ActivityRequested) for record in records):
            continue
        if occurrence_id not in initiated:
            raise ValueError(f"replay divergence: Activity occurrence {occurrence_id} was not initiated")
        transition, delivered = initiated[occurrence_id]
        _refuse_disordered_begin_batch(occurrence_id, transition, records)
        occurrences.append(_rebuilt_occurrence(occurrence_id, transition, delivered, records))
    return tuple(occurrences)


def _refuse_late_begin_record(
    record: TokensConsumed | TokensRead | ActivityRequested,
    ending: set[int],
    ended: set[int],
) -> None:
    """Keep begin facts before every completion or terminal fact of their occurrence."""
    if record.occurrence in ended:
        raise ValueError(
            f"replay divergence: {type(record).__name__} for firing occurrence {record.occurrence} "
            "appears after its terminal boundary"
        )
    if record.occurrence in ending:
        raise ValueError(
            f"replay divergence: {type(record).__name__} for firing occurrence {record.occurrence} "
            "appears after completion began"
        )


def _validate_begin_record_position(
    record: TokensConsumed | TokensRead | ActivityRequested,
    active: tuple[int, Instant] | None,
) -> None:
    """Require one begin-tail fact to remain in its writer-owned batch."""
    if active is None or active[0] != record.occurrence:
        raise ValueError(
            f"replay divergence: {type(record).__name__} for firing occurrence {record.occurrence} "
            "does not belong to its contiguous begin batch"
        )
    if record.instant != active[1]:
        raise ValueError(
            f"replay divergence: {type(record).__name__} for firing occurrence {record.occurrence} "
            f"has instant {record.instant}, not its begin batch instant {active[1]}"
        )


def _validate_activity_record_transition(
    record: ActivityRequested | ActivityCompleted | ActivityFailed | ActivityTerminalQuarantined,
    begun: dict[int, list[Record]],
) -> None:
    """Keep every activity fact on its occurrence's begun transition."""
    boundary = begun[record.occurrence][0]
    assert isinstance(boundary, FiringBegun)
    if record.transition != boundary.transition:
        raise ValueError(
            f"replay divergence: {type(record).__name__} transition {record.transition} for firing occurrence "
            f"{record.occurrence} does not match begun transition {boundary.transition}"
        )


# Complexity exception (>15): this is a cohesive lifecycle-record fold whose
# branches mirror the closed record union; splitting it would obscure ordering.
def _sorted_lifecycle(  # noqa: C901
    history,
) -> tuple[
    dict[int, tuple[NetPath, tuple[Token, ...]]], dict[int, list[Record]], set[int], set[int], dict[int, object]
]:
    """
    Step 1 — sort the records into the occurrence lifecycle's buckets:
    ``initiated`` (the initiation's transition, and a delivery's tokens — a
    source firing selects nothing), ``begun`` (each occurrence's begin
    records: the boundary, then its consumes and reads in recorded input-arc
    order, then an impure occurrence's ``ActivityRequested``), ``ended`` (a
    terminal boundary exists), ``ending`` (end-batch records exist: produce,
    a correlated effect, or ``ActivityFailed`` — which commits only beside
    ``FiringFailed``), ``frozen`` (each occurrence's ``ActivityCompleted``
    result — NOT ending evidence: it commits alone, by design). Sorting
    validates the orderings the single writer guarantees: a begun boundary
    with no initiation; a consume, read, or activity request with no begun
    boundary; a second activity request (one recoverable activity per impure
    handler); a completion for an occurrence that requested no activity; a
    second terminal activity fact; or a lifecycle close/reset whose exact
    cancellation set differs from the open occurrences of that generation at
    that append position — each is replay divergence the live instance can
    never write.
    """
    initiated: dict[int, tuple[NetPath, tuple[Token, ...]]] = {}
    begun: dict[int, list[Record]] = {}
    ended: set[int] = set()
    ending: set[int] = set()
    frozen: dict[int, object] = {}
    scoped_open: dict[int, LifecycleScope] = {}
    lifecycle_cancelled: set[int] = set()
    active_begin: tuple[int, Instant] | None = None
    previous: Record | None = None
    for record in history:
        if not isinstance(record, (TokensConsumed, TokensRead, ActivityRequested)):
            active_begin = None
        if isinstance(record, CandidateSelected):
            if record.occurrence in initiated:
                prior, _ = initiated[record.occurrence]
                raise ValueError(
                    f"replay divergence: firing occurrence {record.occurrence} initiated more than once "
                    f"({prior} then {record.transition})"
                )
            initiated[record.occurrence] = (record.transition, ())
        elif isinstance(record, ExternalEventDelivered):
            if record.occurrence in initiated:
                prior, _ = initiated[record.occurrence]
                raise ValueError(
                    f"replay divergence: firing occurrence {record.occurrence} initiated more than once "
                    f"({prior} then {record.source})"
                )
            initiated[record.occurrence] = (record.source, record.tokens)
        elif isinstance(record, FiringBegun):
            if record.occurrence not in initiated:
                raise ValueError(
                    f"replay divergence: firing occurrence {record.occurrence} ({record.transition}) "
                    f"begun with no initiation record"
                )
            if record.occurrence in begun:
                raise ValueError(
                    f"replay divergence: firing occurrence {record.occurrence} has more than one FiringBegun record"
                )
            if not isinstance(previous, (CandidateSelected, ExternalEventDelivered)) or (
                previous.occurrence != record.occurrence
            ):
                raise ValueError(
                    f"replay divergence: FiringBegun for occurrence {record.occurrence} does not immediately "
                    "follow its initiation in the contiguous begin batch"
                )
            if previous.instant != record.instant:
                raise ValueError(
                    f"replay divergence: FiringBegun for occurrence {record.occurrence} has instant "
                    f"{record.instant}, not its initiation instant {previous.instant}"
                )
            begun[record.occurrence] = [record]
            active_begin = (record.occurrence, record.instant)
            if record.scope is not None:
                scoped_open[record.occurrence] = record.scope
        elif isinstance(record, (TokensConsumed, TokensRead)):
            if record.occurrence not in begun:
                verb = "consumed" if isinstance(record, TokensConsumed) else "read"
                raise ValueError(
                    f"replay divergence: tokens {verb} from {record.place} for firing occurrence "
                    f"{record.occurrence} with no begun boundary"
                )
            _refuse_late_begin_record(record, ending, ended)
            _validate_begin_record_position(record, active_begin)
            begun[record.occurrence].append(record)
        elif isinstance(record, ActivityRequested):
            if record.occurrence not in begun:
                raise ValueError(
                    f"replay divergence: activity {record.activity!r} requested for firing occurrence "
                    f"{record.occurrence} with no begun boundary — the request joins the begin batch"
                )
            _validate_activity_record_transition(record, begun)
            if any(isinstance(existing, ActivityRequested) for existing in begun[record.occurrence]):
                raise ValueError(
                    f"replay divergence: firing occurrence {record.occurrence} ({record.transition}) requested "
                    f"a second activity — one impure handler maps to exactly one activity"
                )
            _refuse_late_begin_record(record, ending, ended)
            _validate_begin_record_position(record, active_begin)
            begun[record.occurrence].append(record)
        elif isinstance(record, ActivityCompleted):
            requested = record.occurrence in begun and any(
                isinstance(existing, ActivityRequested) for existing in begun[record.occurrence]
            )
            if not requested:
                raise ValueError(
                    f"replay divergence: activity completed for firing occurrence {record.occurrence} "
                    f"({record.transition}) but no activity was requested in its begin batch"
                )
            _validate_activity_record_transition(record, begun)
            if record.occurrence in frozen:
                raise ValueError(
                    f"replay divergence: a second terminal activity fact for firing occurrence "
                    f"{record.occurrence} ({record.transition}) — the first one wins, the writer appends no second"
                )
            if record.occurrence in lifecycle_cancelled:
                raise ValueError(
                    f"replay divergence: activity completed for lifecycle-cancelled firing occurrence "
                    f"{record.occurrence} ({record.transition}) — late terminal reports are quarantined"
                )
            frozen[record.occurrence] = record.result
        elif isinstance(record, ActivityFailed):
            requested = record.occurrence in begun and any(
                isinstance(existing, ActivityRequested) for existing in begun[record.occurrence]
            )
            if not requested:
                raise ValueError(
                    f"replay divergence: activity failed for firing occurrence {record.occurrence} "
                    f"({record.transition}) but no activity was requested in its begin batch"
                )
            _validate_activity_record_transition(record, begun)
            if record.occurrence in frozen:
                raise ValueError(
                    f"replay divergence: a second terminal activity fact for firing occurrence "
                    f"{record.occurrence} ({record.transition})"
                )
            if record.occurrence in lifecycle_cancelled:
                raise ValueError(
                    f"replay divergence: activity failed for lifecycle-cancelled firing occurrence "
                    f"{record.occurrence} ({record.transition}) — late terminal reports are quarantined"
                )
            frozen[record.occurrence] = ActivityFailure(
                record.error, record.kind, record.details, record.retryable, record.retry_after
            )
        elif isinstance(record, ActivityTerminalQuarantined):
            if record.occurrence not in begun:
                raise ValueError(
                    f"replay divergence: terminal quarantined for firing occurrence {record.occurrence} "
                    "with no begun boundary"
                )
            _validate_activity_record_transition(record, begun)
        elif isinstance(record, (ScopeClosed, ScopeReset)):
            scope = record.scope if isinstance(record, ScopeClosed) else record.closed
            expected = tuple(occurrence for occurrence, provenance in scoped_open.items() if provenance == scope)
            if record.cancelled != expected:
                raise ValueError(
                    f"replay divergence: lifecycle close for {scope!r} cancels {record.cancelled!r}, "
                    f"but the exact open occurrence set at this append position is {expected!r}"
                )
            pending = tuple(occurrence for occurrence in expected if occurrence in frozen)
            if pending:
                raise ValueError(
                    f"replay divergence: lifecycle close for {scope!r} cancels accepted Activity "
                    f"terminal(s) {pending!r} still awaiting deterministic projection"
                )
            for occurrence in expected:
                del scoped_open[occurrence]
            lifecycle_cancelled.update(expected)
            ended.update(expected)
        elif isinstance(record, TokensProduced):
            ending.add(record.occurrence)
        elif isinstance(record, (DeliveryRegistrationOpened, DeliveryRegistrationClosed)):
            if record.occurrence is not None:
                ending.add(record.occurrence)
        elif isinstance(record, (FiringCompleted, FiringFailed)):
            if record.occurrence not in begun:
                raise ValueError(
                    f"replay divergence: firing occurrence {record.occurrence} reached "
                    f"{type(record).__name__} with no begun boundary"
                )
            boundary = begun[record.occurrence][0]
            assert isinstance(boundary, FiringBegun)
            if record.transition != boundary.transition:
                raise ValueError(
                    f"replay divergence: firing occurrence {record.occurrence} terminal transition "
                    f"{record.transition} does not match begun transition {boundary.transition}"
                )
            if record.occurrence in lifecycle_cancelled:
                raise ValueError(
                    f"replay divergence: firing occurrence {record.occurrence} reached "
                    f"{type(record).__name__} after lifecycle cancellation"
                )
            if record.occurrence in ended:
                raise ValueError(
                    f"replay divergence: firing occurrence {record.occurrence} has more than one firing terminal"
                )
            scoped_open.pop(record.occurrence, None)
            ended.add(record.occurrence)
        previous = record
    return initiated, begun, ended, ending, frozen


def _refuse_disordered_begin_batch(occurrence_id: int, transition: NetPath, records: list[Record]) -> None:
    """
    Step 3b — an OPEN occurrence's begin records must carry the live
    writer's internal batch order: the boundary, then the consumes, then the
    reads, then at most one ``ActivityRequested``, nothing after it —
    ``begin_firing`` and ``_begin_occurrence`` can emit no other shape, so a
    disordered batch is replay divergence, not material to rebuild from
    (writer/replay parity, convention 64). Scoped to open occurrences
    deliberately: ended occurrences leave no live state behind and their
    auditing is the validation-layer posture, not this door's
    (debt 2026-07-09T2310Z's kernel-wide-validation family).
    """
    ranks = {FiringBegun: 0, TokensConsumed: 1, TokensRead: 2, ActivityRequested: 3}
    # The caller has already restricted this batch to the four ranked begin-record types.
    if [ranks[type(record)] for record in records] != sorted(ranks[type(record)] for record in records):  # ty: ignore[invalid-argument-type]
        raise ValueError(
            f"replay divergence: firing occurrence {occurrence_id} ({transition}) carries a disordered "
            f"begin batch — the live writer accounts consumes, then reads, then freezes at most one "
            f"activity request"
        )


def _refuse_torn_batch(occurrence_id: int, transition: NetPath, ending: set[int]) -> None:
    """
    Step 3 — an open occurrence carrying end records has a torn commit batch:
    ``complete()`` appends the end records and the terminal boundary whole
    or not at all [convention 45], so the live instance cannot write this
    shape — replay divergence, fail loud. Rebuilding over the torn batch
    would re-execute a handler whose deposit already landed.
    """
    if occurrence_id in ending:
        raise ValueError(
            f"replay divergence: firing occurrence {occurrence_id} ({transition}) carries end records "
            f"with no terminal boundary — a torn commit batch"
        )


def _rebuilt_occurrence(
    occurrence_id: int, transition: NetPath, delivered: tuple[Token, ...], records: list[Record]
) -> FiringOccurrence:
    """Step 4 — rebuild the occurrence: the binding reassembles from its own records (the initiation supplied the transition and any delivered tokens; the ``TokensConsumed`` and ``TokensRead`` records supply the consumed and read selections in their recorded input-arc order; an ``ActivityRequested`` supplies the resolved invocation — ``prepare`` is never re-run), the begin records ride along verbatim."""
    consumed = tuple((record.place, record.tokens) for record in records if isinstance(record, TokensConsumed))
    read = tuple((record.place, record.tokens) for record in records if isinstance(record, TokensRead))
    invocation = next(
        (
            ActivityInvocation(
                record.activity,
                input=record.input,
                policy=record.policy,
                correlation=record.correlation,
                idempotency=record.idempotency,
            )
            for record in records
            if isinstance(record, ActivityRequested)
        ),
        None,
    )
    begun = next(record for record in records if isinstance(record, FiringBegun))
    if begun.transition != transition:
        raise ValueError(
            f"replay divergence: firing occurrence {occurrence_id} initiation transition {transition} "
            f"does not match begun transition {begun.transition}"
        )
    scoped_records = tuple(
        record for record in records if isinstance(record, (FiringBegun, TokensConsumed, TokensRead, ActivityRequested))
    )
    mismatched = tuple(type(record).__name__ for record in scoped_records if record.scope != begun.scope)
    if mismatched:
        raise ValueError(
            f"replay divergence: firing occurrence {occurrence_id} ({transition}) has scope provenance "
            f"inconsistent with FiringBegun on {mismatched!r}"
        )
    return FiringOccurrence(
        occurrence_id,
        Binding(transition, consumed, read, delivered=deepcopy(delivered)),
        tuple(records),
        invocation=invocation,
        scope=begun.scope,
    )


def complete_firing(
    net: Net,
    marking: Marking,
    occurrence: FiringOccurrence,
    result: HandlerResult,
    instant: Instant,
) -> tuple[Marking, FiringOutcome, tuple[Record, ...]]:
    """Preserve the Instance-layer completion contract while delegating all movement semantics to Petrinet."""
    closes = tuple(registration for registration in result.closes if isinstance(registration, DeliveryRegistration))
    opens = tuple(registration for registration in result.opens if isinstance(registration, DeliveryRegistration))
    if len(closes) != len(result.closes) or len(opens) != len(result.opens):
        raise TypeError("delivery-registration effects must be DeliveryRegistration values")
    effects, marking = _petrinet_firing.complete_firing(net, marking, occurrence.binding.transition, result.tokens)
    appended: tuple[Record, ...] = (
        *(TokensProduced(effect.place, effect.tokens, occurrence=occurrence.id, instant=instant) for effect in effects),
        *(
            DeliveryRegistrationClosed(registration.source, registration.key, occurrence=occurrence.id, instant=instant)
            for registration in closes
        ),
        *(
            DeliveryRegistrationOpened(registration.source, registration.key, occurrence=occurrence.id, instant=instant)
            for registration in opens
        ),
        FiringCompleted(occurrence.binding.transition, occurrence=occurrence.id, instant=instant),
    )
    consumed = tuple(token for _, tokens in occurrence.binding.consumed for token in tokens)
    produced = tuple((effect.place, token) for effect in effects for token in effect.tokens)
    firing = FiringOutcome(
        occurrence.binding.transition,
        occurrence.id,
        consumed,
        produced,
        occurrence.records + appended,
    )
    return marking, firing, appended
