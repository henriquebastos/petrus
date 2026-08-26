"""Compile one inscription net: the topology **and** the guards are generated.

The developer authors dataflow relationships; nothing in ``inet_scenario.py``
names a place, a transition, an arc, a binding, a token, or a handler URI. This
module derives all of them, and it is the only place that knows Petri.

What it generates, in order:

1. **Places from types.** One color is one place; the flow's ``ports`` table and
   its ``latch`` declarations supply the paths.
2. **Ingress.** One source transition per ``await_``. A fused ``fork`` becomes
   that source transition's projection — the only way to open structural state
   atomically with the fact that justifies it, because current Petrus source
   transitions accept no guards and no input arcs.
3. **One transition per choice branch**, with a fixed arc role table:
   ``consume event, consume folded ports, consume taken latches, read read-ports,
   inhibit forbidden latches`` then ``produce folded ports, produce filled
   latches, produce emissions, produce the effect result``. Arc emission order is
   canonical Net v3 arc order, so the table is a contract.
4. **The exclusive guard chain.** Branch ``i`` gets one synthesized
   ``typed_guard`` computing ``pred_i AND NOT pred_j ...`` over the branch's own
   binding. Overlapping authored predicates therefore cannot produce two enabled
   candidates: exclusivity is a property of the compiler, not of the author.
5. **Fused effects.** An Activity branch's transition is the *only* transition
   that observation touches: the guard decides, ``ActivityRequested`` makes the
   decision durable before dispatch, and the projection writes the folded state,
   the filled latches, and the result fact together.

``DerivedActivityHandler`` cannot be reused for step 5 — it refuses any output
arc whose color is not the Activity result — so the compiler owns a small
prepare/project bridge instead. That refusal is recorded as a finding, not
worked around silently.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from inspect import Parameter, Signature
from types import MappingProxyType
from typing import Any, cast

from petrus.impetus.binding import ActivityHandler, Handler
from petrus.impetus.dsl import BuiltNet, GuardSpec, HandlerSpec, NetSpec, arc, petri_handler, typed_guard
from petrus.impetus.net_definition import (
    parse_net_definition,
    project_net_definition,
    serialize_net_definition,
)
from petrus.impetus.petrinet import Arc, Marking, NetPath, NetUri, Token
from petrus.impetus.petrinet.enabledness import Binding, Guard
from petrus.impetus.petrinet.schema import Cel
from petrus.motus.activity import ActivityDefinition, ActivityInvocation, ExecutionPolicy

from inet_kernel import (
    Await,
    Branch,
    Choice,
    CompositionError,
    Effect,
    Flow,
    Inscription,
    Join,
    SourceRef,
)
from inet_tokens import CONVERTER, from_data, to_data
from source_map import SourceMapV1, build_source_map

EVALUATIONS: dict[str, int] = {}
"""Authored-predicate call counts, keyed by symbol.

Guard evaluation is never recorded in History, so the only honest way to report
what a generated ``NOT`` chain costs is to count it deliberately. Tests reset and
read this; nothing in the net reads it, so determinism is untouched.
"""


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


type _Produced = Mapping[NetPath | str, Sequence[Token]]
type _Values = Mapping[type, object]


@dataclass(frozen=True)
class IngressBinding:
    """How one authored ingress delivers through the Engine."""

    source: str
    event_type: type
    scope_name: str


@dataclass(frozen=True)
class BranchPlan:
    """The compiler's fixed lowering record for one branch, for tests and the report."""

    id: str
    transition: str
    predicate: str | None
    negated: tuple[str, ...]
    takes: tuple[str, ...]
    without: tuple[str, ...]
    fills: tuple[str, ...]
    effect: str | None
    emits: tuple[str, ...]
    cel_filter: str | None


@dataclass(frozen=True)
class CompiledFlow:
    """One immutable canonical assembly around the authored inscription net."""

    built: BuiltNet
    handlers: Mapping[NetUri, Handler | ActivityHandler]
    guards: Mapping[NetUri, Guard]
    activities: tuple[ActivityDefinition, ...]
    initial_marking: Marking
    ingress: Mapping[str, IngressBinding]
    source_map: SourceMapV1
    definition_bytes: bytes
    branches: tuple[BranchPlan, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "handlers", MappingProxyType(dict(self.handlers)))
        object.__setattr__(self, "ingress", MappingProxyType(dict(self.ingress)))


# --- pure inscription evaluation ----------------------------------------------


def _decode(binding: Binding) -> dict[type, object]:
    """Decode a firing's bound tokens into typed values, keyed by their color.

    One color is one place, so a color is an unambiguous key. Consumed and read
    selections are both bound; inhibit arcs contribute no selection at all, which
    is exactly why absence is untestable by a guard.
    """
    values: dict[type, object] = {}
    for _, tokens in (*binding.consumed, *binding.read):
        for token in tokens:
            if token.color is None:  # pragma: no cover - every port of this kernel is colored
                continue
            annotation = _COLORS[token.color]
            values[annotation] = from_data(annotation, token.data)
    return values


_COLORS: dict[str, type] = {}
"""Nominal color to token type, populated per lowering from the flow's ports."""


def _evaluate(inscription: Inscription, values: _Values) -> object:
    EVALUATIONS[inscription.source.symbol] = EVALUATIONS.get(inscription.source.symbol, 0) + 1
    return inscription(values)


def _guard_parameters(colors: Sequence[type]) -> tuple[tuple[str, type], ...]:
    return tuple((color.__name__.lower(), color) for color in colors)


def _chain_guard(
    branch: Branch,
    negated: Sequence[Inscription],
    parameters: Sequence[tuple[str, type]],
) -> Callable[..., bool]:
    """Synthesize ``pred_i AND NOT pred_j ...`` as one typed predicate over the whole binding.

    ``derive_typed_guard`` requires every non-inhibit input arc to be matched by a
    typed parameter, so the synthesized signature names all of them even when the
    authored predicates read fewer. The signature and annotations are attached
    explicitly; nothing is inferred from a closure.
    """
    lookup = tuple(parameters)
    target = branch.when
    terms = tuple(negated)

    def generated(**arguments: object) -> bool:
        values = {annotation: arguments[name] for name, annotation in lookup}
        if target is not None and not _evaluate(target, values):
            return False
        return all(not _evaluate(term, values) for term in terms)

    prepared: Any = generated
    prepared.__name__ = f"{branch.id}_guard"
    prepared.__qualname__ = prepared.__name__
    prepared.__signature__ = Signature(
        [Parameter(name, Parameter.KEYWORD_ONLY, annotation=annotation) for name, annotation in lookup],
        return_annotation=bool,
    )
    prepared.__annotations__ = {name: annotation for name, annotation in lookup} | {"return": bool}
    return generated


# --- Activity bridge -----------------------------------------------------------


@dataclass(frozen=True)
class _FusedActivityHandler:
    """Prepare and project one Activity fused into the branch firing that decided it.

    ``DerivedActivityHandler`` refuses this shape: it raises for any output arc
    whose color differs from the Activity result, and a fused branch also
    reproduces its folded state and fills its latches. The compiler therefore
    owns the bridge — still through the public ``ActivityHandler`` protocol, with
    ``ExecutionPolicy(attempts=1)`` so Motus retries never manufacture a business
    rung, and with correlation/idempotency taken from the request's stable
    ``operation`` so restart redispatches one logical operation.
    """

    effect: Effect
    pure: Callable[[Binding], dict[NetPath | str, Sequence[Token]]]
    fact_place: str
    transition: str

    def prepare(self, binding: Binding) -> ActivityInvocation:
        request = _evaluate(self.effect.request, _decode(binding))
        operation = getattr(request, "operation", None)
        if not isinstance(operation, str) or not operation:  # pragma: no cover - refused before lowering
            raise ValueError(f"Activity request for {self.transition} has no stable operation id")
        return ActivityInvocation(
            self.effect.definition.declaration.name,
            input={self.effect.parameter: to_data(request)},
            policy=ExecutionPolicy(attempts=1),
            correlation=operation,
            idempotency=operation,
        )

    def project(self, binding: Binding, result: object) -> _Produced:
        produced = self.pure(binding)
        produced[self.fact_place] = (Token(self.effect.result.__name__, result),)
        return produced


# --- lowering ------------------------------------------------------------------


class _Lowering:
    """One deterministic lowering of one authored inscription net."""

    def __init__(self, authored: Flow) -> None:
        if not isinstance(authored, Flow):
            raise CompositionError(f"compile_flow requires a flow(...), got {authored!r}")
        self.flow = authored
        self.spec = NetSpec(authored.name)
        self.sources: dict[str, SourceRef] = {}
        self.ownership: dict[str, tuple[str, str]] = {}
        self.kinds: dict[str, str] = {}
        self.places: dict[type, str] = dict(authored.ports)
        for item in authored.latches:
            self.places[item.color] = item.path
        self.activity_bindings: list[tuple[str, _FusedActivityHandler]] = []
        self.activities: list[ActivityDefinition] = []
        self.ingress: dict[str, IngressBinding] = {}
        self.plans: list[BranchPlan] = []

    # -- node and arc declaration ---------------------------------------------

    def _handle(self, path: str, kind: str):
        *scopes, leaf = path.split(".")
        view = self.spec.s
        for scope in scopes:
            view = view[scope]
        return getattr(view.p if kind == "place" else view.t, leaf)

    def _source(self, local_id: str, reference: SourceRef) -> str:
        source_id = f"{self.flow.name}.{local_id}"
        existing = self.sources.get(source_id)
        if existing is not None and existing != reference:
            raise CompositionError(f"source id {source_id!r} registered twice with different references")
        self.sources[source_id] = reference
        return source_id

    def _own(self, path: str, kind: str, source_id: str, role: str) -> None:
        if path in self.ownership:
            raise CompositionError(f"node {path} already has source ownership")
        self.ownership[path] = (source_id, role)
        self.kinds[path] = kind

    def place(self, color: type, source_id: str, role: str) -> str:
        path = self.places[color]
        self.spec.place(self._handle(path, "place"), color=color)
        self._own(path, "place", source_id, role)
        return path

    def transition(self, path: str, handler: HandlerSpec | str | None, source_id: str, role: str, guards=()) -> str:
        self.spec.transition(self._handle(path, "transition"), handler=handler, guards=guards)
        self._own(path, "transition", source_id, role)
        return path

    def connect(self, source: str, target: str, *, mode: str = "consume", filter: Cel | None = None) -> None:
        source_node = self._handle(source, self.kinds[source])
        target_node = self._handle(target, self.kinds[target])
        if mode == "consume":
            source_node >> arc(filter=filter) >> target_node
        elif mode == "read":
            source_node >> arc.read() >> target_node
        else:
            source_node >> arc.inhibit() >> target_node

    # -- passages ---------------------------------------------------------------

    def compile(self) -> CompiledFlow:
        _COLORS.clear()
        for color in self.places:
            _COLORS[color.__name__] = color
        self.sources[self.flow.name] = self.flow.source
        self._source(f"lifecycle.{self.flow.lifecycle.name}", self.flow.lifecycle.source)
        self._declare_places()
        for ingress in self.flow.ingress:
            self._lower_ingress(ingress)
        for candidate in self.flow.choices:
            self._lower_choice(candidate, self.flow.joins[self.flow.wiring[candidate.id]])

        built = self.spec.build()
        handlers: dict[NetUri, Handler | ActivityHandler] = dict(built.handlers)
        for path, bridge in self.activity_bindings:
            uri = built.net.handler_uri(NetPath(path))
            if uri is None:  # pragma: no cover - NetSpec.build carries every declared symbol
                raise CompositionError(f"Activity transition {path} lost its canonical handler URI")
            handlers[uri] = bridge

        definition_bytes = serialize_net_definition(project_net_definition(built.net))
        parse_net_definition(definition_bytes)
        source_map = build_source_map(
            built.net,
            self.sources,
            self.ownership,
            ((self.flow.lifecycle.name, f"{self.flow.name}.lifecycle.{self.flow.lifecycle.name}"),),
            definition_bytes,
        )
        return CompiledFlow(
            built=built,
            handlers=handlers,
            guards=built.guards,
            activities=tuple(self.activities),
            initial_marking=Marking(),
            ingress=self.ingress,
            source_map=source_map,
            definition_bytes=definition_bytes,
            branches=tuple(self.plans),
        )

    def _declare_places(self) -> None:
        """Allocate one place per color, each owned by the construct that produces it."""
        owners: dict[type, tuple[str, str]] = {}
        for ingress in self.flow.ingress:
            if ingress.seeds is None:
                owners[ingress.event_type] = (self._source(ingress.id, ingress.source), "typed event port")
                continue
            for projection in ingress.seeds.projections:
                owner = self._source(f"{ingress.seeds.id}.{projection.source.symbol}", projection.source)
                owners[projection.result] = (owner, "seeded generation state")
        for item in self.flow.latches:
            owners[item.color] = (self._source(f"latch.{item.path}", item.source), "structural latch")
        for candidate in self.flow.choices:
            for step in candidate.branches:
                for emission in step.emits:
                    owner = self._source(f"{candidate.id}.{step.id}.{emission.source.symbol}", emission.source)
                    owners[emission.result] = (owner, "terminal fact")
                if step.effect is not None:
                    owner = self._source(f"{candidate.id}.{step.id}.{step.effect.id}", step.effect.source)
                    owners[step.effect.result] = (owner, "effect result fact")
        for color in self.places:
            owner = owners.get(color)
            if owner is None:
                raise CompositionError(f"port {color.__name__} is named by the ports table but nothing produces it")
            self.place(color, owner[0], owner[1])

    def _lower_ingress(self, ingress: Await) -> None:
        owner = self._source(ingress.id, ingress.source)
        path = f"ingress.{ingress.id}"
        if ingress.seeds is None:
            self.transition(path, None, owner, "typed scoped ingress")
            self.connect(path, self.places[ingress.event_type])
        else:
            fork = ingress.seeds
            self._source(fork.id, fork.source)
            self.transition(
                path,
                petri_handler(self._seed_handler(ingress)),
                owner,
                "typed scoped ingress fused with the generation's opening fork",
            )
            for projection in fork.projections:
                self.connect(path, self.places[projection.result])
            for item in fork.fills:
                self.connect(path, item.path)
        self.ingress[ingress.id] = IngressBinding(path, ingress.event_type, self.flow.lifecycle.name)

    def _seed_handler(self, ingress: Await) -> Handler:
        fork = ingress.seeds
        assert fork is not None
        event_type = ingress.event_type
        places = self.places

        def seed(binding: Binding, outputs: tuple[Arc, ...]) -> _Produced:
            del outputs
            [token] = binding.delivered
            values: dict[type, object] = {event_type: from_data(event_type, token.data)}
            produced: dict[NetPath | str, Sequence[Token]] = {}
            for projection in fork.projections:
                value = _evaluate(projection, values)
                produced[places[projection.result]] = (Token(projection.result.__name__, to_data(value)),)
            for item in fork.fills:
                produced[item.path] = (Token(item.color.__name__, {}),)
            return produced

        return seed

    def _lower_choice(self, candidate: Choice, over: Join) -> None:
        self._source(candidate.id, candidate.source)
        for index, step in enumerate(candidate.branches):
            self._lower_branch(candidate, over, index, step)

    def _lower_branch(self, candidate: Choice, over: Join, index: int, step: Branch) -> None:
        owner = self._source(f"{candidate.id}.{step.id}", step.source)
        path = f"{candidate.id}.{step.id}"
        negated = candidate.chain(index)
        consumed: tuple[type, ...] = (over.event.event_type, *over.folds, *(item.color for item in step.takes))
        parameters = _guard_parameters((*consumed, *over.reads))
        guard: GuardSpec = typed_guard(_chain_guard(step, negated, parameters), converter=CONVERTER)
        pure = self._pure_projection(over, step)
        role = self._role(step)

        if step.effect is None:
            self.transition(path, petri_handler(self._pure_handler(pure)), owner, role, guards=(guard,))
        else:
            self._source(f"{candidate.id}.{step.id}.{step.effect.id}", step.effect.source)
            definition = step.effect.definition
            self.transition(path, definition.declaration.name, owner, role, guards=(guard,))
            if definition not in self.activities:
                self.activities.append(definition)
            self.activity_bindings.append(
                (path, _FusedActivityHandler(step.effect, pure, self.places[step.effect.result], path))
            )

        # Fixed arc role table; NetSpec connection order is canonical v3 arc order.
        self.connect(self.places[over.event.event_type], path, filter=CEL_FILTERS.get(_predicate_key(step)))
        for color in over.folds:
            self.connect(self.places[color], path)
        for item in step.takes:
            self.connect(item.path, path)
        for color in over.reads:
            self.connect(self.places[color], path, mode="read")
        for item in step.without:
            self.connect(item.path, path, mode="inhibit")
        for color in over.folds:
            self.connect(path, self.places[color])
        for item in step.fills:
            self.connect(path, item.path)
        for emission in step.emits:
            self.connect(path, self.places[emission.result])
        if step.effect is not None:
            self.connect(path, self.places[step.effect.result])

        self.plans.append(
            BranchPlan(
                id=step.id,
                transition=path,
                predicate=None if step.when is None else step.when.source.symbol,
                negated=tuple(term.source.symbol for term in negated),
                takes=tuple(item.path for item in step.takes),
                without=tuple(item.path for item in step.without),
                fills=tuple(item.path for item in step.fills),
                effect=None if step.effect is None else step.effect.id,
                emits=tuple(emission.result.__name__ for emission in step.emits),
                cel_filter=None
                if _predicate_key(step) not in CEL_FILTERS
                else CEL_FILTERS[_predicate_key(step)].expression,
            )
        )

    @staticmethod
    def _role(step: Branch) -> str:
        if step.effect is not None:
            return f"guarded branch [{step.id}] — decision fused with the {step.effect.id} effect"
        if step.emits:
            return f"guarded branch [{step.id}] — decision producing a terminal fact"
        return f"guarded branch [{step.id}] — durable absorption"

    def _pure_projection(self, over: Join, step: Branch) -> Callable[[Binding], dict[NetPath | str, Sequence[Token]]]:
        """The branch's folded ports, filled latches, and emissions — everything but the effect result."""
        places = self.places
        folds = {fold.result: fold for fold in step.folds}

        def project(binding: Binding) -> dict[NetPath | str, Sequence[Token]]:
            values = _decode(binding)
            produced: dict[NetPath | str, Sequence[Token]] = {}
            for color in over.folds:
                fold = folds.get(color)
                value = values[color] if fold is None else _evaluate(fold, values)
                produced[places[color]] = (Token(color.__name__, to_data(value)),)
            for item in step.fills:
                produced[item.path] = (Token(item.color.__name__, {}),)
            for emission in step.emits:
                value = _evaluate(emission, values)
                produced[places[emission.result]] = (Token(emission.result.__name__, to_data(value)),)
            return produced

        return project

    @staticmethod
    def _pure_handler(project: Callable[[Binding], dict[NetPath | str, Sequence[Token]]]) -> Handler:
        def fire(binding: Binding, outputs: tuple[Arc, ...]) -> _Produced:
            del outputs
            return cast("_Produced", project(binding))

        return fire


def _predicate_key(step: Branch) -> object:
    return None if step.when is None else step.when.function


CEL_FILTERS: dict[object, Cel] = {}
"""Method-to-``Cel`` spellings the compiler emits as canonical arc filters.

The CEL probe. A ``Cel`` arc filter serializes **into** canonical Net v3 bytes
(``arcs[].filter``), unlike a Python-bound guard, which projects as an anonymous
declaration. Populated by the authored scenario; see the report for exactly what
the CEL vocabulary could and could not reach.
"""


def compile_flow(authored: Flow) -> CompiledFlow:
    """Compile one authored inscription net into an immutable canonical assembly."""
    return _Lowering(authored).compile()


__all__ = [
    "CEL_FILTERS",
    "EVALUATIONS",
    "BranchPlan",
    "CompiledFlow",
    "IngressBinding",
    "compile_flow",
]
