"""Petri-aware bindings between firing values and activities."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import KW_ONLY, dataclass, field, is_dataclass
from inspect import Parameter, Signature, signature
from typing import Protocol, get_type_hints, runtime_checkable

from petrus.motus.activity import (
    ActivityDefinition,
    ActivityInvocation,
    DataclassPayloadConverter,
    PayloadConverter,
)
from petrus.impetus.petrinet import Arc, ArcMode, Binding, Guard, Net, NetPath, Token, route


@dataclass(frozen=True)
class HandlerResult:
    """Output tokens and delivery-registration effects returned by a handler."""

    tokens: Mapping[NetPath | str, Sequence[Token]] = field(default_factory=dict)
    _: KW_ONLY
    # Registration values are history-owned. Keeping these containers opaque
    # preserves Binding's dependency direction while the Instance writer
    # validates and records the concrete values exactly as before.
    opens: tuple[object, ...] = ()
    closes: tuple[object, ...] = ()


type Handler = Callable[[Binding, tuple[Arc, ...]], Mapping[NetPath | str, Sequence[Token]] | HandlerResult]


@runtime_checkable
class ActivityHandler(Protocol):
    """The Petri-aware prepare/project bridge around one activity invocation."""

    def prepare(self, binding: Binding) -> ActivityInvocation: ...

    def project(self, binding: Binding, result: object) -> Mapping[NetPath | str, Sequence[Token]] | HandlerResult: ...


@dataclass(frozen=True)
class _DerivedInput:
    name: str
    arc: Arc
    selection: int


@dataclass(frozen=True)
class DerivedActivityHandler:
    """Derive an ordinary Activity prepare/project bridge from typed arcs and a typed Activity."""

    net: Net = field(repr=False)
    transition: NetPath
    activity: ActivityDefinition
    _inputs: tuple[_DerivedInput, ...] = field(init=False, repr=False)
    _outputs: tuple[Arc, ...] = field(init=False, repr=False)
    _result_color: str = field(init=False, repr=False)

    def __post_init__(self) -> None:
        transition = NetPath(self.transition)
        if transition not in self.net.transitions:
            raise ValueError(f"cannot derive Activity handler for {transition}: the transition is not in this net")
        inputs: list[_DerivedInput] = []
        arcs = tuple(arc for arc in self.net.inputs(transition) if arc.mode is not ArcMode.INHIBIT)
        for name, annotation in self.activity.parameters.items():
            color = _annotation_name(annotation, f"Activity parameter {name!r}")
            matches = tuple(arc for arc in arcs if arc.color == color)
            if len(matches) != 1:
                raise ValueError(
                    f"cannot derive Activity handler for {transition}: parameter {name!r} ({color}) requires exactly "
                    f"one matching input arc, found {len(matches)}"
                )
            [arc] = matches
            prior = next((item for item in inputs if item.arc is arc), None)
            if prior is not None:
                raise ValueError(
                    f"cannot derive Activity handler for {transition}: parameter {name!r} ({color}) matches input "
                    f"arc {arc.source} -> {arc.target} already used by parameter {prior.name!r}"
                )
            if arc.weight != 1:
                raise ValueError(
                    f"cannot derive Activity handler for {transition}: parameter {name!r} ({color}) matches "
                    f"weight-{arc.weight} arc {arc.source} -> {arc.target}; collection parameters are not supported"
                )
            arc_index = next(index for index, candidate in enumerate(arcs) if candidate is arc)
            selection = sum(candidate.mode is arc.mode for candidate in arcs[:arc_index])
            inputs.append(_DerivedInput(name, arc, selection))
        matched_inputs = {item.arc for item in inputs}
        for arc in arcs:
            if arc.color is not None and arc not in matched_inputs:
                raise ValueError(
                    f"cannot derive Activity handler for {transition}: typed input arc {arc.source} -> {arc.target} "
                    f"({arc.color}) matches no Activity parameter"
                )
        result_color = _annotation_name(self.activity.result, "Activity return")
        output_arcs = self.net.outputs(transition)
        outputs = tuple(arc for arc in output_arcs if arc.color == result_color)
        if not outputs:
            raise ValueError(
                f"cannot derive Activity handler for {transition}: return type {result_color} matches no output arc"
            )
        unmatched = next((arc for arc in output_arcs if arc.color != result_color), None)
        if unmatched is not None:
            color = unmatched.color if unmatched.color is not None else "untyped"
            raise ValueError(
                f"cannot derive Activity handler for {transition}: output arc {unmatched.source} -> "
                f"{unmatched.target} ({color}) matches no Activity return"
            )
        object.__setattr__(self, "transition", transition)
        object.__setattr__(self, "_inputs", tuple(inputs))
        object.__setattr__(self, "_outputs", outputs)
        object.__setattr__(self, "_result_color", result_color)

    def prepare(self, binding: Binding) -> ActivityInvocation:
        if binding.transition != self.transition:
            raise ValueError(
                f"cannot prepare Activity {self.activity.declaration.name!r} for {binding.transition}: "
                f"this derived handler belongs to {self.transition}"
            )
        payload: dict[str, object] = {}
        for expected in self._inputs:
            selections = binding.read if expected.arc.mode is ArcMode.READ else binding.consumed
            selected = selections[expected.selection] if expected.selection < len(selections) else None
            if selected is None or selected[0] != expected.arc.source or len(selected[1]) != 1:
                count = len(selected[1]) if selected is not None and selected[0] == expected.arc.source else 0
                raise ValueError(
                    f"cannot prepare Activity {self.activity.declaration.name!r} for {binding.transition}: parameter "
                    f"{expected.name!r} ({expected.arc.color}) requires exactly one selected token from "
                    f"{expected.arc.source}, found {count}"
                )
            payload[expected.name] = selected[1][0].data
        return ActivityInvocation(self.activity.declaration.name, input=payload)

    def project(self, binding: Binding, result: object) -> Mapping[NetPath, Sequence[Token]]:
        del binding
        token = Token(self._result_color, result)
        routed: dict[NetPath, tuple[Token, ...]] = {}
        for arc in self._outputs:
            routed[arc.target] = routed.get(arc.target, ()) + (token,)
        return routed


def _annotation_name(annotation: object, subject: str) -> str:
    name = getattr(annotation, "__name__", None)
    if not isinstance(name, str) or not name:
        raise ValueError(f"{subject} annotation {annotation!r} has no nominal type name for arc-color matching")
    return name


@dataclass(frozen=True)
class _TypedInput:
    name: str
    annotation: object
    arc: Arc
    selection: int


@dataclass(frozen=True)
class _TypedInputPlan:
    transition: NetPath
    inputs: tuple[_TypedInput, ...]
    converter: PayloadConverter

    def arguments(self, binding: Binding, subject: str) -> dict[str, object]:
        if binding.transition != self.transition:
            raise ValueError(f"{subject} for {self.transition} cannot handle binding for {binding.transition}")
        arguments = {}
        for expected in self.inputs:
            selections = binding.read if expected.arc.mode is ArcMode.READ else binding.consumed
            selected = selections[expected.selection] if expected.selection < len(selections) else None
            if selected is None or selected[0] != expected.arc.source or len(selected[1]) != 1:
                count = len(selected[1]) if selected is not None and selected[0] == expected.arc.source else 0
                raise ValueError(
                    f"{subject} for {self.transition} parameter {expected.name!r} requires exactly one "
                    f"selected token from {expected.arc.source}, found {count}"
                )
            [token] = selected[1]
            if token.color != expected.arc.color:
                raise ValueError(
                    f"{subject} for {self.transition} parameter {expected.name!r} requires color "
                    f"{expected.arc.color}, got {token.color}"
                )
            arguments[expected.name] = self.converter.decode(token.data, expected.annotation)
        return arguments


@dataclass(frozen=True)
class _DerivedTypedTransform:
    plan: _TypedInputPlan
    function: Callable[..., object]
    outputs: tuple[Arc, ...]
    result: object

    def __call__(self, binding: Binding, outputs: tuple[Arc, ...]):
        if outputs != self.outputs:
            raise ValueError(
                f"typed transform for {self.plan.transition} received output arcs that differ from derivation"
            )
        encoded = self.plan.converter.encode(
            self.function(**self.plan.arguments(binding, "typed transform")),
            self.result,
        )
        routed: dict[NetPath, tuple[Token, ...]] = {}
        for arc in self.outputs:
            routed[arc.target] = routed.get(arc.target, ()) + (Token(arc.color, encoded),)
        return routed


@dataclass(frozen=True)
class _DerivedTypedGuard:
    plan: _TypedInputPlan
    function: Callable[..., object]

    def __call__(self, binding: Binding) -> bool:
        result = self.function(**self.plan.arguments(binding, "typed guard"))
        if type(result) is not bool:
            raise ValueError(f"typed guard for {self.plan.transition} must return bool, got {type(result).__name__}")
        return result


def _dataclass_color(annotation: object, subject: str) -> str:
    if not isinstance(annotation, type) or not is_dataclass(annotation):
        raise ValueError(f"{subject} annotation {annotation!r} must be a concrete dataclass type")
    return _annotation_name(annotation, subject)


def _typed_signature(
    function: Callable[..., object],
    subject: str,
    transition: NetPath,
) -> tuple[Signature, dict[str, object]]:
    call = signature(function)
    try:
        hints = get_type_hints(function)
    except NameError as error:
        raise TypeError(f"cannot derive {subject} for {transition}: typed signature cannot resolve: {error}") from None
    return call, hints


def _typed_input_arcs(net: Net, transition: NetPath, subject: str) -> tuple[Arc, ...]:
    arcs = tuple(arc for arc in net.inputs(transition) if arc.mode is not ArcMode.INHIBIT)
    for arc in arcs:
        if arc.color is None:
            raise ValueError(f"cannot derive {subject} for {transition}: input arc {arc.source} is untyped")
        if arc.weight != 1:
            raise ValueError(
                f"cannot derive {subject} for {transition}: input arc {arc.source} has weight {arc.weight}; "
                f"collection parameters are not supported"
            )
    return arcs


def _match_typed_inputs(
    call: Signature,
    hints: Mapping[str, object],
    arcs: tuple[Arc, ...],
    subject: str,
    transition: NetPath,
) -> tuple[_TypedInput, ...]:
    inputs = []
    used: set[int] = set()
    for parameter in call.parameters.values():
        if parameter.kind not in (Parameter.POSITIONAL_OR_KEYWORD, Parameter.KEYWORD_ONLY):
            raise TypeError(f"cannot derive {subject} for {transition}: parameter {parameter.name!r} must be named")
        if parameter.name not in hints:
            raise TypeError(f"cannot derive {subject} for {transition}: parameter {parameter.name!r} requires a type")
        annotation = hints[parameter.name]
        color = _dataclass_color(annotation, f"parameter {parameter.name!r}")
        matches = [index for index, arc in enumerate(arcs) if arc.color == color]
        if len(matches) != 1:
            raise ValueError(
                f"cannot derive {subject} for {transition}: parameter {parameter.name!r} ({color}) requires exactly "
                f"one matching input arc, found {len(matches)}"
            )
        [index] = matches
        arc = arcs[index]
        if index in used:
            raise ValueError(f"cannot derive {subject} for {transition}: input arc {arc.source} is reused")
        selection = sum(candidate.mode is arc.mode for candidate in arcs[:index])
        inputs.append(_TypedInput(parameter.name, annotation, arc, selection))
        used.add(index)
    for index, arc in enumerate(arcs):
        if index not in used:
            raise ValueError(f"cannot derive {subject} for {transition}: input arc {arc.source} matches no parameter")
    return tuple(inputs)


def _derive_typed_inputs(
    net: Net,
    transition: NetPath | str,
    function: Callable[..., object],
    subject: str,
    converter: PayloadConverter,
) -> tuple[_TypedInputPlan, dict[str, object]]:
    transition = NetPath(transition)
    if transition not in net.transitions:
        raise ValueError(f"cannot derive {subject} for {transition}: transition is not in this net")
    if net.is_source(transition):
        raise ValueError(f"cannot derive {subject} for {transition}: source transitions are not supported")
    call, hints = _typed_signature(function, subject, transition)
    arcs = _typed_input_arcs(net, transition, subject)
    inputs = _match_typed_inputs(call, hints, arcs, subject, transition)
    return _TypedInputPlan(transition, inputs, converter), hints


def derive_typed_transform(
    net: Net,
    transition: NetPath | str,
    function: Callable[..., object],
    *,
    converter: PayloadConverter = DataclassPayloadConverter(),
) -> Handler:
    """Adapt one dataclass transformation over uniquely colored weight-one arcs."""
    plan, hints = _derive_typed_inputs(net, transition, function, "typed transform", converter)
    if "return" not in hints:
        raise TypeError(f"cannot derive typed transform for {plan.transition}: function requires a return type")
    result = hints["return"]
    color = _dataclass_color(result, "return")
    outputs = net.outputs(plan.transition)
    if not outputs:
        raise ValueError(f"cannot derive typed transform for {plan.transition}: transition has no output arcs")
    for arc in outputs:
        if arc.color != color:
            actual = "untyped" if arc.color is None else arc.color
            raise ValueError(
                f"cannot derive typed transform for {plan.transition}: output arc {arc.target} has color "
                f"{actual}, expected {color}"
            )
        if arc.weight != 1:
            raise ValueError(
                f"cannot derive typed transform for {plan.transition}: output arc {arc.target} has weight {arc.weight}"
            )
    return _DerivedTypedTransform(plan, function, outputs, result)


def derive_typed_guard(
    net: Net,
    transition: NetPath | str,
    function: Callable[..., object],
    *,
    converter: PayloadConverter = DataclassPayloadConverter(),
) -> Guard:
    """Adapt one dataclass predicate over uniquely colored weight-one arcs."""
    plan, hints = _derive_typed_inputs(net, transition, function, "typed guard", converter)
    result = hints.get("return")
    if result is not bool:
        actual = "missing" if result is None else repr(result)
        raise TypeError(
            f"cannot derive typed guard for {plan.transition}: return annotation must be bool, got {actual}"
        )
    return _DerivedTypedGuard(plan, function)


def passthrough(binding: Binding, outputs: tuple[Arc, ...]) -> dict[NetPath, tuple[Token, ...]]:
    """Forward each consumed or delivered token through every admitting output arc."""
    return route(binding.tokens, outputs)


__all__ = [
    "ActivityHandler",
    "DerivedActivityHandler",
    "Handler",
    "HandlerResult",
    "derive_typed_guard",
    "derive_typed_transform",
    "passthrough",
]
