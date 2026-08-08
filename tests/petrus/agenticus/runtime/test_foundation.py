"""DS9 shared facts stay strict, provider-neutral, and secret-safe."""

from __future__ import annotations

import dataclasses
import subprocess
import sys

import pytest

from petrus.agenticus.catalog.descriptor import DescriptorIdentity, DescriptorKind
from petrus.agenticus.runtime.installation import (
    InstalledComponent,
    ProbeDisposition,
    ProbeIssue,
    RuntimeInstallation,
    RuntimeProbeResult,
)
from petrus.agenticus.runtime.operation import (
    RuntimeCleanupDisposition,
    RuntimeOperation,
    RuntimeOperationCleanup,
    RuntimeProtocolError,
)
from petrus.agenticus.runtime.result import RuntimeTurnSettlement
from petrus.agenticus.thread.identity import EpisodeId, TurnId
from petrus.agenticus.thread.lifecycle import CancellationDisposition, TurnOutcome


RUNTIME = DescriptorIdentity(DescriptorKind.RUNTIME, "test.runtime", 1)
OTHER_RUNTIME = DescriptorIdentity(DescriptorKind.RUNTIME, "test.other-runtime", 1)
COMPONENT = InstalledComponent("test-client", "1.2.3", "package:test-client@1.2.3")
INSTALLATION = RuntimeInstallation(
    runtime=RUNTIME,
    adapter_contract_version=1,
    components=(COMPONENT,),
    platform="linux",
    architecture="x86_64",
    capabilities=frozenset({"runtime.cancel", "runtime.continue"}),
)


def test_installation_facts_are_canonical_and_have_no_path_or_authority_field() -> None:
    second = InstalledComponent("sidecar", "4.5.6", "package:sidecar@4.5.6")
    installation = RuntimeInstallation(
        RUNTIME,
        1,
        (second, COMPONENT),
        "linux",
        "x86_64",
        frozenset({"runtime.cancel"}),
    )

    assert installation.components == (second, COMPONENT)
    assert {field.name for field in dataclasses.fields(RuntimeInstallation)} == {
        "runtime",
        "adapter_contract_version",
        "components",
        "platform",
        "architecture",
        "capabilities",
    }
    assert not hasattr(installation, "path")
    assert not hasattr(installation, "environment")
    assert not hasattr(installation, "home")


def test_probe_dispositions_preserve_exact_installation_truth() -> None:
    ready = RuntimeProbeResult(RUNTIME, ProbeDisposition.READY, INSTALLATION)
    incompatible = RuntimeProbeResult(
        RUNTIME,
        ProbeDisposition.INCOMPATIBLE,
        INSTALLATION,
        (ProbeIssue("version-mismatch", "test-client"),),
    )
    absent = RuntimeProbeResult(
        RUNTIME,
        ProbeDisposition.NOT_INSTALLED,
        issues=(ProbeIssue("client-not-installed", "test-client"),),
    )
    unavailable = RuntimeProbeResult(
        RUNTIME,
        ProbeDisposition.UNAVAILABLE,
        INSTALLATION,
        (ProbeIssue("service-unavailable", "test-client"),),
    )

    assert ready.installation is INSTALLATION
    assert incompatible.issues == (ProbeIssue("version-mismatch", "test-client"),)
    assert absent.installation is None
    assert unavailable.installation is INSTALLATION

    with pytest.raises(ValueError, match="ready runtime"):
        RuntimeProbeResult(RUNTIME, ProbeDisposition.READY)
    with pytest.raises(ValueError, match="identities must match"):
        RuntimeProbeResult(OTHER_RUNTIME, ProbeDisposition.READY, INSTALLATION)
    with pytest.raises(ValueError, match="unavailable runtime"):
        RuntimeProbeResult(RUNTIME, ProbeDisposition.UNAVAILABLE)


def test_runtime_turn_result_is_one_batch_and_hides_opaque_references() -> None:
    canary = "opaque-secret-reference"
    result = RuntimeTurnSettlement(
        EpisodeId("episode-1"),
        TurnId("turn-1"),
        TurnOutcome.COMPLETED,
        1,
        "turn-completed",
        output_reference=canary,
        continuation_reference="continuation-state-1",
    )

    assert result.accepted_appends == 1
    assert canary not in repr(result)
    assert "continuation-state-1" not in repr(result)
    assert {field.name for field in dataclasses.fields(RuntimeTurnSettlement)} == {
        "episode_id",
        "turn_id",
        "outcome",
        "accepted_appends",
        "termination_code",
        "output_reference",
        "continuation_reference",
    }
    with pytest.raises(ValueError, match="completed runtime Turn"):
        RuntimeTurnSettlement(EpisodeId("episode-1"), TurnId("turn-1"), TurnOutcome.COMPLETED, 0, "turn-completed")
    with pytest.raises(ValueError, match="zero or one"):
        RuntimeTurnSettlement(EpisodeId("episode-1"), TurnId("turn-1"), TurnOutcome.FAILED, 2, "failed")


def test_operation_protocol_is_structural_and_cleanup_fails_closed() -> None:
    settlement = RuntimeTurnSettlement(EpisodeId("episode-1"), TurnId("turn-1"), TurnOutcome.CANCELLED, 0, "cancelled")

    class Operation:
        operation_id = "operation-1"

        def wait(self, timeout: float | None = None) -> RuntimeTurnSettlement:
            return settlement

        def cancel(self, reason: str) -> CancellationDisposition:
            return CancellationDisposition.REQUESTED

        def close(self) -> RuntimeOperationCleanup:
            return RuntimeOperationCleanup(
                self.operation_id,
                RuntimeCleanupDisposition.CLEAN,
                "resources-absent",
            )

    operation = Operation()
    assert isinstance(operation, RuntimeOperation)
    assert operation.wait() is settlement
    assert operation.close().verified
    assert not RuntimeOperationCleanup(
        "operation-2",
        RuntimeCleanupDisposition.UNVERIFIED,
        "cleanup-uncertain",
    ).verified


def test_protocol_errors_expose_only_machine_codes() -> None:
    error = RuntimeProtocolError("malformed-frame")

    assert error.code == "malformed-frame"
    assert str(error) == "runtime protocol error: malformed-frame"
    with pytest.raises(ValueError, match="machine token"):
        RuntimeProtocolError("provider said secret=canary")


def test_foundation_imports_with_optional_provider_sdks_blocked() -> None:
    code = r"""
import importlib.abc
import sys

blocked = {'amp', 'anthropic', 'claude_agent_sdk', 'docker', 'e2b', 'gondolin', 'openai'}

class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.', 1)[0] in blocked:
            raise AssertionError(f'optional provider import attempted: {fullname}')
        return None

sys.meta_path.insert(0, Blocker())
from petrus.agenticus.runtime.installation import RuntimeProbeResult
from petrus.agenticus.runtime.operation import RuntimeOperation
from petrus.agenticus.runtime.result import RuntimeTurnSettlement
assert all(value is not None for value in (RuntimeProbeResult, RuntimeOperation, RuntimeTurnSettlement))
"""

    subprocess.run([sys.executable, "-c", code], check=True)
