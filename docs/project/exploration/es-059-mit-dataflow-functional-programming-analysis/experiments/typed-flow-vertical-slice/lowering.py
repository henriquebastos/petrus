"""One pure compilation passage from the authored machine to canonical Net v3.

Lowering order (fixed role tables, never unordered mappings):

1. validate ids, nominal types, source references, branch exhaustiveness, and
   the lifecycle declaration (the algebra already refused local mistakes);
2. allocate deterministic node paths and record their authored owner;
3. declare places, transitions, and arcs into one ``NetSpec`` in the fixed
   transition order — ingress, decision, simple effects, descent fragments,
   folds — so canonical arc positions are a contract;
4. let low-level fragments declare their nodes/arcs under their assigned scope;
5. call ``NetSpec.build()`` once, retaining its ``BuiltNet`` bindings;
6. derive typed Activity handlers against the canonical ``Net`` and merge them
   by the transition's canonical handler URI;
7. project/serialize/strictly parse Net v3;
8. finish the source-map sidecar bound to the definition hash; and
9. return immutable snapshots.

Generated names derive only from the machine name, explicit authored ids,
nominal outcome colors, and fixed semantic roles — never object identity,
hashes, registration order, or callable names.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import cast

from petrus.impetus.binding import ActivityHandler, DerivedActivityHandler, Handler
from petrus.impetus.dsl import BuiltNet, HandlerSpec, NetSpec, arc, petri_handler
from petrus.impetus.net_definition import (
    parse_net_definition,
    project_net_definition,
    serialize_net_definition,
)
from petrus.impetus.petrinet import Arc, Marking, NetPath, NetUri, Token
from petrus.impetus.petrinet.enabledness import Binding, Guard
from petrus.motus.activity import ActivityDefinition, ActivityInvocation, ExecutionPolicy

from algebra import (
    AwaitEvent,
    Choose,
    CompositionError,
    Decide,
    Decision,
    Drop,
    Effect,
    Fold,
    LowLevel,
    Machine,
    Project,
    SourceRef,
    Terminal,
    To,
    require_operation_field,
)
from domain import from_data, to_data
from source_map import SourceMapV1, build_source_map


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _command_base(outcome_type: type) -> str:
    """The fixed command/effect base name for one routed outcome color."""
    return _snake(outcome_type.__name__.removesuffix("Requested"))


@dataclass(frozen=True)
class IngressBinding:
    """How one authored ingress delivers through the Engine."""

    source: str
    event_type: type
    scope_name: str


@dataclass(frozen=True)
class FragmentPorts:
    """The typed boundary a low-level fragment acknowledges back to the compiler."""

    input: str
    output: str


@dataclass(frozen=True)
class CompiledFlow:
    """One immutable experiment assembly value around the canonical snapshot.

    The existing ``Net`` remains canonical topology; ``handlers``/``guards``
    are live bindings; History is created only by the harness.
    """

    built: BuiltNet
    handlers: Mapping[NetUri, Handler | ActivityHandler]
    guards: Mapping[NetUri, Guard]
    activities: tuple[ActivityDefinition, ...]
    initial_marking: Marking  # empty; the first scoped head seeds state
    ingress: Mapping[str, IngressBinding]
    source_map: SourceMapV1
    definition_bytes: bytes

    def __post_init__(self) -> None:
        object.__setattr__(self, "handlers", MappingProxyType(dict(self.handlers)))
        object.__setattr__(self, "ingress", MappingProxyType(dict(self.ingress)))


@dataclass(frozen=True)
class _OperationActivityHandler:
    """Stamp the request's stable operation as correlation and idempotency.

    Composes the current ``DerivedActivityHandler``; result projection is
    delegated untouched. All Activities run under ``ExecutionPolicy(attempts=1)``
    — the domain, not Motus retries, decides whether to rerun or repair.
    """

    derived: DerivedActivityHandler

    def prepare(self, binding: Binding) -> ActivityInvocation:
        invocation = self.derived.prepare(binding)
        [payload] = cast("Mapping[str, object]", invocation.input).values()
        operation = cast("dict[str, object]", payload).get("operation") if isinstance(payload, dict) else None
        if not isinstance(operation, str) or not operation:
            raise ValueError(f"Activity request for {binding.transition} has no stable operation id")
        return replace(
            invocation,
            policy=ExecutionPolicy(attempts=1),
            correlation=operation,
            idempotency=operation,
        )

    def project(self, binding: Binding, result: object):
        return self.derived.project(binding, result)


type _Produced = Mapping[NetPath | str, Sequence[Token]]


def _fused_projection(step: Project, state_place: str) -> Handler:
    """Compiler-owned typed source projection: accept the event, seed the state."""
    state_color = step.state_type.__name__

    def source_projection(binding: Binding, outputs: tuple[Arc, ...]) -> _Produced:
        del outputs
        [token] = binding.delivered
        event = from_data(step.event_type, token.data)
        state = step.function(event)
        return {state_place: (Token(state_color, to_data(state)),)}

    return source_projection


def _decision_bridge(
    step: Decide,
    state_place: str,
    case_places: Mapping[type, str | None],
) -> Handler:
    """Compiler-owned Petri bridge: one durable decision, one routed outcome."""
    state_color = step.state_type.__name__
    routes = dict(case_places)

    def decide_and_route(binding: Binding, outputs: tuple[Arc, ...]) -> _Produced:
        del outputs
        (_, (state_token,)), (_, (event_token,)) = binding.consumed
        state = from_data(step.state_type, state_token.data)
        event = from_data(step.event_type, event_token.data)
        decision = cast("Decision[object, object]", step.function(state, event))
        produced: dict[NetPath | str, Sequence[Token]] = {state_place: (Token(state_color, to_data(decision.state)),)}
        outcome = decision.outcome
        if type(outcome) not in routes:
            raise ValueError(f"decide [{step.id}] returned undeclared outcome {type(outcome).__name__}")
        target = routes[type(outcome)]
        if target is not None:
            produced[target] = (Token(type(outcome).__name__, to_data(outcome)),)
        return produced

    return decide_and_route


def _fold_bridge(step: Fold, state_place: str, terminal_place: str) -> Handler:
    """Compiler-owned Petri bridge: durable state fold plus one typed output."""
    state_color = step.state_type.__name__
    output_color = step.output_type.__name__

    def fold_and_emit(binding: Binding, outputs: tuple[Arc, ...]) -> _Produced:
        del outputs
        (_, (state_token,)), (_, (event_token,)) = binding.consumed
        state = from_data(step.state_type, state_token.data)
        event = from_data(step.event_type, event_token.data)
        next_state, output = cast("tuple[object, object]", step.function(state, event))
        return {
            state_place: (Token(state_color, to_data(next_state)),),
            terminal_place: (Token(output_color, to_data(output)),),
        }

    return fold_and_emit


class FragmentContext:
    """The bounded raw-``NetSpec`` surface one low-level fragment may use.

    Every node the fragment declares lives under its assigned scope and gets
    source-map ownership, and every arc it draws stays between its own nodes
    and its two supplied ports — a fragment cannot reach any other authored
    node. The compiler re-verifies the nodes after canonical build.
    """

    def __init__(
        self,
        lowering: _Lowering,
        descent: LowLevel,
        scope: str,
        input_place: str,
        input_type: type,
        output_place: str,
        owner: str,
    ) -> None:
        self._lowering = lowering
        self.scope = scope
        self.input = input_place
        self.input_type = input_type
        self.returns = descent.returns
        self.output = output_place
        self._owner = owner
        self.declared: list[tuple[str, str]] = []  # (kind, path) in declaration order

    def _scoped(self, name: str) -> str:
        if not name or "." in name:
            raise CompositionError(f"fragment node name must be one dot-free segment, got {name!r}")
        return f"{self.scope}.{name}"

    def _admitted(self, path: str) -> str:
        """An arc endpoint must be a fragment-owned node or one supplied port."""
        if path.startswith(f"{self.scope}.") or path in (self.input, self.output):
            return path
        raise CompositionError(f"fragment arc endpoint {path} is outside scope {self.scope} and is not a supplied port")

    def place(self, name: str, *, color: type | None = None, role: str) -> str:
        path = self._scoped(name)
        self._lowering.place(path, color, self._owner, role)
        self.declared.append(("place", path))
        return path

    def transition(self, name: str, handler: HandlerSpec, *, role: str) -> str:
        path = self._scoped(name)
        self._lowering.transition(path, handler, self._owner, role)
        self.declared.append(("transition", path))
        return path

    def activity_transition(self, name: str, definition: ActivityDefinition, *, role: str) -> str:
        path = self._scoped(name)
        self._lowering.activity_transition(path, definition, self._owner, role)
        self.declared.append(("transition", path))
        return path

    def consume(self, source: str, target: str) -> None:
        self._lowering.connect(self._admitted(source), self._admitted(target))

    def inhibit(self, place: str, transition: str) -> None:
        self._lowering.connect(self._admitted(place), self._admitted(transition), mode="inhibit")

    def produce(self, transition: str, place: str) -> None:
        self._lowering.connect(self._admitted(transition), self._admitted(place))


class _Lowering:
    """One deterministic lowering of one authored machine."""

    def __init__(self, flow: Machine) -> None:
        if not isinstance(flow, Machine):
            raise CompositionError(f"compile_flow requires a machine(...), got {flow!r}")
        self.flow = flow
        self.spec = NetSpec(flow.name)
        self.sources: dict[str, SourceRef] = {}
        self.ownership: dict[str, tuple[str, str]] = {}
        self.kinds: dict[str, str] = {}
        self.activity_bindings: list[tuple[str, ActivityDefinition]] = []
        self.activities: list[ActivityDefinition] = []
        self.ingress: dict[str, IngressBinding] = {}
        self.fragments: list[tuple[LowLevel, FragmentContext, FragmentPorts]] = []
        self.fact_places: dict[type, str] = {}
        self.state_place: str | None = None
        self.state_type: type | None = None

    # -- node and arc declaration ---------------------------------------------

    def _node_handle(self, path: str, kind: str):
        *scopes, leaf = path.split(".")
        view = self.spec.s
        for scope in scopes:
            view = view[scope]
        return getattr(view.p if kind == "place" else view.t, leaf)

    def _source_id(self, local_id: str) -> str:
        return f"{self.flow.name}.{local_id}"

    def _register_source(self, local_id: str, reference: SourceRef) -> str:
        source_id = self._source_id(local_id)
        existing = self.sources.get(source_id)
        if existing is not None and existing != reference:
            raise CompositionError(f"source id {source_id!r} registered twice with different references")
        self.sources[source_id] = reference
        return source_id

    def _own(self, path: str, kind: str, source_id: str, role: str) -> None:
        if path in self.ownership:
            raise CompositionError(f"node {path} already has source ownership")
        if source_id not in self.sources:
            raise CompositionError(f"node {path} names unknown source id {source_id!r}")
        self.ownership[path] = (source_id, role)
        self.kinds[path] = kind

    def place(self, path: str, color: type | None, source_id: str, role: str) -> str:
        node = self._node_handle(path, "place")
        if color is not None:
            self.spec.place(node, color=color)
        self._own(path, "place", source_id, role)
        return path

    def transition(self, path: str, handler: HandlerSpec | str | None, source_id: str, role: str) -> str:
        node = self._node_handle(path, "transition")
        if handler is not None:
            self.spec.transition(node, handler=handler)
        self._own(path, "transition", source_id, role)
        return path

    def activity_transition(self, path: str, definition: ActivityDefinition, source_id: str, role: str) -> str:
        for request_type in definition.parameters.values():
            if isinstance(request_type, type):
                require_operation_field(request_type, f"Activity transition {path}")
        self.transition(path, definition.declaration.name, source_id, role)
        self.activity_bindings.append((path, definition))
        if definition not in self.activities:
            self.activities.append(definition)
        return path

    def connect(self, source: str, target: str, *, mode: str = "consume") -> None:
        source_kind = self.kinds.get(source)
        target_kind = self.kinds.get(target)
        if source_kind is None or target_kind is None:
            raise CompositionError(f"arc {source} -> {target} references an undeclared node")
        source_node = self._node_handle(source, source_kind)
        target_node = self._node_handle(target, target_kind)
        if mode == "consume":
            source_node >> target_node
        elif mode == "inhibit":
            source_node >> arc.inhibit() >> target_node
        else:  # pragma: no cover - the bounded surface offers two modes
            raise CompositionError(f"unsupported arc mode {mode!r}")

    # -- handler-chain lowering -----------------------------------------------

    def compile(self) -> CompiledFlow:
        self.sources[self.flow.name] = self.flow.source  # the authored root machine
        self._register_source(f"lifecycle.{self.flow.lifecycle.name}", self.flow.lifecycle.source)
        for chain in self.flow.handlers:
            self._lower_chain(chain)
        built = self.spec.build()
        handlers: dict[NetUri, Handler | ActivityHandler] = dict(built.handlers)
        for path, definition in self.activity_bindings:
            uri = built.net.handler_uri(NetPath(path))
            if uri is None:  # NetSpec.build carries every declared handler symbol through
                raise CompositionError(f"Activity transition {path} lost its canonical handler URI")
            handlers[uri] = _OperationActivityHandler(DerivedActivityHandler(built.net, NetPath(path), definition))
        self._verify_fragments(built)
        definition_bytes = serialize_net_definition(project_net_definition(built.net))
        parse_net_definition(definition_bytes)
        source_map = build_source_map(
            built.net,
            self.sources,
            self.ownership,
            ((self.flow.lifecycle.name, self._source_id(f"lifecycle.{self.flow.lifecycle.name}")),),
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
        )

    def _lower_chain(self, chain) -> None:
        trigger = chain.trigger
        steps = chain.steps
        if isinstance(trigger, AwaitEvent):
            if len(steps) == 1 and isinstance(steps[0], Project):
                self._lower_ingress_projection(trigger, steps[0])
            elif len(steps) == 2 and isinstance(steps[0], Decide) and isinstance(steps[1], Choose):
                self._lower_ingress_decision(trigger, steps[0], steps[1])
            elif not steps:
                self._lower_bare_ingress(trigger)
            else:
                raise CompositionError(
                    f"[{trigger.id}] this slice lowers await_event chains of project or decide+choose"
                )
        elif isinstance(trigger, type):
            if len(steps) == 2 and isinstance(steps[0], Fold) and isinstance(steps[1], To):
                self._lower_fact_fold(trigger, steps[0], steps[1])
            else:
                raise CompositionError(f"on({trigger.__name__}) requires a fold(...).to(terminal(...)) chain")
        else:  # pragma: no cover - the algebra's on() refuses other triggers
            raise CompositionError(f"unsupported trigger {trigger!r}")

    def _lower_bare_ingress(self, trigger: AwaitEvent) -> None:
        owner = self._register_source(trigger.id, trigger.source)
        source_path = self.transition(f"ingress.{trigger.id}", None, owner, "typed scoped ingress")
        event_place = self.place(f"events.{trigger.id}", trigger.event_type, owner, "typed event place")
        self.connect(source_path, event_place)
        self.ingress[trigger.id] = IngressBinding(source_path, trigger.event_type, self.flow.lifecycle.name)

    def _state_place_for(self, state_type: type, owner_path: str) -> str:
        if self.state_place is None:
            raise CompositionError(f"{owner_path} needs the state baton, but no project(...) seeded one")
        if self.state_type is not state_type:
            assert self.state_type is not None
            raise CompositionError(
                f"{owner_path} folds state {state_type.__name__}, but the seeded baton is {self.state_type.__name__}"
            )
        return self.state_place

    def _lower_ingress_projection(self, trigger: AwaitEvent, step: Project) -> None:
        ingress_owner = self._register_source(trigger.id, trigger.source)
        project_owner = self._register_source(step.id, step.source)
        if self.state_place is not None:
            raise CompositionError(f"project [{step.id}] would seed a second state baton")
        self.state_place = self.place(
            f"{self.flow.name}.state", step.state_type, project_owner, "generation state baton"
        )
        self.state_type = step.state_type
        # The fused firing splits attribution along the authored block: event
        # acceptance belongs to the await, the seeded state to the projection.
        source_path = self.transition(
            f"ingress.{trigger.id}",
            petri_handler(_fused_projection(step, self.state_place)),
            ingress_owner,
            "typed scoped ingress fused with durable state projection",
        )
        self.connect(source_path, self.state_place)
        self.ingress[trigger.id] = IngressBinding(source_path, trigger.event_type, self.flow.lifecycle.name)

    def _lower_ingress_decision(self, trigger: AwaitEvent, decide: Decide, choose: Choose) -> None:
        ingress_owner = self._register_source(trigger.id, trigger.source)
        decide_owner = self._register_source(decide.id, decide.source)
        state_place = self._state_place_for(decide.state_type, f"decide [{decide.id}]")

        source_path = self.transition(f"ingress.{trigger.id}", None, ingress_owner, "typed scoped ingress")
        event_place = self.place(f"events.{trigger.id}", trigger.event_type, ingress_owner, "typed event place")
        self.connect(source_path, event_place)
        self.ingress[trigger.id] = IngressBinding(source_path, trigger.event_type, self.flow.lifecycle.name)

        # Allocate every routed case place before the decision's arcs so the
        # decision's output arcs land in declared case order.
        case_places: dict[type, str | None] = {}
        for outcome_type, target in choose.cases:
            if isinstance(target, Drop):
                self._register_source(f"{decide.id}.{_snake(outcome_type.__name__)}.drop", target.source)
                case_places[outcome_type] = None
            elif isinstance(target, Terminal):
                target_owner = self._register_source(target.id, target.source)
                case_places[outcome_type] = self.place(
                    f"terminal.{target.id}", outcome_type, target_owner, "terminal outcome"
                )
            elif isinstance(target, (Effect, LowLevel)):
                target_owner = self._register_source(target.id, target.source)
                base = _command_base(outcome_type)
                case_places[outcome_type] = self.place(f"commands.{base}", outcome_type, target_owner, "typed command")
            else:  # pragma: no cover - the algebra's choose() refuses other targets
                raise CompositionError(f"unsupported choose target {target!r}")

        decide_path = self.transition(
            f"{self.flow.name}.{decide.id}.fire",
            petri_handler(_decision_bridge(decide, state_place, case_places)),
            decide_owner,
            "durable decision",
        )
        self.connect(state_place, decide_path)
        self.connect(event_place, decide_path)
        self.connect(decide_path, state_place)
        for outcome_type, _ in choose.cases:
            target_place = case_places[outcome_type]
            if target_place is not None:
                self.connect(decide_path, target_place)

        # Role-ordered target lowering: simple effects first, then descent
        # fragments — the fixed transition order of the experiment plan.
        for outcome_type, target in choose.cases:
            if isinstance(target, Effect):
                self._lower_effect(outcome_type, target, case_places[outcome_type])
        for outcome_type, target in choose.cases:
            if isinstance(target, LowLevel):
                self._lower_fragment(outcome_type, target, case_places[outcome_type])

    def _lower_effect(self, outcome_type: type, target: Effect, command_place: str | None) -> None:
        assert command_place is not None
        owner = self._source_id(target.id)
        base = _command_base(outcome_type)
        fact_place = self.place(
            f"facts.{_snake(target.result_type.__name__)}",
            target.result_type,
            owner,
            "effect result fact",
        )
        fire_path = self.activity_transition(f"effects.{base}.fire", target.definition, owner, "typed Activity effect")
        self.connect(command_place, fire_path)
        self.connect(fire_path, fact_place)
        self._register_fact(target.result_type, fact_place)

    def _lower_fragment(self, outcome_type: type, target: LowLevel, command_place: str | None) -> None:
        assert command_place is not None
        owner = self._source_id(target.id)
        base = _command_base(outcome_type)
        fact_place = self.place(
            f"facts.{_snake(target.returns.__name__)}",
            target.returns,
            owner,
            "accepted effect fact",
        )
        context = FragmentContext(self, target, f"effects.{base}", command_place, outcome_type, fact_place, owner)
        ports = target.fragment(context)
        if not isinstance(ports, FragmentPorts):
            raise CompositionError(f"low_level [{target.id}] must return FragmentPorts, got {ports!r}")
        if ports.input != command_place or ports.output != fact_place:
            raise CompositionError(
                f"low_level [{target.id}] acknowledged ports {ports}, expected "
                f"input {command_place} and output {fact_place}"
            )
        self.fragments.append((target, context, ports))
        self._register_fact(target.returns, fact_place)

    def _register_fact(self, fact_type: type, place: str) -> None:
        existing = self.fact_places.setdefault(fact_type, place)
        if existing != place:  # pragma: no cover - distinct colors get distinct fact paths
            raise CompositionError(f"fact color {fact_type.__name__} produced at {existing} and {place}")

    def _lower_fact_fold(self, trigger: type, fold: Fold, to: To) -> None:
        fold_owner = self._register_source(fold.id, fold.source)
        terminal_owner = self._register_source(to.target.id, to.target.source)
        state_place = self._state_place_for(fold.state_type, f"fold [{fold.id}]")
        fact_place = self.fact_places.get(trigger)
        if fact_place is None:
            raise CompositionError(f"on({trigger.__name__}) has no producer: no authored effect or fragment returns it")
        terminal_place = self.place(f"terminal.{to.target.id}", fold.output_type, terminal_owner, "terminal outcome")
        fold_path = self.transition(
            f"{self.flow.name}.{fold.id}.fire",
            petri_handler(_fold_bridge(fold, state_place, terminal_place)),
            fold_owner,
            "durable state fold",
        )
        self.connect(state_place, fold_path)
        self.connect(fact_place, fold_path)
        self.connect(fold_path, state_place)
        self.connect(fold_path, terminal_place)

    # -- post-build verification ----------------------------------------------

    def _verify_fragments(self, built: BuiltNet) -> None:
        for descent, context, ports in self.fragments:
            for kind, path in context.declared:
                if not path.startswith(f"{context.scope}."):
                    raise CompositionError(
                        f"low_level [{descent.id}] declared {path} outside its scope {context.scope}"
                    )
                collection = built.net.places if kind == "place" else built.net.transitions
                if NetPath(path) not in collection:
                    raise CompositionError(f"low_level [{descent.id}] node {path} did not survive the build")
                if path not in self.ownership:
                    raise CompositionError(f"low_level [{descent.id}] node {path} has no source ownership")
            bound = [path for path, _ in self.activity_bindings if path.startswith(f"{context.scope}.")]
            for path in bound:
                if built.net.handler_uri(NetPath(path)) is None:
                    raise CompositionError(f"low_level [{descent.id}] Activity {path} is not URI-bound")
            for port in (ports.input, ports.output):
                if NetPath(port) not in built.net.places:
                    raise CompositionError(f"low_level [{descent.id}] port {port} is not a canonical place")


def compile_flow(flow: Machine) -> CompiledFlow:
    """Compile one authored machine into an immutable canonical assembly."""
    return _Lowering(flow).compile()
