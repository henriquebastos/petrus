"""Credential-free probe and opt-in authorized acceptance for Pi A2 Local."""

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
from petrus.agenticus.runtime.installation import ProbeDisposition
from petrus.agenticus.runtime.pi import (
    PI_AI_VERSION,
    PI_CC_PATCH_CONNECTION_CAPABILITIES,
    PI_CC_PATCH_VERSION,
    PI_COLLOCATED_HANDS,
    PI_CONNECTION_CAPABILITIES,
    PI_CONTINUATION_CAPABILITIES,
    PI_CONTINUATION_DESCRIPTOR,
    PI_LOCAL_TERRITORY,
    PI_PROGRAM_CAPABILITIES,
    PI_SDK_VERSION,
    PI_SUBSCRIPTION_CONNECTION_CAPABILITIES,
    PiConnectionCustody,
    PiContinuationCodec,
    PiContinuationPayloadV1,
    PiRuntimeAdapter,
    PiRuntimeConfig,
    PiRuntimeInvocation,
)
from petrus.agenticus.runtime.profiles import PI_NATIVE_A2_LOCAL
from petrus.agenticus.thread.continuation import Continuation, ContinuationState
from petrus.agenticus.thread.identity import ContinuationId, EpisodeId, ThreadId, TurnId
from petrus.agenticus.thread.lifecycle import TurnOutcome
from petrus.motus.execution import EnvironmentSpec
from petrus.motus.execution.archive import workspace_archive
from petrus.motus.execution.providers import LocalProcessEnvironment

_HOST_EFFECT = CapabilityDescriptor(
    DescriptorIdentity(DescriptorKind.EFFECT, "host.fenced", 1), frozenset({"effect.host-fenced"})
)
_SAFE_CAPABILITIES = frozenset({"runtime.cancel", "runtime.continue", "runtime.local", "runtime.harness-owned"})


class _Continuations:
    def __init__(self) -> None:
        self.values: dict[str, PiContinuationPayloadV1] = {}

    def store(self, operation_id: str, payload: PiContinuationPayloadV1) -> str:
        reference = f"live-pi-continuation-{operation_id}"
        current = self.values.get(reference)
        if current is not None and current != payload:
            raise RuntimeError("live Pi Continuation custody conflict")
        self.values[reference] = payload
        return reference

    def load(self, state_reference: str) -> PiContinuationPayloadV1:
        return self.values[state_reference]


class _Turns:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def store_turn(self, operation_id: str, final_text: str) -> str:
        reference = f"live-pi-turn-{operation_id}"
        current = self.values.get(reference)
        if current is not None and current != final_text:
            raise RuntimeError("live Pi Turn custody conflict")
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
            raise RuntimeError("live Pi connection key is unavailable")
        return bytearray(AESGCM(self._key).decrypt(ciphertext[:12], ciphertext[12:], context.authenticated_data()))

    def erase(self, connection_id: str) -> KeyErasureEvidence:
        self._erased.add(connection_id)
        return KeyErasureEvidence(connection_id, True)


class _NoCustody:
    def materialize(self, *args, **kwargs):
        raise AssertionError("credential-free qualification may not materialize authority")

    def activate(self, *args, **kwargs):
        raise AssertionError("credential-free qualification may not activate authority")

    def admit_result(self, *args, **kwargs):
        raise AssertionError("credential-free qualification may not admit a result")

    def checkpoint(self, *args, **kwargs):
        raise AssertionError("credential-free qualification may not checkpoint authority")

    def release(self, *args, **kwargs):
        raise AssertionError("credential-free qualification may not release authority")


def _snapshot(
    connection: CapabilityDescriptor = PI_CONNECTION_CAPABILITIES,
) -> ResolutionSnapshot:
    return ResolutionSnapshot(
        1,
        (
            PI_NATIVE_A2_LOCAL,
            connection,
            PI_PROGRAM_CAPABILITIES,
            PI_COLLOCATED_HANDS,
            PI_LOCAL_TERRITORY,
            PI_CONTINUATION_CAPABILITIES,
            _HOST_EFFECT,
        ),
    )


def _adapter(
    root: Path,
    continuations: _Continuations,
    turns: _Turns,
    custody: PiConnectionCustody,
    *,
    provider: str,
    model: str,
    cc_patch: bool = False,
) -> PiRuntimeAdapter:
    working, runtime = root / "project-binding", root / "runtime"
    working.mkdir(exist_ok=True)
    runtime.mkdir(mode=0o700, exist_ok=True)
    runtime.chmod(0o700)
    return PiRuntimeAdapter(
        PiRuntimeConfig(
            provider,
            model,
            working,
            runtime,
            host_id="pi-live-host",
            cc_patch=cc_patch,
            credential_ttl=240,
            wall_timeout=180,
            cancellation_grace=15,
        ),
        PiContinuationCodec(continuations),
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
    connection: CapabilityDescriptor = PI_CONNECTION_CAPABILITIES,
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
            snapshot=_snapshot(connection),
            binding=binding,
            attachment_id=f"pi-live-attachment-{operation_id}",
            deadline=time.monotonic() + 240,
        )
    else:
        attachment = prior.successor(
            episode_id=episode_id,
            snapshot=_snapshot(connection),
            binding=binding,
            attachment_id=f"pi-live-attachment-{operation_id}",
            deadline=time.monotonic() + 240,
        )
    gateway = attachment.gateway(MotusWorkspaceAdapter(provider, binding.execution, test_command=("/usr/bin/true",)))
    grant = attachment.grants().open(
        (ToolMethod.WORKSPACE_READ,),
        writable_paths=(),
        allowed_argv=(),
        deadline=attachment.deadline,
        max_calls=4,
    )
    return attachment, (gateway, grant)


def _read_handoff(
    source: Path,
    *,
    maximum: int = 8192,
    require_api_key_text: bool = True,
) -> tuple[bytearray, tuple[int, ...]]:
    try:
        path_metadata = source.lstat()
    except OSError:
        pytest.fail("the approved Pi handoff could not be inspected safely", pytrace=False)
    if (
        not stat.S_ISREG(path_metadata.st_mode)
        or stat.S_IMODE(path_metadata.st_mode) != 0o600
        or path_metadata.st_uid != os.getuid()
        or path_metadata.st_nlink != 1
    ):
        pytest.fail("the approved Pi handoff failed its private-file custody invariant", pytrace=False)
    try:
        descriptor = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        pytest.fail("the approved Pi handoff could not be opened safely", pytrace=False)
    try:
        before = os.fstat(descriptor)
        value = os.read(descriptor, maximum + 1)
        after = os.fstat(descriptor)
    except OSError:
        pytest.fail("the approved Pi handoff could not be read safely", pytrace=False)
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
        or len(value) > maximum
    ):
        pytest.fail("the approved Pi handoff changed or violated its bound during custody transfer", pytrace=False)
    if require_api_key_text:
        try:
            text = value.decode("utf-8", "strict")
        except UnicodeDecodeError:
            pytest.fail("the approved Pi handoff is not valid runtime authority", pytrace=False)
        if text != text.strip() or any(ord(character) < 32 for character in text):
            pytest.fail("the approved Pi handoff is not valid runtime authority", pytrace=False)
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
            pytest.fail("the approved Pi handoff changed before Agent Connection custody accepted it", pytrace=False)
        source.unlink()
        if os.path.lexists(source):
            pytest.fail("the approved Pi handoff was not consumed into Agent Connection custody", pytrace=False)
    except OSError:
        pytest.fail("the approved Pi handoff could not be consumed safely", pytrace=False)


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        pytest.fail("live Pi qualification requires every explicit authority coordinate", pytrace=False)
    return value


@pytest.mark.qualification_installation
@pytest.mark.skipif(
    os.getenv("PETRUS_CV16_PI_QUALIFY") != "1",
    reason="set PETRUS_CV16_PI_QUALIFY=1 for the exact credential-free Pi A2 probe",
)
def test_exact_pi_a2_sdk_ai_and_node(tmp_path: Path) -> None:
    provider = _required("PETRUS_CV16_PI_PROVIDER")
    model = _required("PETRUS_CV16_PI_MODEL")
    profile = os.getenv("PETRUS_CV16_PI_AUTH_PROFILE", "api-key")
    if profile not in {"api-key", "subscription", "cc-patch-subscription"}:
        pytest.fail("Pi qualification requires an exact authority profile", pytrace=False)
    cc_patch = profile == "cc-patch-subscription"
    continuations, turns = _Continuations(), _Turns()
    adapter = _adapter(
        tmp_path,
        continuations,
        turns,
        _NoCustody(),
        provider=provider,
        model=model,
        cc_patch=cc_patch,
    )

    probe = adapter.probe()

    assert probe.disposition is ProbeDisposition.READY
    assert probe.installation is not None
    versions = {component.name: component.version for component in probe.installation.components}
    assert set(versions) == {"pi-coding-agent", "pi-ai", "node", *({"pi-cc-patch"} if cc_patch else set())}
    assert versions["pi-coding-agent"] == PI_SDK_VERSION == "0.83.0"
    assert versions["pi-ai"] == PI_AI_VERSION == "0.83.0"
    if cc_patch:
        assert versions["pi-cc-patch"] == PI_CC_PATCH_VERSION == "1.0.1"
    assert tuple(map(int, versions["node"].split("."))) >= (22, 19, 0)
    assert probe.installation.capabilities == _SAFE_CAPABILITIES
    assert not continuations.values and not turns.values
    assert not tuple(adapter._config.runtime_root.iterdir())


@pytest.mark.real_provider_acceptance
@pytest.mark.timeout(900)
@pytest.mark.skipif(
    os.getenv("PETRUS_CV16_PI_LIVE") != "1",
    reason="set PETRUS_CV16_PI_LIVE=1 for the authorized Pi A2 G1→G2 cell",
)
def test_exact_pi_a2_fresh_then_native_resume(tmp_path: Path, request: pytest.FixtureRequest) -> None:
    handoff = Path(_required("PETRUS_CV16_PI_AUTH_FILE"))
    provider, model = _required("PETRUS_CV16_PI_PROVIDER"), _required("PETRUS_CV16_PI_MODEL")
    profile = os.getenv("PETRUS_CV16_PI_AUTH_PROFILE", "api-key")
    if profile not in {"api-key", "subscription", "cc-patch-subscription"}:
        pytest.fail("live Pi qualification requires an exact authority profile", pytrace=False)
    subscription = profile != "api-key"
    authority, handoff_identity = _read_handoff(
        handoff,
        maximum=1_000_000 if subscription else 8192,
        require_api_key_text=not subscription,
    )
    connection_capabilities = (
        PI_CC_PATCH_CONNECTION_CAPABILITIES
        if profile == "cc-patch-subscription"
        else PI_SUBSCRIPTION_CONNECTION_CAPABILITIES
        if subscription
        else PI_CONNECTION_CAPABILITIES
    )
    storage = SqliteConnectionStorage(tmp_path / "installation" / "connections.sqlite3")
    materializer = PrivateFileMaterializer(tmp_path / "installation" / "materialized")
    custody = AgentConnectionCustody(storage, _Keys(), materializer, clock=time.monotonic)
    custody.enroll_host("pi-live-host", operation_id="pi-live-enroll")
    opaque = OpaqueState(authority)
    custody.authorize(
        ConnectionIdentity("pi-live", provider, sha256(b"pi-live-account").hexdigest(), profile),
        opaque,
        operation_id="pi-live-authorize",
    )
    assert opaque.erased
    authority[:] = b"\0" * len(authority)
    attachments: list[EpisodeAttachment] = []

    def cleanup() -> None:
        try:
            for attachment in reversed(attachments):
                if not attachment.settled:
                    attachment.settle(drain_timeout=15)
            current = custody.connection("pi-live")
            if current.status is ConnectionStatus.READY:
                custody.revoke("pi-live", operation_id="pi-live-revoke")
                current = custody.connection("pi-live")
            if current.status is not ConnectionStatus.REAUTHORIZATION_REQUIRED:
                custody.erase("pi-live", operation_id="pi-live-erase")
            assert custody.connection("pi-live").status is ConnectionStatus.REAUTHORIZATION_REQUIRED
            assert not tuple(materializer.root.iterdir())
            runtime_root = tmp_path / "runtime"
            assert not runtime_root.exists() or not tuple(runtime_root.iterdir())
        finally:
            storage.close()

    request.addfinalizer(cleanup)
    continuations, turns = _Continuations(), _Turns()
    adapter = _adapter(
        tmp_path,
        continuations,
        turns,
        custody,
        provider=provider,
        model=model,
        cc_patch=profile == "cc-patch-subscription",
    )
    assert adapter.probe().disposition is ProbeDisposition.READY
    _consume_handoff(handoff, handoff_identity)

    g1, g2 = (f"PI_A2_{secrets.token_hex(8).upper()}" for _ in range(2))
    workspace_1 = f"PI_WORKSPACE_{secrets.token_hex(8).upper()}"
    episode_1 = EpisodeId("pi-live-episode-1")
    attachment_1, (gateway_1, grant_1) = _attachment(
        tmp_path, "g1", episode_1, workspace_1, connection=connection_capabilities
    )
    attachments.append(attachment_1)
    operation_1 = adapter.start(
        PiRuntimeInvocation(
            "pi-live-g1",
            episode_1,
            TurnId("pi-live-turn-1"),
            f"Use workspace_read to read marker.txt. Reply with exactly {g1}|{workspace_1} and no other text.",
            custody.connection("pi-live"),
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
    settled_1 = attachment_1.settle(drain_timeout=15)
    assert settled_1.settlement.verified and payload_1.session_jsonl not in settled_1.archive
    assert not tuple(adapter._config.runtime_root.iterdir()) and not tuple(materializer.root.iterdir())

    workspace_2 = f"PI_WORKSPACE_{secrets.token_hex(8).upper()}"
    episode_2 = EpisodeId("pi-live-episode-2")
    attachment_2, (gateway_2, grant_2) = _attachment(
        tmp_path,
        "g2",
        episode_2,
        workspace_2,
        prior=attachment_1,
        connection=connection_capabilities,
    )
    attachments.append(attachment_2)
    prior = Continuation(
        ContinuationId("pi-live-continuation-1"),
        ThreadId("pi-live-thread"),
        PI_CONTINUATION_DESCRIPTOR,
        result_1.continuation_reference or "",
        ContinuationState.IN_USE,
    )
    operation_2 = adapter.start(
        PiRuntimeInvocation(
            "pi-live-g2",
            episode_2,
            TurnId("pi-live-turn-2"),
            "Recall the exact marker from the prior turn, then use workspace_read to read marker.txt. "
            f"Reply with exactly {g1}|{g2}|{workspace_2} and no other text.",
            custody.connection("pi-live"),
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
    assert output_2.index(g1) < output_2.index(g2) < output_2.index(workspace_2)
    assert gateway_2.counters().adapter_entries >= 1
    settled_2 = attachment_2.settle(drain_timeout=15)
    assert settled_2.settlement.verified and payload_2.session_jsonl not in settled_2.archive
    assert not tuple(adapter._config.runtime_root.iterdir()) and not tuple(materializer.root.iterdir())
    assert all(lease.released for lease in storage.load().leases)
    assert custody.connection("pi-live").state_version == (3 if subscription else 1)

    assert custody.revoke("pi-live", operation_id="pi-live-revoke").connection.status is ConnectionStatus.REVOKED
    erased = custody.erase("pi-live", operation_id="pi-live-erase")
    assert erased.connection.status is ConnectionStatus.REAUTHORIZATION_REQUIRED
    assert erased.connection.state_version == (4 if subscription else 2)
