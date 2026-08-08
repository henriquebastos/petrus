"""Thread lineage, Episode/Turn transitions, budgets, and terminal races."""

from __future__ import annotations

import json

import pytest

from petrus.agenticus.catalog.descriptor import DescriptorIdentity, DescriptorKind
from petrus.agenticus.program.descriptor import (
    AgentProgramDescriptor,
    ContinuationRequirement,
    ProgramOwnership,
)
from petrus.agenticus.thread.continuation import Continuation, ContinuationDescriptor, ContinuationState
from petrus.agenticus.thread.identity import ContinuationId, EpisodeId, ThreadId, TurnId
from petrus.agenticus.thread.lifecycle import (
    CancellationDisposition,
    EpisodeBudget,
    EpisodeBudgetExceeded,
    EpisodeOutcome,
    EpisodeState,
    LifecycleTransitionError,
    SettlementDisposition,
    Thread,
    ThreadState,
    TurnOutcome,
    TurnState,
)


def identity(kind: DescriptorKind, name: str) -> DescriptorIdentity:
    return DescriptorIdentity(kind, name, 1)


PROGRAM_ID = identity(DescriptorKind.PROGRAM, "harness.pi-core")
CONTINUATION_IDENTITY = identity(DescriptorKind.CONTINUATION, "pi.core-context")
PROGRAM = AgentProgramDescriptor(
    identity=PROGRAM_ID,
    ownership=ProgramOwnership.HARNESS,
    accepted_continuations=(ContinuationRequirement(CONTINUATION_IDENTITY, PROGRAM_ID),),
    produced_continuation=CONTINUATION_IDENTITY,
)
CONTINUATION_DESCRIPTOR = ContinuationDescriptor(CONTINUATION_IDENTITY, PROGRAM_ID)
BUDGET = EpisodeBudget(max_turns=2, max_accepted_appends=2)


def test_lifecycle_identities_are_serializable_but_not_interchangeable() -> None:
    identities = (
        ThreadId("same-value"),
        ContinuationId("same-value"),
        EpisodeId("same-value"),
        TurnId("same-value"),
    )

    assert len(set(identities)) == 4
    assert [type(value).from_data(value.to_data()) for value in identities] == list(identities)
    with pytest.raises(ValueError, match="trimmed"):
        ThreadId(" thread ")


def test_one_thread_spans_runtime_replacement_without_absorbing_neighboring_identities() -> None:
    thread = Thread(ThreadId("thread-durable"))
    thread = thread.start_episode(
        EpisodeId("episode-gondolin"),
        PROGRAM,
        identity(DescriptorKind.RUNTIME, "pi.gondolin"),
        BUDGET,
    )
    thread = thread.start_turn(TurnId("turn-gondolin-1"))
    thread = thread.accept_append(TurnId("turn-gondolin-1"))
    thread = thread.settle_turn(TurnId("turn-gondolin-1"), TurnOutcome.COMPLETED)
    first_continuation = Continuation(
        ContinuationId("continuation-1"),
        thread.id,
        CONTINUATION_DESCRIPTOR,
        "pi-store:key-1",
    )
    thread = thread.settle_episode(EpisodeOutcome.COMPLETED, first_continuation).thread

    thread = thread.start_episode(
        EpisodeId("episode-e2b"),
        PROGRAM,
        identity(DescriptorKind.RUNTIME, "pi.e2b"),
        BUDGET,
    )
    assert thread.continuation is not None
    assert thread.continuation.state is ContinuationState.IN_USE
    thread = thread.start_turn(TurnId("turn-e2b-1"))
    thread = thread.accept_append(TurnId("turn-e2b-1"))
    thread = thread.settle_turn(TurnId("turn-e2b-1"), TurnOutcome.COMPLETED)
    second_continuation = Continuation(
        ContinuationId("continuation-2"),
        thread.id,
        CONTINUATION_DESCRIPTOR,
        "pi-store:key-2",
    )
    thread = thread.settle_episode(EpisodeOutcome.COMPLETED, second_continuation).thread.close()

    restored = Thread.from_data(thread.to_data())
    encoded = json.dumps(restored.to_data(), sort_keys=True)
    assert restored == thread
    assert restored.state is ThreadState.CLOSED
    assert [episode.runtime.name for episode in restored.episodes] == ["pi.gondolin", "pi.e2b"]
    assert [episode.accepted_appends for episode in restored.episodes] == [1, 1]
    assert restored.continuation is not None
    assert restored.continuation.state is ContinuationState.RETIRED
    assert all(
        forbidden not in encoded
        for forbidden in (
            "workspace",
            "agent_home",
            "process",
            "territory",
            "provider_session",
            "transcript",
            "history",
        )
    )


def test_active_episode_and_turn_round_trip_with_an_in_use_continuation() -> None:
    continuation = Continuation(
        ContinuationId("continuation-active"),
        ThreadId("thread-active"),
        CONTINUATION_DESCRIPTOR,
        "pi-store:active",
    )
    thread = Thread(ThreadId("thread-active"), continuation=continuation)
    thread = thread.start_episode(
        EpisodeId("episode-active"),
        PROGRAM,
        identity(DescriptorKind.RUNTIME, "pi.application-owned"),
        BUDGET,
    ).start_turn(TurnId("turn-active"))

    restored = Thread.from_data(thread.to_data())

    assert restored == thread
    assert restored.continuation is not None
    assert restored.continuation.state is ContinuationState.IN_USE
    assert restored.active_episode.turns[-1].state is TurnState.RUNNING


def test_turn_and_append_budgets_fail_before_an_unaccounted_transition() -> None:
    append_limited = Thread(ThreadId("append-limited")).start_episode(
        EpisodeId("episode-append-limited"),
        PROGRAM,
        identity(DescriptorKind.RUNTIME, "pi.application-owned"),
        EpisodeBudget(max_turns=2, max_accepted_appends=1),
    )
    append_limited = append_limited.start_turn(TurnId("turn-1")).accept_append(TurnId("turn-1"))
    before = append_limited
    with pytest.raises(EpisodeBudgetExceeded, match="accepted_appends"):
        append_limited.accept_append(TurnId("turn-1"))
    assert append_limited == before
    append_limited = append_limited.settle_turn(TurnId("turn-1"), TurnOutcome.COMPLETED)
    with pytest.raises(EpisodeBudgetExceeded, match="accepted_appends"):
        append_limited.start_turn(TurnId("turn-after-append-budget"))
    append_limited = append_limited.settle_episode(EpisodeOutcome.BUDGET_EXHAUSTED).thread
    assert append_limited.episodes[-1].settlement is EpisodeOutcome.BUDGET_EXHAUSTED

    turn_limited = Thread(ThreadId("turn-limited")).start_episode(
        EpisodeId("episode-turn-limited"),
        AgentProgramDescriptor(identity=PROGRAM_ID, ownership=ProgramOwnership.HARNESS),
        identity(DescriptorKind.RUNTIME, "pi.application-owned"),
        EpisodeBudget(max_turns=1, max_accepted_appends=2),
    )
    turn_limited = turn_limited.start_turn(TurnId("only-turn"))
    turn_limited = turn_limited.settle_turn(TurnId("only-turn"), TurnOutcome.COMPLETED)
    with pytest.raises(EpisodeBudgetExceeded, match="turns"):
        turn_limited.start_turn(TurnId("too-many"))
    not_exhausted = Thread(ThreadId("not-exhausted")).start_episode(
        EpisodeId("episode-not-exhausted"),
        AgentProgramDescriptor(identity=PROGRAM_ID, ownership=ProgramOwnership.HARNESS),
        identity(DescriptorKind.RUNTIME, "pi.application-owned"),
        BUDGET,
    )
    with pytest.raises(LifecycleTransitionError, match="requires an exhausted"):
        not_exhausted.settle_episode(EpisodeOutcome.BUDGET_EXHAUSTED)


def test_cancellation_and_settlement_races_are_first_terminal_fact_wins() -> None:
    running = (
        Thread(ThreadId("race-settlement"))
        .start_episode(
            EpisodeId("episode-race-settlement"),
            AgentProgramDescriptor(identity=PROGRAM_ID, ownership=ProgramOwnership.HARNESS),
            identity(DescriptorKind.RUNTIME, "pi.application-owned"),
            BUDGET,
        )
        .active_episode
    )
    settled = running.settle(EpisodeOutcome.COMPLETED)
    assert settled.disposition is SettlementDisposition.ACCEPTED
    late_cancel = settled.episode.request_cancellation()
    assert late_cancel.disposition is CancellationDisposition.TOO_LATE
    assert late_cancel.episode.settlement is EpisodeOutcome.COMPLETED
    assert settled.episode.settle(EpisodeOutcome.COMPLETED).disposition is SettlementDisposition.DUPLICATE
    with pytest.raises(LifecycleTransitionError, match="already settled"):
        settled.episode.settle(EpisodeOutcome.FAILED)

    thread_settled = (
        Thread(ThreadId("thread-race-settlement"))
        .start_episode(
            EpisodeId("thread-episode-race-settlement"),
            AgentProgramDescriptor(identity=PROGRAM_ID, ownership=ProgramOwnership.HARNESS),
            identity(DescriptorKind.RUNTIME, "pi.application-owned"),
            BUDGET,
        )
        .settle_episode(EpisodeOutcome.COMPLETED)
    )
    assert thread_settled.thread.request_cancellation().disposition is CancellationDisposition.TOO_LATE
    duplicate = thread_settled.thread.settle_episode(EpisodeOutcome.COMPLETED)
    assert duplicate.disposition is SettlementDisposition.DUPLICATE
    assert duplicate.thread == thread_settled.thread
    with pytest.raises(LifecycleTransitionError, match="already settled"):
        thread_settled.thread.settle_episode(EpisodeOutcome.FAILED)

    thread = Thread(ThreadId("race-cancellation")).start_episode(
        EpisodeId("episode-race-cancellation"),
        AgentProgramDescriptor(identity=PROGRAM_ID, ownership=ProgramOwnership.HARNESS),
        identity(DescriptorKind.RUNTIME, "pi.application-owned"),
        BUDGET,
    )
    cancellation = thread.request_cancellation()
    assert cancellation.disposition is CancellationDisposition.REQUESTED
    assert cancellation.thread.active_episode.state is EpisodeState.CANCELLING
    cancelled = cancellation.thread.settle_episode(EpisodeOutcome.CANCELLED)
    assert cancelled.disposition is SettlementDisposition.ACCEPTED
    assert cancelled.thread.episodes[-1].settlement is EpisodeOutcome.CANCELLED

    active_turn = (
        Thread(ThreadId("race-active-turn"))
        .start_episode(
            EpisodeId("episode-race-active-turn"),
            AgentProgramDescriptor(identity=PROGRAM_ID, ownership=ProgramOwnership.HARNESS),
            identity(DescriptorKind.RUNTIME, "pi.application-owned"),
            BUDGET,
        )
        .start_turn(TurnId("turn-race-active"))
    )
    cancelling = active_turn.request_cancellation().thread
    with pytest.raises(LifecycleTransitionError, match="cancellation-winning Turn"):
        cancelling.settle_turn(TurnId("turn-race-active"), TurnOutcome.COMPLETED)
    cancelling = cancelling.settle_turn(TurnId("turn-race-active"), TurnOutcome.CANCELLED)
    with pytest.raises(LifecycleTransitionError, match="cancellation won"):
        cancelling.settle_episode(EpisodeOutcome.COMPLETED)


def test_settlement_and_deserialization_require_the_declared_continuation() -> None:
    thread = Thread(ThreadId("thread-required-output")).start_episode(
        EpisodeId("episode-required-output"),
        PROGRAM,
        identity(DescriptorKind.RUNTIME, "pi.application-owned"),
        BUDGET,
    )
    with pytest.raises(LifecycleTransitionError, match="requires its declared"):
        thread.settle_episode(EpisodeOutcome.COMPLETED)

    continuation = Continuation(
        ContinuationId("continuation-required-output"),
        thread.id,
        CONTINUATION_DESCRIPTOR,
        "pi-store:required-output",
    )
    settled = thread.settle_episode(EpisodeOutcome.COMPLETED, continuation).thread
    corrupted = settled.to_data()
    corrupted["continuation"] = None
    episodes = corrupted["episodes"]
    assert isinstance(episodes, list) and isinstance(episodes[0], dict)
    episodes[0]["next_continuation"] = None

    with pytest.raises(ValueError, match="requires its declared"):
        Thread.from_data(corrupted)


def test_failed_episode_retires_its_input_revision_and_may_publish_a_new_one() -> None:
    input_continuation = Continuation(
        ContinuationId("continuation-input"),
        ThreadId("thread-failed"),
        CONTINUATION_DESCRIPTOR,
        "pi-store:same-native-state",
    )
    running = Thread(ThreadId("thread-failed"), continuation=input_continuation).start_episode(
        EpisodeId("episode-failed"),
        PROGRAM,
        identity(DescriptorKind.RUNTIME, "pi.application-owned"),
        BUDGET,
    )
    output_continuation = Continuation(
        ContinuationId("continuation-output"),
        running.id,
        CONTINUATION_DESCRIPTOR,
        "pi-store:same-native-state",
    )

    failed = running.settle_episode(EpisodeOutcome.FAILED, output_continuation).thread

    assert failed.episodes[-1].continuation is not None
    assert failed.episodes[-1].continuation.state is ContinuationState.RETIRED
    assert failed.continuation == output_continuation


def test_provider_shaped_fake_traces_never_enter_the_common_lifecycle() -> None:
    traces: dict[ProgramOwnership, object] = {
        ProgramOwnership.PROVIDER: {"amp_events": [{"type": "assistant", "blocks": [{"text": "done"}]}]},
        ProgramOwnership.HARNESS: [{"role": "assistant", "content": [{"type": "text", "text": "done"}]}],
        ProgramOwnership.NET: (("transition", "append"), {"tokens": {"accepted": 1}}),
    }
    adapter_custody: list[object] = []

    for index, (ownership, trace) in enumerate(traces.items(), start=1):
        descriptor = AgentProgramDescriptor(
            identity=identity(DescriptorKind.PROGRAM, f"fake.{ownership.value}"),
            ownership=ownership,
        )
        thread = Thread(ThreadId(f"thread-{index}"))
        thread = thread.start_episode(
            EpisodeId(f"episode-{index}"),
            descriptor,
            identity(DescriptorKind.RUNTIME, f"runtime.{index}"),
            EpisodeBudget(max_turns=1, max_accepted_appends=1),
        )
        thread = thread.start_turn(TurnId(f"turn-{index}"))
        adapter_custody.append(trace)
        thread = thread.accept_append(TurnId(f"turn-{index}"))
        thread = thread.settle_turn(TurnId(f"turn-{index}"), TurnOutcome.COMPLETED)
        thread = thread.settle_episode(EpisodeOutcome.COMPLETED).thread

        lifecycle_data = json.dumps(thread.to_data(), sort_keys=True)
        assert thread.episodes[-1].turns == (thread.episodes[-1].turns[0],)
        assert thread.episodes[-1].turns[0].state is TurnState.SETTLED
        assert thread.episodes[-1].accepted_appends == 1
        assert all(key not in lifecycle_data for key in ("amp_events", "role", "transition", "tokens"))

    assert adapter_custody == list(traces.values())
