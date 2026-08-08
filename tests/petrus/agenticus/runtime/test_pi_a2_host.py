"""Deterministic conformance for the supported Petrus-owned Pi A2 host."""

from __future__ import annotations

import io
import json
import tarfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import petrus.agenticus.runtime.pi as pi
from petrus.agenticus.connection.custody import ConnectionIdentity
from petrus.agenticus.connection.key import KeyContext, KeyErasureEvidence
from petrus.agenticus.connection.storage import StorageSecurityError
from petrus.agenticus.hands.contract import ToolMethod
from petrus.agenticus.runtime.installation import (
    InstalledComponent,
    ProbeDisposition,
    RuntimeInstallation,
    RuntimeProbeResult,
)
from petrus.agenticus.runtime.operation import RuntimeCleanupDisposition, RuntimeProtocolError
from petrus.agenticus.runtime.pi_a2_host import (
    PiA2DirectAuthority,
    PiA2RuntimeHost,
    PiA2RuntimeHostConfig,
    PiA2RuntimePolicy,
    PiA2RuntimeStart,
    compose_pi_a2_runtime,
)
from petrus.agenticus.runtime.profiles import PI_NATIVE_A2_LOCAL
from petrus.agenticus.thread.continuation import Continuation
from petrus.agenticus.thread.identity import ContinuationId, EpisodeId, ThreadId, TurnId
from petrus.agenticus.thread.lifecycle import TurnOutcome
from petrus.motus.execution import CleanupDisposition, CleanupResult
from petrus.motus.execution.archive import extract_workspace_archive, workspace_archive
from petrus.motus.execution.providers import LocalProcessEnvironment

SESSION = "11111111-1111-4111-8111-111111111111"
API_KEY = b"host-factory-api-key-canary"


def _session(identity: str = SESSION) -> bytes:
    return (
        json.dumps({"type": "session", "version": 3, "id": identity}, separators=(",", ":")).encode()
        + b"\n"
        + json.dumps({"type": "message", "body": "session-canary"}, separators=(",", ":")).encode()
        + b"\n"
    )


class Keys:
    def __init__(self) -> None:
        self.key = b"k" * 32
        self.nonce = 0
        self.erased = 0

    def seal(self, context: KeyContext, plaintext: bytearray) -> bytes:
        self.nonce += 1
        nonce = self.nonce.to_bytes(12, "big")
        return nonce + AESGCM(self.key).encrypt(nonce, bytes(plaintext), context.authenticated_data())

    def open(self, context: KeyContext, ciphertext: bytes) -> bytearray:
        return bytearray(AESGCM(self.key).decrypt(ciphertext[:12], ciphertext[12:], context.authenticated_data()))

    def erase(self, connection_id: str) -> KeyErasureEvidence:
        self.erased += 1
        return KeyErasureEvidence(connection_id, True)


@dataclass
class Plan:
    text: str = "answer"
    clean: bool = True
    error: str | None = None
    hands: bool = False
    read_path: str | None = None
    block: bool = False
    delay: float = 0.0
    ignore_cancel: bool = False
    write_expected: bool | None = None
    write_path: str = "output.txt"


class Client:
    def __init__(self, plan: Plan) -> None:
        self.plan = plan
        self.prior: pi.PiContinuationPayloadV1 | None = None
        self.api_key: str | None = None
        self.entered = threading.Event()

    def run(self, gateway, invocation, current, deadline):
        assert current() and deadline > time.monotonic()
        self.entered.set()
        delayed_until = time.monotonic() + self.plan.delay
        while time.monotonic() < delayed_until and (self.plan.ignore_cancel or current()):
            time.sleep(0.005)
        while self.plan.block and current() and time.monotonic() < deadline:
            time.sleep(0.005)
        if self.plan.error is not None:
            raise RuntimeProtocolError(self.plan.error)
        if self.plan.hands or self.plan.read_path is not None or self.plan.write_expected is not None:
            coordinates = invocation.attachment.coordinates()
            common = {
                "version": 1,
                "episode_id": coordinates.episode_id,
                "attachment_id": coordinates.attachment_id,
                "attachment_epoch": coordinates.attachment_epoch,
                "grant_epoch": invocation.grant_epoch,
            }
        if self.plan.read_path is not None:
            assert gateway.submit(
                {
                    **common,
                    "call_id": "continued-read",
                    "method": "workspace_read",
                    "params": {"path": self.plan.read_path},
                }
            ).ok
        if self.plan.hands:
            requests = (
                ("read", "workspace_read", {"path": "input.txt"}),
                ("search", "workspace_search", {"query": "input", "path": "input.txt"}),
                ("shell", "workspace_shell", {"argv": ["/bin/true"], "cwd": "."}),
                ("write", "workspace_write", {"path": "output.txt", "content": "changed"}),
                ("test", "workspace_test", {}),
            )
            assert all(
                gateway.submit({**common, "call_id": call, "method": method, "params": params}).ok
                for call, method, params in requests
            )
        if self.plan.write_expected is not None:
            result = gateway.submit(
                {
                    **common,
                    "call_id": "policy-write",
                    "method": "workspace_write",
                    "params": {"path": self.plan.write_path, "content": "policy-changed"},
                }
            )
            assert result.ok is self.plan.write_expected
        body = (
            (self.prior.session_jsonl if self.prior else _session())
            + json.dumps({"type": "message", "body": "next"}, separators=(",", ":")).encode()
            + b"\n"
        )
        return pi._HelperResult(pi._Candidate(SESSION, self.plan.text, body), None, "turn-completed")

    def close(self) -> bool:
        return self.plan.clean


class Factory:
    def __init__(self, *plans: Plan) -> None:
        self.plans = list(plans) or [Plan()]
        self.calls: list[dict[str, Any]] = []
        self.clients: list[Client] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        client = Client(self.plans.pop(0))
        client.prior = kwargs["prior"]
        client.api_key = kwargs["api_key"]
        self.clients.append(client)
        return client


class Authority:
    def __init__(self, keys: Keys | None = None) -> None:
        self.keys = keys or Keys()
        self.calls = 0
        self.buffers: list[bytearray] = []

    def supply(self) -> bytearray:
        self.calls += 1
        value = bytearray(API_KEY)
        self.buffers.append(value)
        return value

    def value(self) -> PiA2DirectAuthority:
        return PiA2DirectAuthority(
            ConnectionIdentity("direct", "anthropic", "account", "api-key"),
            self.keys,
            self.supply,
        )


def _config(tmp_path: Path, **changes: object) -> PiA2RuntimeHostConfig:
    working = tmp_path / "working"
    working.mkdir(exist_ok=True)
    (working / "input.txt").write_text("input")
    values: dict[str, Any] = {
        "state_root": tmp_path / "state",
        "working_directory": working,
        "provider": "anthropic",
        "model": "claude-sonnet-4-5",
        "host_id": "hamsterdan",
        "capabilities": frozenset(ToolMethod),
        "allowed_argv": frozenset({("/bin/true",)}),
        "test_command": ("/bin/true",),
        "max_tool_calls": 8,
        "attachment_timeout": 2,
        "command_timeout": 1,
        "credential_ttl": 1,
        "wall_timeout": 0.5,
        "cancellation_grace": 0.05,
    }
    values.update(changes)
    return PiA2RuntimeHostConfig(**values)


def _ready(host: PiA2RuntimeHost) -> RuntimeProbeResult:
    installation = RuntimeInstallation(
        PI_NATIVE_A2_LOCAL.identity,
        1,
        (InstalledComponent("pi-coding-agent", pi.PI_SDK_VERSION, pi.PI_SDK_SOURCE),),
        "test",
        "test",
        frozenset({"runtime.cancel", "runtime.continue", "runtime.harness-owned", "runtime.local"}),
    )
    result = RuntimeProbeResult(PI_NATIVE_A2_LOCAL.identity, ProbeDisposition.READY, installation)
    host._adapter._installation = installation
    host._adapter._node = "/synthetic/node"
    host._adapter._sdk_entrypoint = "/synthetic/pi/index.js"
    host._probe = result
    return result


def _start(
    tmp_path: Path,
    name: str = "operation",
    continuation: Continuation | None = None,
    prompt: str = "prompt",
    *,
    archive: bytes | None = None,
    correlation: str | None = None,
    policy: PiA2RuntimePolicy | None = None,
) -> PiA2RuntimeStart:
    selected = archive if archive is not None else workspace_archive(tmp_path / "working")
    digest = sha256(selected).hexdigest()
    return PiA2RuntimeStart(
        name,
        EpisodeId(f"episode-{name}"),
        TurnId(f"turn-{name}"),
        prompt,
        selected,
        digest,
        correlation or f"test-tree-{digest}",
        policy or PiA2RuntimePolicy(frozenset(ToolMethod), frozenset({"output.txt"}), 8),
        continuation,
    )


def _host(
    tmp_path: Path,
    authority: Authority,
    factory: Factory | None = None,
    provider: LocalProcessEnvironment | None = None,
) -> PiA2RuntimeHost:
    host = compose_pi_a2_runtime(
        config=_config(tmp_path),
        authority=authority.value(),
        provider=provider,
        client_factory=factory or Factory(),
    )
    _ready(host)
    return host


def _tar_with(name: str, *, kind: bytes = tarfile.REGTYPE, linkname: str = "") -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.PAX_FORMAT) as archive:
        member = tarfile.TarInfo(name)
        member.type = kind
        member.linkname = linkname
        if kind == tarfile.REGTYPE:
            content = b"input"
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
        else:
            archive.addfile(member)
    return output.getvalue()


def test_config_and_composition_are_exactly_direct_pi_a2_local(tmp_path: Path) -> None:
    config = _config(tmp_path)
    authority = Authority()
    host = compose_pi_a2_runtime(config=config, authority=authority.value(), client_factory=Factory())

    assert host.descriptor == PI_NATIVE_A2_LOCAL
    assert host.snapshot.descriptor(PI_NATIVE_A2_LOCAL.identity.kind) == PI_NATIVE_A2_LOCAL
    assert authority.calls == 0
    assert host.close()
    assert authority.calls == 0 and authority.keys.erased == 0
    with pytest.raises(ValueError, match="exact direct API-key"):
        _config(tmp_path, model="foreign-model")
    foreign = LocalProcessEnvironment()
    foreign.provider = "foreign"
    with pytest.raises(ValueError, match="only the Local"):
        compose_pi_a2_runtime(config=config, authority=authority.value(), provider=foreign)


def test_start_requires_exact_safe_workspace_and_operation_policy(tmp_path: Path) -> None:
    _config(tmp_path)
    valid = _start(tmp_path)

    with pytest.raises(TypeError, match="exact immutable bytes"):
        replace(valid, workspace_archive=bytearray(valid.workspace_archive))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="does not match"):
        replace(valid, workspace_digest="0" * 64)
    with pytest.raises(ValueError, match="malformed"):
        _start(tmp_path, archive=b"not-an-archive")
    with pytest.raises(ValueError, match="links are not permitted"):
        _start(tmp_path, archive=_tar_with("redirect", kind=tarfile.SYMTYPE, linkname="input.txt"))
    for root in (".git", ".petrus-hands-stage"):
        with pytest.raises(ValueError, match="forbidden archive member"):
            _start(tmp_path, archive=_tar_with(f"{root}/state"))
        with pytest.raises(ValueError, match="control roots"):
            PiA2RuntimePolicy(frozenset({ToolMethod.WORKSPACE_WRITE}), frozenset({f"{root}/state"}), 1)
        with pytest.raises(ValueError, match="control roots"):
            PiA2RuntimePolicy(
                frozenset({ToolMethod.WORKSPACE_WRITE}),
                max_tool_calls=1,
                writable_roots=frozenset({root}),
            )
    with pytest.raises(ValueError, match="require workspace-write"):
        PiA2RuntimePolicy(frozenset({ToolMethod.WORKSPACE_READ}), frozenset({"output.txt"}), 1)
    with pytest.raises(ValueError, match="require workspace-write"):
        PiA2RuntimePolicy(
            frozenset({ToolMethod.WORKSPACE_READ}),
            max_tool_calls=1,
            writable_roots=frozenset({"."}),
        )


def test_probe_is_authority_free_and_nonready_start_fails_before_admission(tmp_path: Path) -> None:
    authority = Authority()
    host = compose_pi_a2_runtime(config=_config(tmp_path), authority=authority.value(), client_factory=Factory())

    result = host.probe()
    assert result.disposition is not ProbeDisposition.READY
    with pytest.raises(RuntimeProtocolError, match="runtime-not-ready"):
        host.start(_start(tmp_path))
    assert authority.calls == 0
    assert host._ledger.lookup("operation") is None
    assert host.close()


def test_completed_operation_commits_bodies_only_after_verified_cleanup(tmp_path: Path) -> None:
    authority, factory = Authority(), Factory(Plan(hands=True))
    host = _host(tmp_path, authority, factory)
    operation = host.start(_start(tmp_path))

    settlement = operation.wait(1)

    assert settlement.outcome is TurnOutcome.COMPLETED and settlement.accepted_appends == 1
    assert settlement.output_reference and host.load_output(settlement.output_reference) == "answer"
    assert settlement.continuation_reference
    archive = host.load_workspace_archive("operation")
    assert archive and API_KEY not in archive
    extracted = tmp_path / "extracted"
    extract_workspace_archive(archive, extracted)
    assert (extracted / "output.txt").read_text() == "changed"
    assert API_KEY not in (tmp_path / "state" / "operations.sqlite3").read_bytes()
    assert API_KEY not in (tmp_path / "state" / "bodies.sqlite3").read_bytes()
    assert authority.calls == 1 and all(not buffer or set(buffer) == {0} for buffer in authority.buffers)
    assert len(factory.calls) == 1 and factory.calls[0]["api_key"] == API_KEY.decode()
    assert operation.close().disposition is RuntimeCleanupDisposition.CLEAN
    assert host.close() and authority.keys.erased == 1


def test_start_archive_not_global_working_directory_is_episode_input(tmp_path: Path) -> None:
    authority = Authority()
    host = _host(tmp_path, authority)
    start = _start(tmp_path)
    (tmp_path / "working" / "input.txt").write_text("ambient-change")

    settlement = host.start(start).wait(1)

    archive = host.load_workspace_archive("operation")
    extracted = tmp_path / "start-archive"
    extract_workspace_archive(archive, extracted)
    assert settlement.outcome is TurnOutcome.COMPLETED
    assert (extracted / "input.txt").read_text() == "input"
    assert host.close()


def test_per_start_policy_is_exact_attachment_authority(tmp_path: Path) -> None:
    authority = Authority()
    host = _host(
        tmp_path,
        authority,
        Factory(Plan(write_expected=False), Plan(write_expected=True, write_path="new/output.txt")),
    )
    read_only = PiA2RuntimePolicy(
        frozenset({ToolMethod.WORKSPACE_READ, ToolMethod.WORKSPACE_SEARCH}),
        max_tool_calls=2,
    )
    coding = PiA2RuntimePolicy(
        frozenset({ToolMethod.WORKSPACE_READ, ToolMethod.WORKSPACE_WRITE}),
        max_tool_calls=2,
        writable_roots=frozenset({"."}),
    )

    first = host.start(_start(tmp_path, "read-only", policy=read_only)).wait(1)
    second = host.start(_start(tmp_path, "coding", policy=coding)).wait(1)

    assert first.outcome is second.outcome is TurnOutcome.COMPLETED
    extracted = tmp_path / "policy-archive"
    extract_workspace_archive(host.load_workspace_archive("coding"), extracted)
    assert (extracted / "new" / "output.txt").read_text() == "policy-changed"
    assert host.close()


def test_policy_ceiling_rejection_does_not_burn_operation_identity(tmp_path: Path) -> None:
    authority = Authority()
    host = compose_pi_a2_runtime(
        config=_config(
            tmp_path,
            capabilities=frozenset({ToolMethod.WORKSPACE_READ}),
            max_tool_calls=2,
        ),
        authority=authority.value(),
        client_factory=Factory(),
    )
    _ready(host)
    excess_capability = PiA2RuntimePolicy(
        frozenset({ToolMethod.WORKSPACE_WRITE}),
        frozenset({"output.txt"}),
        1,
    )
    excess_calls = PiA2RuntimePolicy(frozenset({ToolMethod.WORKSPACE_READ}), max_tool_calls=3)

    for name, policy in (("capability", excess_capability), ("calls", excess_calls)):
        with pytest.raises(RuntimeProtocolError, match="operation-policy-exceeds-host"):
            host.start(_start(tmp_path, name, policy=policy))
        assert host._ledger.lookup(name) is None
    corrected = PiA2RuntimePolicy(frozenset({ToolMethod.WORKSPACE_READ}), max_tool_calls=2)
    assert host.start(_start(tmp_path, "capability", policy=corrected)).wait(1).outcome is TurnOutcome.COMPLETED
    assert authority.calls == 1
    assert host.close()


def test_continuation_and_second_operation_reuse_one_host_authorization(tmp_path: Path) -> None:
    authority, factory = Authority(), Factory(Plan("first", hands=True), Plan("second", read_path="output.txt"))
    host = _host(tmp_path, authority, factory)
    first = host.start(_start(tmp_path, "one")).wait(1)
    assert first.continuation_reference
    continuation = Continuation(
        ContinuationId("continuation-one"),
        ThreadId("thread"),
        pi.PI_CONTINUATION_DESCRIPTOR,
        first.continuation_reference,
    ).claim()

    second = host.start(
        _start(
            tmp_path,
            "two",
            continuation,
            archive=host.load_workspace_archive("one"),
        )
    ).wait(1)

    assert host.load_output(second.output_reference or "") == "second"
    assert authority.calls == 1 and len(factory.calls) == 2
    assert factory.calls[1]["prior"].session_id == SESSION
    assert host.close()


def test_continuation_workspace_mismatch_precedes_admission_and_can_be_corrected(tmp_path: Path) -> None:
    authority = Authority()
    factory = Factory(Plan(write_expected=True), Plan("continued", read_path="output.txt"))
    host = _host(tmp_path, authority, factory)
    first = host.start(_start(tmp_path, "one")).wait(1)
    assert first.continuation_reference
    continuation = Continuation(
        ContinuationId("continuation-mismatch"),
        ThreadId("thread"),
        pi.PI_CONTINUATION_DESCRIPTOR,
        first.continuation_reference,
    ).claim()

    with pytest.raises(RuntimeProtocolError, match="operation-conflict"):
        host.start(_start(tmp_path, "two", continuation))

    assert host._ledger.lookup("two") is None
    assert len(factory.calls) == 1 and authority.calls == 1
    corrected = _start(
        tmp_path,
        "two",
        continuation,
        archive=host.load_workspace_archive("one"),
    )
    assert host.start(corrected).wait(1).outcome is TurnOutcome.COMPLETED
    assert len(factory.calls) == 2 and authority.calls == 1
    assert host.close()


def test_terminal_replay_precedes_probe_authority_and_territory(tmp_path: Path) -> None:
    original = Authority()
    host = _host(tmp_path, original)
    start = _start(tmp_path)
    expected = host.start(start).wait(1)
    assert host.close()
    replay_authority = Authority()
    provider = LocalProcessEnvironment()
    replay = compose_pi_a2_runtime(
        config=_config(tmp_path),
        authority=replay_authority.value(),
        provider=provider,
        client_factory=Factory(),
    )

    operation = replay.start(start)

    assert operation.wait() == expected
    assert replay_authority.calls == 0 and provider.lookup(replay._territory_operation("operation")) is None
    assert operation.close().verified
    assert replay.close()


def test_concurrent_starts_serialize_one_shot_authority_and_dedupe_live_work(tmp_path: Path) -> None:
    authority, factory = Authority(), Factory(Plan(), Plan())
    host = _host(tmp_path, authority, factory)
    starts = (_start(tmp_path, "one"), _start(tmp_path, "two"))

    with ThreadPoolExecutor(max_workers=2) as pool:
        operations = tuple(pool.map(host.start, starts))

    assert host.start(starts[0]) is operations[0]
    assert all(operation.wait(1).outcome is TurnOutcome.COMPLETED for operation in operations)
    assert authority.calls == 1 and len(factory.calls) == 2
    assert host.close()


def test_close_fences_new_starts_and_cancels_active_operation(tmp_path: Path) -> None:
    authority = Authority()
    host = _host(tmp_path, authority, Factory(Plan(block=True)))
    operation = host.start(_start(tmp_path))

    assert host.close()

    assert operation.close().verified
    with pytest.raises(RuntimeProtocolError, match="host-closed"):
        host.start(_start(tmp_path, "later"))


def test_indeterminate_close_prevents_late_waiter_publication(tmp_path: Path) -> None:
    authority = Authority()
    factory = Factory(Plan(delay=0.4, ignore_cancel=True))
    host = _host(tmp_path, authority, factory)
    operation = host.start(_start(tmp_path))
    with ThreadPoolExecutor(max_workers=1) as pool:
        waiter = pool.submit(operation.wait, 1)
        while not factory.clients:
            time.sleep(0.005)
        assert factory.clients[0].entered.wait(1)

        cleanup = operation.close()

        assert cleanup.disposition is RuntimeCleanupDisposition.UNVERIFIED
        with pytest.raises(RuntimeProtocolError, match="operation-closed"):
            waiter.result(1)
    reference = f"pi-a2-output-{sha256(b'operation\0answer').hexdigest()}"
    with pytest.raises(RuntimeProtocolError, match="output-absent"):
        host.load_output(reference)
    record = host._ledger.lookup("operation")
    assert record is not None and record.settlement().outcome is TurnOutcome.INDETERMINATE
    assert host.close()


def test_changed_work_conflicts_before_probe_or_authority(tmp_path: Path) -> None:
    original = Authority()
    host = _host(tmp_path, original)
    original_start = _start(tmp_path)
    host.start(original_start).wait(1)
    assert host.close()
    replay_authority = Authority()
    provider = LocalProcessEnvironment()
    replay = compose_pi_a2_runtime(
        config=_config(tmp_path),
        authority=replay_authority.value(),
        provider=provider,
        client_factory=Factory(),
    )
    (tmp_path / "working" / "input.txt").write_text("changed-input")
    changed_archive = workspace_archive(tmp_path / "working")
    changed_workspace = replace(
        original_start,
        workspace_archive=changed_archive,
        workspace_digest=sha256(changed_archive).hexdigest(),
    )
    changed_policy = replace(
        original_start,
        policy=PiA2RuntimePolicy(frozenset({ToolMethod.WORKSPACE_READ}), max_tool_calls=1),
    )
    changed_root_policy = replace(
        original_start,
        policy=PiA2RuntimePolicy(
            frozenset(ToolMethod),
            max_tool_calls=8,
            writable_roots=frozenset({"."}),
        ),
    )

    for changed in (
        replace(original_start, prompt="changed"),
        changed_workspace,
        replace(original_start, workspace_correlation="changed-tree"),
        changed_policy,
        changed_root_policy,
    ):
        with pytest.raises(RuntimeProtocolError, match="operation-conflict"):
            replay.start(changed)

    assert replay_authority.calls == 0
    assert provider.lookup(replay._territory_operation("operation")) is None
    assert replay.close()


def test_surviving_executing_record_becomes_indeterminate_without_authority(tmp_path: Path) -> None:
    authority = Authority()
    host = _host(tmp_path, authority)
    start = _start(tmp_path)
    fingerprint = host._fingerprint(start)
    host._ledger.admit(start.operation_id, fingerprint, start.episode_id, start.turn_id)
    host._bodies.close()
    host._ledger.close()
    host._storage.close()
    recovered_authority = Authority()
    recovered = compose_pi_a2_runtime(
        config=_config(tmp_path), authority=recovered_authority.value(), client_factory=Factory()
    )

    with pytest.raises(RuntimeProtocolError, match="operation-indeterminate"):
        recovered.start(start)

    assert recovered_authority.calls == 0
    assert recovered.close()


def test_pre_workspace_fingerprint_conflicts_without_authority_or_provider_work(tmp_path: Path) -> None:
    authority = Authority()
    provider = LocalProcessEnvironment()
    host = _host(tmp_path, authority, provider=provider)
    start = _start(tmp_path)
    old_fingerprint = pi.pi_durable_work_fingerprint(
        host._adapter.config,
        start.episode_id,
        start.turn_id,
        start.prompt,
        authority.value().connection,
    )
    host._ledger.admit(start.operation_id, old_fingerprint, start.episode_id, start.turn_id)

    with pytest.raises(RuntimeProtocolError, match="operation-conflict"):
        host.start(start)

    assert authority.calls == 0
    assert provider.lookup(host._territory_operation("operation")) is None
    assert host.close()


def test_invalid_authority_is_consumed_once_and_replays_terminal_failure(tmp_path: Path) -> None:
    authority = Authority()

    def invalid() -> bytearray:
        authority.calls += 1
        value = bytearray()
        authority.buffers.append(value)
        return value

    value = PiA2DirectAuthority(
        ConnectionIdentity("direct", "anthropic", "account", "api-key"), authority.keys, invalid
    )
    host = compose_pi_a2_runtime(config=_config(tmp_path), authority=value, client_factory=Factory())
    _ready(host)

    with pytest.raises(RuntimeProtocolError, match="credential-invalid"):
        host.start(_start(tmp_path))
    replay = host.start(_start(tmp_path))

    assert replay.wait().outcome is TurnOutcome.FAILED
    assert authority.calls == 1 and replay.close().verified
    assert host.close()


class AttachFailure(LocalProcessEnvironment):
    def attach(self, lease, workspace_archive_bytes, input_digest):
        raise RuntimeError("synthetic")


def test_partial_attachment_construction_rolls_back_and_replays_clean_failure(tmp_path: Path) -> None:
    authority = Authority()
    provider = AttachFailure()
    host = _host(tmp_path, authority, provider=provider)
    start = _start(tmp_path)

    with pytest.raises(RuntimeProtocolError, match="runtime-start-failed"):
        host.start(start)
    replay = host.start(start)

    assert replay.wait().outcome is TurnOutcome.FAILED and replay.close().verified
    assert host.load_workspace_archive("operation") == start.workspace_archive
    assert authority.calls == 1 and provider.lookup(host._territory_operation("operation")) is None
    assert host.close()


def test_body_publication_failure_leaves_output_unreadable_and_operation_indeterminate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authority = Authority()
    host = _host(tmp_path, authority)

    def fail_publish(operation_id: str) -> None:
        raise RuntimeError("synthetic")

    monkeypatch.setattr(host._bodies, "publish", fail_publish)
    operation = host.start(_start(tmp_path))

    with pytest.raises(RuntimeProtocolError, match="host-cleanup-uncertain"):
        operation.wait(1)

    reference = f"pi-a2-output-{sha256(b'operation\0answer').hexdigest()}"
    with pytest.raises(RuntimeProtocolError, match="output-absent"):
        host.load_output(reference)
    with pytest.raises(RuntimeProtocolError, match="operation-indeterminate"):
        host.start(_start(tmp_path))
    assert host.close()


class UnverifiedDestroy(LocalProcessEnvironment):
    def destroy(self, lease):
        return CleanupResult(lease.identity, CleanupDisposition.UNVERIFIED, "synthetic")


def test_unverified_territory_cleanup_never_publishes_success(tmp_path: Path) -> None:
    authority = Authority()
    provider = UnverifiedDestroy()
    host = _host(tmp_path, authority, provider=provider)
    operation = host.start(_start(tmp_path))

    with pytest.raises(RuntimeProtocolError, match="host-cleanup-uncertain"):
        operation.wait(1)

    assert operation.close().disposition is RuntimeCleanupDisposition.UNVERIFIED
    with pytest.raises(RuntimeProtocolError, match="operation-indeterminate"):
        host.start(_start(tmp_path))
    with pytest.raises(RuntimeProtocolError, match="host-cleanup-uncertain"):
        host.close()
    lease = provider.lookup(host._territory_operation("operation"))
    assert lease is not None and LocalProcessEnvironment.destroy(provider, lease).verified


def test_private_state_root_rejects_unsafe_existing_mode(tmp_path: Path) -> None:
    state = tmp_path / "unsafe"
    state.mkdir(mode=0o755)
    state.chmod(0o755)
    authority = Authority()

    with pytest.raises(StorageSecurityError, match="mode-0700"):
        compose_pi_a2_runtime(
            config=_config(tmp_path, state_root=state),
            authority=authority.value(),
            client_factory=Factory(),
        )

    assert authority.calls == 0
