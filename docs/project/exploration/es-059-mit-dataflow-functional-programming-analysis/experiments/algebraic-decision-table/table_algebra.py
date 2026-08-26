"""Immutable source values for the algebraic decision table (experiment A, "v2").

This is v1's algebra with exactly one construct replaced. Where v1 authored

    .decide("route_ci", route_ci)      # one opaque (state, event) -> Decision

v2 authors

    .match("route_ci", normalize=..., cases=(case(...), case(...), ...))

so the *structure* of the decision — its rungs, their order, what each one
commits, and what each one emits — becomes visible to the algebra, to the
source map, and to the explained History. Everything else (``await_event``,
``project``, ``effect``, ``terminal``, ``low_level``, ``fold``, ``to``,
``lifecycle``, ``machine``, ``Choose``) is imported unmodified from the v1
slice; this module owns only the case table and the checks it makes possible.

Evaluation contract (one state, uniform):

1. ``normalize(state, event)`` runs once, unconditionally, producing the
   state every construct below observes;
2. cases are tried **in authored order, first match wins**; a case matches
   when its ``when(state, event)`` is true, or when it is the mandatory
   trailing ``otherwise`` case;
3. the matched case's ``fold(state, event)`` produces the committed state and
   its ``emit(state, event)`` — when it has one — produces exactly one routed
   outcome. A ``.drop()`` case emits nothing.

The table is total by construction: exactly one ``otherwise`` case is
required and it must be last, so there is no "fell off the end" runtime path.
Because matching is ordered and first-match-wins, overlapping predicates are
benign — a later case simply never sees an observation an earlier one
claimed. That is the property the algebra can rely on; it is also the reason
predicate overlap cannot be flagged statically (see ``report.md`` §7).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import cast

from algebra import (
    AwaitEvent,
    Choose,
    CompositionError,
    Effect,
    Fold,
    Handler,
    LowLevel,
    Machine,
    Outcome,
    Project,
    SourceRef,
    Step,
    Terminal,
    To,
    _call_site,
    _function_site,
    _named_parameters,
    _require_id,
    _typed_hints,
    machine as _v1_machine,
)


class _Otherwise:
    """The total-table sentinel: matches unconditionally, only as the last case."""

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return "otherwise"


otherwise = _Otherwise()

type Predicate = Callable[..., object] | _Otherwise


@dataclass(frozen=True)
class Case:
    """One rung of an ordered decision table.

    ``when`` classifies, ``fold`` commits, ``emit`` (or its absence) routes.
    All three are ordinary pure typed functions of the normalized
    ``(state, event)`` pair; none of them knows about Petri.
    """

    id: str
    when: Predicate
    fold: Callable[..., object]
    emit: Callable[..., object] | None
    state_type: type
    event_type: type
    emit_type: type | None
    source: SourceRef

    @property
    def outcome_label(self) -> str:
        return "drop" if self.emit_type is None else self.emit_type.__name__


def predicate_name(when: Predicate) -> str:
    """The authored classifier's symbol, or ``otherwise`` for the total case."""
    return "otherwise" if isinstance(when, _Otherwise) else cast(str, getattr(when, "__name__", "<predicate>"))


def _pair(function: Callable[..., object], noun: str) -> tuple[type, type]:
    parameters = _named_parameters(function, noun)
    if len(parameters) != 2:
        raise CompositionError(f"{noun} requires exactly (state, event) typed parameters")
    (_, state_type), (_, event_type) = parameters
    return state_type, event_type


@dataclass(frozen=True)
class CaseBuilder:
    """A case awaiting its routing decision: ``.drop()`` or ``.emit(...)``."""

    id: str
    when: Predicate
    fold: Callable[..., object]
    state_type: type
    event_type: type
    source: SourceRef

    def drop(self) -> Case:
        """Absorb the observation durably: commit the fold, emit nothing."""
        return Case(self.id, self.when, self.fold, None, self.state_type, self.event_type, None, self.source)

    def emit(self, function: Callable[..., object]) -> Case:
        """Emit exactly one outcome; its return annotation is the routed color."""
        noun = f"case [{self.id}] emit"
        state_type, event_type = _pair(function, noun)
        emit_source = _function_site(function)
        if state_type is not self.state_type or event_type is not self.event_type:
            raise CompositionError(
                f"{self.source} [{self.id}] folds ({self.state_type.__name__}, {self.event_type.__name__}), but "
                f"{emit_source} [{self.id}] emits from ({state_type.__name__}, {event_type.__name__})"
            )
        emit_type = _typed_hints(function, noun).get("return")
        if not isinstance(emit_type, type):
            raise CompositionError(f"{emit_source} [{self.id}] emit must return one concrete outcome class")
        return Case(self.id, self.when, self.fold, function, self.state_type, self.event_type, emit_type, self.source)


def case(id: str, *, when: Predicate, fold: Callable[..., object]) -> CaseBuilder:
    """Author one rung: a classifier, a state commit, and (next) its routing."""
    _require_id(id, "case")
    if not callable(fold):
        raise CompositionError(f"case [{id}] requires a pure fold(state, event) -> state, got {fold!r}")
    state_type, event_type = _pair(fold, f"case [{id}] fold")
    folded = _typed_hints(fold, f"case [{id}] fold").get("return")
    if folded is not state_type:
        raise CompositionError(
            f"{_function_site(fold)} [{id}] consumes state {state_type.__name__} but folds to {folded!r}"
        )
    if not isinstance(when, _Otherwise):
        if not callable(when):
            raise CompositionError(f"case [{id}] requires a pure when(state, event) -> bool or otherwise, got {when!r}")
        when_state, when_event = _pair(when, f"case [{id}] when")
        if when_state is not state_type or when_event is not event_type:
            raise CompositionError(
                f"{_function_site(when)} [{id}] classifies ({when_state.__name__}, {when_event.__name__}), but "
                f"{_function_site(fold)} [{id}] folds ({state_type.__name__}, {event_type.__name__})"
            )
        if _typed_hints(when, f"case [{id}] when").get("return") is not bool:
            raise CompositionError(f"{_function_site(when)} [{id}] when must return bool")
    return CaseBuilder(id, when, fold, state_type, event_type, _call_site(id))


@dataclass(frozen=True)
class Match:
    """One durable decision authored as an ordered, total case table."""

    id: str
    normalize: Callable[..., object] | None
    normalize_source: SourceRef | None
    cases: tuple[Case, ...]
    state_type: type
    event_type: type
    outcome_types: tuple[type, ...]
    source: SourceRef

    def case_for(self, case_id: str) -> Case | None:
        return next((entry for entry in self.cases if entry.id == case_id), None)


class UnmatchedObservation(RuntimeError):
    """A total table failed to match; unreachable while ``otherwise`` is required."""


def evaluate_match(match: Match, state: object, event: object) -> tuple[str, object, object | None]:
    """Evaluate one authored table purely: (fired case id, next state, outcome)."""
    current = match.normalize(state, event) if match.normalize is not None else state
    for entry in match.cases:
        if isinstance(entry.when, _Otherwise):
            matched = True
        else:
            answer = cast(Callable[..., object], entry.when)(current, event)
            # The -> bool annotation is checked at construction; the value is
            # enforced here so a classifier drifting to truthy non-bools
            # refuses loud instead of silently selecting its rung.
            if type(answer) is not bool:
                raise ValueError(f"case [{entry.id}] predicate must return bool, got {type(answer).__name__}")
            matched = answer
        if matched:
            outcome = entry.emit(current, event) if entry.emit is not None else None
            return entry.id, entry.fold(current, event), outcome
    raise UnmatchedObservation(f"match [{match.id}] matched no case")  # pragma: no cover - otherwise is mandatory


class TableHandler(Handler):
    """v1's authored handler chain plus ``match`` and its case-table ``choose``."""

    def _with(self, step: object) -> TableHandler:
        return TableHandler(self.trigger, (*self.steps, cast("Step", step)))

    def match(
        self,
        id: str,
        *,
        cases: tuple[Case, ...],
        normalize: Callable[..., object] | None = None,
    ) -> TableHandler:
        _require_id(id, "match")
        if self.steps:
            raise CompositionError(f"match [{id}] must directly follow its trigger in this slice")
        if not cases or not all(isinstance(entry, Case) for entry in cases):
            raise CompositionError(f"match [{id}] requires a non-empty tuple of case(...) values")
        source = _call_site(id)

        seen: dict[str, SourceRef] = {}
        for entry in cases:
            prior = seen.get(entry.id)
            if prior is not None:
                raise CompositionError(
                    f"match [{id}] declares duplicate case id [{entry.id}]: "
                    f"first at {prior} and again at {entry.source}"
                )
            seen[entry.id] = entry.source

        first = cases[0]
        for entry in cases[1:]:
            if entry.state_type is not first.state_type or entry.event_type is not first.event_type:
                raise CompositionError(
                    f"{first.source} [{first.id}] decides ({first.state_type.__name__}, "
                    f"{first.event_type.__name__}), but {entry.source} [{entry.id}] decides "
                    f"({entry.state_type.__name__}, {entry.event_type.__name__})"
                )

        totals = [entry for entry in cases if isinstance(entry.when, _Otherwise)]
        if not totals:
            raise CompositionError(
                f"{source} [{id}] is not total: the last case must be case(..., when=otherwise, ...) "
                f"so every observation reaches exactly one rung"
            )
        if len(totals) > 1:
            raise CompositionError(
                f"{source} [{id}] declares {len(totals)} otherwise cases "
                f"({totals[0].source} [{totals[0].id}] and {totals[1].source} [{totals[1].id}]); "
                f"only the last case may be total"
            )
        if cases[-1] is not totals[0]:
            unreachable = cases[cases.index(totals[0]) + 1]
            raise CompositionError(
                f"{unreachable.source} [{id}.{unreachable.id}] is unreachable: "
                f"{totals[0].source} [{id}.{totals[0].id}] already matches every observation"
            )

        event_type = self.trigger.event_type if isinstance(self.trigger, AwaitEvent) else self.trigger
        if first.event_type is not event_type:
            trigger_label = (
                f"{self.trigger.source} [{self.trigger.id}]"
                if isinstance(self.trigger, AwaitEvent)
                else f"trigger {event_type.__name__}"
            )
            raise CompositionError(
                f"{trigger_label} delivers {event_type.__name__}, but "
                f"{first.source} [{id}.{first.id}] accepts {first.event_type.__name__}"
            )

        normalize_source: SourceRef | None = None
        if normalize is not None:
            if not callable(normalize):
                raise CompositionError(f"match [{id}] normalize must be a pure (state, event) -> state function")
            normalize_source = _function_site(normalize)
            state_type, normalize_event = _pair(normalize, f"match [{id}] normalize")
            folded = _typed_hints(normalize, f"match [{id}] normalize").get("return")
            if (
                state_type is not first.state_type
                or normalize_event is not first.event_type
                or folded is not state_type
            ):
                raise CompositionError(
                    f"{normalize_source} [{id}] normalize must be "
                    f"({first.state_type.__name__}, {first.event_type.__name__}) -> {first.state_type.__name__}"
                )

        outcomes: list[type] = []
        for entry in cases:
            if entry.emit_type is not None and entry.emit_type not in outcomes:
                outcomes.append(entry.emit_type)
        return self._with(
            Match(
                id,
                normalize,
                normalize_source,
                tuple(cases),
                first.state_type,
                first.event_type,
                tuple(outcomes),
                source,
            )
        )

    def choose(self, cases: Mapping[type, Outcome]) -> TableHandler:
        """Route the emitted colors; exhaustiveness is fed by the case table."""
        source = _call_site("choose")
        if not self.steps or not isinstance(self.steps[-1], Match):
            raise CompositionError("choose must directly follow a match step")
        table = cast(Match, self.steps[-1])
        emitters: dict[type, Case] = {}
        for entry in table.cases:  # the first authored emitter of a color owns its diagnostics
            if entry.emit_type is not None:
                emitters.setdefault(entry.emit_type, entry)
        for outcome_type, entry in emitters.items():
            if outcome_type not in cases:
                raise CompositionError(
                    f"{entry.source} [{table.id}.{entry.id}] emits {outcome_type.__name__}, but "
                    f"the choose at {source} routes no target for it"
                )
        for extra, target in cases.items():
            if extra not in emitters:
                label = f"[{target.id}]" if isinstance(target, (Effect, Terminal, LowLevel)) else "drop()"
                raise CompositionError(
                    f"{source} routes {extra.__name__} to {target.source} {label}, but no case in [{table.id}] emits it"
                )
        for outcome_type, target in cases.items():
            if isinstance(target, Effect) and target.request_type is not outcome_type:
                entry = emitters[outcome_type]
                raise CompositionError(
                    f"{entry.source} [{table.id}.{entry.id}] emits {outcome_type.__name__}, but "
                    f"{target.source} [{target.id}] accepts {target.request_type.__name__}"
                )
        ordered = tuple((outcome_type, cases[outcome_type]) for outcome_type in table.outcome_types)
        return self._with(Choose(ordered, source))


def on(trigger: AwaitEvent | type) -> TableHandler:
    if not isinstance(trigger, (AwaitEvent, type)):
        raise CompositionError(f"on requires an await_event ingress or a fact type, got {trigger!r}")
    return TableHandler(trigger)


def _authored_ids(flow: Machine) -> tuple[tuple[str, SourceRef], ...]:
    """Every authored id in the flow, including the table's match and case ids.

    Adapted from v1's walker: the only new arms are ``Match`` and its cases,
    whose ids share one namespace with every other authored id.
    """
    collected: list[tuple[str, SourceRef]] = []
    for handler in flow.handlers:
        if isinstance(handler.trigger, AwaitEvent):
            collected.append((handler.trigger.id, handler.trigger.source))
        for step in handler.steps:
            if isinstance(step, (Project, Fold)):
                collected.append((step.id, step.source))
            elif isinstance(step, Match):
                collected.append((step.id, step.source))
                collected.extend((f"{step.id}.{entry.id}", entry.source) for entry in step.cases)
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
            elif isinstance(step, Match):
                collected.extend((step.state_type, step.event_type, *step.outcome_types))
            elif isinstance(step, Fold):
                collected.extend((step.state_type, step.event_type, step.output_type))
            elif isinstance(step, Choose):
                for outcome_type, target in step.cases:
                    collected.append(outcome_type)
                    if isinstance(target, Effect):
                        collected.extend((target.request_type, target.result_type))
                    elif isinstance(target, LowLevel):
                        collected.append(target.returns)
    return tuple(collected)


def machine(name: str, *, lifecycle, handlers: tuple[Handler, ...]) -> Machine:
    """v1's ``machine`` plus duplicate-id and nominal checks over table ids."""
    flow = Machine(name, lifecycle, tuple(handlers), _call_site(name))

    seen: dict[str, SourceRef] = {}
    for authored_id, reference in _authored_ids(flow):
        prior = seen.get(authored_id)
        if prior is not None:
            raise CompositionError(
                f"duplicate authored id [{authored_id}]: declared at {prior} and again at {reference}"
            )
        seen[authored_id] = reference

    names: dict[str, type] = {}
    for referenced in _referenced_types(flow):
        prior_type = names.setdefault(referenced.__name__, referenced)
        if prior_type is not referenced:
            raise CompositionError(
                f"two distinct classes share the nominal name {referenced.__name__!r}: "
                f"{prior_type!r} and {referenced!r}; nominal port identity requires unique names"
            )

    _v1_machine(name, lifecycle=lifecycle, handlers=handlers)  # v1's own refusals, unchanged
    return flow


__all__ = [
    "Case",
    "CaseBuilder",
    "Match",
    "TableHandler",
    "UnmatchedObservation",
    "case",
    "evaluate_match",
    "machine",
    "on",
    "otherwise",
    "predicate_name",
]
