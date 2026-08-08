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
from dataclasses import dataclass

# Internal imports
from petrus.motus.activity import ActivityFailure, ActivityInvocation
from petrus.impetus.history import (
    ActivityCompleted,
    ActivityFailed,
    ActivityRequested,
    CandidateSelected,
    DeliveryRegistration,
    ExternalEventDelivered,
    FiringBegun,
    FiringCompleted,
    FiringFailed,
    Record,
    DeliveryRegistrationClosed,
    DeliveryRegistrationOpened,
    TokensConsumed,
    TokensProduced,
    TokensRead,
)
from petrus.impetus.binding import HandlerResult
from petrus.impetus.petrinet import Binding, Instant, Marking, Net, NetPath, Token
from petrus.impetus.petrinet import firing as _petrinet_firing


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
                record.result if isinstance(record, ActivityCompleted) else ActivityFailure(record.error)
            )
    return {occurrence: value for occurrence, value in terminal.items() if occurrence in ended}


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
    handler); a completion for an occurrence that requested no activity; or
    a second terminal activity fact — each is replay divergence the live
    instance can never write.
    """
    initiated: dict[int, tuple[NetPath, tuple[Token, ...]]] = {}
    begun: dict[int, list[Record]] = {}
    ended: set[int] = set()
    ending: set[int] = set()
    frozen: dict[int, object] = {}
    for record in history:
        if isinstance(record, CandidateSelected):
            initiated[record.occurrence] = (record.transition, ())
        elif isinstance(record, ExternalEventDelivered):
            initiated[record.occurrence] = (record.source, record.tokens)
        elif isinstance(record, FiringBegun):
            if record.occurrence not in initiated:
                raise ValueError(
                    f"replay divergence: firing occurrence {record.occurrence} ({record.transition}) "
                    f"begun with no initiation record"
                )
            begun[record.occurrence] = [record]
        elif isinstance(record, (TokensConsumed, TokensRead)):
            if record.occurrence not in begun:
                verb = "consumed" if isinstance(record, TokensConsumed) else "read"
                raise ValueError(
                    f"replay divergence: tokens {verb} from {record.place} for firing occurrence "
                    f"{record.occurrence} with no begun boundary"
                )
            begun[record.occurrence].append(record)
        elif isinstance(record, ActivityRequested):
            if record.occurrence not in begun:
                raise ValueError(
                    f"replay divergence: activity {record.activity!r} requested for firing occurrence "
                    f"{record.occurrence} with no begun boundary — the request joins the begin batch"
                )
            if any(isinstance(existing, ActivityRequested) for existing in begun[record.occurrence]):
                raise ValueError(
                    f"replay divergence: firing occurrence {record.occurrence} ({record.transition}) requested "
                    f"a second activity — one impure handler maps to exactly one activity"
                )
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
            if record.occurrence in frozen:
                raise ValueError(
                    f"replay divergence: a second terminal activity fact for firing occurrence "
                    f"{record.occurrence} ({record.transition}) — the first one wins, the writer appends no second"
                )
            frozen[record.occurrence] = record.result
        elif isinstance(record, ActivityFailed):
            if record.occurrence in frozen:
                raise ValueError(
                    f"replay divergence: firing occurrence {record.occurrence} ({record.transition}) failed "
                    f"after its activity completed — the live writer refuses to fail a frozen-completed occurrence"
                )
            ending.add(record.occurrence)
        elif isinstance(record, TokensProduced):
            ending.add(record.occurrence)
        elif isinstance(record, (DeliveryRegistrationOpened, DeliveryRegistrationClosed)):
            if record.occurrence is not None:
                ending.add(record.occurrence)
        elif isinstance(record, (FiringCompleted, FiringFailed)):
            ended.add(record.occurrence)
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
    return FiringOccurrence(
        occurrence_id, Binding(transition, consumed, read, delivered=delivered), tuple(records), invocation=invocation
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
