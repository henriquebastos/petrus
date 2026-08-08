"""
Event history: the append-only record of how an instance evolves.

Records the deterministic evolution of an instance — initial marking, external
events delivered to source transitions, delivery-registration open/close,
timer maturation, candidate selection, begin/consume/read, produce,
completion. Token consumption and production are *explicit* records (not
deltas folded into a firing), so the marking is derivable by replaying
movements alone: ``replay_marking`` folds them over an empty marking and never
re-runs a handler. ``TokensRead`` is the movement family's replay-inert
member: it records what a firing observed without moving it.

Every record carries the ``instant`` of its append — the single writer stamps
it, monotone. The instance's clock watermark (the instant of the latest
appended record) is "now" everywhere the net runtime needs it, live and during
replay; ``entry_instants`` projects the same movement records into each
place-queue token's recorded entry instant, the anchor of duration timers
[DR 2026-07-08 time-projection-virtual-clock-watermark].

Every record of one firing likewise carries its ``occurrence`` — the firing
occurrence id, minted at the initiation record (the pipeline's "selected firing
occurrence" IS the durable record of the chosen candidate — a Navigator ruling)
and correlating the whole lifecycle, pure firings included. ``occurrence`` is
keyword-only with no default: unlike ``instant`` (where 0 is the honest
logical epoch), no occurrence id is honestly assumable, and a default would
silently uncorrelate a record from its firing.

The public per-category payload schema is ratified: ``petrus.impetus.history.codec``
spells every record as JSON under the schema-4 envelope [DR 2026-07-10
durable-history-is-a-history-backend], and the
family names each record's node by its role — ``place`` on the movement
records, ``transition`` on the firing records, ``source`` on the source-only
records (``ExternalEventDelivered``, ``DeliveryRegistrationOpened``/``Closed``) —
renamed family-wide at the schema moment exactly as the deferral ruled
[convention 40; DR 2026-07-14 delivery-registration-terminology].
"""

from __future__ import annotations

# Python imports
from dataclasses import KW_ONLY, dataclass

# Internal imports
from petrus.motus.activity import ExecutionPolicy
from petrus.impetus.petrinet import Marking, Token, TokenNotPresent, TokenQueue
from petrus.impetus.petrinet import Instant, NetPath


@dataclass(frozen=True)
class InstanceCreated:
    """
    The instance's identity fact — the first record of every history this
    kernel writes [ES-020/DEC-026]: ``instance`` is the unique instance id
    (caller-supplied, or minted by the constructor), ``name`` the net
    definition's optional human name. Identity is a fact, not code: resume
    derives both from this record — the one thing about an instance the
    caller does NOT re-supply — and telemetry stamps them on every event, so
    the semantic trace, the operational trace, and any backend keyed by
    instance id join on one identity. Never read by any semantics.
    """

    instance: str
    name: str | None = None
    instant: Instant = 0


@dataclass(frozen=True)
class TokensInitialized:
    """Initial-marking tokens entering a place before any firing."""

    place: NetPath
    tokens: tuple[Token, ...]
    instant: Instant = 0


@dataclass(frozen=True)
class CandidateSelected:
    """The scheduler chose this transition's binding to proceed — the selected firing occurrence's initiation record, minting its id."""

    transition: NetPath
    _: KW_ONLY
    occurrence: int
    instant: Instant = 0


@dataclass(frozen=True)
class ExternalEventDelivered:
    """
    An external event delivered to a source transition entered the history.

    Recorded before the firing it initiates — recording precedes and is
    independent of consumption; as the delivery's initiation record it mints
    the firing occurrence's id. The delivered tokens enter the marking only
    through the firing's ``TokensProduced`` records, so replay re-applies
    movements and never re-delivers.

    ``identity`` is the delivery's stable identity: supplied by the ingress
    adapter (a webhook's provider event id) or, when none exists, the
    writer's derived self-identity ``"occurrence-{id}"`` [DR 2026-07-14
    source-delivery-projection-and-identity] — the ``occurrence-`` prefix is
    the writer-reserved namespace of that derived form (``deliver`` refuses
    supplied identities inside it). The delivery door enforces idempotent
    acceptance by this identity: an accepted identity is answered with the
    prior acknowledgement on redelivery, and these records are the authority
    the accepted-identity index (``replay_accepted_identities``) projects.
    """

    source: NetPath
    tokens: tuple[Token, ...]
    _: KW_ONLY
    identity: str
    occurrence: int
    instant: Instant = 0

    def __post_init__(self) -> None:
        if not isinstance(self.identity, str) or not self.identity:
            raise ValueError(f"ExternalEventDelivered requires a non-empty string identity, got {self.identity!r}")


@dataclass(frozen=True)
class DeliveryRegistration:
    """
    A delivery registration's identity: the runtime's standing
    capability to deliver an external event to ``source``, told apart from
    its siblings on the same source by a caller-chosen ``key`` — several
    webhooks may feed one source, each closable on its own. A registration
    exists only as records (opened at instantiation or from a handler's
    result envelope, closed by a handler or by runtime policy); armed —
    opened and not yet closed — is a projection over them. The source
    spelling normalizes at construction: an identity value compares equal
    however it was spelled.
    """

    source: NetPath
    key: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", NetPath(self.source))
        if not isinstance(self.key, str) or not self.key:
            raise ValueError(f"DeliveryRegistration requires a non-empty string key, got {self.key!r}")


@dataclass(frozen=True)
class DeliveryRegistrationOpened:
    """
    The runtime may deliver external events to this source transition under
    this registration. ``occurrence`` correlates a handler-opened registration
    to the firing whose result envelope carried the effect; ``None`` spells
    the other birthplace honestly — an instantiation open no firing caused.
    Like every firing record's ``occurrence``, it is keyword-only with no
    default: no correlation is honestly assumable.
    """

    source: NetPath
    key: str
    _: KW_ONLY
    occurrence: int | None
    instant: Instant = 0


@dataclass(frozen=True)
class DeliveryRegistrationClosed:
    """
    This registration closed: the runtime can no longer deliver under it. A
    source whose last registration closes takes no further delivery, and
    status can flip on this append alone. ``occurrence`` correlates a
    handler-closed registration to its firing; ``None`` is runtime policy —
    a ``seal``, which closes every armed registration of the source.
    """

    source: NetPath
    key: str
    _: KW_ONLY
    occurrence: int | None
    instant: Instant = 0


@dataclass(frozen=True, kw_only=True)
class TimerMatured:
    """
    A time-based enablement condition became true (record category 2).

    The adapter's wakeup made into a fact: ``maturation_instant`` is the
    derived instant the binding matured, ``instant`` — the record's one
    instant, like every record's — is the observed instant of the wakeup that
    recorded it, never earlier than the maturation it observes. Maturation
    stays derived: the record advances the clock, it stores no timer state.

    Deliberate deviation from the sibling records' default-0 ``instant``
    (keyword-only instead): no honest default satisfies observed >= maturation,
    so a default would exist only to raise — both fields are required.
    """

    maturation_instant: Instant
    instant: Instant

    def __post_init__(self) -> None:
        if self.instant < self.maturation_instant:
            raise ValueError(
                f"timer maturation observed at {self.instant}, before its maturation instant "
                f"{self.maturation_instant}: a wakeup cannot precede what it observes"
            )


@dataclass(frozen=True)
class FiringBegun:
    """The firing occurrence boundary was recorded: its input tokens are accounted from here."""

    transition: NetPath
    _: KW_ONLY
    occurrence: int
    instant: Instant = 0


@dataclass(frozen=True)
class TokensConsumed:
    """Tokens taken from a place at begin firing."""

    place: NetPath
    tokens: tuple[Token, ...]
    _: KW_ONLY
    occurrence: int
    instant: Instant = 0


@dataclass(frozen=True)
class TokensRead:
    """
    Tokens a read arc selected at begin firing — observed, left in place
    (the canonical category-5 read fact [ADR 0031], closing debt
    2026-07-09T2330Z's recording half). Replay-inert for the marking: read
    tokens never leave their queue, so ``apply_movement`` deliberately
    applies this record as nothing. It exists so the canonical history
    carries the whole input binding [ADR 0034] — ``replay_in_flight``
    rebuilds a crashed occurrence's read selections from exactly these
    records, never from the live marking.
    """

    place: NetPath
    tokens: tuple[Token, ...]
    _: KW_ONLY
    occurrence: int
    instant: Instant = 0


@dataclass(frozen=True)
class ActivityRequested:
    """
    An impure firing occurrence froze its exact activity request — the
    authoritative outbox (activity record, category 6) [DR 2026-07-14
    activity-invocation-runtime-seam]. Joins the atomic begin batch after the
    ``TokensRead`` records, before any adapter or queue sees the invocation:
    a crash between durable request and dispatch is closed by republishing
    from this record. ``input`` is the Petri-agnostic typed activity input
    (JSON-faithful, the same durability constraint as token data);
    ``correlation`` and ``idempotency`` are recorded resolved — the writer
    derives the occurrence self-identity (``"occurrence-{id}"``, the
    writer-reserved namespace) where the handler supplied none.
    """

    transition: NetPath
    _: KW_ONLY
    activity: str
    input: object
    policy: ExecutionPolicy
    correlation: str
    idempotency: str
    occurrence: int
    instant: Instant = 0

    def __post_init__(self) -> None:
        for name, value in (
            ("activity", self.activity),
            ("correlation", self.correlation),
            ("idempotency", self.idempotency),
        ):
            if not isinstance(value, str) or not value:
                raise ValueError(f"ActivityRequested requires a non-empty string {name}, got {value!r}")


@dataclass(frozen=True)
class ActivityCompleted:
    """
    The activity's frozen typed external result — the terminal activity fact
    (category 7) [DR 2026-07-14 activity-invocation-runtime-seam]. Committed
    as its own append BEFORE deterministic handler projection, so a
    projection bug or crash never repeats completed external work: after a
    fix, projection retries from this record. The first terminal activity
    fact for an occurrence wins — the writer acknowledges an identical
    re-record without a second append and refuses a different late result.
    ``result`` is JSON-faithful, the same durability constraint as token data.
    """

    transition: NetPath
    result: object
    _: KW_ONLY
    occurrence: int
    instant: Instant = 0


@dataclass(frozen=True)
class ActivityFailed:
    """
    The execution adapter exhausted its resolved policy — the terminal
    activity fact's failure half [DR 2026-07-14
    activity-invocation-runtime-seam]. Committed together with
    ``FiringFailed`` in one batch: infrastructure failure stops the firing
    and is never converted into a business token (a typed provider decline is
    ``ActivityCompleted``, projected and routed like any result).
    """

    transition: NetPath
    error: str
    _: KW_ONLY
    occurrence: int
    instant: Instant = 0


@dataclass(frozen=True)
class TokensProduced:
    """Tokens deposited into a place at end firing."""

    place: NetPath
    tokens: tuple[Token, ...]
    _: KW_ONLY
    occurrence: int
    instant: Instant = 0


@dataclass(frozen=True)
class FiringCompleted:
    """The firing committed its output and marking evolution."""

    transition: NetPath
    _: KW_ONLY
    occurrence: int
    instant: Instant = 0


@dataclass(frozen=True)
class FiringFailed:
    """
    The firing occurrence ended in terminal failure (category 11). The error is
    a value, not a live exception; the consumed tokens stay consumed —
    restoring them would claim work never happened. Retries never reach the
    net: the execution runtime retries a handler without touching the
    history, and only the terminal outcome crosses the seam.
    """

    transition: NetPath
    error: str
    _: KW_ONLY
    occurrence: int
    instant: Instant = 0


# The record types emitted so far — deterministic records and, for impure
# work, activity records, in one unified history [ADR 0034]. Widened as new
# categories land.
Record = (
    InstanceCreated
    | TokensInitialized
    | CandidateSelected
    | ExternalEventDelivered
    | DeliveryRegistrationOpened
    | DeliveryRegistrationClosed
    | TimerMatured
    | FiringBegun
    | TokensConsumed
    | TokensRead
    | ActivityRequested
    | ActivityCompleted
    | TokensProduced
    | FiringCompleted
    | ActivityFailed
    | FiringFailed
)


def apply_movement(queues: dict[NetPath, TokenQueue], record: Record) -> None:
    """
    Apply one record to per-place pair-queues — the single step of the
    movement fold, shared by replay (``replay_queues``) and the live
    instance's incremental maintenance of the same structure. A non-movement
    record applies as nothing — and so does ``TokensRead``, the movement
    family's deliberately replay-inert member: read tokens never leave their
    queue. Deposits enter at the record's instant; each
    consume removes its tokens' front-most equal occurrences
    (``TokenQueue.remove``), exactly as the live ``Marking.consume`` validated
    before the record was appended — applied strictly in record order, so a
    corrupted or reordered trace fails loud instead of silently
    count-matching (a deferred match would pair a consume with a FUTURE
    deposit and read a corrupted trace as valid).
    """
    if isinstance(record, (TokensInitialized, TokensProduced)):
        queue = queues.get(record.place, TokenQueue())
        for token in record.tokens:
            queue = queue.deposit(token, record.instant)
        queues[record.place] = queue
    elif isinstance(record, TokensConsumed):
        try:
            queues[record.place] = queues.get(record.place, TokenQueue()).remove(record.tokens)
        except TokenNotPresent as error:
            raise ValueError(
                f"replay divergence: cannot consume {error.token!r} from {record.place}: token not present"
            ) from None


def replay_queues(history) -> dict[NetPath, TokenQueue]:
    """
    Fold the recorded token movements, in order, into per-place
    ``TokenQueue``s of ``(token, entry instant)`` — the one replay of
    movements the marking and time projections below share, and the primary
    live structure ``Instance`` maintains incrementally (resume folds here
    and continues where the fold left off).
    """
    queues: dict[NetPath, TokenQueue] = {}
    for record in history:
        apply_movement(queues, record)
    return queues


def replay_marking(history) -> Marking:
    """
    Rebuild the marking by re-applying recorded token movements, in order.

    Non-movement records (selection, external events, delivery-registration
    lifecycle, timer maturation, begin, activity request/completion/failure,
    completion, failure) contribute nothing — a frozen activity result enters
    the marking only through the ``TokensProduced`` records its projection
    committed — and ``TokensRead`` contributes nothing by design: reads
    observe, they never move.
    """
    return Marking({place: queue.tokens for place, queue in replay_queues(history).items()})


def entry_instants(history) -> dict[NetPath, tuple[Instant, ...]]:
    """
    Each place-queue token's recorded entry instant, position-aligned with the
    marking the same records replay to: the instant of the record that
    deposited it (initialization, or production — including a delivery's).
    These anchors are what a ``Delay`` timer matures from.
    """
    return {place: queue.instants for place, queue in replay_queues(history).items() if queue}


def replay_watermark(history) -> Instant:
    """
    The clock watermark a recorded history proves: the last record's instant,
    validated monotone on the way there — the single writer only ever appends
    at-or-after its watermark, so an instant that steps backwards is replay
    divergence, and resuming over it would let the next append record an
    instant earlier than an already-recorded fact. An empty history proves no
    watermark and fails loud.
    """
    watermark: Instant | None = None
    for record in history:
        if watermark is not None and record.instant < watermark:
            raise ValueError(
                f"replay divergence: instant {record.instant} steps backwards past {watermark}: "
                f"the single writer appends monotone instants"
            )
        watermark = record.instant
    if watermark is None:
        raise ValueError("an empty history proves no watermark")
    return watermark


def replay_next_occurrence(history) -> int:
    """
    One past the greatest spent occurrence id in the records. Every record but
    the two occurrence-less categories (``TokensInitialized``, ``TimerMatured``)
    carries its occurrence correlation — an id for a firing's records, ``None``
    where no firing caused the fact. Ids mint at initiation records, but the
    fold counts every correlated id as spent: on a partially persisted trace
    an orphan initiation's id is still a recorded fact, and never re-minting
    outranks minting-site bookkeeping. A new occurrence-less record category
    fails loud here until the fold excludes it deliberately.
    """
    spent = (
        record.occurrence
        for record in history
        if not isinstance(record, (InstanceCreated, TokensInitialized, TimerMatured))
    )
    return max((occurrence for occurrence in spent if occurrence is not None), default=0) + 1


def replay_instance_identity(history) -> InstanceCreated | None:
    """
    The recorded identity fact, when the trace holds one — validated where
    the live writer's discipline can be checked: identity is recorded first
    and exactly once, so an ``InstanceCreated`` anywhere past position 0 (a
    duplicate, or a mid-trace one) is replay divergence. ``None`` for a
    pre-identity trace: a legacy history resumes unidentified, never refused
    — absence is age, not corruption [ES-020/DEC-026].
    """
    identity: InstanceCreated | None = None
    for position, record in enumerate(history):
        if isinstance(record, InstanceCreated):
            if position != 0:
                raise ValueError(
                    f"replay divergence: InstanceCreated at position {position}: the single writer records "
                    f"identity as the first record, exactly once"
                )
            identity = record
    return identity


def replay_accepted_identities(history) -> dict[str, ExternalEventDelivered]:
    """
    The accepted delivery identities, each mapped to its complete recorded
    delivery fact — the projection behind the delivery door's idempotent
    acceptance [DR 2026-07-14 source-delivery-projection-and-identity]. An
    exact redelivery is answered with the prior acknowledgement, never a
    second semantic record; reusing the identity for another source or token
    payload is a conflict, so the index retains the evidence needed to tell
    those cases apart. The single writer accepts an identity once, so a trace
    holding one twice is replay divergence — a rebuilt index is valid only if
    the live writer could have written it. Derived self-identities
    (``occurrence-{id}``) index like supplied ones: the projection speaks
    every ``ExternalEventDelivered`` record, and the writer-reserved
    namespace keeps the two from colliding.
    """
    accepted: dict[str, ExternalEventDelivered] = {}
    for record in history:
        if isinstance(record, ExternalEventDelivered):
            if record.identity in accepted:
                raise ValueError(
                    f"replay divergence: delivery identity {record.identity!r} accepted twice — the single "
                    f"writer accepts an identity once and answers a redelivery with the prior acknowledgement"
                )
            accepted[record.identity] = record
    return accepted


def replay_armed(history) -> dict[NetPath, set[str]]:
    """
    The armed delivery-registration keys per source, by re-applying the
    recorded opens and closes, in order — the registration lifecycle's
    ``replay_marking``.
    A source appears once its records do (a source closed to nothing stays
    present and empty); sources with no records are absent — this projection
    speaks only recorded facts, and an instance knows its sources from the
    net. An open of an armed key or a close of an unarmed one fails loud as
    replay divergence: the live instance validated every effect before it
    appended, so a trace that disagrees is corrupted or reordered.
    """
    armed: dict[NetPath, set[str]] = {}
    for record in history:
        if isinstance(record, DeliveryRegistrationOpened):
            keys = armed.setdefault(record.source, set())
            if record.key in keys:
                raise ValueError(
                    f"replay divergence: delivery registration {record.key!r} on {record.source} opened while armed"
                )
            keys.add(record.key)
        elif isinstance(record, DeliveryRegistrationClosed):
            if record.key not in armed.get(record.source, set()):
                raise ValueError(
                    f"replay divergence: delivery registration {record.key!r} on {record.source} closed while not armed"
                )
            armed[record.source].discard(record.key)
    return armed
