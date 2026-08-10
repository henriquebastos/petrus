"""Disposable Lane-3 evidence for generation-scoped tokens and Activities."""

from __future__ import annotations

import pytest

from petrus.impetus.activity_scopes import (
    ActivityCompletionQuarantined,
    ActivityPhase,
    ActivityScopeRuntime,
    ScopeClosed,
    ScopeReset,
)


def _scope_with_pending_and_running_work() -> tuple[ActivityScopeRuntime, object]:
    runtime = ActivityScopeRuntime()
    scope = runtime.open("turn")
    runtime.queue(scope, "queued-1", {"text": "old"})
    runtime.request(scope, "pending")
    runtime.request(scope, "running")
    runtime.start("running")
    return runtime, scope


def test_reset_is_one_atomic_record_that_cleans_tokens_cancels_work_and_opens_the_next_generation() -> None:
    runtime, first = _scope_with_pending_and_running_work()
    before = len(runtime.records)

    outcome = runtime.reset(first, instant=10)

    assert len(runtime.records) == before + 1
    assert runtime.records[-1] == ScopeReset(
        closed=first,
        opened=outcome.opened,
        dropped_tokens=("queued-1",),
        cancelled_activities=("pending", "running"),
        instant=10,
    )
    assert outcome.opened.name == first.name
    assert outcome.opened.generation == first.generation + 1
    assert runtime.active("turn") == outcome.opened
    assert runtime.queued == ()
    assert runtime.activity("pending").phase is ActivityPhase.CANCELLED
    assert runtime.activity("running").phase is ActivityPhase.CANCELLED
    assert [(item.activity, item.prior) for item in outcome.cancelled] == [
        ("pending", ActivityPhase.PENDING),
        ("running", ActivityPhase.RUNNING),
    ]


def test_close_is_atomic_and_returns_cancellation_work_only_after_the_close_commits() -> None:
    class RefusingHistory(list):
        def append(self, event):
            raise OSError("history unavailable")

    runtime = ActivityScopeRuntime()
    scope = runtime.open("turn")
    runtime.request(scope, "pending")
    runtime._history = RefusingHistory(runtime.records)  # noqa: SLF001 - deliberate commit-boundary probe

    with pytest.raises(OSError, match="history unavailable"):
        runtime.close(scope)

    assert runtime.active("turn") == scope
    assert runtime.activity("pending").phase is ActivityPhase.PENDING


def test_close_cancels_both_pending_and_running_activities_and_drops_duplicate_valued_tokens_by_identity() -> None:
    runtime = ActivityScopeRuntime()
    scope = runtime.open("turn")
    runtime.queue(scope, "first", {"same": True})
    runtime.queue(scope, "second", {"same": True})
    runtime.request(scope, "pending")
    runtime.request(scope, "running")
    runtime.start("running")

    outcome = runtime.close(scope)

    assert runtime.records[-1] == ScopeClosed(
        scope,
        dropped_tokens=("first", "second"),
        cancelled_activities=("pending", "running"),
    )
    assert [(item.activity, item.prior) for item in outcome.cancelled] == [
        ("pending", ActivityPhase.PENDING),
        ("running", ActivityPhase.RUNNING),
    ]
    assert runtime.queued == ()


def test_completion_before_close_wins_but_its_scoped_output_is_removed_by_close() -> None:
    runtime = ActivityScopeRuntime()
    scope = runtime.open("turn")
    runtime.request(scope, "work")
    runtime.start("work")

    assert runtime.complete("work", {"answer": 42}, outputs=(("answer", 42),), instant=20) == "accepted"
    outcome = runtime.close(scope, instant=20)

    assert runtime.activity("work").phase is ActivityPhase.COMPLETED
    assert outcome.cancelled == ()
    assert outcome.dropped_tokens == ("answer",)
    assert runtime.queued == ()
    assert runtime.complete("work", {"answer": 42}, instant=21) == "acknowledged"


def test_close_before_completion_wins_and_late_result_is_durably_quarantined_at_the_same_instant() -> None:
    runtime = ActivityScopeRuntime()
    scope = runtime.open("turn")
    runtime.request(scope, "work")
    runtime.start("work")

    runtime.close(scope, instant=20)
    assert runtime.complete("work", {"answer": 42}, instant=20) == "quarantined"

    assert runtime.activity("work").phase is ActivityPhase.CANCELLED
    assert runtime.records[-1] == ActivityCompletionQuarantined("work", scope, {"answer": 42}, instant=20)
    assert runtime.quarantined == {"work": {"answer": 42}}


def test_late_completion_drop_is_replay_stable_across_close_and_resume() -> None:
    runtime = ActivityScopeRuntime()
    scope = runtime.open("turn")
    runtime.request(scope, "work")
    runtime.start("work")
    runtime.close(scope)

    resumed = ActivityScopeRuntime.resume(runtime.records)
    assert resumed.complete("work", {"answer": 42}) == "quarantined"
    once = resumed.records

    resumed_again = ActivityScopeRuntime.resume(once)
    assert resumed_again.complete("work", {"answer": 42}) == "acknowledged-quarantine"
    assert resumed_again.records == once
    assert resumed_again.queued == ()
    assert resumed_again.activity("work").phase is ActivityPhase.CANCELLED


def test_reset_resume_continues_only_the_new_generation_and_quarantines_the_old_activity() -> None:
    runtime = ActivityScopeRuntime()
    old = runtime.open("turn")
    runtime.request(old, "old-work")
    new = runtime.reset(old).opened
    runtime.queue(new, "new-token", "keep")
    runtime.request(new, "new-work")

    resumed = ActivityScopeRuntime.resume(runtime.records)

    assert resumed.active("turn") == new
    assert [token.identity for token in resumed.queued] == ["new-token"]
    assert resumed.complete("old-work", "late") == "quarantined"
    assert resumed.activity("new-work").phase is ActivityPhase.PENDING
