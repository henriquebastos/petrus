"""Lower one guarded decision net: ONE TRANSITION PER LADDER RUNG.

v1's ``_Lowering`` is reused whole (imported, subclassed, never modified): node
and arc declaration, source-map ownership, Activity URI binding, the
``FragmentContext`` descent seam, post-build fragment verification, Net v3
projection, and the sidecar. Only one chain shape is added — ``await_event``
followed by ``branch(...).route(...)`` — and one node-declaration variant, the
transition that carries guards.

Each rung lowers to ``{machine}.{branch}.{rung}.fire`` consuming the state
baton and the typed event under a guard derived from the rung's pure
``when(state, event) -> bool`` through the current
``typed_guard(fn, converter=DomainConverter())`` path. ``derive_typed_guard``
matches the predicate's parameters to the transition's uniquely colored
weight-1 consume arcs, so the state and event colors are what bind the guard's
arguments — the same arcs the handler consumes.

Guards are evaluated during enabledness and are **not** recorded in History: a
rung that refused to fire leaves no canonical trace. Only the rung that fired
does, which is precisely the visibility this variant buys.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from petrus.impetus.binding import Handler
from petrus.impetus.dsl import GuardSpec, HandlerSpec, petri_handler, typed_guard
from petrus.impetus.petrinet import Arc, NetPath, Token
from petrus.impetus.petrinet.enabledness import Binding

from algebra import AwaitEvent, CompositionError, Effect, LowLevel, Machine, Terminal
from domain import DomainConverter, from_data, to_data
from guarded_algebra import Branch, Rung
from lowering import CompiledFlow, IngressBinding, _command_base, _Lowering

CONVERTER = DomainConverter()
"""v1's explicit domain converter.

CRITICAL: the DSL's default ``DataclassPayloadConverter`` does not reconstruct
nested ``Evidence``/``Ladder`` values, so every typed guard here — like every
typed transform in v1 — must be given this converter explicitly.
"""

type _Produced = Mapping[NetPath | str, Sequence[Token]]


@dataclass(frozen=True)
class RungPlan:
    """The compiler's fixed lowering record for one rung, for tests and reports."""

    id: str
    transition: str
    target: str | None
    outcome: str | None
    predicate: str


def _rung_bridge(rung: Rung, state_place: str, target_place: str | None) -> Handler:
    """Compiler-owned Petri bridge: one guarded rung, one folded state, zero/one outcome.

    The guard has already decided that this rung is the ladder's answer, so the
    handler never re-classifies — it only applies the rung's own pure fold and
    emission. ``binding.consumed`` is per consume arc in arc emission order:
    state first, then event.
    """
    state_color = rung.state_type.__name__
    emit = rung.emit
    outcome_type = rung.outcome_type

    def fire_rung(binding: Binding, outputs: tuple[Arc, ...]) -> _Produced:
        del outputs
        (_, (state_token,)), (_, (event_token,)) = binding.consumed
        state = from_data(rung.state_type, state_token.data)
        event = from_data(rung.event_type, event_token.data)
        produced: dict[NetPath | str, Sequence[Token]] = {
            state_place: (Token(state_color, to_data(rung.fold(state, event))),)
        }
        if emit is not None and outcome_type is not None and target_place is not None:
            outcome = emit(state, event)
            if type(outcome) is not outcome_type:
                raise ValueError(f"rung [{rung.id}] emitted {type(outcome).__name__}, declared {outcome_type.__name__}")
            produced[target_place] = (Token(outcome_type.__name__, to_data(outcome)),)
        return produced

    return fire_rung


class _GuardedLowering(_Lowering):
    """v1's lowering plus the guarded-rung chain shape."""

    def __init__(self, flow: Machine) -> None:
        super().__init__(flow)
        self.rung_plans: list[RungPlan] = []

    # -- node declaration ------------------------------------------------------

    def guarded_transition(
        self,
        path: str,
        handler: HandlerSpec,
        guards: tuple[GuardSpec, ...],
        source_id: str,
        role: str,
    ) -> str:
        """v1's ``transition`` with the DSL's authoring-time guard tuple attached."""
        node = self._node_handle(path, "transition")
        self.spec.transition(node, handler=handler, guards=guards)
        self._own(path, "transition", source_id, role)
        return path

    # -- chain lowering --------------------------------------------------------

    def _lower_chain(self, chain) -> None:
        steps = chain.steps
        if isinstance(chain.trigger, AwaitEvent) and len(steps) == 1 and isinstance(steps[0], Branch):
            self._lower_ingress_branch(chain.trigger, steps[0])
            return
        super()._lower_chain(chain)

    def _lower_ingress_branch(self, trigger: AwaitEvent, branch: Branch) -> None:
        if not branch.routes and any(candidate.emit is not None for candidate in branch.rungs):
            raise CompositionError(f"branch [{branch.id}] emits outcomes but was never routed with .route(...)")
        ingress_owner = self._register_source(trigger.id, trigger.source)
        state_place = self._state_place_for(branch.state_type, f"branch [{branch.id}]")

        source_path = self.transition(f"ingress.{trigger.id}", None, ingress_owner, "typed scoped ingress")
        event_place = self.place(f"events.{trigger.id}", trigger.event_type, ingress_owner, "typed event place")
        self.connect(source_path, event_place)
        self.ingress[trigger.id] = IngressBinding(source_path, trigger.event_type, self.flow.lifecycle.name)

        # Allocate every routed target place before any rung arc, so the rung
        # transitions' arcs land contiguously in declared rung order.
        targets = self._allocate_targets(branch)
        for candidate in branch.rungs:
            self._lower_rung(branch, candidate, state_place, event_place, targets[candidate.id])

        # Role-ordered target lowering, exactly v1's fixed order: simple
        # effects first in rung order, then descent fragments.
        for outcome_type, target in branch.routes:
            if isinstance(target, Effect):
                self._lower_effect(outcome_type, target, self._target_place(branch, targets, outcome_type))
        for outcome_type, target in branch.routes:
            if isinstance(target, LowLevel):
                self._lower_fragment(outcome_type, target, self._target_place(branch, targets, outcome_type))

    def _allocate_targets(self, branch: Branch) -> dict[str, str | None]:
        allocated: dict[type, str] = {}
        targets: dict[str, str | None] = {}
        for candidate in branch.rungs:
            outcome_type = candidate.outcome_type
            if outcome_type is None:
                targets[candidate.id] = None
                continue
            if outcome_type in allocated:  # two rungs may emit one color; they share its place
                targets[candidate.id] = allocated[outcome_type]
                continue
            target = branch.target_for(outcome_type)
            if not isinstance(target, (Terminal, Effect, LowLevel)):  # pragma: no cover - route() refuses drop()
                raise CompositionError(f"branch [{branch.id}] cannot route {outcome_type.__name__} to {target!r}")
            owner = self._register_source(target.id, target.source)
            if isinstance(target, Terminal):
                path = self.place(f"terminal.{target.id}", outcome_type, owner, "terminal outcome")
            else:
                path = self.place(f"commands.{_command_base(outcome_type)}", outcome_type, owner, "typed command")
            allocated[outcome_type] = path
            targets[candidate.id] = path
        return targets

    def _target_place(self, branch: Branch, targets: Mapping[str, str | None], outcome_type: type) -> str:
        for candidate in branch.rungs:
            if candidate.outcome_type is outcome_type:
                place = targets[candidate.id]
                assert place is not None
                return place
        raise CompositionError(f"branch [{branch.id}] routes {outcome_type.__name__} but no rung emits it")

    def _lower_rung(
        self,
        branch: Branch,
        candidate: Rung,
        state_place: str,
        event_place: str,
        target_place: str | None,
    ) -> None:
        owner = self._register_source(f"{branch.id}.{candidate.id}", candidate.source)
        outcome_type = candidate.outcome_type
        detail = "absorbing rung" if outcome_type is None else f"rung emitting {outcome_type.__name__}"
        path = self.guarded_transition(
            f"{self.flow.name}.{branch.id}.{candidate.id}.fire",
            petri_handler(_rung_bridge(candidate, state_place, target_place)),
            (typed_guard(candidate.when, converter=CONVERTER),),
            owner,
            f"guarded ladder rung [{candidate.id}] — {detail}",
        )
        self.connect(state_place, path)
        self.connect(event_place, path)
        self.connect(path, state_place)
        if target_place is not None:
            self.connect(path, target_place)
        self.rung_plans.append(
            RungPlan(
                candidate.id,
                path,
                target_place,
                None if outcome_type is None else outcome_type.__name__,
                candidate.source.symbol,
            )
        )


@dataclass(frozen=True)
class GuardedFlow:
    """v1's ``CompiledFlow`` plus the rung lowering plan this variant produced."""

    compiled: CompiledFlow
    rungs: tuple[RungPlan, ...]


def compile_guarded_flow(flow: Machine) -> CompiledFlow:
    """Compile one authored guarded machine into v1's immutable canonical assembly."""
    return _GuardedLowering(flow).compile()


def compile_guarded(flow: Machine) -> GuardedFlow:
    """Compile and additionally return the rung plan, for tests and the report."""
    lowering = _GuardedLowering(flow)
    compiled = lowering.compile()
    return GuardedFlow(compiled, tuple(lowering.rung_plans))


__all__ = [
    "CONVERTER",
    "GuardedFlow",
    "RungPlan",
    "compile_guarded",
    "compile_guarded_flow",
]
