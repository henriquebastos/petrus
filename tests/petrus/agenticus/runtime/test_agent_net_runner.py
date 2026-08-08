from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from petrus.agenticus.attachment.binding import BindingSettlement
from petrus.agenticus.attachment.episode import EpisodeAttachment
from petrus.agenticus.catalog.descriptor import CapabilityDescriptor
from petrus.agenticus.catalog.resolution import ResolutionSnapshot
from petrus.agenticus.hands.contract import CAPABILITY_SCOPED_HANDS, ToolMethod
from petrus.agenticus.hands.gateway import ShellOutcome, StagedWrite, TestOutcome as HandsTestOutcome
from petrus.agenticus.program.agent_net import (
    HANDS_ACTIVITY,
    MODEL_PHASE_ACTIVITY,
    LoopState,
    ModelSettlement,
    Proposal,
    StopReason,
)
from petrus.agenticus.runtime.agent_net_runner import (
    AgentNetRunner,
    AgentNetRunnerError,
    HaltCode,
    JsonAgentNetThreadRepository,
)
from petrus.agenticus.runtime.profiles import AGENT_AS_NET_A5_LOCAL, TerritoryProfile, territory_identity
from petrus.agenticus.thread.identity import EpisodeId, ThreadId
from petrus.agenticus.thread.lifecycle import EpisodeOutcome, Thread, TurnOutcome
from petrus.impetus.history import ActivityCompleted, ActivityRequested
from petrus.motus.activity import ActivityInvocation

DIGEST = "a" * 64


@dataclass
class Binding:
    events: list[str] = field(default_factory=list)
    binding_kind: str = "local-runner"

    def cancel(self, reason: str) -> None:
        self.events.append("cancel")

    def export_archive(self) -> bytes:
        self.events.append("export")
        return b"archive"

    def settle(self) -> BindingSettlement:
        self.events.append("destroy")
        return BindingSettlement(self.binding_kind, "clean", True)


class Workspace:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def read(self, path: str) -> str:
        self.calls.append("read")
        return "safe"

    def search(self, query: str, path: str) -> tuple[str, ...]:
        self.calls.append("search")
        return ("match",)

    def shell(self, argv: tuple[str, ...], cwd: str) -> ShellOutcome:
        self.calls.append("shell")
        return ShellOutcome(0, "safe", "", False)

    def stage_write(self, call_id: str, path: str, content: str) -> StagedWrite:
        self.calls.append("stage")
        return StagedWrite(call_id, path, "b" * 64)

    def commit_write(self, staged: StagedWrite) -> str:
        self.calls.append("commit")
        return staged.digest

    def discard_write(self, staged: StagedWrite) -> None:
        self.calls.append("discard")

    def run_test(self) -> HandsTestOutcome:
        self.calls.append("test")
        return HandsTestOutcome(True, "c" * 64)

    def discard_all_stages(self) -> int:
        self.calls.append("cleanup")
        return 0


class Model:
    def __init__(self, plans: list[tuple[StopReason, tuple[Proposal, ...]]]) -> None:
        self.plans = iter(plans)
        self.calls: list[LoopState] = []

    def __call__(self, invocation: ActivityInvocation, *, context) -> object:
        assert invocation.activity == MODEL_PHASE_ACTIVITY
        state = LoopState.from_data(invocation.input)
        self.calls.append(state)
        context.heartbeat(details={"phase": "model"})
        stop, proposals = next(self.plans)
        return ModelSettlement(
            state,
            stop,
            DIGEST,
            f"output-{state.phase}",
            f"continuation-{state.phase}",
            proposals,
        ).to_data()


class FailingModel:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, invocation: ActivityInvocation, *, context) -> object:
        self.calls += 1
        raise RuntimeError("provider-failed")


def attachment(
    *,
    methods: tuple[ToolMethod, ...] = (ToolMethod.WORKSPACE_READ,),
    max_calls: int = 4,
    identity: str = "attachment-1",
) -> tuple[EpisodeAttachment, Binding]:
    binding = Binding()
    snapshot = ResolutionSnapshot(
        1,
        (
            AGENT_AS_NET_A5_LOCAL,
            CAPABILITY_SCOPED_HANDS,
            CapabilityDescriptor(territory_identity(TerritoryProfile.LOCAL), frozenset()),
        ),
    )
    current = EpisodeAttachment(
        episode_id=EpisodeId("episode-1"),
        snapshot=snapshot,
        binding=binding,
        attachment_id=identity,
        deadline=100,
        clock=lambda: 1,
    )
    current.grants().open(
        methods,
        writable_paths=("out.txt",),
        allowed_argv=(("printf", "ok"),),
        deadline=90,
        max_calls=max_calls,
    )
    return current, binding


def initial(
    *,
    capabilities: tuple[str, ...] = ("workspace_read",),
    phase_limit: int = 3,
    tool_limit: int = 4,
) -> LoopState:
    return LoopState(
        "episode-1",
        "turn-1",
        1,
        phase_limit,
        0,
        tool_limit,
        None,
        None,
        1,
        capabilities,
    )


def create(
    root: Path,
    model: Model,
    current: EpisodeAttachment,
    workspace: Workspace,
    *,
    state: LoopState | None = None,
) -> AgentNetRunner:
    return AgentNetRunner.create(
        root,
        instance_id="agent-net-1",
        thread=Thread(ThreadId("thread-1")),
        initial=state or initial(),
        attachment=current,
        model_activity=model,
        hands_adapter=workspace,
    )


def test_local_runner_uses_history_for_order_and_projects_thread_idempotently(tmp_path: Path) -> None:
    current, binding = attachment()
    workspace = Workspace()
    model = Model(
        [
            (StopReason.TOOL_USE, (Proposal("read-1", "workspace_read", {"path": "README.md"}),)),
            (StopReason.STOP, ()),
        ]
    )
    runner = create(tmp_path, model, current, workspace)

    projection = runner.drain()

    assert projection.settled and projection.terminal is not None
    assert projection.terminal.code.value == "completed"
    assert [(item.output_reference, item.continuation_reference) for item in projection.appends] == [
        ("output-1", "continuation-1"),
        ("output-2", "continuation-2"),
    ]
    assert [item.call_id for item in projection.hands] == ["read-1"]
    episode = projection.thread.episodes[-1]
    assert episode.accepted_appends == 2
    assert episode.turns[-1].outcome is TurnOutcome.COMPLETED
    assert episode.settlement is EpisodeOutcome.COMPLETED
    assert episode.next_continuation is not None
    assert episode.next_continuation.state_reference == "continuation-2"
    assert workspace.calls == ["read", "cleanup"]
    assert binding.events == ["export", "destroy"]
    requested = [record.activity for record in runner.engine.records if isinstance(record, ActivityRequested)]
    assert requested == [MODEL_PHASE_ACTIVITY, HANDS_ACTIVITY, MODEL_PHASE_ACTIVITY]
    assert len([record for record in runner.engine.records if isinstance(record, ActivityCompleted)]) == 3

    durable = JsonAgentNetThreadRepository(tmp_path / "thread.json").load()
    assert durable == projection
    thread_text = (tmp_path / "thread.json").read_text()
    thread_value = json.loads(thread_text)
    assert "attachment" not in json.dumps(thread_value["thread"])
    assert thread_value["attachment"]["attachment_id"] == "attachment-1"
    assert "transcript" not in thread_text
    runner.close()

    reloaded = AgentNetRunner.load(
        tmp_path,
        attachment=current,
        model_activity=Model([]),
        hands_adapter=workspace,
    )
    assert reloaded.projection == projection
    with pytest.raises(AgentNetRunnerError, match="cannot advance"):
        reloaded.advance()
    reloaded.close()


def test_quiescent_reconstruction_projects_unobserved_completion_without_redispatch(tmp_path: Path) -> None:
    current, _ = attachment()
    workspace = Workspace()
    first_model = Model([(StopReason.STOP, ())])
    first = create(tmp_path, first_model, current, workspace)
    first.engine.advance()  # request and execute exactly once; result is buffered outside History
    first.engine.advance()  # commit ActivityCompleted and deterministic firing; skip Thread projection to mimic death
    assert first.projection.appends == ()
    assert first.engine.in_flight == ()
    first.close()

    replacement = Model([])
    resumed = AgentNetRunner.load(
        tmp_path,
        attachment=current,
        model_activity=replacement,
        hands_adapter=workspace,
    )

    assert len(resumed.projection.appends) == 1
    assert replacement.calls == []
    resumed.drain()
    assert resumed.thread.episodes[-1].settlement is EpisodeOutcome.COMPLETED
    assert replacement.calls == []
    resumed.close()


def test_reconstruction_finishes_thread_projection_after_attachment_settled_before_save(tmp_path: Path) -> None:
    current, binding = attachment()
    workspace = Workspace()
    runner = create(tmp_path, Model([(StopReason.STOP, ())]), current, workspace)
    runner.advance()
    runner.advance()
    original = runner.repository

    class FailingRepository:
        def load(self):
            return original.load()

        def save(self, expected, value) -> None:
            if value.terminal is not None:
                raise OSError("injected final Thread save refusal")
            original.save(expected, value)

    runner.repository = FailingRepository()
    with pytest.raises(OSError, match="injected final"):
        runner.advance()
    assert current.settled
    assert binding.events == ["export", "destroy"]
    runner.close()

    resumed = AgentNetRunner.load(
        tmp_path,
        attachment=current,
        model_activity=Model([]),
        hands_adapter=workspace,
    )

    assert resumed.settled
    assert resumed.projection.terminal is not None
    assert resumed.thread.episodes[-1].settlement is EpisodeOutcome.COMPLETED
    assert binding.events == ["export", "destroy"]
    resumed.close()


def test_reconstructed_in_flight_model_is_indeterminate_before_first_advance(tmp_path: Path) -> None:
    current, binding = attachment()
    workspace = Workspace()
    paid = Model([(StopReason.STOP, ())])
    first = create(tmp_path, paid, current, workspace)
    first.advance()
    assert len(paid.calls) == 1
    assert first.engine.in_flight
    first.close()

    forbidden = Model([])
    resumed = AgentNetRunner.load(
        tmp_path,
        attachment=current,
        model_activity=forbidden,
        hands_adapter=workspace,
    )

    assert resumed.settled
    assert resumed.projection.halt is not None
    assert resumed.projection.halt.code is HaltCode.INDETERMINATE
    assert resumed.projection.halt.activity == MODEL_PHASE_ACTIVITY
    assert resumed.thread.episodes[-1].turns[-1].outcome is TurnOutcome.INDETERMINATE
    assert resumed.thread.episodes[-1].settlement is EpisodeOutcome.INDETERMINATE
    assert forbidden.calls == [] and workspace.calls == []
    assert binding.events == ["cancel", "export", "destroy"]
    with pytest.raises(AgentNetRunnerError, match="cannot advance"):
        resumed.advance()
    resumed.close()


def test_reconstructed_in_flight_hands_is_indeterminate_without_a_second_crossing(tmp_path: Path) -> None:
    current, binding = attachment()
    workspace = Workspace()
    model = Model([(StopReason.TOOL_USE, (Proposal("read-1", "workspace_read", {"path": "README.md"}),))])
    first = create(tmp_path, model, current, workspace)
    while not (
        first.engine.in_flight
        and first.engine.in_flight[0].invocation is not None
        and first.engine.in_flight[0].invocation.activity == HANDS_ACTIVITY
    ):
        first.advance()
    assert workspace.calls == ["read"]
    assert len(first.projection.appends) == 1
    first.close()

    before = list(workspace.calls)
    resumed = AgentNetRunner.load(
        tmp_path,
        attachment=current,
        model_activity=Model([]),
        hands_adapter=workspace,
    )

    assert resumed.projection.halt is not None
    assert resumed.projection.halt.code is HaltCode.INDETERMINATE
    assert resumed.projection.halt.activity == HANDS_ACTIVITY
    assert workspace.calls == [*before, "cleanup"]
    assert binding.events == ["cancel", "export", "destroy"]
    assert not any(
        isinstance(record, ActivityCompleted) and record.occurrence == resumed.projection.halt.occurrence
        for record in resumed.engine.records
    )
    resumed.close()


def test_in_process_activity_failure_settles_thread_and_attachment_before_propagating(tmp_path: Path) -> None:
    current, binding = attachment()
    workspace = Workspace()
    model = FailingModel()
    runner = AgentNetRunner.create(
        tmp_path,
        instance_id="agent-net-1",
        thread=Thread(ThreadId("thread-1")),
        initial=initial(),
        attachment=current,
        model_activity=model,
        hands_adapter=workspace,
    )
    runner.advance()

    with pytest.raises(RuntimeError, match="failed terminally"):
        runner.advance()

    assert model.calls == 1
    assert runner.projection.halt is not None
    assert runner.projection.halt.code is HaltCode.ACTIVITY_FAILED
    assert runner.projection.halt.activity == MODEL_PHASE_ACTIVITY
    assert runner.thread.episodes[-1].turns[-1].outcome is TurnOutcome.FAILED
    assert runner.thread.episodes[-1].settlement is EpisodeOutcome.FAILED
    assert binding.events == ["cancel", "export", "destroy"]
    assert workspace.calls == []
    runner.close()


def test_model_abort_cancels_attachment_and_projects_first_terminal_outcome(tmp_path: Path) -> None:
    current, binding = attachment()
    runner = create(tmp_path, Model([(StopReason.ABORTED, ())]), current, Workspace())

    projection = runner.drain()

    episode = projection.thread.episodes[-1]
    assert episode.turns[-1].outcome is TurnOutcome.CANCELLED
    assert episode.settlement is EpisodeOutcome.CANCELLED
    assert binding.events == ["cancel", "export", "destroy"]
    durable = JsonAgentNetThreadRepository(tmp_path / "thread.json").load()
    assert durable == projection
    runner.close()


def test_create_is_once_and_stale_attachment_or_grant_fails_before_history(tmp_path: Path) -> None:
    current, _ = attachment()
    runner = create(tmp_path, Model([(StopReason.STOP, ())]), current, Workspace())
    with pytest.raises(AgentNetRunnerError, match="already exists"):
        create(tmp_path, Model([]), current, Workspace())
    runner.close()

    other, _ = attachment(identity="attachment-other")
    with pytest.raises(AgentNetRunnerError, match="does not match"):
        AgentNetRunner.load(
            tmp_path,
            attachment=other,
            model_activity=Model([]),
            hands_adapter=Workspace(),
        )

    wrong, _ = attachment(methods=(ToolMethod.WORKSPACE_TEST,))
    with pytest.raises(AgentNetRunnerError, match="does not match"):
        create(
            tmp_path / "wrong",
            Model([]),
            wrong,
            Workspace(),
            state=initial(capabilities=("workspace_read",)),
        )
    assert not (tmp_path / "wrong" / "history.jsonl").exists()
    assert not (tmp_path / "wrong" / "thread.json").exists()


def test_mid_episode_grant_replacement_fails_before_another_engine_action(tmp_path: Path) -> None:
    current, _ = attachment()
    model = Model([(StopReason.STOP, ())])
    runner = create(tmp_path, model, current, Workspace())
    current.grants().open([ToolMethod.WORKSPACE_TEST], deadline=90, max_calls=4)

    with pytest.raises(AgentNetRunnerError, match="does not match"):
        runner.advance()

    assert model.calls == []
    assert not [record for record in runner.engine.records if isinstance(record, ActivityRequested)]
    runner.close()


def test_durable_projection_rejects_mutation_and_carries_no_private_payload(tmp_path: Path) -> None:
    current, _ = attachment()
    runner = create(tmp_path, Model([(StopReason.STOP, ())]), current, Workspace())
    repository = JsonAgentNetThreadRepository(tmp_path / "thread.json")
    stale = repository.load()
    assert stale is not None
    runner.advance()
    runner.advance()
    with pytest.raises(AgentNetRunnerError, match="changed concurrently"):
        repository.save(stale, stale)
    value = json.loads((tmp_path / "thread.json").read_text())
    assert set(value) == {
        "schema_version",
        "instance_id",
        "initial",
        "thread",
        "attachment",
        "appends",
        "hands",
        "terminal",
        "halt",
    }
    assert "private-model-output" not in json.dumps(value)
    runner.close()
