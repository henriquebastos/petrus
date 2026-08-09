"""
Enabledness: which transitions can fire, under which bindings, given a marking.

Pure: a function of net structure, the current marking, and the (pure) filter
and guard implementations — deterministic and free of marking side effects; the
deliberate diagnostic side effects are the warnings a raising filter or guard
emits. A ``Binding`` names a transition and the exact tokens each input arc
would take, so firing has nothing left to decide about token selection.

Candidate computation enumerates token selections from arcs first, then gates
the assembled bindings with the transition's declared guards, then with its
declared timers. A transition may be enabled under many bindings at once
[firing-semantics.md]: each consume/read arc contributes every combination of
``weight`` tokens it admits — its inscription's color (nominal match) narrowed
by its optional filter, a pure single-token boolean — and the transition's
alternatives are the cross product, enumerated input-arc-major and
FIFO-position-minor, so the head selection (the first ``weight`` admitted
tokens per arc, front-to-back) is always the first binding. A selection the
guards or timers skip therefore never disables a transition a deeper
admissible selection would enable. Consume removes its selection at firing,
read leaves it in place, inhibit selects nothing and gates on the absence of a
matching token. A filter or guard that raises on a concrete token or binding
makes it not admitted / not satisfied — skipped deterministically (uniformly
across arc modes) and surfaced as a ``FilterEvaluationWarning`` /
``GuardEvaluationWarning``, never silently swallowed.

Timers are enabledness condition 5, evaluated per firing binding: a binding is
enabled only when every declared timer has matured against the clock watermark
— a not-yet-matured binding is not enabled, purely, with no timer state stored
[DR 2026-07-08 timers-keyed-per-firing-binding-age-anchored]. A ``Delay``
anchors to the binding's youngest recorded entry instant among consume/read
selections (inhibitors contribute no anchor); an ``Until`` matures at its
declared instant. ``next_maturation`` derives the wakeup the adapter owes: the
earliest maturation among bindings enabled but for their timers.
"""

from __future__ import annotations

# Python imports
import warnings
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from itertools import combinations, product
from typing import Any

# Internal imports
from petrus.impetus.petrinet.marking import Marking, Token, TokenQueue
from petrus.impetus.petrinet.schema import (
    Arc,
    ArcMode,
    Delay,
    GuardDeclaration,
    Instant,
    Net,
    NetPath,
    NetUri,
    Transition,
    Until,
)


class GuardEvaluationWarning(UserWarning):
    """A guard raised while evaluating a concrete binding; the binding was skipped as not satisfied."""


class FilterEvaluationWarning(UserWarning):
    """An arc filter raised while evaluating a concrete token; the token was treated as not admitted."""


# A selection: the tokens ONE arc takes from ONE place — ``(place, tokens)``,
# the tokens in FIFO-scan order of the arc's admitted positions. The unit a
# binding is assembled from (consumed and read selections, each in input-arc
# order), and the shape a firing's movement records replay.
type Selection = tuple[NetPath, tuple[Token, ...]]


@dataclass(frozen=True)
class Binding:
    """
    A transition and the tokens each input arc selects: ``consumed`` (removed at
    firing) and ``read`` (selected but left in place). Both are ``(place, tokens)``
    per arc in input-arc order, so firing has nothing left to decide about
    selection. A source firing selects nothing — ``delivered`` carries the
    external event's tokens instead. Guards evaluate over the full binding;
    passthrough forwards ``tokens`` (consumed or delivered, never read).
    """

    transition: NetPath
    consumed: tuple[Selection, ...]
    read: tuple[Selection, ...] = ()
    delivered: tuple[Token, ...] = ()

    def __post_init__(self) -> None:
        if self.delivered and (self.consumed or self.read):
            raise ValueError(
                f"binding for {self.transition}: a delivered binding is a source firing and selects nothing — "
                f"it cannot also carry consumed or read selections"
            )

    @property
    def tokens(self) -> tuple[Token, ...]:
        """The tokens the firing forwards by default: consumed selections flattened in input-arc order, or a source firing's delivered tokens. Read selections stay in place and are never forwarded."""
        return tuple(token for _, tokens in self.consumed for token in tokens) + self.delivered

    @property
    def peeked(self) -> tuple[Token, ...]:
        """Every token the binding holds — consumed/delivered then read selections, each in input-arc order. What guards see."""
        return self.tokens + tuple(token for _, tokens in self.read for token in tokens)


# A guard implementation: a pure boolean over the full binding.
type Guard = Callable[[Binding], bool]
type GuardImplementationKey = GuardDeclaration | NetUri
type GuardImplementations = Mapping[Any, Guard]

# A filter implementation: a pure boolean over a single token.
type Filter = Callable[[Token], bool]
type FilterImplementations = Mapping[Any, Filter]


@dataclass(frozen=True)
class Veto:
    """The arc gates its transition out: a consume/read arc found fewer than ``weight`` admitted tokens, or an inhibit arc found ``weight``. No selection can repair it — enumeration stops at the first veto."""


@dataclass(frozen=True)
class Satisfied:
    """The arc is satisfied, contributing nothing: an inhibit arc below ``weight``. No selection, and no anchor — absence has no entry instant."""


@dataclass(frozen=True)
class Alternative:
    """One way an arc can select: a ``Selection`` and — when a ``Delay`` demands them — the selected tokens' recorded entry instants (the timer anchors), position-aligned with the selection's tokens."""

    selection: Selection
    anchors: tuple[Instant, ...] = ()


@dataclass(frozen=True)
class Alternatives:
    """The arc's alternative selections: every combination of ``weight`` admitted tokens, enumerated FIFO-lexicographically over the admitted positions, the head selection first. ``arc`` says how the selections participate (consume or read)."""

    arc: Arc
    alternatives: tuple[Alternative, ...]


# An arc's whole answer to a marking [glossary: the offer]: veto /
# satisfied-contributing-nothing / alternative selections (+ their timer
# anchors). Offers are kernel-side semantics — the schema's ``Arc`` stays
# pure, language-neutral data (net-as-IR) and never answers markings itself.
type Offer = Veto | Satisfied | Alternatives


def offer(
    arc: Arc,
    marking: Marking,
    filters: FilterImplementations,
    anchors: Mapping[NetPath, tuple[Instant, ...]] | None = None,
    filter_identity: NetUri | None = None,
) -> Offer:
    """
    The arc's whole answer to ``marking``: ``Veto``, ``Satisfied``, or
    ``Alternatives`` with every admitted combination (enabledness conditions
    1–3 compiled per arc; guards and timers judge the assembled bindings,
    downstream). ``anchors`` is the entry-instant threading's one home: pass
    each place queue's recorded entry instants (position-aligned) when the
    transition's timers demand anchors — they must cover every admitted
    position, and missing or misaligned instants fail loud — or ``None``
    when nothing anchors, and the alternatives carry no instants.
    """

    def admits(token: Token) -> bool:
        """The arc's admission judgment (inscription narrowed by filter), bound for the queue's scan."""
        return admitted(arc, token, filters, filter_identity)

    queue = TokenQueue.time_blind(marking.place(arc.source))
    if arc.mode is ArcMode.INHIBIT:
        if len(queue.admitted_by(admits, limit=arc.weight)) >= arc.weight:
            return Veto()  # weight matching tokens present -> transition gated out
        return Satisfied()
    positions = queue.admitted_by(admits)
    if len(positions) < arc.weight:  # consume and read both require >= weight admitted
        return Veto()
    instants = anchors.get(arc.source, ()) if anchors is not None else None
    if instants is not None and positions[-1] >= len(instants):
        raise ValueError(
            f"candidate computation for timed transition {arc.target}: entry instants for place "
            f"{arc.source} are missing or misaligned ({len(instants)} recorded, selection "
            f"reaches position {positions[-1]}); a Delay anchors to each selected token's "
            f"recorded entry instant"
        )
    return Alternatives(
        arc,
        tuple(
            Alternative(
                (arc.source, tuple(queue[position] for position in combination)),
                () if instants is None else tuple(instants[position] for position in combination),
            )
            for combination in combinations(positions, arc.weight)
        ),
    )


def candidates(
    net: Net,
    marking: Marking,
    guards: GuardImplementations | None = None,
    filters: FilterImplementations | None = None,
    watermark: Instant | None = None,
    entry_instants: Mapping[NetPath, tuple[Instant, ...]] | None = None,
) -> list[Binding]:
    """
    Enabled firing candidates under ``marking``, in stable (path-sorted) order.

    ``guards`` and ``filters`` map the declared guards and arc filters — named
    symbols and inline ``Cel`` expressions alike —
    to their bound implementations (the binding layer resolves both). A
    transition is enabled only if every input arc finds a selection, all
    declared guards hold over the assembled binding, and every declared timer
    has matured against ``watermark`` — the clock watermark, required together
    with ``entry_instants`` (each place queue's recorded entry instants,
    position-aligned) whenever the net declares timers. Source transitions are
    excluded — they fire only on external delivery, never from the scheduler.

    Enumeration yields every enabled binding per transition (transitions
    path-sorted; within a transition, alternatives input-arc-major and
    FIFO-position-minor, the head selection first), so a guard or timer
    skipping one selection never disables a transition another admissible
    selection enables — the ruled per-binding skip, whole. The scheduler
    chooses among the candidates [ADR 0008]; ``select_conservative`` keeps
    firing the head selection of the path-first enabled transition.
    """
    enabled, _ = _survey(net, marking, guards or {}, filters or {}, watermark, entry_instants or {})
    return enabled


def next_maturation(
    net: Net,
    marking: Marking,
    guards: GuardImplementations | None = None,
    filters: FilterImplementations | None = None,
    watermark: Instant | None = None,
    entry_instants: Mapping[NetPath, tuple[Instant, ...]] | None = None,
) -> Instant | None:
    """
    The earliest maturation instant among bindings enabled but for their
    timers — the wakeup the runtime owes the adapter after every append, and
    the timer leg of quiescence. ``None`` when no binding is waiting on time.
    """
    _, pending = _survey(net, marking, guards or {}, filters or {}, watermark, entry_instants or {})
    return min(pending, default=None)


# Complexity exception: reviewed as one linear enabledness-enumeration algorithm.
def _survey(  # noqa: C901
    net: Net,
    marking: Marking,
    guards: GuardImplementations,
    filters: FilterImplementations,
    watermark: Instant | None,
    entry_instants: Mapping[NetPath, tuple[Instant, ...]],
) -> tuple[list[Binding], list[Instant]]:
    """
    The shared enumeration behind ``candidates`` and ``next_maturation``: the
    enabled bindings, and the maturation instants of bindings that satisfied
    their arcs and guards but not yet their timers. Each wrapper re-runs the
    enumeration and keeps the projection it names — derived, never cached.

    Enumeration cost (debt 2026-07-11T2130Z, noted at closure): the candidate
    list materializes eagerly — ``C(n, weight)`` combinations per selecting
    arc, crossed across arcs — before any scheduler chooses, so a large
    marking on a wide join pays the whole cross product up front. Free under
    the conservative default (``bindings[0]`` is the head selection) and
    faithful to the spec (the core enumerates, the scheduler chooses
    [ADR 0008]); a lazy or bounded enumeration is the
    non-conservative-scheduler turn's design change, not a local tweak.
    Selections here are BY VALUE: two equal tokens at distinct positions
    yield identical bindings — the pinned value-aliasing invariant (see the
    debt's closure and its pinning test).

    Per transition, the spec's linear composition [firing-semantics.md
    §Enabledness, conditions 1–5]: each input arc answers the marking with
    its ``offer``; the transition's alternatives are the cross product of
    the selecting offers; guards judge the assembled bindings; timers split
    enabled-now from pending.
    """
    if watermark is None and any(t.timers and not net.is_source(p) for p, t in net.transitions.items()):
        raise ValueError(
            "candidate computation over a timed net requires the clock: pass the watermark and entry instants"
        )
    enabled: list[Binding] = []
    pending: list[Instant] = []
    for path in sorted(net.transitions, key=str):
        if net.is_source(path):
            continue
        transition = net.transitions[path]
        # The clock check above enforces the watermark half of the required
        # pair; the entry-instant half is offer()'s, threaded only when a
        # Delay demands anchors — never a raw IndexError.
        anchored = any(isinstance(timer, Delay) for timer in transition.timers)
        offers: list[Alternatives] = []
        for arc, position in zip(net.inputs(path), net.input_positions(path)):
            answer = offer(arc, marking, filters, entry_instants if anchored else None, net.filter_uris()[position])
            if isinstance(answer, Veto):
                break  # one veto gates the transition out; later arcs are never consulted
            if isinstance(answer, Alternatives):
                offers.append(answer)
            # Satisfied contributes nothing: no selection, no anchor.
        else:
            # The cross product of the arcs' alternatives, input-arc-major and
            # FIFO-position-minor — the head selection is the first binding.
            for choice in product(*(answer.alternatives for answer in offers)):
                consumed = []
                read = []
                anchors = []
                for answer, alternative in zip(offers, choice):
                    if answer.arc.mode is ArcMode.CONSUME:
                        consumed.append(alternative.selection)
                    else:  # READ: selected but left in place -- carried in the binding for guards, never forwarded
                        read.append(alternative.selection)
                    anchors.extend(alternative.anchors)
                binding = Binding(path, tuple(consumed), tuple(read))
                if not guards_hold(transition, binding, guards, net.guard_uris(path)):
                    continue
                mature = maturation(transition.timers, max(anchors, default=None))
                if mature is None or mature <= watermark:
                    enabled.append(binding)
                else:
                    pending.append(mature)
    return enabled, pending


def maturation(timers: tuple[Delay | Until, ...], anchor: Instant | None) -> Instant | None:
    """
    The instant at which every declared timer has matured — the latest of each
    ``Delay``'s ``anchor + duration`` and each ``Until``'s declared instant;
    ``None`` when no timers are declared. ``anchor`` is the binding's youngest
    recorded entry instant among consume/read selections (net validation
    guarantees a ``Delay`` has one).
    """
    if not timers:
        return None
    return max(anchor + timer.duration if isinstance(timer, Delay) else timer.instant for timer in timers)


def selection(arc: Arc, queue: tuple[Token, ...], filters: FilterImplementations) -> tuple[Token, ...]:
    """
    The HEAD selection ``arc`` makes from its place's queue: FIFO-first-match,
    the first ``weight`` tokens the arc admits, scanning front-to-back — the
    first alternative candidate enumeration considers (the deeper combinations
    are ``_survey``'s, never this function's). Fewer than ``weight`` admitted
    means every selection falls short — not satisfied for consume/read,
    satisfied for inhibit. Candidate computation works in
    ``TokenQueue.admitted_by``, the coordinate form whose positions also
    index the entry instants.
    """
    scanned = TokenQueue.time_blind(queue)
    positions = scanned.admitted_by(lambda token: admitted(arc, token, filters), limit=arc.weight)
    return tuple(scanned[position] for position in positions)


def admitted(
    arc: Arc,
    token: Token,
    filters: FilterImplementations,
    filter_identity: NetUri | None = None,
) -> bool:
    """
    Whether ``arc`` admits ``token``: the inscription's color (nominal match,
    ``Arc.admits``) narrowed by its optional filter. A filter raising on a
    concrete token means the token is not admitted — uniformly across arc
    modes (on an inhibit arc an unreadable token does not gate the transition
    out) — surfaced as a ``FilterEvaluationWarning``. A missing implementation
    is not an evaluation error — it raises, loudly; the runtime validates the
    mapping before the instance can run.
    """
    if not arc.admits(token):
        return False
    if arc.filter is None:
        return True
    identity = filter_identity if filter_identity is not None else arc.filter
    implementation = filters[identity] if identity in filters else filters[arc.filter]
    try:
        return bool(implementation(token))
    except Exception as error:
        # Keep the authored declaration visible beside its canonical occurrence
        # identity; the latter disambiguates same-endpoint parallel arcs.
        warnings.warn(
            f"filter {arc.filter!r} at {identity!r} raised {error!r} evaluating {token!r}; token not admitted",
            FilterEvaluationWarning,
            stacklevel=2,
        )
        return False


def guards_hold(
    transition: Transition,
    binding: Binding,
    guards: GuardImplementations,
    identities: tuple[NetUri, ...] = (),
) -> bool:
    """
    Whether all of the transition's declared guards hold over ``binding`` —
    conjunction, short-circuiting at the first failure. The enablement outcome
    is order-independent (guards are pure); diagnostics follow declaration
    order and stop at the first failing guard.

    A guard raising on a concrete binding means the binding is not satisfied:
    skipped, with the error surfaced as a ``GuardEvaluationWarning``. A missing
    implementation is not an evaluation error — it raises, loudly; the runtime
    validates named symbols and compiles inline ``Cel`` declarations before the
    instance can run.
    """
    for position, declaration in enumerate(transition.guards):
        identity = identities[position] if identities else declaration
        guard = guards[identity] if identity in guards else guards[declaration]
        try:
            satisfied = guard(binding)
        except Exception as error:
            warnings.warn(
                f"guard {declaration!r} at {identity!r} on transition {binding.transition} raised {error!r} "
                f"over peeked tokens {binding.peeked}; binding skipped",
                GuardEvaluationWarning,
                stacklevel=2,
            )
            return False
        if not satisfied:
            return False
    return True
