"""Instance-scoped selection of one already-enabled firing ``Binding``.

Selection is a pure proposal.  Policy state moves only when the Engine has
committed the corresponding begin, and load reconstructs it from the existing
``CandidateSelected``/``FiringBegun`` pair without adding History facts.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Protocol

from petrus.impetus.history import CandidateSelected, FiringBegun, Record
from petrus.impetus.petrinet import Binding, NetPath

type SelectionState = object
type AdmissionFilter = Callable[[Binding], bool]
type StableRanker = Callable[[Binding], object]


@dataclass(frozen=True)
class SelectionProposal:
    """One proposed binding and the immutable state change its commit earns."""

    binding: Binding
    prior_state: SelectionState
    next_state: SelectionState


class SelectionPolicy(Protocol):
    """Pure proposal plus reconstruction from one committed transition."""

    def propose(self, candidates: tuple[Binding, ...], state: SelectionState) -> SelectionProposal | None: ...

    def fold_committed(self, state: SelectionState, transition: NetPath) -> SelectionState: ...


@dataclass(frozen=True)
class First:
    """Select the first binding in Petrinet enumeration order."""

    def propose(self, candidates: tuple[Binding, ...], state: SelectionState) -> SelectionProposal | None:
        if not candidates:
            return None
        return SelectionProposal(candidates[0], state, state)

    def fold_committed(self, state: SelectionState, transition: NetPath) -> SelectionState:
        del transition
        return state


@dataclass(frozen=True, init=False)
class Priority:
    """Highest configured transition priority first; original order breaks ties."""

    priorities: Mapping[NetPath, int]

    def __init__(self, priorities: Mapping[NetPath | str, int]):
        snapshot = {NetPath(path): priority for path, priority in priorities.items()}
        object.__setattr__(self, "priorities", MappingProxyType(snapshot))

    def propose(self, candidates: tuple[Binding, ...], state: SelectionState) -> SelectionProposal | None:
        if not candidates:
            return None
        binding = max(candidates, key=lambda candidate: self.priorities.get(candidate.transition, 0))
        return SelectionProposal(binding, state, state)

    def fold_committed(self, state: SelectionState, transition: NetPath) -> SelectionState:
        del transition
        return state


@dataclass(frozen=True, init=False)
class RoundRobin:
    """Transition-level rotation; each transition's first binding wins its tie."""

    transitions: tuple[NetPath, ...]

    def __init__(self, transitions: Sequence[NetPath | str]):
        ring = tuple(NetPath(transition) for transition in transitions)
        if not ring or len(set(ring)) != len(ring):
            raise ValueError("round-robin transitions must be a non-empty unique sequence")
        object.__setattr__(self, "transitions", ring)

    def propose(self, candidates: tuple[Binding, ...], state: SelectionState) -> SelectionProposal | None:
        if not candidates:
            return None
        cursor = 0 if state is None else _cursor(state, len(self.transitions))
        first_by_transition: dict[NetPath, Binding] = {}
        for candidate in candidates:
            first_by_transition.setdefault(candidate.transition, candidate)
        for offset in range(len(self.transitions)):
            transition = self.transitions[(cursor + offset) % len(self.transitions)]
            if transition in first_by_transition:
                next_state = (self.transitions.index(transition) + 1) % len(self.transitions)
                return SelectionProposal(first_by_transition[transition], state, next_state)
        raise ValueError("offered candidates are outside the round-robin transition ring")

    def fold_committed(self, state: SelectionState, transition: NetPath) -> SelectionState:
        del state
        try:
            return (self.transitions.index(transition) + 1) % len(self.transitions)
        except ValueError:
            raise ValueError(f"committed transition {transition} is outside the round-robin transition ring") from None


@dataclass(frozen=True)
class SelectionPipeline:
    """Fixed filters → stable rankers → one strategy composition."""

    filters: tuple[AdmissionFilter, ...] = ()
    rankers: tuple[StableRanker, ...] = ()
    strategy: SelectionPolicy = First()

    def __init__(
        self,
        *,
        filters: Iterable[AdmissionFilter] = (),
        rankers: Iterable[StableRanker] = (),
        strategy: SelectionPolicy = First(),
    ):
        object.__setattr__(self, "filters", tuple(filters))
        object.__setattr__(self, "rankers", tuple(rankers))
        object.__setattr__(self, "strategy", strategy)

    def propose(self, candidates: tuple[Binding, ...], state: SelectionState) -> SelectionProposal | None:
        admitted = tuple(candidate for candidate in candidates if all(rule(candidate) for rule in self.filters))
        if not admitted:
            return None
        for ranker in reversed(self.rankers):
            # One ranker owns the runtime contract that all of its keys are mutually orderable.
            admitted = tuple(sorted(admitted, key=ranker))  # ty: ignore[no-matching-overload]
        proposal = self.strategy.propose(admitted, state)
        if proposal is None:
            return None
        if proposal.binding not in admitted:
            raise ValueError("selection strategy proposed a binding outside the admitted candidates")
        if proposal.prior_state != state:
            raise ValueError("selection strategy proposal does not carry the pipeline's prior state")
        return proposal

    def fold_committed(self, state: SelectionState, transition: NetPath) -> SelectionState:
        return self.strategy.fold_committed(state, transition)


def fold_history(policy: SelectionPolicy, state: SelectionState, history: Iterable[Record]) -> SelectionState:
    """Fold exact selected+begun pairs; an orphan advances no policy state.

    Occurrence identity recovery, not this fold, accounts for every recorded
    selection id (including an orphan) and therefore never mints it again.
    """
    selected: dict[int, CandidateSelected] = {}
    begun: dict[int, list[FiringBegun]] = {}
    for record in history:
        if isinstance(record, CandidateSelected):
            if record.occurrence in selected:
                raise ValueError(
                    f"selection replay divergence: duplicate CandidateSelected for occurrence {record.occurrence}"
                )
            selected[record.occurrence] = record
        elif isinstance(record, FiringBegun):
            begun.setdefault(record.occurrence, []).append(record)
    for occurrence, selection in selected.items():
        boundaries = begun.get(occurrence, ())
        if len(boundaries) > 1:
            raise ValueError(f"selection replay divergence: duplicate FiringBegun for occurrence {occurrence}")
        if boundaries and boundaries[0].transition != selection.transition:
            raise ValueError(
                f"selection replay divergence: occurrence {occurrence} selected {selection.transition} "
                f"but began {boundaries[0].transition}"
            )
        if boundaries:
            state = policy.fold_committed(state, selection.transition)
    return state


def _cursor(state: SelectionState, size: int) -> int:
    if not isinstance(state, int) or isinstance(state, bool) or not 0 <= state < size:
        raise ValueError(f"invalid round-robin state: {state!r}")
    return state


__all__ = [
    "AdmissionFilter",
    "First",
    "Priority",
    "RoundRobin",
    "SelectionPipeline",
    "SelectionPolicy",
    "SelectionProposal",
    "SelectionState",
    "StableRanker",
    "fold_history",
]
