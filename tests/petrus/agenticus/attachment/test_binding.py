from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from petrus.agenticus.attachment.binding import BindingSettlement, MotusAttachmentBinding, MotusBindingError
from petrus.motus.execution import CleanupDisposition, CleanupResult, Command, EnvironmentSpec
from petrus.motus.execution.archive import workspace_archive
from petrus.motus.execution.providers import LocalProcessEnvironment


@dataclass
class ProviderManagedBinding:
    """An honest provider-managed binding has no Motus lease."""

    binding_kind: str = "provider-managed"
    cancelled: bool = False

    def cancel(self, reason: str) -> None:
        self.cancelled = True

    def export_archive(self) -> bytes:
        return b"archive"

    def settle(self) -> BindingSettlement:
        return BindingSettlement(self.binding_kind, "clean", True)


def test_outer_binding_shape_does_not_assume_motus() -> None:
    binding = ProviderManagedBinding()
    binding.cancel("stop")
    assert binding.cancelled and binding.export_archive() == b"archive" and binding.settle().verified
    assert not hasattr(binding, "lease_identity")


def test_motus_binding_is_lookup_first_and_settles_exact_lease(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    provider = LocalProcessEnvironment()
    existing = provider.create("ds6-binding", EnvironmentSpec())
    binding = MotusAttachmentBinding.open(
        provider,
        "ds6-binding",
        EnvironmentSpec(),
        workspace_archive_bytes=workspace_archive(source),
        input_digest="input",
    )
    assert binding.lease_identity == existing.identity
    assert binding.execution.lease.identity == existing.identity
    assert binding.export_archive()
    settlement = binding.settle()
    assert settlement.verified and settlement.disposition == CleanupDisposition.CLEAN.value


@pytest.mark.parametrize("interruption", ("cancel", "timeout"))
def test_motus_binding_discards_interrupted_output_but_still_destroys_the_territory(
    tmp_path: Path, interruption: str
) -> None:
    source = tmp_path / f"source-{interruption}"
    source.mkdir()
    (source / "value").write_text("base")
    base_archive = workspace_archive(source)
    provider = LocalProcessEnvironment()
    binding = MotusAttachmentBinding.open(
        provider,
        f"ds6-{interruption}",
        EnvironmentSpec(),
        workspace_archive_bytes=base_archive,
        input_digest="input",
    )
    if interruption == "cancel":
        binding.cancel("stop")
    else:
        result = binding.execute(Command(("/bin/sh", "-c", "printf changed > value; sleep 1"), timeout=0.05))
        assert result.timed_out
    assert binding.export_archive() == base_archive
    assert binding.settle().verified


def test_foreign_cleanup_evidence_never_verifies(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    provider = LocalProcessEnvironment()
    binding = MotusAttachmentBinding.open(
        provider,
        "ds6-foreign",
        EnvironmentSpec(),
        workspace_archive_bytes=workspace_archive(source),
        input_digest="input",
    )
    original = provider.destroy
    provider.destroy = lambda lease: CleanupResult(  # type: ignore[method-assign]
        provider.create("other", EnvironmentSpec()).identity, CleanupDisposition.CLEAN
    )
    try:
        assert not binding.settle().verified
    finally:
        provider.destroy = original  # type: ignore[method-assign]
        original(provider.lookup("ds6-foreign"))  # type: ignore[arg-type]
        other = provider.lookup("other")
        if other is not None:
            original(other)


def test_open_attach_failure_cleans_the_claimed_lease_or_fails_uncertain(tmp_path: Path) -> None:
    provider = LocalProcessEnvironment()
    original = provider.attach
    provider.attach = lambda *args: (_ for _ in ()).throw(RuntimeError("SECRET-CANARY"))  # type: ignore[method-assign]
    try:
        with pytest.raises(MotusBindingError, match="verified cleanup") as failed:
            MotusAttachmentBinding.open(
                provider,
                "ds6-attach-failure",
                EnvironmentSpec(),
                workspace_archive_bytes=workspace_archive(tmp_path),
                input_digest="input",
            )
        assert "SECRET-CANARY" not in repr(failed.value)
        assert provider.lookup("ds6-attach-failure") is None
    finally:
        provider.attach = original  # type: ignore[method-assign]
