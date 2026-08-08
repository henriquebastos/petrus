from __future__ import annotations

from collections import Counter
from dataclasses import replace
from threading import RLock

import pytest

from petrus.agenticus.hands.conformance import ConformanceError, SevenStepEpisodePolicy
from petrus.agenticus.hands.contract import RejectionCategory, ToolError, ToolMethod, ToolResult
from petrus.agenticus.hands.gateway import (
    CallFence,
    GatewayCounters,
    HandsGateway,
    ShellOutcome,
    StagedWrite,
    TestOutcome as Outcome,
)
from petrus.agenticus.hands.grants import GrantLedger


class Adapter:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.target: dict[str, str] = {}
        self.close_on_stage: Fence | None = None

    def read(self, path: str) -> str:
        self.calls.append("read")
        return "message"

    def search(self, query: str, path: str) -> tuple[str, ...]:
        self.calls.append("search")
        return ("message.txt:1:message",)

    def shell(self, argv: tuple[str, ...], cwd: str) -> ShellOutcome:
        self.calls.append("shell")
        return ShellOutcome(0, "message", "", False)

    def stage_write(self, call_id: str, path: str, content: str) -> StagedWrite:
        self.calls.append("stage")
        self.target[f"stage:{call_id}"] = content
        if self.close_on_stage is not None:
            self.close_on_stage.value = replace(self.close_on_stage.value, open=False)
        return StagedWrite(call_id, path, "d" * 64)

    def commit_write(self, staged: StagedWrite) -> str:
        self.calls.append("commit")
        self.target[staged.path] = self.target.pop(f"stage:{staged.call_id}")
        return staged.digest

    def discard_write(self, staged: StagedWrite) -> None:
        self.calls.append("discard")
        self.target.pop(f"stage:{staged.call_id}", None)

    def run_test(self) -> Outcome:
        self.calls.append("test")
        return Outcome(True, "e" * 64)

    def discard_all_stages(self) -> int:
        stages = tuple(key for key in self.target if key.startswith("stage:"))
        for stage in stages:
            del self.target[stage]
        return len(stages)


class Fence:
    def __init__(self, value: CallFence | None = None) -> None:
        self.value = value or CallFence(True, False, 100)

    def snapshot(self) -> CallFence:
        return self.value


def request(
    *,
    suffix: str,
    episode_id: str,
    attachment_id: str,
    attachment_epoch: int,
    grant_epoch: int,
    method: str,
    params: dict[str, object],
) -> dict[str, object]:
    return {
        "version": 1,
        "call_id": f"{suffix}:{method}",
        "episode_id": episode_id,
        "attachment_id": attachment_id,
        "attachment_epoch": attachment_epoch,
        "grant_epoch": grant_epoch,
        "method": method,
        "params": params,
    }


def blocked_write(attachment_id: str, epoch: int) -> ToolResult:
    return ToolResult(
        call_id=f"blocked-{attachment_id}",
        attachment_id=attachment_id,
        epoch=epoch,
        ok=False,
        data=None,
        error=ToolError(RejectionCategory.WRITE, "no current write grant"),
    )


def run_episode(suffix: str, epoch: int, adapter: Adapter) -> tuple[dict[str, object], GatewayCounters]:
    attachment_id = f"attachment-{suffix}"
    ledger = GrantLedger(attachment_id, epoch)
    initial = ledger.open(
        [
            ToolMethod.WORKSPACE_READ,
            ToolMethod.WORKSPACE_SEARCH,
            ToolMethod.WORKSPACE_SHELL,
            ToolMethod.WORKSPACE_TEST,
        ],
        allowed_argv=[("/bin/cat", "message.txt")],
        deadline=90,
        max_calls=5,
    )
    fence = Fence()
    episode_id = f"episode-{suffix}"
    gateway = HandsGateway(
        episode_id=episode_id,
        adapter=adapter,
        grants=ledger,
        fence=fence,
        barrier=RLock(),
        clock=lambda: 1,
    )
    policy = SevenStepEpisodePolicy(
        attachment_id=attachment_id,
        attachment_epoch=epoch,
        expected_marker=f"ES049_APP_{suffix.upper()}_OK",
    )
    successful: Counter[ToolMethod] = Counter()

    policy.begin_turn()
    policy.append_observation()
    policy.observe(ToolMethod.WORKSPACE_WRITE, blocked_write(attachment_id, epoch))

    steps: tuple[tuple[ToolMethod, str, dict[str, object]], ...] = (
        (ToolMethod.WORKSPACE_READ, "workspace_read", {"path": "message.txt"}),
        (ToolMethod.WORKSPACE_SEARCH, "workspace_search", {"query": "message", "path": "message.txt"}),
        (ToolMethod.WORKSPACE_SHELL, "workspace_shell", {"argv": ["/bin/cat", "message.txt"], "cwd": "."}),
        (ToolMethod.WORKSPACE_WRITE, "workspace_write", {"path": "message.txt", "content": suffix}),
        (ToolMethod.WORKSPACE_TEST, "workspace_test", {}),
    )
    grant = initial
    for method, name, params in steps:
        policy.begin_turn()
        policy.append_observation()
        result = gateway.submit(
            request(
                suffix=f"{suffix}-{policy.turns}",
                episode_id=episode_id,
                attachment_id=attachment_id,
                attachment_epoch=epoch,
                grant_epoch=grant.grant_epoch,
                method=name,
                params=params,
            )
        )
        assert result.ok
        successful[method] += 1
        policy.observe(method, result)
        if policy.turns == 3:
            assert policy.write_grant_ready
            policy.note_grant_opened()
            grant = ledger.open(
                ToolMethod,
                writable_paths=["message.txt"],
                allowed_argv=[("/bin/cat", "message.txt")],
                deadline=90,
                max_calls=3,
            )

    policy.begin_turn()
    policy.append_observation()
    decision = policy.admit_marker(f"ES049_APP_{suffix.upper()}_OK")
    assert decision.admitted
    return (
        {
            "invocations": policy.turns,
            "appends": policy.appends,
            "blocked_write_turn": policy.blocked_write_turn,
            "grant_opened_turn": policy.grant_opened_turn,
            "finalized_turns": {method.value: policy.finalized_turn(method) for method in ToolMethod},
            "successful_tools": {method.value: successful[method] for method in ToolMethod},
            "marker_outcome": decision.outcome,
            "premature_markers": policy.premature_markers,
        },
        gateway.counters(),
    )


def sum_counters(counters: tuple[GatewayCounters, ...]) -> dict[str, object]:
    return {
        "requests": sum(counter.requests for counter in counters),
        "adapter_entries": sum(counter.adapter_entries for counter in counters),
        "stages": sum(counter.stages for counter in counters),
        "commits": sum(counter.commits for counter in counters),
        "stage_discards": sum(counter.stage_discards for counter in counters),
        "mutations": sum(counter.target_mutations for counter in counters),
        "rejections": dict(sum((Counter(counter.rejections) for counter in counters), start=Counter())),
    }


def run_negative_probe(adapter: Adapter) -> tuple[GatewayCounters, ...]:
    counters: list[GatewayCounters] = []

    def submit(
        category: RejectionCategory,
        *,
        capabilities: tuple[ToolMethod, ...],
        method: str,
        params: dict[str, object],
        request_changes: dict[str, object] | None = None,
        allowed_argv: tuple[tuple[str, ...], ...] = (),
        writable_paths: tuple[str, ...] = (),
        deadline: float = 90,
        clock: float = 1,
        close_on_stage: bool = False,
    ) -> None:
        attachment_id = f"probe-{category.value}"
        ledger = GrantLedger(attachment_id, 9)
        grant = ledger.open(
            capabilities,
            writable_paths=writable_paths,
            allowed_argv=allowed_argv,
            deadline=deadline,
            max_calls=1,
        )
        fence = Fence()
        episode_id = f"episode-{category.value}"
        gateway = HandsGateway(
            episode_id=episode_id,
            adapter=adapter,
            grants=ledger,
            fence=fence,
            barrier=RLock(),
            clock=lambda: clock,
        )
        payload = request(
            suffix=category.value,
            episode_id=episode_id,
            attachment_id=attachment_id,
            attachment_epoch=9,
            grant_epoch=grant.grant_epoch,
            method=method,
            params=params,
        )
        if request_changes:
            payload.update(request_changes)
        adapter.close_on_stage = fence if close_on_stage else None
        result = gateway.submit(payload)
        adapter.close_on_stage = None
        assert result.error and result.error.category is category
        counters.append(gateway.counters())

    submit(RejectionCategory.UNKNOWN, capabilities=(), method="future_tool", params={})
    submit(
        RejectionCategory.PATH,
        capabilities=(ToolMethod.WORKSPACE_READ,),
        method="workspace_read",
        params={"path": "../escape"},
    )
    submit(RejectionCategory.CAPABILITY, capabilities=(), method="workspace_read", params={"path": "message.txt"})
    submit(
        RejectionCategory.ARGV,
        capabilities=(ToolMethod.WORKSPACE_SHELL,),
        allowed_argv=(("/bin/cat", "message.txt"),),
        method="workspace_shell",
        params={"argv": ["/bin/echo", "message.txt"], "cwd": "."},
    )
    submit(RejectionCategory.WRITE, capabilities=(), method="workspace_write", params={"path": "x", "content": "x"})
    submit(
        RejectionCategory.DEADLINE,
        capabilities=(ToolMethod.WORKSPACE_READ,),
        method="workspace_read",
        params={"path": "message.txt"},
        deadline=5,
        clock=10,
    )
    submit(
        RejectionCategory.STALE_EPOCH,
        capabilities=(ToolMethod.WORKSPACE_READ,),
        method="workspace_read",
        params={"path": "message.txt"},
        request_changes={"attachment_epoch": 10},
    )
    submit(
        RejectionCategory.POST_FENCE,
        capabilities=(ToolMethod.WORKSPACE_WRITE,),
        writable_paths=("message.txt",),
        method="workspace_write",
        params={"path": "message.txt", "content": "late"},
        close_on_stage=True,
    )
    return tuple(counters)


def test_es049_two_episode_trace_and_gateway_report_are_exact() -> None:
    adapter = Adapter()
    e1, e1_counters = run_episode("e1", 1, adapter)
    e2, e2_counters = run_episode("e2", 2, adapter)
    negatives = run_negative_probe(adapter)
    aggregate = sum_counters((e1_counters, e2_counters, *negatives))
    report = {
        "episodes": {"e1": e1, "e2": e2},
        "total_appends": e1["appends"] + e2["appends"],
        "application_crossings": 10,
        "gateway": aggregate,
    }

    expected_episode = {
        "invocations": 7,
        "appends": 7,
        "blocked_write_turn": 1,
        "grant_opened_turn": 3,
        "finalized_turns": {
            "workspace_read": 2,
            "workspace_search": 3,
            "workspace_shell": 4,
            "workspace_write": 5,
            "workspace_test": 6,
        },
        "successful_tools": {method.value: 1 for method in ToolMethod},
        "marker_outcome": "episode_complete",
        "premature_markers": 0,
    }
    assert report == {
        "episodes": {"e1": expected_episode, "e2": expected_episode},
        "total_appends": 14,
        "application_crossings": 10,
        "gateway": {
            "requests": 18,
            "adapter_entries": 11,
            "stages": 3,
            "commits": 2,
            "stage_discards": 1,
            "mutations": 2,
            "rejections": {
                "capability": 1,
                "path": 1,
                "argv": 1,
                "write": 1,
                "unknown": 1,
                "deadline": 1,
                "stale_epoch": 1,
                "post_fence": 1,
            },
        },
    }


def test_premature_marker_is_a_step_and_never_crosses_hands() -> None:
    policy = SevenStepEpisodePolicy(
        attachment_id="attachment-probe",
        attachment_epoch=1,
        expected_marker="DONE",
    )
    policy.begin_turn()
    policy.append_observation()
    policy.observe(ToolMethod.WORKSPACE_WRITE, blocked_write("attachment-probe", 1))
    policy.begin_turn()
    policy.append_observation()
    decision = policy.admit_marker("DONE")
    assert {
        "invocations": policy.turns,
        "appends": policy.appends,
        "outcome": decision.outcome,
        "admitted": decision.admitted,
        "premature_markers": policy.premature_markers,
        "gateway_requests": 0,
    } == {
        "invocations": 2,
        "appends": 2,
        "outcome": "episode_step",
        "admitted": False,
        "premature_markers": 1,
        "gateway_requests": 0,
    }


@pytest.mark.parametrize("category", [RejectionCategory.ABORTED, RejectionCategory.DEADLINE])
def test_abort_and_deadline_fail_policy_closed_while_stale_results_are_ignored(
    category: RejectionCategory,
) -> None:
    policy = SevenStepEpisodePolicy(attachment_id="attachment", attachment_epoch=2, expected_marker="DONE")
    policy.begin_turn()
    stale = ToolResult("stale", "attachment", 1, False, None, ToolError(category, "call rejected"))
    policy.observe(ToolMethod.WORKSPACE_READ, stale)
    assert not policy.failed
    current = ToolResult("current", "attachment", 2, False, None, ToolError(category, "call rejected"))
    policy.observe(ToolMethod.WORKSPACE_READ, current)
    assert policy.failed and not policy.admit_marker("DONE").admitted


def test_turn_and_append_budgets_are_independently_finite() -> None:
    turns = SevenStepEpisodePolicy(
        attachment_id="attachment",
        attachment_epoch=1,
        expected_marker="DONE",
        max_turns=1,
    )
    turns.begin_turn()
    with pytest.raises(ConformanceError, match="turn budget"):
        turns.begin_turn()
    appends = SevenStepEpisodePolicy(
        attachment_id="attachment",
        attachment_epoch=1,
        expected_marker="DONE",
        max_appends=1,
    )
    appends.append_observation()
    with pytest.raises(ConformanceError, match="append budget"):
        appends.append_observation()
