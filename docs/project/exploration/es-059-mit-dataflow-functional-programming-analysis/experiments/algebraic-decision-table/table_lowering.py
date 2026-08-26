"""Lower the ordered case table to **exactly one** transition.

This module is a thin extension of the v1 slice's ``lowering._Lowering``: the
ingress, projection, effect, fragment, and fold lowerings are inherited
unchanged, and only the ``match`` + ``choose`` chain is new. That is the
experiment's hard invariant made structural — a richer authored decision must
still allocate one transition, one state output arc, and one output arc per
routed color, in the same fixed role order, so the canonical Net v3 bytes are
the v1 bytes.

What the case table adds to lowering is *attribution*, not topology: every
``case(...)`` and the optional ``normalize`` register their own source-map
source id, and the compiled flow carries a case index the explained-History
projection uses to name the rung that fired.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields
from typing import cast

from petrus.impetus.binding import Handler
from petrus.impetus.dsl import petri_handler
from petrus.impetus.petrinet import Arc, NetPath, Token
from petrus.impetus.petrinet.enabledness import Binding

from algebra import AwaitEvent, Choose, CompositionError, Effect, LowLevel, Machine, Terminal
from algebra import Handler as AuthoredHandler
from domain import from_data, to_data
from lowering import (
    CompiledFlow,
    FragmentContext,
    FragmentPorts,
    IngressBinding,
    _command_base,
    _Lowering,
)
from table_algebra import Match, evaluate_match, predicate_name

__all__ = ["CaseAttribution", "FragmentContext", "FragmentPorts", "TableCompiledFlow", "compile_flow"]


@dataclass(frozen=True)
class CaseAttribution:
    """One authored rung, joined to the color it emits (its History fingerprint)."""

    match_id: str
    case_id: str
    source_id: str
    when: str
    fold: str
    emit: str | None
    emit_color: str | None

    @property
    def transition_path(self) -> str:
        return self.match_id


@dataclass(frozen=True)
class TableCompiledFlow(CompiledFlow):
    """v1's compiled assembly plus the authored case index for attribution."""

    cases: tuple[CaseAttribution, ...] = ()

    def case_for_color(self, color: str | None) -> CaseAttribution | None:
        """The unique rung emitting ``color``; ``None`` when it does not identify one."""
        matching = [entry for entry in self.cases if entry.emit_color == color and color is not None]
        return matching[0] if len(matching) == 1 else None

    @property
    def absorbing_cases(self) -> tuple[CaseAttribution, ...]:
        """The ``.drop()`` rungs — mutually indistinguishable in canonical History."""
        return tuple(entry for entry in self.cases if entry.emit_color is None)


type _Produced = Mapping[NetPath | str, Sequence[Token]]


def _match_bridge(table: Match, state_place: str, case_places: Mapping[type, str]) -> Handler:
    """Compiler-owned Petri bridge: one durable decision, one routed outcome.

    Identical in shape to v1's ``_decision_bridge``; the only difference is
    that the decision is evaluated by ``evaluate_match`` over the authored
    table instead of by one opaque function call.
    """
    state_color = table.state_type.__name__
    routes = dict(case_places)

    def match_and_route(binding: Binding, outputs: tuple[Arc, ...]) -> _Produced:
        del outputs
        (_, (state_token,)), (_, (event_token,)) = binding.consumed
        state = from_data(table.state_type, state_token.data)
        event = from_data(table.event_type, event_token.data)
        _fired, next_state, outcome = evaluate_match(table, state, event)
        produced: dict[NetPath | str, Sequence[Token]] = {state_place: (Token(state_color, to_data(next_state)),)}
        if outcome is not None:
            color = type(outcome)
            if color not in routes:
                raise ValueError(f"match [{table.id}] emitted unrouted outcome {color.__name__}")
            produced[routes[color]] = (Token(color.__name__, to_data(outcome)),)
        return produced

    return match_and_route


class _TableLowering(_Lowering):
    """v1's lowering with one extra chain shape: ``await_event → match → choose``."""

    def __init__(self, flow: Machine) -> None:
        super().__init__(flow)
        self.case_attributions: list[CaseAttribution] = []

    def compile(self) -> TableCompiledFlow:
        base = super().compile()
        carried = {field.name: getattr(base, field.name) for field in fields(CompiledFlow)}
        return TableCompiledFlow(**carried, cases=tuple(self.case_attributions))

    def _lower_chain(self, chain: AuthoredHandler) -> None:
        steps = chain.steps
        if (
            isinstance(chain.trigger, AwaitEvent)
            and len(steps) == 2
            and isinstance(steps[0], Match)
            and isinstance(steps[1], Choose)
        ):
            self._lower_ingress_match(chain.trigger, steps[0], steps[1])
            return
        super()._lower_chain(chain)

    def _lower_ingress_match(self, trigger: AwaitEvent, table: Match, choose: Choose) -> None:
        ingress_owner = self._register_source(trigger.id, trigger.source)
        match_owner = self._register_source(table.id, table.source)
        if table.normalize_source is not None:
            self._register_source(f"{table.id}.normalize", table.normalize_source)
        for entry in table.cases:
            source_id = self._register_source(f"{table.id}.{entry.id}", entry.source)
            self.case_attributions.append(
                CaseAttribution(
                    match_id=f"{self.flow.name}.{table.id}.fire",
                    case_id=entry.id,
                    source_id=source_id,
                    when=predicate_name(entry.when),
                    fold=_symbol(entry.fold),
                    emit=None if entry.emit is None else _symbol(entry.emit),
                    emit_color=None if entry.emit_type is None else entry.emit_type.__name__,
                )
            )
        state_place = self._state_place_for(table.state_type, f"match [{table.id}]")

        source_path = self.transition(f"ingress.{trigger.id}", None, ingress_owner, "typed scoped ingress")
        event_place = self.place(f"events.{trigger.id}", trigger.event_type, ingress_owner, "typed event place")
        self.connect(source_path, event_place)
        self.ingress[trigger.id] = IngressBinding(source_path, trigger.event_type, self.flow.lifecycle.name)

        # Allocate every routed color's place before the decision's arcs, so
        # the decision's output arcs land in first-emitted-in-the-table order.
        case_places: dict[type, str] = {}
        for outcome_type, target in choose.cases:
            if isinstance(target, Terminal):
                target_owner = self._register_source(target.id, target.source)
                case_places[outcome_type] = self.place(
                    f"terminal.{target.id}", outcome_type, target_owner, "terminal outcome"
                )
            elif isinstance(target, (Effect, LowLevel)):
                target_owner = self._register_source(target.id, target.source)
                base = _command_base(outcome_type)
                case_places[outcome_type] = self.place(f"commands.{base}", outcome_type, target_owner, "typed command")
            else:  # pragma: no cover - table choose() refuses drop() and other targets
                raise CompositionError(f"unsupported choose target {target!r}; v2 declares drops per case")

        match_path = self.transition(
            f"{self.flow.name}.{table.id}.fire",
            petri_handler(_match_bridge(table, state_place, case_places)),
            match_owner,
            "durable decision",
        )
        self.connect(state_place, match_path)
        self.connect(event_place, match_path)
        self.connect(match_path, state_place)
        for outcome_type, _ in choose.cases:
            self.connect(match_path, case_places[outcome_type])

        for outcome_type, target in choose.cases:
            if isinstance(target, Effect):
                self._lower_effect(outcome_type, target, case_places[outcome_type])
        for outcome_type, target in choose.cases:
            if isinstance(target, LowLevel):
                self._lower_fragment(outcome_type, target, case_places[outcome_type])


def _symbol(function: object) -> str:
    return cast(str, getattr(function, "__name__", "<anonymous>"))


def compile_flow(flow: Machine) -> TableCompiledFlow:
    """Compile one authored table machine into an immutable canonical assembly."""
    return _TableLowering(flow).compile()
