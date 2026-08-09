"""Deterministic conformance for the stock Codex A2 Local lane."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import petrus.agenticus.runtime.codex as codex
from petrus.agenticus.attachment.binding import MotusAttachmentBinding
from petrus.agenticus.attachment.episode import EpisodeAttachment
from petrus.agenticus.catalog.descriptor import CapabilityDescriptor, DescriptorIdentity, DescriptorKind
from petrus.agenticus.catalog.resolution import ResolutionSnapshot
from petrus.agenticus.connection.custody import (
    AdmissionResult,
    AgentConnectionCustody,
    AttachmentFence,
    CleanupEvidence,
    ConnectionIdentity,
    ConnectionStatus,
    ConnectionView,
    LeaseMode,
    Materialization,
    OpaqueState,
    PublicationResult,
    ReleaseResult,
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
    CODEX_GONDOLIN_OCI_DIGEST,
    CODEX_GONDOLIN_SDK_VERSION,
    CODEX_GONDOLIN_TERRITORY,
    CODEX_GONDOLIN_VERSION,
    CODEX_LOCAL_TERRITORY,
    CODEX_NPM_INTEGRITY,
    CODEX_PROGRAM,
    CODEX_PROGRAM_CAPABILITIES,
    CODEX_SOURCE_COMMIT,
    CODEX_VERSION,
    CodexContinuationCodec,
    CodexContinuationPayloadV1,
    CodexGondolinRuntimeAdapter,
    CodexRuntimeAdapter,
    CodexRuntimeConfig,
    CodexRuntimeInvocation,
)
from petrus.agenticus.runtime.installation import ProbeDisposition
from petrus.agenticus.runtime.operation import RuntimeCleanupDisposition, RuntimeProtocolError
from petrus.agenticus.runtime.profiles import CODEX_A2_LOCAL, CODEX_A3_GONDOLIN
from petrus.agenticus.thread.continuation import Continuation, ContinuationState
from petrus.agenticus.thread.identity import ContinuationId, EpisodeId, ThreadId, TurnId
from petrus.agenticus.thread.lifecycle import CancellationDisposition, TurnOutcome
from petrus.motus.execution import (
    MAX_PRIVATE_FILE_BYTES,
    CleanupDisposition,
    Command,
    CommandResult,
    EnvironmentCapability,
    EnvironmentSpec,
    ExecutionAttachment,
    PrivateFileCleanupResult,
)
from petrus.motus.execution.archive import extract_workspace_archive, workspace_archive
from petrus.motus.execution.gondolin import GondolinEnvironment
from petrus.motus.execution.providers import LocalProcessEnvironment

THREAD = "11111111-1111-4111-8111-111111111111"
OTHER_THREAD = "22222222-2222-4222-8222-222222222222"
ROLLOUT_PATH = f"sessions/2026/08/03/rollout-2026-08-03T00-00-00-{THREAD}.jsonl"
AUTH_CANARY = b"opaque-auth-canary"
ROLLOUT_CANARY = b"opaque-rollout-canary"
PROMPT_CANARY = "prompt-canary-never-render"
HOST_FENCED_EFFECT = CapabilityDescriptor(
    DescriptorIdentity(DescriptorKind.EFFECT, "host.fenced", 1),
    frozenset({"effect.host-fenced"}),
)


class Continuations:
    def __init__(self) -> None:
        self.values: dict[str, CodexContinuationPayloadV1] = {}

    def store(self, operation_id: str, payload: CodexContinuationPayloadV1) -> str:
        reference = f"codex-continuation-{operation_id}"
        existing = self.values.get(reference)
        if existing is not None and existing != payload:
            raise RuntimeError("conflicting Continuation payload")
        self.values[reference] = payload
        return reference

    def load(self, state_reference: str) -> CodexContinuationPayloadV1:
        return self.values[state_reference]


class BlockingContinuations(Continuations):
    def __init__(self) -> None:
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()

    def store(self, operation_id: str, payload: CodexContinuationPayloadV1) -> str:
        self.entered.set()
        assert self.release.wait(5)
        return super().store(operation_id, payload)


class Turns:
    def __init__(self) -> None:
        self.values: dict[str, tuple[str, str]] = {}

    def store_turn(self, operation_id: str, thread_id: str, final_text: str) -> str:
        reference = f"codex-turn-{operation_id}"
        value = (thread_id, final_text)
        existing = self.values.get(reference)
        if existing is not None and existing != value:
            raise RuntimeError("conflicting Turn payload")
        self.values[reference] = value
        return reference


class Home:
    def __init__(self, value: bytes) -> None:
        self.value = value

    def read(self) -> bytes:
        return self.value

    def replace(self, value: bytes) -> None:
        if not value:
            raise ValueError("empty auth state")
        self.value = value

    def __repr__(self) -> str:
        return "Home(<opaque>)"


class Custody:
    def __init__(self) -> None:
        self.authority_epoch = 3
        self.state_version = 4
        self.auth = AUTH_CANARY
        self.records: list[tuple[str, str]] = []
        self.mismatched_fence = False
        self.checkpoint_cleanup_uncertain = False

    def view(self) -> ConnectionView:
        return ConnectionView(
            ConnectionIdentity("codex-connection", "codex", "safe-account", "file-auth"),
            ConnectionStatus.READY,
            self.authority_epoch,
            self.state_version,
            None,
        )

    def materialize(
        self,
        connection_id: str,
        host_id: str,
        *,
        mode: LeaseMode,
        ttl: float,
        operation_id: str,
    ) -> Materialization:
        assert connection_id == "codex-connection" and host_id == "host-1"
        assert mode is LeaseMode.REFRESH and ttl > 0
        self.records.append(("materialize", operation_id))
        fence = AttachmentFence(
            f"connection-attachment-{self.state_version}",
            f"connection-lease-{self.state_version}",
            connection_id,
            host_id,
            1,
            self.authority_epoch + int(self.mismatched_fence),
            self.state_version,
        )
        return Materialization(fence, mode, time.monotonic() + ttl, Home(self.auth))

    def activate(self, materialization: Materialization, *, operation_id: str) -> None:
        self.records.append(("activate", operation_id))

    def admit_result(self, fence: AttachmentFence, *, operation_id: str) -> AdmissionResult:
        assert fence.authority_epoch == self.authority_epoch and fence.base_version == self.state_version
        self.records.append(("admit", operation_id))
        return AdmissionResult(operation_id, "result", fence.attachment_id)

    def checkpoint(self, materialization: Materialization, *, operation_id: str) -> PublicationResult:
        self.records.append(("checkpoint", operation_id))
        self.auth = materialization.home.read()
        self.state_version += 1
        cleanup = CleanupEvidence(
            materialization.fence.attachment_id,
            True,
            False,
            len(self.auth),
            security_violation=self.checkpoint_cleanup_uncertain,
        )
        return PublicationResult(operation_id, self.view(), cleanup)

    def release(self, materialization: Materialization, *, operation_id: str) -> ReleaseResult:
        self.records.append(("release", operation_id))
        return ReleaseResult(
            operation_id,
            CleanupEvidence(materialization.fence.attachment_id, True, False, len(materialization.home.read())),
        )


class PublishingCustody(Custody):
    def __init__(self) -> None:
        super().__init__()
        self.publication_entered = threading.Event()
        self.publication_release = threading.Event()

    def admit_result(self, fence: AttachmentFence, *, operation_id: str) -> AdmissionResult:
        self.publication_entered.set()
        assert self.publication_release.wait(5)
        return super().admit_result(fence, operation_id=operation_id)


class SyntheticKeyOperations:
    def __init__(self) -> None:
        self._key = bytes.fromhex("5f" * 32)
        self._nonce = 0

    def seal(self, context: KeyContext, plaintext: bytearray) -> bytes:
        self._nonce += 1
        nonce = self._nonce.to_bytes(12, "big")
        return nonce + AESGCM(self._key).encrypt(nonce, bytes(plaintext), context.authenticated_data())

    def open(self, context: KeyContext, ciphertext: bytes) -> bytearray:
        return bytearray(AESGCM(self._key).decrypt(ciphertext[:12], ciphertext[12:], context.authenticated_data()))

    def erase(self, connection_id: str) -> KeyErasureEvidence:
        return KeyErasureEvidence(connection_id, True)


class RecordingLocal(LocalProcessEnvironment):
    def __init__(self) -> None:
        super().__init__()
        self.commands: list[Command] = []

    def execute(self, attachment: ExecutionAttachment, command: Command) -> CommandResult:
        self.commands.append(command)
        return super().execute(attachment, command)


class UncertainCleanupLocal(RecordingLocal):
    def cleanup_private_files(self, attachment: ExecutionAttachment) -> PrivateFileCleanupResult:
        result = super().cleanup_private_files(attachment)
        return replace(result, disposition=CleanupDisposition.UNVERIFIED)


def snapshot(*, runtime: CapabilityDescriptor = CODEX_A2_LOCAL) -> ResolutionSnapshot:
    return ResolutionSnapshot(
        1,
        (
            runtime,
            CODEX_CONNECTION_CAPABILITIES,
            CODEX_PROGRAM_CAPABILITIES,
            CODEX_COLLOCATED_HANDS,
            CODEX_LOCAL_TERRITORY,
            CODEX_CONTINUATION_CAPABILITIES,
            HOST_FENCED_EFFECT,
        ),
    )


def gondolin_snapshot() -> ResolutionSnapshot:
    return ResolutionSnapshot(
        1,
        (
            CODEX_A3_GONDOLIN,
            CODEX_CONNECTION_CAPABILITIES,
            CODEX_PROGRAM_CAPABILITIES,
            CODEX_COLLOCATED_HANDS,
            CODEX_GONDOLIN_TERRITORY,
            CODEX_CONTINUATION_CAPABILITIES,
            HOST_FENCED_EFFECT,
        ),
    )


def fake_codex(tmp_path: Path, version: str = CODEX_VERSION) -> Path:
    executable = tmp_path / "codex"
    executable.write_text(
        f"""#!{sys.executable}
import json, os, signal, sys, time
from pathlib import Path

THREAD={THREAD!r}
OTHER={OTHER_THREAD!r}
RELATIVE={ROLLOUT_PATH!r}
args=sys.argv[1:]
if args == ["--version"]:
 print("codex-cli {version}")
 raise SystemExit(0)
if args == ["exec", "resume", "--help"]:
 print("SESSION_ID PROMPT --last --all")
 raise SystemExit(0)
if args == ["exec", "--help"]:
 print("--json --color --sandbox --config --skip-git-repo-check --ignore-user-config --ignore-rules")
 raise SystemExit(0)
prompt=args[-1]
if "--dangerously-bypass-approvals-and-sandbox" in args and args[-2] != "--":
 raise SystemExit(73)
resume="resume" in args
thread=args[args.index("resume")+1] if resume else THREAD
home=Path(os.environ["CODEX_HOME"])
auth=home / "auth.json"
auth.write_bytes(auth.read_bytes()+b"|refreshed")
auth.chmod(0o600)
if resume:
 matches=list(home.glob(f"sessions/**/*-{{thread}}.jsonl"))
 if len(matches)!=1: raise SystemExit(70)
 rollout=matches[0]
 prior=rollout.read_bytes()
else:
 rollout=home / RELATIVE
 rollout.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
 prior=b""
if prompt == "oversize-rollout":
 rollout.write_bytes(b"x"*1000001)
else:
 rollout.write_bytes(prior+b"\\n"+prompt.encode())
rollout.chmod(0o600)
if prompt in {{"timeout", "cancel-me"}}:
 time.sleep(5)
if prompt == "command-signal":
 os.kill(os.getpid(),signal.SIGTERM)
if prompt == "output-overflow":
 sys.stdout.write("x"*100000); sys.stdout.flush(); time.sleep(5)
if prompt == "malformed-jsonl":
 print("not-json")
 raise SystemExit(0)
emitted=OTHER if prompt == "foreign-thread" else thread
print(json.dumps({{"type":"thread.started","thread_id":emitted}}))
print(json.dumps({{"type":"turn.started"}}))
if prompt == "provider-failure":
 print(json.dumps({{"type":"turn.failed","error":{{"message":"provider canary not retained"}}}}))
 raise SystemExit(1)
text=("resumed:first:second" if resume and b"first" in prior and prompt=="second" else "answer:"+prompt)
print(json.dumps({{"type":"item.completed","item":{{"id":"item-1","type":"agent_message","text":text}}}}))
print(json.dumps({{"type":"turn.completed","usage":{{"input_tokens":1,"output_tokens":1}}}}))
"""
    )
    executable.chmod(0o755)
    return executable


def fake_gondolin_sdk(tmp_path: Path, executable: Path) -> Path:
    architecture = tmp_path / "fake-uname"
    architecture.write_text("#!/bin/sh\nprintf aarch64\n")
    architecture.chmod(0o755)
    command_started = tmp_path / "fake-codex-command-started"
    module = tmp_path / "fake-gondolin-codex.mjs"
    source = (
        textwrap.dedent(
            """
        import childProcess from "node:child_process";
        import fs from "node:fs";
        import os from "node:os";
        import path from "node:path";
        export const VERSION = "0.12.0";
        export const PETRUS_FAKE = true;
        export class RealFSProvider { constructor(root) { this.root = root; } }
        export function createHttpHooks() { return { httpHooks: { qualified: true }, env: {} }; }
        export function resolveImageSelector(selector) {
          if (selector !== "fake-image") throw new Error("wrong image");
          return { assetDir: selector };
        }
        export function loadGuestAssets(assetDir) {
          return {
            kernelPath: path.join(assetDir, "kernel"),
            initrdPath: path.join(assetDir, "initrd"),
            rootfsPath: path.join(assetDir, "rootfs"),
          };
        }
        export class VM {
          static async create(options) {
            const assets = options.sandbox.imagePath;
            if (!assets || typeof assets !== "object" || path.dirname(assets.rootfsPath) !== "fake-image" || !options.sandbox.netEnabled) throw new Error("wrong image");
            if (!options.httpHooks.qualified) throw new Error("wrong hooks");
            const vm = new VM(options.vfs.mounts["/petrus-transfer"].root);
            await vm.start();
            return vm;
          }
          constructor(root) {
            this.root = root;
            this.child = null;
            this.started = false;
            this.guest = fs.mkdtempSync(path.join(process.env.TMPDIR ?? os.tmpdir(), "fake-codex-guest-"));
          }
          async start() { this.started = true; }
          exec(argv, options) {
            if (!this.started) throw new Error("sandbox stopped");
            const privateRoot = path.join(this.guest, ".petrus-private");
            const mapped = value => value === "/workspace" || value.startsWith("/workspace/")
              ? value.replace("/workspace", this.guest)
              : value === "/tmp/.petrus-private" || value.startsWith("/tmp/.petrus-private/")
              ? value.replace("/tmp/.petrus-private", privateRoot)
              : value === "/petrus-transfer" || value.startsWith("/petrus-transfer/")
              ? value.replace("/petrus-transfer", this.root)
              : value === "/usr/local/bin/codex" ? __CODEX__
              : value === "/bin/uname" ? __UNAME__ : value;
            const cwd = options.cwd ? mapped(options.cwd) : this.root;
            let translated = argv.map(value => mapped(value).replace?.("R='/tmp/.petrus-private'", `R='${privateRoot}'`) ?? mapped(value));
            if (translated[0] === "/bin/tar" && !fs.existsSync(translated[0])) translated[0] = "/usr/bin/tar";
            const env = Object.fromEntries(Object.entries(options.env ?? {}).map(([key, value]) => [key, mapped(value)]));
            if (argv.includes("cancel-me")) fs.writeFileSync(__STARTED__, "started");
            this.child = childProcess.spawn(translated[0], translated.slice(1), { cwd, env, detached: true });
            if (Buffer.isBuffer(options.stdin)) this.child.stdin.end(options.stdin); else this.child.stdin.end();
            const child = this.child, queued = [], waiters = [];
            let finished = false;
            const emit = value => { const waiter = waiters.shift(); waiter ? waiter(value) : queued.push(value); };
            child.stdout.on("data", data => emit({ value: { stream: "stdout", data }, done: false }));
            child.stderr.on("data", data => emit({ value: { stream: "stderr", data }, done: false }));
            child.on("close", () => { finished = true; emit({ done: true }); });
            const result = new Promise((resolve, reject) => {
              child.on("error", reject);
              child.on("close", code => code === null ? reject(new Error("VM closed")) : resolve({ exitCode: code }));
            });
            return { result, output() { return { [Symbol.asyncIterator]() { return this; }, next() {
              if (queued.length) return Promise.resolve(queued.shift());
              if (finished) return Promise.resolve({ done: true });
              return new Promise(resolve => waiters.push(resolve));
            } }; } };
          }
          async close() {
            if (this.child && this.child.exitCode === null) {
              const child = this.child;
              const closed = new Promise(resolve => child.once("close", resolve));
              try { process.kill(-child.pid, "SIGKILL"); } catch {}
              await closed;
            }
            fs.rmSync(this.guest, { recursive: true, force: true });
          }
        }
        """
        )
        .replace("__CODEX__", json.dumps(str(executable)))
        .replace("__UNAME__", json.dumps(str(architecture)))
        .replace("__STARTED__", json.dumps(str(command_started)))
    )
    module.write_text(source)
    return module


@dataclass
class Rig:
    adapter: CodexRuntimeAdapter
    executable: Path
    continuations: Continuations
    turns: Turns
    custody: Custody
    tmp_path: Path

    def invocation(
        self,
        operation_id: str,
        prompt: str,
        *,
        continuation: Continuation | None = None,
        selected: ResolutionSnapshot | None = None,
        provider: RecordingLocal | None = None,
        deadline: float | None = None,
    ) -> tuple[CodexRuntimeInvocation, EpisodeAttachment, RecordingLocal]:
        provider = provider or RecordingLocal()
        episode = operation_id.replace("operation", "episode")
        source = self.tmp_path / f"workspace-{operation_id}"
        source.mkdir()
        binding = MotusAttachmentBinding.open(
            provider,
            f"territory-{operation_id}",
            EnvironmentSpec(required_capabilities=frozenset({EnvironmentCapability.PRIVATE_FILE_TRANSFER.value})),
            workspace_archive_bytes=workspace_archive(source),
            input_digest=f"input-{operation_id}",
        )
        attachment = EpisodeAttachment(
            episode_id=EpisodeId(episode),
            snapshot=selected or snapshot(),
            binding=binding,
            attachment_id=f"agenticus-attachment-{operation_id}",
            deadline=time.monotonic() + 5 if deadline is None else deadline,
        )
        return (
            CodexRuntimeInvocation(
                operation_id,
                EpisodeId(episode),
                TurnId(f"turn-{operation_id}"),
                prompt,
                self.custody.view(),
                attachment,
                continuation,
            ),
            attachment,
            provider,
        )


def make_rig(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    command_timeout: float = 2,
    output_limit: int = 1_000_000,
    continuations: Continuations | None = None,
    custody: Custody | None = None,
) -> Rig:
    executable = fake_codex(tmp_path)
    continuations, turns, custody = continuations or Continuations(), Turns(), custody or Custody()
    adapter = CodexRuntimeAdapter(
        CodexRuntimeConfig(
            "host-1",
            credential_ttl=2,
            command_timeout=command_timeout,
            output_limit=output_limit,
            cancellation_grace=1,
        ),
        CodexContinuationCodec(continuations),
        turns,
        custody,
    )
    monkeypatch.setattr(codex.shutil, "which", lambda name: str(executable))
    probe = adapter.probe()
    assert probe.disposition is ProbeDisposition.READY
    return Rig(adapter, executable, continuations, turns, custody, tmp_path)


def continuation(reference: str) -> Continuation:
    return Continuation(
        ContinuationId(f"continuation-{reference}"),
        ThreadId("agenticus-thread"),
        CODEX_CONTINUATION_DESCRIPTOR,
        reference,
        ContinuationState.IN_USE,
    )


def settle_attachment(attachment: EpisodeAttachment) -> None:
    settled = attachment.settle(drain_timeout=1)
    assert settled.settlement.verified
    assert AUTH_CANARY not in settled.archive and ROLLOUT_CANARY not in settled.archive


def gondolin_invocation(
    tmp_path: Path,
    provider: GondolinEnvironment,
    custody: Custody,
    operation_id: str,
    prompt: str,
    *,
    continuation_value: Continuation | None = None,
) -> tuple[CodexRuntimeInvocation, EpisodeAttachment]:
    source = tmp_path / f"gondolin-workspace-{operation_id}"
    source.mkdir()
    (source / "public-input.txt").write_text("public-workspace-canary")
    binding = MotusAttachmentBinding.open(
        provider,
        f"territory-{operation_id}",
        EnvironmentSpec(
            image="fake-image",
            required_capabilities=frozenset(
                {
                    EnvironmentCapability.VM.value,
                    EnvironmentCapability.MICROVM.value,
                    EnvironmentCapability.PRIVATE_FILE_TRANSFER.value,
                }
            ),
        ),
        workspace_archive_bytes=workspace_archive(source),
        input_digest=f"input-{operation_id}",
    )
    episode_id = EpisodeId(operation_id.replace("operation", "episode"))
    attachment = EpisodeAttachment(
        episode_id=episode_id,
        snapshot=gondolin_snapshot(),
        binding=binding,
        attachment_id=f"agenticus-attachment-{operation_id}",
        deadline=time.monotonic() + 15,
    )
    return (
        CodexRuntimeInvocation(
            operation_id,
            episode_id,
            TurnId(f"turn-{operation_id}"),
            prompt,
            custody.view(),
            attachment,
            continuation_value,
        ),
        attachment,
    )


def test_exact_descriptors_and_opaque_values_hide_provider_bodies() -> None:
    payload = CodexContinuationPayloadV1(THREAD, ROLLOUT_PATH, ROLLOUT_CANARY)

    assert CODEX_PROGRAM.accepts_fresh_start
    assert CODEX_PROGRAM.ownership.value == "provider-owned"
    assert CODEX_PROGRAM.produced_continuation == CODEX_CONTINUATION_DESCRIPTOR.identity
    assert payload.schema_version == 1
    assert ROLLOUT_CANARY.decode() not in repr(payload)
    assert CODEX_VERSION == "0.145.0"
    assert CODEX_SOURCE_COMMIT == "1e85ca099e4265bf89f4016772d299816e231bb3"
    assert CODEX_NPM_INTEGRITY.startswith("sha512-")
    assert CODEX_A2_LOCAL.identity.name == "codex.a2.local"
    with pytest.raises(ValueError, match="safe provider-relative"):
        CodexContinuationPayloadV1(THREAD, "../rollout.jsonl", ROLLOUT_CANARY)
    with pytest.raises(ValueError, match="bounded file"):
        CodexContinuationPayloadV1(THREAD, ROLLOUT_PATH, b"")
    with pytest.raises(ValueError, match="bounded file"):
        CodexContinuationPayloadV1(THREAD, ROLLOUT_PATH, b"x" * (MAX_PRIVATE_FILE_BYTES + 1))


def test_invocation_hides_prompt_and_requires_exact_file_auth_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch)
    invocation, attachment, _ = rig.invocation("operation-values", PROMPT_CANARY)
    assert PROMPT_CANARY not in repr(invocation)
    wrong_connection = replace(
        invocation.connection,
        identity=replace(invocation.connection.identity, profile="ambient"),
    )
    with pytest.raises(ValueError, match="file-auth"):
        CodexRuntimeInvocation(
            invocation.operation_id,
            invocation.episode_id,
            invocation.turn_id,
            invocation.prompt,
            wrong_connection,
            invocation.attachment,
        )
    settle_attachment(attachment)


@pytest.mark.parametrize(
    ("events", "returncode", "code"),
    (
        (({"type": "thread.started", "thread_id": THREAD},), 0, "codex-lifecycle"),
        (
            (
                {"type": "thread.started", "thread_id": THREAD},
                {"type": "turn.started"},
                {"type": "turn.failed", "error": {"message": "safe"}},
            ),
            0,
            "exit-inconsistent",
        ),
        (
            (
                {"type": "thread.started", "thread_id": THREAD},
                {"type": "turn.started"},
                {"type": "turn.completed", "usage": {}},
            ),
            0,
            "missing-agent-message",
        ),
        (
            (
                {"type": "turn.started"},
                {"type": "thread.started", "thread_id": THREAD},
                {"type": "turn.failed", "error": {"message": "safe"}},
            ),
            1,
            "codex-lifecycle",
        ),
    ),
)
def test_jsonl_protocol_fails_closed(events: tuple[dict[str, object], ...], returncode: int, code: str) -> None:
    raw = b"\n".join(json.dumps(event).encode() for event in events)
    with pytest.raises(RuntimeProtocolError, match=code):
        codex._parse_jsonl(raw, returncode)


def test_jsonl_uses_latest_sanitized_completed_agent_message() -> None:
    events = (
        {"type": "thread.started", "thread_id": THREAD},
        {"type": "turn.started"},
        {"type": "item.completed", "item": {"id": "message-1", "type": "agent_message", "text": "first"}},
        {
            "type": "item.completed",
            "item": {"id": "message-2", "type": "agent_message", "text": "\x1b[31mlast\x1b[0m\x00"},
        },
        {"type": "turn.completed", "usage": {"provider": "not retained"}},
    )
    candidate = codex._parse_jsonl(b"\n".join(json.dumps(event).encode() for event in events), 0)
    assert candidate.thread_id == THREAD and candidate.completed and candidate.text == "last�"
    assert "provider" not in repr(candidate)


@pytest.mark.parametrize(
    ("middle", "code"),
    (
        (({"type": "protocol.drift"},), "unknown-event"),
        (({"type": "error", "message": 7},), "malformed-error"),
        (({"type": "item.completed", "item": {"type": "agent_message", "text": "missing-id"}},), "malformed-item"),
        (
            (
                {"type": "item.completed", "item": {"id": "same", "type": "agent_message", "text": "one"}},
                {"type": "item.completed", "item": {"id": "same", "type": "agent_message", "text": "two"}},
            ),
            "duplicate-item-terminal",
        ),
    ),
)
def test_jsonl_rejects_protocol_drift_and_malformed_items(middle: tuple[dict[str, object], ...], code: str) -> None:
    events = (
        {"type": "thread.started", "thread_id": THREAD},
        {"type": "turn.started"},
        *middle,
        {"type": "turn.completed", "usage": {}},
    )
    raw = b"\n".join(json.dumps(event).encode() for event in events)
    with pytest.raises(RuntimeProtocolError, match=code):
        codex._parse_jsonl(raw, 0)


def helper_environment(home: Path, transfer: Path) -> dict[str, str]:
    return {**os.environ, "CODEX_HOME": str(home), "PETRUS_CODEX_ROLLOUT_ROOT": str(transfer)}


def private_roots(tmp_path: Path) -> tuple[Path, Path]:
    home, transfer = tmp_path / "home", tmp_path / "transfer"
    home.mkdir(mode=0o700)
    transfer.mkdir(mode=0o700)
    (home / "auth.json").write_bytes(AUTH_CANARY)
    (transfer / "rollout.jsonl").write_bytes(ROLLOUT_CANARY)
    os.chmod(home / "auth.json", 0o600)
    os.chmod(transfer / "rollout.jsonl", 0o600)
    return home, transfer


def test_private_helper_stages_collects_and_scrubs_one_rollout(tmp_path: Path) -> None:
    home, transfer = private_roots(tmp_path)
    environment = helper_environment(home, transfer)
    staged = subprocess.run(
        (sys.executable, "-c", codex._HELPER_SOURCE, "stage", THREAD, ROLLOUT_PATH),
        env=environment,
        capture_output=True,
        check=True,
    )
    assert codex._parse_helper(staged.stdout, collect=False) is None and staged.stderr == b""
    provider_rollout = home / ROLLOUT_PATH
    provider_rollout.write_bytes(ROLLOUT_CANARY + b"-updated")
    os.chmod(provider_rollout, 0o644)
    (home / "state_5.sqlite").write_bytes(b"provider-state")
    collected = subprocess.run(
        (sys.executable, "-c", codex._HELPER_SOURCE, "collect", THREAD),
        env=environment,
        capture_output=True,
        check=True,
    )
    assert codex._parse_helper(collected.stdout, collect=True) == ROLLOUT_PATH
    assert str(tmp_path).encode() not in collected.stdout + collected.stderr
    assert (transfer / "rollout.jsonl").read_bytes() == ROLLOUT_CANARY + b"-updated"
    assert tuple(path.name for path in home.iterdir()) == ("auth.json",)


def test_helper_rejects_foreign_thread_symlinks_and_oversize_rollout(tmp_path: Path) -> None:
    home, transfer = private_roots(tmp_path)
    environment = helper_environment(home, transfer)
    foreign = subprocess.run(
        (
            sys.executable,
            "-c",
            codex._HELPER_SOURCE,
            "stage",
            THREAD,
            ROLLOUT_PATH.replace(THREAD, OTHER_THREAD),
        ),
        env=environment,
        capture_output=True,
    )
    assert foreign.returncode == 64 and foreign.stdout == foreign.stderr == b""

    (transfer / "rollout.jsonl").unlink()
    (transfer / "rollout.jsonl").symlink_to(home / "auth.json")
    symlink = subprocess.run(
        (sys.executable, "-c", codex._HELPER_SOURCE, "stage", THREAD, ROLLOUT_PATH),
        env=environment,
        capture_output=True,
    )
    assert symlink.returncode == 64 and symlink.stdout == symlink.stderr == b""

    (transfer / "rollout.jsonl").unlink()
    (transfer / "rollout.jsonl").write_bytes(b"x" * (MAX_PRIVATE_FILE_BYTES + 1))
    os.chmod(transfer / "rollout.jsonl", 0o600)
    oversize = subprocess.run(
        (sys.executable, "-c", codex._HELPER_SOURCE, "stage", THREAD, ROLLOUT_PATH),
        env=environment,
        capture_output=True,
    )
    assert oversize.returncode == 64 and oversize.stdout == oversize.stderr == b""

    (transfer / "rollout.jsonl").write_bytes(ROLLOUT_CANARY)
    os.chmod(transfer / "rollout.jsonl", 0o600)
    staged = subprocess.run(
        (sys.executable, "-c", codex._HELPER_SOURCE, "stage", THREAD, ROLLOUT_PATH),
        env=environment,
        capture_output=True,
        check=True,
    )
    assert staged.stderr == b""
    foreign_path = home / ROLLOUT_PATH.replace(THREAD, OTHER_THREAD)
    foreign_path.parent.mkdir(parents=True, exist_ok=True)
    foreign_path.write_bytes(ROLLOUT_CANARY)
    collect = subprocess.run(
        (sys.executable, "-c", codex._HELPER_SOURCE, "collect", THREAD),
        env=environment,
        capture_output=True,
    )
    assert collect.returncode == 64 and collect.stdout == collect.stderr == b""


def test_scrub_removes_but_reports_symlink_invariant_violation(tmp_path: Path) -> None:
    home, transfer = private_roots(tmp_path)
    victim = tmp_path / "victim"
    victim.write_bytes(b"victim")
    (home / "foreign").symlink_to(victim)
    result = subprocess.run(
        (sys.executable, "-c", codex._HELPER_SOURCE, "scrub"),
        env=helper_environment(home, transfer),
        capture_output=True,
    )
    assert result.returncode == 64 and result.stdout == result.stderr == b""
    assert victim.read_bytes() == b"victim"
    assert tuple(path.name for path in home.iterdir()) == ("auth.json",)


def test_probe_freezes_exact_installation_and_resolved_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch)
    result = rig.adapter.probe()
    assert result.disposition is ProbeDisposition.READY
    assert rig.adapter._executable == str(rig.executable)
    assert result.installation is not None
    assert result.installation.components[0].version == CODEX_VERSION
    assert not hasattr(result.installation, "path")


def test_probe_reports_absence_version_drift_and_protocol_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch)
    monkeypatch.setattr(codex.shutil, "which", lambda name: None)
    assert rig.adapter.probe().disposition is ProbeDisposition.NOT_INSTALLED

    monkeypatch.setattr(codex.shutil, "which", lambda name: "/qualified/codex")

    def drifted(argv, **kwargs):
        if argv[-1] == "--version":
            return SimpleNamespace(stdout="codex-cli 0.146.0\n")
        return SimpleNamespace(stdout="SESSION_ID --json --color --sandbox --skip-git-repo-check --ignore-user-config")

    monkeypatch.setattr(codex.subprocess, "run", drifted)
    assert rig.adapter.probe().disposition is ProbeDisposition.INCOMPATIBLE

    def incomplete(argv, **kwargs):
        if argv[-1] == "--version":
            return SimpleNamespace(stdout="codex-cli 0.145.0\n")
        return SimpleNamespace(stdout="SESSION_ID --json")

    monkeypatch.setattr(codex.subprocess, "run", incomplete)
    assert rig.adapter.probe().disposition is ProbeDisposition.UNAVAILABLE
    assert rig.adapter._executable is None


def test_snapshot_mismatch_rejects_before_connection_materialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch)
    wrong_runtime = CapabilityDescriptor(
        DescriptorIdentity(DescriptorKind.RUNTIME, "wrong.runtime", 1),
        frozenset(),
    )
    invocation, attachment, _ = rig.invocation(
        "operation-snapshot",
        "first",
        selected=snapshot(runtime=wrong_runtime),
    )
    with pytest.raises(RuntimeProtocolError, match="resolution-mismatch"):
        rig.adapter.start(invocation)
    assert rig.custody.records == []
    settle_attachment(attachment)


def test_fresh_turn_uses_real_local_private_roots_and_publication_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch)
    invocation, attachment, provider = rig.invocation("operation-first", "first")
    operation = rig.adapter.start(invocation)
    result = operation.wait(5)

    assert result.outcome is TurnOutcome.COMPLETED and result.accepted_appends == 1
    assert result.termination_code == "turn-completed"
    assert result.output_reference == "codex-turn-operation-first"
    assert result.continuation_reference == "codex-continuation-operation-first"
    payload = rig.continuations.load(result.continuation_reference)
    assert payload.thread_id == THREAD and payload.rollout_path == ROLLOUT_PATH
    assert b"first" in payload.rollout and AUTH_CANARY not in payload.rollout
    assert rig.turns.values[result.output_reference] == (THREAD, "answer:first")
    assert rig.custody.auth == AUTH_CANARY + b"|refreshed"
    assert [kind for kind, _ in rig.custody.records] == ["materialize", "activate", "admit", "checkpoint"]

    codex_commands = [command for command in provider.commands if command.argv[0] == str(rig.executable)]
    assert len(codex_commands) == 1
    argv = codex_commands[0].argv
    assert argv[:2] == (str(rig.executable), "exec") and argv[-2:] == ("--", "first")
    assert "--ephemeral" not in argv and "resume" not in argv
    assert argv.count("--json") == 1 and argv.count("--ignore-rules") == 1
    assert argv[argv.index("--config") + 1] == "cli_auth_credentials_store=file"
    assert AUTH_CANARY not in repr(operation).encode() and PROMPT_CANARY not in repr(rig.adapter)
    assert operation.close().disposition is RuntimeCleanupDisposition.CLEAN
    with pytest.raises(RuntimeProtocolError, match="operation-closed"):
        operation.wait()
    settle_attachment(attachment)


def test_hyphen_prefixed_prompt_cannot_be_reparsed_as_a_codex_option(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch)
    prompt = "--dangerously-bypass-approvals-and-sandbox"
    invocation, attachment, provider = rig.invocation("operation-option-prompt", prompt)

    operation = rig.adapter.start(invocation)
    result = operation.wait(5)

    assert result.outcome is TurnOutcome.COMPLETED
    command = next(command for command in provider.commands if command.argv[0] == str(rig.executable))
    assert command.argv[-2:] == ("--", prompt)
    assert operation.close().verified
    settle_attachment(attachment)


def test_native_rollout_continues_in_replacement_local_attachment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch)
    first, first_attachment, _ = rig.invocation("operation-one", "first")
    first_operation = rig.adapter.start(first)
    first_result = first_operation.wait(5)
    assert first_operation.close().verified
    settle_attachment(first_attachment)

    second, second_attachment, provider = rig.invocation(
        "operation-two",
        "second",
        continuation=continuation(first_result.continuation_reference or ""),
    )
    second_operation = rig.adapter.start(second)
    second_result = second_operation.wait(5)
    assert second_result.outcome is TurnOutcome.COMPLETED
    assert rig.turns.values[second_result.output_reference or ""] == (THREAD, "resumed:first:second")
    payload = rig.continuations.load(second_result.continuation_reference or "")
    assert payload.thread_id == THREAD and b"first" in payload.rollout and b"second" in payload.rollout
    argv = next(command.argv for command in provider.commands if command.argv[0] == str(rig.executable))
    assert "resume" in argv and argv[argv.index("resume") + 1] == THREAD and argv[-1] == "second"
    assert second_operation.close().verified
    settle_attachment(second_attachment)


def test_provider_failure_checkpoints_auth_and_returns_native_continuation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch)
    invocation, attachment, _ = rig.invocation("operation-provider-failure", "provider-failure")
    operation = rig.adapter.start(invocation)
    result = operation.wait(5)
    assert result.outcome is TurnOutcome.FAILED and result.accepted_appends == 0
    assert result.termination_code == "provider-failed"
    assert result.output_reference is None and result.continuation_reference is not None
    assert [kind for kind, _ in rig.custody.records][-2:] == ["admit", "checkpoint"]
    assert operation.close().verified
    settle_attachment(attachment)


@pytest.mark.parametrize(
    ("prompt", "timeout", "output_limit", "code"),
    (
        ("timeout", 0.1, 1_000_000, "command-timeout"),
        ("command-signal", 2, 1_000_000, "command-signal"),
        ("output-overflow", 2, 512, "output-overflow"),
        ("malformed-jsonl", 2, 1_000_000, "malformed-jsonl"),
        ("oversize-rollout", 2, 1_000_000, "collect-failed"),
    ),
)
def test_ambiguous_or_malformed_turn_releases_without_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    prompt: str,
    timeout: float,
    output_limit: int,
    code: str,
) -> None:
    rig = make_rig(tmp_path, monkeypatch, command_timeout=timeout, output_limit=output_limit)
    invocation, attachment, _ = rig.invocation(f"operation-{prompt}", prompt)
    operation = rig.adapter.start(invocation)
    result = operation.wait(5)
    assert result.outcome is TurnOutcome.FAILED and result.termination_code == code
    assert result.output_reference is result.continuation_reference is None
    assert "checkpoint" not in [kind for kind, _ in rig.custody.records]
    assert [kind for kind, _ in rig.custody.records][-1] == "release"
    assert operation.close().disposition is RuntimeCleanupDisposition.CLEAN
    settle_attachment(attachment)


def test_cancellation_wins_before_candidate_publication(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = make_rig(tmp_path, monkeypatch, command_timeout=5)
    invocation, attachment, provider = rig.invocation("operation-cancel", "cancel-me")
    operation = rig.adapter.start(invocation)
    deadline = time.monotonic() + 2
    while (
        not any(command.argv[0] == str(rig.executable) for command in provider.commands) and time.monotonic() < deadline
    ):
        time.sleep(0.01)
    assert operation.cancel("navigator-cancelled") is CancellationDisposition.REQUESTED
    assert operation.cancel("navigator-cancelled") is CancellationDisposition.ALREADY_REQUESTED
    result = operation.wait(5)
    assert result.outcome is TurnOutcome.CANCELLED and result.termination_code == "cancelled"
    assert result.output_reference is result.continuation_reference is None
    assert [kind for kind, _ in rig.custody.records][-1] == "release"
    assert operation.cancel("late") is CancellationDisposition.TOO_LATE
    assert operation.close().verified
    settle_attachment(attachment)


def test_cancellation_wins_while_candidate_bodies_are_still_being_stored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    continuations = BlockingContinuations()
    rig = make_rig(tmp_path, monkeypatch, continuations=continuations)
    invocation, attachment, _ = rig.invocation("operation-cancel-before-publish", "first")
    operation = rig.adapter.start(invocation)
    assert continuations.entered.wait(5)

    assert operation.cancel("cancel-before-publication") is CancellationDisposition.REQUESTED
    continuations.release.set()
    result = operation.wait(5)

    assert result.outcome is TurnOutcome.CANCELLED
    assert result.output_reference is result.continuation_reference is None
    assert "checkpoint" not in [kind for kind, _ in rig.custody.records]
    assert [kind for kind, _ in rig.custody.records][-1] == "release"
    assert operation.close().verified
    settle_attachment(attachment)


def test_publication_claim_makes_later_cancellation_too_late(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    custody = PublishingCustody()
    rig = make_rig(tmp_path, monkeypatch, custody=custody)
    invocation, attachment, _ = rig.invocation("operation-publishing", "first")
    operation = rig.adapter.start(invocation)
    assert custody.publication_entered.wait(5)

    assert operation.cancel("late-publication-race") is CancellationDisposition.TOO_LATE
    custody.publication_release.set()
    result = operation.wait(5)

    assert result.outcome is TurnOutcome.COMPLETED
    assert [kind for kind, _ in custody.records][-2:] == ["admit", "checkpoint"]
    assert operation.close().verified
    settle_attachment(attachment)


def test_lookup_first_duplicate_and_changed_request_conflict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = make_rig(tmp_path, monkeypatch)
    invocation, attachment, provider = rig.invocation("operation-dedup", "first")
    operation = rig.adapter.start(invocation)
    result = operation.wait(5)
    assert rig.adapter.start(invocation) is operation
    changed = replace(invocation, prompt="changed")
    with pytest.raises(RuntimeProtocolError, match="operation-conflict"):
        rig.adapter.start(changed)
    assert len([command for command in provider.commands if command.argv[0] == str(rig.executable)]) == 1
    assert result.outcome is TurnOutcome.COMPLETED and operation.close().verified
    settle_attachment(attachment)


def test_operation_identity_includes_the_exact_claimed_continuation_envelope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch)
    rig.continuations.values["same-body"] = CodexContinuationPayloadV1(THREAD, ROLLOUT_PATH, ROLLOUT_CANARY)
    available = replace(continuation("same-body"), state=ContinuationState.AVAILABLE)
    invocation, attachment, _ = rig.invocation(
        "operation-continuation-identity",
        "second",
        continuation=available,
    )
    with pytest.raises(RuntimeProtocolError, match="continuation-not-claimed"):
        rig.adapter.start(invocation)

    claimed = replace(available, state=ContinuationState.IN_USE)
    operation = rig.adapter.start(replace(invocation, continuation=claimed))
    assert operation.wait(5).outcome is TurnOutcome.COMPLETED
    changed_identity = replace(claimed, id=ContinuationId("continuation-other"))
    with pytest.raises(RuntimeProtocolError, match="operation-conflict"):
        rig.adapter.start(replace(invocation, continuation=changed_identity))
    assert operation.close().verified
    settle_attachment(attachment)


def test_real_connection_custody_and_local_motus_route_refresh_and_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installation = tmp_path / "installation"
    storage = SqliteConnectionStorage(installation / "connections.sqlite3")
    materializer = PrivateFileMaterializer(installation / "materialized")
    custody = AgentConnectionCustody(storage, SyntheticKeyOperations(), materializer, clock=time.monotonic)
    custody.enroll_host("host-1", operation_id="enroll-codex-host")
    state = OpaqueState(AUTH_CANARY)
    custody.authorize(
        ConnectionIdentity("codex-real", "codex", "safe-account", "file-auth"),
        state,
        operation_id="authorize-codex",
    )
    assert state.erased

    executable = fake_codex(tmp_path)
    continuations, turns = Continuations(), Turns()
    adapter = CodexRuntimeAdapter(
        CodexRuntimeConfig("host-1", credential_ttl=2, command_timeout=2, cancellation_grace=1),
        CodexContinuationCodec(continuations),
        turns,
        custody,
    )
    monkeypatch.setattr(codex.shutil, "which", lambda name: str(executable))
    assert adapter.probe().disposition is ProbeDisposition.READY

    provider = RecordingLocal()
    source = tmp_path / "real-workspace"
    source.mkdir()
    binding = MotusAttachmentBinding.open(
        provider,
        "territory-real-custody",
        EnvironmentSpec(required_capabilities=frozenset({EnvironmentCapability.PRIVATE_FILE_TRANSFER.value})),
        workspace_archive_bytes=workspace_archive(source),
        input_digest="input-real-custody",
    )
    attachment = EpisodeAttachment(
        episode_id=EpisodeId("episode-real-custody"),
        snapshot=snapshot(),
        binding=binding,
        attachment_id="agenticus-attachment-real-custody",
        deadline=time.monotonic() + 5,
    )
    invocation = CodexRuntimeInvocation(
        "operation-real-custody",
        attachment.episode_id,
        TurnId("turn-real-custody"),
        "first",
        custody.connection("codex-real"),
        attachment,
    )

    operation = adapter.start(invocation)
    result = operation.wait(5)
    assert result.outcome is TurnOutcome.COMPLETED and operation.close().verified
    assert custody.connection("codex-real").state_version == 2
    assert not tuple(materializer.root.iterdir())

    verification = custody.materialize(
        "codex-real",
        "host-1",
        mode=LeaseMode.READ,
        ttl=2,
        operation_id="verify-codex-refresh",
    )
    assert verification.home.read() == AUTH_CANARY + b"|refreshed"
    released = custody.release(verification, operation_id="release-codex-verification")
    assert released.cleanup.removed and not tuple(materializer.root.iterdir())
    settle_attachment(attachment)
    storage.close()


def test_stale_connection_fence_releases_before_provider_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch)
    rig.custody.mismatched_fence = True
    invocation, attachment, provider = rig.invocation("operation-stale", "first")
    operation = rig.adapter.start(invocation)
    result = operation.wait(5)
    assert result.outcome is TurnOutcome.FAILED and result.termination_code == "custody-state-mismatch"
    assert not any(command.argv[0] == str(rig.executable) for command in provider.commands)
    assert [kind for kind, _ in rig.custody.records] == ["materialize", "release"]
    assert operation.close().verified
    settle_attachment(attachment)


def test_connection_cleanup_uncertainty_blocks_candidate_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch)
    rig.custody.checkpoint_cleanup_uncertain = True
    invocation, attachment, _ = rig.invocation("operation-connection-cleanup", "first")
    operation = rig.adapter.start(invocation)
    result = operation.wait(5)
    assert result.outcome is TurnOutcome.FAILED
    assert result.termination_code == "connection-cleanup-uncertain"
    assert result.output_reference is result.continuation_reference is None
    assert operation.close().disposition is RuntimeCleanupDisposition.UNVERIFIED
    settle_attachment(attachment)


def test_private_cleanup_uncertainty_blocks_candidate_result(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = make_rig(tmp_path, monkeypatch)
    provider = UncertainCleanupLocal()
    invocation, attachment, _ = rig.invocation(
        "operation-private-cleanup",
        "first",
        provider=provider,
    )
    operation = rig.adapter.start(invocation)
    result = operation.wait(5)
    assert result.outcome is TurnOutcome.FAILED and result.termination_code == "private-cleanup-uncertain"
    assert operation.close().disposition is RuntimeCleanupDisposition.UNVERIFIED
    settle_attachment(attachment)


def test_expired_deadline_creates_no_connection_or_runtime_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path, monkeypatch)
    invocation, attachment, provider = rig.invocation(
        "operation-expired",
        "first",
        deadline=time.monotonic() - 1,
    )
    operation = rig.adapter.start(invocation)
    result = operation.wait(5)
    assert result.outcome is TurnOutcome.FAILED and result.termination_code == "deadline-exceeded"
    assert rig.custody.records == [] and provider.commands == []
    assert operation.close().disposition is RuntimeCleanupDisposition.NOT_CREATED
    settle_attachment(attachment)


def test_codex_runtime_import_has_no_optional_provider_dependency() -> None:
    code = r"""
import importlib.abc
import sys

blocked = {'openai', 'docker', 'e2b', 'gondolin'}

class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.', 1)[0] in blocked:
            raise AssertionError(f'optional provider import attempted: {fullname}')
        return None

sys.meta_path.insert(0, Blocker())
from petrus.agenticus.runtime.codex import CodexRuntimeAdapter
assert CodexRuntimeAdapter is not None
"""
    subprocess.run([sys.executable, "-c", code], check=True)


def test_gondolin_lane_reuses_one_episode_territory_across_replacement_operation_and_resume(tmp_path: Path) -> None:
    assert CODEX_GONDOLIN_SDK_VERSION == "0.12.0"
    executable = fake_codex(tmp_path, CODEX_GONDOLIN_VERSION)
    sdk = fake_gondolin_sdk(tmp_path, executable)
    root = tmp_path / "gondolin"
    provider = GondolinEnvironment(root, sdk_module=str(sdk), lease_ttl=30)
    continuations, turns, custody = Continuations(), Turns(), Custody()
    adapter = CodexGondolinRuntimeAdapter(
        CodexRuntimeConfig("host-1", credential_ttl=10, command_timeout=10, cancellation_grace=2),
        CodexContinuationCodec(continuations),
        turns,
        custody,
    )
    assert adapter.probe().disposition is ProbeDisposition.UNAVAILABLE

    failed, attachment = gondolin_invocation(
        tmp_path,
        provider,
        custody,
        "operation-gondolin-failed",
        "provider-failure",
    )
    binding = attachment.binding
    assert isinstance(binding, MotusAttachmentBinding)
    territory = binding.lease_identity
    recreated = GondolinEnvironment(root, sdk_module=str(sdk), lease_ttl=30)
    observed = recreated.lookup(territory.operation_id)
    assert observed is not None and observed.identity == territory
    assert len(tuple(root.iterdir())) == 1

    with pytest.raises(RuntimeProtocolError, match="territory-not-qualified"):
        adapter.start(failed)
    probe = adapter.probe(attachment)
    assert probe.disposition is ProbeDisposition.READY
    assert probe.installation is not None
    assert probe.installation.runtime == CODEX_A3_GONDOLIN.identity
    assert probe.installation.platform == "linux" and probe.installation.architecture == "aarch64"
    component = probe.installation.components[0]
    assert component.version == CODEX_GONDOLIN_VERSION
    assert CODEX_GONDOLIN_IMAGE_REF in component.source_identity
    assert CODEX_GONDOLIN_BUILD_ID in component.source_identity
    assert CODEX_GONDOLIN_OCI_DIGEST in component.source_identity

    failed_operation = adapter.start(failed)
    failed_result = failed_operation.wait(10)
    assert failed_result.outcome is TurnOutcome.FAILED and failed_result.termination_code == "provider-failed"
    assert failed_result.output_reference is None and failed_result.continuation_reference is not None
    assert failed_operation.close().verified
    failed_payload = continuations.load(failed_result.continuation_reference)
    assert attachment.binding.lease_identity == territory

    first = CodexRuntimeInvocation(
        "operation-gondolin-replacement",
        attachment.episode_id,
        TurnId("turn-gondolin-replacement"),
        "first",
        custody.view(),
        attachment,
        continuation(failed_result.continuation_reference),
    )
    first_operation = adapter.start(first)
    first_result = first_operation.wait(10)
    assert first_result.outcome is TurnOutcome.COMPLETED and first_result.accepted_appends == 1
    assert first_operation.close().verified
    first_payload = continuations.load(first_result.continuation_reference or "")
    assert turns.values[first_result.output_reference or ""] == (THREAD, "answer:first")
    assert first_payload.thread_id == failed_payload.thread_id
    assert failed_payload.rollout in first_payload.rollout and b"first" in first_payload.rollout
    assert attachment.binding.lease_identity == territory

    second = CodexRuntimeInvocation(
        "operation-gondolin-phase-two",
        attachment.episode_id,
        TurnId("turn-gondolin-phase-two"),
        "second",
        custody.view(),
        attachment,
        continuation(first_result.continuation_reference or ""),
    )
    second_operation = adapter.start(second)
    second_result = second_operation.wait(10)
    assert second_result.outcome is TurnOutcome.COMPLETED and second_operation.close().verified
    second_payload = continuations.load(second_result.continuation_reference or "")
    assert second_payload.thread_id == first_payload.thread_id
    assert first_payload.rollout in second_payload.rollout and b"second" in second_payload.rollout
    assert turns.values[second_result.output_reference or ""] == (THREAD, "resumed:first:second")
    assert attachment.binding.lease_identity == territory

    settled = attachment.settle(drain_timeout=2)
    assert settled.settlement.verified
    restored = tmp_path / "gondolin-settled-workspace"
    extract_workspace_archive(settled.archive, restored)
    assert (restored / "public-input.txt").read_text() == "public-workspace-canary"
    assert AUTH_CANARY not in settled.archive
    assert all(payload.rollout not in settled.archive for payload in (failed_payload, first_payload, second_payload))
    assert binding.cleanup_result is not None
    assert binding.cleanup_result.identity == territory
    assert binding.cleanup_result.disposition is CleanupDisposition.CLEAN
    assert recreated.lookup(territory.operation_id) is None and not any(root.iterdir())


def test_gondolin_lane_rejects_guest_version_drift_before_materialization(tmp_path: Path) -> None:
    executable = fake_codex(tmp_path, CODEX_VERSION)
    sdk = fake_gondolin_sdk(tmp_path, executable)
    provider = GondolinEnvironment(tmp_path / "gondolin-drift", sdk_module=str(sdk), lease_ttl=30)
    custody = Custody()
    adapter = CodexGondolinRuntimeAdapter(
        CodexRuntimeConfig("host-1", credential_ttl=10, command_timeout=10, cancellation_grace=2),
        CodexContinuationCodec(Continuations()),
        Turns(),
        custody,
    )
    invocation, attachment = gondolin_invocation(
        tmp_path,
        provider,
        custody,
        "operation-gondolin-drift",
        "never-run",
    )
    probe = adapter.probe(attachment)
    assert probe.disposition is ProbeDisposition.INCOMPATIBLE
    assert probe.installation is not None and probe.installation.components[0].version == CODEX_VERSION
    assert custody.records == []
    with pytest.raises(RuntimeProtocolError, match="territory-not-qualified"):
        adapter.start(invocation)
    assert attachment.settle(drain_timeout=2).settlement.verified


def test_gondolin_lane_requires_its_exact_guest_helper_before_materialization(tmp_path: Path) -> None:
    executable = fake_codex(tmp_path, CODEX_GONDOLIN_VERSION)
    sdk = fake_gondolin_sdk(tmp_path, executable)
    provider = GondolinEnvironment(tmp_path / "gondolin-helper", sdk_module=str(sdk), lease_ttl=30)
    custody = Custody()
    adapter = CodexGondolinRuntimeAdapter(
        CodexRuntimeConfig("host-1", credential_ttl=10, command_timeout=10, cancellation_grace=2),
        CodexContinuationCodec(Continuations()),
        Turns(),
        custody,
    )
    adapter._helper_executable = "/missing/petrus-python3"
    invocation, attachment = gondolin_invocation(
        tmp_path,
        provider,
        custody,
        "operation-gondolin-helper",
        "never-run",
    )
    probe = adapter.probe(attachment)
    assert probe.disposition is ProbeDisposition.UNAVAILABLE
    assert probe.issues[0].code == "territory-probe-failed" and custody.records == []
    with pytest.raises(RuntimeProtocolError, match="territory-not-qualified"):
        adapter.start(invocation)
    assert attachment.settle(drain_timeout=2).settlement.verified


@pytest.mark.parametrize("failed_phase", ("import", "export", "delete", "cleanup"))
def test_gondolin_lane_private_probe_failure_cleans_and_never_qualifies_or_materializes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failed_phase: str,
) -> None:
    executable = fake_codex(tmp_path, CODEX_GONDOLIN_VERSION)
    sdk = fake_gondolin_sdk(tmp_path, executable)
    provider = GondolinEnvironment(tmp_path / f"gondolin-{failed_phase}", sdk_module=str(sdk), lease_ttl=30)
    custody = Custody()
    adapter = CodexGondolinRuntimeAdapter(
        CodexRuntimeConfig("host-1", credential_ttl=10, command_timeout=10, cancellation_grace=2),
        CodexContinuationCodec(Continuations()),
        Turns(),
        custody,
    )
    invocation, attachment = gondolin_invocation(
        tmp_path,
        provider,
        custody,
        f"operation-gondolin-{failed_phase}",
        "never-run",
    )

    def fail(*_args):
        raise RuntimeError("private probe failed")

    if failed_phase == "import":
        monkeypatch.setattr(provider, "import_private_file", fail)
    elif failed_phase == "export":
        monkeypatch.setattr(provider, "export_private_file", fail)
    elif failed_phase == "delete":
        original_delete = provider.delete_private_file

        def unverified_delete(execution, reference):
            return replace(original_delete(execution, reference), disposition=CleanupDisposition.UNVERIFIED)

        monkeypatch.setattr(provider, "delete_private_file", unverified_delete)

    cleanup_calls = 0
    original_cleanup = provider.cleanup_private_files

    def observed_cleanup(execution):
        nonlocal cleanup_calls
        cleanup_calls += 1
        result = original_cleanup(execution)
        if failed_phase == "cleanup":
            return replace(result, disposition=CleanupDisposition.UNVERIFIED)
        return result

    monkeypatch.setattr(provider, "cleanup_private_files", observed_cleanup)
    probe = adapter.probe(attachment)
    assert probe.disposition is ProbeDisposition.UNAVAILABLE
    assert probe.issues[0].code == "territory-probe-failed"
    assert cleanup_calls == 1 and custody.records == []
    with pytest.raises(RuntimeProtocolError, match="territory-not-qualified"):
        adapter.start(invocation)
    assert attachment.settle(drain_timeout=2).settlement.verified


def test_gondolin_lane_failed_reprobe_revokes_only_that_exact_attachment(tmp_path: Path, monkeypatch) -> None:
    executable = fake_codex(tmp_path, CODEX_GONDOLIN_VERSION)
    sdk = fake_gondolin_sdk(tmp_path, executable)
    provider = GondolinEnvironment(tmp_path / "gondolin-reprobe", sdk_module=str(sdk), lease_ttl=30)
    custody = Custody()
    adapter = CodexGondolinRuntimeAdapter(
        CodexRuntimeConfig("host-1", credential_ttl=10, command_timeout=10, cancellation_grace=2),
        CodexContinuationCodec(Continuations()),
        Turns(),
        custody,
    )
    first, first_attachment = gondolin_invocation(
        tmp_path,
        provider,
        custody,
        "operation-gondolin-reprobe-first",
        "never-run",
    )
    assert adapter.probe(first_attachment).disposition is ProbeDisposition.READY
    original_import = provider.import_private_file
    monkeypatch.setattr(
        provider,
        "import_private_file",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("private probe failed")),
    )
    assert adapter.probe(first_attachment).disposition is ProbeDisposition.UNAVAILABLE
    monkeypatch.setattr(provider, "import_private_file", original_import)

    _second, second_attachment = gondolin_invocation(
        tmp_path,
        provider,
        custody,
        "operation-gondolin-reprobe-second",
        "never-run",
    )
    assert adapter.probe(second_attachment).disposition is ProbeDisposition.READY
    with pytest.raises(RuntimeProtocolError, match="territory-not-qualified"):
        adapter.start(first)
    assert custody.records == []
    assert first_attachment.settle(drain_timeout=2).settlement.verified
    assert second_attachment.settle(drain_timeout=2).settlement.verified


def test_gondolin_lane_cancellation_closes_the_vm_discards_output_and_still_settles(tmp_path: Path) -> None:
    executable = fake_codex(tmp_path, CODEX_GONDOLIN_VERSION)
    sdk = fake_gondolin_sdk(tmp_path, executable)
    provider = GondolinEnvironment(tmp_path / "gondolin-cancel", sdk_module=str(sdk), lease_ttl=30)
    continuations, turns, custody = Continuations(), Turns(), Custody()
    adapter = CodexGondolinRuntimeAdapter(
        CodexRuntimeConfig("host-1", credential_ttl=10, command_timeout=10, cancellation_grace=2),
        CodexContinuationCodec(continuations),
        turns,
        custody,
    )
    invocation, attachment = gondolin_invocation(
        tmp_path,
        provider,
        custody,
        "operation-gondolin-cancel",
        "cancel-me",
    )
    assert adapter.probe(attachment).disposition is ProbeDisposition.READY
    operation = adapter.start(invocation)
    started = tmp_path / "fake-codex-command-started"
    deadline = time.monotonic() + 5
    while not started.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert started.exists()
    assert operation.cancel("navigator-cancelled") is CancellationDisposition.REQUESTED
    result = operation.wait(10)
    assert result.outcome is TurnOutcome.CANCELLED and result.accepted_appends == 0
    assert result.output_reference is result.continuation_reference is None
    assert operation.close().disposition is RuntimeCleanupDisposition.UNVERIFIED
    settled = attachment.settle(drain_timeout=2)
    assert settled.settlement.verified
    assert continuations.values == {} and turns.values == {}
    assert not any((tmp_path / "gondolin-cancel").iterdir())
