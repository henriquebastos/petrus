"""Immutable source values for the **guarded decision net** authoring variant.

This is experiment v2 of ES-059. v1 (``../typed-flow-vertical-slice``) authors
the CI-routing decision as ONE opaque pure function returning
``Decision[state, outcome-union]`` and lowers it to ONE transition. v2 keeps
every other construct identical and replaces that single ``decide(...).choose``
step with a ``branch(...)`` of explicit **rungs**: one guarded transition per
ladder rung, so the ladder is visible in the canonical topology.

Reused from v1 unchanged (imported, never copied): ``SourceRef``,
``CompositionError``, ``lifecycle``, ``await_event``, ``effect``, ``terminal``,
``drop``, ``low_level``, ``machine``, ``Handler``'s ``project``/``fold``/``to``
chain, and the id/type validation helpers. New here: ``Rung``, ``Branch``,
``rung(...)``, ``GuardedHandler.branch/route``, and ``guarded_machine``.

The construct performs no motion: composition mistakes fail here, before
lowering and before any History file exists. What it deliberately **cannot**
check is the rung-set's mutual exclusivity and exhaustiveness — see
``report.md`` §7 and ``test_guarded_exclusivity.py``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace

from algebra import (
    AwaitEvent,
    CompositionError,
    Drop,
    Effect,
    Handler,
    Lifecycle,
    LowLevel,
    Machine,
    Outcome,
    SourceRef,
    Terminal,
    _authored_ids,
    _call_site,
    _function_site,
    _named_parameters,
    _referenced_types,
    _require_id,
    _typed_hints,
    machine,
)

__all__ = [
    "Branch",
    "GuardedHandler",
    "Rung",
    "RungDraft",
    "guarded_machine",
    "on",
    "rung",
]


def _predicate_types(function: Callable[..., object], noun: str) -> tuple[type, type]:
    """A rung predicate is ``(state, event) -> bool`` over concrete domain types."""
    parameters = _named_parameters(function, noun)
    if len(parameters) != 2:
        raise CompositionError(f"{noun} requires exactly (state, event) typed parameters")
    (_, state_type), (_, event_type) = parameters
    hints = _typed_hints(function, noun)
    if hints.get("return") is not bool:
        raise CompositionError(f"{noun} must return bool so the current typed-guard path can derive it")
    return state_type, event_type


def _pair_types(function: Callable[..., object], noun: str) -> tuple[type, type, type]:
    """A rung fold/emit is ``(state, event) -> Result`` over concrete domain types."""
    parameters = _named_parameters(function, noun)
    if len(parameters) != 2:
        raise CompositionError(f"{noun} requires exactly (state, event) typed parameters")
    (_, state_type), (_, event_type) = parameters
    hints = _typed_hints(function, noun)
    result = hints.get("return")
    if not isinstance(result, type):
        raise CompositionError(f"{noun} requires a concrete return type, got {result!r}")
    return state_type, event_type, result


@dataclass(frozen=True)
class Rung:
    """One guarded ladder rung: a predicate, a state fold, and zero/one outcome.

    Lowers to its own transition consuming ``state + event`` under a guard
    derived from ``when``. ``emit is None`` spells the deliberate no-output
    rung — the case v1 could only express as an outcome color that produced no
    token, and therefore could not name in History.
    """

    id: str
    when: Callable[..., bool]
    fold: Callable[..., object]
    emit: Callable[..., object] | None
    state_type: type
    event_type: type
    outcome_type: type | None
    source: SourceRef


@dataclass(frozen=True)
class RungDraft:
    """A rung awaiting its ``.emit(...)`` or ``.drop()`` disposition."""

    id: str
    when: Callable[..., bool]
    fold: Callable[..., object]
    state_type: type
    event_type: type
    source: SourceRef

    def emit(self, function: Callable[..., object]) -> Rung:
        state_type, event_type, outcome_type = _pair_types(function, f"rung [{self.id}] emit")
        self._require_pair(state_type, event_type, f"rung [{self.id}] emit")
        return Rung(
            self.id, self.when, self.fold, function, self.state_type, self.event_type, outcome_type, self.source
        )

    def drop(self) -> Rung:
        return Rung(self.id, self.when, self.fold, None, self.state_type, self.event_type, None, self.source)

    def _require_pair(self, state_type: type, event_type: type, noun: str) -> None:
        if state_type is not self.state_type or event_type is not self.event_type:
            raise CompositionError(
                f"{noun} accepts ({state_type.__name__}, {event_type.__name__}) but rung [{self.id}] "
                f"is guarded over ({self.state_type.__name__}, {self.event_type.__name__})"
            )


def rung(id: str, *, when: Callable[..., bool], fold: Callable[..., object]) -> RungDraft:
    """Author one ladder rung from a pure predicate and a pure state fold."""
    _require_id(id, "rung")
    state_type, event_type = _predicate_types(when, f"rung [{id}] when")
    fold_state, fold_event, fold_result = _pair_types(fold, f"rung [{id}] fold")
    if fold_state is not state_type or fold_event is not event_type:
        raise CompositionError(
            f"rung [{id}] fold accepts ({fold_state.__name__}, {fold_event.__name__}) but its predicate "
            f"{_function_site(when)} guards ({state_type.__name__}, {event_type.__name__})"
        )
    if fold_result is not state_type:
        raise CompositionError(
            f"rung [{id}] fold returns {fold_result.__name__} but must reproduce the state baton {state_type.__name__}"
        )
    # The predicate is the rule a reader wants when asking "why did this rung
    # fire (or why did nothing happen)", so it owns the rung's attribution.
    return RungDraft(id, when, fold, state_type, event_type, _function_site(when))


@dataclass(frozen=True)
class Branch:
    """One authored ladder: an ordered rung set plus its outcome routing."""

    id: str
    rungs: tuple[Rung, ...]
    routes: tuple[tuple[type, Outcome], ...]
    state_type: type
    event_type: type
    source: SourceRef

    def target_for(self, outcome_type: type) -> Outcome:
        for candidate, target in self.routes:
            if candidate is outcome_type:
                return target
        raise CompositionError(f"branch [{self.id}] routes no outcome {outcome_type.__name__}")


class GuardedHandler(Handler):
    """v1's authored chain plus the ``branch(...).route(...)`` rung form."""

    def _with(self, step) -> GuardedHandler:
        return GuardedHandler(self.trigger, (*self.steps, step))

    def branch(self, id: str, *, rungs: tuple[Rung, ...]) -> GuardedHandler:
        _require_id(id, "branch")
        if self.steps:
            raise CompositionError(f"branch [{id}] must directly follow its trigger in this slice")
        if not rungs or not all(isinstance(candidate, Rung) for candidate in rungs):
            raise CompositionError(f"branch [{id}] requires a non-empty tuple of rung(...) values")
        source = _call_site(id)
        event_type = self.trigger.event_type if isinstance(self.trigger, AwaitEvent) else self.trigger
        state_types = {candidate.state_type for candidate in rungs}
        if len(state_types) != 1:
            raise CompositionError(
                f"branch [{id}] rungs disagree about the state baton: {sorted(t.__name__ for t in state_types)}"
            )
        [state_type] = state_types
        for candidate in rungs:
            if candidate.event_type is not event_type:
                raise CompositionError(
                    f"{source} [{id}] is triggered by {event_type.__name__}, but "
                    f"{candidate.source} [{candidate.id}] accepts {candidate.event_type.__name__}"
                )
        seen: dict[str, SourceRef] = {}
        for candidate in rungs:
            prior = seen.get(candidate.id)
            if prior is not None:
                raise CompositionError(
                    f"branch [{id}] declares rung [{candidate.id}] twice: at {prior} and again at {candidate.source}"
                )
            seen[candidate.id] = candidate.source
        return self._with(Branch(id, tuple(rungs), (), state_type, event_type, source))

    def route(self, cases: Mapping[type, Outcome]) -> GuardedHandler:
        if not self.steps or not isinstance(self.steps[-1], Branch):
            raise CompositionError("route must directly follow a branch step")
        branch = self.steps[-1]
        emitted: list[type] = []
        for candidate in branch.rungs:
            if candidate.outcome_type is not None and candidate.outcome_type not in emitted:
                emitted.append(candidate.outcome_type)
        for outcome_type in emitted:
            if outcome_type not in cases:
                raise CompositionError(f"{branch.source} [{branch.id}] has no route for {outcome_type.__name__}")
        for extra in cases:
            if extra not in emitted:
                raise CompositionError(
                    f"{branch.source} [{branch.id}] emits no outcome {extra.__name__} routed by this route"
                )
        for outcome_type, target in cases.items():
            if isinstance(target, Effect) and target.request_type is not outcome_type:
                source = next(r.source for r in branch.rungs if r.outcome_type is outcome_type)
                raise CompositionError(
                    f"{source} produces {outcome_type.__name__}, but "
                    f"{target.source} [{target.id}] accepts {target.request_type.__name__}"
                )
        routes = tuple((outcome_type, cases[outcome_type]) for outcome_type in emitted)
        return GuardedHandler(self.trigger, (*self.steps[:-1], replace(branch, routes=routes)))


def on(trigger: AwaitEvent | type) -> GuardedHandler:
    """Start one authored chain; identical to v1's ``on`` plus ``branch``."""
    if not isinstance(trigger, (AwaitEvent, type)):
        raise CompositionError(f"on requires an await_event ingress or a fact type, got {trigger!r}")
    return GuardedHandler(trigger)


def _branch_ids(flow: Machine) -> list[tuple[str, SourceRef]]:
    collected: list[tuple[str, SourceRef]] = []
    for handler in flow.handlers:
        for step in handler.steps:
            if not isinstance(step, Branch):
                continue
            collected.append((step.id, step.source))
            # Rung ids are unique within their branch scope, so a rung may
            # legitimately share a bare name with a routed effect ("rerun").
            collected.extend((f"{step.id}.{candidate.id}", candidate.source) for candidate in step.rungs)
            for _, target in step.routes:
                if isinstance(target, (Effect, Terminal, LowLevel)):
                    collected.append((target.id, target.source))
                elif isinstance(target, Drop):  # pragma: no cover - route() refuses a drop target
                    raise CompositionError(f"branch [{step.id}] cannot route an emitted outcome to drop()")
    return collected


def _branch_types(flow: Machine) -> list[type]:
    collected: list[type] = []
    for handler in flow.handlers:
        for step in handler.steps:
            if not isinstance(step, Branch):
                continue
            collected.extend((step.state_type, step.event_type))
            for outcome_type, target in step.routes:
                collected.append(outcome_type)
                if isinstance(target, Effect):
                    collected.extend((target.request_type, target.result_type))
                elif isinstance(target, LowLevel):
                    collected.append(target.returns)
    return collected


def guarded_machine(name: str, *, lifecycle: Lifecycle, handlers: tuple[Handler, ...]) -> Machine:
    """v1's ``machine(...)`` validation extended over branch/rung constructs."""
    flow = machine(name, lifecycle=lifecycle, handlers=handlers)

    seen: dict[str, SourceRef] = {}
    for authored_id, source in [*_authored_ids(flow), *_branch_ids(flow)]:
        prior = seen.get(authored_id)
        if prior is not None:
            raise CompositionError(f"duplicate authored id [{authored_id}]: declared at {prior} and again at {source}")
        seen[authored_id] = source

    names: dict[str, type] = {}
    for referenced in [*_referenced_types(flow), *_branch_types(flow)]:
        prior_type = names.setdefault(referenced.__name__, referenced)
        if prior_type is not referenced:
            raise CompositionError(
                f"two distinct classes share the nominal name {referenced.__name__!r}: "
                f"{prior_type!r} and {referenced!r}; nominal port identity requires unique names"
            )
    return flow
