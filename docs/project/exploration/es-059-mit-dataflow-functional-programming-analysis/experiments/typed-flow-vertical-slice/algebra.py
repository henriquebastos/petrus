"""Immutable typed source values for the readiness flow.

This module owns source values only: frozen dataclasses, explicit authored
ids, and source references. It performs no motion — no History write, no
Activity execution, no Engine construction — and holds no mutable runtime
state. Composition mistakes fail here, before lowering and before any History
file exists.
"""

from __future__ import annotations

import sys
import types
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields, is_dataclass
from pathlib import Path
from typing import Union, get_args, get_origin, get_type_hints

from petrus.motus.activity import ActivityDefinition

EXPERIMENT_ROOT = Path(__file__).resolve().parent


class CompositionError(ValueError):
    """An authored composition is invalid; raised before lowering and motion."""


@dataclass(frozen=True)
class SourceRef:
    """One authored source location, experiment-relative for stable goldens."""

    file: str
    line: int
    symbol: str

    def __str__(self) -> str:
        return f"{self.file}:{self.line}"


def _normalize(filename: str) -> str:
    path = Path(filename).resolve()
    try:
        return path.relative_to(EXPERIMENT_ROOT).as_posix()
    except ValueError:
        return path.name


def _call_site(symbol: str) -> SourceRef:
    """Attribute a value-only construct to its authoring call site.

    The frame is read once at construction and only plain strings/ints are
    retained; no frame is consulted during execution or resume.
    """
    frame = sys._getframe(2)
    try:
        return SourceRef(_normalize(frame.f_code.co_filename), frame.f_lineno, symbol)
    finally:
        del frame


def _function_site(function: Callable[..., object]) -> SourceRef:
    code: types.CodeType = getattr(function, "__code__")  # noqa: B009 - Callable has no typed __code__
    return SourceRef(_normalize(code.co_filename), code.co_firstlineno, getattr(function, "__name__", "<function>"))


def _require_id(value: str, noun: str) -> str:
    if not isinstance(value, str) or not value or "." in value:
        raise CompositionError(f"{noun} id must be one non-empty dot-free segment, got {value!r}")
    return value


@dataclass(frozen=True)
class Decision[S, O]:
    """A pure decision's paired state update and single tagged outcome.

    Algebra machinery, not a durable domain color: the lowering handler
    serializes ``state`` and the selected domain outcome to separate tokens.
    """

    state: S
    outcome: O


@dataclass(frozen=True)
class Lifecycle:
    """The exact Engine lifecycle scope name used by scoped ingress."""

    name: str
    source: SourceRef


def lifecycle(name: str) -> Lifecycle:
    if not isinstance(name, str) or not name:
        raise CompositionError(f"lifecycle requires a non-empty scope name, got {name!r}")
    return Lifecycle(name, _call_site(name))


@dataclass(frozen=True)
class AwaitEvent:
    """Typed external ingress under the machine's lifecycle scope."""

    id: str
    event_type: type
    source: SourceRef


def await_event(id: str, event_type: type) -> AwaitEvent:
    _require_id(id, "await_event")
    if not isinstance(event_type, type):
        raise CompositionError(f"await_event requires a concrete event type, got {event_type!r}")
    return AwaitEvent(id, event_type, _call_site(id))


@dataclass(frozen=True)
class Project:
    """Pure typed source-event projection, fused with its source firing."""

    id: str
    function: Callable[..., object]
    event_type: type
    state_type: type
    source: SourceRef


@dataclass(frozen=True)
class Decide:
    """Pure durable update plus one tagged outcome."""

    id: str
    function: Callable[..., object]
    state_type: type
    event_type: type
    outcome_types: tuple[type, ...]
    source: SourceRef


@dataclass(frozen=True)
class Effect:
    """One typed Activity request/result boundary."""

    id: str
    definition: ActivityDefinition
    request_type: type
    result_type: type
    source: SourceRef


def require_operation_field(request_type: type, noun: str) -> None:
    """Stable operation identity is part of the request contract, checked before motion."""
    if not is_dataclass(request_type) or "operation" not in {field.name for field in fields(request_type)}:
        raise CompositionError(
            f"{noun} request type {request_type.__name__} must be a dataclass with an "
            f"'operation' field carrying the stable operation id"
        )


def effect(id: str, definition: ActivityDefinition) -> Effect:
    _require_id(id, "effect")
    if not isinstance(definition, ActivityDefinition):
        raise CompositionError(f"effect requires a typed ActivityDefinition, got {definition!r}")
    parameters = dict(definition.parameters)
    if len(parameters) != 1:
        raise CompositionError(
            f"effect {id!r} requires an Activity with exactly one typed request parameter, got {sorted(parameters)}"
        )
    [request_type] = parameters.values()
    result_type = definition.result
    if not isinstance(request_type, type) or not isinstance(result_type, type):
        raise CompositionError(f"effect {id!r} requires concrete request/result types on its Activity")
    require_operation_field(request_type, f"effect [{id}]")
    # The authoring site — the choose branch — owns the attribution, not the
    # Activity implementation's decorator line: change locality points here.
    return Effect(id, definition, request_type, result_type, _call_site(id))


@dataclass(frozen=True)
class Terminal:
    """Named observable output place; its color is the routed outcome type."""

    id: str
    source: SourceRef


def terminal(id: str) -> Terminal:
    _require_id(id, "terminal")
    return Terminal(id, _call_site(id))


@dataclass(frozen=True)
class Drop:
    """Deliberate no-output outcome; represented only in the case table."""

    source: SourceRef


def drop() -> Drop:
    return Drop(_call_site("drop"))


@dataclass(frozen=True)
class LowLevel:
    """Explicit Petri descent under one stable authored scope."""

    id: str
    fragment: Callable[..., object]
    returns: type
    source: SourceRef


def low_level(id: str, fragment: Callable[..., object], *, returns: type) -> LowLevel:
    _require_id(id, "low_level")
    if not callable(fragment):
        raise CompositionError(f"low_level {id!r} requires a fragment callback, got {fragment!r}")
    if not isinstance(returns, type):
        raise CompositionError(f"low_level {id!r} requires a concrete returns type, got {returns!r}")
    return LowLevel(id, fragment, returns, _function_site(fragment))


type Outcome = Effect | Terminal | Drop | LowLevel


@dataclass(frozen=True)
class Choose:
    """Exhaustive typed routing by outcome type; no transition of its own."""

    cases: tuple[tuple[type, Outcome], ...]
    source: SourceRef


@dataclass(frozen=True)
class Fold:
    """Pure durable update of the state baton with one typed output."""

    id: str
    function: Callable[..., object]
    state_type: type
    event_type: type
    output_type: type
    source: SourceRef


@dataclass(frozen=True)
class To:
    """Route a fold's typed output to one terminal."""

    target: Terminal


type Step = Project | Decide | Choose | Fold | To


def _typed_hints(function: Callable[..., object], noun: str) -> dict[str, object]:
    try:
        return get_type_hints(function)
    except NameError as error:
        raise CompositionError(f"{noun} cannot resolve its typed signature: {error}") from None


def _named_parameters(function: Callable[..., object], noun: str) -> tuple[tuple[str, type], ...]:
    hints = _typed_hints(function, noun)
    code: types.CodeType = getattr(function, "__code__")  # noqa: B009 - Callable has no typed __code__
    names = list(code.co_varnames[: code.co_argcount])
    parameters = []
    for name in names:
        annotation = hints.get(name)
        if not isinstance(annotation, type):
            raise CompositionError(f"{noun} parameter {name!r} requires a concrete type annotation")
        parameters.append((name, annotation))
    return tuple(parameters)


def _decision_types(function: Callable[..., object], noun: str) -> tuple[type, tuple[type, ...]]:
    hints = _typed_hints(function, noun)
    annotation = hints.get("return")
    if get_origin(annotation) is not Decision:
        raise CompositionError(f"{noun} must return Decision[State, Outcome], got {annotation!r}")
    state_type, outcome = get_args(annotation)
    if get_origin(outcome) in (Union, types.UnionType):
        outcomes = get_args(outcome)
    else:
        outcomes = (outcome,)
    if not all(isinstance(candidate, type) for candidate in (state_type, *outcomes)):
        raise CompositionError(f"{noun} Decision types must be concrete classes, got {annotation!r}")
    return state_type, tuple(outcomes)


@dataclass(frozen=True)
class Handler:
    """One authored trigger and its typed step chain."""

    trigger: AwaitEvent | type
    steps: tuple[Step, ...] = ()

    def _event_type(self) -> type:
        return self.trigger.event_type if isinstance(self.trigger, AwaitEvent) else self.trigger

    def _with(self, step: Step) -> Handler:
        return Handler(self.trigger, (*self.steps, step))

    def project(self, id: str, function: Callable[..., object]) -> Handler:
        _require_id(id, "project")
        if not isinstance(self.trigger, AwaitEvent) or self.steps:
            raise CompositionError(f"project [{id}] must directly follow an await_event trigger")
        parameters = _named_parameters(function, f"project [{id}]")
        if len(parameters) != 1:
            raise CompositionError(f"project [{id}] requires exactly one typed event parameter")
        [(_, event_type)] = parameters
        source = _function_site(function)
        if event_type is not self.trigger.event_type:
            raise CompositionError(
                f"{self.trigger.source} [{self.trigger.id}] delivers "
                f"{self.trigger.event_type.__name__}, but {source} [{id}] accepts {event_type.__name__}"
            )
        hints = _typed_hints(function, f"project [{id}]")
        state_type = hints.get("return")
        if not isinstance(state_type, type):
            raise CompositionError(f"project [{id}] requires a concrete state return type")
        return self._with(Project(id, function, event_type, state_type, source))

    def decide(self, id: str, function: Callable[..., object]) -> Handler:
        _require_id(id, "decide")
        if self.steps:
            raise CompositionError(f"decide [{id}] must directly follow its trigger in this slice")
        parameters = _named_parameters(function, f"decide [{id}]")
        if len(parameters) != 2:
            raise CompositionError(f"decide [{id}] requires exactly (state, event) typed parameters")
        (_, state_parameter), (_, event_parameter) = parameters
        source = _function_site(function)
        if event_parameter is not self._event_type():
            trigger_label = (
                f"{self.trigger.source} [{self.trigger.id}]"
                if isinstance(self.trigger, AwaitEvent)
                else f"trigger {self._event_type().__name__}"
            )
            raise CompositionError(
                f"{trigger_label} delivers {self._event_type().__name__}, but "
                f"{source} [{id}] accepts {event_parameter.__name__}"
            )
        state_type, outcome_types = _decision_types(function, f"decide [{id}]")
        if state_parameter is not state_type:
            raise CompositionError(
                f"{source} [{id}] consumes state {state_parameter.__name__} but returns "
                f"Decision state {state_type.__name__}"
            )
        return self._with(Decide(id, function, state_type, event_parameter, outcome_types, source))

    def choose(self, cases: Mapping[type, Outcome]) -> Handler:
        source = _call_site("choose")
        if not self.steps or not isinstance(self.steps[-1], Decide):
            raise CompositionError("choose must directly follow a decide step")
        decide = self.steps[-1]
        declared = decide.outcome_types
        for missing in declared:
            if missing not in cases:
                raise CompositionError(f"{decide.source} [{decide.id}] has no branch for {missing.__name__}")
        for extra in cases:
            if extra not in declared:
                raise CompositionError(
                    f"{decide.source} [{decide.id}] declares no outcome {extra.__name__} routed by this choose"
                )
        for outcome_type, target in cases.items():
            if isinstance(target, Effect) and target.request_type is not outcome_type:
                raise CompositionError(
                    f"{decide.source} [{decide.id}] produces {outcome_type.__name__}, but "
                    f"{target.source} [{target.id}] accepts {target.request_type.__name__}"
                )
        ordered = tuple((outcome_type, cases[outcome_type]) for outcome_type in declared)
        return self._with(Choose(ordered, source))

    def fold(self, id: str, function: Callable[..., object]) -> Handler:
        _require_id(id, "fold")
        if self.steps:
            raise CompositionError(f"fold [{id}] must directly follow its trigger in this slice")
        parameters = _named_parameters(function, f"fold [{id}]")
        if len(parameters) != 2:
            raise CompositionError(f"fold [{id}] requires exactly (state, event) typed parameters")
        (_, state_parameter), (_, event_parameter) = parameters
        source = _function_site(function)
        if event_parameter is not self._event_type():
            raise CompositionError(
                f"trigger delivers {self._event_type().__name__}, but {source} [{id}] "
                f"accepts {event_parameter.__name__}"
            )
        hints = _typed_hints(function, f"fold [{id}]")
        annotation = hints.get("return")
        if get_origin(annotation) is not tuple:
            raise CompositionError(f"fold [{id}] must return tuple[State, Output], got {annotation!r}")
        state_type, output_type = get_args(annotation)
        if state_parameter is not state_type:
            raise CompositionError(
                f"{source} [{id}] consumes state {state_parameter.__name__} but returns state {state_type.__name__}"
            )
        if not isinstance(output_type, type):
            raise CompositionError(f"fold [{id}] output must be a concrete class, got {output_type!r}")
        return self._with(Fold(id, function, state_type, event_parameter, output_type, source))

    def to(self, target: Terminal) -> Handler:
        if not isinstance(target, Terminal):
            raise CompositionError(f"to requires a terminal, got {target!r}")
        if not self.steps or not isinstance(self.steps[-1], Fold):
            raise CompositionError("to must directly follow a fold step")
        return self._with(To(target))


def on(trigger: AwaitEvent | type) -> Handler:
    if not isinstance(trigger, (AwaitEvent, type)):
        raise CompositionError(f"on requires an await_event ingress or a fact type, got {trigger!r}")
    return Handler(trigger)


@dataclass(frozen=True)
class Machine[S]:
    """One authored machine: name, lifecycle scope, and its handler chains."""

    name: str
    lifecycle: Lifecycle
    handlers: tuple[Handler, ...]
    source: SourceRef


def _authored_ids(flow: Machine) -> tuple[tuple[str, SourceRef], ...]:
    collected: list[tuple[str, SourceRef]] = []
    for handler in flow.handlers:
        if isinstance(handler.trigger, AwaitEvent):
            collected.append((handler.trigger.id, handler.trigger.source))
        for step in handler.steps:
            if isinstance(step, (Project, Decide, Fold)):
                collected.append((step.id, step.source))
            elif isinstance(step, Choose):
                for _, target in step.cases:
                    if isinstance(target, (Effect, Terminal, LowLevel)):
                        collected.append((target.id, target.source))
            elif isinstance(step, To):
                collected.append((step.target.id, step.target.source))
    return tuple(collected)


def _referenced_types(flow: Machine) -> tuple[type, ...]:
    collected: list[type] = []
    for handler in flow.handlers:
        trigger = handler.trigger
        collected.append(trigger.event_type if isinstance(trigger, AwaitEvent) else trigger)
        for step in handler.steps:
            if isinstance(step, Project):
                collected.extend((step.event_type, step.state_type))
            elif isinstance(step, Decide):
                collected.extend((step.state_type, step.event_type, *step.outcome_types))
            elif isinstance(step, Fold):
                collected.extend((step.state_type, step.event_type, step.output_type))
            elif isinstance(step, Choose):
                for outcome_type, target in step.cases:
                    collected.append(outcome_type)
                    if isinstance(target, Effect):
                        collected.extend((step_type for step_type in (target.request_type, target.result_type)))
                    elif isinstance(target, LowLevel):
                        collected.append(target.returns)
    return tuple(collected)


def _validate(flow: Machine) -> None:
    ids = _authored_ids(flow)
    seen: dict[str, SourceRef] = {}
    for authored_id, source in ids:
        prior = seen.get(authored_id)
        if prior is not None:
            raise CompositionError(f"duplicate authored id [{authored_id}]: declared at {prior} and again at {source}")
        seen[authored_id] = source

    names: dict[str, type] = {}
    for referenced in _referenced_types(flow):
        prior = names.setdefault(referenced.__name__, referenced)
        if prior is not referenced:
            raise CompositionError(
                f"two distinct classes share the nominal name {referenced.__name__!r}: "
                f"{prior!r} and {referenced!r}; nominal port identity requires unique names"
            )


def machine(name: str, *, lifecycle: Lifecycle, handlers: tuple[Handler, ...]) -> Machine:
    if not isinstance(name, str) or not name:
        raise CompositionError(f"machine requires a non-empty name, got {name!r}")
    if not isinstance(lifecycle, Lifecycle):
        raise CompositionError(f"machine requires a lifecycle(...), got {lifecycle!r}")
    if not handlers or not all(isinstance(handler, Handler) for handler in handlers):
        raise CompositionError("machine requires a non-empty tuple of on(...) handlers")
    flow = Machine(name, lifecycle, tuple(handlers), _call_site(name))
    _validate(flow)
    return flow
