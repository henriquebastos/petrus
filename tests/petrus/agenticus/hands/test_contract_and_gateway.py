from __future__ import annotations

import json
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, RLock

import pytest

from petrus.agenticus.hands.contract import (
    CAPABILITY_SCOPED_HANDS,
    MAX_ARGV_PARTS,
    MAX_CONTENT_CHARS,
    RejectionCategory,
    ToolMethod,
    ToolCallConflict,
    ToolRequestRejected,
    parse_tool_request,
)
from petrus.agenticus.catalog.descriptor import DescriptorKind
from petrus.agenticus.hands.gateway import CallFence, HandsGateway, ShellOutcome, StagedWrite, TestOutcome as Outcome
from petrus.agenticus.hands.grants import CapabilityGrant, GrantLedger, GrantLedgerError


def request(method: str, params: dict[str, object], **changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "version": 1,
        "call_id": "call-1",
        "episode_id": "episode-1",
        "attachment_id": "attachment-1",
        "attachment_epoch": 1,
        "grant_epoch": 1,
        "method": method,
        "params": params,
    }
    value.update(changes)
    return value


@pytest.mark.parametrize(
    ("method", "params"),
    [
        ("workspace_read", {"path": "README.md"}),
        ("workspace_search", {"query": "needle", "path": ".hidden"}),
        ("workspace_shell", {"argv": ["printf", "ok"], "cwd": "."}),
        ("workspace_write", {"path": "out.txt", "content": "safe"}),
        ("workspace_test", {}),
    ],
)
def test_closed_v1_requests_are_exact_strict_and_json_safe(method: str, params: dict[str, object]) -> None:
    parsed = parse_tool_request(request(method, params))
    assert parsed.method.value == method
    json.dumps(request(method, params), allow_nan=False)
    with pytest.raises(ToolRequestRejected) as extra:
        parse_tool_request(request(method, params, extra=True))
    assert extra.value.category is RejectionCategory.SCHEMA


def test_capability_scoped_hands_descriptor_is_host_registerable_and_exact() -> None:
    assert CAPABILITY_SCOPED_HANDS.identity.kind is DescriptorKind.HANDS
    assert CAPABILITY_SCOPED_HANDS.identity.contract_version == 1
    assert CAPABILITY_SCOPED_HANDS.offers == {
        "hands.capability-scoped",
        "workspace.read",
        "workspace.search",
        "workspace.shell",
        "workspace.write",
        "workspace.test",
    }


@pytest.mark.parametrize("path", ["/absolute", "../escape", "a/../b", "a//b", "a\\b", "nul\0x"])
def test_paths_fail_closed_before_policy(path: str) -> None:
    with pytest.raises(ToolRequestRejected) as rejected:
        parse_tool_request(request("workspace_read", {"path": path}))
    assert rejected.value.category is RejectionCategory.PATH


def test_unknown_malformed_and_bounds_are_safe() -> None:
    with pytest.raises(ToolRequestRejected) as unknown:
        parse_tool_request(request("future_tool", {}))
    assert unknown.value.category is RejectionCategory.UNKNOWN
    with pytest.raises(ToolRequestRejected):
        parse_tool_request(request("workspace_shell", {"argv": ["x"] * (MAX_ARGV_PARTS + 1), "cwd": "."}))
    with pytest.raises(ToolRequestRejected):
        parse_tool_request(request("workspace_write", {"path": "x", "content": "x" * (MAX_CONTENT_CHARS + 1)}))
    canary = "SECRET-CANARY"
    with pytest.raises(ToolRequestRejected) as malformed:
        parse_tool_request({"call_id": canary})
    assert canary not in repr(malformed.value)


def test_workspace_write_accepts_exact_1024_character_boundary() -> None:
    assert MAX_CONTENT_CHARS == 1024
    parsed = parse_tool_request(request("workspace_write", {"path": "x", "content": "x" * 1024}))
    assert parsed.params.content == "x" * 1024

    with pytest.raises(ToolRequestRejected) as oversized:
        parse_tool_request(request("workspace_write", {"path": "x", "content": "x" * 1025}))
    assert oversized.value.category is RejectionCategory.WRITE
    with pytest.raises(ToolRequestRejected) as nul:
        parse_tool_request(request("workspace_write", {"path": "x", "content": "x\0y"}))
    assert nul.value.category is RejectionCategory.SCHEMA


def test_grants_are_exact_finite_monotonic_and_budgeted() -> None:
    ledger = GrantLedger("attachment-1", 1)
    first = ledger.open(
        [ToolMethod.WORKSPACE_READ],
        deadline=10.0,
        max_calls=1,
        writable_paths=(),
        allowed_argv=(),
    )
    assert ledger.consume(first.grant_epoch) is first
    with pytest.raises(GrantLedgerError):
        ledger.consume(first.grant_epoch)
    second = ledger.open(
        [ToolMethod.WORKSPACE_SHELL],
        deadline=11.0,
        max_calls=2,
        allowed_argv=[("printf", "ok")],
        writable_paths=(),
    )
    assert second.grant_epoch == first.grant_epoch + 1
    with pytest.raises(GrantLedgerError):
        ledger.consume(first.grant_epoch)
    current = ledger.current()
    with pytest.raises(ValueError):
        ledger.open([], deadline=float("inf"), max_calls=1)
    assert ledger.current() is current
    third = ledger.open([], deadline=12, max_calls=1)
    assert third.grant_epoch == second.grant_epoch + 1


def test_write_roots_are_bounded_and_denied_roots_take_precedence() -> None:
    adapter, fence = Adapter(), Fence()
    ledger = GrantLedger("attachment-1", 1)
    ledger.open(
        [ToolMethod.WORKSPACE_WRITE],
        writable_roots=["."],
        denied_writable_roots=[".git", ".petrus-hands-stage"],
        deadline=50,
        max_calls=3,
    )
    hands = HandsGateway(
        episode_id="episode-1",
        adapter=adapter,
        grants=ledger,
        fence=fence,
        barrier=RLock(),
        clock=lambda: 1,
    )

    accepted = hands.submit(request("workspace_write", {"path": "src/new.txt", "content": "safe"}))
    git = hands.submit(request("workspace_write", {"path": ".git/config", "content": "unsafe"}, call_id="call-2"))
    stage = hands.submit(
        request(
            "workspace_write",
            {"path": ".petrus-hands-stage/foreign", "content": "unsafe"},
            call_id="call-3",
        )
    )

    assert accepted.ok and adapter.target["src/new.txt"] == "safe"
    assert git.error and git.error.category is RejectionCategory.PATH
    assert stage.error and stage.error.category is RejectionCategory.PATH
    assert adapter.calls == ["stage", "commit"]
    with pytest.raises(ValueError, match="normalized relative path"):
        ledger.open([ToolMethod.WORKSPACE_WRITE], writable_roots=["../foreign"], deadline=50, max_calls=1)


def test_write_root_matching_uses_segments_and_denial_overrides_exact_path() -> None:
    grant = CapabilityGrant(
        "attachment-1",
        1,
        1,
        frozenset({ToolMethod.WORKSPACE_WRITE}),
        frozenset({".git/config"}),
        frozenset(),
        50,
        3,
        writable_roots=frozenset({"src"}),
        denied_writable_roots=frozenset({".git"}),
    )
    deny_all = replace(grant, denied_writable_roots=frozenset({"."}))

    assert grant.permits_write_path("src/new.txt")
    assert not grant.permits_write_path("src2/new.txt")
    assert not grant.permits_write_path(".git/config")
    assert not deny_all.permits_write_path("src/new.txt")


class Adapter:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.target: dict[str, str] = {}

    def read(self, path: str) -> str:
        self.calls.append("read")
        return "safe"

    def search(self, query: str, path: str) -> tuple[str, ...]:
        self.calls.append("search")
        return ("match",)

    def shell(self, argv: tuple[str, ...], cwd: str) -> ShellOutcome:
        self.calls.append("shell")
        return ShellOutcome(0, "ok", "", False)

    def stage_write(self, call_id: str, path: str, content: str) -> StagedWrite:
        self.calls.append("stage")
        self.target["stage"] = content
        return StagedWrite(call_id, path, "d" * 64)

    def commit_write(self, staged: StagedWrite) -> str:
        self.calls.append("commit")
        self.target[staged.path] = self.target.pop("stage")
        return staged.digest

    def discard_write(self, staged: StagedWrite) -> None:
        self.calls.append("discard")
        self.target.pop("stage", None)

    def run_test(self) -> Outcome:
        self.calls.append("test")
        return Outcome(True, "e" * 64)

    def discard_all_stages(self) -> int:
        present = int("stage" in self.target)
        self.target.pop("stage", None)
        return present


class Fence:
    value = CallFence(True, False, 100.0)

    def snapshot(self) -> CallFence:
        return self.value


def gateway(capabilities: list[ToolMethod], *, clock=lambda: 1.0) -> tuple[HandsGateway, Adapter, Fence]:
    adapter, fence = Adapter(), Fence()
    ledger = GrantLedger("attachment-1", 1)
    ledger.open(capabilities, writable_paths=["out.txt"], allowed_argv=[("printf", "ok")], deadline=50, max_calls=20)
    return (
        HandsGateway(
            episode_id="episode-1",
            adapter=adapter,
            grants=ledger,
            fence=fence,
            barrier=RLock(),
            clock=clock,
        ),
        adapter,
        fence,
    )


def test_all_direct_rejections_are_pre_crossing_and_flat() -> None:
    hands, adapter, fence = gateway([ToolMethod.WORKSPACE_READ])
    cases = [
        request("future", {}),
        request("workspace_write", {"path": "out.txt", "content": "x"}),
        request("workspace_shell", {"argv": ["printf", "ok"], "cwd": "."}),
        request("workspace_read", {"path": "README.md"}, attachment_epoch=2),
    ]
    fence.value = replace(fence.value, open=False)
    cases.append(request("workspace_read", {"path": "README.md"}))
    for index, item in enumerate(cases):
        item["call_id"] = f"reject-{index}"
        assert not hands.submit(item).ok
    counters = hands.counters()
    assert counters.adapter_entries == counters.stages == counters.commits == counters.target_mutations == 0
    assert adapter.calls == []


def test_foreign_episode_is_rejected_before_adapter_crossing() -> None:
    hands, adapter, _ = gateway([ToolMethod.WORKSPACE_READ])
    result = hands.submit(request("workspace_read", {"path": "README.md"}, episode_id="episode-foreign"))
    assert result.error and result.error.category is RejectionCategory.STALE_EPOCH
    assert adapter.calls == [] and hands.counters().adapter_entries == 0


def test_staged_write_commits_once_and_post_fence_discards() -> None:
    hands, adapter, fence = gateway([ToolMethod.WORKSPACE_WRITE])
    good = hands.submit(request("workspace_write", {"path": "out.txt", "content": "new"}))
    assert good.ok and adapter.calls == ["stage", "commit"] and adapter.target == {"out.txt": "new"}
    assert hands.counters().target_mutations == 1

    class Closing(Adapter):
        def stage_write(self, call_id: str, path: str, content: str) -> StagedWrite:
            staged = super().stage_write(call_id, path, content)
            fence.value = replace(fence.value, open=False)
            return staged

    closing = Closing()
    ledger = GrantLedger("attachment-1", 1)
    ledger.open([ToolMethod.WORKSPACE_WRITE], writable_paths=["out.txt"], deadline=50, max_calls=1)
    rejected_gateway = HandsGateway(
        episode_id="episode-1",
        adapter=closing,
        grants=ledger,
        fence=fence,
        barrier=RLock(),
        clock=lambda: 1,
    )
    fence.value = CallFence(True, False, 100)
    rejected = rejected_gateway.submit(request("workspace_write", {"path": "out.txt", "content": "canary"}))
    assert rejected.error and rejected.error.category is RejectionCategory.POST_FENCE
    assert closing.calls == ["stage", "discard"] and "out.txt" not in closing.target


def test_provider_exception_is_sanitized_and_evidence_is_bounded() -> None:
    hands, adapter, _ = gateway([ToolMethod.WORKSPACE_READ])

    def explode(path: str) -> str:
        raise RuntimeError("SECRET-CANARY")

    adapter.read = explode  # type: ignore[method-assign]
    result = hands.submit(request("workspace_read", {"path": "README.md"}))
    rendered = repr(result.to_data()) + repr(hands.evidence())
    assert result.error and result.error.category is RejectionCategory.PROVIDER
    assert "SECRET-CANARY" not in rendered


def test_model_projection_preserves_semantics_without_attachment_custody() -> None:
    hands, _, _ = gateway([ToolMethod.WORKSPACE_READ])

    result = hands.submit(request("workspace_read", {"path": "README.md"}))

    assert result.to_model_data() == {
        "version": 1,
        "ok": True,
        "data": {"content": "safe"},
        "error": None,
    }
    assert result.to_data()["call_id"] == "call-1"
    assert result.to_data()["attachment_id"] == "attachment-1"
    assert result.to_data()["epoch"] == 1


def test_exact_retransmission_is_terminal_and_conflict_fails_loud() -> None:
    hands, adapter, fence = gateway([ToolMethod.WORKSPACE_READ])
    payload = request("workspace_read", {"path": "README.md"})
    first = hands.submit(payload)
    fence.value = CallFence(False, True, 0)
    second = hands.submit(dict(payload))
    assert second is first
    assert adapter.calls == ["read"]
    assert len(hands.evidence()) == 1
    with pytest.raises(ToolCallConflict, match="immutable request") as conflict:
        hands.submit(request("workspace_read", {"path": "other"}))
    assert "other" not in repr(conflict.value)


def test_concurrent_exact_duplicates_single_flight() -> None:
    hands, adapter, _ = gateway([ToolMethod.WORKSPACE_READ])
    entered = Barrier(2)
    release = Barrier(2)

    def delayed(path: str) -> str:
        adapter.calls.append("read")
        entered.wait()
        release.wait()
        return "safe"

    adapter.read = delayed  # type: ignore[method-assign]
    payload = request("workspace_read", {"path": "README.md"})
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(hands.submit, payload)
        entered.wait()
        second = pool.submit(hands.submit, dict(payload))
        release.wait()
        assert first.result() is second.result()
    assert adapter.calls == ["read"]
    assert len(hands.evidence()) == 1


def test_call_ledger_and_grant_exhaustion_are_budget_not_stale() -> None:
    adapter, fence = Adapter(), Fence()
    ledger = GrantLedger("attachment-1", 1)
    ledger.open([ToolMethod.WORKSPACE_READ], deadline=50, max_calls=1)
    hands = HandsGateway(
        episode_id="episode-1",
        adapter=adapter,
        grants=ledger,
        fence=fence,
        barrier=RLock(),
        clock=lambda: 1,
        max_calls=2,
    )
    assert hands.submit(request("workspace_read", {"path": "one"}, call_id="one")).ok
    exhausted = hands.submit(request("workspace_read", {"path": "two"}, call_id="two"))
    full = hands.submit(request("workspace_read", {"path": "three"}, call_id="three"))
    assert exhausted.error and exhausted.error.category is RejectionCategory.BUDGET
    assert full.error and full.error.category is RejectionCategory.BUDGET


def test_malformed_adapter_result_is_a_typed_provider_error() -> None:
    hands, adapter, _ = gateway([ToolMethod.WORKSPACE_READ])
    adapter.read = lambda path: "x" * 5000  # type: ignore[method-assign]
    result = hands.submit(request("workspace_read", {"path": "README.md"}))
    assert result.error and result.error.category is RejectionCategory.PROVIDER
    assert len(hands.evidence()) == 1


def test_abandoned_primary_allows_an_exact_waiter_to_reclaim_without_key_error() -> None:
    hands, adapter, _ = gateway([ToolMethod.WORKSPACE_READ])
    entered = Barrier(2)
    release = Barrier(2)
    attempts = 0

    def interrupted(path: str) -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            entered.wait()
            release.wait()
            raise KeyboardInterrupt
        return "safe"

    adapter.read = interrupted  # type: ignore[method-assign]
    payload = request("workspace_read", {"path": "README.md"})
    with ThreadPoolExecutor(max_workers=2) as pool:
        primary = pool.submit(hands.submit, payload)
        entered.wait()
        duplicate = pool.submit(hands.submit, dict(payload))
        release.wait()
        with pytest.raises(KeyboardInterrupt):
            primary.result()
        assert duplicate.result().ok
    assert attempts == 2 and len(hands.evidence()) == 1


def test_authority_target_deadline_abort_and_grant_postchecks_fail_closed() -> None:
    class Admission:
        def admit(self, call_id: str) -> bool:
            return False

    adapter, fence = Adapter(), Fence()
    ledger = GrantLedger("attachment-1", 1)
    ledger.open([ToolMethod.WORKSPACE_READ], deadline=50, max_calls=1)
    authority = HandsGateway(
        episode_id="episode-1",
        adapter=adapter,
        grants=ledger,
        fence=fence,
        barrier=RLock(),
        admission=Admission(),
        clock=lambda: 1,
    )
    denied = authority.submit(request("workspace_read", {"path": "README.md"}))
    assert denied.error and denied.error.category is RejectionCategory.AUTHORITY

    class Target:
        def is_current(self) -> bool:
            return False

    adapter, fence = Adapter(), Fence()
    ledger = GrantLedger("attachment-1", 1)
    ledger.open([ToolMethod.WORKSPACE_WRITE], writable_paths=["out.txt"], deadline=50, max_calls=1)
    stale_target = HandsGateway(
        episode_id="episode-1",
        adapter=adapter,
        grants=ledger,
        fence=fence,
        barrier=RLock(),
        target=Target(),
        clock=lambda: 1,
    )
    denied = stale_target.submit(request("workspace_write", {"path": "out.txt", "content": "safe"}))
    assert denied.error and denied.error.category is RejectionCategory.POST_FENCE
    assert adapter.calls == ["stage", "discard"] and "out.txt" not in adapter.target

    for category, update in (
        (RejectionCategory.DEADLINE, CallFence(True, False, 0)),
        (RejectionCategory.ABORTED, CallFence(True, True, 100)),
    ):
        adapter, fence = Adapter(), Fence()
        ledger = GrantLedger("attachment-1", 1)
        ledger.open([ToolMethod.WORKSPACE_READ], deadline=50, max_calls=1)

        def change_fence(path: str, *, value: CallFence = update) -> str:
            fence.value = value
            return "safe"

        adapter.read = change_fence  # type: ignore[method-assign]
        checked = HandsGateway(
            episode_id="episode-1",
            adapter=adapter,
            grants=ledger,
            fence=fence,
            barrier=RLock(),
            clock=lambda: 1,
        )
        denied = checked.submit(request("workspace_read", {"path": "README.md"}))
        assert denied.error and denied.error.category is category

    adapter, fence = Adapter(), Fence()
    ledger = GrantLedger("attachment-1", 1)
    ledger.open([ToolMethod.WORKSPACE_WRITE], writable_paths=["out.txt"], deadline=50, max_calls=1)

    def replace_grant(call_id: str, path: str, content: str) -> StagedWrite:
        staged = Adapter.stage_write(adapter, call_id, path, content)
        ledger.open([ToolMethod.WORKSPACE_WRITE], writable_paths=["out.txt"], deadline=50, max_calls=1)
        return staged

    adapter.stage_write = replace_grant  # type: ignore[method-assign]
    checked = HandsGateway(
        episode_id="episode-1",
        adapter=adapter,
        grants=ledger,
        fence=fence,
        barrier=RLock(),
        clock=lambda: 1,
    )
    denied = checked.submit(request("workspace_write", {"path": "out.txt", "content": "safe"}))
    assert denied.error and denied.error.category is RejectionCategory.STALE_EPOCH
    assert adapter.calls == ["stage", "discard"] and "out.txt" not in adapter.target


def test_claimed_call_is_drained_before_attachment_cleanup_can_start() -> None:
    hands, adapter, _ = gateway([ToolMethod.WORKSPACE_READ])
    ledger = hands._grants  # noqa: SLF001 - concurrency test pins the claim/consume window
    original = ledger.consume
    entered = Event()
    release = Event()

    def delayed_consume(grant_epoch: int):
        entered.set()
        assert release.wait(2)
        return original(grant_epoch)

    ledger.consume = delayed_consume  # type: ignore[method-assign]
    payload = request("workspace_read", {"path": "README.md"})
    with ThreadPoolExecutor(max_workers=2) as pool:
        submitted = pool.submit(hands.submit, payload)
        assert entered.wait(2)
        drained = pool.submit(hands.drain, 2)
        assert not drained.done()
        release.set()
        assert submitted.result().ok and drained.result()
    assert adapter.calls == ["read"]
