"""Deterministic conformance for the exact Claude A2 Local runtime lane."""

from __future__ import annotations

import asyncio
import importlib.metadata
import json
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import petrus.agenticus.runtime.claude as claude
from petrus.agenticus.attachment.binding import MotusAttachmentBinding
from petrus.agenticus.attachment.episode import EpisodeAttachment
from petrus.agenticus.catalog.descriptor import CapabilityDescriptor, DescriptorIdentity, DescriptorKind
from petrus.agenticus.catalog.resolution import ResolutionSnapshot
from petrus.agenticus.connection.custody import (
    AdmissionResult,
    AttachmentFence,
    CleanupEvidence,
    ConnectionIdentity,
    ConnectionStatus,
    ConnectionView,
    LeaseMode,
    Materialization,
    ReleaseResult,
)
from petrus.agenticus.hands.contract import ToolMethod
from petrus.agenticus.hands.workspace import MotusWorkspaceAdapter
from petrus.agenticus.runtime.claude import (
    CLAUDE_CODE_DISTRIBUTION_COMMIT,
    CLAUDE_CODE_VERSION,
    CLAUDE_COLLOCATED_HANDS,
    CLAUDE_CONNECTION_CAPABILITIES,
    CLAUDE_CONTINUATION_CAPABILITIES,
    CLAUDE_CONTINUATION_DESCRIPTOR,
    CLAUDE_LOCAL_TERRITORY,
    CLAUDE_PROGRAM,
    CLAUDE_PROGRAM_CAPABILITIES,
    CLAUDE_SDK_SOURCE_COMMIT,
    CLAUDE_SDK_VERSION,
    ClaudeContinuationCodec,
    ClaudeContinuationPayloadV1,
    ClaudeRuntimeAdapter,
    ClaudeRuntimeConfig,
    ClaudeRuntimeInvocation,
)
from petrus.agenticus.runtime.installation import InstalledComponent, ProbeDisposition, RuntimeInstallation
from petrus.agenticus.runtime.operation import RuntimeCleanupDisposition, RuntimeProtocolError
from petrus.agenticus.runtime.profiles import CLAUDE_A2_LOCAL
from petrus.agenticus.thread.continuation import Continuation, ContinuationState
from petrus.agenticus.thread.identity import ContinuationId, EpisodeId, ThreadId, TurnId
from petrus.agenticus.thread.lifecycle import CancellationDisposition, TurnOutcome
from petrus.motus.execution import EnvironmentSpec
from petrus.motus.execution.archive import workspace_archive
from petrus.motus.execution.providers import LocalProcessEnvironment

SESSION = "11111111-1111-4111-8111-111111111111"
OTHER_SESSION = "22222222-2222-4222-8222-222222222222"
PROJECT_KEY = "-tmp-agenticus-claude-project"
AUTH_CANARY = b"sk-ant-api03-secret-canary-never-render"
PROMPT_CANARY = "prompt-canary-never-render"
TRANSCRIPT_CANARY = "transcript-canary-never-render"
HOST_FENCED_EFFECT = CapabilityDescriptor(
    DescriptorIdentity(DescriptorKind.EFFECT, "host.fenced", 1),
    frozenset({"effect.host-fenced"}),
)


def transcript(*entries: dict[str, object]) -> bytes:
    return claude._encode_transcript(entries, 10_000, 4_000_000)


class Continuations:
    def __init__(self) -> None:
        self.values: dict[str, ClaudeContinuationPayloadV1] = {}

    def store(self, operation_id: str, payload: ClaudeContinuationPayloadV1) -> str:
        reference = f"claude-continuation-{operation_id}"
        existing = self.values.get(reference)
        if existing is not None and existing != payload:
            raise RuntimeError("conflicting Continuation")
        self.values[reference] = payload
        return reference

    def load(self, state_reference: str) -> ClaudeContinuationPayloadV1:
        return self.values[state_reference]


class FailingContinuations(Continuations):
    def store(self, operation_id: str, payload: ClaudeContinuationPayloadV1) -> str:
        raise RuntimeError("continuation canary")


class Turns:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def store_turn(self, operation_id: str, final_text: str) -> str:
        reference = f"claude-turn-{operation_id}"
        existing = self.values.get(reference)
        if existing is not None and existing != final_text:
            raise RuntimeError("conflicting Turn")
        self.values[reference] = final_text
        return reference


class Home:
    def __init__(self, value: bytes) -> None:
        self.value = value

    def read(self) -> bytes:
        return self.value

    def __repr__(self) -> str:
        return "Home(<opaque>)"


class Custody:
    def __init__(self) -> None:
        self.authority_epoch = 3
        self.state_version = 4
        self.records: list[tuple[str, str]] = []
        self.foreign_fence = False
        self.release_uncertain = False
        self.admission_foreign = False

    def view(self) -> ConnectionView:
        return ConnectionView(
            ConnectionIdentity("claude-connection", "claude", "safe-account", "api-key"),
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
        assert connection_id == "claude-connection" and host_id == "host-1"
        assert mode is LeaseMode.READ and ttl > 0
        self.records.append(("materialize", operation_id))
        fence = AttachmentFence(
            "connection-attachment",
            "connection-lease",
            connection_id,
            host_id,
            1,
            self.authority_epoch + int(self.foreign_fence),
            self.state_version,
        )
        return Materialization(fence, mode, time.monotonic() + ttl, Home(AUTH_CANARY))

    def admit_result(self, fence: AttachmentFence, *, operation_id: str) -> AdmissionResult:
        self.records.append(("admit", operation_id))
        return AdmissionResult(
            operation_id,
            "result",
            "foreign-attachment" if self.admission_foreign else fence.attachment_id,
        )

    def release(self, materialization: Materialization, *, operation_id: str) -> ReleaseResult:
        self.records.append(("release", operation_id))
        cleanup = CleanupEvidence(
            materialization.fence.attachment_id,
            True,
            False,
            len(AUTH_CANARY),
            security_violation=self.release_uncertain,
        )
        return ReleaseResult(operation_id, cleanup)


class BlockingAdmissionCustody(Custody):
    def __init__(self) -> None:
        super().__init__()
        self.entered = threading.Event()
        self.resume = threading.Event()

    def admit_result(self, fence: AttachmentFence, *, operation_id: str) -> AdmissionResult:
        self.entered.set()
        assert self.resume.wait(5)
        return super().admit_result(fence, operation_id=operation_id)


@dataclass
class ClientPlan:
    session: str = SESSION
    subtype: str = "success"
    is_error: bool = False
    terminal_reason: str | None = "completed"
    text: str | None = "answer"
    connect_error: bool = False
    query_error: bool = False
    disconnect_error: bool = False
    no_result: bool = False
    multiple_results: bool = False
    mirror_error: bool = False
    block: bool = False
    release_on_interrupt: bool = True
    event_size: int = 64
    transcript_text: str = TRANSCRIPT_CANARY
    store_failure: bool = False
    disconnect_text: str | None = None


class Client:
    def __init__(self, options: dict[str, object], plan: ClientPlan) -> None:
        self.options, self.plan = options, plan
        self.connected = self.disconnected = False
        self.interrupts = 0
        self.loaded: list[dict[str, object]] | None = None
        self.query_started = threading.Event()
        self._release: asyncio.Event | None = None

    async def connect(self, prompt: str | None = None) -> None:
        assert prompt is None
        if self.plan.connect_error:
            raise RuntimeError("connect canary")
        store = self.options["session_store"]
        resume = self.options.get("resume")
        if resume is not None:
            self.loaded = await store.load({"project_key": PROJECT_KEY, "session_id": resume})
        self.connected = True

    async def query(self, prompt: str, session_id: str = "default") -> None:
        assert session_id == "default" and prompt
        self.query_started.set()
        if self.plan.query_error:
            raise RuntimeError("query canary")
        entry = {"type": "assistant", "uuid": f"entry-{len(self.loaded or [])}", "body": self.plan.transcript_text}
        store = self.options["session_store"]
        try:
            if self.plan.store_failure:
                entry["body"] = "x" * 10_000
            await store.append({"project_key": PROJECT_KEY, "session_id": self.plan.session}, [entry])
        except RuntimeError:
            pass

    async def receive_response(self):
        if self.plan.block:
            self._release = asyncio.Event()
            await self._release.wait()
        yield claude._Event(self.plan.event_size)
        if self.plan.mirror_error:
            yield claude._MirrorError(self.plan.event_size)
        if not self.plan.no_result:
            result = claude._Result(
                self.plan.subtype,
                self.plan.is_error,
                self.plan.session,
                self.plan.terminal_reason,
                self.plan.text,
                self.plan.event_size,
            )
            yield result
            if self.plan.multiple_results:
                yield result

    async def interrupt(self) -> None:
        self.interrupts += 1
        if self.plan.release_on_interrupt and self._release is not None:
            self._release.set()

    async def disconnect(self) -> None:
        if self.plan.disconnect_text is not None:
            store = self.options["session_store"]
            await store.append(
                {"project_key": PROJECT_KEY, "session_id": self.plan.session},
                [{"type": "assistant", "uuid": "disconnect-entry", "body": self.plan.disconnect_text}],
            )
        self.disconnected = True
        if self._release is not None:
            self._release.set()
        if self.plan.disconnect_error:
            raise RuntimeError("disconnect canary")


class Factory:
    def __init__(self, *plans: ClientPlan) -> None:
        self.plans = list(plans) or [ClientPlan()]
        self.options: list[dict[str, object]] = []
        self.clients: list[Client] = []

    def create(
        self,
        options: dict[str, object],
        gateway,
        invocation: ClaudeRuntimeInvocation,
    ) -> Client:
        assert gateway is invocation.gateway
        plan = self.plans.pop(0)
        client = Client(options, plan)
        self.options.append(options)
        self.clients.append(client)
        return client


def snapshot(runtime: CapabilityDescriptor = CLAUDE_A2_LOCAL) -> ResolutionSnapshot:
    return ResolutionSnapshot(
        1,
        (
            runtime,
            CLAUDE_CONNECTION_CAPABILITIES,
            CLAUDE_PROGRAM_CAPABILITIES,
            CLAUDE_COLLOCATED_HANDS,
            CLAUDE_LOCAL_TERRITORY,
            CLAUDE_CONTINUATION_CAPABILITIES,
            HOST_FENCED_EFFECT,
        ),
    )


@dataclass
class Rig:
    adapter: ClaudeRuntimeAdapter
    continuations: Continuations
    turns: Turns
    custody: Custody
    factory: Factory
    root: Path

    def invocation(
        self,
        operation_id: str,
        prompt: str = PROMPT_CANARY,
        *,
        continuation_value: Continuation | None = None,
        selected: ResolutionSnapshot | None = None,
        deadline: float | None = None,
    ) -> tuple[ClaudeRuntimeInvocation, EpisodeAttachment]:
        provider = LocalProcessEnvironment()
        source = self.root / f"workspace-{operation_id}"
        source.mkdir()
        (source / "marker.txt").write_text("workspace-marker")
        binding = MotusAttachmentBinding.open(
            provider,
            f"territory-{operation_id}",
            EnvironmentSpec(),
            workspace_archive_bytes=workspace_archive(source),
            input_digest=f"input-{operation_id}",
        )
        episode_id = EpisodeId(operation_id.replace("operation", "episode"))
        attachment = EpisodeAttachment(
            episode_id=episode_id,
            snapshot=selected or snapshot(),
            binding=binding,
            attachment_id=f"attachment-{operation_id}",
            deadline=time.monotonic() + 5 if deadline is None else deadline,
        )
        workspace = MotusWorkspaceAdapter(provider, binding.execution, test_command=("/bin/true",))
        gateway = attachment.gateway(workspace)
        grant = attachment.grants().open(
            tuple(ToolMethod),
            writable_paths=("output.txt",),
            allowed_argv=(("/bin/true",),),
            deadline=attachment.deadline,
            max_calls=16,
        )
        return (
            ClaudeRuntimeInvocation(
                operation_id,
                episode_id,
                TurnId(f"turn-{operation_id}"),
                prompt,
                self.custody.view(),
                attachment,
                gateway,
                grant.grant_epoch,
                continuation_value,
            ),
            attachment,
        )


def make_rig(
    tmp_path: Path,
    *,
    plans: tuple[ClientPlan, ...] = (),
    custody: Custody | None = None,
    continuations: Continuations | None = None,
    wall_timeout: float = 2,
    cancellation_grace: float = 0.1,
    max_message_bytes: int = 1_000_000,
    max_transcript_bytes: int = 4_000_000,
) -> Rig:
    working = tmp_path / "project"
    working.mkdir()
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir(mode=0o700)
    runtime_root.chmod(0o700)
    continuations, turns = continuations or Continuations(), Turns()
    custody = custody or Custody()
    factory = Factory(*plans)
    adapter = ClaudeRuntimeAdapter(
        ClaudeRuntimeConfig(
            "claude-sonnet-4-5",
            working,
            runtime_root,
            host_id="host-1",
            credential_ttl=2,
            wall_timeout=wall_timeout,
            cancellation_grace=cancellation_grace,
            disconnect_timeout=25,
            max_message_bytes=max_message_bytes,
            max_transcript_bytes=max_transcript_bytes,
        ),
        ClaudeContinuationCodec(continuations),
        turns,
        custody,
        client_factory=factory,
    )
    adapter._installation = RuntimeInstallation(
        CLAUDE_A2_LOCAL.identity,
        1,
        (InstalledComponent("claude", CLAUDE_CODE_VERSION, "test:claude"),),
        "test",
        "test",
    )
    adapter._cli = "/qualified/claude"
    return Rig(adapter, continuations, turns, custody, factory, tmp_path)


def continuation(reference: str) -> Continuation:
    return Continuation(
        ContinuationId(f"continuation-{reference}"),
        ThreadId("agenticus-thread"),
        CLAUDE_CONTINUATION_DESCRIPTOR,
        reference,
        ContinuationState.IN_USE,
    )


def settle_attachment(attachment: EpisodeAttachment) -> None:
    settled = attachment.settle(drain_timeout=1)
    assert settled.settlement.verified
    assert AUTH_CANARY not in settled.archive


def test_exact_descriptors_and_opaque_values_hide_provider_bodies(tmp_path: Path) -> None:
    payload = ClaudeContinuationPayloadV1(
        SESSION,
        "d" * 64,
        PROJECT_KEY,
        transcript({"type": "assistant", "body": TRANSCRIPT_CANARY}),
    )
    runtime_root = tmp_path / "private"
    runtime_root.mkdir(mode=0o700)
    runtime_root.chmod(0o700)
    config = ClaudeRuntimeConfig("claude-sonnet-4-5", tmp_path, runtime_root)

    assert CLAUDE_PROGRAM.accepts_fresh_start
    assert CLAUDE_PROGRAM.ownership.value == "provider-owned"
    assert CLAUDE_PROGRAM.produced_continuation == CLAUDE_CONTINUATION_DESCRIPTOR.identity
    assert CLAUDE_A2_LOCAL.identity.name == "claude.a2.local"
    assert CLAUDE_SDK_VERSION == "0.2.128"
    assert CLAUDE_CODE_VERSION == "2.1.220"
    assert CLAUDE_SDK_SOURCE_COMMIT == "ec776735b0eb8a8286827a005b35be1782e1940c"
    assert CLAUDE_CODE_DISTRIBUTION_COMMIT == "7ef6eec9d9ba84ea6f233f26c45f1df5c5991843"
    rendered = repr(payload) + repr(config)
    assert SESSION not in rendered and PROJECT_KEY not in rendered and TRANSCRIPT_CANARY not in rendered
    assert str(tmp_path) not in rendered


@pytest.mark.parametrize("session", ["", "not-a-uuid", "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"])
def test_continuation_rejects_noncanonical_session(session: str) -> None:
    with pytest.raises(ValueError, match="Claude session identity"):
        ClaudeContinuationPayloadV1(session, "d" * 64, PROJECT_KEY, transcript({"type": "assistant"}))


def test_session_store_empty_append_and_unknown_load_are_protocol_noops() -> None:
    async def exercise() -> None:
        store = claude._SessionStore(max_entries=3, max_total_bytes=1024)
        key = {"project_key": PROJECT_KEY, "session_id": SESSION}
        await store.append(key, [])
        assert await store.load(key) is None
        assert await store.load({"project_key": PROJECT_KEY, "session_id": OTHER_SESSION}) is None
        assert not store.failed

    asyncio.run(exercise())


def test_session_store_deduplicates_uuid_and_rejects_conflict() -> None:
    async def exercise() -> None:
        store = claude._SessionStore(max_entries=3, max_total_bytes=1024)
        key = {"project_key": PROJECT_KEY, "session_id": SESSION}
        entry = {"type": "assistant", "uuid": "same", "body": "one"}
        await store.append(key, [entry])
        await store.append(key, [entry])
        project, body = store.snapshot(SESSION)
        assert project == PROJECT_KEY
        assert len(claude._decode_transcript(body, 3, 1024)) == 1
        with pytest.raises(RuntimeError, match="session-store-failed"):
            await store.append(key, [{**entry, "body": "two"}])
        assert store.failed

    asyncio.run(exercise())


def test_official_client_requires_child_and_resume_temp_absence(tmp_path: Path) -> None:
    class Raw:
        def __init__(self, *, clean: bool) -> None:
            self._materialized = SimpleNamespace(config_dir=tmp_path / "resume")
            self._transport = SimpleNamespace(_process=SimpleNamespace(returncode=None))
            self.clean = clean
            self._materialized.config_dir.mkdir()

        async def disconnect(self) -> None:
            if self.clean:
                self._materialized.config_dir.rmdir()
                self._transport._process.returncode = 0

    async def exercise() -> None:
        clean = claude._OfficialClient(Raw(clean=True), SimpleNamespace())
        await clean.disconnect()
        uncertain = claude._OfficialClient(Raw(clean=False), SimpleNamespace())
        with pytest.raises(RuntimeProtocolError, match="client-cleanup-uncertain"):
            await uncertain.disconnect()
        uncertain.client._transport._process.returncode = 0
        uncertain.client._materialized.config_dir.rmdir()

    asyncio.run(exercise())


class ProbeOptions:
    def __init__(
        self,
        tools=None,
        allowed_tools=None,
        mcp_servers=None,
        strict_mcp_config=None,
        permission_mode=None,
        resume=None,
        session_store=None,
        session_store_flush=None,
        setting_sources=None,
        skills=None,
        plugins=None,
        agents=None,
        model=None,
        fallback_model=None,
        cwd=None,
        cli_path=None,
        env=None,
        max_turns=None,
        max_budget_usd=None,
        max_buffer_size=None,
        hooks=None,
        stderr=None,
    ) -> None:
        pass


def probe_sdk(tmp_path: Path, *, protocol: bool = True) -> object:
    values = {
        "__file__": str(tmp_path / "sdk" / "__init__.py"),
        "ClaudeSDKClient": object,
        "ClaudeAgentOptions": ProbeOptions,
        "ResultMessage": object,
        "MirrorErrorMessage": object,
        "UserMessage": object,
        "AssistantMessage": object,
        "SystemMessage": object,
        "StreamEvent": object,
        "RateLimitEvent": object,
        "SessionStore": object,
        "tool": object,
        "create_sdk_mcp_server": object,
        "HookMatcher": object,
    }
    if not protocol:
        values.pop("HookMatcher")
    return SimpleNamespace(**values)


def probe_rig(tmp_path: Path) -> ClaudeRuntimeAdapter:
    rig = make_rig(tmp_path)
    rig.adapter._installation = None
    rig.adapter._cli = None
    return rig.adapter


def fake_cli(tmp_path: Path, version: str = CLAUDE_CODE_VERSION) -> Path:
    executable = tmp_path / "claude"
    executable.write_text(f"#!{sys.executable}\nprint('{version} (Claude Code)')\n")
    executable.chmod(0o755)
    return executable


def test_probe_reports_absent_sdk_before_materialization(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = probe_rig(tmp_path)

    def absent(_name: str) -> str:
        raise importlib.metadata.PackageNotFoundError

    monkeypatch.setattr(claude.importlib.metadata, "version", absent)
    result = adapter.probe(cli_path=str(fake_cli(tmp_path)))

    assert result.disposition is ProbeDisposition.NOT_INSTALLED


@pytest.mark.parametrize(
    ("sdk_version", "cli_version", "disposition"),
    [
        ("0.2.127", CLAUDE_CODE_VERSION, ProbeDisposition.INCOMPATIBLE),
        (CLAUDE_SDK_VERSION, "2.1.219", ProbeDisposition.INCOMPATIBLE),
    ],
)
def test_probe_rejects_version_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    sdk_version: str,
    cli_version: str,
    disposition: ProbeDisposition,
) -> None:
    adapter = probe_rig(tmp_path)
    monkeypatch.setattr(claude.importlib.metadata, "version", lambda _name: sdk_version)
    monkeypatch.setattr(claude.importlib, "import_module", lambda _name: probe_sdk(tmp_path))

    result = adapter.probe(cli_path=str(fake_cli(tmp_path, cli_version)))

    assert result.disposition is disposition
    assert result.installation is not None
    assert not adapter._custody.records


def test_probe_requires_exact_public_protocol(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = probe_rig(tmp_path)
    monkeypatch.setattr(claude.importlib.metadata, "version", lambda _name: CLAUDE_SDK_VERSION)
    monkeypatch.setattr(claude.importlib, "import_module", lambda _name: probe_sdk(tmp_path, protocol=False))

    result = adapter.probe(cli_path=str(fake_cli(tmp_path)))

    assert result.disposition is ProbeDisposition.UNAVAILABLE


def test_probe_records_exact_ready_installation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = probe_rig(tmp_path)
    monkeypatch.setattr(claude.importlib.metadata, "version", lambda _name: CLAUDE_SDK_VERSION)
    monkeypatch.setattr(claude.importlib, "import_module", lambda _name: probe_sdk(tmp_path))

    result = adapter.probe(cli_path=str(fake_cli(tmp_path)))

    assert result.disposition is ProbeDisposition.READY
    assert [component.version for component in result.installation.components] == [
        CLAUDE_SDK_VERSION,
        CLAUDE_CODE_VERSION,
    ]
    assert result.installation.capabilities == frozenset(
        {"runtime.cancel", "runtime.continue", "runtime.local", "runtime.provider-managed"}
    )


def test_fresh_turn_is_one_append_with_isolated_options_and_ordered_custody(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    invocation, attachment = rig.invocation("operation-first")

    operation = rig.adapter.start(invocation)
    result = operation.wait(3)

    assert result.outcome is TurnOutcome.COMPLETED and result.accepted_appends == 1
    assert result.output_reference == "claude-turn-operation-first"
    assert result.continuation_reference == "claude-continuation-operation-first"
    assert rig.custody.records == [
        ("materialize", "operation-first.materialize"),
        ("admit", "operation-first.admit"),
        ("release", "operation-first.release"),
    ]
    options = rig.factory.options[0]
    assert options["tools"] == list(claude._TOOLS) == options["allowed_tools"]
    assert options["strict_mcp_config"] is True and options["setting_sources"] == []
    assert options["skills"] == [] and options["plugins"] == [] and options["agents"] == {}
    assert options["permission_mode"] == "dontAsk" and options["fallback_model"] is None
    assert options["resume"] is None and options["session_store_flush"] == "eager"
    assert options["stderr"] is claude._discard_provider_stderr
    assert Path(options["cli_path"]).name == "claude-launcher"
    environment = options["env"]
    assert environment["ANTHROPIC_API_KEY"].encode() == AUTH_CANARY
    assert all(environment[name] == "" for name in claude._AUTH_ENVIRONMENT)
    assert not tuple(rig.adapter._config.runtime_root.iterdir())
    payload = rig.continuations.values[result.continuation_reference]
    assert payload.session_id == SESSION and payload.project_key == PROJECT_KEY
    assert operation.close().disposition is RuntimeCleanupDisposition.CLEAN
    settle_attachment(attachment)


def test_cli_wrapper_drops_ambient_environment_before_provider_exec(tmp_path: Path) -> None:
    target = tmp_path / "target"
    output = tmp_path / "names.json"
    target.write_text(
        f"#!{sys.executable} -I\nimport json, os, sys\nopen(sys.argv[1], 'w').write(json.dumps(sorted(os.environ)))\n"
    )
    target.chmod(0o700)
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    wrapper = claude._install_cli_wrapper(root, str(target))
    environment = {
        "ANTHROPIC_API_KEY": "synthetic-key",
        "CLAUDE_CONFIG_DIR": str(root),
        "AMBIENT_AUTH_CANARY": "must-not-cross",
        "PYTHONPATH": str(tmp_path / "ambient-python"),
    }

    subprocess.run([wrapper, str(output)], check=True, env=environment, capture_output=True)

    names = set(json.loads(output.read_text()))
    assert {"ANTHROPIC_API_KEY", "CLAUDE_CONFIG_DIR", "HOME", "PATH", "LANG", "LC_ALL"} <= names
    assert "AMBIENT_AUTH_CANARY" not in names and "PYTHONPATH" not in names


def test_multiline_prompt_and_unicode_result_are_preserved_without_controls(tmp_path: Path) -> None:
    plan = ClientPlan(text="\x1b[31mOlá 👋\x1b[0m\x00")
    rig = make_rig(tmp_path, plans=(plan,))
    invocation, attachment = rig.invocation("operation-unicode", prompt="first line\n\tsecond line")

    result = rig.adapter.start(invocation).wait(3)

    assert result.outcome is TurnOutcome.COMPLETED
    assert rig.turns.values["claude-turn-operation-unicode"] == "Olá 👋�"
    settle_attachment(attachment)


@pytest.mark.parametrize("prompt", ["", "nul\x00prompt", "x" * (claude._MAX_PROMPT_BYTES + 1)])
def test_invalid_prompt_rejects_before_materialization(tmp_path: Path, prompt: str) -> None:
    rig = make_rig(tmp_path)
    invocation, attachment = rig.invocation("operation-invalid-prompt")

    with pytest.raises(ValueError, match="Claude prompt"):
        replace(invocation, prompt=prompt)

    assert not rig.custody.records
    settle_attachment(attachment)


def test_native_continuation_resumes_only_accepted_transcript(tmp_path: Path) -> None:
    rig = make_rig(
        tmp_path, plans=(ClientPlan(text="first"), ClientPlan(text="second", transcript_text="second-entry"))
    )
    first_invocation, first_attachment = rig.invocation("operation-first")
    first = rig.adapter.start(first_invocation).wait(3)
    first_payload = rig.continuations.values[first.continuation_reference]
    settle_attachment(first_attachment)
    claimed = continuation(first.continuation_reference)
    second_invocation, second_attachment = rig.invocation("operation-second", continuation_value=claimed)

    second = rig.adapter.start(second_invocation).wait(3)

    assert second.outcome is TurnOutcome.COMPLETED
    assert rig.factory.options[1]["resume"] == SESSION
    assert rig.factory.clients[1].loaded == list(claude._decode_transcript(first_payload.transcript, 10_000, 4_000_000))
    second_payload = rig.continuations.values[second.continuation_reference]
    entries = claude._decode_transcript(second_payload.transcript, 10_000, 4_000_000)
    assert len(entries) == 2 and entries[-1]["body"] == "second-entry"
    settle_attachment(second_attachment)


def test_disconnect_final_flush_is_included_before_continuation_publication(tmp_path: Path) -> None:
    rig = make_rig(tmp_path, plans=(ClientPlan(disconnect_text="final-flush"),))
    invocation, attachment = rig.invocation("operation-final-flush")

    result = rig.adapter.start(invocation).wait(3)

    payload = rig.continuations.values[result.continuation_reference]
    entries = claude._decode_transcript(payload.transcript, 10_000, 4_000_000)
    assert entries[-1]["body"] == "final-flush" and len(entries) == 2
    assert rig.factory.clients[0].disconnected
    settle_attachment(attachment)


@pytest.mark.parametrize(
    "plan",
    [
        ClientPlan(is_error=True),
        ClientPlan(subtype="error_max_turns", is_error=True, terminal_reason="max_turns"),
        ClientPlan(subtype="error_max_budget_usd", is_error=True, terminal_reason="completed"),
        ClientPlan(terminal_reason="aborted_tools"),
    ],
)
def test_provider_terminal_failures_never_append(tmp_path: Path, plan: ClientPlan) -> None:
    rig = make_rig(tmp_path, plans=(plan,))
    invocation, attachment = rig.invocation("operation-failed")

    result = rig.adapter.start(invocation).wait(3)

    assert result.outcome is TurnOutcome.FAILED and result.accepted_appends == 0
    assert result.termination_code == "provider-failed"
    assert not rig.turns.values and not rig.continuations.values
    assert [kind for kind, _ in rig.custody.records] == ["materialize", "release"]
    settle_attachment(attachment)


@pytest.mark.parametrize(
    ("plan", "code"),
    [
        (ClientPlan(no_result=True), "result-cardinality"),
        (ClientPlan(multiple_results=True), "result-cardinality"),
        (ClientPlan(mirror_error=True), "session-store-failed"),
        (ClientPlan(store_failure=True), "session-store-failed"),
        (ClientPlan(event_size=1000), "message-overflow"),
    ],
)
def test_malformed_or_incomplete_streams_fail_closed(tmp_path: Path, plan: ClientPlan, code: str) -> None:
    rig = make_rig(
        tmp_path,
        plans=(plan,),
        max_message_bytes=128 if plan.event_size > 128 else 1_000_000,
        max_transcript_bytes=512 if plan.store_failure else 4_000_000,
    )
    invocation, attachment = rig.invocation("operation-malformed")

    result = rig.adapter.start(invocation).wait(3)

    assert result.outcome is TurnOutcome.FAILED and result.termination_code == code
    assert not rig.turns.values and not rig.continuations.values
    assert [kind for kind, _ in rig.custody.records] == ["materialize", "release"]
    settle_attachment(attachment)


def test_snapshot_and_grant_mismatch_reject_before_materialization(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    foreign = CapabilityDescriptor(
        DescriptorIdentity(DescriptorKind.RUNTIME, "foreign", 1),
        frozenset(),
    )
    invocation, attachment = rig.invocation("operation-foreign", selected=snapshot(foreign))

    with pytest.raises(RuntimeProtocolError, match="resolution-mismatch"):
        rig.adapter.start(invocation)
    assert not rig.custody.records
    settle_attachment(attachment)


def test_stale_local_lease_rejects_before_authority_materialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(tmp_path)
    invocation, attachment = rig.invocation("operation-stale-local")
    provider = attachment.binding.provider
    lookup = provider.lookup
    monkeypatch.setattr(provider, "lookup", lambda _operation_id: None)

    with pytest.raises(RuntimeProtocolError, match="runtime-local-lease-required"):
        rig.adapter.start(invocation)

    assert not rig.custody.records
    monkeypatch.setattr(provider, "lookup", lookup)
    settle_attachment(attachment)


def test_stale_continuation_project_rejects_before_materialization(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    payload = ClaudeContinuationPayloadV1(SESSION, "f" * 64, PROJECT_KEY, transcript({"type": "assistant"}))
    rig.continuations.values["foreign-project"] = payload
    invocation, attachment = rig.invocation("operation-resume", continuation_value=continuation("foreign-project"))

    with pytest.raises(RuntimeProtocolError, match="continuation-project-mismatch"):
        rig.adapter.start(invocation)
    assert not rig.custody.records
    settle_attachment(attachment)


@pytest.mark.parametrize(
    ("plan", "expected"),
    [
        (ClientPlan(connect_error=True), "provider-failed"),
        (ClientPlan(query_error=True), "provider-failed"),
        (ClientPlan(disconnect_error=True), "cleanup-unverified"),
    ],
)
def test_client_failures_clean_or_report_uncertainty(tmp_path: Path, plan: ClientPlan, expected: str) -> None:
    rig = make_rig(tmp_path, plans=(plan,))
    invocation, attachment = rig.invocation("operation-client-failure")

    operation = rig.adapter.start(invocation)
    result = operation.wait(3)

    assert result.outcome is TurnOutcome.FAILED and result.termination_code == expected
    assert not tuple(rig.adapter._config.runtime_root.iterdir())
    assert operation.close().verified is (expected != "cleanup-unverified")
    settle_attachment(attachment)


def test_stale_connection_fence_releases_without_client_start(tmp_path: Path) -> None:
    custody = Custody()
    custody.foreign_fence = True
    rig = make_rig(tmp_path, custody=custody)
    invocation, attachment = rig.invocation("operation-stale")

    result = rig.adapter.start(invocation).wait(3)

    assert result.termination_code == "custody-state-mismatch"
    assert not rig.factory.clients
    assert [kind for kind, _ in custody.records] == ["materialize", "release"]
    settle_attachment(attachment)


def test_release_uncertainty_downgrades_completed_candidate(tmp_path: Path) -> None:
    custody = Custody()
    custody.release_uncertain = True
    rig = make_rig(tmp_path, custody=custody)
    invocation, attachment = rig.invocation("operation-uncertain")

    operation = rig.adapter.start(invocation)
    result = operation.wait(3)

    assert result.outcome is TurnOutcome.FAILED and result.termination_code == "cleanup-unverified"
    assert result.accepted_appends == 0
    assert operation.close().disposition is RuntimeCleanupDisposition.UNVERIFIED
    settle_attachment(attachment)


def test_cancel_interrupts_and_drains_without_publication(tmp_path: Path) -> None:
    rig = make_rig(tmp_path, plans=(ClientPlan(block=True),))
    invocation, attachment = rig.invocation("operation-cancel")
    operation = rig.adapter.start(invocation)
    assert rig.factory.clients or _wait_for(lambda: bool(rig.factory.clients))
    assert rig.factory.clients[0].query_started.wait(2)

    assert operation.cancel("navigator-cancel") is CancellationDisposition.REQUESTED
    assert operation.cancel("navigator-cancel") is CancellationDisposition.ALREADY_REQUESTED
    result = operation.wait(3)

    assert result.outcome is TurnOutcome.CANCELLED and result.accepted_appends == 0
    assert rig.factory.clients[0].interrupts >= 1
    assert not rig.turns.values and not rig.continuations.values
    assert operation.close().verified
    settle_attachment(attachment)


def test_response_timeout_interrupts_then_fails_after_bounded_grace(tmp_path: Path) -> None:
    rig = make_rig(
        tmp_path,
        plans=(ClientPlan(block=True, release_on_interrupt=False),),
        wall_timeout=0.1,
        cancellation_grace=0.05,
    )
    invocation, attachment = rig.invocation("operation-timeout")

    operation = rig.adapter.start(invocation)
    result = operation.wait(3)

    assert result.outcome is TurnOutcome.FAILED and result.termination_code == "deadline-exceeded"
    assert rig.factory.clients[0].interrupts == 1
    assert operation.close().verified
    settle_attachment(attachment)


def test_response_completing_after_timeout_interrupt_never_publishes(tmp_path: Path) -> None:
    rig = make_rig(
        tmp_path,
        plans=(ClientPlan(block=True, release_on_interrupt=True),),
        wall_timeout=0.1,
        cancellation_grace=0.2,
    )
    invocation, attachment = rig.invocation("operation-late-result")

    result = rig.adapter.start(invocation).wait(3)

    assert result.outcome is TurnOutcome.FAILED and result.termination_code == "deadline-exceeded"
    assert result.accepted_appends == 0 and result.output_reference is None
    assert result.continuation_reference is None
    assert not rig.turns.values and not rig.continuations.values
    settle_attachment(attachment)


def test_candidate_store_failure_returns_no_public_references(tmp_path: Path) -> None:
    continuations = FailingContinuations()
    rig = make_rig(tmp_path, continuations=continuations)
    invocation, attachment = rig.invocation("operation-store-failure")

    result = rig.adapter.start(invocation).wait(3)

    assert result.outcome is TurnOutcome.FAILED and result.accepted_appends == 0
    assert result.output_reference is None and result.continuation_reference is None
    settle_attachment(attachment)


def test_result_first_and_publication_claim_make_cancellation_too_late(tmp_path: Path) -> None:
    custody = BlockingAdmissionCustody()
    rig = make_rig(tmp_path, custody=custody)
    invocation, attachment = rig.invocation("operation-publication")
    operation = rig.adapter.start(invocation)
    assert custody.entered.wait(2)

    assert operation.cancel("too-late") is CancellationDisposition.TOO_LATE
    custody.resume.set()
    result = operation.wait(3)

    assert result.outcome is TurnOutcome.COMPLETED
    assert operation.cancel("after-result") is CancellationDisposition.TOO_LATE
    settle_attachment(attachment)


def test_operation_redelivery_is_idempotent_and_conflicts_fail(tmp_path: Path) -> None:
    rig = make_rig(tmp_path, plans=(ClientPlan(block=True),))
    invocation, attachment = rig.invocation("operation-duplicate")
    first = rig.adapter.start(invocation)

    assert rig.adapter.start(invocation) is first
    conflicting = replace(invocation, prompt="different prompt")
    with pytest.raises(RuntimeProtocolError, match="operation-conflict"):
        rig.adapter.start(conflicting)
    first.cancel("finish-test")
    first.wait(3)
    settle_attachment(attachment)


def test_output_and_authority_canaries_never_render_or_log(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    plan = ClientPlan(text="answer", transcript_text=TRANSCRIPT_CANARY)
    rig = make_rig(tmp_path, plans=(plan,))
    invocation, attachment = rig.invocation("operation-canary")

    operation = rig.adapter.start(invocation)
    result = operation.wait(3)
    rendered = (
        repr(rig.adapter) + repr(invocation) + repr(operation) + repr(result) + repr(operation.close()) + caplog.text
    )

    for canary in (AUTH_CANARY.decode(), PROMPT_CANARY, TRANSCRIPT_CANARY, SESSION):
        assert canary not in rendered
    settle_attachment(attachment)


def _wait_for(predicate, timeout: float = 2) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


class HookMatcher:
    def __init__(self, matcher=None, hooks=None) -> None:
        self.matcher, self.hooks = matcher, hooks


@dataclass
class Tool:
    name: str
    schema: dict[str, object]
    handler: object


class RawClient:
    def __init__(self, options) -> None:
        self.options = options


class ToolSdk:
    HookMatcher = HookMatcher
    ClaudeAgentOptions = dict
    ClaudeSDKClient = RawClient

    @staticmethod
    def tool(name, _description, schema):
        return lambda handler: Tool(name, schema, handler)

    @staticmethod
    def create_sdk_mcp_server(name, tools):
        return {"name": name, "tools": tools}


def test_official_mcp_bridge_denies_unknown_and_uses_provider_tool_identity(tmp_path: Path) -> None:
    rig = make_rig(tmp_path)
    invocation, attachment = rig.invocation("operation-tools")
    factory = claude._OfficialFactory(ToolSdk())
    options: dict[str, object] = {}

    wrapped = factory.create(options, invocation.gateway, invocation)
    hooks = wrapped.client.options["hooks"]["PreToolUse"][0].hooks
    server = wrapped.client.options["mcp_servers"]["petrus_hands"]
    read = next(tool for tool in server["tools"] if tool.name == "workspace_read")

    async def exercise() -> None:
        denied = await hooks[0](
            {"tool_name": "Read", "tool_use_id": "foreign-call", "tool_input": {"path": "marker.txt"}},
            None,
            {},
        )
        assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
        subagent = await hooks[0](
            {
                "tool_name": "mcp__petrus_hands__workspace_read",
                "tool_use_id": "subagent-call",
                "tool_input": {"path": "marker.txt"},
                "agent_id": "foreign-agent",
            },
            None,
            {},
        )
        assert subagent["hookSpecificOutput"]["permissionDecision"] == "deny"
        allowed = await hooks[0](
            {
                "tool_name": "mcp__petrus_hands__workspace_read",
                "tool_use_id": "provider-tool-call",
                "tool_input": {"path": "marker.txt"},
            },
            None,
            {},
        )
        assert allowed["hookSpecificOutput"]["permissionDecision"] == "allow"
        response = await read.handler({"path": "marker.txt"})
        body = json.loads(response["content"][0]["text"])
        assert body["ok"] is True and body["call_id"] == "provider-tool-call"

    asyncio.run(exercise())
    assert invocation.gateway.counters().adapter_entries == 1
    settle_attachment(attachment)


def test_runtime_module_import_has_no_optional_sdk_dependency() -> None:
    source = """
import sys
class Block:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'claude_agent_sdk' or fullname.startswith('claude_agent_sdk.'):
            raise RuntimeError('optional SDK imported')
        return None
sys.meta_path.insert(0, Block())
from petrus.agenticus.runtime.claude import ClaudeRuntimeAdapter
assert 'claude_agent_sdk' not in sys.modules
"""
    result = subprocess.run((sys.executable, "-c", source), capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
