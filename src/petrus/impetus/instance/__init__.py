"""
The Instance: one running Petrinet Instance.

An ``Instance`` holds a net, its live state — per-place pair-queues of
``(token, entry instant)``, maintained incrementally by folding exactly the
movement records it appends; the marking and the timer anchors are its two
views — and its event history. It
computes enabled candidates, lets the scheduler pick one, fires it through the
begin/end lifecycle, and appends the resulting records. The history is
injectable at construction — hand it a durable backend (e.g.
``petrus.impetus.history_store.JsonlHistoryStore``) and every append is durable as it
happens, committed before any other instance state moves; after a crash,
``resume`` rebuilds a live instance from that recorded history and continues
the same file. External events enter
through ``deliver`` — the ingress seam, gated by the delivery
registrations: one per source transition opens at construction (the "default"
key), a handler's result envelope opens and closes further ones (the
``HandlerResult`` envelope — handlers drive the lifecycle), ``seal`` is the
runtime-policy close-all, and delivery requires an armed delivery
registration. Every delivery carries a stable identity — supplied by the
ingress adapter, or derived as the occurrence's self-identity — recorded on
the ``ExternalEventDelivered`` fact and enforced at this door: a redelivered
identity returns the prior acknowledgement, appending nothing [DR 2026-07-14
source-delivery-projection-and-identity].
Instance status is a derived projection over the history, never stored.

The instance is the history's single writer, and with that the keeper of the
clock watermark: every appending method takes an optional ``at`` instant
(``None`` advances nothing; an earlier instant clamps to the watermark —
monotone, never rejected), every record is stamped with the effective instant,
and any record advances the clock. The kernel never reads a wall clock; a
``Engine``, with its ``Clock``, hosts nonblocking advancement, supplying
instants and turning an observed ``next_maturation`` into ``wake`` calls
[DR 2026-07-08 time-projection-virtual-clock-watermark].

The Instance resolves declared guard, handler, filter, and completion symbols
at construction. Their Petri-aware contracts and CEL compiler live in
``petrus.impetus.binding``; a transition with no handler symbol is default-bound to
its pure ``passthrough``.

Every firing crosses the firing-occurrence seam — ``begin`` accounts the
binding's tokens and records the durable occurrence (freezing an impure
firing's ``ActivityRequested`` in the same batch), Dispatch runs
the activity and ``record_activity_completion`` freezes its terminal result,
and ``complete``/``fail`` commit the terminal outcome [ADR 0007, ADR 0012;
DR 2026-07-14 activity-invocation-runtime-seam]. ``step`` and ``deliver`` are
the inline drivers over the pure half of the seam: begin, run the bound
handler here, commit — a raising handler records its terminal failure and
propagates (halt-on-failure is this inline driver's policy, not net
semantics); an ActivityHandler-bound transition needs Dispatch,
so ``step`` refuses it and a source transition can never bind one. The
pluggable substrate lives in ``petrus.motus.dispatch`` and whole-action driving
remains private implementation pending the Engine–Instance ownership decision.
"""

from __future__ import annotations

# Python imports
import json
import warnings
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from types import MappingProxyType
from uuid import uuid7

# Internal imports
import petrus.telemetry as telemetry
from petrus.motus.activity import ActivityFailure, ActivityInvocation
from petrus.impetus.binding import ActivityHandler, Handler, HandlerResult, passthrough
from petrus.impetus.binding.cel import compile_completion, compile_filter, compile_guard
from petrus.impetus.petrinet import (
    AnonymousDeclaration,
    Binding,
    Cel,
    ConsumedTokens,
    Filter,
    Guard,
    ReadTokens,
    begin_firing as _begin_movement,
    candidates,
    complete_firing as _complete_movement,
    next_maturation,
)
from petrus.impetus.instance.firing import (
    FiringOutcome,
    FiringOccurrence,
    Scheduler,
    begin_firing as begin_firing,
    complete_firing as complete_firing,
    replay_in_flight,
    replay_projection_pending,
    replay_terminal_activity,
    select_conservative,
)
from petrus.impetus.history import (
    ActivityCompleted,
    ActivityFailed,
    ActivityRequested,
    CandidateSelected,
    ExternalEventDelivered,
    FiringBegun,
    FiringCompleted,
    FiringFailed,
    InstanceCreated,
    Record,
    DeliveryRegistration,
    DeliveryRegistrationClosed,
    DeliveryRegistrationOpened,
    TimerMatured,
    TokensConsumed,
    TokensInitialized,
    TokensProduced,
    TokensRead,
    apply_movement,
    replay_accepted_identities,
    replay_armed,
    replay_instance_identity,
    replay_next_occurrence,
    replay_queues,
    replay_watermark,
)
from petrus.impetus.history_store import HistoryStore, InMemoryHistoryStore
from petrus.impetus.petrinet import Marking, Token, TokenQueue
from petrus.impetus.petrinet import ArcMode, FilterDeclaration, Instant, Net, NetPath, NetUri

# A completion-condition implementation: a pure boolean over the marking.
type Completion = Callable[[Marking], bool]

_MISSING_IMPLEMENTATION = object()


def _implementation_for(
    declaration: str | AnonymousDeclaration,
    uri: NetUri,
    supplied: Mapping[str | NetUri, object],
    subject: str,
):
    """Resolve one exact declaration or its named shared fallback, never both."""
    exact = uri in supplied
    named = isinstance(declaration, str) and declaration in supplied
    if exact and named:
        raise ValueError(
            f"{subject} declaration {uri} has both an exact implementation and local symbol {declaration!r}"
        )
    if exact:
        return supplied[uri]
    if named:
        return supplied[declaration]
    return _MISSING_IMPLEMENTATION


# The operational shadow of this module's appends [ES-020]: one emit per
# committed fact batch, AFTER the append — telemetry speaks only appended
# truth — stamped with the record's virtual instant, never a wall clock
# (which this kernel does not read; wall-clock spans belong to the driving
# runtime and the backends). Never consulted by any semantics.
log = telemetry.get_logger("impetus")


def _instance_log(net: Net, instance_id: str | None) -> telemetry.TelemetryLogger:
    """The instance's bound logger: every event stamped with the identity (``instance=``) and, when the definition is named, the kind (``net=``). Unbound only for a pre-identity legacy resume."""
    fields: dict[str, str] = {}
    if instance_id is not None:
        fields["instance"] = instance_id
    if net.name is not None:
        fields["net"] = net.name
    return log.bind(**fields) if fields else log


@dataclass(frozen=True)
class PriorAcknowledgement:
    """
    The delivery door's answer to a transport redelivery [DR 2026-07-14
    source-delivery-projection-and-identity]: this ``identity`` was already
    accepted, by the delivery that minted ``occurrence``. Not a firing — the
    caller tells the two apart by type — and minting one appends nothing and
    burns no id: duplicate attempts are operational telemetry, never
    canonical history.
    """

    identity: str
    occurrence: int


def _source_transitions(net: Net) -> list[NetPath]:
    """The net's source transitions in stable (string) order — the one spelling of the registration surface's key set, shared by both constructors."""
    return sorted((path for path in net.transitions if net.is_source(path)), key=str)


def _canonical_payload(value: object, rejection: str) -> object:
    """
    The canonical snapshot of an activity payload (invocation ``input``, or a
    terminal activity ``result``), taken at the writer's door BEFORE anything
    freezes or appends: a round trip through the payload's JSON
    representation — the durable spelling — so the value the instance
    retains IS the value the record holds. Three consequences, each
    deliberate: the writer owns a copy (later caller mutation cannot diverge
    the live projection from the durable record); JSON-lossy shapes
    canonicalize once (a tuple becomes its list form here, so the
    idempotent-acknowledgement value equality survives a durable round
    trip); and a value with no JSON spelling — a Token, Binding, Marking, or
    any other net object — fails loud here, before any append (the
    invocation is Petri-agnostic by ruling: never net state). Deliberate
    asymmetry with ordinary token-data doors: they retain the caller's value,
    so JSON-faithfulness remains their documented durability constraint
    (``petrus.impetus.history.codec``, pinned by its round-trip tests). Delivery
    idempotency is keyed by the explicit ``identity`` string, while an exact
    redelivery additionally compares the retained source and tokens and
    refuses changed content [DR 2026-07-14
    source-delivery-projection-and-identity]. A protocol adapter may
    canonicalize before that door — Fabric does — but the kernel
    does not silently rewrite ordinary token data. Here activity-payload
    equality is independently load-bearing: K6's acknowledge-or-conflict
    reads it.
    """
    try:
        return json.loads(json.dumps(value))
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"{rejection}: the payload must be JSON-faithful — objects, arrays, strings, numbers, booleans, "
            f"null — and never net state; {error}"
        ) from None


def _validate_binding_shape(net: Net, binding: Binding, rejection: str) -> None:
    """
    The one home of the begin-batch shape rule, writer and replay alike: a
    binding carries exactly one consume selection per consume arc and one
    read selection per read arc — in input-arc order, on each arc's place,
    weight tokens each. ``begin`` enforces it before anything is appended,
    and ``resume`` re-checks it on rebuilt bindings, so the single writer
    can never append a begin batch its own resume would refuse: replay
    validates only what the live writer could have written [convention 48],
    which binds the writer to refuse what replay would reject. (A source
    binding has no input arcs and passes trivially — its partition guards
    are the doors'.)
    """
    for mode, selections, noun in (
        (ArcMode.CONSUME, binding.consumed, "consume"),
        (ArcMode.READ, binding.read, "read"),
    ):
        arcs = tuple(arc for arc in net.inputs(binding.transition) if arc.mode is mode)
        if tuple(place for place, _ in selections) != tuple(arc.source for arc in arcs) or any(
            len(tokens) != arc.weight for arc, (_, tokens) in zip(arcs, selections)
        ):
            raise ValueError(
                f"{rejection}: its {noun} selections do not match the transition's {noun} arcs — "
                f"a live begin takes one {noun} selection per arc, in input-arc order, weight tokens each"
            )


class CompletionEvaluationWarning(UserWarning):
    """The completion condition raised while evaluating the quiescent marking; status read it as not holding."""


class Status(StrEnum):
    """Derived four-valued instance status (plus neutral TERMINATED)."""

    RUNNING = "running"
    TERMINATED = "terminated"
    COMPLETED = "completed"
    STUCK = "stuck"
    AWAITING = "awaiting"


class Instance:
    """A running execution of a net definition."""

    def __init__(
        self,
        net: Net,
        marking: Marking | None = None,
        scheduler: Scheduler = select_conservative,
        guards: Mapping[str | NetUri, Guard] | None = None,
        handlers: Mapping[str | NetUri, Handler | ActivityHandler] | None = None,
        filters: Mapping[str, Filter] | None = None,
        completions: Mapping[str, Completion] | None = None,
        at: Instant = 0,
        history: HistoryStore | None = None,
        instance_id: str | None = None,
    ):
        self.net = net
        # The instance identity [ES-020/DEC-026]: unique per instance —
        # caller-supplied (a webhook tenant, a saga id — also what a caller
        # hands the postgres backend and the Absurd adapter, so all three
        # surfaces key on one identity) or minted here. Recorded below as
        # the history's first fact (``InstanceCreated``): identity survives
        # a crash because resume derives it from the record, never from a
        # re-supplied argument — the autogenerated id is deterministic under
        # replay for exactly that reason. Telemetry stamps it on every event.
        # uuid7 by Navigator ruling (2026-07-17): minted ids sort by creation
        # time across a fleet. The stated concession: uuid7 embeds wall-clock
        # milliseconds, the one wall-clock read this kernel makes — into an
        # opaque identity only, never a semantic field; the record's own time
        # axis stays the virtual ``instant``.
        self.instance_id = instance_id if instance_id is not None else uuid7().hex
        self._log = _instance_log(net, self.instance_id)
        marking = marking if marking is not None else Marking()
        for place, tokens in marking:
            declaration = net.places.get(place)
            if declaration is None or declaration.color is None:
                continue
            mismatch = next((token for token in tokens if token.color != declaration.color), None)
            if mismatch is not None:
                raise ValueError(
                    f"initial marking for place {place} requires color {declaration.color!r}, "
                    f"got {mismatch.color!r} on {mismatch!r}"
                )
        self._scheduler = scheduler
        # The clock watermark starts at the construction instant — the entry
        # instant the initial marking anchors to (default 0, the logical
        # epoch; a wall-clock caller passes its own instants throughout).
        self._watermark: Instant = at
        self._bind_symbols(guards, handlers, filters, completions)
        # The persistence seam: the history is injectable, and a durable
        # backend (e.g. petrus.impetus.history_store.JsonlHistoryStore) makes every
        # append durable from the first record — construction records and
        # deliver()'s inline firings included. Construction takes a fresh
        # history only: it appends the instance's initial records below;
        # a recorded history is resume()'s, never built over a second
        # beginning. A backend that joins a caller-held transaction makes
        # the whole instance transactional with it: a rollback retracts
        # appended facts this instance's live state (watermark, marking,
        # occurrence counter, in-flight) already advanced on — the caller
        # discards the instance together with the backend and reconstructs
        # via resume() over a freshly loaded history.
        if history is not None and len(history):
            raise ValueError(
                f"cannot construct an Instance over a recorded history ({len(history)} records): "
                f"construction appends the instance's initial records; a recorded history is for resume()"
            )
        self.history = history if history is not None else InMemoryHistoryStore()
        # One delivery registration per source transition auto-opens
        # at instantiation, under the well-known "default" key (Navigator
        # rulings, slices 8 and 10b): the runtime may deliver external events
        # while the source holds an armed registration. Handlers open and
        # close further registrations through their result envelopes; open
        # and close are recorded process facts — status can flip on a close
        # with zero net activity. The armed keys per source are a projection
        # the DeliveryRegistrationOpened/DeliveryRegistrationClosed records are the authority
        # of, never independent truth. The initial records commit as one
        # batch, like every appending door's.
        sources = _source_transitions(net)
        self._armed: dict[NetPath, set[str]] = {source: {"default"} for source in sources}
        initial: list[Record] = [InstanceCreated(self.instance_id, name=net.name, instant=at)]
        initial.extend(TokensInitialized(place, tokens, instant=at) for place, tokens in marking)
        initial.extend(DeliveryRegistrationOpened(source, "default", occurrence=None, instant=at) for source in sources)
        self.history.extend(initial)
        # The primary live state: per-place pair-queues of (token, entry
        # instant), maintained incrementally by folding exactly the movement
        # records this instance appends — the same fold resume replays whole
        # (``replay_queues``), so live state IS the projection, kept current.
        # The marking and the entry instants are its two views.
        self._queues: dict[NetPath, TokenQueue] = {}
        for record in initial:
            apply_movement(self._queues, record)
        # The firing-occurrence seam's working state: ids mint monotonically at
        # the initiation record, and the in-flight set — begun without ended —
        # is a projection the begin/complete/fail records are the authority of.
        # The frozen results are the projection the ActivityCompleted records
        # are the authority of: one terminal activity fact per in-flight
        # impure occurrence, held for complete() to project. The terminal
        # index is its ended sibling — the ActivityCompleted/ActivityFailed
        # facts of ended occurrences, answering late redeliveries — and the
        # accepted identities are the ExternalEventDelivered projection the
        # delivery door's idempotent acceptance reads. Each rebuilds at
        # resume from exactly its records.
        self._next_occurrence = 1
        self._in_flight: dict[int, FiringOccurrence] = {}
        self._frozen_results: dict[int, object] = {}
        self._terminal_activity: dict[int, object] = {}
        self._accepted_identities: dict[str, ExternalEventDelivered] = {}
        self._log.emit(
            "instance_created",
            places=len(net.places),
            transitions=len(net.transitions),
            records=len(initial),
            instant=at,
        )

    # Complexity exception: reviewed as the single fail-fast symbol-binding boundary.
    def _bind_symbols(  # noqa: C901
        self,
        guards: Mapping[str | NetUri, Guard] | None,
        handlers: Mapping[str | NetUri, Handler | ActivityHandler] | None,
        filters: Mapping[str, Filter] | None,
        completions: Mapping[str, Completion] | None,
    ) -> None:
        """The binding layer's one home, shared by both constructors: resolve every declared symbol and inline expression of ``self.net`` to its implementation, fail-fast."""
        net = self.net
        handler_inputs = dict(handlers or {})
        resolved_handlers: dict[NetUri, Handler | ActivityHandler] = {}
        missing_handlers = []
        for transition in net.transitions.values():
            declaration = transition.handler
            if declaration is None:
                continue
            uri = net.handler_uri(transition.path)
            assert uri is not None
            implementation = _implementation_for(declaration, uri, handler_inputs, "handler")
            if implementation is _MISSING_IMPLEMENTATION:
                missing_handlers.append(declaration if isinstance(declaration, str) else str(uri))
            else:
                resolved_handlers[uri] = implementation
        if missing_handlers:
            raise ValueError(f"handler declaration(s) with no implementation: {sorted(missing_handlers)}")
        self._handlers: Mapping[NetUri, Handler | ActivityHandler] = MappingProxyType(resolved_handlers)
        # The refined purity classification [DR 2026-07-14 source-delivery-
        # projection-and-identity]: a source transition locally and atomically
        # projects its delivered fact — a plain-callable projection is its
        # only legal binding, and an ActivityHandler (recoverable impure
        # work) is refused fail-fast, here, where symbols resolve.
        for transition in net.transitions.values():
            uri = net.handler_uri(transition.path)
            if uri is not None and net.is_source(transition.path) and isinstance(self._handlers[uri], ActivityHandler):
                raise ValueError(
                    f"handler declaration {uri} binds an ActivityHandler to source transition "
                    f"{transition.path}: a source transition locally and atomically projects its delivered "
                    f"fact — recoverable impure work belongs in a downstream handled transition "
                    f"[DR 2026-07-14 source-delivery-projection-and-identity]"
                )
        guard_inputs = dict(guards or {})
        resolved: dict[NetUri, Guard] = {}
        missing_guards = []
        for transition in net.transitions.values():
            scope = {arc.source for arc in net.inputs(transition.path) if arc.mode is not ArcMode.INHIBIT}
            for declaration, uri in zip(transition.guards, net.guard_uris(transition.path)):
                if isinstance(declaration, Cel):
                    if uri in guard_inputs:
                        raise ValueError(f"inline guard declaration {uri} already supplies its Cel implementation")
                    resolved[uri] = compile_guard(declaration, transition.path, scope)
                    continue
                implementation = _implementation_for(declaration, uri, guard_inputs, "guard")
                if implementation is _MISSING_IMPLEMENTATION:
                    missing_guards.append(declaration if isinstance(declaration, str) else str(uri))
                else:
                    resolved[uri] = implementation
        if missing_guards:
            raise ValueError(f"guard declaration(s) with no implementation: {sorted(missing_guards)}")
        self._guards: Mapping[NetUri, Guard] = MappingProxyType(resolved)
        # Filters resolve both declared encodings to one implementation per
        # declaration: named symbols from the supplied mapping, inline Cel
        # expressions compiled here at construction (an invalid expression
        # never runs).
        filters = filters or {}
        declared_filters = {arc.filter for arc in net.arcs if arc.filter is not None}
        missing = {f for f in declared_filters if isinstance(f, str)} - filters.keys()
        if missing:
            raise ValueError(f"filter symbol(s) with no implementation: {sorted(missing)}")
        self._filters: Mapping[FilterDeclaration, Filter] = MappingProxyType(
            {f: (filters[f] if isinstance(f, str) else compile_filter(f)) for f in declared_filters}
        )
        # The net's one optional #completion declaration resolves the same two
        # encodings: a named symbol from the supplied mapping, an inline Cel
        # compiled here — where an unresolvable place reference, like an
        # invalid expression, is a declared mismatch that never evaluates.
        completions = completions or {}
        self._completion: Completion | None
        if isinstance(net.completion, str) and net.completion not in completions:
            raise ValueError(f"completion symbol with no implementation: {net.completion!r}")
        if net.completion is None:
            self._completion = None
        elif isinstance(net.completion, str):
            self._completion = completions[net.completion]
        else:
            self._completion = compile_completion(net.completion, net.places)

    @classmethod
    # Complexity exception: reviewed as one history-to-live-state reconstruction boundary.
    def resume(  # noqa: C901
        cls,
        net: Net,
        history: HistoryStore,
        scheduler: Scheduler = select_conservative,
        guards: Mapping[str | NetUri, Guard] | None = None,
        handlers: Mapping[str | NetUri, Handler | ActivityHandler] | None = None,
        filters: Mapping[str, Filter] | None = None,
        completions: Mapping[str, Completion] | None = None,
    ) -> Instance:
        """
        Rebuild a live instance from its recorded history — crash-resume: the
        history is the whole truth of an instance, so every piece of live
        state is computed as the projection the records are the authority of.
        The marking replays from the movements, the armed registrations from
        the open/close records, the watermark is the last record's instant,
        the occurrence counter continues past every recorded id (an orphan
        initiation's included — a minted id is a fact, never re-minted), and
        the occurrences begun without ending come back in flight, real
        ``FiringOccurrence`` values for the driver to ``complete()`` or
        ``fail()``. The caller re-supplies what records never hold — the net
        and its bound implementations: callables are code, not facts.
        Nothing is appended; the resumed instance keeps appending to the
        same history — hand it the loaded durable backend and the file
        continues across the crash.

        Fail-loud doors, guarding what becomes live state: an empty history
        has nothing to resume (construct an ``Instance`` instead — the
        mirror of ``__init__`` rejecting a recorded history); records that
        would put live state on nodes this net does not have, or misuse ones
        it does (tokens on a foreign place, delivery registrations off a
        source, a scheduled selection on a source, a delivery on a
        non-source, consumed or read records that do not match the
        transition's consume or read arcs, an instant stepping backwards),
        are a foreign or corrupted trace. An in-flight occurrence's rebuilt
        binding carries the exact recorded read selections — begin records
        them (debt 2026-07-09T2330Z, recording half), so a resumed handler
        observes what the crashed one observed, never the live marking.
        Records that leave no live state behind (an ended occurrence,
        whatever it names) are not audited here — whole-trace auditing is a
        validation-layer posture, not this door's
        (debt 2026-07-09T2310Z's kernel-wide-validation family).
        """
        if not len(history):
            raise ValueError("cannot resume from an empty history: nothing is recorded — construct an Instance instead")
        instance = cls.__new__(cls)
        instance.net = net
        # The identity is derived, never re-supplied: the InstanceCreated
        # fact holds it (None only for a pre-identity legacy trace, which
        # resumes unidentified). A recorded net name that disagrees with the
        # re-supplied net's is a foreign trace, refused like any other
        # node-level mismatch this door guards.
        identity = replay_instance_identity(history)
        if identity is not None and identity.name is not None and net.name is not None and identity.name != net.name:
            raise ValueError(
                f"cannot resume: the history records net name {identity.name!r} but the supplied net is "
                f"named {net.name!r} — a foreign trace"
            )
        instance.instance_id = identity.instance if identity is not None else None
        instance._log = _instance_log(net, instance.instance_id)
        instance._scheduler = scheduler
        instance._bind_symbols(guards, handlers, filters, completions)
        instance.history = history
        instance._queues = replay_queues(history)
        for place, _ in instance.marking:
            if place not in net.places:
                raise ValueError(f"cannot resume: token records on {place}: not a place of this net")
        instance._watermark = replay_watermark(history)
        armed = replay_armed(history)
        for source in armed:
            if source not in net.transitions:
                raise ValueError(
                    f"cannot resume: delivery-registration records on {source}: not a transition of this net"
                )
            if not net.is_source(source):
                raise ValueError(
                    f"cannot resume: delivery-registration records on transition {source}: it has input arcs — "
                    f"only a source transition has delivery registrations"
                )
        instance._armed = {source: armed.get(source, set()) for source in _source_transitions(net)}
        in_flight = replay_in_flight(history)
        for occurrence in in_flight:
            rejection = f"cannot resume firing occurrence {occurrence.id} ({occurrence.binding.transition})"
            transition = occurrence.binding.transition
            if transition not in net.transitions:
                raise ValueError(f"{rejection}: not a transition of this net")
            # The begin/deliver door partition, enforced on the rebuilt
            # traffic too [convention 36]: the live instance can record
            # neither a scheduled selection on a source nor a delivery on a
            # non-source.
            if net.is_source(transition) and not occurrence.binding.delivered:
                raise ValueError(
                    f"{rejection}: a scheduled selection on a source transition — a source fires only through deliver()"
                )
            if not net.is_source(transition) and occurrence.binding.delivered:
                raise ValueError(
                    f"{rejection}: an external event on a transition with input arcs — "
                    f"only a source transition takes delivery"
                )
            # The begin-batch shape rule, re-checked on the rebuilt binding —
            # the same helper begin() enforces at the writing door, so a
            # trace whose consume or read facts disagree with the arcs
            # rebuilds a binding begin() could never have minted.
            _validate_binding_shape(net, occurrence.binding, rejection)
            # Code-vs-record coherence for the activity seam: the live writer
            # freezes ActivityRequested in every impure begin batch and never
            # in a pure one, so a rebuilt occurrence must agree with the
            # re-supplied binding's classification — a mismatch is a foreign
            # trace or the wrong bindings, either way not resumable silently.
            activity_bound = isinstance(instance.bound_handler(transition), ActivityHandler)
            if occurrence.invocation is not None and not activity_bound:
                raise ValueError(
                    f"{rejection}: its begin batch froze an activity request, but the transition is "
                    f"not bound to an ActivityHandler — projection needs the handler that prepared it"
                )
            if occurrence.invocation is None and activity_bound:
                raise ValueError(
                    f"{rejection}: the transition binds an ActivityHandler, but the begin batch froze "
                    f"no ActivityRequested — the live writer always freezes the request at begin"
                )
        instance._in_flight = {occurrence.id: occurrence for occurrence in in_flight}
        instance._frozen_results = replay_projection_pending(history)
        instance._terminal_activity = replay_terminal_activity(history)
        instance._accepted_identities = replay_accepted_identities(history)
        instance._next_occurrence = replay_next_occurrence(history)
        instance._log.emit(
            "instance_resumed",
            records=len(history),
            watermark=instance._watermark,
            in_flight=len(instance._in_flight),
        )
        return instance

    @property
    def marking(self) -> Marking:
        """The current marking — the time-blind view of the primary pair-queues, derived on every read, never stored beside them."""
        return Marking({place: queue.tokens for place, queue in self._queues.items()})

    @property
    def watermark(self) -> Instant:
        """The clock watermark — "now": the instant of the latest appended record (the construction instant before any)."""
        return self._watermark

    def _instant(self, at: Instant | None) -> Instant:
        """The effective instant an append would take: ``None`` means the watermark (no advance); an earlier instant clamps to it (monotone, never rejected). A pure read — committing is ``_advance``'s."""
        return self._watermark if at is None else max(at, self._watermark)

    def _advance(self, instant: Instant) -> None:
        """Commit an append's effective instant — an ``_instant`` reading its caller already transformed with — advancing the watermark: the one home of the watermark-is-the-latest-append identity. Called exactly after a method's append has committed (advance-after-append, never before): a durable backend may raise, and a raising append must leave the watermark still speaking only appended records."""
        self._watermark = instant

    def _entry_instants(self) -> dict[NetPath, tuple[Instant, ...]]:
        """Each place queue's recorded entry instants — the Delay anchors: the time view of the same pair-queues the marking projects, read off live state (never re-folded from the history)."""
        return {place: queue.instants for place, queue in self._queues.items() if queue}

    def candidates(self):
        """Enabled firing candidates under the current marking at the watermark, in scheduler order."""
        return candidates(self.net, self.marking, self._guards, self._filters, self._watermark, self._entry_instants())

    def enabled_transitions(self) -> list[NetPath]:
        """Distinct enabled transitions, in stable order — a transition enabled under many bindings appears once."""
        seen: list[NetPath] = []
        for binding in self.candidates():
            if binding.transition not in seen:
                seen.append(binding.transition)
        return seen

    @property
    def armed(self) -> Mapping[NetPath, frozenset[str]]:
        """
        The armed delivery registrations, per source transition — the
        read a driver decides delivery by. The name is the whole contract: an
        entry means ``deliver`` can land on that door, so the mapping's truth
        IS the any-armed judgment and a fully sealed instance reads empty —
        whether a node is a source at all stays the net's question
        (``is_source``). A structurally read-only snapshot each read; the
        open/close records stay the only way this projection moves.
        """
        return MappingProxyType({source: frozenset(keys) for source, keys in self._armed.items() if keys})

    @property
    def in_flight(self) -> tuple[FiringOccurrence, ...]:
        """The firing occurrences begun and not yet ended, in begin order — the working leg of quiescence: an instance with a token out with a worker is working, not done."""
        return tuple(self._in_flight.values())

    @property
    def projection_pending(self) -> tuple[FiringOccurrence, ...]:
        """
        The in-flight occurrences whose terminal activity result is frozen
        (``ActivityCompleted`` committed) but whose firing has not ended, in
        begin order — ``complete()`` retries deterministic projection alone;
        the activity is never re-invoked [DR 2026-07-14
        activity-invocation-runtime-seam]. Its complement is the outbox: an
        in-flight impure occurrence NOT here still owes its Dispatch
        a dispatch of ``occurrence.invocation``.
        """
        return tuple(occurrence for occurrence in self._in_flight.values() if occurrence.id in self._frozen_results)

    def begin(self, binding: Binding, at: Instant | None = None) -> FiringOccurrence:
        """
        Begin a durable firing occurrence for ``binding``: mint the occurrence id,
        record the selection (the initiation record belongs to the initiating
        site — this is the scheduler-side door; delivery initiates with an
        external-event record instead), and account the consumed tokens out of
        the marking [ADR 0007]. For an ActivityHandler-bound transition,
        ``prepare(binding)`` runs FIRST — before anything is appended, so a
        prepare failure is a code failure, not a net fact — and the resolved
        invocation joins the begin batch as ``ActivityRequested``, the
        authoritative outbox [DR 2026-07-14 activity-invocation-runtime-seam].
        Raises on a foreign transition, a source
        transition (never scheduled — it fires only through ``deliver``), a
        delivered binding, a hand-built binding whose selections do not match
        the transition's consume/read arcs (the shape rule resume re-checks —
        the writer never appends a begin batch its own resume refuses), a
        prepared invocation that is not an ``ActivityInvocation`` or whose
        supplied identity sits in the writer-reserved ``occurrence-``
        namespace [convention 65], and a
        stale selection whose tokens are gone — validated before anything is
        appended, so the history takes no partial fact.
        """
        if binding.transition not in self.net.transitions:
            raise ValueError(f"cannot begin firing {binding.transition}: not a transition of this net")
        if self.net.is_source(binding.transition):
            raise ValueError(
                f"cannot begin firing {binding.transition}: a source transition is never scheduled — "
                f"it fires only through deliver()"
            )
        if binding.delivered:
            raise ValueError(
                f"cannot begin a delivered binding for {binding.transition}: a source firing enters through deliver()"
            )
        _validate_binding_shape(self.net, binding, f"cannot begin firing {binding.transition}")
        invocation = self._prepared_invocation(binding)
        try:
            return self._begin_occurrence(
                binding,
                at,
                lambda occurrence, instant: CandidateSelected(
                    binding.transition, occurrence=occurrence, instant=instant
                ),
                invocation=invocation,
            )
        except ValueError as error:
            raise ValueError(f"cannot begin firing {binding.transition}: stale selection — {error}") from error

    def _prepared_invocation(self, binding: Binding) -> ActivityInvocation | None:
        """
        The prepare half of the activity seam, run before anything is
        appended: ``None`` for a pure binding; for an ActivityHandler, the
        prepared invocation — shape-checked (this is the seam where
        handler-owned data enters the kernel [convention 28]) and its
        supplied identities checked against the writer-reserved
        ``occurrence-`` namespace, where the writer mints the derived
        self-identity [convention 65].
        """
        handler = self.bound_handler(binding.transition)
        if not isinstance(handler, ActivityHandler):
            return None
        invocation = handler.prepare(binding)
        if not isinstance(invocation, ActivityInvocation):
            raise ValueError(
                f"cannot begin firing {binding.transition}: prepare must return an ActivityInvocation, "
                f"got {invocation!r}"
            )
        for name, value in (("correlation", invocation.correlation), ("idempotency", invocation.idempotency)):
            if value is not None and value.startswith("occurrence-"):
                raise ValueError(
                    f"cannot begin firing {binding.transition}: {name} {value!r} uses the writer-reserved "
                    f"'occurrence-' prefix — the derived self-identity namespace; supply an identity "
                    f"outside it, or None for the writer to derive"
                )
        # The canonical snapshot: the input the occurrence retains and the
        # record freezes is the durable spelling, owned by the writer.
        return replace(
            invocation,
            input=_canonical_payload(
                invocation.input, f"cannot begin firing {binding.transition}: invalid activity input"
            ),
        )

    def _begin_occurrence(
        self,
        binding: Binding,
        at: Instant | None,
        initiation: Callable[[int, Instant], Record],
        invocation: ActivityInvocation | None = None,
    ) -> FiringOccurrence:
        """
        The one home of an occurrence's birth: compute the effective instant,
        account the begin (which may fail loud — nothing appended then),
        resolve an impure occurrence's ``None`` identities to the derived
        self-identity the minted id names, and commit in one batch — the
        door's ``initiation`` record first, minting the id, the occurrence's
        begin records after it, an impure occurrence's ``ActivityRequested``
        last, the occurrence in flight.
        """
        instant = self._instant(at)
        # The Petrinet transform validates and computes movements without
        # knowing History. Instance alone narrates those effects; committed
        # state still folds from the records, live and replay alike.
        effects, _ = _begin_movement(self.marking, binding)
        narrated: list[Record] = [FiringBegun(binding.transition, occurrence=self._next_occurrence, instant=instant)]
        for effect in effects:
            if isinstance(effect, ConsumedTokens):
                narrated.append(
                    TokensConsumed(effect.place, effect.tokens, occurrence=self._next_occurrence, instant=instant)
                )
            elif isinstance(effect, ReadTokens):
                narrated.append(
                    TokensRead(effect.place, effect.tokens, occurrence=self._next_occurrence, instant=instant)
                )
            else:
                raise TypeError(f"unknown Petrinet begin effect: {effect!r}")
        records = tuple(narrated)
        if invocation is not None:
            identity = f"occurrence-{self._next_occurrence}"
            correlation = invocation.correlation if invocation.correlation is not None else identity
            idempotency = invocation.idempotency if invocation.idempotency is not None else identity
            invocation = replace(
                invocation,
                correlation=correlation,
                idempotency=idempotency,
            )
            records = records + (
                ActivityRequested(
                    binding.transition,
                    activity=invocation.activity,
                    input=invocation.input,
                    policy=invocation.policy,
                    correlation=correlation,
                    idempotency=idempotency,
                    occurrence=self._next_occurrence,
                    instant=instant,
                ),
            )
        occurrence = FiringOccurrence(self._next_occurrence, binding, records, invocation=invocation)
        self.history.extend([initiation(occurrence.id, instant), *records])
        self._advance(instant)
        self._next_occurrence += 1
        for record in records:
            apply_movement(self._queues, record)
        self._in_flight[occurrence.id] = occurrence
        self._log.emit(
            "firing_begun",
            transition=str(binding.transition),
            occurrence=occurrence.id,
            instant=instant,
            impure=invocation is not None,
        )
        return occurrence

    def record_activity_completion(
        self, occurrence: FiringOccurrence, result: object, at: Instant | None = None
    ) -> None:
        """
        Freeze the activity's typed terminal ``result`` as ``ActivityCompleted``
        — its own append, committed BEFORE deterministic projection, so a
        projection bug or crash never repeats completed external work
        [DR 2026-07-14 activity-invocation-runtime-seam]. Only an impure
        in-flight occurrence takes one. The first terminal activity fact wins
        (K6 discipline at the writer): a value-equal re-record is an
        idempotent acknowledgement — no second append, return quietly — and a
        different late result is an operational conflict, refused loud.
        ``result`` is snapshotted canonical at this door — its JSON round
        trip, the durable spelling — so the frozen value never trails a
        caller's later mutation and the acknowledgement's value equality
        survives a durable round trip (a re-recorded tuple acknowledges
        against its frozen list form); a result with no JSON spelling fails
        loud, appending nothing.

        An ENDED occurrence answers from the terminal-result index (the
        ActivityCompleted/ActivityFailed projection, live and rebuilt at
        resume): an at-least-once adapter may redeliver after the firing
        completed, and the redelivery still needs its acknowledgement — a
        canonical-value-equal result returns the prior acknowledgement
        quietly, a different one is an operational conflict, and an
        occurrence that ended in terminal activity failure refuses any late
        result: a failed occurrence cannot retroactively succeed
        [DR 2026-07-14 source-delivery-projection-and-identity — "a
        different late result is an operational conflict"]. Like
        ``_ensure_in_flight``, the ended path knows the occurrence by its
        id: exact for ids this instance minted.
        """
        rejection = (
            f"cannot record an activity completion for firing occurrence {occurrence.id} "
            f"({occurrence.binding.transition})"
        )
        if occurrence.id in self._terminal_activity:
            # The ended-occurrence acknowledgement door: judge the canonical
            # value against the recorded terminal fact, append nothing.
            result = _canonical_payload(result, f"{rejection}: invalid activity result")
            terminal = self._terminal_activity[occurrence.id]
            if isinstance(terminal, ActivityFailure):
                raise ValueError(
                    f"{rejection}: the occurrence ended in terminal activity failure ({terminal.error!r}) — "
                    f"a failed occurrence cannot retroactively succeed, and a different late result is an "
                    f"operational conflict [DR 2026-07-14 source-delivery-projection-and-identity]"
                )
            if terminal == result:
                # the recorded fact already answers this redelivery; acknowledge quietly
                self._log.emit("activity_redelivery_acknowledged", occurrence=occurrence.id)
                return
            raise ValueError(
                f"{rejection}: the occurrence ended with a different result — an operational conflict, not a redelivery"
            )
        self._ensure_in_flight(occurrence, "record an activity completion for")
        if occurrence.invocation is None:
            raise ValueError(
                f"{rejection}: a pure firing runs no activity — complete() takes its handler's result directly"
            )
        result = _canonical_payload(result, f"{rejection}: invalid activity result")
        if occurrence.id in self._frozen_results:
            if self._frozen_results[occurrence.id] == result:
                # the first terminal activity fact won; acknowledge, append nothing
                self._log.emit("activity_redelivery_acknowledged", occurrence=occurrence.id)
                return
            raise ValueError(
                f"{rejection}: a terminal activity fact already exists with a "
                f"different result — an operational conflict, not a redelivery"
            )
        instant = self._instant(at)
        self.history.append(
            ActivityCompleted(occurrence.binding.transition, result, occurrence=occurrence.id, instant=instant)
        )
        self._advance(instant)
        self._frozen_results[occurrence.id] = result
        self._log.emit(
            "activity_result_recorded",
            transition=str(occurrence.binding.transition),
            occurrence=occurrence.id,
            instant=instant,
        )

    def complete(
        self,
        occurrence: FiringOccurrence,
        result: Mapping[NetPath | str, Sequence[Token]] | HandlerResult | None = None,
        at: Instant | None = None,
    ) -> FiringOutcome:
        """
        End the occurrence by committing the atomic completion boundary —
        deposit per output arc contract, the delivery-registration effects the
        envelope carries, the terminal record — one batch.

        Two shapes, split by the occurrence's purity: a PURE occurrence
        completes with its handler's terminal ``result`` (the
        ``HandlerResult`` envelope, or its bare-mapping sugar, normalized here
        at the seam that admits both spellings). An IMPURE occurrence takes
        NO result — its result was frozen by ``record_activity_completion``
        (``ActivityCompleted``, the one source of the result), and this
        method retries deterministic projection from that frozen fact:
        ``handler.project(binding, result)``, then the boundary. Completing an
        impure occurrence with no frozen terminal fact fails loud; a
        projection failure propagates with nothing appended — the occurrence
        stays in flight, projection-pending, for fixed code to retry
        [the decision's Deferred section]. An invalid delivery-registration
        effect likewise fails loud before anything is appended — the history
        takes no partial fact. The occurrence leaves the in-flight set;
        ending it again raises.
        """
        self._ensure_in_flight(occurrence, "complete")
        rejection = f"cannot complete firing occurrence {occurrence.id} ({occurrence.binding.transition})"
        if occurrence.invocation is None:
            if result is None:
                raise ValueError(f"{rejection}: a pure firing completes with its handler's result")
            projected = result
        else:
            if result is not None:
                raise ValueError(
                    f"{rejection}: an impure firing projects its frozen activity result — complete() takes "
                    f"no result; record_activity_completion supplies it"
                )
            if occurrence.id not in self._frozen_results:
                raise ValueError(
                    f"{rejection}: no terminal activity fact is recorded — record_activity_completion first"
                )
            handler = self.bound_handler(occurrence.binding.transition)
            if not isinstance(handler, ActivityHandler):
                raise TypeError(
                    f"{rejection}: its impure occurrence is not bound to an ActivityHandler — recorded and live state disagree"
                )
            projected = handler.project(occurrence.binding, self._frozen_results[occurrence.id])
        envelope = projected if isinstance(projected, HandlerResult) else HandlerResult(tokens=projected)
        armed, closes, opens = self._armed_after(occurrence, envelope)
        instant = self._instant(at)
        # As at begin, Petrinet computes movements and Instance alone narrates
        # the canonical completion batch, including registration policy and
        # terminal lifecycle facts.
        effects, _ = _complete_movement(self.net, self.marking, occurrence.binding.transition, envelope.tokens)
        appended = (
            *(
                TokensProduced(effect.place, effect.tokens, occurrence=occurrence.id, instant=instant)
                for effect in effects
            ),
            *(
                DeliveryRegistrationClosed(
                    registration.source, registration.key, occurrence=occurrence.id, instant=instant
                )
                for registration in closes
            ),
            *(
                DeliveryRegistrationOpened(
                    registration.source, registration.key, occurrence=occurrence.id, instant=instant
                )
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
        self.history.extend(list(appended))
        self._advance(instant)
        for record in appended:
            apply_movement(self._queues, record)
        self._armed = armed
        if occurrence.invocation is not None:
            # The frozen result moves from projection-pending to the ended
            # terminal index: late redeliveries acknowledge against it.
            self._terminal_activity[occurrence.id] = self._frozen_results.pop(occurrence.id)
        del self._in_flight[occurrence.id]
        self._log.emit(
            "firing_completed",
            transition=str(occurrence.binding.transition),
            occurrence=occurrence.id,
            instant=instant,
            records=len(appended),
        )
        return firing

    def _armed_after(
        self, occurrence: FiringOccurrence, envelope: HandlerResult
    ) -> tuple[dict[NetPath, set[str]], tuple[DeliveryRegistration, ...], tuple[DeliveryRegistration, ...]]:
        """
        The armed projection with the envelope's delivery-registration effects
        applied — closes before opens, the ruled apply order, so one result
        can refresh a key. Validation is the side condition: this is the one
        home of ruling 4's effect rules, and a violation raises before the
        caller has appended anything — per effect, each checked against
        the state the earlier ones produced: an effect on an unknown or
        non-source transition, a close of a registration that is not armed,
        an open of one that is. Any projection may carry effects — the
        effect records are canonical facts in the completion batch, and a
        source transition's deterministic projection legitimately closes its
        own registration [DR 2026-07-14 source-delivery-projection-and-
        identity] (the old effects-require-an-impure-handler rule rode the
        retired observed-result record). This is the seam where handler-owned
        data enters the kernel, so the elements are checked like deliver()
        checks tokens.
        """
        rejection = f"cannot complete firing occurrence {occurrence.id} ({occurrence.binding.transition})"
        armed = {source: set(keys) for source, keys in self._armed.items()}
        registrations: list[DeliveryRegistration] = []
        for effect in (*envelope.closes, *envelope.opens):
            if not isinstance(effect, DeliveryRegistration):
                raise ValueError(
                    f"{rejection}: every delivery-registration effect must be a DeliveryRegistration, found {effect!r}"
                )
            if effect.source not in self.net.transitions:
                raise ValueError(
                    f"{rejection}: delivery-registration effect on {effect.source}: not a transition of this net"
                )
            if not self.net.is_source(effect.source):
                raise ValueError(
                    f"{rejection}: delivery-registration effect on transition {effect.source}: it has input arcs — "
                    f"only a source transition has delivery registrations"
                )
            registrations.append(effect)
        closes = tuple(registrations[: len(envelope.closes)])
        opens = tuple(registrations[len(envelope.closes) :])
        for effect in closes:
            if effect.key not in armed[effect.source]:
                raise ValueError(
                    f"{rejection}: close of delivery registration {effect.key!r} on {effect.source}: not armed"
                )
            armed[effect.source].discard(effect.key)
        for effect in opens:
            if effect.key in armed[effect.source]:
                raise ValueError(
                    f"{rejection}: open of delivery registration {effect.key!r} on {effect.source}: already armed"
                )
            armed[effect.source].add(effect.key)
        return armed, closes, opens

    def fail(self, occurrence: FiringOccurrence, error: str, at: Instant | None = None) -> None:
        """
        End the occurrence in terminal failure. The batch is the whole commit:
        for an impure occurrence, ``ActivityFailed`` (exhausted execution)
        and ``FiringFailed`` land together — one semantic fact, whole or not
        at all [convention 45]; a pure occurrence records ``FiringFailed``
        alone. The consumed tokens stay consumed (restoring them would claim
        work never happened) and no retry is implied — retries are the
        Dispatch's, invisible to the net until the terminal outcome,
        and what happens next (halt, compensate, restart) is runtime policy,
        never net semantics. An occurrence whose activity already COMPLETED
        refuses to fail: the external work happened — a projection failure is
        fixed in code and retried from the frozen result, never converted
        into a failed firing [the decision's Deferred section].
        """
        self._ensure_in_flight(occurrence, "fail")
        if occurrence.id in self._frozen_results:
            raise ValueError(
                f"cannot fail firing occurrence {occurrence.id} ({occurrence.binding.transition}): its "
                f"activity already completed — the frozen result stands; fix the projection and retry "
                f"complete() [DR 2026-07-14 activity-invocation-runtime-seam, Deferred]"
            )
        instant = self._instant(at)
        records: list[Record] = []
        if occurrence.invocation is not None:
            records.append(
                ActivityFailed(occurrence.binding.transition, error, occurrence=occurrence.id, instant=instant)
            )
        records.append(FiringFailed(occurrence.binding.transition, error, occurrence=occurrence.id, instant=instant))
        self.history.extend(records)
        self._advance(instant)
        if occurrence.invocation is not None:
            # The terminal index's failure half: a late result meets the
            # recorded ActivityFailed, never a silent "never began it".
            self._terminal_activity[occurrence.id] = ActivityFailure(error)
        del self._in_flight[occurrence.id]
        self._log.emit(
            "firing_failed",
            transition=str(occurrence.binding.transition),
            occurrence=occurrence.id,
            instant=instant,
            error=error,
        )

    def _ensure_in_flight(self, occurrence: FiringOccurrence, verb: str) -> None:
        """A terminal commit takes exactly the occurrence this instance has in flight. Ended and never-begun are told apart by the id — exact for ids this instance minted; a foreign occurrence whose id collides reads as its local twin."""
        if self._in_flight.get(occurrence.id) == occurrence:
            return
        if occurrence.id < self._next_occurrence and occurrence.id not in self._in_flight:
            raise ValueError(
                f"cannot {verb} firing occurrence {occurrence.id} ({occurrence.binding.transition}): "
                f"not in flight — this instance's occurrence {occurrence.id} already ended"
            )
        raise ValueError(
            f"cannot {verb} firing occurrence {occurrence.id} ({occurrence.binding.transition}): this instance never began it"
        )

    def _execute(self, occurrence: FiringOccurrence) -> FiringOutcome:
        """The inline driver's execution — pure projections only (``step`` and ``deliver`` refuse activity transitions before beginning): run the bound handler here and commit its terminal outcome — a raising handler, or a result the commit rejects, records its failure and propagates, loud. (``Engine`` drives the same seam, activities included, through Dispatch.)"""
        handler = self.bound_handler(occurrence.binding.transition)
        if isinstance(handler, ActivityHandler):
            raise TypeError(f"pure firing {occurrence.binding.transition} is bound to an ActivityHandler")
        try:
            result = handler(occurrence.binding, self.net.outputs(occurrence.binding.transition))
            return self.complete(occurrence, result)
        except Exception as error:
            # complete()'s rejection leaves the occurrence in flight for its
            # driver to fail — this inline driver, here.
            if occurrence.id in self._in_flight:
                self.fail(occurrence, repr(error))
            raise

    def step(self, at: Instant | None = None) -> FiringOutcome | None:
        """
        Select and fire one candidate at the effective instant, begin to end,
        inline. Returns the firing outcome, or None if nothing is enabled
        then — in which case nothing was appended and the watermark stays put:
        a fruitless probe is not a fact, and semantic time advances only at
        appends. An ActivityHandler-bound candidate is refused loud before
        anything begins: an activity needs Dispatch, and this
        inline driver holds none — ``Engine`` drives activity transitions.
        """
        prospective = self._instant(at)
        # The prospective-instant evaluation stays on the pure layer: the
        # instance's own candidates() speaks only the watermark, and the
        # judgment below is committed by the selection record or discarded.
        enabled = candidates(self.net, self.marking, self._guards, self._filters, prospective, self._entry_instants())
        binding = self._scheduler(enabled)
        if binding is None:
            return None
        if isinstance(self.bound_handler(binding.transition), ActivityHandler):
            raise ValueError(
                f"cannot step firing {binding.transition}: it binds an ActivityHandler, and this inline "
                f"driver holds no Dispatch — drive it through Engine"
            )
        return self._execute(self.begin(binding, at))

    # Complexity exception: reviewed as one ordered idempotent delivery boundary.
    def deliver(  # noqa: C901
        self,
        source: NetPath | str,
        tokens: Token | Sequence[Token],
        at: Instant | None = None,
        *,
        identity: str | None = None,
    ) -> FiringOutcome | PriorAcknowledgement:
        """
        Deliver an external event to a source transition, firing it.

        The event is recorded as a fact before the firing it initiates. The
        delivered tokens enter the firing as the binding's tokens: the default
        passthrough routes them by color through the output arcs (runtime
        injection is passthrough over the delivered tokens — a Navigator
        ruling); a declared handler receives them and may transform.
        ``identity`` is the delivery's stable identity, supplied by the
        ingress adapter (a webhook's provider event id) [DR 2026-07-14
        source-delivery-projection-and-identity]; when ``None``, the writer
        derives the occurrence's self-identity (``"occurrence-{id}"``) —
        honest that no external identity existed. The ``occurrence-`` prefix
        is therefore writer-reserved: a supplied identity inside it would
        collide with a later derived one, and is refused.

        This door enforces idempotent acceptance: an already-accepted exact
        delivery returns the ``PriorAcknowledgement`` — no second semantic
        record, no token, no id minted — while reusing the identity for a
        changed source or token payload fails as a conflict. That judgment
        precedes current source and registration validation: a one-shot
        registration may have closed after the first commit, and the broker
        retry still needs its acknowledgement [the decision's ruled
        ordering]. Distinct identities are preserved even when their token
        data is equal. Raises on
        a non-source transition, a source with no armed delivery registration, an
        empty delivery, an empty or writer-reserved identity, and a non-Token
        item (this is the seam where outside-world data enters the kernel;
        the other token boundaries trust their declared types — see
        docs/project/debt/items/2026-07-09T2310Z-token-element-validation-is-per-boundary-not-kernel-wide.md).
        """
        path = NetPath(source)
        delivered = (tokens,) if isinstance(tokens, Token) else tuple(tokens)
        if not delivered:
            raise ValueError(f"delivery to {path} requires at least one token")
        for item in delivered:
            if not isinstance(item, Token):
                raise ValueError(f"delivery to {path}: every delivered item must be a Token, found {item!r}")
        if identity is not None:
            # Identity and payload shape run before current source/registration
            # state: everything about that door may have rotted since the
            # first accepted commit, but the recorded fact still distinguishes
            # an exact retry from conflicting identity reuse.
            if not isinstance(identity, str) or not identity:
                raise ValueError(f"delivery to {path}: identity must be a non-empty string, got {identity!r}")
            if identity.startswith("occurrence-"):
                # The derived self-identity's namespace is writer-reserved: a
                # supplied "occurrence-2" would collide with a later derived
                # one, and dedup would collapse two distinct events into one.
                raise ValueError(
                    f"delivery to {path}: identity {identity!r} uses the writer-reserved 'occurrence-' "
                    f"prefix — the derived self-identity namespace; supply the transport's identity outside it"
                )
            if identity in self._accepted_identities:
                prior = self._accepted_identities[identity]
                if prior.source != path or prior.tokens != delivered:
                    self._log.emit(
                        "delivery_conflicted",
                        source=str(path),
                        identity=identity,
                        occurrence=prior.occurrence,
                    )
                    raise ValueError(
                        f"delivery identity conflict for {identity!r}: it was accepted for source {prior.source} "
                        f"with different delivery content"
                    )
                self._log.emit(
                    "delivery_redelivered",
                    source=str(path),
                    identity=identity,
                    occurrence=prior.occurrence,
                )
                return PriorAcknowledgement(identity, prior.occurrence)
        if path not in self.net.transitions:
            raise ValueError(f"cannot deliver to {path}: not a transition of this net")
        if not self.net.is_source(path):
            raise ValueError(
                f"cannot deliver to transition {path}: it has input arcs — only a source transition takes delivery"
            )
        if not self._armed[path]:
            raise ValueError(f"cannot deliver to source transition {path}: no armed delivery registration")
        binding = Binding(path, consumed=(), delivered=delivered)
        # The ingress-side door of the occurrence seam: the external event is the
        # initiation record, minting the occurrence id; the begin accounts
        # nothing (a source firing consumes no selection).
        occurrence = self._begin_occurrence(
            binding,
            at,
            lambda occurrence, instant: ExternalEventDelivered(
                path,
                delivered,
                identity=identity if identity is not None else f"occurrence-{occurrence}",
                occurrence=occurrence,
                instant=instant,
            ),
        )
        # The event fact is committed: the identity is accepted from here —
        # even if the projection below fails, the redelivery is answered by
        # the record, exactly as replay_accepted_identities would answer it.
        accepted_identity = identity if identity is not None else f"occurrence-{occurrence.id}"
        self._accepted_identities[accepted_identity] = ExternalEventDelivered(
            path,
            delivered,
            identity=accepted_identity,
            occurrence=occurrence.id,
            instant=self._watermark,
        )
        self._log.emit(
            "delivery_accepted",
            source=str(path),
            identity=identity if identity is not None else f"occurrence-{occurrence.id}",
            occurrence=occurrence.id,
            tokens=len(delivered),
        )
        return self._execute(occurrence)

    def seal(self, source: NetPath | str, at: Instant | None = None) -> None:
        """
        The runtime-policy close-all: close every armed delivery registration
        of the source transition, one recorded close per registration (key
        order). No further delivery — until a handler's result envelope opens
        a new registration and re-arms the source; seal is a close, not a
        permanent state (a Navigator ruling). The instance no longer waits on the
        source, so status can flip on this append alone
        (AWAITING -> STUCK/TERMINATED), with zero net activity.
        """
        path = NetPath(source)
        if path not in self.net.transitions:
            raise ValueError(f"cannot seal {path}: not a transition of this net")
        if not self.net.is_source(path):
            raise ValueError(
                f"cannot seal transition {path}: it has input arcs — only a source transition has delivery registrations"
            )
        if not self._armed[path]:
            raise ValueError(f"cannot seal source transition {path}: no armed delivery registration")
        instant = self._instant(at)
        closes: list[Record] = [
            DeliveryRegistrationClosed(path, key, occurrence=None, instant=instant) for key in sorted(self._armed[path])
        ]
        self.history.extend(closes)
        self._advance(instant)
        self._armed[path].clear()
        self._log.emit("registrations_sealed", source=str(path), closed=len(closes), instant=instant)

    def wake(self, at: Instant) -> TimerMatured | None:
        """
        The adapter's wakeup landing at the observed instant ``at``, made into
        the category-2 fact: derives the occasioning maturation itself (the
        pending ``next_maturation``) and appends a ``TimerMatured`` record —
        the append advances the watermark, so every maturation up to ``at``
        derives matured. A wakeup that matures nothing (early, stale, or
        spurious) is suppressed: no fact happened, ``None`` — harmless by
        construction. Maturation only enables; firing stays ``step``'s.
        """
        pending = self.next_maturation
        instant = self._instant(at)
        if pending is None or instant < pending:
            return None
        record = TimerMatured(maturation_instant=pending, instant=instant)
        self.history.append(record)
        self._advance(instant)
        self._log.emit("timer_matured", maturation=pending, instant=instant)
        return record

    @property
    def next_maturation(self) -> Instant | None:
        """
        The earliest maturation among bindings enabled but for their timers —
        the wakeup this instance owes its adapter (re-derived after every
        append; there is no durable timer state), and None when nothing waits
        on time.
        """
        return next_maturation(
            self.net, self.marking, self._guards, self._filters, self._watermark, self._entry_instants()
        )

    def bound_handler(self, transition: NetPath) -> Handler | ActivityHandler:
        """The transition's bound implementation; no symbol -> the default passthrough binding. The binding layer's symbol resolution, and the one home of the purity classification's subject: a plain callable is a pure projection, an ``ActivityHandler`` is impure work [DR 2026-07-14 source-delivery-projection-and-identity]."""
        uri = self.net.handler_uri(transition)
        # ty does not currently recognize passthrough's narrower concrete mapping return as Handler-compatible.
        return self._handlers[uri] if uri is not None else passthrough  # ty: ignore[invalid-return-type]

    def run(self) -> list[FiringOutcome]:
        """
        Step until nothing is enabled at the watermark. Returns the firings in
        order. A timed instance may return sleeping — waiting on
        ``next_maturation``, not quiescent; advancing time is the adapter's
        (``wake`` — the Engine observes time and wakes), never this loop's.
        """
        firings = []
        while (firing := self.step()) is not None:
            firings.append(firing)
        return firings

    @property
    def is_quiescent(self) -> bool:
        """
        No non-source transition is enabled at the watermark, no binding can
        mature into enablement, AND no firing occurrence has begun without ending
        [firing-semantics.md Termination] — an instance waiting on time is
        sleeping, and one with tokens out with a worker is working; neither is
        done.
        """
        return not self.candidates() and self.next_maturation is None and not self._in_flight

    @property
    def status(self) -> Status:
        """
        RUNNING while not quiescent — the completion condition reports, it
        never halts. When quiescent, the declared condition supplies the done
        judgment (COMPLETED when it holds — completion outranks an armed
        registration), the registrations supply the waiting judgment (AWAITING
        while any registration is armed), and only then the collapse:
        STUCK with a condition declared, the neutral TERMINATED without one
        (done and stuck are then indistinguishable). Derived on every read,
        never stored.
        """
        if not self.is_quiescent:
            return Status.RUNNING
        if self._completion is not None and self._completion_holds():
            return Status.COMPLETED
        if any(self._armed.values()):
            return Status.AWAITING
        return Status.STUCK if self._completion is not None else Status.TERMINATED

    def _completion_holds(self) -> bool:
        """
        The condition over the current marking — free of marking and history
        side effects; the deliberate diagnostic side effect is the warning: a
        raising condition reads as not holding, surfaced as a
        ``CompletionEvaluationWarning`` carrying the expression, the concrete
        marking, and the error, never silently swallowed. The expression is
        addressed by repr until NetUri addressing lands (docs/project/debt/
        items/2026-07-09T0000Z-evaluation-diagnostics-not-neturi-addressed.md).
        """
        marking = self.marking
        completion = self._completion
        if completion is None:
            raise RuntimeError("cannot evaluate an absent completion condition")
        try:
            return bool(completion(marking))
        except Exception as error:
            warnings.warn(
                f"completion condition {self.net.completion!r} raised {error!r} evaluating {marking!r}; "
                f"read as not holding",
                CompletionEvaluationWarning,
                stacklevel=2,
            )
            return False
