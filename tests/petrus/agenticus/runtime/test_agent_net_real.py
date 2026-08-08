"""Credential-free probe and opt-in direct-key acceptance for Agent-as-a-Net."""

from __future__ import annotations

import json
import os
import secrets
import stat
import subprocess
import time
from hashlib import sha256
from pathlib import Path
from typing import cast

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from petrus.agenticus.attachment.binding import MotusAttachmentBinding
from petrus.agenticus.attachment.episode import EpisodeAttachment
from petrus.agenticus.catalog.descriptor import CapabilityDescriptor
from petrus.agenticus.catalog.resolution import ResolutionSnapshot
from petrus.agenticus.connection.custody import (
    AdmissionResult,
    AgentConnectionCustody,
    AttachmentFence,
    ConnectionIdentity,
    ConnectionStatus,
    ConnectionView,
    CustodyError,
    LeaseMode,
    Materialization,
    OpaqueState,
    ReleaseResult,
)
from petrus.agenticus.connection.key import KeyContext, KeyErasureEvidence
from petrus.agenticus.connection.materialization import PrivateFileMaterializer
from petrus.agenticus.connection.storage import SqliteConnectionStorage
from petrus.agenticus.hands.contract import CAPABILITY_SCOPED_HANDS, ToolMethod
from petrus.agenticus.hands.workspace import MotusWorkspaceAdapter
from petrus.agenticus.program.agent_net import (
    HANDS_ACTIVITY,
    MODEL_PHASE_ACTIVITY,
    LoopState,
    StopReason,
)
from petrus.agenticus.runtime.agent_net_runner import AgentNetRunner
from petrus.agenticus.runtime.pi import PI_AI_VERSION, PI_SDK_VERSION
from petrus.agenticus.runtime.pi_model_phase import (
    PiModelPhaseAdapter,
    PiModelPhaseConfig,
    PiModelPhaseContinuationPayloadV1,
    PiModelPhaseOperations,
    PiModelPhaseOutputPayloadV1,
    PiModelPhasePublication,
)
from petrus.agenticus.runtime.profiles import AGENT_AS_NET_A5_LOCAL, TerritoryProfile, territory_identity
from petrus.agenticus.thread.identity import EpisodeId, ThreadId
from petrus.agenticus.thread.lifecycle import EpisodeOutcome, Thread, TurnOutcome
from petrus.impetus.history import ActivityCompleted, ActivityRequested
from petrus.motus.execution import EnvironmentSpec
from petrus.motus.execution.archive import workspace_archive
from petrus.motus.execution.providers import LocalProcessEnvironment

_PROVIDER = "anthropic"
_MODEL = "claude-sonnet-4-5"
_HOST = "agent-net-live-host"
_CONNECTION = "agent-net-live"


class _Keys:
    """Qualification-owned erasable host key boundary."""

    def __init__(self) -> None:
        self._keys: dict[str, bytearray] = {}
        self._nonce = 0

    @property
    def retained(self) -> int:
        return len(self._keys)

    def seal(self, context: KeyContext, plaintext: bytearray) -> bytes:
        key = self._keys.setdefault(context.connection_id, bytearray(os.urandom(32)))
        self._nonce += 1
        nonce = self._nonce.to_bytes(12, "big")
        return nonce + AESGCM(bytes(key)).encrypt(nonce, bytes(plaintext), context.authenticated_data())

    def open(self, context: KeyContext, ciphertext: bytes) -> bytearray:
        key = self._keys.get(context.connection_id)
        if key is None:
            raise RuntimeError("Agent-as-a-Net connection key is unavailable")
        return bytearray(AESGCM(bytes(key)).decrypt(ciphertext[:12], ciphertext[12:], context.authenticated_data()))

    def erase(self, connection_id: str) -> KeyErasureEvidence:
        key = self._keys.pop(connection_id, None)
        if key is not None:
            key[:] = b"\0" * len(key)
        return KeyErasureEvidence(connection_id, True)


class _Operations(PiModelPhaseOperations):
    """Private payload custody kept outside both durable process stores."""

    def __init__(self) -> None:
        self.outputs: dict[str, PiModelPhaseOutputPayloadV1] = {}
        self.continuations: dict[str, PiModelPhaseContinuationPayloadV1] = {}
        self.operations: dict[str, PiModelPhasePublication] = {}

    def load_continuation(self, reference: str) -> PiModelPhaseContinuationPayloadV1:
        return self.continuations[reference]

    def publish(
        self,
        operation_id: str,
        output: PiModelPhaseOutputPayloadV1,
        continuation: PiModelPhaseContinuationPayloadV1,
    ) -> PiModelPhasePublication:
        prior = self.operations.get(operation_id)
        if prior is not None:
            if (
                self.outputs[prior.output_reference] != output
                or self.continuations[prior.continuation_reference] != continuation
            ):
                raise RuntimeError("Agent-as-a-Net private publication conflict")
            return prior
        ordinal = len(self.operations) + 1
        publication = PiModelPhasePublication(
            f"agent-net-output-{ordinal}",
            f"agent-net-continuation-{ordinal}",
        )
        self.outputs[publication.output_reference] = output
        self.continuations[publication.continuation_reference] = continuation
        self.operations[operation_id] = publication
        return publication

    def clear(self) -> None:
        self.outputs.clear()
        self.continuations.clear()
        self.operations.clear()


class _CustodyBridge:
    """Probe before authority, then delegate only to production DS2 custody."""

    def __init__(self) -> None:
        self.target: AgentConnectionCustody | None = None

    def bind(self, target: AgentConnectionCustody) -> None:
        if self.target is not None:
            raise RuntimeError("Agent-as-a-Net custody bridge is already bound")
        self.target = target

    def _target(self) -> AgentConnectionCustody:
        if self.target is None:
            raise AssertionError("credential-free probe may not materialize authority")
        return self.target

    def materialize(
        self,
        connection_id: str,
        host_id: str,
        *,
        mode: LeaseMode,
        ttl: float,
        operation_id: str,
    ) -> Materialization:
        return self._target().materialize(
            connection_id,
            host_id,
            mode=mode,
            ttl=ttl,
            operation_id=operation_id,
        )

    def admit_result(self, fence: AttachmentFence, *, operation_id: str) -> AdmissionResult:
        return self._target().admit_result(fence, operation_id=operation_id)

    def release(self, materialization: Materialization, *, operation_id: str) -> ReleaseResult:
        return self._target().release(materialization, operation_id=operation_id)


class _OperationsBridge(PiModelPhaseOperations):
    def __init__(self) -> None:
        self.target: _Operations | None = None

    def bind(self, target: _Operations) -> None:
        if self.target is not None:
            raise RuntimeError("Agent-as-a-Net operations bridge is already bound")
        self.target = target

    def _target(self) -> _Operations:
        if self.target is None:
            raise AssertionError("credential-free probe may not load or publish private values")
        return self.target

    def load_continuation(self, reference: str) -> PiModelPhaseContinuationPayloadV1:
        return self._target().load_continuation(reference)

    def publish(
        self,
        operation_id: str,
        output: PiModelPhaseOutputPayloadV1,
        continuation: PiModelPhaseContinuationPayloadV1,
    ) -> PiModelPhasePublication:
        return self._target().publish(operation_id, output, continuation)


def _required_path(name: str, *, directory: bool = False) -> Path:
    value = os.getenv(name)
    if not value:
        pytest.fail(f"Agent-as-a-Net qualification requires {name}", pytrace=False)
    try:
        path = Path(value).resolve(strict=True)
    except OSError:
        pytest.fail(f"Agent-as-a-Net qualification cannot resolve {name}", pytrace=False)
    if directory != path.is_dir():
        pytest.fail(f"Agent-as-a-Net qualification received the wrong {name} path kind", pytrace=False)
    return path


def _required_handoff() -> Path:
    value = os.getenv("PETRUS_CV16_AGENT_NET_AUTH_FILE")
    if not value:
        pytest.fail("Agent-as-a-Net qualification requires its authority handoff", pytrace=False)
    path = Path(value)
    if not path.is_absolute():
        pytest.fail("Agent-as-a-Net authority handoff must be absolute", pytrace=False)
    return path


def _read_handoff(source: Path, maximum: int = 8192) -> tuple[bytearray, tuple[int, ...]]:
    try:
        metadata = source.lstat()
    except OSError:
        pytest.fail("the approved Agent-as-a-Net handoff is unavailable", pytrace=False)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_uid != os.getuid()
        or metadata.st_nlink != 1
    ):
        pytest.fail("the approved Agent-as-a-Net handoff failed private-file custody", pytrace=False)
    descriptor = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(descriptor)
        value = os.read(descriptor, maximum + 1)
        after = os.fstat(descriptor)
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
        pytest.fail("the approved Agent-as-a-Net handoff changed during transfer", pytrace=False)
    try:
        text = value.decode("utf-8", "strict")
    except UnicodeDecodeError:
        pytest.fail("the approved Agent-as-a-Net handoff is not direct API-key authority", pytrace=False)
    if not text.startswith("sk-ant-") or text != text.strip() or any(ord(character) < 32 for character in text):
        pytest.fail("the approved Agent-as-a-Net handoff is not direct API-key authority", pytrace=False)
    return bytearray(value), identity


def _consume_handoff(source: Path, expected: tuple[int, ...]) -> None:
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
        pytest.fail("the approved Agent-as-a-Net handoff changed before DS2 acceptance", pytrace=False)
    source.unlink()
    if os.path.lexists(source):
        pytest.fail("the approved Agent-as-a-Net handoff was not consumed", pytrace=False)


def _adapter(
    root: Path,
    connection: ConnectionView,
    custody: _CustodyBridge,
    operations: _OperationsBridge,
) -> PiModelPhaseAdapter:
    runtime = root / "phase-runtime"
    runtime.mkdir(parents=True, mode=0o700, exist_ok=True)
    runtime.chmod(0o700)
    return PiModelPhaseAdapter(
        PiModelPhaseConfig(
            _PROVIDER,
            _MODEL,
            _HOST,
            runtime,
            "agent-net-live-episode",
            "agent-net-live-turn",
            system_prompt=(
                "Follow the bounded task exactly. Use only the supplied Agenticus tools and never invent workspace data."
            ),
            observation=(
                "Call workspace_read exactly once with path marker.txt. After its result, call no more tools and "
                "reply with the exact marker content."
            ),
            timeout=240,
        ),
        connection,
        custody,
        operations,
        node=str(_required_path("PETRUS_CV16_AGENT_NET_NODE")),
    )


def _probe(adapter: PiModelPhaseAdapter) -> tuple[Path, Path]:
    package = _required_path("PETRUS_CV16_AGENT_NET_PACKAGE_ROOT", directory=True)
    node = _required_path("PETRUS_CV16_AGENT_NET_NODE")
    assert (
        subprocess.run((str(node), "--version"), capture_output=True, text=True, check=True).stdout.strip()
        == "v22.19.0"
    )
    coding = json.loads((package / "package.json").read_text())
    ai = json.loads((package / "node_modules/@earendil-works/pi-ai/package.json").read_text())
    core = json.loads((package / "node_modules/@earendil-works/pi-agent-core/package.json").read_text())
    assert (coding["name"], coding["version"]) == ("@earendil-works/pi-coding-agent", PI_SDK_VERSION)
    assert (ai["name"], ai["version"]) == ("@earendil-works/pi-ai", PI_AI_VERSION)
    assert (core["name"], core["version"]) == ("@earendil-works/pi-agent-core", PI_SDK_VERSION)
    assert adapter.probe(package)
    return node, package


@pytest.mark.qualification_installation
@pytest.mark.skipif(
    os.getenv("PETRUS_CV16_AGENT_NET_QUALIFY") != "1",
    reason="set PETRUS_CV16_AGENT_NET_QUALIFY=1 for the exact credential-free Agent-as-a-Net probe",
)
def test_exact_agent_net_pi_installation_and_public_phase(tmp_path: Path) -> None:
    connection = ConnectionView(
        ConnectionIdentity(_CONNECTION, _PROVIDER, sha256(b"agent-net-live-account").hexdigest(), "api-key"),
        ConnectionStatus.READY,
        1,
        1,
        None,
    )
    adapter = _adapter(tmp_path, connection, _CustodyBridge(), _OperationsBridge())
    node, package = _probe(adapter)
    helper = Path(__file__).parents[4] / "src/petrus/agenticus/runtime/pi_model_phase_helper.mjs"
    result = subprocess.run(
        (str(node), str(helper), str(package / "dist/index.js"), "--test-probe"),
        capture_output=True,
        text=True,
        check=False,
        env={"HOME": str(tmp_path), "PATH": str(node.parent), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
        timeout=20,
    )
    assert result.returncode == 0 and result.stderr == ""
    assert json.loads(result.stdout) == {
        "type": "test-probe",
        "ok": True,
        "stream_calls": 1,
        "convert": True,
        "tool_execute": False,
        "network": False,
        "complete": True,
    }


@pytest.mark.real_provider_acceptance
@pytest.mark.timeout(900)
@pytest.mark.skipif(
    os.getenv("PETRUS_CV16_AGENT_NET_LIVE") != "1",
    reason="set PETRUS_CV16_AGENT_NET_LIVE=1 for the direct-key Agent-as-a-Net binding cell",
)
def test_agent_net_direct_anthropic_key_runs_one_bounded_local_task(
    tmp_path: Path,
    request: pytest.FixtureRequest,
) -> None:
    handoff = _required_handoff()
    identity = ConnectionIdentity(
        _CONNECTION,
        _PROVIDER,
        sha256(b"agent-net-live-account").hexdigest(),
        "api-key",
    )
    expected_connection = ConnectionView(identity, ConnectionStatus.READY, 1, 1, None)
    custody_bridge, operations_bridge = _CustodyBridge(), _OperationsBridge()
    adapter = _adapter(tmp_path, expected_connection, custody_bridge, operations_bridge)
    _probe(adapter)  # Exact package and credential-free helper gate before authority transfer.

    authority, handoff_identity = _read_handoff(handoff)

    def erase_authority_source() -> None:
        authority[:] = b"\0" * len(authority)

    request.addfinalizer(erase_authority_source)
    storage = SqliteConnectionStorage(tmp_path / "installation" / "connections.sqlite3")
    request.addfinalizer(storage.close)
    materializer = PrivateFileMaterializer(tmp_path / "installation" / "materialized")
    keys = _Keys()
    custody = AgentConnectionCustody(storage, keys, materializer, clock=time.monotonic)
    operations = _Operations()
    runner: AgentNetRunner | None = None
    attachment: EpisodeAttachment | None = None
    binding: MotusAttachmentBinding | None = None

    def cleanup() -> None:
        nonlocal runner
        try:
            try:
                if runner is not None:
                    runner.close()
                    runner = None
            finally:
                try:
                    if attachment is not None and not attachment.settled:
                        attachment.cancel("qualification-cleanup")
                        attachment.settle(drain_timeout=15)
                    elif attachment is None and binding is not None and binding.cleanup_result is None:
                        binding.cancel("qualification-cleanup")
                        binding.settle()
                finally:
                    try:
                        try:
                            current = custody.connection(_CONNECTION)
                        except CustodyError:
                            pass
                        else:
                            if current.status is ConnectionStatus.READY:
                                custody.revoke(_CONNECTION, operation_id="agent-net-live-revoke")
                                current = custody.connection(_CONNECTION)
                            if current.status is not ConnectionStatus.REAUTHORIZATION_REQUIRED:
                                custody.erase(_CONNECTION, operation_id="agent-net-live-erase")
                    finally:
                        keys.erase(_CONNECTION)
                        operations.clear()
        finally:
            authority[:] = b"\0" * len(authority)

    request.addfinalizer(cleanup)
    custody.enroll_host(_HOST, operation_id="agent-net-live-enroll")
    opaque = OpaqueState(authority)
    custody.authorize(identity, opaque, operation_id="agent-net-live-authorize")
    current = custody.connection(_CONNECTION)
    assert opaque.erased
    assert (current.identity, current.status, current.authority_epoch, current.state_version) == (
        expected_connection.identity,
        expected_connection.status,
        expected_connection.authority_epoch,
        expected_connection.state_version,
    )
    authority[:] = b"\0" * len(authority)
    custody_bridge.bind(custody)
    operations_bridge.bind(operations)
    _consume_handoff(handoff, handoff_identity)

    marker = f"AGENT_NET_{secrets.token_hex(12).upper()}"
    source = tmp_path / "workspace-source"
    source.mkdir()
    (source / "marker.txt").write_text(marker)
    provider = LocalProcessEnvironment()
    binding = MotusAttachmentBinding.open(
        provider,
        "agent-net-live-territory",
        EnvironmentSpec(),
        workspace_archive_bytes=workspace_archive(source),
        input_digest=sha256(marker.encode()).hexdigest(),
    )
    snapshot = ResolutionSnapshot(
        1,
        (
            AGENT_AS_NET_A5_LOCAL,
            CAPABILITY_SCOPED_HANDS,
            CapabilityDescriptor(territory_identity(TerritoryProfile.LOCAL), frozenset()),
        ),
    )
    attachment = EpisodeAttachment(
        episode_id=EpisodeId("agent-net-live-episode"),
        snapshot=snapshot,
        binding=binding,
        attachment_id="agent-net-live-attachment",
        deadline=time.monotonic() + 600,
    )
    grant = attachment.grants().open(
        (ToolMethod.WORKSPACE_READ,),
        writable_paths=(),
        allowed_argv=(),
        deadline=attachment.deadline,
        max_calls=2,
    )
    workspace = MotusWorkspaceAdapter(provider, binding.execution, test_command=("/usr/bin/true",))
    initial = LoopState(
        "agent-net-live-episode",
        "agent-net-live-turn",
        1,
        3,
        0,
        2,
        None,
        None,
        grant.grant_epoch,
        (ToolMethod.WORKSPACE_READ.value,),
    )
    active = AgentNetRunner.create(
        tmp_path / "runner",
        instance_id="agent-net-live-instance",
        thread=Thread(ThreadId("agent-net-live-thread")),
        initial=initial,
        attachment=attachment,
        model_activity=adapter,
        hands_adapter=workspace,
    )
    runner = active

    projection = active.drain(max_actions=64)

    assert projection.settled and projection.terminal is not None
    assert projection.terminal.code.value == "completed"
    assert len(projection.appends) == 2 and len(projection.hands) == 1
    episode = projection.thread.episodes[-1]
    assert episode.accepted_appends == 2
    assert episode.turns[-1].outcome is TurnOutcome.COMPLETED
    assert episode.settlement is EpisodeOutcome.COMPLETED
    assert episode.next_continuation is not None
    assert episode.next_continuation.state_reference == projection.appends[-1].continuation_reference

    records = active.history.records
    requests = [record for record in records if isinstance(record, ActivityRequested)]
    completions = [record for record in records if isinstance(record, ActivityCompleted)]
    assert [record.activity for record in requests] == [MODEL_PHASE_ACTIVITY, HANDS_ACTIVITY, MODEL_PHASE_ACTIVITY]
    assert len(completions) == 3
    hands_request = cast(dict[str, object], requests[1].input)
    hands_proposal = cast(dict[str, object], hands_request["proposal"])
    assert hands_proposal["method"] == ToolMethod.WORKSPACE_READ.value
    assert hands_proposal["params"] == {"path": "marker.txt"}

    first = operations.continuations[projection.appends[0].continuation_reference].transcript_json
    second = operations.continuations[projection.appends[1].continuation_reference].transcript_json
    first_messages, second_messages = json.loads(first), json.loads(second)
    assert second_messages[: len(first_messages)] == first_messages
    results = [message for message in second_messages if message.get("role") == "toolResult"]
    assert len(results) == 1
    model_result = json.loads(results[0]["content"][0]["text"])
    assert set(model_result) == {"version", "ok", "data", "error"}
    assert model_result["ok"] is True and model_result["data"]["content"] == marker
    final_output = operations.outputs[projection.appends[-1].output_reference].assistant_json
    final_message = json.loads(final_output)
    assert marker in "".join(item.get("text", "") for item in final_message["content"])
    assert final_message["stopReason"] == StopReason.STOP.value
    private_transcript = json.dumps(second_messages, separators=(",", ":"))
    coordinates = attachment.coordinates()
    assert coordinates.attachment_id not in private_transcript
    assert all(name not in private_transcript for name in ("attachment_id", "attachment_epoch", "grant_epoch"))

    history_text = (tmp_path / "runner/history.jsonl").read_text()
    thread_text = (tmp_path / "runner/thread.json").read_text()
    assert marker in history_text and marker not in thread_text
    assert all(
        value not in history_text + thread_text for value in ("api_key", "ANTHROPIC_API_KEY", private_transcript)
    )
    assert "sk-ant-" not in history_text + thread_text + private_transcript
    assert '"attachment"' not in json.dumps(json.loads(thread_text)["thread"])

    assert attachment.settled and attachment.last_settlement is not None
    assert attachment.last_settlement.settlement.verified
    assert second not in attachment.last_settlement.archive
    assert b"sk-ant-" not in attachment.last_settlement.archive
    assert binding.cleanup_result is not None and binding.cleanup_result.verified
    assert provider.lookup("agent-net-live-territory") is None
    assert not tuple((tmp_path / "phase-runtime").iterdir())
    assert not tuple(materializer.root.iterdir())
    assert all(lease.released for lease in storage.load().leases)

    assert (
        custody.revoke(_CONNECTION, operation_id="agent-net-live-revoke").connection.status is ConnectionStatus.REVOKED
    )
    erased = custody.erase(_CONNECTION, operation_id="agent-net-live-erase")
    assert erased.connection.status is ConnectionStatus.REAUTHORIZATION_REQUIRED
    assert (erased.connection.state_version, erased.connection.authority_epoch) == (2, 2)
    assert erased.connection.state_digest is None and keys.retained == 0
    operations.clear()
    assert not operations.outputs and not operations.continuations and not operations.operations
