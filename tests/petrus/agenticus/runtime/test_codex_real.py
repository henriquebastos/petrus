"""Opt-in authorized acceptance for the exact Codex A2 Local lane."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
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
from petrus.agenticus.runtime.codex import (
    CODEX_COLLOCATED_HANDS,
    CODEX_CONNECTION_CAPABILITIES,
    CODEX_CONTINUATION_CAPABILITIES,
    CODEX_CONTINUATION_DESCRIPTOR,
    CODEX_GONDOLIN_BUILD_ID,
    CODEX_GONDOLIN_IMAGE_REF,
    CODEX_GONDOLIN_TERRITORY,
    CODEX_GONDOLIN_VERSION,
    CODEX_LOCAL_TERRITORY,
    CODEX_PROGRAM_CAPABILITIES,
    CODEX_VERSION,
    CodexContinuationCodec,
    CodexContinuationPayloadV1,
    CodexGondolinRuntimeAdapter,
    CodexRuntimeAdapter,
    CodexRuntimeConfig,
    CodexRuntimeInvocation,
)
from petrus.agenticus.runtime.installation import ProbeDisposition
from petrus.agenticus.runtime.profiles import CODEX_A2_LOCAL, CODEX_A3_GONDOLIN
from petrus.agenticus.thread.continuation import Continuation, ContinuationState
from petrus.agenticus.thread.identity import ContinuationId, EpisodeId, ThreadId, TurnId
from petrus.agenticus.thread.lifecycle import TurnOutcome
from petrus.motus.execution import EnvironmentCapability, EnvironmentSpec
from petrus.motus.execution.archive import workspace_archive
from petrus.motus.execution.gondolin import GondolinEnvironment
from petrus.motus.execution.providers import LocalProcessEnvironment

_G1 = "CODEX_A2_G1_20260803"
_G2 = "CODEX_A2_G2_20260803"
_A3_G1 = "CODEX_A3_G1_20260803"
_A3_G2 = "CODEX_A3_G2_20260803"
_HOST_EFFECT = CapabilityDescriptor(
    DescriptorIdentity(DescriptorKind.EFFECT, "host.fenced", 1),
    frozenset({"effect.host-fenced"}),
)


class _Continuations:
    def __init__(self) -> None:
        self.values: dict[str, CodexContinuationPayloadV1] = {}

    def store(self, operation_id: str, payload: CodexContinuationPayloadV1) -> str:
        reference = f"live-continuation-{operation_id}"
        existing = self.values.get(reference)
        if existing is not None and existing != payload:
            raise RuntimeError("conflicting live Continuation candidate")
        self.values[reference] = payload
        return reference

    def load(self, state_reference: str) -> CodexContinuationPayloadV1:
        return self.values[state_reference]


class _Turns:
    def __init__(self) -> None:
        self.values: dict[str, tuple[str, str]] = {}

    def store_turn(self, operation_id: str, thread_id: str, final_text: str) -> str:
        reference = f"live-turn-{operation_id}"
        value = (thread_id, final_text)
        existing = self.values.get(reference)
        if existing is not None and existing != value:
            raise RuntimeError("conflicting live Turn candidate")
        self.values[reference] = value
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
            raise RuntimeError("live connection key is unavailable")
        return bytearray(AESGCM(self._key).decrypt(ciphertext[:12], ciphertext[12:], context.authenticated_data()))

    def erase(self, connection_id: str) -> KeyErasureEvidence:
        self._erased.add(connection_id)
        return KeyErasureEvidence(connection_id, True)


def _snapshot() -> ResolutionSnapshot:
    return ResolutionSnapshot(
        1,
        (
            CODEX_A2_LOCAL,
            CODEX_CONNECTION_CAPABILITIES,
            CODEX_PROGRAM_CAPABILITIES,
            CODEX_COLLOCATED_HANDS,
            CODEX_LOCAL_TERRITORY,
            CODEX_CONTINUATION_CAPABILITIES,
            _HOST_EFFECT,
        ),
    )


def _gondolin_snapshot() -> ResolutionSnapshot:
    return ResolutionSnapshot(
        1,
        (
            CODEX_A3_GONDOLIN,
            CODEX_CONNECTION_CAPABILITIES,
            CODEX_PROGRAM_CAPABILITIES,
            CODEX_COLLOCATED_HANDS,
            CODEX_GONDOLIN_TERRITORY,
            CODEX_CONTINUATION_CAPABILITIES,
            _HOST_EFFECT,
        ),
    )


def _opaque_file_auth(source: Path) -> tuple[bytes, tuple[int, ...]]:
    try:
        metadata = source.lstat()
    except FileNotFoundError:
        pytest.skip("the authorized Gondolin cell requires its explicitly selected opaque file auth")
    except OSError:
        pytest.fail("the selected opaque file auth could not be inspected safely", pytrace=False)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_uid != os.getuid()
        or metadata.st_nlink != 1
    ):
        pytest.fail("the selected opaque file auth failed its custody invariant")
    try:
        descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        pytest.fail("the selected opaque file auth could not be opened safely", pytrace=False)
    try:
        try:
            before = os.fstat(descriptor)
            value = os.read(descriptor, 1_000_001)
            after = os.fstat(descriptor)
        except OSError:
            pytest.fail("the selected opaque file auth could not be read safely", pytrace=False)
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
        or len(value) > 1_000_000
    ):
        pytest.fail("the selected opaque file auth changed or violated its bound during custody transfer")
    return value, identity


def _consume_opaque_file_auth(source: Path, expected_identity: tuple[int, ...]) -> None:
    try:
        metadata = source.lstat()
        identity = (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_mode,
            metadata.st_uid,
            metadata.st_nlink,
            metadata.st_size,
            metadata.st_mtime_ns,
        )
        if identity != expected_identity:
            pytest.fail("the selected opaque file auth changed before Agent Connection custody accepted it")
        source.unlink()
        if os.path.lexists(source):
            pytest.fail("the selected opaque file auth was not consumed into Agent Connection custody")
    except OSError:
        pytest.fail(
            "the selected opaque file auth could not be consumed into Agent Connection custody",
            pytrace=False,
        )


def _official_file_auth(tmp_path: Path, executable: Path) -> bytes:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("the authorized Codex A2 cell requires OPENAI_API_KEY for one-time official file login")
    home = tmp_path / "login-handoff"
    home.mkdir(mode=0o700)
    environment = {
        "HOME": str(home),
        "CODEX_HOME": str(home),
        "LANG": "C.UTF-8",
        "PATH": os.pathsep.join(
            dict.fromkeys((str(executable.parent), str(Path(shutil.which("node") or "").parent), os.defpath))
        ),
    }
    login = subprocess.run(
        (str(executable), "login", "--with-api-key"),
        input=api_key.encode() + b"\n",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
        timeout=30,
    )
    if login.returncode != 0:
        pytest.fail("official Codex file-auth bootstrap failed")
    auth = home / "auth.json"
    try:
        metadata = auth.lstat()
    except FileNotFoundError:
        pytest.fail("official Codex file-auth bootstrap produced no handoff")
    if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_nlink != 1:
        pytest.fail("official Codex file-auth handoff failed its private-file invariant")
    descriptor = os.open(auth, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        value = os.read(descriptor, 1_000_001)
    finally:
        os.close(descriptor)
    if not value or len(value) > 1_000_000:
        pytest.fail("official Codex file-auth handoff is outside the accepted bound")
    auth.unlink()
    shutil.rmtree(home)
    return value


def _binding(tmp_path: Path, operation_id: str) -> MotusAttachmentBinding:
    workspace = tmp_path / f"workspace-{operation_id}"
    workspace.mkdir()
    return MotusAttachmentBinding.open(
        LocalProcessEnvironment(),
        f"territory-{operation_id}",
        EnvironmentSpec(required_capabilities=frozenset({EnvironmentCapability.PRIVATE_FILE_TRANSFER.value})),
        workspace_archive_bytes=workspace_archive(workspace),
        input_digest=f"input-{operation_id}",
    )


def _gondolin_binding(
    tmp_path: Path,
    operation_id: str,
    provider: GondolinEnvironment,
    image: str,
) -> MotusAttachmentBinding:
    workspace = tmp_path / f"workspace-{operation_id}"
    workspace.mkdir()
    return MotusAttachmentBinding.open(
        provider,
        f"territory-{operation_id}",
        EnvironmentSpec(
            image=image,
            required_capabilities=frozenset(
                {
                    EnvironmentCapability.VM.value,
                    EnvironmentCapability.MICROVM.value,
                    EnvironmentCapability.PRIVATE_FILE_TRANSFER.value,
                }
            ),
        ),
        workspace_archive_bytes=workspace_archive(workspace),
        input_digest=f"input-{operation_id}",
    )


@pytest.mark.real_provider_acceptance
@pytest.mark.skipif(
    os.getenv("PETRUS_CV16_CODEX_LIVE") != "1",
    reason="set PETRUS_CV16_CODEX_LIVE=1 for the authorized Codex A2 Local cell",
)
def test_exact_codex_a2_local_fresh_then_native_resume(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    configured = os.getenv("PETRUS_CV16_CODEX_BIN")
    executable_name = configured or shutil.which("codex")
    if executable_name is None:
        pytest.skip("the exact Codex CLI is not installed")
    executable = Path(executable_name).absolute()
    auth = _official_file_auth(tmp_path, executable)

    storage = SqliteConnectionStorage(tmp_path / "installation" / "connections.sqlite3")
    materializer = PrivateFileMaterializer(tmp_path / "installation" / "materialized")
    custody = AgentConnectionCustody(storage, _Keys(), materializer, clock=time.monotonic)
    custody.enroll_host("codex-live-host", operation_id="codex-live-enroll")
    opaque = OpaqueState(auth)
    custody.authorize(
        ConnectionIdentity("codex-live", "codex", sha256(b"codex-live-account").hexdigest(), "file-auth"),
        opaque,
        operation_id="codex-live-authorize",
    )
    assert opaque.erased

    continuations, turns = _Continuations(), _Turns()
    adapter = CodexRuntimeAdapter(
        CodexRuntimeConfig(
            "codex-live-host",
            credential_ttl=240,
            command_timeout=180,
            cancellation_grace=10,
        ),
        CodexContinuationCodec(continuations),
        turns,
        custody,
    )
    system_which = shutil.which
    monkeypatch.setattr(shutil, "which", lambda name: str(executable) if name == "codex" else system_which(name))
    probe = adapter.probe()
    assert probe.disposition is ProbeDisposition.READY
    assert probe.installation is not None and probe.installation.components[0].version == CODEX_VERSION

    episode_1 = EpisodeId("codex-live-episode-1")
    attachment_1 = EpisodeAttachment(
        episode_id=episode_1,
        snapshot=_snapshot(),
        binding=_binding(tmp_path, "g1"),
        attachment_id="codex-live-attachment-1",
        deadline=time.monotonic() + 240,
    )
    operation_1 = adapter.start(
        CodexRuntimeInvocation(
            "codex-live-g1",
            episode_1,
            TurnId("codex-live-turn-1"),
            f"Reply with exactly {_G1}. Do not run commands or use tools.",
            custody.connection("codex-live"),
            attachment_1,
        )
    )
    result_1 = operation_1.wait(240)
    assert result_1.outcome is TurnOutcome.COMPLETED and result_1.accepted_appends == 1
    assert operation_1.close().verified
    output_1 = turns.values[result_1.output_reference or ""][1]
    payload_1 = continuations.values[result_1.continuation_reference or ""]
    assert _G1 in output_1 and payload_1.thread_id
    settled_1 = attachment_1.settle(drain_timeout=10)
    assert (
        settled_1.settlement.verified and auth not in settled_1.archive and payload_1.rollout not in settled_1.archive
    )

    episode_2 = EpisodeId("codex-live-episode-2")
    attachment_2 = attachment_1.successor(
        episode_id=episode_2,
        snapshot=_snapshot(),
        binding=_binding(tmp_path, "g2"),
        attachment_id="codex-live-attachment-2",
        deadline=time.monotonic() + 240,
    )
    prior = Continuation(
        ContinuationId("codex-live-continuation-1"),
        ThreadId("codex-live-thread"),
        CODEX_CONTINUATION_DESCRIPTOR,
        result_1.continuation_reference or "",
        ContinuationState.IN_USE,
    )
    operation_2 = adapter.start(
        CodexRuntimeInvocation(
            "codex-live-g2",
            episode_2,
            TurnId("codex-live-turn-2"),
            f"State the prior marker, then {_G2}. Do not run commands or use tools.",
            custody.connection("codex-live"),
            attachment_2,
            prior,
        )
    )
    result_2 = operation_2.wait(240)
    assert result_2.outcome is TurnOutcome.COMPLETED and result_2.accepted_appends == 1
    assert operation_2.close().verified
    output_2 = turns.values[result_2.output_reference or ""][1]
    payload_2 = continuations.values[result_2.continuation_reference or ""]
    assert payload_2.thread_id == payload_1.thread_id
    assert _G1 in output_2 and _G2 in output_2 and output_2.index(_G1) < output_2.index(_G2)
    settled_2 = attachment_2.settle(drain_timeout=10)
    assert (
        settled_2.settlement.verified and auth not in settled_2.archive and payload_2.rollout not in settled_2.archive
    )
    assert custody.connection("codex-live").state_version == 3
    assert not tuple(materializer.root.iterdir())

    custody.revoke("codex-live", operation_id="codex-live-revoke")
    erased = custody.erase("codex-live", operation_id="codex-live-erase")
    assert erased.connection.status is ConnectionStatus.REAUTHORIZATION_REQUIRED
    storage.close()


@pytest.mark.real_gondolin_acceptance
@pytest.mark.skipif(
    os.getenv("PETRUS_CV16_CODEX_GONDOLIN_LIVE") != "1",
    reason="set PETRUS_CV16_CODEX_GONDOLIN_LIVE=1 for the authorized Codex A3 Gondolin cell",
)
def test_exact_codex_a3_gondolin_fresh_then_native_resume(
    tmp_path: Path,
    request: pytest.FixtureRequest,
) -> None:
    sdk = os.getenv("PETRUS_REAL_GONDOLIN_SDK_MODULE")
    image = os.getenv("PETRUS_REAL_GONDOLIN_IMAGE")
    auth_name = os.getenv("PETRUS_CV16_CODEX_AUTH_FILE")
    if not sdk or not image or not auth_name:
        pytest.skip("the authorized Codex A3 cell requires the selected Gondolin SDK, image, and opaque auth")
    if image != CODEX_GONDOLIN_IMAGE_REF or os.getenv("PETRUS_REAL_GONDOLIN_BUILD_ID") != CODEX_GONDOLIN_BUILD_ID:
        pytest.skip("the authorized Codex A3 cell requires the exact selected immutable image build")
    auth_source = Path(auth_name)
    auth, original_auth_identity = _opaque_file_auth(auth_source)

    storage = SqliteConnectionStorage(tmp_path / "installation" / "connections.sqlite3")
    materializer = PrivateFileMaterializer(tmp_path / "installation" / "materialized")
    custody = AgentConnectionCustody(storage, _Keys(), materializer, clock=time.monotonic)
    custody.enroll_host("codex-gondolin-host", operation_id="codex-gondolin-enroll")
    opaque = OpaqueState(auth)
    custody.authorize(
        ConnectionIdentity("codex-gondolin", "codex", sha256(b"codex-gondolin-account").hexdigest(), "file-auth"),
        opaque,
        operation_id="codex-gondolin-authorize",
    )
    assert opaque.erased

    def erase_custody() -> None:
        try:
            custody.revoke("codex-gondolin", operation_id="codex-gondolin-revoke")
            erased = custody.erase("codex-gondolin", operation_id="codex-gondolin-erase")
            if erased.connection.status is not ConnectionStatus.REAUTHORIZATION_REQUIRED:
                pytest.fail("the Gondolin Agent Connection did not finish in reauthorization-required state")
        except Exception:
            pytest.fail("the Gondolin Agent Connection cleanup could not be verified", pytrace=False)

    request.addfinalizer(storage.close)
    request.addfinalizer(erase_custody)
    _consume_opaque_file_auth(auth_source, original_auth_identity)

    continuations, turns = _Continuations(), _Turns()
    adapter = CodexGondolinRuntimeAdapter(
        CodexRuntimeConfig(
            "codex-gondolin-host",
            credential_ttl=300,
            command_timeout=240,
            cancellation_grace=15,
        ),
        CodexContinuationCodec(continuations),
        turns,
        custody,
    )
    provider = GondolinEnvironment(tmp_path / "gondolin", sdk_module=sdk, lease_ttl=600, startup_timeout=120)

    binding_1 = _gondolin_binding(tmp_path, "a3-g1", provider, image)
    episode_1 = EpisodeId("codex-gondolin-episode-1")
    attachment_1 = EpisodeAttachment(
        episode_id=episode_1,
        snapshot=_gondolin_snapshot(),
        binding=binding_1,
        attachment_id="codex-gondolin-attachment-1",
        deadline=time.monotonic() + 300,
    )
    try:
        probe_1 = adapter.probe(attachment_1)
        assert probe_1.disposition is ProbeDisposition.READY
        assert probe_1.installation is not None
        assert probe_1.installation.components[0].version == CODEX_GONDOLIN_VERSION
        operation_1 = adapter.start(
            CodexRuntimeInvocation(
                "codex-gondolin-g1",
                episode_1,
                TurnId("codex-gondolin-turn-1"),
                f"Reply with exactly {_A3_G1}. Do not run commands or use tools.",
                custody.connection("codex-gondolin"),
                attachment_1,
            )
        )
        result_1 = operation_1.wait(300)
        assert result_1.outcome is TurnOutcome.COMPLETED and result_1.accepted_appends == 1
        assert operation_1.close().verified
        output_1 = turns.values[result_1.output_reference or ""][1]
        payload_1 = continuations.values[result_1.continuation_reference or ""]
        if _A3_G1 not in output_1 or not payload_1.thread_id:
            pytest.fail("the first Gondolin Codex marker or native thread identity was absent")
    finally:
        settled_1 = attachment_1.settle(drain_timeout=15)
    assert settled_1.settlement.verified
    if auth in settled_1.archive or payload_1.rollout in settled_1.archive:
        pytest.fail("private Codex state entered the first Gondolin workspace archive")
    assert not any((tmp_path / "gondolin").iterdir())

    binding_2 = _gondolin_binding(tmp_path, "a3-g2", provider, image)
    episode_2 = EpisodeId("codex-gondolin-episode-2")
    attachment_2 = attachment_1.successor(
        episode_id=episode_2,
        snapshot=_gondolin_snapshot(),
        binding=binding_2,
        attachment_id="codex-gondolin-attachment-2",
        deadline=time.monotonic() + 300,
    )
    prior = Continuation(
        ContinuationId("codex-gondolin-continuation-1"),
        ThreadId("codex-gondolin-thread"),
        CODEX_CONTINUATION_DESCRIPTOR,
        result_1.continuation_reference or "",
        ContinuationState.IN_USE,
    )
    try:
        probe_2 = adapter.probe(attachment_2)
        assert probe_2.disposition is ProbeDisposition.READY
        operation_2 = adapter.start(
            CodexRuntimeInvocation(
                "codex-gondolin-g2",
                episode_2,
                TurnId("codex-gondolin-turn-2"),
                f"State the prior marker, then {_A3_G2}. Do not run commands or use tools.",
                custody.connection("codex-gondolin"),
                attachment_2,
                prior,
            )
        )
        result_2 = operation_2.wait(300)
        assert result_2.outcome is TurnOutcome.COMPLETED and result_2.accepted_appends == 1
        assert operation_2.close().verified
        output_2 = turns.values[result_2.output_reference or ""][1]
        payload_2 = continuations.values[result_2.continuation_reference or ""]
        if payload_2.thread_id != payload_1.thread_id:
            pytest.fail("the Gondolin Codex native thread identity changed across Episodes")
        if _A3_G1 not in output_2 or _A3_G2 not in output_2 or output_2.index(_A3_G1) >= output_2.index(_A3_G2):
            pytest.fail("the resumed Gondolin Codex marker order was not preserved")
    finally:
        settled_2 = attachment_2.settle(drain_timeout=15)
    assert settled_2.settlement.verified
    if auth in settled_2.archive or payload_2.rollout in settled_2.archive:
        pytest.fail("private Codex state entered the second Gondolin workspace archive")
    assert not any((tmp_path / "gondolin").iterdir())
    assert custody.connection("codex-gondolin").state_version == 3
    assert not tuple(materializer.root.iterdir())
