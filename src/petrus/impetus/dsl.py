"""Python net-authoring frontend that lowers a minimal fluent specification to ``Net``."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from types import MappingProxyType
from typing import cast

from petrus.motus.activity import DataclassPayloadConverter, PayloadConverter
from petrus.impetus.binding import (
    ActivityHandler,
    Handler,
    derive_typed_guard as _derive_typed_guard,
    derive_typed_transform,
)
from petrus.impetus.petrinet.enabledness import Guard
from petrus.impetus.petrinet.schema import (
    AnonymousDeclaration,
    Arc,
    ArcMode,
    Cel,
    Color,
    CompletionDeclaration,
    Delay,
    FilterDeclaration,
    Net,
    NetPath,
    NetUri,
    Place,
    Transition,
    Until,
)

type ColorSpec = Color | type


class _HandlerFlavor(StrEnum):
    PETRI = "petri"
    DIRECT = "direct"


class _GuardFlavor(StrEnum):
    PETRI = "petri"
    TYPED = "typed"


@dataclass(frozen=True)
class HandlerSpec:
    """An explicitly flavored Python handler implementation specification."""

    flavor: _HandlerFlavor
    implementation: Callable[..., object] = field(repr=False)
    converter: PayloadConverter | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.flavor, _HandlerFlavor):
            raise TypeError(f"invalid handler specification flavor {self.flavor!r}")
        if not callable(self.implementation):
            raise TypeError(f"handler specification requires a callable, got {self.implementation!r}")


@dataclass(frozen=True)
class GuardSpec:
    """An explicitly flavored Python guard implementation specification."""

    flavor: _GuardFlavor
    implementation: Callable[..., object] = field(repr=False)
    converter: PayloadConverter | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.flavor, _GuardFlavor):
            raise TypeError(f"invalid guard specification flavor {self.flavor!r}")
        if not callable(self.implementation):
            raise TypeError(f"guard specification requires a callable, got {self.implementation!r}")


type HandlerInput = str | HandlerSpec | None
type GuardInput = str | Cel | GuardSpec | Callable[..., object]
type NormalizedGuard = str | Cel | GuardSpec


class _Unset:
    pass


_UNSET = _Unset()


def _anonymous(implementation: Callable[..., object]) -> AnonymousDeclaration:
    """Retain a callable's non-semantic display name on its anonymous declaration."""
    name = getattr(implementation, "__name__", None)
    return AnonymousDeclaration(name if isinstance(name, str) and name else None)


def petri_handler(implementation: Handler) -> HandlerSpec:
    """Bind an existing Petri-aware pure handler through the authored net."""
    if not callable(implementation):
        raise TypeError(f"petri_handler requires a callable, got {implementation!r}")
    return HandlerSpec(_HandlerFlavor.PETRI, implementation)


def direct(
    implementation=None,
    *,
    converter: PayloadConverter = DataclassPayloadConverter(),
):
    """Mark a pure typed transformation for direct local execution."""

    def declare(function) -> HandlerSpec:
        if not callable(function):
            raise TypeError(f"direct requires a callable, got {function!r}")
        return HandlerSpec(_HandlerFlavor.DIRECT, function, converter)

    return declare if implementation is None else declare(implementation)


def petri_guard(implementation: Guard) -> GuardSpec:
    """Bind an existing Petri-aware guard through the authored net."""
    if not callable(implementation):
        raise TypeError(f"petri_guard requires a callable, got {implementation!r}")
    return GuardSpec(_GuardFlavor.PETRI, implementation)


@dataclass(frozen=True)
class ArcSpec:
    """Authored arc inscription placed between node specifications with ``>>``."""

    mode: ArcMode = ArcMode.CONSUME
    weight: int = 1
    color: ColorSpec | None = None
    filter: FilterDeclaration | None = None

    def __rrshift__(self, sources):
        source_nodes = _nodes(sources)
        spec = source_nodes[0]._spec
        if any(node._spec is not spec for node in source_nodes):
            raise ValueError("an arc cannot connect nodes from different net specifications")
        return _PendingConnection(spec, source_nodes, self)


class _ArcFactory:
    """Create explicit consume, read, and inhibit inscriptions."""

    def __call__(
        self,
        *,
        weight: int = 1,
        color: ColorSpec | None = None,
        filter: FilterDeclaration | None = None,
    ) -> ArcSpec:
        return ArcSpec(ArcMode.CONSUME, weight, color, filter)

    def read(
        self,
        *,
        weight: int = 1,
        color: ColorSpec | None = None,
        filter: FilterDeclaration | None = None,
    ) -> ArcSpec:
        return ArcSpec(ArcMode.READ, weight, color, filter)

    def inhibit(
        self,
        *,
        weight: int = 1,
        color: ColorSpec | None = None,
        filter: FilterDeclaration | None = None,
    ) -> ArcSpec:
        return ArcSpec(ArcMode.INHIBIT, weight, color, filter)


arc = _ArcFactory()


@dataclass(frozen=True)
class NodeSpec:
    """One net-specification-owned authored node identity."""

    _spec: NetSpec = field(repr=False)
    _path: NetPath

    def __abs__(self) -> NetPath:
        return self._path

    def __rshift__(self, target):
        if isinstance(target, ArcSpec):
            return _PendingConnection(self._spec, (self,), target)
        self._spec._connect((self,), target, ArcSpec())
        return target

    def __rrshift__(self, sources):
        self._spec._connect(_nodes(sources), self, ArcSpec())
        return self


@dataclass(frozen=True)
class PlaceSpec(NodeSpec):
    """One authored place; its optional color is configured by its builder."""

    def __call__(self, color: ColorSpec | None) -> PlaceSpec:
        return self._spec.place(self, color=color)

    def override(self, *, color: ColorSpec | None) -> PlaceSpec:
        return self._spec._override_place(self, color=color)

    @property
    def color(self) -> ColorSpec | None:
        _, configured, color = self._spec._lookup_place(self._path)
        return color if configured else None


@dataclass(frozen=True)
class TransitionSpec(NodeSpec):
    """One authored transition; behavior declarations are configured by its builder."""

    def __call__(
        self,
        *,
        handler: HandlerInput = None,
        guards: GuardInput | tuple[GuardInput, ...] = (),
        timers: tuple[Delay | Until, ...] = (),
    ) -> TransitionSpec:
        return self._spec.transition(self, handler=handler, guards=guards, timers=timers)

    def override(
        self,
        *,
        handler: HandlerInput | _Unset = _UNSET,
        guards: GuardInput | tuple[GuardInput, ...] | _Unset = _UNSET,
        timers: tuple[Delay | Until, ...] | _Unset = _UNSET,
    ) -> TransitionSpec:
        return self._spec._override_transition(self, handler=handler, guards=guards, timers=timers)


@dataclass(frozen=True)
class ConnectionSpec:
    """One authored source-target connection and its arc inscription."""

    source: NodeSpec
    target: NodeSpec
    arc: ArcSpec


@dataclass(frozen=True)
class _TransitionSpecValue:
    handler: HandlerInput = None
    guards: tuple[NormalizedGuard, ...] = ()
    timers: tuple[Delay | Until, ...] = ()


@dataclass(frozen=True)
class _TransitionOverride:
    handler: HandlerInput | _Unset = _UNSET
    guards: tuple[NormalizedGuard, ...] | _Unset = _UNSET
    timers: tuple[Delay | Until, ...] | _Unset = _UNSET


@dataclass
class _StampedSpec:
    path: NetPath
    source: NetSpec


@dataclass(frozen=True)
class BuiltNet:
    """One immutable canonical net snapshot and its Python implementations."""

    net: Net
    handlers: Mapping[NetUri, Handler | ActivityHandler] = field(default_factory=dict)
    guards: Mapping[NetUri, Guard] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "handlers", MappingProxyType(dict(self.handlers)))
        object.__setattr__(self, "guards", MappingProxyType(dict(self.guards)))


class _PendingConnection:
    def __init__(self, spec: NetSpec, sources: tuple[NodeSpec, ...], inscription: ArcSpec) -> None:
        self._spec = spec
        self._sources = sources
        self._inscription = inscription

    def __rshift__(self, targets):
        self._spec._connect(self._sources, targets, self._inscription)
        return targets


class _NodeProxy[T: NodeSpec]:
    def __init__(self, spec: NetSpec, prefix: tuple[str, ...], kind: type[T]) -> None:
        self._spec = spec
        self._prefix = prefix
        self._kind = kind

    def __getattr__(self, name: str) -> T:
        if name.startswith("_"):
            raise AttributeError(name)
        return self._spec._node(self._prefix + (name,), self._kind)


class ScopeSpec:
    """A path-local authoring view that may receive one reusable net specification."""

    def __init__(self, spec: NetSpec, prefix: tuple[str, ...]) -> None:
        self._spec = spec
        self._prefix = prefix

    @property
    def p(self) -> _NodeProxy[PlaceSpec]:
        return _NodeProxy(self._spec, self._prefix, PlaceSpec)

    @property
    def t(self) -> _NodeProxy[TransitionSpec]:
        return _NodeProxy(self._spec, self._prefix, TransitionSpec)

    @property
    def s(self) -> ScopeSpec:
        return self

    def __getattr__(self, name: str) -> ScopeSpec:
        if name.startswith("_"):
            raise AttributeError(name)
        return ScopeSpec(self._spec, self._prefix + (name,))

    def __getitem__(self, name: str) -> ScopeSpec:
        if not isinstance(name, str):
            raise TypeError(f"scope segment must be a string, got {name!r}")
        if not name or NetPath.SEP in name:
            raise ValueError(f"scope segment must be one non-empty path segment, got {name!r}")
        return ScopeSpec(self._spec, self._prefix + (name,))

    def stamp(self, source: NetSpec) -> ScopeSpec:
        """Stamp one reusable definition at this destination scope when built."""
        return self._spec._stamp(self._prefix, source)


class NetSpec:
    """One authored net definition, reusable as a root net or a stamped subnet."""

    def __init__(self, name: str | None = None, *, completion: CompletionDeclaration | None = None) -> None:
        if name is not None and (not isinstance(name, str) or not name):
            raise ValueError(f"net specification name must be a non-empty string or None, got {name!r}")
        self.name = name
        self.completion = completion
        self._place_handles: dict[NetPath, PlaceSpec] = {}
        self._transition_handles: dict[NetPath, TransitionSpec] = {}
        self._places: dict[NetPath, PlaceSpec] = {}
        self._transitions: dict[NetPath, TransitionSpec] = {}
        self._place_colors: dict[NetPath, ColorSpec | None] = {}
        self._transition_values: dict[NetPath, _TransitionSpecValue] = {}
        self._place_overrides: dict[NetPath, ColorSpec | None] = {}
        self._transition_overrides: dict[NetPath, _TransitionOverride] = {}
        self._connections: list[ConnectionSpec] = []
        self._stamps: dict[NetPath, _StampedSpec] = {}
        self._events: list[NodeSpec | ConnectionSpec | _StampedSpec] = []

    @property
    def p(self) -> _NodeProxy[PlaceSpec]:
        return _NodeProxy(self, (), PlaceSpec)

    @property
    def t(self) -> _NodeProxy[TransitionSpec]:
        return _NodeProxy(self, (), TransitionSpec)

    @property
    def s(self) -> ScopeSpec:
        return ScopeSpec(self, ())

    @property
    def connections(self) -> tuple[ConnectionSpec, ...]:
        return tuple(self._connections)

    def copy(self) -> NetSpec:
        """Snapshot this composed authored definition as an independent flat specification."""
        return NetBuilder(self)._effective_spec()

    def build(self) -> BuiltNet:
        """Compose and lower this specification through the canonical net boundary."""
        return NetBuilder(self).build()

    def place(self, node: PlaceSpec, *, color: ColorSpec | None = None) -> PlaceSpec:
        self._require_node(node, PlaceSpec, "place")
        normalized = _color_name(color)
        inherited, configured, existing = self._lookup_place(node._path)
        if inherited:
            if configured and existing != normalized:
                raise ValueError(f"place {node._path} is already configured with color {existing!r}")
            self._place_overrides[node._path] = normalized
            return node
        existing = self._place_colors.get(node._path, normalized)
        if node._path in self._place_colors and existing != normalized:
            raise ValueError(f"place {node._path} is already configured with color {existing!r}")
        self._place_colors[node._path] = normalized
        return node

    def _override_place(self, node: PlaceSpec, *, color: ColorSpec | None) -> PlaceSpec:
        self._require_node(node, PlaceSpec, "place")
        inherited, configured, _ = self._lookup_place(node._path)
        if not configured:
            raise ValueError(f"place {node._path} has no explicit or inherited configuration to override")
        normalized = _color_name(color)
        if inherited:
            self._place_overrides[node._path] = normalized
        else:
            self._place_colors[node._path] = normalized
        return node

    def transition(
        self,
        node: TransitionSpec,
        *,
        handler: HandlerInput = None,
        guards: GuardInput | tuple[GuardInput, ...] = (),
        timers: tuple[Delay | Until, ...] = (),
    ) -> TransitionSpec:
        value = self._transition_value(node, handler, guards, timers)
        inherited, configured, existing = self._lookup_transition(node._path)
        if inherited:
            if configured and existing != value:
                raise ValueError(
                    f"transition {node._path} is already configured; use transition.override(...) to change it"
                )
            self._transition_overrides[node._path] = _TransitionOverride(value.handler, value.guards, value.timers)
            return node
        existing = self._transition_values.get(node._path)
        if existing is not None and existing != value:
            raise ValueError(
                f"transition {node._path} is already configured; use transition.override(...) to change it"
            )
        self._transition_values[node._path] = value
        return node

    def _override_transition(
        self,
        node: TransitionSpec,
        *,
        handler: HandlerInput | _Unset,
        guards: GuardInput | tuple[GuardInput, ...] | _Unset,
        timers: tuple[Delay | Until, ...] | _Unset,
    ) -> TransitionSpec:
        self._require_node(node, TransitionSpec, "transition")
        inherited, configured, _ = self._lookup_transition(node._path)
        if not configured:
            raise ValueError(f"transition {node._path} has no explicit or inherited configuration to override")
        if isinstance(handler, _Unset) and isinstance(guards, _Unset) and isinstance(timers, _Unset):
            raise TypeError("transition override requires at least one of handler, guards, or timers")

        changes: dict[str, object] = {}
        if not isinstance(handler, _Unset):
            changes["handler"] = self._normalize_handler(handler)
        if not isinstance(guards, _Unset):
            changes["guards"] = _normalize_guards(guards)
        if not isinstance(timers, _Unset):
            changes["timers"] = timers

        if inherited:
            current = self._transition_overrides.get(node._path, _TransitionOverride())
            self._transition_overrides[node._path] = replace(current, **changes)
        else:
            self._transition_values[node._path] = replace(self._transition_values[node._path], **changes)
        return node

    def _canonical_net(self) -> Net:
        places = [Place(path, _color_name(self._place_colors.get(path))) for path in self._places]
        transitions = []
        for path in self._transitions:
            value = self._transition_values.get(path, _TransitionSpecValue())
            handler = (
                _anonymous(value.handler.implementation) if isinstance(value.handler, HandlerSpec) else value.handler
            )
            guards = tuple(
                _anonymous(guard.implementation) if isinstance(guard, GuardSpec) else guard for guard in value.guards
            )
            transitions.append(Transition(path, handler, guards, value.timers))
        arcs = [
            Arc(
                connection.source._path,
                connection.target._path,
                connection.arc.mode,
                connection.arc.weight,
                _color_name(connection.arc.color),
                connection.arc.filter,
            )
            for connection in self._connections
        ]
        return Net(places, transitions, arcs, completion=self.completion, name=self.name)

    def _lower_handlers(self, net: Net) -> dict[NetUri, Handler | ActivityHandler]:
        implementations: dict[NetUri, Handler | ActivityHandler] = {}
        for path, value in self._transition_values.items():
            if not isinstance(value.handler, HandlerSpec):
                continue
            uri = net.handler_uri(path)
            assert uri is not None
            if value.handler.flavor is _HandlerFlavor.DIRECT:
                converter = (
                    value.handler.converter if value.handler.converter is not None else DataclassPayloadConverter()
                )
                implementations[uri] = derive_typed_transform(
                    net,
                    path,
                    value.handler.implementation,
                    converter=converter,
                )
            else:
                implementations[uri] = cast(Handler, value.handler.implementation)
        return implementations

    def _lower_guards(self, net: Net) -> dict[NetUri, Guard]:
        implementations: dict[NetUri, Guard] = {}
        for path, value in self._transition_values.items():
            for guard, uri in zip(value.guards, net.guard_uris(path)):
                if not isinstance(guard, GuardSpec):
                    continue
                if guard.flavor is _GuardFlavor.TYPED:
                    converter = guard.converter if guard.converter is not None else DataclassPayloadConverter()
                    implementations[uri] = _derive_typed_guard(
                        net,
                        path,
                        guard.implementation,
                        converter=converter,
                    )
                else:
                    implementations[uri] = cast(Guard, guard.implementation)
        return implementations

    def _node[T: NodeSpec](self, segments: tuple[str, ...], kind: type[T]) -> T:
        path = NetPath(".".join(segments))
        if kind is PlaceSpec:
            node = self._place_handles.setdefault(path, PlaceSpec(self, path))
            if self._stamp_for(path) is None and path not in self._places:
                self._places[path] = node
                self._events.append(node)
            return cast(T, node)
        if kind is TransitionSpec:
            node = self._transition_handles.setdefault(path, TransitionSpec(self, path))
            if self._stamp_for(path) is None and path not in self._transitions:
                self._transitions[path] = node
                self._events.append(node)
            return cast(T, node)
        raise TypeError(f"unsupported node specification type {kind!r}")

    def _require_node(self, node: NodeSpec, kind: type[NodeSpec], subject: str) -> None:
        if not isinstance(node, kind) or node._spec is not self:
            raise TypeError(
                f"{subject} configuration requires a {kind.__name__} from this net specification, got {node!r}"
            )

    def _transition_value(
        self,
        node: TransitionSpec,
        handler: HandlerInput,
        guards: GuardInput | tuple[GuardInput, ...],
        timers: tuple[Delay | Until, ...],
    ) -> _TransitionSpecValue:
        self._require_node(node, TransitionSpec, "transition")
        return _TransitionSpecValue(self._normalize_handler(handler), _normalize_guards(guards), timers)

    @staticmethod
    def _normalize_handler(handler: HandlerInput) -> HandlerInput:
        if isinstance(handler, NodeSpec):
            raise TypeError("a node specification cannot be used as a handler")
        if callable(handler) and not isinstance(handler, HandlerSpec):
            raise TypeError("handler callables require direct(...) or the advanced petri_handler(...)")
        return handler

    def _connect(self, sources: Iterable[NodeSpec], targets, inscription: ArcSpec) -> None:
        source_nodes = _nodes(tuple(sources))
        target_nodes = _nodes(targets)
        if any(node._spec is not self for node in (*source_nodes, *target_nodes)):
            raise ValueError("an arc cannot connect nodes from different net specifications")
        additions = [ConnectionSpec(source, target, inscription) for source in source_nodes for target in target_nodes]
        self._connections.extend(additions)
        self._events.extend(additions)

    def _stamp(self, segments: tuple[str, ...], source: NetSpec) -> ScopeSpec:
        if not isinstance(source, NetSpec):
            raise TypeError(f"scope stamp requires a NetSpec, got {source!r}")
        if not segments:
            raise ValueError(
                f"cannot stamp {_spec_label(source)} at <root>: reusable definitions require a non-root scope"
            )
        path = NetPath(".".join(segments))
        enclosing = self._stamp_for(path)
        if enclosing is not None and enclosing.path != path:
            raise ValueError(
                f"cannot stamp {_spec_label(source)} at {path}: scope belongs to "
                f"{_spec_label(enclosing.source)} stamped at {enclosing.path}"
            )

        occupied_places = [candidate for candidate in self._places if _within(candidate, path)]
        occupied_transitions = [candidate for candidate in self._transitions if _within(candidate, path)]
        nested = [candidate for candidate in self._stamps if candidate != path and _within(candidate, path)]
        if occupied_places or occupied_transitions or nested:
            owners = (
                *(f"place {candidate}" for candidate in occupied_places),
                *(f"transition {candidate}" for candidate in occupied_transitions),
                *(f"stamp {candidate}" for candidate in nested),
            )
            raise ValueError(
                f"cannot stamp {_spec_label(source)} at {path}: destination already owns {', '.join(owners)}"
            )

        existing = self._stamps.get(path)
        if existing is None:
            stamp = _StampedSpec(path, source)
            self._stamps[path] = stamp
            self._events.append(stamp)
        else:
            existing.source = source

        self._place_overrides = {
            candidate: value for candidate, value in self._place_overrides.items() if not _within(candidate, path)
        }
        self._transition_overrides = {
            candidate: value for candidate, value in self._transition_overrides.items() if not _within(candidate, path)
        }
        return ScopeSpec(self, segments)

    def _stamp_for(self, path: NetPath) -> _StampedSpec | None:
        matches = [stamp for prefix, stamp in self._stamps.items() if _within(path, prefix)]
        if not matches:
            return None
        return max(matches, key=lambda stamp: len(stamp.path))

    def _lookup_place(self, path: NetPath) -> tuple[bool, bool, ColorSpec | None]:
        stamp = self._stamp_for(path)
        if stamp is None:
            return False, path in self._place_colors, self._place_colors.get(path)
        relative = _relative(path, stamp.path)
        exists, configured, color = stamp.source._source_place(relative)
        if not exists:
            raise ValueError(
                f"stamp of {_spec_label(stamp.source)} at {stamp.path} has no place {relative!s} requested as {path}"
            )
        if path in self._place_overrides:
            return True, True, self._place_overrides[path]
        return True, configured, color

    def _source_place(self, path: NetPath | None) -> tuple[bool, bool, ColorSpec | None]:
        if path is None:
            return False, False, None
        stamp = self._stamp_for(path)
        if stamp is None:
            return path in self._places, path in self._place_colors, self._place_colors.get(path)
        try:
            _, configured, color = self._lookup_place(path)
        except ValueError:
            return False, False, None
        return True, configured, color

    def _lookup_transition(self, path: NetPath) -> tuple[bool, bool, _TransitionSpecValue]:
        stamp = self._stamp_for(path)
        if stamp is None:
            return False, path in self._transition_values, self._transition_values.get(path, _TransitionSpecValue())
        relative = _relative(path, stamp.path)
        exists, configured, value = stamp.source._source_transition(relative)
        if not exists:
            raise ValueError(
                f"stamp of {_spec_label(stamp.source)} at {stamp.path} has no transition "
                f"{relative!s} requested as {path}"
            )
        override = self._transition_overrides.get(path)
        if override is None:
            return True, configured, value
        changes = {
            field: candidate
            for field, candidate in (
                ("handler", override.handler),
                ("guards", override.guards),
                ("timers", override.timers),
            )
            if not isinstance(candidate, _Unset)
        }
        return True, True, replace(value, **changes)

    def _source_transition(self, path: NetPath | None) -> tuple[bool, bool, _TransitionSpecValue]:
        if path is None:
            return False, False, _TransitionSpecValue()
        stamp = self._stamp_for(path)
        if stamp is None:
            return (
                path in self._transitions,
                path in self._transition_values,
                self._transition_values.get(path, _TransitionSpecValue()),
            )
        try:
            _, configured, value = self._lookup_transition(path)
        except ValueError:
            return False, False, _TransitionSpecValue()
        return True, configured, value


class NetBuilder:
    """Compose one root ``NetSpec`` and lower it through canonical ``Net`` validation."""

    def __init__(self, root: NetSpec) -> None:
        if not isinstance(root, NetSpec):
            raise TypeError(f"NetBuilder requires a root NetSpec, got {root!r}")
        self.root = root

    def build(self) -> BuiltNet:
        effective = self._effective_spec()
        net = effective._canonical_net()
        return BuiltNet(net, effective._lower_handlers(net), effective._lower_guards(net))

    def _effective_spec(self) -> NetSpec:
        effective = NetSpec(self.root.name, completion=self.root.completion)
        self._compose(self.root, effective, (), ())
        return effective

    def _compose(
        self,
        source: NetSpec,
        effective: NetSpec,
        prefix: tuple[str, ...],
        stack: tuple[tuple[NetSpec, tuple[str, ...]], ...],
    ) -> None:
        frame = (source, prefix)
        if any(candidate is source for candidate, _ in stack):
            cycle = " -> ".join(f"{_spec_label(spec)} at {_scope_label(path)}" for spec, path in (*stack, frame))
            raise ValueError(f"net specification stamp cycle: {cycle}")
        if prefix and source.completion is not None:
            raise ValueError(
                f"stamped net specification {_spec_label(source)} at {_scope_label(prefix)} "
                "cannot declare root completion"
            )
        stack = (*stack, frame)

        for event in source._events:
            self._compose_event(source, effective, prefix, stack, event)

        for path in source._place_overrides:
            _, configured, color = source._lookup_place(path)
            assert configured
            effective._place_colors[_prefixed(prefix, path)] = color
        for path in source._transition_overrides:
            _, configured, value = source._lookup_transition(path)
            assert configured
            effective._transition_values[_prefixed(prefix, path)] = value

    def _compose_event(
        self,
        source: NetSpec,
        effective: NetSpec,
        prefix: tuple[str, ...],
        stack: tuple[tuple[NetSpec, tuple[str, ...]], ...],
        event: NodeSpec | ConnectionSpec | _StampedSpec,
    ) -> None:
        if isinstance(event, PlaceSpec):
            path = _prefixed(prefix, event._path)
            effective._node(tuple(path), PlaceSpec)
            if event._path in source._place_colors:
                effective._place_colors[path] = source._place_colors[event._path]
        elif isinstance(event, TransitionSpec):
            path = _prefixed(prefix, event._path)
            effective._node(tuple(path), TransitionSpec)
            if event._path in source._transition_values:
                effective._transition_values[path] = source._transition_values[event._path]
        elif isinstance(event, ConnectionSpec):
            self._require_connection_endpoints(source, prefix, event)
            source_node = effective._node(tuple(_prefixed(prefix, event.source._path)), type(event.source))
            target_node = effective._node(tuple(_prefixed(prefix, event.target._path)), type(event.target))
            effective._connect((source_node,), target_node, event.arc)
        elif isinstance(event, _StampedSpec):
            self._compose(event.source, effective, (*prefix, *event.path), stack)
        else:  # pragma: no cover - the closed authored-event union is internal
            raise TypeError(f"unsupported authored event {event!r}")

    @staticmethod
    def _require_connection_endpoints(
        source: NetSpec,
        prefix: tuple[str, ...],
        connection: ConnectionSpec,
    ) -> None:
        for node in (connection.source, connection.target):
            if isinstance(node, PlaceSpec):
                exists, _, _ = source._source_place(node._path)
                kind = "place"
            else:
                exists, _, _ = source._source_transition(node._path)
                kind = "transition"
            if not exists:
                raise ValueError(
                    f"net specification {_spec_label(source)} at {_scope_label(prefix)} connection references "
                    f"missing {kind} {_prefixed(prefix, node._path)}"
                )


def _within(path: NetPath, prefix: NetPath) -> bool:
    return len(path) >= len(prefix) and tuple(path[: len(prefix)]) == tuple(prefix)


def _relative(path: NetPath, prefix: NetPath) -> NetPath | None:
    segments = tuple(path[len(prefix) :])
    return NetPath(".".join(segments)) if segments else None


def _prefixed(prefix: tuple[str, ...], path: NetPath) -> NetPath:
    return NetPath(".".join((*prefix, *path)))


def _scope_label(path: tuple[str, ...]) -> str:
    return ".".join(path) if path else "<root>"


def _spec_label(spec: NetSpec) -> str:
    return spec.name if spec.name is not None else "<anonymous>"


def _color_name(color: ColorSpec | None) -> Color | None:
    if color is None or isinstance(color, str):
        return color
    if isinstance(color, type):
        name = getattr(color, "__name__", None)
        if isinstance(name, str) and name:
            return name
    raise TypeError(f"color must be a nominal string, Python type, or None, got {color!r}")


def _nodes(value) -> tuple[NodeSpec, ...]:
    nodes = value if isinstance(value, tuple) else (value,)
    if not nodes or not all(isinstance(node, NodeSpec) for node in nodes):
        raise TypeError(f"expected a node specification or non-empty tuple of them, got {value!r}")
    return nodes


def _normalize_guards(guards: GuardInput | tuple[GuardInput, ...]) -> tuple[NormalizedGuard, ...]:
    if isinstance(guards, tuple):
        authored = cast(tuple[GuardInput, ...], guards)
    elif isinstance(guards, str | Cel | GuardSpec) or callable(guards):
        authored = (guards,)
    else:
        raise TypeError("guards must be one string, Cel, callable, explicit guard specification, or a tuple of them")
    normalized: list[NormalizedGuard] = []
    for guard in authored:
        if isinstance(guard, NodeSpec):
            raise TypeError("a node specification cannot be used as a guard")
        if callable(guard) and not isinstance(guard, GuardSpec):
            normalized.append(GuardSpec(_GuardFlavor.TYPED, guard))
        elif isinstance(guard, str | Cel | GuardSpec):
            normalized.append(guard)
        else:
            raise TypeError(f"invalid guard authoring value {guard!r}")
    return tuple(normalized)


__all__ = [
    "ArcSpec",
    "BuiltNet",
    "ConnectionSpec",
    "GuardSpec",
    "HandlerSpec",
    "NetBuilder",
    "NetSpec",
    "NodeSpec",
    "PlaceSpec",
    "ScopeSpec",
    "TransitionSpec",
    "arc",
    "direct",
    "petri_guard",
    "petri_handler",
]
