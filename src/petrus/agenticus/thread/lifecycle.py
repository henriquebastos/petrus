"""Immutable Thread, Episode, and Turn lifecycle contracts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from petrus.agenticus.catalog.descriptor import DescriptorIdentity, DescriptorKind, _exact_object
from petrus.agenticus.program.descriptor import AgentProgramDescriptor
from petrus.agenticus.thread.continuation import (
    Continuation,
    ContinuationState,
    require_continuation_compatible,
)
from petrus.agenticus.thread.identity import EpisodeId, ThreadId, TurnId

_SCHEMA_VERSION = 1


def _positive_integer(value: object, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _nonnegative_integer(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def _identity_of_kind(value: object, kind: DescriptorKind, name: str) -> DescriptorIdentity:
    if not isinstance(value, DescriptorIdentity) or value.kind is not kind:
        raise TypeError(f"{name} must be a {kind.value} DescriptorIdentity")
    return value


def _same_continuation_revision(left: Continuation | None, right: Continuation | None) -> bool:
    if left is None or right is None:
        return left is right
    return replace(left, state=ContinuationState.AVAILABLE) == replace(
        right,
        state=ContinuationState.AVAILABLE,
    )


class ThreadState(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class EpisodeState(StrEnum):
    RUNNING = "running"
    CANCELLING = "cancelling"
    SETTLED = "settled"


class TurnState(StrEnum):
    RUNNING = "running"
    SETTLED = "settled"


class TurnOutcome(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INDETERMINATE = "indeterminate"


class EpisodeOutcome(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BUDGET_EXHAUSTED = "budget-exhausted"
    INDETERMINATE = "indeterminate"


class CancellationDisposition(StrEnum):
    REQUESTED = "requested"
    ALREADY_REQUESTED = "already-requested"
    TOO_LATE = "too-late"


class SettlementDisposition(StrEnum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"


class LifecycleTransitionError(ValueError):
    """A requested lifecycle transition is not valid from current state."""


class EpisodeBudgetExceeded(LifecycleTransitionError):
    """A Turn or accepted append would exceed the Episode budget."""

    def __init__(self, dimension: str) -> None:
        self.dimension = dimension
        super().__init__(f"Episode budget exhausted for {dimension}")


@dataclass(frozen=True)
class EpisodeBudget:
    """The exact progression bounds owned by an Episode."""

    max_turns: int
    max_accepted_appends: int

    def __post_init__(self) -> None:
        _positive_integer(self.max_turns, "Episode budget max_turns")
        _positive_integer(self.max_accepted_appends, "Episode budget max_accepted_appends")

    def to_data(self) -> dict[str, int]:
        return {
            "schema_version": _SCHEMA_VERSION,
            "max_turns": self.max_turns,
            "max_accepted_appends": self.max_accepted_appends,
        }

    @classmethod
    def from_data(cls, data: object) -> EpisodeBudget:
        data = _exact_object(
            data,
            {"schema_version", "max_turns", "max_accepted_appends"},
            "Episode budget requires its exact versioned fields",
        )
        if type(data["schema_version"]) is not int or data["schema_version"] != _SCHEMA_VERSION:
            raise ValueError(f"Episode budget schema_version must be integer {_SCHEMA_VERSION}")
        return cls(
            max_turns=_positive_integer(data["max_turns"], "Episode budget max_turns"),
            max_accepted_appends=_positive_integer(
                data["max_accepted_appends"],
                "Episode budget max_accepted_appends",
            ),
        )


@dataclass(frozen=True)
class Turn:
    """One progression step and only its provider-neutral lifecycle facts."""

    id: TurnId
    episode: EpisodeId
    ordinal: int
    state: TurnState = TurnState.RUNNING
    accepted_appends: int = 0
    outcome: TurnOutcome | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, TurnId):
            raise TypeError("Turn id must be TurnId")
        if not isinstance(self.episode, EpisodeId):
            raise TypeError("Turn episode must be EpisodeId")
        _positive_integer(self.ordinal, "Turn ordinal")
        if not isinstance(self.state, TurnState):
            raise TypeError("Turn state must be TurnState")
        _nonnegative_integer(self.accepted_appends, "Turn accepted_appends")
        if self.state is TurnState.RUNNING and self.outcome is not None:
            raise ValueError("a running Turn cannot have an outcome")
        if self.state is TurnState.SETTLED and not isinstance(self.outcome, TurnOutcome):
            raise ValueError("a settled Turn requires a TurnOutcome")

    def accept_append(self) -> Turn:
        if self.state is not TurnState.RUNNING:
            raise LifecycleTransitionError("accepted appends require a running Turn")
        return replace(self, accepted_appends=self.accepted_appends + 1)

    def settle(self, outcome: TurnOutcome) -> Turn:
        if not isinstance(outcome, TurnOutcome):
            raise TypeError("Turn settlement requires TurnOutcome")
        if self.state is TurnState.SETTLED:
            raise LifecycleTransitionError("Turn is already settled")
        return replace(self, state=TurnState.SETTLED, outcome=outcome)

    def to_data(self) -> dict[str, object]:
        return {
            "schema_version": _SCHEMA_VERSION,
            "id": self.id.to_data(),
            "episode": self.episode.to_data(),
            "ordinal": self.ordinal,
            "state": self.state.value,
            "accepted_appends": self.accepted_appends,
            "outcome": None if self.outcome is None else self.outcome.value,
        }

    @classmethod
    def from_data(cls, data: object) -> Turn:
        data = _exact_object(
            data,
            {"schema_version", "id", "episode", "ordinal", "state", "accepted_appends", "outcome"},
            "Turn requires its exact versioned lifecycle fields",
        )
        if type(data["schema_version"]) is not int or data["schema_version"] != _SCHEMA_VERSION:
            raise ValueError(f"Turn schema_version must be integer {_SCHEMA_VERSION}")
        try:
            state = TurnState(data["state"])
            outcome = None if data["outcome"] is None else TurnOutcome(data["outcome"])
        except (TypeError, ValueError) as error:
            raise ValueError("Turn state or outcome is not supported") from error
        return cls(
            id=TurnId.from_data(data["id"]),
            episode=EpisodeId.from_data(data["episode"]),
            ordinal=_positive_integer(data["ordinal"], "Turn ordinal"),
            state=state,
            accepted_appends=_nonnegative_integer(data["accepted_appends"], "Turn accepted_appends"),
            outcome=outcome,
        )


@dataclass(frozen=True)
class Episode:
    """One bounded execution with no workspace, process, or transcript custody."""

    id: EpisodeId
    thread: ThreadId
    program: DescriptorIdentity
    runtime: DescriptorIdentity
    budget: EpisodeBudget
    expected_continuation: DescriptorIdentity | None = None
    continuation: Continuation | None = None
    state: EpisodeState = EpisodeState.RUNNING
    turns: tuple[Turn, ...] = ()
    accepted_appends: int = 0
    settlement: EpisodeOutcome | None = None
    next_continuation: Continuation | None = None

    def __post_init__(self) -> None:
        self._validate_identities()
        turns = tuple(self.turns)
        if any(not isinstance(turn, Turn) or turn.episode != self.id for turn in turns):
            raise TypeError("Episode turns must be Turn values for this Episode")
        if len({turn.id for turn in turns}) != len(turns):
            raise ValueError("Episode Turn ids must be unique")
        if tuple(turn.ordinal for turn in turns) != tuple(range(1, len(turns) + 1)):
            raise ValueError("Episode Turn ordinals must be contiguous from one")
        if len(turns) > self.budget.max_turns:
            raise ValueError("Episode turns exceed max_turns")
        if sum(turn.accepted_appends for turn in turns) != self.accepted_appends:
            raise ValueError("Episode accepted_appends must equal its Turn accounting")
        if self.accepted_appends > self.budget.max_accepted_appends:
            raise ValueError("Episode accepted_appends exceed budget")
        running_turns = tuple(turn for turn in turns if turn.state is TurnState.RUNNING)
        if len(running_turns) > 1 or (running_turns and running_turns[-1] is not turns[-1]):
            raise ValueError("only the final Episode Turn may be running")
        object.__setattr__(self, "turns", turns)
        self._validate_state(running_turns)

    def _validate_identities(self) -> None:
        if not isinstance(self.id, EpisodeId):
            raise TypeError("Episode id must be EpisodeId")
        if not isinstance(self.thread, ThreadId):
            raise TypeError("Episode thread must be ThreadId")
        _identity_of_kind(self.program, DescriptorKind.PROGRAM, "Episode program")
        _identity_of_kind(self.runtime, DescriptorKind.RUNTIME, "Episode runtime")
        if not isinstance(self.budget, EpisodeBudget):
            raise TypeError("Episode budget must be EpisodeBudget")
        if self.expected_continuation is not None:
            _identity_of_kind(
                self.expected_continuation,
                DescriptorKind.CONTINUATION,
                "Episode expected_continuation",
            )
        for name, continuation in (("continuation", self.continuation), ("next_continuation", self.next_continuation)):
            if continuation is not None and (
                not isinstance(continuation, Continuation) or continuation.thread != self.thread
            ):
                raise TypeError(f"Episode {name} must be a Continuation for this Thread")
        if not isinstance(self.state, EpisodeState):
            raise TypeError("Episode state must be EpisodeState")
        _nonnegative_integer(self.accepted_appends, "Episode accepted_appends")

    def _validate_state(self, running_turns: tuple[Turn, ...]) -> None:
        if self.state is EpisodeState.SETTLED:
            self._validate_settled_state(running_turns)
            return
        if self.settlement is not None or self.next_continuation is not None:
            raise ValueError("an active Episode cannot have settlement output")
        if self.continuation is not None and self.continuation.state is not ContinuationState.IN_USE:
            raise ValueError("an active Episode input Continuation must be in use")

    def _validate_settled_state(self, running_turns: tuple[Turn, ...]) -> None:
        if not isinstance(self.settlement, EpisodeOutcome):
            raise ValueError("a settled Episode requires an EpisodeOutcome")
        if running_turns:
            raise ValueError("a settled Episode cannot have a running Turn")
        if self.continuation is not None and self.continuation.state is not ContinuationState.RETIRED:
            raise ValueError("a settled Episode input Continuation must be retired")
        self._validate_result_continuation()

    def _validate_result_continuation(self) -> None:
        if (
            self.settlement is EpisodeOutcome.COMPLETED
            and self.expected_continuation is not None
            and self.next_continuation is None
        ):
            raise ValueError("a completed Episode requires its declared result Continuation")
        if self.next_continuation is None:
            return
        if self.expected_continuation is None:
            raise ValueError("Episode program does not declare a result Continuation")
        if self.next_continuation.state is not ContinuationState.AVAILABLE:
            raise ValueError("an Episode result Continuation must be available")
        if self.next_continuation.descriptor.identity != self.expected_continuation:
            raise ValueError("Episode result Continuation descriptor does not match its program")
        if self.next_continuation.descriptor.program != self.program:
            raise ValueError("Episode result Continuation names another Agent Program")

    @property
    def active_turn(self) -> Turn | None:
        return self.turns[-1] if self.turns and self.turns[-1].state is TurnState.RUNNING else None

    @property
    def budget_exhausted(self) -> bool:
        return len(self.turns) >= self.budget.max_turns or self.accepted_appends >= self.budget.max_accepted_appends

    def start_turn(self, turn_id: TurnId) -> Episode:
        if self.state is not EpisodeState.RUNNING:
            raise LifecycleTransitionError("new Turns require a running Episode")
        if self.active_turn is not None:
            raise LifecycleTransitionError("an Episode may have only one running Turn")
        if len(self.turns) >= self.budget.max_turns:
            raise EpisodeBudgetExceeded("turns")
        if self.accepted_appends >= self.budget.max_accepted_appends:
            raise EpisodeBudgetExceeded("accepted_appends")
        if any(turn.id == turn_id for turn in self.turns):
            raise LifecycleTransitionError("Turn id is already present in this Episode")
        turn = Turn(turn_id, self.id, len(self.turns) + 1)
        return replace(self, turns=(*self.turns, turn))

    def accept_append(self, turn_id: TurnId) -> Episode:
        if self.state is not EpisodeState.RUNNING:
            raise LifecycleTransitionError("accepted appends require a running Episode")
        turn = self._require_active_turn(turn_id)
        if self.accepted_appends >= self.budget.max_accepted_appends:
            raise EpisodeBudgetExceeded("accepted_appends")
        return self._replace_turn(turn.accept_append(), accepted_appends=self.accepted_appends + 1)

    def settle_turn(self, turn_id: TurnId, outcome: TurnOutcome) -> Episode:
        turn = self._require_active_turn(turn_id)
        if self.state is EpisodeState.CANCELLING and outcome is TurnOutcome.COMPLETED:
            raise LifecycleTransitionError("a cancellation-winning Turn cannot complete")
        return self._replace_turn(turn.settle(outcome))

    def _require_active_turn(self, turn_id: TurnId) -> Turn:
        if not isinstance(turn_id, TurnId):
            raise TypeError("Turn transition id must be TurnId")
        turn = self.active_turn
        if turn is None or turn.id != turn_id:
            raise LifecycleTransitionError("Turn is not the running Turn of this Episode")
        return turn

    def _replace_turn(self, turn: Turn, *, accepted_appends: int | None = None) -> Episode:
        return replace(
            self,
            turns=(*self.turns[:-1], turn),
            accepted_appends=self.accepted_appends if accepted_appends is None else accepted_appends,
        )

    def request_cancellation(self) -> EpisodeCancellation:
        if self.state is EpisodeState.SETTLED:
            return EpisodeCancellation(self, CancellationDisposition.TOO_LATE)
        if self.state is EpisodeState.CANCELLING:
            return EpisodeCancellation(self, CancellationDisposition.ALREADY_REQUESTED)
        return EpisodeCancellation(replace(self, state=EpisodeState.CANCELLING), CancellationDisposition.REQUESTED)

    def settle(
        self,
        outcome: EpisodeOutcome,
        next_continuation: Continuation | None = None,
    ) -> EpisodeSettlement:
        if not isinstance(outcome, EpisodeOutcome):
            raise TypeError("Episode settlement requires EpisodeOutcome")
        if self.state is EpisodeState.SETTLED:
            if self.settlement is outcome and self.next_continuation == next_continuation:
                return EpisodeSettlement(self, SettlementDisposition.DUPLICATE)
            raise LifecycleTransitionError("Episode is already settled with a different outcome or Continuation")
        if self.active_turn is not None:
            raise LifecycleTransitionError("Episode cannot settle while a Turn is running")
        if outcome is EpisodeOutcome.COMPLETED and self.state is not EpisodeState.RUNNING:
            raise LifecycleTransitionError("cancellation won before completed settlement")
        if outcome is EpisodeOutcome.CANCELLED and self.state is not EpisodeState.CANCELLING:
            raise LifecycleTransitionError("cancelled settlement requires a cancellation request")
        if outcome is EpisodeOutcome.BUDGET_EXHAUSTED and (
            self.state is not EpisodeState.RUNNING or not self.budget_exhausted
        ):
            raise LifecycleTransitionError("budget-exhausted settlement requires an exhausted Episode budget")
        continuation = None if self.continuation is None else self.continuation.retire()
        episode = replace(
            self,
            state=EpisodeState.SETTLED,
            settlement=outcome,
            continuation=continuation,
            next_continuation=next_continuation,
        )
        return EpisodeSettlement(episode, SettlementDisposition.ACCEPTED)

    def to_data(self) -> dict[str, object]:
        return {
            "schema_version": _SCHEMA_VERSION,
            "id": self.id.to_data(),
            "thread": self.thread.to_data(),
            "program": self.program.to_data(),
            "runtime": self.runtime.to_data(),
            "budget": self.budget.to_data(),
            "expected_continuation": (
                None if self.expected_continuation is None else self.expected_continuation.to_data()
            ),
            "continuation": None if self.continuation is None else self.continuation.to_data(),
            "state": self.state.value,
            "turns": [turn.to_data() for turn in self.turns],
            "accepted_appends": self.accepted_appends,
            "settlement": None if self.settlement is None else self.settlement.value,
            "next_continuation": (None if self.next_continuation is None else self.next_continuation.to_data()),
        }

    @classmethod
    def from_data(cls, data: object) -> Episode:
        data = _exact_object(
            data,
            {
                "schema_version",
                "id",
                "thread",
                "program",
                "runtime",
                "budget",
                "expected_continuation",
                "continuation",
                "state",
                "turns",
                "accepted_appends",
                "settlement",
                "next_continuation",
            },
            "Episode requires its exact versioned lifecycle fields",
        )
        if type(data["schema_version"]) is not int or data["schema_version"] != _SCHEMA_VERSION:
            raise ValueError(f"Episode schema_version must be integer {_SCHEMA_VERSION}")
        turns = data["turns"]
        if not isinstance(turns, list):
            raise TypeError("Episode turns must be a JSON array")
        try:
            state = EpisodeState(data["state"])
            settlement = None if data["settlement"] is None else EpisodeOutcome(data["settlement"])
        except (TypeError, ValueError) as error:
            raise ValueError("Episode state or settlement is not supported") from error
        expected = data["expected_continuation"]
        continuation = data["continuation"]
        next_continuation = data["next_continuation"]
        return cls(
            id=EpisodeId.from_data(data["id"]),
            thread=ThreadId.from_data(data["thread"]),
            program=DescriptorIdentity.from_data(data["program"]),
            runtime=DescriptorIdentity.from_data(data["runtime"]),
            budget=EpisodeBudget.from_data(data["budget"]),
            expected_continuation=None if expected is None else DescriptorIdentity.from_data(expected),
            continuation=None if continuation is None else Continuation.from_data(continuation),
            state=state,
            turns=tuple(Turn.from_data(turn) for turn in turns),
            accepted_appends=_nonnegative_integer(data["accepted_appends"], "Episode accepted_appends"),
            settlement=settlement,
            next_continuation=(None if next_continuation is None else Continuation.from_data(next_continuation)),
        )


@dataclass(frozen=True)
class EpisodeCancellation:
    episode: Episode
    disposition: CancellationDisposition


@dataclass(frozen=True)
class EpisodeSettlement:
    episode: Episode
    disposition: SettlementDisposition


@dataclass(frozen=True)
class Thread:
    """Durable related-work lineage across sequential Episodes and runtimes."""

    id: ThreadId
    state: ThreadState = ThreadState.OPEN
    episodes: tuple[Episode, ...] = ()
    continuation: Continuation | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, ThreadId):
            raise TypeError("Thread id must be ThreadId")
        if not isinstance(self.state, ThreadState):
            raise TypeError("Thread state must be ThreadState")
        episodes = self._validated_episodes()
        active = tuple(episode for episode in episodes if episode.state is not EpisodeState.SETTLED)
        self._validate_continuation()
        self._validate_state(active)
        object.__setattr__(self, "episodes", episodes)

    def _validated_episodes(self) -> tuple[Episode, ...]:
        episodes = tuple(self.episodes)
        if any(not isinstance(episode, Episode) or episode.thread != self.id for episode in episodes):
            raise TypeError("Thread episodes must be Episode values for this Thread")
        if len({episode.id for episode in episodes}) != len(episodes):
            raise ValueError("Thread Episode ids must be unique")
        active = tuple(episode for episode in episodes if episode.state is not EpisodeState.SETTLED)
        if len(active) > 1 or (active and active[-1] is not episodes[-1]):
            raise ValueError("only the final Thread Episode may be active")
        for previous, current in zip(episodes, episodes[1:], strict=False):
            if not _same_continuation_revision(previous.next_continuation, current.continuation):
                raise ValueError("adjacent Thread Episodes must share one Continuation revision")
        output_ids = [episode.next_continuation.id for episode in episodes if episode.next_continuation is not None]
        if len(set(output_ids)) != len(output_ids):
            raise ValueError("Thread result Continuation ids must be unique")
        return episodes

    def _validate_continuation(self) -> None:
        if self.continuation is not None and (
            not isinstance(self.continuation, Continuation) or self.continuation.thread != self.id
        ):
            raise TypeError("Thread continuation must be a Continuation for this Thread")

    def _validate_state(self, active: tuple[Episode, ...]) -> None:
        if self.state is ThreadState.CLOSED:
            if active:
                raise ValueError("a closed Thread cannot have an active Episode")
            if self.continuation is not None and self.continuation.state is not ContinuationState.RETIRED:
                raise ValueError("a closed Thread Continuation must be retired")
            if self.episodes and not _same_continuation_revision(
                self.continuation,
                self.episodes[-1].next_continuation,
            ):
                raise ValueError("a closed Thread must retain its final Continuation revision")
        elif active:
            if self.continuation != active[-1].continuation:
                raise ValueError("an active Episode must own the Thread Continuation")
        else:
            if self.continuation is not None and self.continuation.state is not ContinuationState.AVAILABLE:
                raise ValueError("an open resting Thread Continuation must be available")
            if self.episodes and self.continuation != self.episodes[-1].next_continuation:
                raise ValueError("an open resting Thread must expose its final Continuation")

    @property
    def active_episode(self) -> Episode:
        if not self.episodes or self.episodes[-1].state is EpisodeState.SETTLED:
            raise LifecycleTransitionError("Thread has no active Episode")
        return self.episodes[-1]

    def start_episode(
        self,
        episode_id: EpisodeId,
        program: AgentProgramDescriptor,
        runtime: DescriptorIdentity,
        budget: EpisodeBudget,
    ) -> Thread:
        if self.state is not ThreadState.OPEN:
            raise LifecycleTransitionError("a closed Thread cannot start an Episode")
        if self.episodes and self.episodes[-1].state is not EpisodeState.SETTLED:
            raise LifecycleTransitionError("a Thread may have only one active Episode")
        if any(episode.id == episode_id for episode in self.episodes):
            raise LifecycleTransitionError("Episode id is already present in this Thread")
        if not isinstance(program, AgentProgramDescriptor):
            raise TypeError("Episode program must be AgentProgramDescriptor")
        descriptor = None if self.continuation is None else self.continuation.descriptor
        require_continuation_compatible(program, descriptor)
        continuation = None if self.continuation is None else self.continuation.claim()
        episode = Episode(
            id=episode_id,
            thread=self.id,
            program=program.identity,
            runtime=runtime,
            budget=budget,
            expected_continuation=program.produced_continuation,
            continuation=continuation,
        )
        return replace(self, episodes=(*self.episodes, episode), continuation=continuation)

    def start_turn(self, turn_id: TurnId) -> Thread:
        return self._replace_active_episode(self.active_episode.start_turn(turn_id))

    def accept_append(self, turn_id: TurnId) -> Thread:
        return self._replace_active_episode(self.active_episode.accept_append(turn_id))

    def settle_turn(self, turn_id: TurnId, outcome: TurnOutcome) -> Thread:
        return self._replace_active_episode(self.active_episode.settle_turn(turn_id, outcome))

    def request_cancellation(self) -> ThreadCancellation:
        if self.episodes and self.episodes[-1].state is EpisodeState.SETTLED:
            return ThreadCancellation(self, CancellationDisposition.TOO_LATE)
        cancellation = self.active_episode.request_cancellation()
        thread = self._replace_active_episode(cancellation.episode)
        return ThreadCancellation(thread, cancellation.disposition)

    def settle_episode(
        self,
        outcome: EpisodeOutcome,
        continuation: Continuation | None = None,
    ) -> ThreadSettlement:
        if self.episodes and self.episodes[-1].state is EpisodeState.SETTLED:
            retry = self.episodes[-1].settle(outcome, continuation)
            return ThreadSettlement(self, retry.disposition)
        episode = self.active_episode
        self._validate_result_continuation(episode, outcome, continuation)
        settlement = episode.settle(outcome, continuation)
        thread = replace(
            self,
            episodes=(*self.episodes[:-1], settlement.episode),
            continuation=continuation,
        )
        return ThreadSettlement(thread, settlement.disposition)

    def _validate_result_continuation(
        self,
        episode: Episode,
        outcome: EpisodeOutcome,
        continuation: Continuation | None,
    ) -> None:
        expected = episode.expected_continuation
        if outcome is EpisodeOutcome.COMPLETED and expected is not None and continuation is None:
            raise LifecycleTransitionError("completed Episode requires its declared result Continuation")
        if continuation is None:
            return
        if expected is None:
            raise LifecycleTransitionError("Agent Program does not declare a result Continuation")
        if continuation.thread != self.id:
            raise LifecycleTransitionError("result Continuation belongs to another Thread")
        if continuation.state is not ContinuationState.AVAILABLE:
            raise LifecycleTransitionError("result Continuation must be available")
        if continuation.descriptor.identity != expected:
            raise LifecycleTransitionError("result Continuation descriptor does not match Agent Program")
        if continuation.descriptor.program != episode.program:
            raise LifecycleTransitionError("result Continuation names another Agent Program")
        known_ids = {
            item.id
            for prior in self.episodes
            for item in (prior.continuation, prior.next_continuation)
            if item is not None
        }
        if continuation.id in known_ids:
            raise LifecycleTransitionError("result Continuation id is already present in this Thread")

    def _replace_active_episode(self, episode: Episode) -> Thread:
        return replace(self, episodes=(*self.episodes[:-1], episode), continuation=episode.continuation)

    def close(self) -> Thread:
        if self.state is ThreadState.CLOSED:
            return self
        if self.episodes and self.episodes[-1].state is not EpisodeState.SETTLED:
            raise LifecycleTransitionError("a Thread cannot close with an active Episode")
        continuation = None if self.continuation is None else self.continuation.retire()
        return replace(self, state=ThreadState.CLOSED, continuation=continuation)

    def to_data(self) -> dict[str, object]:
        return {
            "schema_version": _SCHEMA_VERSION,
            "id": self.id.to_data(),
            "state": self.state.value,
            "episodes": [episode.to_data() for episode in self.episodes],
            "continuation": None if self.continuation is None else self.continuation.to_data(),
        }

    @classmethod
    def from_data(cls, data: object) -> Thread:
        data = _exact_object(
            data,
            {"schema_version", "id", "state", "episodes", "continuation"},
            "Thread requires its exact versioned lifecycle fields",
        )
        if type(data["schema_version"]) is not int or data["schema_version"] != _SCHEMA_VERSION:
            raise ValueError(f"Thread schema_version must be integer {_SCHEMA_VERSION}")
        episodes = data["episodes"]
        if not isinstance(episodes, list):
            raise TypeError("Thread episodes must be a JSON array")
        try:
            state = ThreadState(data["state"])
        except (TypeError, ValueError) as error:
            raise ValueError("Thread state is not supported") from error
        continuation = data["continuation"]
        return cls(
            id=ThreadId.from_data(data["id"]),
            state=state,
            episodes=tuple(Episode.from_data(episode) for episode in episodes),
            continuation=None if continuation is None else Continuation.from_data(continuation),
        )


@dataclass(frozen=True)
class ThreadCancellation:
    thread: Thread
    disposition: CancellationDisposition


@dataclass(frozen=True)
class ThreadSettlement:
    thread: Thread
    disposition: SettlementDisposition
