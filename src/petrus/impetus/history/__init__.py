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
spells records without lifecycle or queue-occurrence provenance under the
established schema-4 envelope and lifecycle-scope/provenance records under the
additive schema-5 envelope [DR 2026-07-10
durable-history-is-a-history-backend; DR 2026-08-11
history-first-lifecycle-scopes]. Each record has one canonical spelling, and a
History may contain both in append order. The
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
from petrus.impetus.scope import LifecycleScope


def _validate_entries(
    tokens: tuple[Token, ...],
    entries: tuple[int, ...],
    scope: LifecycleScope | None,
    noun: str,
) -> None:
    if entries and len(entries) != len(tokens):
        raise ValueError(f"{noun} requires one queue-entry identity per token")
    if any(isinstance(entry, bool) or not isinstance(entry, int) or entry < 1 for entry in entries):
        raise ValueError(f"{noun} queue-entry identities must be positive integers")
    if len(set(entries)) != len(entries):
        raise ValueError(f"{noun} queue-entry identities must be unique")
    if scope is not None and len(entries) != len(tokens):
        raise ValueError(f"{noun} scoped movements require one queue-entry identity per token")
    if entries and scope is None:
        raise ValueError(f"{noun} queue-entry identities require lifecycle scope provenance")


def _exact_scope(scope: LifecycleScope, noun: str) -> None:
    if not isinstance(scope, LifecycleScope):
        raise ValueError(f"{noun} requires an exact LifecycleScope generation")


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
    _: KW_ONLY
    entries: tuple[int, ...] = ()
    scope: LifecycleScope | None = None

    def __post_init__(self) -> None:
        _validate_entries(self.tokens, self.entries, self.scope, "TokensInitialized")
        if self.scope is not None:
            _exact_scope(self.scope, "TokensInitialized")


@dataclass(frozen=True)
class ScopeOpened:
    """One exact lifecycle generation became active."""

    scope: LifecycleScope
    instant: Instant = 0

    def __post_init__(self) -> None:
        _exact_scope(self.scope, "ScopeOpened")


@dataclass(frozen=True)
class ScopeClosed:
    """One generation closed, discarding exact queued entries and cancelling exact firings."""

    scope: LifecycleScope
    discarded: tuple[int, ...] = ()
    cancelled: tuple[int, ...] = ()
    instant: Instant = 0

    def __post_init__(self) -> None:
        _exact_scope(self.scope, "ScopeClosed")
        _validate_positive_ids(self.discarded, "ScopeClosed discarded queue entries")
        _validate_occurrence_ids(self.cancelled, "ScopeClosed cancelled occurrences")


@dataclass(frozen=True)
class ScopeReset:
    """Atomic close of one generation and open of its immediate successor."""

    closed: LifecycleScope
    opened: LifecycleScope
    discarded: tuple[int, ...] = ()
    cancelled: tuple[int, ...] = ()
    instant: Instant = 0

    def __post_init__(self) -> None:
        _exact_scope(self.closed, "ScopeReset closed")
        _exact_scope(self.opened, "ScopeReset opened")
        if self.opened.name != self.closed.name or self.opened.generation != self.closed.generation + 1:
            raise ValueError("ScopeReset must open the immediate next generation of the same name")
        _validate_positive_ids(self.discarded, "ScopeReset discarded queue entries")
        _validate_occurrence_ids(self.cancelled, "ScopeReset cancelled occurrences")


def _validate_occurrence_ids(values: tuple[int, ...], noun: str) -> None:
    _validate_positive_ids(values, noun)


def _validate_positive_ids(values: tuple[int, ...], noun: str) -> None:
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 1 for value in values):
        raise ValueError(f"{noun} must be positive integers")
    if len(set(values)) != len(values):
        raise ValueError(f"{noun} must be unique")


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
    scope: LifecycleScope | None = None
    instant: Instant = 0

    def __post_init__(self) -> None:
        if not isinstance(self.identity, str) or not self.identity:
            raise ValueError(f"ExternalEventDelivered requires a non-empty string identity, got {self.identity!r}")
        if self.scope is not None:
            _exact_scope(self.scope, "ExternalEventDelivered")


@dataclass(frozen=True)
class ScopedDeliveryDropped:
    """An identified delivery proved to target a closed generation and was acknowledged without firing."""

    source: NetPath
    tokens: tuple[Token, ...]
    _: KW_ONLY
    identity: str
    scope: LifecycleScope
    instant: Instant = 0

    def __post_init__(self) -> None:
        if not isinstance(self.identity, str) or not self.identity:
            raise ValueError("ScopedDeliveryDropped requires a non-empty string identity")
        _exact_scope(self.scope, "ScopedDeliveryDropped")


@dataclass(frozen=True)
class ScopedDeliveryQuarantined:
    """An identified delivery named a scope but could not prove its generation."""

    source: NetPath
    tokens: tuple[Token, ...]
    _: KW_ONLY
    identity: str
    scope: LifecycleScope | str
    instant: Instant = 0

    def __post_init__(self) -> None:
        if not isinstance(self.identity, str) or not self.identity:
            raise ValueError("ScopedDeliveryQuarantined requires a non-empty string identity")
        valid_name = isinstance(self.scope, str) and bool(self.scope) and "\x00" not in self.scope
        if not isinstance(self.scope, LifecycleScope) and not valid_name:
            raise ValueError("ScopedDeliveryQuarantined requires a non-empty scope name without NUL")


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
    scope: LifecycleScope | None = None
    instant: Instant = 0

    def __post_init__(self) -> None:
        if self.scope is not None:
            _exact_scope(self.scope, "FiringBegun")


@dataclass(frozen=True)
class TokensConsumed:
    """Tokens taken from a place at begin firing."""

    place: NetPath
    tokens: tuple[Token, ...]
    _: KW_ONLY
    occurrence: int
    entries: tuple[int, ...] = ()
    scope: LifecycleScope | None = None
    instant: Instant = 0

    def __post_init__(self) -> None:
        _validate_entries(self.tokens, self.entries, self.scope, "TokensConsumed")
        if self.scope is not None:
            _exact_scope(self.scope, "TokensConsumed")


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
    entries: tuple[int, ...] = ()
    scope: LifecycleScope | None = None
    instant: Instant = 0

    def __post_init__(self) -> None:
        _validate_entries(self.tokens, self.entries, self.scope, "TokensRead")
        if self.scope is not None:
            _exact_scope(self.scope, "TokensRead")


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
    scope: LifecycleScope | None = None
    instant: Instant = 0

    def __post_init__(self) -> None:
        for name, value in (
            ("activity", self.activity),
            ("correlation", self.correlation),
            ("idempotency", self.idempotency),
        ):
            if not isinstance(value, str) or not value:
                raise ValueError(f"ActivityRequested requires a non-empty string {name}, got {value!r}")
        if self.scope is not None:
            _exact_scope(self.scope, "ActivityRequested")


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
    kind: str = "ActivityError"
    details: object = None
    retryable: bool = False
    retry_after: float | None = None
    _: KW_ONLY
    occurrence: int
    instant: Instant = 0


@dataclass(frozen=True)
class ActivityTerminalQuarantined:
    """A terminal report arrived after lifecycle cancellation and cannot mutate the closed generation."""

    transition: NetPath
    outcome: object
    scope: LifecycleScope
    _: KW_ONLY
    occurrence: int
    instant: Instant = 0

    def __post_init__(self) -> None:
        _exact_scope(self.scope, "ActivityTerminalQuarantined")


@dataclass(frozen=True)
class TokensProduced:
    """Tokens deposited into a place at end firing."""

    place: NetPath
    tokens: tuple[Token, ...]
    _: KW_ONLY
    occurrence: int
    entries: tuple[int, ...] = ()
    scope: LifecycleScope | None = None
    instant: Instant = 0

    def __post_init__(self) -> None:
        _validate_entries(self.tokens, self.entries, self.scope, "TokensProduced")
        if self.scope is not None:
            _exact_scope(self.scope, "TokensProduced")


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
    | ScopeOpened
    | ScopeClosed
    | ScopeReset
    | CandidateSelected
    | ExternalEventDelivered
    | ScopedDeliveryDropped
    | ScopedDeliveryQuarantined
    | DeliveryRegistrationOpened
    | DeliveryRegistrationClosed
    | TimerMatured
    | FiringBegun
    | TokensConsumed
    | TokensRead
    | ActivityRequested
    | ActivityCompleted
    | ActivityTerminalQuarantined
    | TokensProduced
    | FiringCompleted
    | ActivityFailed
    | FiringFailed
)


def _apply_scope_cleanup(queues: dict[NetPath, TokenQueue], record: ScopeClosed | ScopeReset) -> None:
    """Discard one close/reset record's exact queue occurrences and prove completeness."""
    closed = record.scope if isinstance(record, ScopeClosed) else record.closed
    remaining = set(record.discarded)
    for place, queue in tuple(queues.items()):
        present = tuple(
            identity
            for identity, scope in zip(queue.identities, queue.scopes, strict=True)
            if identity in remaining and scope == closed
        )
        if present:
            queues[place] = queue.discard(present)
            remaining.difference_update(present)
    if remaining:
        raise ValueError(
            f"replay divergence: cannot discard queue entries {sorted(remaining)} from lifecycle scope {closed!r}"
        )
    retained = tuple(
        identity
        for queue in queues.values()
        for identity, scope in zip(queue.identities, queue.scopes, strict=True)
        if scope == closed
    )
    if retained:
        raise ValueError(f"replay divergence: lifecycle close left queue entries {retained!r} in scope {closed!r}")


def apply_movement(
    queues: dict[NetPath, TokenQueue],
    record: Record,
    *,
    inferred_entries: tuple[int, ...] | None = None,
) -> None:
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
        next_identity = _next_queue_identity(queues)
        entries = record.entries or inferred_entries or tuple(range(next_identity, next_identity + len(record.tokens)))
        if len(entries) != len(record.tokens):
            raise ValueError("movement fold requires one inferred queue-entry identity per token")
        existing = {
            identity
            for existing_queue in queues.values()
            for identity in existing_queue.identities
            if identity is not None
        }
        duplicated = existing.intersection(entries)
        if duplicated:
            raise ValueError(f"replay divergence: queue-entry identities already present {sorted(duplicated)}")
        for token, identity in zip(record.tokens, entries, strict=True):
            queue = queue.deposit(token, record.instant, identity=identity, scope=record.scope)
        queues[record.place] = queue
    elif isinstance(record, TokensConsumed):
        try:
            queues[record.place] = queues.get(record.place, TokenQueue()).remove(record.tokens, record.entries)
        except TokenNotPresent as error:
            raise ValueError(
                f"replay divergence: cannot consume {error.token!r} from {record.place}: token not present"
            ) from None
    elif isinstance(record, (ScopeClosed, ScopeReset)):
        _apply_scope_cleanup(queues, record)


def _next_queue_identity(queues: dict[NetPath, TokenQueue]) -> int:
    return (
        max(
            (identity for queue in queues.values() for identity in queue.identities if identity is not None),
            default=0,
        )
        + 1
    )


def replay_queues(history) -> dict[NetPath, TokenQueue]:
    """
    Fold the recorded token movements, in order, into per-place
    ``TokenQueue``s of ``(token, entry instant)`` — the one replay of
    movements the marking and time projections below share, and the primary
    live structure ``Instance`` maintains incrementally (resume folds here
    and continues where the fold left off).
    """
    queues, _ = _replay_queue_projection(history)
    return queues


def _replay_queue_projection(history) -> tuple[dict[NetPath, TokenQueue], int]:
    """Replay queues plus the next never-spent durable queue identity."""
    queues: dict[NetPath, TokenQueue] = {}
    next_identity = 1
    spent: set[int] = set()
    for record in history:
        inferred_entries = None
        if isinstance(record, (TokensInitialized, TokensProduced)):
            inferred_entries = record.entries or tuple(range(next_identity, next_identity + len(record.tokens)))
            duplicated = spent.intersection(inferred_entries)
            if duplicated:
                raise ValueError(f"replay divergence: queue-entry identities were already spent {sorted(duplicated)}")
            spent.update(inferred_entries)
            if inferred_entries:
                next_identity = max(next_identity, max(inferred_entries) + 1)
        apply_movement(queues, record, inferred_entries=inferred_entries)
    return queues, next_identity


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
        if not isinstance(
            record,
            (
                InstanceCreated,
                TokensInitialized,
                ScopeOpened,
                ScopeClosed,
                ScopeReset,
                ScopedDeliveryDropped,
                ScopedDeliveryQuarantined,
                TimerMatured,
            ),
        )
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


type AcceptedDelivery = ExternalEventDelivered | ScopedDeliveryDropped | ScopedDeliveryQuarantined


def replay_accepted_identities(history) -> dict[str, AcceptedDelivery]:
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
    accepted: dict[str, AcceptedDelivery] = {}
    for record in history:
        if isinstance(record, (ExternalEventDelivered, ScopedDeliveryDropped, ScopedDeliveryQuarantined)):
            if record.identity in accepted:
                raise ValueError(
                    f"replay divergence: delivery identity {record.identity!r} accepted twice — the single "
                    f"writer accepts an identity once and answers a redelivery with the prior acknowledgement"
                )
            accepted[record.identity] = record
    return accepted


# Complexity exception: one ordered fold over the closed lifecycle/provenance record family.
def replay_scopes(history) -> tuple[dict[str, LifecycleScope], dict[str, int]]:  # noqa: C901
    """Rebuild active generations and the greatest generation spent per name."""
    active: dict[str, LifecycleScope] = {}
    generations: dict[str, int] = {}
    for record in history:
        if isinstance(record, ScopeOpened):
            scope = record.scope
            if scope.name in active or scope.generation != generations.get(scope.name, 0) + 1:
                raise ValueError(f"replay divergence: invalid scope open {scope!r}")
            active[scope.name] = scope
            generations[scope.name] = scope.generation
        elif isinstance(record, ScopeClosed):
            if active.get(record.scope.name) != record.scope:
                raise ValueError(f"replay divergence: scope {record.scope!r} closed while not active")
            del active[record.scope.name]
        elif isinstance(record, ScopeReset):
            if active.get(record.closed.name) != record.closed:
                raise ValueError(f"replay divergence: scope {record.closed!r} reset while not active")
            active[record.opened.name] = record.opened
            generations[record.opened.name] = record.opened.generation
        elif isinstance(record, ScopedDeliveryDropped):
            if (
                active.get(record.scope.name) == record.scope
                or generations.get(record.scope.name, 0) < record.scope.generation
            ):
                raise ValueError(
                    f"replay divergence: delivery dropped for scope {record.scope!r} without proof it was closed"
                )
        elif isinstance(record, ScopedDeliveryQuarantined) and isinstance(record.scope, LifecycleScope):
            if (
                active.get(record.scope.name) == record.scope
                or generations.get(record.scope.name, 0) >= record.scope.generation
            ):
                raise ValueError(
                    f"replay divergence: exact delivery target {record.scope!r} was quarantined despite a known disposition"
                )
        elif (
            isinstance(
                record,
                (
                    TokensInitialized,
                    ExternalEventDelivered,
                    FiringBegun,
                    TokensConsumed,
                    TokensRead,
                    ActivityRequested,
                    TokensProduced,
                ),
            )
            and record.scope is not None
        ):
            if active.get(record.scope.name) != record.scope:
                raise ValueError(
                    f"replay divergence: {type(record).__name__} uses inactive lifecycle scope {record.scope!r}"
                )
    return active, generations


def replay_cancellation_positions(history) -> dict[int, int]:
    """Map each lifecycle-cancelled occurrence to its one-based canonical append position."""
    positions: dict[int, int] = {}
    for position, record in enumerate(history, start=1):
        if isinstance(record, (ScopeClosed, ScopeReset)):
            for occurrence in record.cancelled:
                if occurrence in positions:
                    raise ValueError(f"replay divergence: firing occurrence {occurrence} cancelled twice")
                positions[occurrence] = position
    return positions


def replay_next_queue_identity(history) -> int:
    """One past every queue occurrence reconstructed from canonical movement order."""
    _, next_identity = _replay_queue_projection(history)
    return next_identity


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
