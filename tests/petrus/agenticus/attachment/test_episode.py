from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event

import pytest

from petrus.agenticus.attachment.binding import BindingSettlement, MotusAttachmentBinding
from petrus.agenticus.attachment.episode import EpisodeAttachment, EpisodeAttachmentError, UncertainCustodyError
from petrus.agenticus.catalog.descriptor import CapabilityDescriptor, DescriptorIdentity, DescriptorKind
from petrus.agenticus.catalog.resolution import ResolutionSnapshot
from petrus.agenticus.hands.contract import ToolMethod
from petrus.agenticus.hands.workspace import MotusWorkspaceAdapter
from petrus.agenticus.thread.identity import EpisodeId
from petrus.motus.execution import EnvironmentSpec
from petrus.motus.execution.archive import extract_workspace_archive, workspace_archive
from petrus.motus.execution.providers import LocalProcessEnvironment


def snapshot(suffix: str) -> ResolutionSnapshot:
    return ResolutionSnapshot(
        1,
        tuple(
            CapabilityDescriptor(DescriptorIdentity(kind, f"{kind.value}-{suffix}", 1), frozenset(), ())
            for kind in (DescriptorKind.RUNTIME, DescriptorKind.HANDS, DescriptorKind.TERRITORY)
        ),
    )


@dataclass
class Binding:
    outcomes: list[bool | Exception]
    binding_kind: str = "provider-managed"
    events: list[str] = field(default_factory=list)

    def cancel(self, reason: str) -> None:
        self.events.append("cancel")

    def export_archive(self) -> bytes:
        self.events.append("export")
        return b"archive"

    def settle(self) -> BindingSettlement:
        self.events.append("destroy")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        verified = outcome
        return BindingSettlement(self.binding_kind, "clean" if verified else "unverified", verified)


def attachment(binding: Binding, *, identity: str = "attachment-1", epoch: int = 1) -> EpisodeAttachment:
    return EpisodeAttachment(
        episode_id=EpisodeId("episode-1"),
        snapshot=snapshot("one"),
        binding=binding,
        attachment_id=identity,
        attachment_epoch=epoch,
        deadline=100,
        clock=lambda: 1,
    )


def test_settlement_is_ordered_and_successor_is_a_new_episode_attachment() -> None:
    old_binding = Binding([True])
    old = attachment(old_binding, epoch=4)
    old.cancel("stop")
    record = old.settle()
    assert old_binding.events == ["cancel", "export", "destroy"]
    assert record.epoch == 4 and record.archive == b"archive" and record.settlement.verified

    new_binding = Binding([True])
    successor = old.successor(
        episode_id=EpisodeId("episode-2"),
        snapshot=snapshot("two"),
        binding=new_binding,
        attachment_id="attachment-2",
        deadline=200,
    )
    assert successor is not old
    assert successor.epoch == 5 and successor.binding is new_binding
    assert successor.grants() is not old.grants()
    assert successor.coordinates().episode_id == "episode-2"
    assert old.settled and old.binding is old_binding
    with pytest.raises(EpisodeAttachmentError):
        old.successor(
            episode_id=EpisodeId("episode-1"),
            snapshot=snapshot("two"),
            binding=new_binding,
            attachment_id="attachment-2",
            deadline=200,
        )


def test_unverified_custody_blocks_progress_until_destroy_retry_verifies() -> None:
    binding = Binding([False, True])
    old = attachment(binding)
    assert not old.settle().settlement.verified
    assert old.custody_uncertain
    with pytest.raises(UncertainCustodyError):
        old.successor(
            episode_id=EpisodeId("episode-2"),
            snapshot=snapshot("two"),
            binding=Binding([True]),
            attachment_id="attachment-2",
            deadline=200,
        )
    assert old.retry_settlement().settlement.verified
    assert binding.events == ["export", "destroy", "destroy"]


def test_raising_binding_settlement_records_uncertain_custody_and_can_retry() -> None:
    binding = Binding([RuntimeError("SECRET-CANARY"), True])
    old = attachment(binding)
    with pytest.raises(EpisodeAttachmentError, match="binding settlement failed") as failed:
        old.settle()
    assert "SECRET-CANARY" not in repr(failed.value)
    assert old.custody_uncertain
    assert old.last_settlement is not None and not old.last_settlement.settlement.verified
    assert old.retry_settlement().settlement.verified


def test_settlement_waits_for_every_claimed_call_before_export_and_destroy() -> None:
    binding = Binding([True])
    current = attachment(binding)
    entered = Event()
    release = Event()

    class Adapter:
        def read(self, path: str) -> str:
            return "safe"

        def search(self, query: str, path: str) -> tuple[str, ...]:
            return ()

        def shell(self, argv: tuple[str, ...], cwd: str):
            raise AssertionError

        def stage_write(self, call_id: str, path: str, content: str):
            raise AssertionError

        def commit_write(self, staged):
            raise AssertionError

        def discard_write(self, staged) -> None:
            raise AssertionError

        def run_test(self):
            raise AssertionError

        def discard_all_stages(self) -> int:
            return 0

    gateway = current.gateway(Adapter())
    ledger = current.grants()
    grant = ledger.open([ToolMethod.WORKSPACE_READ], deadline=50, max_calls=1)
    original = ledger.consume

    def delayed_consume(grant_epoch: int):
        entered.set()
        assert release.wait(2)
        return original(grant_epoch)

    ledger.consume = delayed_consume  # type: ignore[method-assign]
    payload = {
        "version": 1,
        "call_id": "settlement-race",
        "episode_id": "episode-1",
        "attachment_id": "attachment-1",
        "attachment_epoch": 1,
        "grant_epoch": grant.grant_epoch,
        "method": "workspace_read",
        "params": {"path": "README.md"},
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        submitted = pool.submit(gateway.submit, payload)
        assert entered.wait(2)
        settled = pool.submit(current.settle, drain_timeout=2)
        assert not settled.done() and binding.events == []
        release.set()
        assert not submitted.result().ok
        assert settled.result().settlement.verified
    assert binding.events == ["export", "destroy"]


def test_concurrent_settlement_cannot_export_or_destroy_one_binding_twice() -> None:
    entered = Event()
    release = Event()

    class BlockingBinding(Binding):
        def export_archive(self) -> bytes:
            self.events.append("export")
            entered.set()
            assert release.wait(2)
            return b"archive"

    binding = BlockingBinding([True])
    current = attachment(binding)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(current.settle)
        assert entered.wait(2)
        second = pool.submit(current.settle)
        with pytest.raises(EpisodeAttachmentError, match="already in progress"):
            second.result()
        release.set()
        assert first.result().settlement.verified
    assert binding.events == ["export", "destroy"]


def test_cancellation_is_serialized_before_settlement_and_is_too_late_afterward() -> None:
    entered = Event()
    release = Event()

    class BlockingCancelBinding(Binding):
        def cancel(self, reason: str) -> None:
            self.events.append("cancel")
            entered.set()
            assert release.wait(2)

    binding = BlockingCancelBinding([True])
    current = attachment(binding)
    with ThreadPoolExecutor(max_workers=2) as pool:
        cancelled = pool.submit(current.cancel, "stop")
        assert entered.wait(2)
        settled = pool.submit(current.settle)
        assert not settled.done() and binding.events == ["cancel"]
        release.set()
        cancelled.result()
        assert settled.result().settlement.verified
    assert binding.events == ["cancel", "export", "destroy"]
    with pytest.raises(EpisodeAttachmentError, match="already settled"):
        current.cancel("late")


def test_cancellation_cannot_enter_after_settlement_has_started() -> None:
    entered = Event()
    release = Event()

    class BlockingExportBinding(Binding):
        def export_archive(self) -> bytes:
            self.events.append("export")
            entered.set()
            assert release.wait(2)
            return b"archive"

    binding = BlockingExportBinding([True])
    current = attachment(binding)
    with ThreadPoolExecutor(max_workers=2) as pool:
        settled = pool.submit(current.settle)
        assert entered.wait(2)
        cancelled = pool.submit(current.cancel, "late")
        with pytest.raises(EpisodeAttachmentError, match="already in progress"):
            cancelled.result()
        release.set()
        assert settled.result().settlement.verified
    assert binding.events == ["export", "destroy"]


def test_local_episode_attachment_composes_gateway_archive_cleanup_and_successor_fences(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    provider = LocalProcessEnvironment()
    binding = MotusAttachmentBinding.open(
        provider,
        "ds6-composed-episode",
        EnvironmentSpec(),
        workspace_archive_bytes=workspace_archive(source),
        input_digest="input",
    )
    current = EpisodeAttachment(
        episode_id=EpisodeId("episode-local-1"),
        snapshot=snapshot("local"),
        binding=binding,
        attachment_id="attachment-local-1",
        deadline=100,
        clock=lambda: 1,
    )
    adapter = MotusWorkspaceAdapter(
        provider,
        binding.execution,
        test_command=("/bin/sh", "-c", "test -f output.txt"),
    )
    gateway = current.gateway(adapter)
    grant = current.grants().open(
        [ToolMethod.WORKSPACE_WRITE, ToolMethod.WORKSPACE_TEST],
        writable_paths=["output.txt"],
        deadline=90,
        max_calls=2,
    )

    def payload(call_id: str, method: str, params: dict[str, object]) -> dict[str, object]:
        return {
            "version": 1,
            "call_id": call_id,
            "episode_id": current.episode_id.value,
            "attachment_id": current.attachment_id,
            "attachment_epoch": current.epoch,
            "grant_epoch": grant.grant_epoch,
            "method": method,
            "params": params,
        }

    assert gateway.submit(payload("write", "workspace_write", {"path": "output.txt", "content": "safe"})).ok
    assert gateway.submit(payload("test", "workspace_test", {})).ok
    record = current.settle()
    restored = tmp_path / "restored"
    extract_workspace_archive(record.archive, restored)
    assert (restored / "output.txt").read_text() == "safe"
    assert record.settlement.verified and binding.cleanup_result is not None
    assert provider.lookup("ds6-composed-episode") is None

    successor = current.successor(
        episode_id=EpisodeId("episode-local-2"),
        snapshot=snapshot("provider"),
        binding=Binding([True]),
        attachment_id="attachment-local-2",
        deadline=200,
    )

    class PoisonAdapter:
        def read(self, path: str) -> str:
            raise AssertionError("stale request crossed the successor gateway")

    successor_grant = successor.grants().open([ToolMethod.WORKSPACE_READ], deadline=190, max_calls=1)
    successor_gateway = successor.gateway(PoisonAdapter())  # type: ignore[arg-type]
    stale = successor_gateway.submit(
        {
            "version": 1,
            "call_id": "old-attachment",
            "episode_id": successor.episode_id.value,
            "attachment_id": current.attachment_id,
            "attachment_epoch": current.epoch,
            "grant_epoch": successor_grant.grant_epoch,
            "method": "workspace_read",
            "params": {"path": "output.txt"},
        }
    )
    assert stale.error and stale.error.category.value == "stale_epoch"


@pytest.mark.parametrize("epoch", [0, -1, True])
def test_attachment_epoch_is_exactly_positive(epoch: object) -> None:
    with pytest.raises(ValueError, match="epoch"):
        attachment(Binding([True]), epoch=epoch)  # type: ignore[arg-type]
