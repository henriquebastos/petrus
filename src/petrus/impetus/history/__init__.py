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
spells every record under one field-complete schema-5 envelope [DR 2026-07-10
durable-history-is-a-history-backend; DR 2026-08-11
history-first-lifecycle-scopes]. Each record has one canonical spelling. The
family names each record's node by its role — ``place`` on the movement
records, ``transition`` on the firing records, ``source`` on the source-only
records (``ExternalEventDelivered``, ``DeliveryRegistrationOpened``/``Closed``) —
renamed family-wide at the schema moment exactly as the deferral ruled
[convention 40; DR 2026-07-14 delivery-registration-terminology].
"""

from __future__ import annotations

# Python imports
from copy import deepcopy
from dataclasses import KW_ONLY, dataclass, fields
import json
from typing import cast, get_args

# Internal imports
from petrus.motus.activity import ExecutionPolicy
from petrus.impetus.petrinet import Marking, Token, TokenNotPresent, TokenQueue
from petrus.impetus.petrinet import Instant, NetPath
from petrus.impetus.petrinet.schema import canonical_net_path
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
    if type(scope) is not LifecycleScope:
        raise ValueError(f"{noun} requires an exact LifecycleScope generation")


def _canonical_json_shape(value: object) -> bool:
    if value is None or type(value) in {bool, int, float, str}:
        return True
    if type(value) is list:
        return all(_canonical_json_shape(item) for item in value)
    if type(value) is dict:
        return all(type(key) is str and _canonical_json_shape(item) for key, item in value.items())
    return False


def _validate_delivery_tokens(tokens: object, record: str) -> None:
    if type(tokens) is not tuple or not tokens:
        msg = f"{record} tokens must be a non-empty tuple of canonical Tokens"
        raise ValueError(msg)
    for position, token in enumerate(tokens):
        if type(token) is not Token:
            msg = f"{record} token at position {position} must be an exact Token"
            raise ValueError(msg)
        if token.color is not None and type(token.color) is not str:
            msg = f"{record} token color at position {position} must be an exact string or None"
            raise ValueError(msg)
        try:
            json.dumps(token.data, allow_nan=False)
        except (TypeError, ValueError) as error:
            msg = f"{record} token data at position {position} must be strict JSON"
            raise ValueError(msg) from error
        if not _canonical_json_shape(token.data):
            msg = f"{record} token data at position {position} must have canonical JSON types"
            raise ValueError(msg)


def _validate_delivery_identity(identity: object, record: str) -> None:
    if type(identity) is not str or not identity:
        raise ValueError(f"{record} requires an exact non-empty string identity, got {identity!r}")


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


def _validate_occurrence_id(value: object, noun: str) -> None:
    if type(value) is not int or value < 1:
        raise ValueError(f"{noun} must be a positive integer, got {value!r}")


def _validated_registration_source(
    source: NetPath | str,
    key: object,
    occurrence: object,
    noun: str,
) -> NetPath:
    if type(key) is not str or not key:
        raise ValueError(f"{noun} requires a non-empty string key of the exact built-in type, got {key!r}")
    if occurrence is not None:
        _validate_occurrence_id(occurrence, f"{noun} occurrence")
    return canonical_net_path(source, f"{noun} source")


def _validate_occurrence_ids(values: tuple[int, ...], noun: str) -> None:
    _validate_positive_ids(values, noun)


def _validate_positive_ids(values: tuple[int, ...], noun: str) -> None:
    if any(type(value) is not int or value < 1 for value in values):
        raise ValueError(f"{noun} must use exact positive integers")
    if len(set(values)) != len(values):
        raise ValueError(f"{noun} must be unique")


@dataclass(frozen=True)
class CandidateSelected:
    """The scheduler chose this transition's binding to proceed — the selected firing occurrence's initiation record, minting its id."""

    transition: NetPath
    _: KW_ONLY
    occurrence: int
    instant: Instant = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "transition", canonical_net_path(self.transition, "CandidateSelected transition"))
        _validate_occurrence_id(self.occurrence, "CandidateSelected occurrence")


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
    adapter (a webhook's provider event id) [DR 2026-07-14
    source-delivery-projection-and-identity]. Every source delivery requires
    one: the writer never substitutes an occurrence-derived identity that the
    adapter could not reconstruct after a crash. The delivery door enforces
    idempotent acceptance by this identity: redelivery reconstructs the
    accepted unfinished occurrence or, after it ends, returns its prior
    acknowledgement. These records are the authority the accepted-identity
    index (``replay_accepted_identities``) projects.
    """

    source: NetPath
    tokens: tuple[Token, ...]
    _: KW_ONLY
    identity: str
    occurrence: int
    scope: LifecycleScope | None = None
    instant: Instant = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", canonical_net_path(self.source, "ExternalEventDelivered source"))
        _validate_occurrence_id(self.occurrence, "ExternalEventDelivered occurrence")
        _validate_delivery_identity(self.identity, "ExternalEventDelivered")
        _validate_delivery_tokens(self.tokens, "ExternalEventDelivered")
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
        object.__setattr__(self, "source", canonical_net_path(self.source, "ScopedDeliveryDropped source"))
        _validate_delivery_identity(self.identity, "ScopedDeliveryDropped")
        _validate_delivery_tokens(self.tokens, "ScopedDeliveryDropped")
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
        object.__setattr__(self, "source", canonical_net_path(self.source, "ScopedDeliveryQuarantined source"))
        _validate_delivery_identity(self.identity, "ScopedDeliveryQuarantined")
        _validate_delivery_tokens(self.tokens, "ScopedDeliveryQuarantined")
        valid_name = type(self.scope) is str and bool(self.scope) and "\x00" not in self.scope
        if type(self.scope) is not LifecycleScope and not valid_name:
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
        object.__setattr__(self, "source", canonical_net_path(self.source, "DeliveryRegistration source"))
        if type(self.key) is not str or not self.key:
            raise ValueError(
                f"DeliveryRegistration requires a non-empty string key of the exact built-in type, got {self.key!r}"
            )


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

    def __post_init__(self) -> None:
        source = _validated_registration_source(
            self.source,
            self.key,
            self.occurrence,
            type(self).__name__,
        )
        object.__setattr__(self, "source", source)


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

    def __post_init__(self) -> None:
        source = _validated_registration_source(
            self.source,
            self.key,
            self.occurrence,
            type(self).__name__,
        )
        object.__setattr__(self, "source", source)


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
        _validate_occurrence_id(self.occurrence, "FiringBegun occurrence")
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
        _validate_occurrence_id(self.occurrence, "TokensProduced occurrence")
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

    def __post_init__(self) -> None:
        _validate_occurrence_id(self.occurrence, "FiringCompleted occurrence")


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

    def __post_init__(self) -> None:
        _validate_occurrence_id(self.occurrence, "FiringFailed occurrence")
        if type(self.error) is not str or not self.error or len(self.error) > 4096:
            raise ValueError("FiringFailed error must be a non-empty string of at most 4096 characters")


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


_RECORD_NODE_FIELDS = frozenset({"place", "source", "transition"})
_RECORD_ID_FIELDS = frozenset({"cancelled", "discarded", "entries"})
_RECORD_STRING_FIELDS = frozenset(
    {"activity", "correlation", "error", "idempotency", "identity", "instance", "key", "kind", "name"}
)
_RECORD_NONEMPTY_STRING_FIELDS = _RECORD_STRING_FIELDS - {"name"}
_RECORD_ACTIVITY_PAYLOAD_FIELDS = {
    ActivityRequested: frozenset({"input"}),
    ActivityCompleted: frozenset({"result"}),
    ActivityFailed: frozenset({"details"}),
    ActivityTerminalQuarantined: frozenset({"outcome"}),
}
_DELIVERY_RECORD_TYPES = frozenset({ExternalEventDelivered, ScopedDeliveryDropped, ScopedDeliveryQuarantined})


def _canonical_record_node(record_type: type, name: str, value: object) -> NetPath:
    """Canonicalize one record node address."""
    return canonical_net_path(value, f"{record_type.__name__} {name}")


def _canonical_record_occurrence(record_type: type, name: str, value: object) -> object:
    """Validate one optional firing occurrence identity."""
    noun = f"{record_type.__name__} {name}"
    if value is not None:
        _validate_occurrence_id(value, noun)
    return value


def _canonical_record_tokens(record_type: type, name: str, value: object) -> tuple[Token, ...]:
    """Own one exact detached token tuple."""
    _validate_record_tokens(record_type, name, value)
    tokens = cast("tuple[Token, ...]", value)
    return tuple(Token(token.color, deepcopy(token.data)) for token in tokens)


def _validate_record_tokens(record_type: type, name: str, value: object) -> None:
    """Validate exact token containers without reading or copying opaque token data."""
    noun = f"{record_type.__name__} {name}"
    if type(value) is not tuple:
        raise ValueError(f"{noun} must be an exact tuple of Tokens")
    for position, token in enumerate(value):
        if type(token) is not Token:
            raise ValueError(f"{noun} token at position {position} must be an exact Token")
        if token.color is not None and type(token.color) is not str:
            raise ValueError(f"{noun} token color at position {position} must be an exact string or None")
    if record_type in _DELIVERY_RECORD_TYPES:
        _validate_delivery_tokens(value, record_type.__name__)


def _canonical_record_ids(record_type: type, name: str, value: object) -> tuple[int, ...]:
    """Validate one tuple of durable positive identities."""
    noun = f"{record_type.__name__} {name}"
    if type(value) is not tuple:
        raise ValueError(f"{noun} must be an exact tuple of positive integers")
    identities = cast("tuple[int, ...]", value)
    _validate_positive_ids(identities, noun)
    return identities


def _canonical_record_scope(record_type: type, name: str, value: object) -> LifecycleScope | str | None:
    """Own one exact lifecycle scope spelling."""
    if value is None:
        return None
    if type(value) is LifecycleScope:
        return LifecycleScope(value.name, value.generation)
    if name == "scope" and type(value) is str:
        return value
    noun = f"{record_type.__name__} {name}"
    raise ValueError(f"{noun} must be an exact LifecycleScope, exact name string, or None")


def _canonical_record_policy(record_type: type, name: str, value: object) -> ExecutionPolicy:
    """Own one exact execution policy."""
    _validate_record_policy(record_type, name, value)
    policy = {field.name: getattr(value, field.name) for field in fields(ExecutionPolicy)}
    return ExecutionPolicy(**policy)


def _validate_record_policy(record_type: type, name: str, value: object) -> None:
    """Validate an execution policy from its original fields without invoking copy protocols."""
    noun = f"{record_type.__name__} {name}"
    if type(value) is not ExecutionPolicy:
        raise ValueError(f"{noun} must be an exact ExecutionPolicy")
    policy = {field.name: getattr(value, field.name) for field in fields(ExecutionPolicy)}
    if type(policy["attempts"]) is not int or type(policy["heartbeat_timeout"]) is not int:
        raise ValueError(f"{noun} integer fields must use the exact built-in type")
    for field_name in (
        "initial_interval",
        "coefficient",
        "max_interval",
        "jitter",
        "start_to_close",
        "schedule_to_close",
    ):
        item = policy[field_name]
        if item is not None and type(item) not in {int, float}:
            raise ValueError(f"{noun} numeric fields must use exact built-in numbers")


def _validate_record_activity_payload(record_type: type, name: str, value: object) -> None:
    """Require the exact retained JSON shape before replay detaches an activity payload."""
    noun = f"{record_type.__name__} {name}"
    if not _canonical_json_shape(value):
        raise ValueError(f"{noun} must have canonical JSON types")
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{noun} must be strict JSON") from error


def _canonical_record_string(record_type: type, name: str, value: object) -> str | None:
    """Validate one exact record string while preserving established errors."""
    noun = f"{record_type.__name__} {name}"
    if name == "instance":
        if type(value) is not str or not value:
            raise ValueError(f"Instance identity must be a non-empty string, got {value!r}")
        return value
    if name == "identity":
        _validate_delivery_identity(value, record_type.__name__)
        return cast("str", value)
    if record_type is FiringFailed and name == "error":
        if type(value) is not str or not value or len(value) > 4096:
            raise ValueError("FiringFailed error must be a non-empty string of at most 4096 characters")
        return value
    if name in _RECORD_STRING_FIELDS:
        if value is not None and type(value) is not str:
            raise ValueError(f"{noun} must use the exact built-in string type")
        if name in _RECORD_NONEMPTY_STRING_FIELDS and not value:
            raise ValueError(f"{noun} must be a non-empty string")
    return cast("str | None", value)


def _canonical_record_retryable(record_type: type, name: str, value: object) -> bool:
    """Validate the exact activity-failure retry flag."""
    if type(value) is not bool:
        raise ValueError(f"{record_type.__name__} {name} must use the exact built-in boolean type")
    return value


def _canonical_record_retry_after(record_type: type, name: str, value: object) -> int | float | None:
    """Validate the optional activity-failure retry delay."""
    if value is not None and type(value) not in {int, float}:
        raise ValueError(f"{record_type.__name__} {name} must use an exact built-in number or None")
    return cast("int | float | None", value)


def _detached_record_value(record_type: type, name: str, value: object) -> object:
    """Own one payload field with no protocol-specific scalar rule."""
    del record_type, name
    return deepcopy(value)


_RECORD_FIELD_CANONICALIZERS = (
    {name: _canonical_record_node for name in _RECORD_NODE_FIELDS}
    | {"occurrence": _canonical_record_occurrence}
    | {"tokens": _canonical_record_tokens}
    | {name: _canonical_record_ids for name in _RECORD_ID_FIELDS}
    | {name: _canonical_record_scope for name in ("scope", "closed", "opened")}
    | {"policy": _canonical_record_policy}
    | {name: _canonical_record_string for name in _RECORD_STRING_FIELDS}
    | {"retryable": _canonical_record_retryable, "retry_after": _canonical_record_retry_after}
)
_RECORD_FIELD_VALIDATORS = _RECORD_FIELD_CANONICALIZERS | {
    "tokens": _validate_record_tokens,
    "policy": _validate_record_policy,
}


def _canonical_record_field(record_type: type, name: str, value: object) -> object:
    """Validate and own one exact dataclass field before replay can observe it."""
    canonicalize = _RECORD_FIELD_CANONICALIZERS.get(name, _detached_record_value)
    return canonicalize(record_type, name, value)


def _validate_record_field(record_type: type, name: str, value: object) -> None:
    """Validate one original field without invoking payload copy protocols."""
    validate = _RECORD_FIELD_VALIDATORS.get(name)
    if validate is not None:
        validate(record_type, name, value)
    elif name in _RECORD_ACTIVITY_PAYLOAD_FIELDS.get(record_type, ()):
        _validate_record_activity_payload(record_type, name, value)


def _canonical_record(record_type: type[Record], record: object) -> Record:
    """Reconstruct one field-complete detached record through its canonical constructor."""
    values = {
        field.name: _canonical_record_field(record_type, field.name, getattr(record, field.name))
        for field in fields(record_type)
        if field.init
    }
    return record_type(**values)  # ty: ignore[invalid-argument-type]


def validate_history_record_values(history) -> tuple[Record, ...]:
    """Validate original record fields without detaching opaque payloads."""
    records = tuple(history)
    record_types = get_args(Record)
    for position, record in enumerate(records):
        record_type = type(record)
        if record_type not in record_types:
            raise ValueError(
                f"replay divergence: record at position {position} must use an exact record type, found "
                f"{record_type.__name__}; load records through a canonical History backend"
            )
        for field in fields(record_type):
            if field.init:
                _validate_record_field(record_type, field.name, getattr(record, field.name))
    return cast("tuple[Record, ...]", records)


def validate_history_records(history) -> tuple[Record, ...]:
    """Reconstruct exact canonical record values before replay reads any field."""
    records = validate_history_record_values(history)
    return tuple(_canonical_record(type(record), record) for record in records)


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
    for queues, next_identity in _replay_queue_states(history):
        pass
    return queues, next_identity


def _replay_queue_states(history):
    """Yield the cumulative queue projection after every History record."""
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
        yield queues, next_identity


def replay_markings(history) -> tuple[Marking, ...]:
    """Project the complete marking after each History record in one movement fold."""
    return tuple(
        Marking({place: queue.tokens for place, queue in queues.items()}) for queues, _ in _replay_queue_states(history)
    )


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
    Fold the recorded identity fact from canonical records: identity is first
    and exactly once, so a missing identity or an ``InstanceCreated`` anywhere
    past position 0 is replay divergence.
    """
    identity: InstanceCreated | None = None
    records = tuple(history)
    for position, record in enumerate(records):
        if isinstance(record, InstanceCreated):
            if position != 0:
                raise ValueError(
                    f"replay divergence: InstanceCreated at position {position}: the single writer records "
                    f"identity as the first record, exactly once"
                )
            identity = record
    if records and identity is None:
        raise ValueError("replay divergence: the construction batch requires InstanceCreated as its first record")
    return identity


type AcceptedDeliveryFact = ExternalEventDelivered | ScopedDeliveryDropped | ScopedDeliveryQuarantined


# Complexity exception: one ordered validation fold over the completion-effect record family.
def _validate_correlated_delivery_registration_batches(records: tuple[Record, ...]) -> None:  # noqa: C901
    """Require every firing-correlated registration effect to end in its contiguous completion batch."""
    effect_occurrences = {
        record.occurrence
        for record in records
        if isinstance(record, (DeliveryRegistrationOpened, DeliveryRegistrationClosed))
        and record.occurrence is not None
    }
    begun: dict[int, NetPath] = {}
    active: tuple[int, Instant, int] | None = None
    for record in records:
        if active is not None:
            occurrence, instant, prior_rank = active
            if (
                isinstance(record, FiringCompleted)
                and record.occurrence == occurrence
                and record.instant == instant
                and record.transition == begun[occurrence]
            ):
                active = None
                continue
            if isinstance(record, TokensProduced):
                rank = 0
            elif isinstance(record, DeliveryRegistrationClosed):
                rank = 1
            elif isinstance(record, DeliveryRegistrationOpened):
                rank = 2
            else:
                raise ValueError(
                    f"replay divergence: correlated delivery registration effect for occurrence {occurrence} "
                    "does not belong to a contiguous writer-valid completion batch"
                )
            if record.occurrence != occurrence or record.instant != instant or rank < prior_rank:
                raise ValueError(
                    f"replay divergence: correlated delivery registration effect for occurrence {occurrence} "
                    "does not belong to a contiguous writer-valid completion batch"
                )
            active = (occurrence, instant, rank)
            continue
        if isinstance(record, FiringBegun):
            begun[record.occurrence] = record.transition
        if isinstance(record, TokensProduced) and record.occurrence in effect_occurrences:
            if record.occurrence not in begun:
                raise ValueError(
                    f"replay divergence: correlated delivery registration effect for occurrence "
                    f"{record.occurrence} does not belong to a contiguous writer-valid completion batch"
                )
            active = (record.occurrence, record.instant, 0)
        if (
            isinstance(record, (DeliveryRegistrationOpened, DeliveryRegistrationClosed))
            and record.occurrence is not None
        ):
            if record.occurrence not in begun:
                raise ValueError(
                    f"replay divergence: correlated delivery registration effect for occurrence "
                    f"{record.occurrence} does not belong to a contiguous writer-valid completion batch"
                )
            rank = 2 if isinstance(record, DeliveryRegistrationOpened) else 1
            active = (record.occurrence, record.instant, rank)
    if active is not None:
        occurrence, _, _ = active
        raise ValueError(
            f"replay divergence: correlated delivery registration effect for occurrence {occurrence} "
            "does not belong to a contiguous writer-valid completion batch"
        )


def _apply_delivery_registration(
    armed: dict[NetPath, set[str]],
    record: Record,
    *,
    initial_registration_batch: bool,
    initial_instant: Instant,
) -> None:
    """Apply one registration record with the live writer's open/close preconditions."""
    if isinstance(record, DeliveryRegistrationOpened):
        keys = armed.setdefault(record.source, set())
        if record.key in keys:
            raise ValueError(
                f"replay divergence: delivery registration {record.key!r} on {record.source} opened while armed"
            )
        if record.occurrence is None:
            if not initial_registration_batch:
                raise ValueError(
                    f"replay divergence: uncorrelated delivery registration {record.key!r} on "
                    f"{record.source} opened outside the initial construction batch; the single writer "
                    "emits an uncorrelated open only in the initial construction batch"
                )
            if record.key != "default":
                raise ValueError(
                    f"replay divergence: initial delivery registration on {record.source} uses key "
                    f"{record.key!r}; the single writer uses only 'default'"
                )
            if record.instant != initial_instant:
                raise ValueError(
                    f"replay divergence: initial delivery registration {record.key!r} on {record.source} "
                    f"uses instant {record.instant}, not construction instant {initial_instant}"
                )
        keys.add(record.key)
    elif isinstance(record, DeliveryRegistrationClosed):
        if record.key not in armed.get(record.source, set()):
            raise ValueError(
                f"replay divergence: delivery registration {record.key!r} on {record.source} closed while not armed"
            )
        armed[record.source].discard(record.key)


def _advance_initial_registration_batch(
    record: Record,
    *,
    initial_registration_batch: bool,
    registrations_started: bool,
) -> tuple[bool, bool]:
    """Validate and advance the construction prefix before applying ``record``."""
    if isinstance(record, DeliveryRegistrationOpened) and record.occurrence is None:
        return initial_registration_batch, True
    if isinstance(record, TokensInitialized):
        if not initial_registration_batch or registrations_started:
            raise ValueError(
                "replay divergence: TokensInitialized appears outside the contiguous initial construction prefix"
            )
        return initial_registration_batch, registrations_started
    if isinstance(record, InstanceCreated):
        return initial_registration_batch, registrations_started
    return False, registrations_started


def replay_accepted_identities(history) -> dict[str, AcceptedDeliveryFact]:
    """
    The accepted delivery identities, each mapped to its complete recorded
    delivery fact — the projection behind the delivery door's idempotent
    acceptance [DR 2026-07-14 source-delivery-projection-and-identity]. An
    exact redelivery reconstructs its accepted unfinished occurrence or,
    after that occurrence ends, returns its prior acknowledgement; neither
    answer appends a second semantic record. Reusing the identity for another
    source or token payload is a conflict, so the index retains the evidence
    needed to tell those cases apart. The single writer accepts an identity
    once, so a trace holding one twice is replay divergence — a rebuilt index
    is valid only if the live writer could have written it.
    """
    accepted: dict[str, AcceptedDeliveryFact] = {}
    armed: dict[NetPath, set[str]] = {}
    records = tuple(history)
    _validate_correlated_delivery_registration_batches(records)
    initial_instant = records[0].instant if records else 0
    initial_registration_batch = True
    registrations_started = False
    for position, record in enumerate(records):
        initial_registration_batch, registrations_started = _advance_initial_registration_batch(
            record,
            initial_registration_batch=initial_registration_batch,
            registrations_started=registrations_started,
        )
        _apply_delivery_registration(
            armed,
            record,
            initial_registration_batch=initial_registration_batch,
            initial_instant=initial_instant,
        )
        if isinstance(record, (ExternalEventDelivered, ScopedDeliveryDropped, ScopedDeliveryQuarantined)):
            _validate_delivery_tokens(
                record.tokens,
                f"replay divergence: {type(record).__name__} identity {record.identity!r}",
            )
            if isinstance(record, ExternalEventDelivered):
                if not armed.get(record.source):
                    raise ValueError(
                        f"replay divergence: accepted delivery identity {record.identity!r} source "
                        f"{record.source} had no armed delivery registration"
                    )
                expected = FiringBegun(
                    record.source,
                    occurrence=record.occurrence,
                    scope=record.scope,
                    instant=record.instant,
                )
                following = records[position + 1] if position + 1 < len(records) else None
                if following != expected:
                    msg = (
                        "replay divergence: accepted delivery identity "
                        f"{record.identity!r} requires an immediately following matching "
                        f"FiringBegun {expected!r}; found {following!r}"
                    )
                    raise ValueError(msg)
            if record.identity in accepted:
                raise ValueError(
                    f"replay divergence: delivery identity {record.identity!r} accepted twice — the single "
                    f"writer accepts an identity once and answers redelivery from that accepted fact"
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
    records = tuple(history)
    _validate_correlated_delivery_registration_batches(records)
    initial_instant = records[0].instant if records else 0
    initial_registration_batch = True
    registrations_started = False
    for record in records:
        initial_registration_batch, registrations_started = _advance_initial_registration_batch(
            record,
            initial_registration_batch=initial_registration_batch,
            registrations_started=registrations_started,
        )
        _apply_delivery_registration(
            armed,
            record,
            initial_registration_batch=initial_registration_batch,
            initial_instant=initial_instant,
        )
    return armed
