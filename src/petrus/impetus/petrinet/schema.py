"""
Net structure: the declarative, language-neutral description of a net.

- ``NetPath`` — an immutable node address (a dotted path; a flat net uses a single segment).
- ``ArcMode`` — how an input arc participates in enablement (consume / read / inhibit).
- ``Cel`` — an inline CEL expression, the inline encoding of the pure expression tier.
- ``FilterDeclaration`` / ``GuardDeclaration`` / ``CompletionDeclaration`` — declarations
  named by the vocabulary each slot reads (one token / the full binding / the
  marking); guards additionally admit an anonymous behavior marker assigned a
  canonical occurrence identity by ``Net``.
- ``Arc`` — a directed place<->transition connection with a mode, weight, and inscription.
- ``Place`` / ``Transition`` — the two kinds of node.
- ``Net`` — the flattened net: nodes, arcs, and input/output indices, validated
  at build, plus the optional completion condition (bound and compiled at the
  instance level).

Structure only. How a net executes lives in ``firing`` / ``petrinet.enabledness``; how a
symbol binds to code is a later concern. A place may declare its nominal token
color as an authoring default, resolved once onto otherwise-untyped incident
arcs when the net is built. Input inscriptions (resolved color + optional
filter) narrow what an arc admits; output inscriptions are the routing
contracts deposits are checked against. Guard, handler, filter, and completion
implementations bind to the declared symbols at the instance level
(``runtime``); inline CEL compiles there too.
"""

from __future__ import annotations

# Python imports
import re
from dataclasses import dataclass, field, replace
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

if TYPE_CHECKING:  # marking imports schema; the reverse edge exists only for type checking
    from petrus.impetus.petrinet.marking import Token

# An instant on the instance's virtual clock: opaque to the kernel, totally
# ordered among the instants one instance sees (ints as logical epochs,
# datetimes for wall-clock adapters — mixing them is the caller's bug).
type Instant = Any

# A duration a Delay timer adds to an instant: ``instant + duration`` must
# yield an Instant (int + int, datetime + timedelta).
type Duration = Any

# A language-neutral nominal color name. Python-facing authoring layers may
# obtain one from a domain type (for example ``Generation.__name__``), but the
# kernel schema contains the portable name, never the implementation object.
type Color = str


class NetPath(tuple):
    """
    Immutable node address, inheriting from ``tuple``.

    A flat net addresses a node by its bare id (``NetPath("start")``); nested
    nets grow segments (``NetPath("review.start")`` -> ``("review", "start")``).
    Accepts a non-empty dotted string, or an existing ``NetPath`` (returned as-is).

    Example::

        NetPath("start")              # ("start",)
        str(NetPath("review.start"))  # "review.start"
    """

    SEP = "."

    def __new__(cls, value: str | NetPath) -> NetPath:
        if isinstance(value, NetPath):
            return value
        if not isinstance(value, str) or not value:
            raise ValueError(f"NetPath requires a non-empty dotted string or a NetPath, got {value!r}")
        segments = value.split(cls.SEP)
        if any(not segment for segment in segments):
            raise ValueError(f"NetPath segments must be non-empty, got {value!r}")
        return super().__new__(cls, segments)

    def __str__(self) -> str:
        return self.SEP.join(self)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({str(self)!r})"

    def __deepcopy__(self, memo: dict[int, object]) -> NetPath:
        memo[id(self)] = self
        return self


def canonical_net_path(value: object, noun: str) -> NetPath:
    """Return a base NetPath from an exact protocol spelling."""
    if type(value) is NetPath:
        return value
    if type(value) is str:
        return NetPath(value)
    raise ValueError(f"{noun} must be an exact NetPath or built-in string, got {value!r}")


@dataclass(frozen=True, order=True)
class NetUri:
    """Canonical ASCII address of one addressable part of a flattened net."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value or not self.value.isascii():
            raise ValueError(f"NetUri requires a non-empty canonical ASCII value, got {self.value!r}")
        if (
            not self.value.startswith(("place:/", "transition:/", "arc:/"))
            or self.value.count("#") > 1
            or any(character.isspace() for character in self.value)
            or "?" in self.value
            or "\\" in self.value
            or re.search(r"%(?![0-9A-F]{2})", self.value)
        ):
            raise ValueError(f"invalid canonical NetUri {self.value!r}")

    @classmethod
    def declaration(
        cls,
        owner: str,
        path: NetPath | str,
        declaration: str,
        name: str | None = None,
    ) -> NetUri:
        """Address one declaration anchored on a place or transition."""
        if owner not in {"place", "transition"}:
            raise ValueError(f"declaration owner must be 'place' or 'transition', got {owner!r}")
        if not declaration or not declaration.isascii() or not declaration.replace("-", "").isalnum():
            raise ValueError(f"declaration kind must be a non-empty ASCII name, got {declaration!r}")
        if name is not None and (not isinstance(name, str) or not name):
            raise ValueError(f"declaration name must be a non-empty string or None, got {name!r}")
        path = NetPath(path)
        encoded_path = "/".join(quote(segment, safe="-._~") for segment in path)
        fragment = declaration if name is None else f"{declaration}:{quote(name, safe='-._~$')}"
        return cls(f"{owner}:/{encoded_path}#{fragment}")

    @classmethod
    def arc(cls, source: NetPath | str, target: NetPath | str, occurrence: int | None = None) -> NetUri:
        """Address one directed arc, optionally by its generated pair-local occurrence."""
        if occurrence is not None and (
            isinstance(occurrence, bool) or not isinstance(occurrence, int) or occurrence < 0
        ):
            raise ValueError(f"arc occurrence must be a non-negative integer or None, got {occurrence!r}")

        def encoded(path: NetPath | str) -> str:
            return "/".join(quote(segment, safe="-._~") for segment in NetPath(path))

        fragment = "" if occurrence is None else f"#${occurrence}"
        return cls(f"arc:/{encoded(source)}->/{encoded(target)}{fragment}")

    @classmethod
    def arc_filter(cls, arc: NetUri) -> NetUri:
        """Address the filter declaration anchored on an arc occurrence."""
        if not isinstance(arc, NetUri) or not arc.value.startswith("arc:/"):
            raise ValueError(f"arc filter owner must be an arc NetUri, got {arc!r}")
        base, separator, occurrence = arc.value.partition("#")
        if separator and re.fullmatch(r"\$[0-9]+", occurrence) is None:
            raise ValueError(f"arc filter owner must use a generated occurrence fragment, got {arc!r}")
        fragment = "filter" if not separator else f"filter:{occurrence}"
        return cls(f"{base}#{fragment}")

    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.value!r})"


class ArcMode(StrEnum):
    """How an input arc participates in enablement: consume removes tokens, read peeks, inhibit gates on absence."""

    CONSUME = "consume"
    READ = "read"
    INHIBIT = "inhibit"


@dataclass(frozen=True)
class Cel:
    """
    An inline CEL expression — the inline encoding of the pure expression tier
    (arc filters, transition guards, and the net's completion condition).
    Structure only: the expression compiles at the instance level, through the
    CEL adapter (``petrus.impetus.binding.cel``).
    """

    expression: str

    def __post_init__(self) -> None:
        if not isinstance(self.expression, str) or not self.expression:
            raise ValueError(f"Cel requires a non-empty expression string, got {self.expression!r}")

    def __str__(self) -> str:
        """
        The expression source — presentation only. Identity stays the
        dataclass's: an expression is NOT a name, so equality, hash, and the
        ``Mapping[str | Cel, ...]`` registry keys never collapse a ``Cel``
        into its string (the vetoed str-subclass half); diagnostics keep
        ``!r``, which shows the tag.
        """
        return self.expression


# The three declaration unions of the pure expression tier: every slot admits
# a named symbol (``str``, bound at the instance level) or an inline ``Cel``
# expression (compiled there). One encoding shape, three vocabularies — a
# filter reads one token, a guard reads the full binding, the completion
# reads the marking — and until these names, only position said which was
# meant. Aliases only: construction-time checks spell the union structurally
# (``isinstance`` does not take a type alias).
type FilterDeclaration = str | Cel


@dataclass(frozen=True)
class AnonymousDeclaration:
    """A behavior declaration whose canonical identity comes from its owner and position."""

    display_name: str | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if self.display_name is not None and (not isinstance(self.display_name, str) or not self.display_name):
            raise ValueError(
                f"anonymous declaration display name must be a non-empty string or None, got {self.display_name!r}"
            )


ANONYMOUS = AnonymousDeclaration()

type HandlerDeclaration = str | AnonymousDeclaration
type GuardDeclaration = str | Cel | AnonymousDeclaration
type CompletionDeclaration = str | Cel


@dataclass(frozen=True)
class Delay:
    """
    A duration timer: matures a binding at ``anchor + duration``, the anchor
    being the youngest recorded entry instant among the binding's
    consume/read-bound tokens. Structure only: maturation is derived at
    candidate computation (``enabledness``), never stored.
    """

    duration: Duration


@dataclass(frozen=True)
class Until:
    """An absolute timer: matures every binding at its declared instant."""

    instant: Instant


@dataclass(frozen=True)
class Arc:
    """
    A directed place<->transition connection.

    Input arcs (place -> transition) carry a mode; on output arcs the mode is an
    unused default. ``color`` is the inscription's optional color/type: an
    untyped arc admits any token, a typed arc admits its color only (nominal
    match). On output arcs it is the routing contract the runtime deposits
    against. ``filter`` — input arcs only — narrows admission further: a pure
    single-token boolean, spelled as a named symbol (``str``, bound at the
    instance level) or an inline ``Cel`` expression.
    """

    source: NetPath
    target: NetPath
    mode: ArcMode = ArcMode.CONSUME
    weight: int = 1
    color: Color | None = None
    filter: FilterDeclaration | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.mode, ArcMode):
            raise ValueError(f"arc mode must be an ArcMode, got {self.mode!r}: {self.source} -> {self.target}")
        if isinstance(self.weight, bool) or not isinstance(self.weight, int) or self.weight < 1:
            raise ValueError(f"arc weight must be an integer >= 1, got {self.weight!r}: {self.source} -> {self.target}")
        if self.color is not None and (not isinstance(self.color, str) or not self.color):
            raise ValueError(
                f"arc color must be a non-empty nominal color name or None, got {self.color!r}: "
                f"{self.source} -> {self.target}"
            )
        # The two declared filter encodings only; anything else would surface
        # later as the CEL adapter's internal error instead of a declared
        # mismatch.
        if self.filter is not None and not isinstance(self.filter, str | Cel):
            raise ValueError(
                f"filter must be a symbol name or an inline Cel expression, got {self.filter!r}: "
                f"{self.source} -> {self.target}"
            )
        if isinstance(self.filter, str) and (not self.filter or self.filter.startswith("$")):
            raise ValueError(
                f"filter symbol must be non-empty and cannot start with '$', got {self.filter!r}: "
                f"{self.source} -> {self.target}"
            )

    @property
    def is_consume(self) -> bool:
        """Whether this is a consuming input arc (also the unused output-arc default)."""
        return self.mode is ArcMode.CONSUME

    @property
    def is_read(self) -> bool:
        """Whether this is a non-consuming read input arc."""
        return self.mode is ArcMode.READ

    @property
    def is_inhibit(self) -> bool:
        """Whether this is an inhibiting input arc."""
        return self.mode is ArcMode.INHIBIT

    def admits(self, token: Token) -> bool:
        """
        The nominal color match: untyped matches anything, typed matches its
        color only. On an output arc this is the whole routing contract; on an
        input arc a declared filter narrows admission further — the full
        predicate is ``enabledness.admitted``.
        """
        return self.color is None or self.color == token.color


@dataclass(frozen=True)
class Place:
    """A location that holds tokens, optionally declaring their nominal color."""

    path: NetPath
    color: Color | None = None

    def __post_init__(self) -> None:
        if self.color is not None and (not isinstance(self.color, str) or not self.color):
            raise ValueError(
                f"place color must be a non-empty nominal color name or None, got {self.color!r}: {self.path}"
            )


@dataclass(frozen=True)
class Transition:
    """
    A process step that may fire when enabled. No implementation kind: the
    handler is a named or anonymous declaration, bound to an implementation
    separately; each guard is a pure boolean over the full firing binding,
    declared as a named symbol, inline ``Cel`` expression, or anonymous
    declaration. Multiple guards compose as conjunction, and so do the
    declared timers: a binding is matured only when every ``Delay`` / ``Until``
    has matured.
    """

    path: NetPath
    handler: HandlerDeclaration | None = None
    guards: tuple[GuardDeclaration, ...] = ()
    timers: tuple[Delay | Until, ...] = ()

    def __post_init__(self) -> None:
        if self.handler is not None and not isinstance(self.handler, str | AnonymousDeclaration):
            raise ValueError(
                f"handler must be a symbol name or anonymous declaration, got {self.handler!r}: {self.path}"
            )
        if isinstance(self.handler, str) and (not self.handler or self.handler.startswith("$")):
            raise ValueError(
                f"handler symbol must be non-empty and cannot start with '$', got {self.handler!r}: {self.path}"
            )
        # The three declared guard encodings only; anything else would surface
        # later as the binding layer's internal error instead of a declared
        # mismatch.
        named_guards: set[str] = set()
        for guard in self.guards:
            if not isinstance(guard, str | Cel | AnonymousDeclaration):
                raise ValueError(
                    f"guard must be a symbol name, inline Cel expression, or anonymous declaration, "
                    f"got {guard!r}: {self.path}"
                )
            if isinstance(guard, str):
                if not guard or guard.startswith("$"):
                    raise ValueError(
                        f"guard symbol must be non-empty and cannot start with '$', got {guard!r}: {self.path}"
                    )
                if guard in named_guards:
                    raise ValueError(f"duplicate named guard {guard!r}: {self.path}")
                named_guards.add(guard)
        # The two ratified timer forms only; anything else would surface later
        # as a broken maturation instead of a declared mismatch.
        for timer in self.timers:
            if not isinstance(timer, Delay | Until):
                raise ValueError(f"timer must be a Delay or an Until, got {timer!r}: {self.path}")


def _resolve_place_colors(place_map, transition_map, arcs) -> tuple[Arc, ...]:
    """Compile place color defaults into canonical runtime arc inscriptions."""
    resolved: list[Arc] = []
    for arc in arcs:
        if arc.source in place_map and arc.target in transition_map:
            place = place_map[arc.source]
        elif arc.source in transition_map and arc.target in place_map:
            place = place_map[arc.target]
        else:
            raise ValueError(f"arc must connect a place and a transition: {arc.source} -> {arc.target}")
        if place.color is not None and arc.color is not None and place.color != arc.color:
            raise ValueError(
                f"arc {arc.source} -> {arc.target} declares color {arc.color!r}, incompatible with "
                f"place {place.path} color {place.color!r}"
            )
        resolved.append(replace(arc, color=place.color) if arc.color is None and place.color is not None else arc)
    return tuple(resolved)


class Net:
    """
    A flattened net: places, transitions, arcs, and derived input/output indices.

    Built and validated once, then immutable — ``places`` and ``transitions`` are
    read-only views. A transition with no input arcs is a source transition (the
    external-event entry point). ``completion`` is the net's one optional
    completion condition (canonical fragment ``#completion``): a pure boolean
    predicate over the marking — a named symbol (``str``, bound at the instance
    level) or an inline ``Cel`` expression — supplying the *done* judgment of
    instance status. It never affects enabledness or firing. ``name`` is the
    definition's optional human name ("order-fulfillment") — purely
    descriptive: recorded on the instance's identity fact and carried by
    telemetry (which net KIND is running), never read by any semantics
    [ES-020/DEC-026].
    """

    # Complexity exception: reviewed as the net's single construction-validation boundary.
    def __init__(  # noqa: C901
        self, places, transitions, arcs, completion: CompletionDeclaration | None = None, name: str | None = None
    ):
        # The two declared encodings only; anything else would surface later
        # as the CEL adapter's internal error instead of a declared mismatch.
        if completion is not None and not isinstance(completion, str | Cel):
            raise ValueError(f"completion must be a symbol name or an inline Cel expression, got {completion!r}")
        if isinstance(completion, str) and (not completion or completion.startswith("$")):
            raise ValueError(f"completion symbol must be non-empty and cannot start with '$', got {completion!r}")
        if name is not None and (not isinstance(name, str) or not name):
            raise ValueError(f"net name must be a non-empty string, got {name!r}")
        self.completion = completion
        self.name = name
        places = tuple(places)
        transitions = tuple(transitions)
        place_map = {p.path: p for p in places}
        transition_map = {t.path: t for t in transitions}

        if len(place_map) != len(places):
            raise ValueError("duplicate place path")
        if len(transition_map) != len(transitions):
            raise ValueError("duplicate transition path")

        collisions = place_map.keys() & transition_map.keys()
        if collisions:
            raise ValueError(f"place/transition name collision: {sorted(map(str, collisions))}")

        self.places = MappingProxyType(place_map)
        self.transitions = MappingProxyType(transition_map)

        handler_declarations: dict[NetUri, HandlerDeclaration] = {}
        guard_declarations: dict[NetUri, GuardDeclaration] = {}
        self._handler_uris: dict[NetPath, NetUri] = {}
        self._guard_uris: dict[NetPath, tuple[NetUri, ...]] = {}
        for path, transition in transition_map.items():
            if transition.handler is not None:
                uri = NetUri.declaration("transition", path, "handler")
                self._handler_uris[path] = uri
                handler_declarations[uri] = transition.handler
            guard_uris = []
            for position, guard in enumerate(transition.guards):
                name = guard if isinstance(guard, str) else f"${position}"
                uri = NetUri.declaration("transition", path, "guard", name)
                guard_uris.append(uri)
                guard_declarations[uri] = guard
            self._guard_uris[path] = tuple(guard_uris)
        self.handler_declarations = MappingProxyType(handler_declarations)
        self.guard_declarations = MappingProxyType(guard_declarations)

        # Resolve once: enabledness, routing, filters, and derived handlers
        # retain their one arc-inscription contract and perform no place lookup.
        self.arcs = _resolve_place_colors(place_map, transition_map, arcs)

        pair_counts: dict[tuple[NetPath, NetPath], int] = {}
        for arc in self.arcs:
            pair = (arc.source, arc.target)
            pair_counts[pair] = pair_counts.get(pair, 0) + 1
        pair_positions: dict[tuple[NetPath, NetPath], int] = {}
        arc_uris = []
        filter_uris = []
        filter_declarations: dict[NetUri, FilterDeclaration] = {}
        for arc in self.arcs:
            pair = (arc.source, arc.target)
            position = pair_positions.get(pair, 0)
            pair_positions[pair] = position + 1
            uri = NetUri.arc(arc.source, arc.target, position if pair_counts[pair] > 1 else None)
            arc_uris.append(uri)
            filter_uri = NetUri.arc_filter(uri) if arc.filter is not None else None
            filter_uris.append(filter_uri)
            if filter_uri is not None:
                if filter_uri in filter_declarations:  # pragma: no cover - generated occurrences make this impossible
                    raise ValueError(f"arc filter URI collision: {filter_uri}")
                assert arc.filter is not None
                filter_declarations[filter_uri] = arc.filter
        if len(set(arc_uris)) != len(arc_uris):  # pragma: no cover - generated occurrences make this impossible
            raise ValueError("arc URI collision")
        self._arc_uris = tuple(arc_uris)
        self._filter_uris = tuple(filter_uris)
        self.filter_declarations = MappingProxyType(filter_declarations)

        self._inputs: dict[NetPath, list[Arc]] = {}
        self._input_positions: dict[NetPath, list[int]] = {}
        self._outputs: dict[NetPath, list[Arc]] = {}
        for position, arc in enumerate(self.arcs):
            if arc.source in self.places and arc.target in self.transitions:
                self._inputs.setdefault(arc.target, []).append(arc)
                self._input_positions.setdefault(arc.target, []).append(position)
            elif arc.source in self.transitions and arc.target in self.places:
                # Modes and filters are input inscriptions; ignored ones would
                # silently mis-describe the deposit.
                if arc.mode is not ArcMode.CONSUME:
                    raise ValueError(f"mode on output arc {arc.source} -> {arc.target}: modes are input inscriptions")
                if arc.filter is not None:
                    raise ValueError(
                        f"filter on output arc {arc.source} -> {arc.target}: a filter is an input inscription"
                    )
                self._outputs.setdefault(arc.source, []).append(arc)
            else:  # pragma: no cover - resolution above establishes the endpoint shape
                raise AssertionError(f"resolved arc lost its place/transition shape: {arc.source} -> {arc.target}")

        # A passthrough-bound transition whose only inputs are read/inhibit would
        # consume nothing, produce nothing, fire forever on an unchanging marking,
        # and livelock — permanently invalid. With a handler the emit is the
        # point; whether the net self-gates is the author's design concern.
        for transition, arcs in self._inputs.items():
            if not self.transitions[transition].handler and not any(arc.mode is ArcMode.CONSUME for arc in arcs):
                raise ValueError(
                    f"transition {transition}: a non-source transition with no consume input arc and no "
                    f"handler would fire forever consuming and producing nothing"
                )

        # Guards and timers are enabledness machinery and source transitions
        # are excluded from enabledness — they fire only on external delivery,
        # so a declared guard or timer would never be evaluated. Refuse what
        # cannot be honored.
        for path, transition in self.transitions.items():
            if self.is_source(path) and transition.guards:
                raise ValueError(
                    f"transition {path}: guards on a source transition cannot be honored — it fires only "
                    f"on external delivery, never through enabledness; found {list(transition.guards)!r}"
                )
            if self.is_source(path) and transition.timers:
                raise ValueError(
                    f"transition {path}: timers on a source transition cannot be honored — it fires only "
                    f"on external delivery, never through enabledness; found {list(transition.timers)!r}"
                )
            # A duration timer anchors to the youngest bound token's recorded
            # entry instant; inhibitor arcs contribute no anchor — absence has
            # no entry instant [DR timers-keyed-per-firing-binding-age-anchored].
            if any(isinstance(timer, Delay) for timer in transition.timers) and not any(
                arc.mode is not ArcMode.INHIBIT for arc in self._inputs.get(path, ())
            ):
                raise ValueError(
                    f"transition {path}: a duration timer has no anchor — every input arc is an inhibitor "
                    f"and absence has no entry instant; declare a consume or read input, or use an "
                    f"absolute Until timer"
                )

    def inputs(self, transition: NetPath) -> tuple[Arc, ...]:
        """Input arcs targeting this transition."""
        return tuple(self._inputs.get(transition, ()))

    def outputs(self, transition: NetPath) -> tuple[Arc, ...]:
        """Output arcs leaving this transition."""
        return tuple(self._outputs.get(transition, ()))

    def arc_uris(self) -> tuple[NetUri, ...]:
        """Canonical arc occurrence identities, position-aligned with ``arcs``."""
        return self._arc_uris

    def arc_uri(self, position: int) -> NetUri:
        """Canonical identity of the arc occurrence at a global arc position."""
        return self._arc_uris[position]

    def filter_uris(self) -> tuple[NetUri | None, ...]:
        """Filter identities, position-aligned with ``arcs`` (``None`` when absent)."""
        return self._filter_uris

    def input_positions(self, transition: NetPath) -> tuple[int, ...]:
        """Global arc positions of a transition's inputs, in input order."""
        return tuple(self._input_positions.get(transition, ()))

    def handler_uri(self, transition: NetPath) -> NetUri | None:
        """The canonical identity of this transition's declared handler, if any."""
        return self._handler_uris.get(transition)

    def guard_uris(self, transition: NetPath) -> tuple[NetUri, ...]:
        """Canonical identities of this transition's guards in authored order."""
        return self._guard_uris.get(transition, ())

    def is_source(self, transition: NetPath) -> bool:
        """A source transition has no input arcs; it fires only on external delivery."""
        return transition not in self._inputs

    def __repr__(self) -> str:
        return f"Net({len(self.places)}p, {len(self.transitions)}t, {len(self.arcs)}a)"
