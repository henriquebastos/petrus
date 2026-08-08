"""Credential-free probe and opt-in authorized acceptance for Claude A2 Local."""

from __future__ import annotations

import os
import secrets
import stat
import time
from hashlib import sha256
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from petrus.agenticus.attachment.binding import MotusAttachmentBinding
from petrus.agenticus.attachment.episode import EpisodeAttachment
from petrus.agenticus.catalog.descriptor import CapabilityDescriptor, DescriptorIdentity, DescriptorKind
from petrus.agenticus.catalog.resolution import ResolutionSnapshot
from petrus.agenticus.connection.custody import (
    AgentConnectionCustody,
    ConnectionIdentity,
    ConnectionStatus,
    OpaqueState,
)
from petrus.agenticus.connection.key import KeyContext, KeyErasureEvidence
from petrus.agenticus.connection.materialization import PrivateFileMaterializer
from petrus.agenticus.connection.storage import SqliteConnectionStorage
from petrus.agenticus.hands.contract import ToolMethod
from petrus.agenticus.hands.gateway import HandsGateway
from petrus.agenticus.hands.grants import CapabilityGrant
from petrus.agenticus.hands.workspace import MotusWorkspaceAdapter
from petrus.agenticus.runtime.claude import (
    CLAUDE_CODE_VERSION,
    CLAUDE_COLLOCATED_HANDS,
    CLAUDE_CONNECTION_CAPABILITIES,
    CLAUDE_CONTINUATION_CAPABILITIES,
    CLAUDE_CONTINUATION_DESCRIPTOR,
    CLAUDE_LOCAL_TERRITORY,
    CLAUDE_PROGRAM_CAPABILITIES,
    CLAUDE_SDK_VERSION,
    ClaudeConnectionCustody,
    ClaudeContinuationCodec,
    ClaudeContinuationPayloadV1,
    ClaudeRuntimeAdapter,
    ClaudeRuntimeConfig,
    ClaudeRuntimeInvocation,
)
from petrus.agenticus.runtime.installation import ProbeDisposition
from petrus.agenticus.runtime.profiles import CLAUDE_A2_LOCAL
from petrus.agenticus.thread.continuation import Continuation, ContinuationState
from petrus.agenticus.thread.identity import ContinuationId, EpisodeId, ThreadId, TurnId
from petrus.agenticus.thread.lifecycle import TurnOutcome
from petrus.motus.execution import EnvironmentSpec
from petrus.motus.execution.archive import workspace_archive
from petrus.motus.execution.providers import LocalProcessEnvironment

_HOST_EFFECT = CapabilityDescriptor(
    DescriptorIdentity(DescriptorKind.EFFECT, "host.fenced", 1),
    frozenset({"effect.host-fenced"}),
)


class _Continuations:
    def __init__(self) -> None:
        self.values: dict[str, ClaudeContinuationPayloadV1] = {}

    def store(self, operation_id: str, payload: ClaudeContinuationPayloadV1) -> str:
        reference = f"live-claude-continuation-{operation_id}"
        current = self.values.get(reference)
        if current is not None and current != payload:
            raise RuntimeError("live Claude Continuation custody conflict")
        self.values[reference] = payload
        return reference

    def load(self, state_reference: str) -> ClaudeContinuationPayloadV1:
        return self.values[state_reference]


class _Turns:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def store_turn(self, operation_id: str, final_text: str) -> str:
        reference = f"live-claude-turn-{operation_id}"
        current = self.values.get(reference)
        if current is not None and current != final_text:
            raise RuntimeError("live Claude Turn custody conflict")
        self.values[reference] = final_text
        return reference


class _Keys:
    def __init__(self) -> None:
        self._key = os.urandom(32)
        self._nonce = 0
        self._erased: set[str] = set()

    def seal(self, context: KeyContext, plaintext: bytearray) -> bytes:
        self._erased.discard(context.connection_id)
        self._nonce += 1
        nonce = self._nonce.to_bytes(12, "big")
        return nonce + AESGCM(self._key).encrypt(nonce, bytes(plaintext), context.authenticated_data())

    def open(self, context: KeyContext, ciphertext: bytes) -> bytearray:
        if context.connection_id in self._erased:
            raise RuntimeError("live Claude connection key is unavailable")
        return bytearray(AESGCM(self._key).decrypt(ciphertext[:12], ciphertext[12:], context.authenticated_data()))

    def erase(self, connection_id: str) -> KeyErasureEvidence:
        self._erased.add(connection_id)
        return KeyErasureEvidence(connection_id, True)


class _NoCustody:
    def materialize(self, *args, **kwargs):
        raise AssertionError("credential-free qualification may not materialize authority")

    def admit_result(self, *args, **kwargs):
        raise AssertionError("credential-free qualification may not admit a result")

    def release(self, *args, **kwargs):
        raise AssertionError("credential-free qualification may not release authority")


def _snapshot() -> ResolutionSnapshot:
    return ResolutionSnapshot(
        1,
        (
            CLAUDE_A2_LOCAL,
            CLAUDE_CONNECTION_CAPABILITIES,
            CLAUDE_PROGRAM_CAPABILITIES,
            CLAUDE_COLLOCATED_HANDS,
            CLAUDE_LOCAL_TERRITORY,
            CLAUDE_CONTINUATION_CAPABILITIES,
            _HOST_EFFECT,
        ),
    )


def _adapter(
    root: Path,
    continuations: _Continuations,
    turns: _Turns,
    custody: ClaudeConnectionCustody,
    *,
    model: str,
) -> ClaudeRuntimeAdapter:
    working = root / "project-binding"
    runtime = root / "runtime"
    working.mkdir(exist_ok=True)
    runtime.mkdir(mode=0o700, exist_ok=True)
    runtime.chmod(0o700)
    return ClaudeRuntimeAdapter(
        ClaudeRuntimeConfig(
            model,
            working,
            runtime,
            host_id="claude-live-host",
            credential_ttl=240,
            wall_timeout=180,
            cancellation_grace=15,
            disconnect_timeout=30,
        ),
        ClaudeContinuationCodec(continuations),
        turns,
        custody,
    )


def _attachment(
    root: Path,
    operation_id: str,
    episode_id: EpisodeId,
    marker: str,
    *,
    prior: EpisodeAttachment | None = None,
) -> tuple[EpisodeAttachment, tuple[HandsGateway, CapabilityGrant]]:
    source = root / f"workspace-{operation_id}"
    source.mkdir()
    (source / "marker.txt").write_text(marker)
    provider = LocalProcessEnvironment()
    binding = MotusAttachmentBinding.open(
        provider,
        f"territory-{operation_id}",
        EnvironmentSpec(),
        workspace_archive_bytes=workspace_archive(source),
        input_digest=f"input-{operation_id}",
    )
    if prior is None:
        attachment = EpisodeAttachment(
            episode_id=episode_id,
            snapshot=_snapshot(),
            binding=binding,
            attachment_id=f"claude-live-attachment-{operation_id}",
            deadline=time.monotonic() + 240,
        )
    else:
        attachment = prior.successor(
            episode_id=episode_id,
            snapshot=_snapshot(),
            binding=binding,
            attachment_id=f"claude-live-attachment-{operation_id}",
            deadline=time.monotonic() + 240,
        )
    workspace = MotusWorkspaceAdapter(provider, binding.execution, test_command=("/usr/bin/true",))
    gateway = attachment.gateway(workspace)
    grant = attachment.grants().open(
        tuple(ToolMethod),
        writable_paths=("output.txt",),
        allowed_argv=(("/usr/bin/true",),),
        deadline=attachment.deadline,
        max_calls=8,
    )
    return attachment, (gateway, grant)


def _read_handoff(source: Path) -> tuple[bytearray, tuple[int, ...]]:
    try:
        before_path = source.lstat()
    except FileNotFoundError:
        pytest.skip("the authorized Claude A2 cell requires its approved disposable API-key handoff")
    except OSError:
        pytest.fail("the approved Claude handoff could not be inspected safely", pytrace=False)
    if (
        not stat.S_ISREG(before_path.st_mode)
        or stat.S_IMODE(before_path.st_mode) != 0o600
        or before_path.st_uid != os.getuid()
        or before_path.st_nlink != 1
    ):
        pytest.fail("the approved Claude handoff failed its private-file custody invariant")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(source, flags)
    except OSError:
        pytest.fail("the approved Claude handoff could not be opened safely", pytrace=False)
    try:
        before = os.fstat(descriptor)
        value = os.read(descriptor, 8193)
        after = os.fstat(descriptor)
    except OSError:
        pytest.fail("the approved Claude handoff could not be read safely", pytrace=False)
    finally:
        os.close(descriptor)
    identity = (
        before.st_dev,
        before.st_ino,
        before.st_mode,
        before.st_uid,
        before.st_nlink,
        before.st_size,
        before.st_mtime_ns,
    )
    if (
        identity
        != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_uid,
            after.st_nlink,
            after.st_size,
            after.st_mtime_ns,
        )
        or not value
        or len(value) > 8192
    ):
        pytest.fail("the approved Claude handoff changed or violated its bound during custody transfer")
    try:
        text = value.decode("utf-8", "strict")
    except UnicodeDecodeError:
        pytest.fail("the approved Claude handoff is not valid runtime authority", pytrace=False)
    if text != text.strip() or any(ord(character) < 32 for character in text):
        pytest.fail("the approved Claude handoff is not valid runtime authority", pytrace=False)
    return bytearray(value), identity


def _consume_handoff(source: Path, expected: tuple[int, ...]) -> None:
    try:
        current = source.lstat()
        identity = (
            current.st_dev,
            current.st_ino,
            current.st_mode,
            current.st_uid,
            current.st_nlink,
            current.st_size,
            current.st_mtime_ns,
        )
        if identity != expected:
            pytest.fail("the approved Claude handoff changed before Agent Connection custody accepted it")
        source.unlink()
        if os.path.lexists(source):
            pytest.fail("the approved Claude handoff was not consumed into Agent Connection custody")
    except OSError:
        pytest.fail("the approved Claude handoff could not be consumed safely", pytrace=False)


@pytest.mark.qualification_installation
@pytest.mark.skipif(
    os.getenv("PETRUS_CV16_CLAUDE_QUALIFY") != "1",
    reason="set PETRUS_CV16_CLAUDE_QUALIFY=1 for the exact credential-free Claude A2 probe",
)
def test_exact_claude_a2_sdk_and_bundled_client(tmp_path: Path) -> None:
    continuations, turns = _Continuations(), _Turns()
    adapter = _adapter(
        tmp_path,
        continuations,
        turns,
        _NoCustody(),
        model=os.getenv("PETRUS_CV16_CLAUDE_MODEL", "claude-sonnet-4-5"),
    )

    probe = adapter.probe()

    assert probe.disposition is ProbeDisposition.READY
    assert probe.installation is not None
    versions = {component.name: component.version for component in probe.installation.components}
    assert versions == {"claude-agent-sdk": CLAUDE_SDK_VERSION, "claude-code": CLAUDE_CODE_VERSION}
    assert not continuations.values and not turns.values


@pytest.mark.real_provider_acceptance
@pytest.mark.timeout(900)
@pytest.mark.skipif(
    os.getenv("PETRUS_CV16_CLAUDE_LIVE") != "1",
    reason="set PETRUS_CV16_CLAUDE_LIVE=1 for the authorized Claude A2 G1→G2 cell",
)
def test_exact_claude_a2_fresh_then_native_resume(tmp_path: Path, request: pytest.FixtureRequest) -> None:
    handoff_name = os.getenv("PETRUS_CV16_CLAUDE_AUTH_FILE")
    if not handoff_name:
        pytest.skip("the authorized Claude A2 cell requires its approved disposable handoff locator")
    handoff = Path(handoff_name)
    authority, handoff_identity = _read_handoff(handoff)
    model = os.getenv("PETRUS_CV16_CLAUDE_MODEL", "claude-sonnet-4-5")

    storage = SqliteConnectionStorage(tmp_path / "installation" / "connections.sqlite3")
    materializer = PrivateFileMaterializer(tmp_path / "installation" / "materialized")
    custody = AgentConnectionCustody(storage, _Keys(), materializer, clock=time.monotonic)
    custody.enroll_host("claude-live-host", operation_id="claude-live-enroll")
    opaque = OpaqueState(authority)
    custody.authorize(
        ConnectionIdentity(
            "claude-live",
            "claude",
            sha256(b"claude-live-account").hexdigest(),
            "api-key",
        ),
        opaque,
        operation_id="claude-live-authorize",
    )
    assert opaque.erased
    authority[:] = b"\0" * len(authority)

    def settle_connection() -> None:
        try:
            current = custody.connection("claude-live")
            if current.status is ConnectionStatus.READY:
                custody.revoke("claude-live", operation_id="claude-live-revoke")
                current = custody.connection("claude-live")
            if current.status is not ConnectionStatus.REAUTHORIZATION_REQUIRED:
                custody.erase("claude-live", operation_id="claude-live-erase")
            if custody.connection("claude-live").status is not ConnectionStatus.REAUTHORIZATION_REQUIRED:
                pytest.fail("the Claude Agent Connection did not finish reauthorization-required")
        except Exception:
            pytest.fail("the Claude Agent Connection cleanup could not be verified", pytrace=False)
        finally:
            storage.close()

    request.addfinalizer(settle_connection)
    continuations, turns = _Continuations(), _Turns()
    adapter = _adapter(tmp_path, continuations, turns, custody, model=model)
    probe = adapter.probe()
    assert probe.disposition is ProbeDisposition.READY
    _consume_handoff(handoff, handoff_identity)

    g1, g2 = (f"CLAUDE_A2_{secrets.token_hex(8).upper()}" for _ in range(2))
    workspace_1 = f"CLAUDE_WORKSPACE_{secrets.token_hex(8).upper()}"
    episode_1 = EpisodeId("claude-live-episode-1")
    attachment_1, (gateway_1, grant_1) = _attachment(tmp_path, "g1", episode_1, workspace_1)
    try:
        operation_1 = adapter.start(
            ClaudeRuntimeInvocation(
                "claude-live-g1",
                episode_1,
                TurnId("claude-live-turn-1"),
                "Use the workspace_read tool to read marker.txt. Then reply with exactly "
                f"{g1}|{workspace_1} and no other text.",
                custody.connection("claude-live"),
                attachment_1,
                gateway_1,
                grant_1.grant_epoch,
            )
        )
        result_1 = operation_1.wait(240)
        assert result_1.outcome is TurnOutcome.COMPLETED and result_1.accepted_appends == 1
        assert operation_1.close().verified
        output_1 = turns.values[result_1.output_reference or ""]
        payload_1 = continuations.values[result_1.continuation_reference or ""]
        assert g1 in output_1 and workspace_1 in output_1
        assert gateway_1.counters().adapter_entries >= 1
    finally:
        settled_1 = attachment_1.settle(drain_timeout=15)
    assert settled_1.settlement.verified
    assert payload_1.transcript not in settled_1.archive
    assert not tuple(adapter._config.runtime_root.iterdir())
    assert not tuple(materializer.root.iterdir())

    workspace_2 = f"CLAUDE_WORKSPACE_{secrets.token_hex(8).upper()}"
    episode_2 = EpisodeId("claude-live-episode-2")
    attachment_2, (gateway_2, grant_2) = _attachment(
        tmp_path,
        "g2",
        episode_2,
        workspace_2,
        prior=attachment_1,
    )
    prior = Continuation(
        ContinuationId("claude-live-continuation-1"),
        ThreadId("claude-live-thread"),
        CLAUDE_CONTINUATION_DESCRIPTOR,
        result_1.continuation_reference or "",
        ContinuationState.IN_USE,
    )
    try:
        operation_2 = adapter.start(
            ClaudeRuntimeInvocation(
                "claude-live-g2",
                episode_2,
                TurnId("claude-live-turn-2"),
                "Recall the exact marker from the prior turn, then use workspace_read to read marker.txt. "
                f"Reply with exactly {g1}|{g2}|{workspace_2} and no other text.",
                custody.connection("claude-live"),
                attachment_2,
                gateway_2,
                grant_2.grant_epoch,
                prior,
            )
        )
        result_2 = operation_2.wait(240)
        assert result_2.outcome is TurnOutcome.COMPLETED and result_2.accepted_appends == 1
        assert operation_2.close().verified
        output_2 = turns.values[result_2.output_reference or ""]
        payload_2 = continuations.values[result_2.continuation_reference or ""]
        assert payload_2.session_id == payload_1.session_id
        assert g1 in output_2 and g2 in output_2 and workspace_2 in output_2
        assert output_2.index(g1) < output_2.index(g2) < output_2.index(workspace_2)
        assert gateway_2.counters().adapter_entries >= 1
    finally:
        settled_2 = attachment_2.settle(drain_timeout=15)
    assert settled_2.settlement.verified
    assert payload_2.transcript not in settled_2.archive
    assert not tuple(adapter._config.runtime_root.iterdir())
    assert not tuple(materializer.root.iterdir())
    assert all(lease.released for lease in storage.load().leases)
    assert custody.connection("claude-live").state_version == 1

    revoked = custody.revoke("claude-live", operation_id="claude-live-revoke")
    assert revoked.connection.status is ConnectionStatus.REVOKED
    erased = custody.erase("claude-live", operation_id="claude-live-erase")
    assert erased.connection.status is ConnectionStatus.REAUTHORIZATION_REQUIRED
