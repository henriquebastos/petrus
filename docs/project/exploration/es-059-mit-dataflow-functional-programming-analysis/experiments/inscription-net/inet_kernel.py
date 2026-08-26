"""The inscription kernel: seven combinators over typed ports.

The research object of this experiment. A developer writes a *dataflow
expression* — which typed values arrive, which typed values are produced, and
which capabilities are consumed on the way — and the compiler derives the
topology **and the guards**. Nothing here performs motion: constructing a flow
writes no History, builds no Engine, and calls no domain function.

The seven combinators:

===================  ==========================================================
``await_``           external scoped ingress; one source transition
``fork``             one firing, several typed outputs, from pure functions
``join``             one firing over several typed inputs (consume / read)
``choice``           ordered guarded branches over one join
``effect``           a Motus Activity fused into a branch's firing
``latch``            a thin-token place: presence, absence, and refill
``>>``               sequence: glue a producer's ports into a consumer node
===================  ==========================================================

Ports are not a combinator. A port **is a type**: the compiler allocates exactly
one place per token color, named by the flow's ``ports`` table. That is the
Open-Petri-Nets gluing rule spelled the cheapest way it can be spelled — two
nodes are connected when they agree on a type.

Everything the kernel refuses, it refuses here, before lowering:

* a predicate that is not ``(...) -> bool`` over concrete token types;
* a predicate that reads a latch color (latches are absence-testable, and a
  generated ``NOT`` chain cannot evaluate a term whose token another branch
  never binds);
* duplicate branch ids, naming both authoring sites;
* two distinct classes sharing one nominal name;
* a fold that does not return one of the join's folded port types;
* an Activity request type without a stable ``operation`` field;
* a missing or misplaced ``otherwise``; and
* **an incomplete structural cover** — the check that makes exhaustiveness a
  compiler property rather than an authoring obligation (see ``_cover``).
"""

from __future__ import annotations

import sys
import types
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields
from inspect import signature
from itertools import product
from pathlib import Path
from typing import Any, cast, get_type_hints

from petrus.motus.activity import ActivityDefinition

from algebra import CompositionError, SourceRef

EXPERIMENT_ROOT = Path(__file__).resolve().parent


def _normalize(filename: str) -> str:
    path = Path(filename).resolve()
    try:
        return path.relative_to(EXPERIMENT_ROOT).as_posix()
    except ValueError:
        return path.name


def _call_site(symbol: str) -> SourceRef:
    """Attribute a value-only construct to its authoring call site.

    The frame is read once at construction; only plain strings and ints are
    retained and no frame is consulted during execution or resume.
    """
    frame = sys._getframe(2)
    try:
        return SourceRef(_normalize(frame.f_code.co_filename), frame.f_lineno, symbol)
    finally:
        del frame


def function_site(function: Callable[..., object]) -> SourceRef:
    code: types.CodeType = getattr(function, "__code__")  # noqa: B009 - Callable has no typed __code__
    return SourceRef(_normalize(code.co_filename), code.co_firstlineno, getattr(function, "__name__", "<function>"))


def _field_names(candidate: type) -> tuple[str, ...]:
    """The dataclass field names of a token type (empty for a thin token)."""
    return tuple(field.name for field in fields(cast("Any", candidate)))


def _require_id(value: str, noun: str) -> str:
    if not isinstance(value, str) or not value or "." in value:
        raise CompositionError(f"{noun} id must be one non-empty dot-free segment, got {value!r}")
    return value


# --- typed signatures ----------------------------------------------------------


@dataclass(frozen=True)
class Inscription:
    """One authored pure function lifted into the net as a guard, fold, or emission.

    ``parameters`` are the concrete token types the function reads — including
    ``self`` when the author passed an unbound method reference. ``result`` is
    what it produces. This is the whole contract the compiler needs to wire a
    pure function to arcs.
    """

    function: Callable[..., object]
    parameters: tuple[tuple[str, type], ...]
    result: type
    source: SourceRef

    @property
    def reads(self) -> frozenset[type]:
        return frozenset(annotation for _, annotation in self.parameters)

    def __call__(self, values: Mapping[type, object]) -> object:
        return self.function(**{name: values[annotation] for name, annotation in self.parameters})


def inscribe(function: Callable[..., object], noun: str) -> Inscription:
    """Read one pure function's typed signature, refusing anything unliftable."""
    if not callable(function):
        raise CompositionError(f"{noun} requires a callable, got {function!r}")
    name = getattr(function, "__name__", repr(function))
    call = signature(function)
    try:
        hints = get_type_hints(function)
    except NameError as error:  # pragma: no cover - the tokens module resolves
        raise CompositionError(f"{noun} [{name}] cannot resolve its typed signature: {error}") from None
    parameters: list[tuple[str, type]] = []
    for parameter in call.parameters.values():
        annotation = hints.get(parameter.name)
        if not isinstance(annotation, type):
            raise CompositionError(
                f"{noun} [{name}] parameter {parameter.name!r} needs a concrete token type annotation "
                f"(an unbound method must annotate self)"
            )
        parameters.append((parameter.name, annotation))
    result = hints.get("return")
    if not isinstance(result, type):
        raise CompositionError(f"{noun} [{name}] needs a concrete return type annotation, got {result!r}")
    seen = [annotation for _, annotation in parameters]
    if len(set(seen)) != len(seen):
        raise CompositionError(f"{noun} [{name}] reads one token type twice; arc-color matching is nominal")
    return Inscription(function, tuple(parameters), result, function_site(function))


# --- latches -------------------------------------------------------------------


@dataclass(frozen=True)
class Latch:
    """A thin-token place: its whole content is whether a token is there.

    ``takes`` consumes it (presence required, testable by a guard because the
    token enters the binding); ``without`` inhibits on it (absence required,
    testable *only* by an inhibitor arc); ``fills`` produces it.
    """

    path: str
    color: type
    source: SourceRef


def latch(path: str, color: type) -> Latch:
    if not isinstance(path, str) or not path:
        raise CompositionError(f"latch requires a non-empty place path, got {path!r}")
    if not isinstance(color, type) or _field_names(color):
        raise CompositionError(f"latch [{path}] color must be a field-free thin token type, got {color!r}")
    return Latch(path, color, _call_site(path))


# --- await / fork --------------------------------------------------------------


@dataclass(frozen=True)
class Fork:
    """One firing producing several typed outputs from pure functions."""

    id: str
    projections: tuple[Inscription, ...]
    fills: tuple[Latch, ...]
    source: SourceRef


def fork(id: str, *projections: Callable[..., object], fills: Sequence[Latch] = ()) -> Fork:
    _require_id(id, "fork")
    lifted = tuple(inscribe(projection, "fork projection") for projection in projections)
    if not lifted and not fills:
        raise CompositionError(f"fork [{id}] produces nothing")
    return Fork(id, lifted, tuple(fills), _call_site(id))


@dataclass(frozen=True)
class Await:
    """Typed external ingress under the flow's lifecycle scope."""

    id: str
    event_type: type
    seeds: Fork | None
    source: SourceRef

    def __rshift__(self, target: Choice) -> Wired:
        """Sequence: this ingress's event port feeds one downstream node."""
        if not isinstance(target, Choice):
            raise CompositionError(f"await_ [{self.id}] >> expects a choice(...), got {target!r}")
        return Wired(self, target)


def await_(id: str, event_type: type, *, seeds: Fork | None = None) -> Await:
    """External scoped ingress.

    ``seeds`` fuses a pure ``fork`` into the source firing: current Petrus
    source transitions accept no guards and no input arcs, so the fusion is the
    only way to admit a fact and open its structural state in one durable step.
    """
    _require_id(id, "await_")
    if not isinstance(event_type, type):
        raise CompositionError(f"await_ [{id}] requires a concrete event type, got {event_type!r}")
    if seeds is not None:
        for projection in seeds.projections:
            if projection.reads != frozenset({event_type}):
                raise CompositionError(
                    f"await_ [{id}] seed [{projection.source.symbol}] must read only {event_type.__name__}, "
                    f"got {sorted(annotation.__name__ for annotation in projection.reads)}"
                )
    return Await(id, event_type, seeds, _call_site(id))


# --- join ----------------------------------------------------------------------


@dataclass(frozen=True)
class Join:
    """One firing over several typed inputs.

    ``event`` is consumed. ``reads`` are read arcs — required present, exposed to
    guards, never consumed. ``folds`` are consumed and reproduced, so a branch
    may replace their value; that reproduction is what makes them state.
    """

    event: Await
    reads: tuple[type, ...]
    folds: tuple[type, ...]
    source: SourceRef

    @property
    def ports(self) -> tuple[type, ...]:
        return (self.event.event_type, *self.reads, *self.folds)


def join(event: Await, *, reads: Sequence[type] = (), folds: Sequence[type] = ()) -> Join:
    if not isinstance(event, Await):
        raise CompositionError(f"join requires an await_(...) event, got {event!r}")
    ports = (event.event_type, *reads, *folds)
    if len(set(ports)) != len(ports):
        raise CompositionError(f"join [{event.id}] names one port type twice; one color is one place")
    return Join(event, tuple(reads), tuple(folds), _call_site(event.id))


# --- effect --------------------------------------------------------------------


@dataclass(frozen=True)
class Effect:
    """One Motus Activity fused into the branch firing that decided to run it."""

    id: str
    definition: ActivityDefinition
    request: Inscription
    parameter: str
    result: type
    source: SourceRef


def effect(id: str, definition: ActivityDefinition, *, request: Callable[..., object]) -> Effect:
    _require_id(id, "effect")
    if not isinstance(definition, ActivityDefinition):
        raise CompositionError(f"effect [{id}] requires an @activity definition, got {definition!r}")
    lifted = inscribe(request, f"effect [{id}] request")
    parameters = dict(definition.parameters)
    if len(parameters) != 1:
        raise CompositionError(
            f"effect [{id}] Activity must take exactly one request parameter, got {sorted(parameters)}"
        )
    [(parameter, annotation)] = parameters.items()
    if annotation is not lifted.result:
        raise CompositionError(
            f"effect [{id}] request builds {lifted.result.__name__}, but the Activity accepts "
            f"{getattr(annotation, '__name__', annotation)!r} at {lifted.source}"
        )
    if "operation" not in _field_names(lifted.result):
        raise CompositionError(
            f"effect [{id}] request type {lifted.result.__name__} has no stable 'operation' field; "
            f"correlation and idempotency must survive restart"
        )
    result = definition.result
    if not isinstance(result, type):
        raise CompositionError(f"effect [{id}] Activity needs a concrete result type, got {result!r}")
    return Effect(id, definition, lifted, parameter, result, _call_site(id))


# --- ordered guarded choice ----------------------------------------------------


@dataclass(frozen=True)
class Branch:
    """One rung of an ordered choice: a predicate, a structural pattern, an answer."""

    id: str
    when: Inscription | None  # None marks the otherwise branch
    takes: tuple[Latch, ...]
    without: tuple[Latch, ...]
    fills: tuple[Latch, ...]
    folds: tuple[Inscription, ...]
    emits: tuple[Inscription, ...]
    effect: Effect | None
    source: SourceRef

    @property
    def latches(self) -> frozenset[Latch]:
        return frozenset(self.takes) | frozenset(self.without)

    def excludes(self, other: Branch) -> bool:
        """Structural exclusivity: one branch takes a latch the other forbids."""
        return bool(
            (frozenset(self.takes) & frozenset(other.without)) or (frozenset(self.without) & frozenset(other.takes))
        )


def branch(
    id: str,
    *,
    when: Callable[..., object] | None = None,
    takes: Sequence[Latch] = (),
    without: Sequence[Latch] = (),
    fills: Sequence[Latch] = (),
    folds: Sequence[Callable[..., object]] = (),
    emits: Sequence[Callable[..., object]] = (),
    effect: Effect | None = None,
    site: SourceRef | None = None,
) -> Branch:
    _require_id(id, "branch")
    predicate = None
    if when is not None:
        predicate = inscribe(when, f"branch [{id}] predicate")
        if predicate.result is not bool:
            raise CompositionError(
                f"branch [{id}] predicate [{predicate.source.symbol}] must return bool, "
                f"got {predicate.result.__name__} at {predicate.source}"
            )
    overlap = frozenset(takes) & frozenset(without)
    if overlap:
        raise CompositionError(f"branch [{id}] both takes and forbids {sorted(item.path for item in overlap)}")
    return Branch(
        id,
        predicate,
        tuple(takes),
        tuple(without),
        tuple(fills),
        tuple(inscribe(fold, f"branch [{id}] fold") for fold in folds),
        tuple(inscribe(emit, f"branch [{id}] emission") for emit in emits),
        effect,
        _call_site(id) if site is None else site,
    )


def otherwise(
    id: str,
    *,
    fills: Sequence[Latch] = (),
    folds: Sequence[Callable[..., object]] = (),
    emits: Sequence[Callable[..., object]] = (),
    effect: Effect | None = None,
) -> Branch:
    """The total branch: no predicate, no structural precondition, always last."""
    return branch(id, fills=fills, folds=folds, emits=emits, effect=effect, site=_call_site(id))


@dataclass(frozen=True)
class Choice:
    """Ordered guarded choice: N+1 branches, N+1 generated transitions, N+1 generated guards."""

    id: str
    branches: tuple[Branch, ...]
    source: SourceRef

    def chain(self, index: int) -> tuple[Inscription, ...]:
        """The predicates branch ``index`` must negate.

        ``guard_i = pred_i AND NOT pred_1 AND ... AND NOT pred_{i-1}``, minus
        every earlier predicate whose branch is *structurally* exclusive of this
        one (an inhibitor already separates them, and the earlier predicate may
        be the very same function). Identical predicates are negated once.
        """
        target = self.branches[index]
        negated: list[Inscription] = []
        for earlier in self.branches[:index]:
            if earlier.when is None or earlier.excludes(target):
                continue
            if any(candidate.function is earlier.when.function for candidate in negated):
                continue
            if target.when is not None and target.when.function is earlier.when.function:
                continue
            negated.append(earlier.when)
        return tuple(negated)


def _cover(choice_id: str, group: Sequence[Branch]) -> None:
    """Refuse a predicate group whose structural patterns are not a complete, disjoint cover.

    This is the check experiment B could not have. Branches sharing one
    predicate are separated only by which latches they require present and
    absent. Expanding every branch's partial pattern over the group's latch set
    and demanding an exact partition of ``2**k`` assignments proves, at compile
    time, that exactly one branch of the group is structurally enabled for every
    reachable marking — so a true predicate can never strand its observation.
    """
    latches = sorted({item for candidate in group for item in candidate.latches}, key=lambda item: item.path)
    claimed: dict[tuple[bool, ...], Branch] = {}
    for candidate in group:
        takes, without = frozenset(candidate.takes), frozenset(candidate.without)
        options = [(True,) if item in takes else (False,) if item in without else (True, False) for item in latches]
        for assignment in product(*options):
            prior = claimed.get(assignment)
            if prior is not None:
                raise CompositionError(
                    f"choice [{choice_id}] branches [{prior.id}] at {prior.source} and [{candidate.id}] at "
                    f"{candidate.source} share a predicate and can both be enabled; their latch patterns overlap"
                )
            claimed[assignment] = candidate
    missing = [assignment for assignment in product(*([(True, False)] * len(latches))) if assignment not in claimed]
    if missing:
        gap = missing[0]
        spelling = ", ".join(
            f"{item.path}={'present' if present else 'absent'}" for item, present in zip(latches, gap, strict=True)
        )
        raise CompositionError(
            f"choice [{choice_id}] branch group [{group[0].when.source.symbol if group[0].when else 'otherwise'}] "
            f"leaves {spelling} unanswered; a true predicate would strand its observation"
        )


def choice(id: str, *branches: Branch) -> Choice:
    _require_id(id, "choice")
    if len(branches) < 2:
        raise CompositionError(f"choice [{id}] needs at least one branch and one otherwise(...)")
    seen: dict[str, Branch] = {}
    for candidate in branches:
        if not isinstance(candidate, Branch):
            raise CompositionError(f"choice [{id}] accepts branch(...) values, got {candidate!r}")
        prior = seen.get(candidate.id)
        if prior is not None:
            raise CompositionError(
                f"choice [{id}] declares duplicate branch id [{candidate.id}]: "
                f"first at {prior.source} and again at {candidate.source}"
            )
        seen[candidate.id] = candidate
    total = [index for index, candidate in enumerate(branches) if candidate.when is None]
    if total != [len(branches) - 1]:
        raise CompositionError(
            f"choice [{id}] requires exactly one otherwise(...) branch, last, so every observation is answered"
        )
    groups: dict[object, list[Branch]] = {}
    for candidate in branches[:-1]:
        assert candidate.when is not None
        groups.setdefault(candidate.when.function, []).append(candidate)
    for group in groups.values():
        _cover(id, group)
    return Choice(id, tuple(branches), _call_site(id))


# --- flow ----------------------------------------------------------------------


@dataclass(frozen=True)
class Wired:
    """One sequenced ``producer >> consumer`` pair."""

    producer: Await
    consumer: Choice


@dataclass(frozen=True)
class Lifecycle:
    name: str
    source: SourceRef


def lifecycle(name: str) -> Lifecycle:
    if not isinstance(name, str) or not name:
        raise CompositionError(f"lifecycle requires a non-empty scope name, got {name!r}")
    return Lifecycle(name, _call_site(name))


@dataclass(frozen=True)
class Flow:
    """One authored inscription net: a naming table, a lifecycle, and the nodes."""

    name: str
    lifecycle: Lifecycle
    ports: Mapping[type, str]
    latches: tuple[Latch, ...]
    ingress: tuple[Await, ...]
    joins: Mapping[str, Join]
    choices: tuple[Choice, ...]
    wiring: Mapping[str, str]  # choice id -> the ingress id whose event port it consumes
    source: SourceRef


def flow(
    name: str,
    *,
    lifecycle: Lifecycle,
    ports: Mapping[type, str],
    latches: Sequence[Latch],
    nodes: Sequence[Await | Wired],
    joins: Sequence[Join] = (),
) -> Flow:
    """Assemble and validate one whole inscription net before any lowering."""
    if not isinstance(name, str) or not name:
        raise CompositionError(f"flow requires a non-empty name, got {name!r}")
    _require_nominal_types(ports, latches)

    ingress: list[Await] = []
    choices: list[Choice] = []
    wiring: dict[str, str] = {}
    for node in nodes:
        if isinstance(node, Await):
            ingress.append(node)
        elif isinstance(node, Wired):
            ingress.append(node.producer)
            choices.append(node.consumer)
            wiring[node.consumer.id] = node.producer.id
        else:
            raise CompositionError(
                f"flow [{name}] nodes accept await_(...) or await_(...) >> choice(...), got {node!r}"
            )

    by_event = {candidate.event.id: candidate for candidate in joins}
    for candidate in choices:
        over = by_event.get(wiring[candidate.id])
        if over is None:
            raise CompositionError(f"choice [{candidate.id}] has no join(...) over ingress [{wiring[candidate.id]}]")
        _validate_choice(candidate, over, ports, latches)

    return Flow(
        name,
        lifecycle,
        dict(ports),
        tuple(latches),
        tuple(ingress),
        by_event,
        tuple(choices),
        wiring,
        _call_site(name),
    )


def _require_nominal_types(ports: Mapping[type, str], latches: Sequence[Latch]) -> None:
    colors: dict[str, type] = {}
    for color in (*ports, *(item.color for item in latches)):
        prior = colors.get(color.__name__)
        if prior is not None and prior is not color:
            raise CompositionError(
                f"two distinct classes share the nominal name {color.__name__!r}: {prior!r} and {color!r}"
            )
        colors[color.__name__] = color
    paths = [*ports.values(), *(item.path for item in latches)]
    if len(set(paths)) != len(paths):
        raise CompositionError(f"one place path is claimed twice: {sorted(paths)}")


def _validate_choice(
    candidate: Choice,
    over: Join,
    ports: Mapping[type, str],
    latches: Sequence[Latch],
) -> None:
    available = frozenset(over.ports)
    latch_colors = frozenset(item.color for item in latches)
    for step in candidate.branches:
        if step.when is not None:
            forbidden = step.when.reads & latch_colors
            if forbidden:
                raise CompositionError(
                    f"choice [{candidate.id}] branch [{step.id}] predicate at {step.when.source} reads latch "
                    f"{sorted(color.__name__ for color in forbidden)}; a latch is structure, not a predicate term"
                )
            unknown = step.when.reads - available
            if unknown:
                raise CompositionError(
                    f"choice [{candidate.id}] branch [{step.id}] predicate at {step.when.source} reads "
                    f"{sorted(color.__name__ for color in unknown)}, which the join does not carry"
                )
        producers = (*step.folds, *step.emits, *((step.effect.request,) if step.effect else ()))
        for inscription in producers:
            unknown = inscription.reads - available - frozenset(item.color for item in step.takes)
            if unknown:
                raise CompositionError(
                    f"choice [{candidate.id}] branch [{step.id}] inscription at {inscription.source} reads "
                    f"{sorted(color.__name__ for color in unknown)}, which its firing does not bind"
                )
        for fold in step.folds:
            if fold.result not in over.folds:
                raise CompositionError(
                    f"choice [{candidate.id}] branch [{step.id}] fold at {fold.source} produces "
                    f"{fold.result.__name__}, which is not a folded port of the join"
                )
        for emission in step.emits:
            if emission.result not in ports:
                raise CompositionError(
                    f"choice [{candidate.id}] branch [{step.id}] emission at {emission.source} produces "
                    f"{emission.result.__name__}, which the flow's ports table does not name"
                )
        if step.effect is not None and step.effect.result not in ports:
            raise CompositionError(
                f"choice [{candidate.id}] branch [{step.id}] effect [{step.effect.id}] returns "
                f"{step.effect.result.__name__}, which the flow's ports table does not name"
            )


__all__ = [
    "Await",
    "Branch",
    "Choice",
    "CompositionError",
    "Effect",
    "Flow",
    "Fork",
    "Inscription",
    "Join",
    "Latch",
    "Lifecycle",
    "SourceRef",
    "Wired",
    "await_",
    "branch",
    "choice",
    "effect",
    "flow",
    "fork",
    "function_site",
    "inscribe",
    "join",
    "latch",
    "lifecycle",
    "otherwise",
]
