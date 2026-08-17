"""Focused deterministic conformance for the exact Pi native A2/A4 lanes."""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, cast

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

import petrus.agenticus.runtime.pi as pi
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
from petrus.agenticus.connection.materialization import MaterializedState, PrivateFileMaterializer
from petrus.agenticus.connection.storage import SqliteConnectionStorage, StorageError
from petrus.agenticus.hands.contract import RejectionCategory, ToolMethod, ToolResult
from petrus.agenticus.hands.workspace import MotusWorkspaceAdapter
from petrus.agenticus.runtime.installation import InstalledComponent, RuntimeInstallation
from petrus.agenticus.runtime.operation import RuntimeCleanupDisposition, RuntimeProtocolError
from petrus.agenticus.runtime.pi_recovery import PiOperationPhase, PiRecoveredRuntime, SqlitePiOperationLedger
from petrus.agenticus.runtime.profiles import PI_NATIVE_A2_LOCAL, PI_NATIVE_A4_E2B, PI_NATIVE_A4_GONDOLIN
from petrus.agenticus.thread.continuation import Continuation, ContinuationState
from petrus.agenticus.thread.identity import ContinuationId, EpisodeId, ThreadId, TurnId
from petrus.agenticus.thread.lifecycle import CancellationDisposition, TurnOutcome
from petrus.motus.execution import EnvironmentSpec
from petrus.motus.execution.archive import workspace_archive
from petrus.motus.execution.providers import LocalProcessEnvironment

SESSION = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
KEY = b"pi-key-canary-never-render"
AUTH = b'{"anthropic":{"type":"oauth","access":"pi-access-canary","refresh":"pi-refresh-canary","expires":1}}'
REFRESHED_AUTH = b'{"anthropic":{"type":"oauth","access":"pi-access-next","refresh":"pi-refresh-next","expires":2}}'
OPENAI_AUTH = b'{"openai-codex":{"type":"oauth","access":"pi-openai-access-canary","refresh":"pi-openai-refresh-canary","expires":1,"accountId":"pi-openai-account-canary"}}'
REFRESHED_OPENAI_AUTH = b'{"openai-codex":{"type":"oauth","access":"pi-openai-access-next","refresh":"pi-openai-refresh-next","expires":2,"accountId":"pi-openai-account-next"}}'
PROMPT = "pi-prompt-canary-never-render"
SESSION_CANARY = "pi-session-canary-never-render"
EFFECT = CapabilityDescriptor(
    DescriptorIdentity(DescriptorKind.EFFECT, "host.fenced", 1), frozenset({"effect.host-fenced"})
)


def session(identity: str = SESSION, *entries: dict[str, object]) -> bytes:
    values = ({"type": "session", "version": 3, "id": identity}, *entries)
    return b"".join(json.dumps(value, separators=(",", ":"), allow_nan=False).encode() + b"\n" for value in values)


class Continuations:
    def __init__(self) -> None:
        self.values: dict[str, pi.PiContinuationPayloadV1] = {}
        self.fail = False

    def store(self, operation_id: str, payload: pi.PiContinuationPayloadV1) -> str:
        if self.fail:
            raise RuntimeError("store failed")
        ref = f"pi-continuation-{operation_id}"
        if ref in self.values and self.values[ref] != payload:
            raise RuntimeError("conflict")
        self.values[ref] = payload
        return ref

    def load(self, state_reference: str) -> pi.PiContinuationPayloadV1:
        return self.values[state_reference]


class Turns:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.fail = False

    def store_turn(self, operation_id: str, final_text: str) -> str:
        if self.fail:
            raise RuntimeError("store failed")
        ref = f"pi-turn-{operation_id}"
        self.values[ref] = final_text
        return ref


class Home:
    def __init__(self, value: bytes) -> None:
        self.value = value

    def read(self) -> bytes:
        return self.value

    def replace(self, value: bytes) -> None:
        self.value = value

    def __repr__(self) -> str:
        return "Home(<opaque>)"


class Custody:
    def __init__(self, profile: str = "api-key", provider: str = "provider") -> None:
        self.records: list[tuple[str, str]] = []
        self.uncertain = False
        self.checkpoint_fail = False
        self.profile, self.provider = profile, provider
        self.home = Home(KEY if profile == "api-key" else OPENAI_AUTH if provider == "openai-codex" else AUTH)
        self.state_version = 4

    def view(self) -> ConnectionView:
        return ConnectionView(
            ConnectionIdentity("connection", self.provider, "account", self.profile),
            ConnectionStatus.READY,
            3,
            self.state_version,
            None,
        )

    def materialize(self, connection_id, host_id, *, mode, ttl, operation_id):
        expected = LeaseMode.READ if self.profile == "api-key" else LeaseMode.REFRESH
        assert (connection_id, host_id, mode) == ("connection", "host", expected)
        self.records.append(("materialize", operation_id))
        return Materialization(
            AttachmentFence("credential", "lease", connection_id, host_id, 1, 3, self.state_version),
            mode,
            time.monotonic() + ttl,
            cast(MaterializedState, self.home),
        )

    def activate(self, materialization, *, operation_id):
        assert materialization.mode is LeaseMode.REFRESH
        self.records.append(("activate", operation_id))

    def admit_result(self, fence, *, operation_id):
        self.records.append(("admit", operation_id))
        return AdmissionResult(operation_id, "result", fence.attachment_id)

    def checkpoint(self, materialization, *, operation_id):
        assert materialization.mode is LeaseMode.REFRESH
        self.records.append(("checkpoint", operation_id))
        if self.checkpoint_fail:
            raise RuntimeError("checkpoint failed")
        self.state_version += 1
        return PublicationResult(
            operation_id,
            self.view(),
            CleanupEvidence(materialization.fence.attachment_id, True, False, len(self.home.read())),
        )

    def release(self, materialization, *, operation_id):
        self.records.append(("release", operation_id))
        return ReleaseResult(
            operation_id,
            CleanupEvidence(
                materialization.fence.attachment_id,
                True,
                False,
                len(self.home.read()),
                security_violation=self.uncertain,
            ),
        )


class Keys:
    def __init__(self) -> None:
        self.key = b"k" * 32
        self.nonce = 0

    def seal(self, context: KeyContext, plaintext: bytearray) -> bytes:
        self.nonce += 1
        nonce = self.nonce.to_bytes(12, "big")
        return nonce + AESGCM(self.key).encrypt(nonce, bytes(plaintext), context.authenticated_data())

    def open(self, context: KeyContext, ciphertext: bytes) -> bytearray:
        return bytearray(AESGCM(self.key).decrypt(ciphertext[:12], ciphertext[12:], context.authenticated_data()))

    def erase(self, connection_id: str) -> KeyErasureEvidence:
        return KeyErasureEvidence(connection_id, True)


@dataclass
class Plan:
    error: str | None = None
    provider_failed: bool = False
    block: bool = False
    clean: bool = True
    identity: str = SESSION
    text: str = "answer"
    refreshed_auth: bytes | None = None
    omit_auth: bool = False


class Client:
    def __init__(self, plan: Plan) -> None:
        self.plan = plan
        self.entered = threading.Event()
        self.prior: pi.PiContinuationPayloadV1 | None = None
        self.native_auth: bytes | None = None

    def run(self, gateway, invocation, current, deadline):
        self.entered.set()
        while self.plan.block and current() and time.monotonic() < deadline:
            time.sleep(0.005)
        if self.plan.error:
            raise RuntimeProtocolError(self.plan.error)
        if not current():
            raise RuntimeProtocolError("cancelled")
        if time.monotonic() >= deadline:
            raise RuntimeProtocolError("deadline-exceeded")
        if self.plan.provider_failed:
            refreshed = (
                self.plan.refreshed_auth
                if self.plan.refreshed_auth is not None
                else REFRESHED_OPENAI_AUTH
                if self.native_auth == OPENAI_AUTH
                else REFRESHED_AUTH
            )
            return pi._HelperResult(None, refreshed, "provider-failed")
        prior = self.prior
        body = (
            (prior.session_jsonl if prior else session(self.plan.identity))
            + json.dumps({"type": "message", "body": SESSION_CANARY}).encode()
            + b"\n"
        )
        candidate = pi._Candidate(self.plan.identity, self.plan.text, body)
        refreshed = (
            self.plan.refreshed_auth
            if self.plan.refreshed_auth is not None
            else REFRESHED_OPENAI_AUTH
            if self.native_auth == OPENAI_AUTH
            else REFRESHED_AUTH
        )
        return pi._HelperResult(
            candidate,
            refreshed if self.native_auth is not None and not self.plan.omit_auth else None,
            "turn-completed",
        )

    def close(self) -> bool:
        return self.plan.clean


class Factory:
    def __init__(self, *plans: Plan) -> None:
        self.plans = list(plans) or [Plan()]
        self.calls: list[dict[str, Any]] = []
        self.clients: list[Client] = []
        self.fail_create = False

    def create(self, **kwargs):
        if self.fail_create:
            raise RuntimeError("spawn failed")
        self.calls.append(kwargs)
        client = Client(self.plans.pop(0))
        client.prior = kwargs["prior"]
        client.native_auth = kwargs["native_auth"]
        self.clients.append(client)
        return client


def snapshot(
    runtime=None,
    connection=pi.PI_CONNECTION_CAPABILITIES,
    *,
    territory_profile: str = "local",
) -> ResolutionSnapshot:
    selected_runtime = (
        runtime
        or {
            "local": PI_NATIVE_A2_LOCAL,
            "gondolin": PI_NATIVE_A4_GONDOLIN,
            "e2b": PI_NATIVE_A4_E2B,
        }[territory_profile]
    )
    hands = pi.PI_COLLOCATED_HANDS if territory_profile == "local" else pi.PI_CAPABILITY_SCOPED_HANDS
    territory = {
        "local": pi.PI_LOCAL_TERRITORY,
        "gondolin": pi.PI_GONDOLIN_TERRITORY,
        "e2b": pi.PI_E2B_TERRITORY,
    }[territory_profile]
    return ResolutionSnapshot(
        1,
        (
            selected_runtime,
            connection,
            pi.PI_PROGRAM_CAPABILITIES,
            hands,
            territory,
            pi.PI_CONTINUATION_CAPABILITIES,
            EFFECT,
        ),
    )


class Rig:
    def __init__(
        self,
        tmp_path: Path,
        *plans: Plan,
        wall_timeout: float = 2,
        profile: str = "api-key",
        provider: str | None = None,
        territory_profile: str = "local",
        predecessor: Rig | None = None,
    ) -> None:
        self.root = tmp_path
        tmp_path.mkdir(parents=True, exist_ok=True)
        working, private = tmp_path / "working", tmp_path / "private"
        if predecessor is None:
            working.mkdir()
        else:
            working = predecessor.adapter._config.working_directory
        private.mkdir(mode=0o700)
        private.chmod(0o700)
        selected_provider = provider or ("provider" if profile == "api-key" else "anthropic")
        catalog = (
            pi.PI_CC_PATCH_SUBSCRIPTION_CATALOG if profile == "cc-patch-subscription" else pi.PI_SUBSCRIPTION_CATALOG
        )
        selected_model = "model" if profile == "api-key" else dict(catalog)[selected_provider]
        self.profile, self.territory_profile = profile, territory_profile
        self.connection = {
            "api-key": pi.PI_CONNECTION_CAPABILITIES,
            "subscription": pi.PI_SUBSCRIPTION_CONNECTION_CAPABILITIES,
            "cc-patch-subscription": pi.PI_CC_PATCH_CONNECTION_CAPABILITIES,
        }[profile]
        self.continuations = predecessor.continuations if predecessor is not None else Continuations()
        self.turns = predecessor.turns if predecessor is not None else Turns()
        self.custody = predecessor.custody if predecessor is not None else Custody(profile, selected_provider)
        self.factory = Factory(*plans)
        self.adapter = pi.PiRuntimeAdapter(
            pi.PiRuntimeConfig(
                selected_provider,
                selected_model,
                working,
                private,
                host_id="host",
                cc_patch=profile == "cc-patch-subscription",
                credential_ttl=10,
                wall_timeout=wall_timeout,
                cancellation_grace=0.05,
                territory_profile=territory_profile,
            ),
            pi.PiContinuationCodec(self.continuations),
            self.turns,
            self.custody,
            client_factory=self.factory,
        )
        self.adapter._installation = RuntimeInstallation(
            self.adapter.descriptor.identity,
            1,
            (InstalledComponent("pi-coding-agent", pi.PI_SDK_VERSION, pi.PI_SDK_SOURCE),),
            "test",
            "test",
        )
        self.adapter._node, self.adapter._sdk_entrypoint = "/fake/node", "/fake/pi/index.js"
        if profile == "cc-patch-subscription":
            self.adapter._cc_patch_entrypoint = "/fake/pi-cc-patch/index.ts"

    def invocation(
        self,
        name: str,
        *,
        continuation=None,
        selected=None,
        deadline=None,
        capabilities: tuple[ToolMethod, ...] | None = None,
        max_calls: int = 16,
    ):
        provider = LocalProcessEnvironment()
        source = self.root / f"source-{name}"
        source.mkdir()
        (source / "marker.txt").write_text("marker")
        binding = MotusAttachmentBinding.open(
            provider,
            f"territory-{name}",
            EnvironmentSpec(),
            workspace_archive_bytes=workspace_archive(source),
            input_digest=name,
        )
        if self.territory_profile != "local":
            provider.provider = self.territory_profile
            object.__setattr__(binding.execution.lease, "provider", self.territory_profile)
            object.__setattr__(binding._lease, "provider", self.territory_profile)  # noqa: SLF001
            provider._leases[binding.lease_identity.operation_id] = binding._lease  # noqa: SLF001
        episode = EpisodeId(f"episode-{name}")
        attachment = EpisodeAttachment(
            episode_id=episode,
            snapshot=selected or snapshot(connection=self.connection, territory_profile=self.territory_profile),
            binding=binding,
            attachment_id=f"attachment-{name}",
            deadline=time.monotonic() + (20 if self.profile != "api-key" else 5) if deadline is None else deadline,
        )
        gateway = attachment.gateway(MotusWorkspaceAdapter(provider, binding.execution, test_command=("/bin/true",)))
        admitted = tuple(ToolMethod) if capabilities is None else capabilities
        grant = attachment.grants().open(
            admitted,
            writable_paths=("output.txt",) if ToolMethod.WORKSPACE_WRITE in admitted else (),
            allowed_argv=(("/bin/true",),) if ToolMethod.WORKSPACE_SHELL in admitted else (),
            deadline=attachment.deadline,
            max_calls=max_calls,
        )
        return pi.PiRuntimeInvocation(
            name,
            episode,
            TurnId(f"turn-{name}"),
            PROMPT,
            self.custody.view(),
            attachment,
            gateway,
            grant.grant_epoch,
            continuation,
        ), attachment


def claimed(reference: str) -> Continuation:
    return Continuation(
        ContinuationId(f"id-{reference}"),
        ThreadId("thread"),
        pi.PI_CONTINUATION_DESCRIPTOR,
        reference,
        ContinuationState.IN_USE,
    )


def test_descriptors_pins_and_reprs_are_exact_and_opaque(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    invocation, _ = rig.invocation("opaque")
    payload = pi.PiContinuationPayloadV1(SESSION, "d" * 64, session(SESSION, {"body": SESSION_CANARY}))
    assert pi.PI_PROGRAM.ownership.value == "harness-owned" and pi.PI_PROGRAM.owns_steering is False
    assert pi.PI_SDK_VERSION == pi.PI_AI_VERSION == "0.83.0"
    assert pi.PI_NATIVE_A2_LOCAL.identity.name == "pi.native.a2.local"
    assert pi.PI_API_KEY_CATALOG == (
        ("anthropic", "claude-sonnet-4-5"),
        ("openrouter", "anthropic/claude-sonnet-4.5"),
        ("openai", "gpt-5.6-sol"),
    )
    assert pi.PI_SUBSCRIPTION_CATALOG == (
        ("anthropic", "claude-sonnet-4-5"),
        ("openai-codex", "gpt-5.6-sol"),
    )
    assert pi.PI_CC_PATCH_SUBSCRIPTION_CATALOG == (("anthropic", "claude-sonnet-4-5"),)
    assert pi.PI_CC_PATCH_VERSION == "1.0.1"
    assert pi.PI_CC_PATCH_SOURCE_COMMIT == "1891a39e3e1c61e37f950159fdc51de1ecffce84"
    assert pi.PI_SUBSCRIPTION_CONNECTION_CAPABILITIES.offers == frozenset({"connection.pi-compatible"})
    assert pi.PI_CC_PATCH_CONNECTION_CAPABILITIES.offers == frozenset({"connection.pi-compatible"})
    rendered = repr(payload) + repr(rig.adapter._config) + repr(invocation) + repr(rig.adapter)
    for secret in (SESSION, SESSION_CANARY, PROMPT, "pi-access-canary", "pi-refresh-canary", str(tmp_path)):
        assert secret not in rendered


@pytest.mark.parametrize(
    ("territory_profile", "descriptor", "hands_name", "territory_name", "capabilities"),
    [
        (
            "local",
            PI_NATIVE_A2_LOCAL,
            "pi.collocated",
            "motus.local",
            frozenset({"runtime.cancel", "runtime.continue", "runtime.local", "runtime.harness-owned"}),
        ),
        (
            "gondolin",
            PI_NATIVE_A4_GONDOLIN,
            "pi.capability-scoped",
            "motus.gondolin",
            frozenset({"runtime.cancel", "runtime.continue", "runtime.split", "runtime.harness-owned"}),
        ),
        (
            "e2b",
            PI_NATIVE_A4_E2B,
            "pi.capability-scoped",
            "motus.e2b",
            frozenset({"runtime.cancel", "runtime.continue", "runtime.split", "runtime.harness-owned"}),
        ),
    ],
)
def test_native_territory_profile_selects_exact_descriptor_and_capabilities(
    tmp_path: Path,
    territory_profile: str,
    descriptor: CapabilityDescriptor,
    hands_name: str,
    territory_name: str,
    capabilities: frozenset[str],
) -> None:
    rig = Rig(tmp_path / territory_profile, territory_profile=territory_profile)

    assert rig.adapter.descriptor is descriptor
    assert rig.adapter.hands.identity.name == hands_name
    assert rig.adapter.territory.identity.name == territory_name
    assert rig.adapter._runtime_capabilities == capabilities
    assert f"territory_profile={territory_profile!r}" in repr(rig.adapter)


def test_native_territory_profile_defaults_local_and_rejects_unknown(tmp_path: Path) -> None:
    fields = pi.PiRuntimeConfig.__dataclass_fields__
    working, private = tmp_path / "working", tmp_path / "private"
    working.mkdir()
    private.mkdir(mode=0o700)

    assert fields["territory_profile"].default == "local"
    with pytest.raises(ValueError, match="territory_profile"):
        pi.PiRuntimeConfig("provider", "model", working, private, territory_profile="docker")


@pytest.mark.parametrize("identity", ["", "not-uuid", "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"])
def test_payload_rejects_noncanonical_identity(identity: str) -> None:
    with pytest.raises(ValueError, match="session identity"):
        pi.PiContinuationPayloadV1(identity, "d" * 64, session())


@pytest.mark.parametrize(
    "body",
    [
        b"{}",
        b"{}\n",
        b'{"type":"session","version":3,"id":"11111111-1111-4111-8111-111111111111","x":NaN}\n',
        session() + session(),
    ],
)
def test_native_jsonl_is_complete_strict_and_has_one_matching_header(body: bytes) -> None:
    with pytest.raises(ValueError):
        pi.PiContinuationPayloadV1(SESSION, "d" * 64, body)


def test_native_jsonl_is_preserved_without_rewriting() -> None:
    body = b'{ "type":"session", "version":3, "id":"11111111-1111-4111-8111-111111111111" }\n'
    assert pi.PiContinuationPayloadV1(SESSION, "d" * 64, body).session_jsonl == body


@pytest.mark.parametrize(
    "encoded",
    [
        base64.b64encode(AUTH).decode() + "=",
        base64.b64encode(AUTH + b"\0").decode(),
        base64.b64encode(AUTH).decode(),
    ],
)
def test_native_auth_protocol_rejects_noncanonical_or_oversized_frames(encoded: str) -> None:
    maximum = len(AUTH) - 1 if encoded == base64.b64encode(AUTH).decode() else len(AUTH) + 1
    with pytest.raises(ValueError):
        pi._decode_native_auth(encoded, "anthropic", maximum)


def test_fresh_success_has_exact_custody_and_private_invocation(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    invocation, _ = rig.invocation("first")
    operation = rig.adapter.start(invocation)
    result = operation.wait(3)
    assert (result.outcome, result.accepted_appends, result.output_reference, result.continuation_reference) == (
        TurnOutcome.COMPLETED,
        1,
        "pi-turn-first",
        "pi-continuation-first",
    )
    assert rig.custody.records == [
        ("materialize", "first.materialize"),
        ("admit", "first.admit"),
        ("release", "first.release"),
    ]
    call = rig.factory.calls[0]
    assert (call["config"].provider, call["config"].model, call["api_key"], call["prior"]) == (
        "provider",
        "model",
        KEY.decode(),
        None,
    )
    assert set(pi._SCHEMAS) == {method.value for method in ToolMethod} and all(
        schema.get("additionalProperties") is False for schema in pi._SCHEMAS.values()
    )
    assert (
        not tuple(rig.adapter._config.runtime_root.iterdir())
        and operation.close().disposition is RuntimeCleanupDisposition.CLEAN
    )


FRAMED_TOOL_SDK = r"""
import fs from "node:fs";
import path from "node:path";
export class ModelRuntime {
  static async create() { return new ModelRuntime(); }
  async setRuntimeApiKey(provider, key) { if (provider !== "provider" || key !== "pi-key-canary-never-render") throw new Error(); }
  getModel(provider, id) { return {provider, id}; }
}
export class SettingsManager { static inMemory(value) { return value; } }
export class DefaultResourceLoader { constructor(options) { this.options=options; } async reload() {} getExtensions(){return {extensions:[],errors:[]};} }
class Manager {
  constructor(cwd, directory, id, file=null) { this.cwd=cwd; this.directory=directory; this.id=id; this.file=file || path.join(directory,"native.jsonl"); }
  getSessionFile() { return this.file; }
}
export class SessionManager {
  static create(cwd, directory, options) { return new Manager(cwd,directory,options.id); }
  static open(file, directory, cwd) { const header=JSON.parse(fs.readFileSync(file,"utf8").split("\n")[0]); return new Manager(cwd,directory,header.id,file); }
  static inMemory(cwd, options) { return new Manager(cwd,cwd,options.id); }
}
export const defineTool = tool => tool;
export async function createAgentSession(options) {
  const state={messages:[]}; const listeners=[];
  const session={
    state,
    subscribe(listener) { listeners.push(listener); return ()=>{}; },
    async prompt() {
      const tool=options.customTools.find(value=>value.name==="workspace_read");
      const resumed=fs.existsSync(options.sessionManager.getSessionFile());
      const callId=resumed?"provider-tool-call-resumed":"provider-tool-call";
      const result=await tool.execute(callId,{path:"marker.txt"},undefined);
      const projected=JSON.parse(result.content[0].text);
      if(Object.keys(projected).sort().join()!=="data,error,ok,version"||projected.version!==1||projected.ok!==true||projected.error!==null||!projected.data?.content?.includes("marker")) throw new Error();
      state.messages=[{role:"assistant",stopReason:"stop",content:[{type:"text",text:"protocol-answer"}]}];
      const header={type:"session",version:3,id:options.sessionManager.id};
      const file=options.sessionManager.getSessionFile();
      if(!fs.existsSync(file))fs.writeFileSync(file,JSON.stringify(header)+"\n",{mode:0o600,flag:"wx"});
      fs.appendFileSync(file,JSON.stringify({type:"message",role:"tool",toolCallId:callId,result:projected})+"\n");
      for(const listener of listeners) listener({type:"agent_end"});
    },
    async waitForIdle() {}, async abort() {}, dispose() {},
  };
  return {session};
}
"""


def framed_tool_client(
    node: str,
    sdk: Path,
    private_root: Path,
    rig: Rig,
    invocation: pi.PiRuntimeInvocation,
    prior: pi.PiContinuationPayloadV1 | None = None,
) -> pi._SubprocessClient:
    private_root.mkdir(mode=0o700)
    private_root.chmod(0o700)
    return pi._SubprocessClient(
        node=node,
        sdk_entrypoint=str(sdk),
        helper=Path(pi.__file__).with_name("pi_helper.mjs"),
        private_root=private_root,
        config=rig.adapter._config,
        invocation=invocation,
        prior=prior,
        api_key=KEY.decode(),
        native_auth=None,
        extension=None,
    )


@pytest.mark.parametrize("territory_profile", ["local", "gondolin", "e2b"])
def test_private_node_helper_routes_the_provider_tool_identity_through_hands(
    tmp_path: Path, territory_profile: str
) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for the private helper protocol test")
    rig = Rig(tmp_path, territory_profile=territory_profile)
    invocation, _ = rig.invocation("helper-protocol")
    private_root = rig.adapter._config.runtime_root / "protocol-operation"
    sdk = tmp_path / "fake-pi-sdk.mjs"
    sdk.write_text(FRAMED_TOOL_SDK)
    client = framed_tool_client(node, sdk, private_root, rig, invocation)

    result = client.run(
        invocation.gateway,
        invocation,
        lambda: True,
        time.monotonic() + 3,
    )

    candidate = result.candidate
    assert candidate is not None and result.native_auth is None and result.code == "turn-completed"
    assert candidate.text == "protocol-answer"
    assert candidate.session_jsonl.startswith(b'{"type":"session","version":3,"id":"' + candidate.session_id.encode())
    assert b'"toolCallId":"provider-tool-call"' in candidate.session_jsonl
    assert b'"call_id"' not in candidate.session_jsonl
    assert invocation.attachment.attachment_id.encode() not in candidate.session_jsonl
    assert b'"attachment_id"' not in candidate.session_jsonl
    assert b'"epoch"' not in candidate.session_jsonl
    evidence = invocation.gateway.evidence()
    assert len(evidence) == 1
    assert evidence[0].call_id == "provider-tool-call"
    assert evidence[0].method is ToolMethod.WORKSPACE_READ
    assert invocation.gateway.counters().adapter_entries == 1
    assert client.close()
    shutil.rmtree(private_root)


@pytest.mark.parametrize(
    ("capabilities", "resumed"),
    [
        ((ToolMethod.WORKSPACE_READ, ToolMethod.WORKSPACE_SEARCH), False),
        ((ToolMethod.WORKSPACE_READ, ToolMethod.WORKSPACE_SEARCH), True),
        ((ToolMethod.WORKSPACE_READ, ToolMethod.WORKSPACE_SEARCH, ToolMethod.WORKSPACE_WRITE), False),
        ((ToolMethod.WORKSPACE_READ, ToolMethod.WORKSPACE_SEARCH, ToolMethod.WORKSPACE_WRITE), True),
    ],
)
def test_private_node_helper_advertises_only_the_fresh_or_resumed_operations_current_grant(
    tmp_path: Path, capabilities: tuple[ToolMethod, ...], resumed: bool
) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for the private helper protocol test")
    rig = Rig(tmp_path)
    invocation, _ = rig.invocation("filtered-tools", capabilities=capabilities)
    private_root = rig.adapter._config.runtime_root / "filtered-tools-operation"
    sdk = tmp_path / "filtered-tools-sdk.mjs"
    expected = ",".join(method.value for method in capabilities)
    sdk.write_text(
        FRAMED_TOOL_SDK.replace(
            "  const state={messages:[]}; const listeners=[];",
            f"  if(options.customTools.map(value=>value.name).join()!=='{expected}') "
            "throw new Error('advertisement');\n"
            "  const state={messages:[]}; const listeners=[];",
        )
    )
    prior = (
        pi.PiContinuationPayloadV1(
            SESSION,
            pi._working_binding(rig.adapter._config.working_directory),
            session(),
        )
        if resumed
        else None
    )
    client = framed_tool_client(node, sdk, private_root, rig, invocation, prior)

    assert tuple(client._start["schemas"]) == tuple(method.value for method in capabilities)
    result = client.run(invocation.gateway, invocation, lambda: True, time.monotonic() + 3)

    assert result.candidate is not None
    assert not resumed or result.candidate.session_id == SESSION
    assert invocation.gateway.evidence()[0].method is ToolMethod.WORKSPACE_READ
    assert client.close()
    shutil.rmtree(private_root)


def test_private_client_keeps_gateway_authoritative_for_a_forged_known_tool(tmp_path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for the private helper protocol test")
    rig = Rig(tmp_path)
    invocation, _ = rig.invocation(
        "forged-known-tool",
        capabilities=(ToolMethod.WORKSPACE_READ,),
        max_calls=1,
    )
    private_root = rig.adapter._config.runtime_root / "forged-known-tool-operation"
    private_root.mkdir(mode=0o700)
    helper = tmp_path / "forged-known-tool-helper.mjs"
    helper.write_text(
        """
import readline from "node:readline";
const reader=readline.createInterface({input:process.stdin,crlfDelay:Infinity});
const send=value=>process.stdout.write(JSON.stringify(value)+"\\n");
let start;
reader.on("line",line=>{
  const frame=JSON.parse(line);
  if(!start){
    start=frame;send({type:"ready"});
    send({type:"tool_call",id:"forged",method:"workspace_test",params:{}});return;
  }
  if(frame.type!=="tool_result")throw new Error("protocol");
  if(frame.id==="forged"){
    if(frame.result.ok||frame.result.error?.category!=="capability")throw new Error("authority");
    send({type:"tool_call",id:"allowed",method:"workspace_read",params:{path:"marker.txt"}});return;
  }
  if(frame.id!=="allowed"||!frame.result.ok||!frame.result.data?.content?.includes("marker"))
    throw new Error("read");
  const body=Buffer.from(JSON.stringify({type:"session",version:3,id:start.session_id})+"\\n").toString("base64");
  const complete={type:"complete",session_id:start.session_id,text:"answer",session:body};
  process.stdout.write(JSON.stringify(complete)+"\\n",()=>process.exit(0));reader.close();
});
"""
    )
    client = pi._SubprocessClient(
        node=node,
        sdk_entrypoint="/ignored",
        helper=helper,
        private_root=private_root,
        config=rig.adapter._config,
        invocation=invocation,
        prior=None,
        api_key=KEY.decode(),
        native_auth=None,
        extension=None,
    )

    result = client.run(invocation.gateway, invocation, lambda: True, time.monotonic() + 3)

    assert result.candidate is not None and result.candidate.text == "answer"
    evidence = invocation.gateway.evidence()
    assert [(item.method, item.ok, item.category) for item in evidence] == [
        (ToolMethod.WORKSPACE_TEST, False, RejectionCategory.CAPABILITY),
        (ToolMethod.WORKSPACE_READ, True, None),
    ]
    assert invocation.gateway.counters().adapter_entries == 1
    assert client.close()
    shutil.rmtree(private_root)


def test_private_client_keeps_unknown_tools_outside_the_closed_protocol(tmp_path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for the private helper protocol test")
    rig = Rig(tmp_path)
    invocation, _ = rig.invocation("forged-unknown-tool", capabilities=(ToolMethod.WORKSPACE_READ,))
    private_root = rig.adapter._config.runtime_root / "forged-unknown-tool-operation"
    private_root.mkdir(mode=0o700)
    helper = tmp_path / "forged-unknown-tool-helper.mjs"
    helper.write_text(
        """
import readline from "node:readline";
const reader=readline.createInterface({input:process.stdin,crlfDelay:Infinity});
const send=value=>process.stdout.write(JSON.stringify(value)+"\\n");
reader.once("line",()=>{
  send({type:"ready"});
  send({type:"tool_call",id:"unknown",method:"future_tool",params:{}});
});
"""
    )
    client = pi._SubprocessClient(
        node=node,
        sdk_entrypoint="/ignored",
        helper=helper,
        private_root=private_root,
        config=rig.adapter._config,
        invocation=invocation,
        prior=None,
        api_key=KEY.decode(),
        native_auth=None,
        extension=None,
    )

    with pytest.raises(RuntimeProtocolError, match="malformed-tool-call"):
        client.run(invocation.gateway, invocation, lambda: True, time.monotonic() + 3)
    assert not invocation.gateway.evidence()
    assert client.close()
    shutil.rmtree(private_root)


@pytest.mark.parametrize("schemas", [{}, {"future_tool": {}}])
def test_private_node_helper_rejects_empty_or_unknown_advertised_tool_sets(
    tmp_path: Path, schemas: dict[str, object]
) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for the private helper protocol test")
    rig = Rig(tmp_path)
    invocation, _ = rig.invocation("invalid-tools")
    private_root = rig.adapter._config.runtime_root / "invalid-tools-operation"
    sdk = tmp_path / "invalid-tools-sdk.mjs"
    sdk.write_text(FRAMED_TOOL_SDK)
    client = framed_tool_client(node, sdk, private_root, rig, invocation)
    client._start["schemas"] = schemas

    with pytest.raises(RuntimeProtocolError, match="protocol-failed"):
        client.run(invocation.gateway, invocation, lambda: True, time.monotonic() + 3)
    assert not invocation.gateway.evidence()
    assert client.close()
    shutil.rmtree(private_root)


def test_private_node_helper_rejects_custody_bearing_model_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for the private helper protocol test")
    rig = Rig(tmp_path)
    invocation, attachment = rig.invocation("full-result")
    private_root = rig.adapter._config.runtime_root / "full-result-operation"
    sdk = tmp_path / "fake-pi-sdk.mjs"
    sdk.write_text(FRAMED_TOOL_SDK)
    client = framed_tool_client(node, sdk, private_root, rig, invocation)
    monkeypatch.setattr(ToolResult, "to_model_data", lambda result: result.to_data())

    with pytest.raises(RuntimeProtocolError, match="protocol-failed"):
        client.run(invocation.gateway, invocation, lambda: True, time.monotonic() + 3)
    assert invocation.gateway.counters().adapter_entries == 1
    assert client.close()
    shutil.rmtree(private_root)
    assert attachment.settle().settlement.verified


def test_framed_native_a4_resume_excludes_episode_custody_from_exact_jsonl_prefix(tmp_path: Path) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for the private helper protocol test")
    sdk = tmp_path / "fake-pi-sdk.mjs"
    sdk.write_text(FRAMED_TOOL_SDK)
    helper = Path(pi.__file__).with_name("pi_helper.mjs")

    gondolin = Rig(tmp_path / "gondolin", territory_profile="gondolin")
    gondolin.adapter._node = node
    gondolin.adapter._sdk_entrypoint = str(sdk)
    gondolin.adapter._factory = pi._SubprocessFactory(helper)
    first_invocation, first_attachment = gondolin.invocation("g1")
    first_operation = gondolin.adapter.start(first_invocation)
    first_result = first_operation.wait(3)
    assert first_result.continuation_reference is not None
    assert first_operation.close().disposition is RuntimeCleanupDisposition.CLEAN
    first = gondolin.continuations.values[first_result.continuation_reference]
    assert not tuple(gondolin.adapter._config.runtime_root.iterdir())
    assert first_attachment.settle().settlement.verified

    e2b = Rig(tmp_path / "e2b", territory_profile="e2b", predecessor=gondolin)
    e2b.adapter._node = node
    e2b.adapter._sdk_entrypoint = str(sdk)
    e2b.adapter._factory = pi._SubprocessFactory(helper)
    second_invocation, second_attachment = e2b.invocation(
        "g2", continuation=claimed(first_result.continuation_reference)
    )
    second_operation = e2b.adapter.start(second_invocation)
    second_result = second_operation.wait(3)
    assert second_result.continuation_reference is not None
    assert second_operation.close().disposition is RuntimeCleanupDisposition.CLEAN
    second = e2b.continuations.values[second_result.continuation_reference]
    assert not tuple(e2b.adapter._config.runtime_root.iterdir())

    assert second.session_id == first.session_id
    assert second.session_jsonl.startswith(first.session_jsonl)
    assert len(second.session_jsonl) > len(first.session_jsonl)
    assert second.session_jsonl.index(b'"toolCallId":"provider-tool-call"') < second.session_jsonl.index(
        b'"toolCallId":"provider-tool-call-resumed"'
    )
    for custody in (
        b'"call_id"',
        b'"attachment_id"',
        first_invocation.attachment.attachment_id.encode(),
        second_invocation.attachment.attachment_id.encode(),
        b'"epoch"',
    ):
        assert custody not in second.session_jsonl
    assert first_invocation.gateway.evidence()[0].call_id == "provider-tool-call"
    assert second_invocation.gateway.evidence()[0].call_id == "provider-tool-call-resumed"
    assert first_invocation.gateway.attachment_id == first_invocation.attachment.attachment_id
    assert second_invocation.gateway.attachment_id == second_invocation.attachment.attachment_id
    assert second_attachment.settle().settlement.verified


@pytest.mark.parametrize(
    ("profile", "provider", "model", "authority", "refreshed"),
    [
        ("subscription", "anthropic", "claude-sonnet-4-5", AUTH, REFRESHED_AUTH),
        ("subscription", "openai-codex", "gpt-5.6-sol", OPENAI_AUTH, REFRESHED_OPENAI_AUTH),
        ("cc-patch-subscription", "anthropic", "claude-sonnet-4-5", AUTH, REFRESHED_AUTH),
    ],
)
@pytest.mark.parametrize("provider_failure", [False, True])
@pytest.mark.parametrize("returned_mode", [0o600, 0o640])
def test_private_node_helper_imports_and_exports_native_subscription_auth(
    tmp_path: Path,
    provider_failure: bool,
    returned_mode: int,
    profile: str,
    provider: str,
    model: str,
    authority: bytes,
    refreshed: bytes,
) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for the private helper protocol test")
    rig = Rig(tmp_path, profile=profile, provider=provider)
    invocation, _ = rig.invocation("subscription-helper")
    private_root = rig.adapter._config.runtime_root / "subscription-operation"
    private_root.mkdir(mode=0o700)
    private_root.chmod(0o700)
    sdk = tmp_path / "fake-pi-subscription-sdk.mjs"
    source = r"""
import fs from "node:fs";
import path from "node:path";
const EXPECTED_AUTH="__EXPECTED_AUTH__", REFRESHED_AUTH="__REFRESHED_AUTH__", PROVIDER="__PROVIDER__", MODEL="__MODEL__", FAIL=__FAIL__;
export class ModelRuntime {
  constructor(authPath) { this.authPath=authPath; }
  static async create(options) {
    const metadata=fs.statSync(options.authPath);
    if(options.modelsPath!==null||options.allowModelNetwork!==false||(metadata.mode&0o777)!==0o600||fs.readFileSync(options.authPath).toString("base64")!==EXPECTED_AUTH)throw new Error("auth");
    return new ModelRuntime(options.authPath);
  }
  async setRuntimeApiKey() { throw new Error("api-key-forbidden"); }
  async listCredentials() { return [{providerId:PROVIDER,type:"oauth"}]; }
  isUsingOAuth(provider) { return provider===PROVIDER; }
  getModel(provider,id) { return provider===PROVIDER&&id===MODEL?{provider,id}:undefined; }
}
export class SettingsManager { static inMemory(value) { return value; } }
export class DefaultResourceLoader { constructor(options) { this.options=options; } async reload() {} getExtensions(){return {extensions:(this.options.additionalExtensionPaths||[]).map(resolvedPath=>({resolvedPath})),errors:[]};} }
class Manager {
  constructor(cwd,directory,id,file=null){this.cwd=cwd;this.directory=directory;this.id=id;this.file=file||path.join(directory,"native.jsonl");}
  getSessionFile(){return this.file;}
}
export class SessionManager {
  static create(cwd,directory,options){return new Manager(cwd,directory,options.id);}
  static open(file,directory,cwd){const header=JSON.parse(fs.readFileSync(file,"utf8").split("\n")[0]);return new Manager(cwd,directory,header.id,file);}
  static inMemory(cwd,options){return new Manager(cwd,cwd,options.id);}
}
export const defineTool=tool=>tool;
export async function createAgentSession(options){
  const state={messages:[]};
  const session={
    state,subscribe(){return ()=>{};},
    async prompt(){
      const tool=options.customTools.find(value=>value.name==="workspace_read");
      const result=await tool.execute("subscription-tool-call",{path:"marker.txt"},undefined);
      if(!result.content[0].text.includes("marker"))throw new Error("provider");
      fs.rmSync(options.modelRuntime.authPath);
      fs.writeFileSync(options.modelRuntime.authPath,Buffer.from(REFRESHED_AUTH,"base64"),{mode:__MODE__,flag:"wx"});
      fs.chmodSync(options.modelRuntime.authPath,__MODE__);
      if(FAIL)throw new Error("provider");
      state.messages=[{role:"assistant",stopReason:"stop",content:[{type:"text",text:"subscription-answer"}]}];
      const header={type:"session",version:3,id:options.sessionManager.id};
      fs.writeFileSync(options.sessionManager.getSessionFile(),JSON.stringify(header)+"\n",{mode:0o600});
    },
    async waitForIdle(){},async abort(){},dispose(){},
  };
  return {session};
}
"""
    sdk.write_text(
        source.replace("__EXPECTED_AUTH__", base64.b64encode(authority).decode())
        .replace("__REFRESHED_AUTH__", base64.b64encode(refreshed).decode())
        .replace("__PROVIDER__", provider)
        .replace("__MODEL__", model)
        .replace("__FAIL__", "true" if provider_failure else "false")
        .replace("__MODE__", str(returned_mode))
    )
    extension = None
    if profile == "cc-patch-subscription":
        extension_path = tmp_path / "fake-cc-patch.ts"
        extension_path.write_text("export default function() {}")
        extension = str(extension_path.resolve())
    client = pi._SubprocessClient(
        node=node,
        sdk_entrypoint=str(sdk),
        helper=Path(pi.__file__).with_name("pi_helper.mjs"),
        private_root=private_root,
        config=rig.adapter._config,
        invocation=invocation,
        prior=None,
        api_key=None,
        native_auth=authority,
        extension=extension,
    )

    if returned_mode != 0o600:
        with pytest.raises(RuntimeProtocolError, match="protocol-failed"):
            client.run(invocation.gateway, invocation, lambda: True, time.monotonic() + 3)
        assert client.close()
        shutil.rmtree(private_root)
        return

    result = client.run(invocation.gateway, invocation, lambda: True, time.monotonic() + 3)

    assert result.native_auth == refreshed
    assert result.code == ("provider-failed" if provider_failure else "turn-completed")
    assert (result.candidate is None) is provider_failure
    if result.candidate is not None:
        assert result.candidate.text == "subscription-answer"
    assert invocation.gateway.evidence()[-1].call_id == "subscription-tool-call"
    assert client.close()
    shutil.rmtree(private_root)


@pytest.mark.parametrize(
    ("profile", "terminal"),
    [
        (
            "subscription",
            'send({type:"complete",session_id:start.session_id,text:"answer",session:body});process.exit(0);',
        ),
        (
            "subscription",
            'send({type:"failed",code:"aborted",auth:start.auth});process.exit(1);',
        ),
        (
            "api-key",
            'send({type:"complete",session_id:start.session_id,text:"answer",session:body,auth:"e30="});process.exit(0);',
        ),
    ],
)
def test_private_client_rejects_auth_on_the_wrong_terminal_frame(tmp_path: Path, profile: str, terminal: str) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for the private helper protocol test")
    rig = Rig(tmp_path, profile=profile)
    invocation, _ = rig.invocation("wrong-auth-frame")
    private_root = rig.adapter._config.runtime_root / "wrong-auth-operation"
    private_root.mkdir(mode=0o700)
    helper = tmp_path / "wrong-auth-helper.mjs"
    helper.write_text(
        """
import readline from "node:readline";
const reader=readline.createInterface({input:process.stdin,crlfDelay:Infinity});
const send=value=>process.stdout.write(JSON.stringify(value)+"\\n");
reader.once("line",line=>{
  const start=JSON.parse(line);
  const body=Buffer.from(JSON.stringify({type:"session",version:3,id:start.session_id})+"\\n").toString("base64");
  send({type:"ready"});
  __TERMINAL__
});
""".replace("__TERMINAL__", terminal)
    )
    client = pi._SubprocessClient(
        node=node,
        sdk_entrypoint="/ignored",
        helper=helper,
        private_root=private_root,
        config=rig.adapter._config,
        invocation=invocation,
        prior=None,
        api_key=KEY.decode() if profile == "api-key" else None,
        native_auth=AUTH if profile == "subscription" else None,
        extension=None,
    )

    with pytest.raises(RuntimeProtocolError, match="frame-order|malformed-failed"):
        client.run(invocation.gateway, invocation, lambda: True, time.monotonic() + 3)
    assert client.close()
    shutil.rmtree(private_root)


def test_native_resume_preserves_identity_and_extends_opaque_jsonl(tmp_path: Path) -> None:
    rig = Rig(tmp_path, Plan(text="one"), Plan(text="two"))
    first_inv, _ = rig.invocation("g1")
    first = rig.adapter.start(first_inv).wait(3)
    assert first.continuation_reference is not None
    old = rig.continuations.values[first.continuation_reference]
    second_inv, _ = rig.invocation("g2", continuation=claimed(first.continuation_reference))
    second = rig.adapter.start(second_inv).wait(3)
    assert second.continuation_reference is not None
    new = rig.continuations.values[second.continuation_reference]
    assert (
        rig.factory.calls[1]["prior"] is old
        and new.session_id == old.session_id
        and new.session_jsonl.startswith(old.session_jsonl)
    )


def test_native_a4_resumes_only_continuation_after_settled_gondolin_replacement(tmp_path: Path) -> None:
    gondolin = Rig(tmp_path / "gondolin", Plan(text="one"), territory_profile="gondolin")
    first_invocation, first_attachment = gondolin.invocation("g1")
    first_operation = gondolin.adapter.start(first_invocation)
    first = first_operation.wait(3)
    assert first_operation.close().disposition is RuntimeCleanupDisposition.CLEAN
    first_payload = gondolin.continuations.values[first.continuation_reference or ""]
    assert first_attachment.settle().settlement.verified

    e2b = Rig(tmp_path / "e2b", Plan(text="two"), territory_profile="e2b", predecessor=gondolin)
    second_invocation, second_attachment = e2b.invocation(
        "g2", continuation=claimed(first.continuation_reference or "")
    )
    second_operation = e2b.adapter.start(second_invocation)
    second = second_operation.wait(3)
    assert second_operation.close().disposition is RuntimeCleanupDisposition.CLEAN
    second_payload = e2b.continuations.values[second.continuation_reference or ""]

    assert e2b.factory.calls[0]["prior"] is first_payload
    assert second_payload.session_id == first_payload.session_id
    assert second_payload.session_jsonl.startswith(first_payload.session_jsonl)
    assert b"attachment-g1" not in first_payload.session_jsonl
    assert b"attachment-g1" not in second_payload.session_jsonl
    assert b"attachment-g2" not in second_payload.session_jsonl
    assert second_attachment.settle().settlement.verified


def test_native_a4_rejects_cross_territory_resume_with_a_different_project_binding(tmp_path: Path) -> None:
    gondolin = Rig(tmp_path / "gondolin", territory_profile="gondolin")
    first_invocation, first_attachment = gondolin.invocation("g1")
    first_operation = gondolin.adapter.start(first_invocation)
    first = first_operation.wait(3)
    assert first_operation.close().disposition is RuntimeCleanupDisposition.CLEAN
    assert first_attachment.settle().settlement.verified

    e2b = Rig(tmp_path / "e2b", territory_profile="e2b")
    e2b.continuations.values.update(gondolin.continuations.values)
    second_invocation, second_attachment = e2b.invocation(
        "g2", continuation=claimed(first.continuation_reference or "")
    )

    with pytest.raises(RuntimeProtocolError, match="continuation-project-mismatch"):
        e2b.adapter.start(second_invocation)
    assert not e2b.custody.records and not e2b.factory.calls
    assert second_attachment.settle().settlement.verified


def test_native_a4_rejects_cross_profile_resolution_and_lease_before_authority(tmp_path: Path) -> None:
    rig = Rig(tmp_path, territory_profile="gondolin")
    foreign, foreign_attachment = rig.invocation(
        "foreign",
        selected=snapshot(connection=rig.connection, territory_profile="e2b"),
    )
    with pytest.raises(RuntimeProtocolError, match="resolution-mismatch"):
        rig.adapter.start(foreign)
    assert not rig.custody.records and not rig.factory.calls
    assert foreign_attachment.settle().settlement.verified

    stale, stale_attachment = rig.invocation("stale")
    binding = cast(MotusAttachmentBinding, stale_attachment.binding)
    object.__setattr__(binding.execution.lease, "provider", "e2b")
    try:
        with pytest.raises(RuntimeProtocolError, match="runtime-territory-lease-required"):
            rig.adapter.start(stale)
        assert not rig.custody.records and not rig.factory.calls
    finally:
        object.__setattr__(binding.execution.lease, "provider", "gondolin")
    assert stale_attachment.settle().settlement.verified


def test_native_a4_post_run_lease_drift_releases_authority_without_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = Rig(tmp_path, territory_profile="gondolin")
    invocation, attachment = rig.invocation("post-run-stale")
    binding = cast(MotusAttachmentBinding, attachment.binding)
    run = Client.run

    def complete_then_replace(self, gateway, current_invocation, current, deadline):
        result = run(self, gateway, current_invocation, current, deadline)
        object.__setattr__(binding.execution.lease, "provider", "e2b")
        return result

    monkeypatch.setattr(Client, "run", complete_then_replace)
    operation = rig.adapter.start(invocation)
    result = operation.wait(3)

    assert result.outcome is TurnOutcome.FAILED
    assert result.termination_code == "runtime-territory-lease-required"
    assert result.accepted_appends == 0
    assert result.output_reference is result.continuation_reference is None
    assert [name for name, _ in rig.custody.records] == ["materialize", "release"]
    assert operation.close().disposition is RuntimeCleanupDisposition.CLEAN
    object.__setattr__(binding.execution.lease, "provider", "gondolin")
    assert attachment.settle().settlement.verified


@pytest.mark.parametrize("territory_profile", ["gondolin", "e2b"])
def test_native_a4_cancellation_wins_while_remote_publication_lookup_is_stalled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, territory_profile: str
) -> None:
    rig = Rig(tmp_path, territory_profile=territory_profile)
    invocation, attachment = rig.invocation("stalled-publication")
    lookup_started, release_lookup = threading.Event(), threading.Event()
    binding_current = rig.adapter._binding_current
    calls = 0

    def stall_after_initial_validation(current: pi.PiRuntimeInvocation) -> bool:
        nonlocal calls
        calls += 1
        if calls > 1:
            lookup_started.set()
            assert release_lookup.wait(2)
        return binding_current(current)

    monkeypatch.setattr(rig.adapter, "_binding_current", stall_after_initial_validation)
    operation = rig.adapter.start(invocation)
    assert lookup_started.wait(2)

    try:
        wait_started = time.monotonic()
        with pytest.raises(TimeoutError, match="has not settled"):
            operation.wait(0.05)
        assert time.monotonic() - wait_started < 0.2
        started = time.monotonic()
        assert operation.cancel("stop") is CancellationDisposition.REQUESTED
        assert time.monotonic() - started < 0.2
    finally:
        release_lookup.set()

    result = operation.wait(3)
    assert result.outcome is TurnOutcome.CANCELLED
    assert result.output_reference is result.continuation_reference is None
    assert not rig.turns.values and not rig.continuations.values
    assert [name for name, _ in rig.custody.records] == ["materialize", "release"]
    assert operation.close().disposition is RuntimeCleanupDisposition.CLEAN
    assert attachment.settle().settlement.verified


@pytest.mark.parametrize("territory_profile", ["gondolin", "e2b"])
@pytest.mark.parametrize("lapse", ["grant", "deadline"])
def test_native_a4_rechecks_publication_admission_after_remote_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, territory_profile: str, lapse: str
) -> None:
    rig = Rig(tmp_path, territory_profile=territory_profile)
    invocation, attachment = rig.invocation("stale-admission")
    now = [time.monotonic()]
    rig.adapter._clock = lambda: now[0]
    lookup_started, release_lookup = threading.Event(), threading.Event()
    binding_current = rig.adapter._binding_current
    calls = 0

    def stall_after_initial_validation(current: pi.PiRuntimeInvocation) -> bool:
        nonlocal calls
        calls += 1
        if calls > 1:
            lookup_started.set()
            assert release_lookup.wait(2)
        return binding_current(current)

    monkeypatch.setattr(rig.adapter, "_binding_current", stall_after_initial_validation)
    operation = rig.adapter.start(invocation)
    assert lookup_started.wait(2)
    if lapse == "grant":
        attachment.grants().close()
        expected = "grant-mismatch"
    else:
        now[0] = attachment.deadline
        expected = "deadline-exceeded"
    release_lookup.set()

    result = operation.wait(3)
    assert result.outcome is TurnOutcome.FAILED
    assert result.termination_code == expected
    assert result.output_reference is result.continuation_reference is None
    assert not rig.turns.values and not rig.continuations.values
    assert [name for name, _ in rig.custody.records] == ["materialize", "release"]
    assert operation.close().disposition is RuntimeCleanupDisposition.CLEAN
    assert attachment.settle().settlement.verified


def test_native_a4_publication_claim_makes_later_cancellation_too_late(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = Rig(tmp_path, territory_profile="gondolin")
    invocation, attachment = rig.invocation("claimed-publication")
    admission_started, release_admission = threading.Event(), threading.Event()
    admit_result = rig.custody.admit_result

    def stalled_admission(fence, *, operation_id):
        admission_started.set()
        assert release_admission.wait(2)
        return admit_result(fence, operation_id=operation_id)

    monkeypatch.setattr(rig.custody, "admit_result", stalled_admission)
    operation = rig.adapter.start(invocation)
    assert admission_started.wait(2)
    assert operation.cancel("stop") is CancellationDisposition.TOO_LATE
    release_admission.set()

    result = operation.wait(3)
    assert result.outcome is TurnOutcome.COMPLETED
    assert result.output_reference is not None and result.continuation_reference is not None
    assert operation.close().disposition is RuntimeCleanupDisposition.CLEAN
    assert attachment.settle().settlement.verified


def test_resolution_stale_lease_provider_and_expired_deadline_fail_before_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = Rig(tmp_path)
    foreign = CapabilityDescriptor(DescriptorIdentity(DescriptorKind.RUNTIME, "foreign", 1), frozenset())
    inv, _ = rig.invocation("resolution", selected=snapshot(foreign))
    with pytest.raises(RuntimeProtocolError, match="resolution-mismatch"):
        rig.adapter.start(inv)
    inv, attachment = rig.invocation("lease")
    monkeypatch.setattr(attachment.binding.provider, "lookup", lambda _: None)
    with pytest.raises(RuntimeProtocolError, match="runtime-local-lease-required"):
        rig.adapter.start(inv)
    inv, _ = rig.invocation("provider")
    inv = replace(
        inv,
        connection=replace(inv.connection, identity=ConnectionIdentity("connection", "other", "account", "api-key")),
    )
    with pytest.raises(RuntimeProtocolError, match="connection-provider-mismatch"):
        rig.adapter.start(inv)
    expired, _ = rig.invocation("expired", deadline=time.monotonic() - 1)
    result = rig.adapter.start(expired).wait(3)
    assert result.termination_code == "deadline-exceeded" and rig.custody.records == [] and not rig.factory.calls


@pytest.mark.parametrize(
    ("plan", "code"), [(Plan(error="provider-failed"), "provider-failed"), (Plan(clean=False), "cleanup-unverified")]
)
def test_provider_and_cleanup_failures_publish_no_references(tmp_path: Path, plan: Plan, code: str) -> None:
    rig = Rig(tmp_path, plan)
    invocation, _ = rig.invocation("failure")
    result = rig.adapter.start(invocation).wait(3)
    assert result.outcome is TurnOutcome.FAILED and result.termination_code == code and result.accepted_appends == 0
    assert result.output_reference is None and result.continuation_reference is None


def test_output_storage_failure_and_release_uncertainty_remove_candidate_refs(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.turns.fail = True
    invocation, _ = rig.invocation("store")
    result = rig.adapter.start(invocation).wait(3)
    assert (
        result.outcome is TurnOutcome.FAILED
        and result.output_reference is None
        and result.continuation_reference is None
    )
    rig = Rig(tmp_path / "continuation")
    rig.continuations.fail = True
    invocation, _ = rig.invocation("continuation-store")
    result = rig.adapter.start(invocation).wait(3)
    assert "pi-turn-continuation-store" in rig.turns.values
    assert (
        result.outcome is TurnOutcome.FAILED
        and result.output_reference is None
        and result.continuation_reference is None
    )
    rig = Rig(tmp_path / "other")
    rig.custody.uncertain = True
    invocation, _ = rig.invocation("release")
    result = rig.adapter.start(invocation).wait(3)
    assert (
        result.termination_code == "cleanup-unverified"
        and result.output_reference is None
        and result.continuation_reference is None
    )


@pytest.mark.parametrize("profile", ["subscription", "cc-patch-subscription"])
def test_subscription_success_checkpoints_rotated_native_auth_after_verified_cleanup(
    tmp_path: Path, profile: str
) -> None:
    rig = Rig(tmp_path, profile=profile)
    invocation, _ = rig.invocation("subscription")

    result = rig.adapter.start(invocation).wait(3)

    assert (result.outcome, result.accepted_appends, result.termination_code) == (
        TurnOutcome.COMPLETED,
        1,
        "turn-completed",
    )
    assert rig.custody.records == [
        ("materialize", "subscription.materialize"),
        ("activate", "subscription.activate"),
        ("admit", "subscription.admit"),
        ("checkpoint", "subscription.checkpoint"),
    ]
    assert rig.custody.home.value == REFRESHED_AUTH and rig.custody.state_version == 5
    call = rig.factory.calls[0]
    assert call["api_key"] is None and call["native_auth"] == AUTH
    assert call["extension"] == ("/fake/pi-cc-patch/index.ts" if profile == "cc-patch-subscription" else None)
    assert not tuple(rig.adapter._config.runtime_root.iterdir())


def test_clean_subscription_provider_failure_checkpoints_auth_without_turn_publication(tmp_path: Path) -> None:
    rig = Rig(tmp_path, Plan(provider_failed=True), profile="subscription")
    invocation, _ = rig.invocation("provider-failure")

    result = rig.adapter.start(invocation).wait(3)

    assert (result.outcome, result.accepted_appends, result.termination_code) == (
        TurnOutcome.FAILED,
        0,
        "provider-failed",
    )
    assert result.output_reference is None and result.continuation_reference is None
    assert [kind for kind, _ in rig.custody.records] == ["materialize", "activate", "admit", "checkpoint"]
    assert rig.custody.home.value == REFRESHED_AUTH


def test_subscription_spawn_failure_releases_before_activation(tmp_path: Path) -> None:
    rig = Rig(tmp_path, profile="subscription")
    rig.factory.fail_create = True
    invocation, _ = rig.invocation("spawn")

    result = rig.adapter.start(invocation).wait(3)

    assert result.outcome is TurnOutcome.FAILED and result.accepted_appends == 0
    assert [kind for kind, _ in rig.custody.records] == ["materialize", "release"]


def test_helper_construction_refuses_a_grant_replaced_after_initial_validation(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    invocation, attachment = rig.invocation("replaced-grant", capabilities=(ToolMethod.WORKSPACE_READ,))

    class ReplacingFactory:
        def create(self, **arguments):
            attachment.grants().open(
                [ToolMethod.WORKSPACE_READ],
                deadline=attachment.deadline,
                max_calls=1,
            )
            return pi._SubprocessClient(
                helper=Path(pi.__file__).with_name("pi_helper.mjs"),
                **arguments,
            )

    rig.adapter._factory = ReplacingFactory()
    operation = rig.adapter.start(invocation)

    result = operation.wait(3)

    assert (result.outcome, result.accepted_appends, result.termination_code) == (
        TurnOutcome.FAILED,
        0,
        "grant-mismatch",
    )
    assert [kind for kind, _ in rig.custody.records] == ["materialize", "release"]
    assert operation.close().disposition is RuntimeCleanupDisposition.CLEAN
    assert not tuple(rig.adapter._config.runtime_root.iterdir())
    assert attachment.settle().settlement.verified


def test_cc_patch_lane_rejects_native_subscription_descriptor_before_authority(tmp_path: Path) -> None:
    rig = Rig(tmp_path, profile="cc-patch-subscription")
    invocation, _ = rig.invocation("wrong-profile")
    invocation = replace(
        invocation,
        connection=replace(
            invocation.connection,
            identity=replace(invocation.connection.identity, profile="subscription"),
        ),
    )

    with pytest.raises(RuntimeProtocolError, match="connection-profile-mismatch"):
        rig.adapter.start(invocation)
    assert not rig.custody.records and not rig.factory.calls

    native = Rig(tmp_path / "native", profile="subscription")
    invocation, _ = native.invocation("wrong-profile")
    invocation = replace(
        invocation,
        connection=replace(
            invocation.connection,
            identity=replace(invocation.connection.identity, profile="cc-patch-subscription"),
        ),
    )
    with pytest.raises(RuntimeProtocolError, match="connection-profile-mismatch"):
        native.adapter.start(invocation)
    assert not native.custody.records and not native.factory.calls


def test_cc_patch_lane_requires_qualified_extension_before_authority(tmp_path: Path) -> None:
    rig = Rig(tmp_path, profile="cc-patch-subscription")
    rig.adapter._cc_patch_entrypoint = None
    invocation, _ = rig.invocation("missing-extension")

    with pytest.raises(RuntimeProtocolError, match="cc-patch-not-ready"):
        rig.adapter.start(invocation)
    assert not rig.custody.records and not rig.factory.calls


def test_uncertain_subscription_run_releases_activated_lease_without_checkpoint(tmp_path: Path) -> None:
    rig = Rig(tmp_path, Plan(error="protocol-failed"), profile="subscription")
    invocation, _ = rig.invocation("uncertain")

    result = rig.adapter.start(invocation).wait(3)

    assert result.outcome is TurnOutcome.FAILED and result.accepted_appends == 0
    assert result.output_reference is None and result.continuation_reference is None
    assert [kind for kind, _ in rig.custody.records] == ["materialize", "activate", "release"]


def test_subscription_stale_attachment_after_run_prevents_checkpoint_and_result_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = Rig(tmp_path, profile="subscription")
    invocation, _ = rig.invocation("stale")
    monkeypatch.setattr(pi._Operation, "claim", lambda _: "grant-mismatch")

    result = rig.adapter.start(invocation).wait(3)

    assert result.termination_code == "grant-mismatch" and result.accepted_appends == 0
    assert result.output_reference is None and result.continuation_reference is None
    assert not rig.turns.values and not rig.continuations.values
    assert [kind for kind, _ in rig.custody.records] == ["materialize", "activate", "release"]


@pytest.mark.parametrize("provider_failed", [False, True])
def test_subscription_auth_export_with_uncertain_helper_cleanup_is_not_checkpointed(
    tmp_path: Path, provider_failed: bool
) -> None:
    rig = Rig(tmp_path, Plan(clean=False, provider_failed=provider_failed), profile="subscription")
    invocation, _ = rig.invocation("cleanup")

    result = rig.adapter.start(invocation).wait(3)

    assert result.termination_code == "cleanup-unverified" and result.accepted_appends == 0
    assert result.output_reference is None and result.continuation_reference is None
    assert [kind for kind, _ in rig.custody.records] == ["materialize", "activate", "release"]
    assert not tuple(rig.adapter._config.runtime_root.iterdir())


def test_subscription_missing_returned_auth_requires_reauthorization(tmp_path: Path) -> None:
    rig = Rig(tmp_path, Plan(omit_auth=True), profile="subscription")
    invocation, _ = rig.invocation("missing-auth")

    result = rig.adapter.start(invocation).wait(3)

    assert result.termination_code == "credential-invalid" and result.accepted_appends == 0
    assert [kind for kind, _ in rig.custody.records] == ["materialize", "activate", "release"]
    assert not rig.turns.values and not rig.continuations.values


@pytest.mark.parametrize(
    ("provider", "authority"),
    [
        ("anthropic", b"not-json"),
        ("anthropic", b'{"other":{"type":"oauth","access":"a","refresh":"r","expires":1}}'),
        (
            "anthropic",
            b'{"anthropic":{"type":"oauth","access":"a","refresh":"r","expires":1},"other":{}}',
        ),
        (
            "anthropic",
            b'{"anthropic":{"type":"oauth","access":"a","access":"b","refresh":"r","expires":1}}',
        ),
        (
            "openai-codex",
            b'{"openai-codex":{"type":"oauth","access":"a","refresh":"r","expires":1}}',
        ),
    ],
)
def test_invalid_subscription_authority_is_rejected_before_activation(
    tmp_path: Path, provider: str, authority: bytes
) -> None:
    rig = Rig(tmp_path, profile="subscription", provider=provider)
    rig.custody.home.value = authority
    invocation, _ = rig.invocation("invalid-input")

    result = rig.adapter.start(invocation).wait(3)

    assert result.termination_code == "credential-invalid" and result.accepted_appends == 0
    assert [kind for kind, _ in rig.custody.records] == ["materialize", "release"]
    assert not rig.factory.calls and not tuple(rig.adapter._config.runtime_root.iterdir())


@pytest.mark.parametrize(
    ("provider", "returned"),
    [
        ("anthropic", b"not-json"),
        ("anthropic", b'{"other":{"type":"oauth","access":"a","refresh":"r","expires":1}}'),
        (
            "anthropic",
            b'{"anthropic":{"type":"oauth","access":"a","refresh":"r","expires":1},"other":{}}',
        ),
        (
            "openai-codex",
            b'{"openai-codex":{"type":"oauth","access":"a","refresh":"r","expires":1}}',
        ),
    ],
)
def test_invalid_returned_subscription_authority_requires_reauthorization(
    tmp_path: Path, provider: str, returned: bytes
) -> None:
    rig = Rig(tmp_path, Plan(refreshed_auth=returned), profile="subscription", provider=provider)
    invocation, _ = rig.invocation("invalid-output")

    result = rig.adapter.start(invocation).wait(3)

    assert result.termination_code == "credential-invalid" and result.accepted_appends == 0
    assert result.output_reference is None and result.continuation_reference is None
    assert [kind for kind, _ in rig.custody.records] == ["materialize", "activate", "release"]
    assert not tuple(rig.adapter._config.runtime_root.iterdir())


def test_subscription_reserves_publication_time_before_materializing_authority(tmp_path: Path) -> None:
    rig = Rig(tmp_path, profile="subscription")
    invocation, _ = rig.invocation("ttl")
    rig.adapter._config = replace(rig.adapter._config, credential_ttl=2)
    with pytest.raises(RuntimeProtocolError, match="subscription-ttl-insufficient"):
        rig.adapter.start(invocation)
    assert rig.custody.records == []

    rig = Rig(tmp_path / "deadline", profile="subscription")
    invocation, _ = rig.invocation("deadline", deadline=time.monotonic() + 1)
    result = rig.adapter.start(invocation).wait(3)
    assert result.termination_code == "deadline-exceeded" and rig.custody.records == []


def test_subscription_deadline_after_activation_releases_without_checkpoint(tmp_path: Path) -> None:
    rig = Rig(tmp_path, Plan(block=True), wall_timeout=0.05, profile="subscription")
    invocation, _ = rig.invocation("run-deadline")

    result = rig.adapter.start(invocation).wait(3)

    assert result.termination_code == "deadline-exceeded" and result.accepted_appends == 0
    assert [kind for kind, _ in rig.custody.records] == ["materialize", "activate", "release"]
    assert not rig.turns.values and not rig.continuations.values


def test_subscription_storage_or_checkpoint_failure_publishes_no_references(tmp_path: Path) -> None:
    rig = Rig(tmp_path, profile="subscription")
    rig.turns.fail = True
    invocation, _ = rig.invocation("turn-store")
    result = rig.adapter.start(invocation).wait(3)
    assert result.outcome is TurnOutcome.FAILED and result.output_reference is None
    assert not rig.turns.values and not rig.continuations.values
    assert [kind for kind, _ in rig.custody.records] == ["materialize", "activate", "admit", "checkpoint"]

    rig = Rig(tmp_path / "checkpoint", profile="subscription")
    rig.custody.checkpoint_fail = True
    invocation, _ = rig.invocation("checkpoint")
    result = rig.adapter.start(invocation).wait(3)
    assert result.outcome is TurnOutcome.FAILED and result.accepted_appends == 0
    assert result.output_reference is None and result.continuation_reference is None
    assert [kind for kind, _ in rig.custody.records] == [
        "materialize",
        "activate",
        "admit",
        "checkpoint",
        "release",
    ]


@pytest.mark.parametrize("malformed", [False, True])
def test_stale_or_malformed_subscription_checkpoint_publishes_no_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, malformed: bool
) -> None:
    rig = Rig(tmp_path, profile="subscription")
    invocation, _ = rig.invocation("bad-checkpoint")

    def checkpoint(materialization, *, operation_id):
        rig.custody.records.append(("checkpoint", operation_id))
        if malformed:
            return object()
        return PublicationResult(
            operation_id,
            rig.custody.view(),
            CleanupEvidence(materialization.fence.attachment_id, True, False, len(rig.custody.home.read())),
        )

    monkeypatch.setattr(rig.custody, "checkpoint", checkpoint)

    result = rig.adapter.start(invocation).wait(3)

    assert result.termination_code == "connection-publication-mismatch" and result.accepted_appends == 0
    assert result.output_reference is None and result.continuation_reference is None
    assert not rig.turns.values and not rig.continuations.values
    assert [kind for kind, _ in rig.custody.records] == [
        "materialize",
        "activate",
        "admit",
        "checkpoint",
        "release",
    ]


def test_real_refresh_custody_checkpoints_or_requires_reauthorization_after_activation(tmp_path: Path) -> None:
    storage = SqliteConnectionStorage(tmp_path / "connection.sqlite3")
    custody = AgentConnectionCustody(
        storage, Keys(), PrivateFileMaterializer(tmp_path / "materialized"), clock=time.monotonic
    )
    custody.enroll_host("host", operation_id="enroll")
    state = OpaqueState(AUTH)
    custody.authorize(
        ConnectionIdentity("pi-subscription", "anthropic", "account", "subscription"),
        state,
        operation_id="authorize",
    )
    unactivated = custody.materialize(
        "pi-subscription", "host", mode=LeaseMode.REFRESH, ttl=30, operation_id="materialize-0"
    )
    custody.release(unactivated, operation_id="release-0")
    assert custody.connection("pi-subscription").status is ConnectionStatus.READY
    first = custody.materialize("pi-subscription", "host", mode=LeaseMode.REFRESH, ttl=30, operation_id="materialize-1")
    custody.activate(first, operation_id="activate-1")
    first.home.replace(REFRESHED_AUTH)
    checkpoint = custody.checkpoint(first, operation_id="checkpoint-1")
    assert checkpoint.connection.status is ConnectionStatus.READY and checkpoint.connection.state_version == 2
    second = custody.materialize(
        "pi-subscription", "host", mode=LeaseMode.REFRESH, ttl=30, operation_id="materialize-2"
    )
    custody.activate(second, operation_id="activate-2")
    custody.release(second, operation_id="release-2")
    current = custody.connection("pi-subscription")
    assert current.status is ConnectionStatus.REAUTHORIZATION_REQUIRED and current.state_digest is None
    storage.close()


@pytest.mark.parametrize("profile", ["api-key", "subscription"])
def test_cancel_deadline_redelivery_conflict_and_too_late_claim(tmp_path: Path, profile: str) -> None:
    rig = Rig(tmp_path, Plan(block=True), profile=profile)
    invocation, _ = rig.invocation("cancel")
    operation = rig.adapter.start(invocation)
    deadline = time.monotonic() + 2
    while not rig.factory.clients and time.monotonic() < deadline:
        time.sleep(0.005)
    assert rig.factory.clients
    assert rig.factory.clients[0].entered.wait(2)
    assert rig.adapter.start(invocation) is operation
    with pytest.raises(RuntimeProtocolError, match="operation-conflict"):
        rig.adapter.start(replace(invocation, prompt="changed"))
    assert operation.cancel("stop") is CancellationDisposition.REQUESTED
    assert operation.wait(3).outcome is TurnOutcome.CANCELLED
    if profile == "subscription":
        assert [kind for kind, _ in rig.custody.records] == ["materialize", "activate", "release"]


def test_thread_start_failure_rolls_back_registration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rig = Rig(tmp_path)
    invocation, _ = rig.invocation("thread")
    monkeypatch.setattr(threading.Thread, "start", lambda self: (_ for _ in ()).throw(RuntimeError("start")))
    with pytest.raises(RuntimeError, match="start"):
        rig.adapter.start(invocation)
    assert "thread" not in rig.adapter._operations


def test_canaries_never_render_log_or_error(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    rig = Rig(tmp_path, profile="subscription", provider="openai-codex")
    invocation, _ = rig.invocation("canary")
    operation = rig.adapter.start(invocation)
    result = operation.wait(3)
    rendered = repr(rig.adapter) + repr(invocation) + repr(operation) + repr(result) + caplog.text
    for secret in (
        KEY.decode(),
        PROMPT,
        SESSION_CANARY,
        SESSION,
        "pi-openai-access-canary",
        "pi-openai-refresh-canary",
        "pi-openai-account-canary",
    ):
        assert secret not in rendered


def test_import_has_no_node_or_npm_dependency() -> None:
    source = "import subprocess; subprocess.run=lambda *a,**k: (_ for _ in ()).throw(RuntimeError('called')); import petrus.agenticus.runtime.pi"
    result = subprocess.run((sys.executable, "-c", source), capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr


def test_adapter_evicts_only_closed_operation_receipts(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    invocation, _ = rig.invocation("evict")
    operation = rig.adapter.start(invocation)
    with pytest.raises(RuntimeProtocolError, match="operation-active"):
        rig.adapter.evict(invocation.operation_id)
    operation.wait(3)
    assert rig.adapter.receipt(invocation.operation_id) is not None
    operation.close()
    assert rig.adapter.evict(invocation.operation_id) is True
    assert rig.adapter.evict(invocation.operation_id) is False


def test_recovered_runtime_persists_before_dispatch_and_wait_publication(tmp_path: Path) -> None:
    rig = Rig(tmp_path / "rig")
    invocation, _ = rig.invocation("durable")
    ledger = SqlitePiOperationLedger(tmp_path / "ledger" / "operations.sqlite3")
    runtime = PiRecoveredRuntime(rig.adapter, ledger)
    original_start = rig.adapter.start

    def observed_start(value):
        record = ledger.lookup(value.operation_id)
        assert record is not None and record.phase is PiOperationPhase.EXECUTING
        return original_start(value)

    rig.adapter.start = observed_start  # type: ignore[method-assign]
    first = runtime.start(invocation)
    assert runtime.start(invocation) is first
    result = first.wait(3)
    assert len(rig.factory.calls) == 1
    assert ledger.lookup(invocation.operation_id).settlement() == result  # type: ignore[union-attr]
    cleanup = first.close()
    assert ledger.lookup(invocation.operation_id).cleanup is cleanup.disposition  # type: ignore[union-attr]
    ledger.close()


def test_restart_classifies_execution_and_replays_without_adapter_access(tmp_path: Path) -> None:
    path = tmp_path / "ledger" / "operations.sqlite3"
    rig = Rig(tmp_path / "first")
    invocation, _ = rig.invocation("ambiguous")
    ledger = SqlitePiOperationLedger(path)
    ledger.admit(
        invocation.operation_id,
        pi.pi_durable_fingerprint(rig.adapter.config, invocation),
        invocation.episode_id,
        invocation.turn_id,
    )
    assert ledger.lookup(invocation.operation_id).phase is PiOperationPhase.EXECUTING  # type: ignore[union-attr]
    ledger.close()

    reopened = SqlitePiOperationLedger(path)
    assert reopened.lookup(invocation.operation_id).phase is PiOperationPhase.EXECUTING  # type: ignore[union-attr]
    recovered = PiRecoveredRuntime(rig.adapter, reopened)
    assert recovered.recovered_settlements[0].outcome is TurnOutcome.INDETERMINATE
    result = recovered.start(invocation).wait()
    assert result.outcome is TurnOutcome.INDETERMINATE
    assert result.termination_code == "restart-indeterminate" and result.accepted_appends == 0
    assert not rig.factory.calls
    reopened.close()


def test_recovery_atomically_classifies_every_preexisting_execution(tmp_path: Path) -> None:
    path = tmp_path / "ledger" / "operations.sqlite3"
    rig = Rig(tmp_path / "rig")
    first, _ = rig.invocation("ambiguous-one")
    second, _ = rig.invocation("ambiguous-two")
    ledger = SqlitePiOperationLedger(path)
    for invocation in (first, second):
        ledger.admit(
            invocation.operation_id,
            pi.pi_durable_fingerprint(rig.adapter.config, invocation),
            invocation.episode_id,
            invocation.turn_id,
        )
    ledger.close()

    reopened = SqlitePiOperationLedger(path)
    runtime = PiRecoveredRuntime(rig.adapter, reopened)
    assert len(runtime.recovered_settlements) == 2
    assert {result.outcome for result in runtime.recovered_settlements} == {TurnOutcome.INDETERMINATE}
    assert all(record.phase is PiOperationPhase.SETTLED for record in reopened.records())
    assert not rig.factory.calls
    reopened.close()


def test_operation_ledger_refuses_a_second_live_writer(tmp_path: Path) -> None:
    path = tmp_path / "ledger" / "operations.sqlite3"
    ledger = SqlitePiOperationLedger(path)
    with pytest.raises(StorageError, match="already has a live writer"):
        SqlitePiOperationLedger(path)
    ledger.close()
    SqlitePiOperationLedger(path).close()


def test_completed_replay_conflict_acknowledgement_watermark_and_eviction(tmp_path: Path) -> None:
    path = tmp_path / "ledger" / "operations.sqlite3"
    rig = Rig(tmp_path / "first")
    invocation, _ = rig.invocation("completed")
    ledger = SqlitePiOperationLedger(path)
    runtime = PiRecoveredRuntime(rig.adapter, ledger)
    operation = runtime.start(invocation)
    result = operation.wait(3)
    assert runtime.start(invocation) is operation
    operation.close()
    runtime.acknowledge(invocation.operation_id)
    assert ledger.watermark() == 1
    assert runtime.evict() == (invocation.operation_id,)
    assert runtime.start(invocation).wait() == result
    ledger.close()

    fresh = Rig(tmp_path / "fresh", predecessor=rig)
    reopened = SqlitePiOperationLedger(path)
    recovered = PiRecoveredRuntime(fresh.adapter, reopened)
    assert recovered.start(invocation).wait() == result
    assert not fresh.factory.calls
    with pytest.raises(RuntimeProtocolError, match="operation-conflict"):
        recovered.start(replace(invocation, prompt="changed prompt"))
    reopened.close()


def test_close_persists_a_naturally_settled_result_before_cleanup(tmp_path: Path) -> None:
    rig = Rig(tmp_path / "rig")
    invocation, _ = rig.invocation("close-before-wait")
    ledger = SqlitePiOperationLedger(tmp_path / "ledger" / "operations.sqlite3")
    operation = PiRecoveredRuntime(rig.adapter, ledger).start(invocation)
    deadline = time.monotonic() + 3
    while rig.adapter.receipt(invocation.operation_id) is None and time.monotonic() < deadline:
        time.sleep(0.001)
    cleanup = operation.close()
    record = ledger.lookup(invocation.operation_id)
    assert record is not None and record.settlement().outcome is TurnOutcome.COMPLETED
    assert record.cleanup is cleanup.disposition is RuntimeCleanupDisposition.CLEAN
    with pytest.raises(RuntimeProtocolError, match="operation-closed"):
        operation.wait()
    assert operation.close() == cleanup
    ledger.close()


def test_cancelled_close_without_a_local_receipt_is_durably_indeterminate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = Rig(tmp_path / "rig", Plan(block=True))
    invocation, _ = rig.invocation("close-without-receipt")
    ledger = SqlitePiOperationLedger(tmp_path / "ledger" / "operations.sqlite3")
    runtime = PiRecoveredRuntime(rig.adapter, ledger)
    monkeypatch.setattr(rig.adapter, "receipt", lambda operation_id: None)
    operation = runtime.start(invocation)
    deadline = time.monotonic() + 2
    while not rig.factory.clients and time.monotonic() < deadline:
        time.sleep(0.001)
    assert rig.factory.clients and rig.factory.clients[0].entered.wait(2)
    assert operation.cancel("stop") is CancellationDisposition.REQUESTED
    cleanup = operation.close()
    record = ledger.lookup(invocation.operation_id)
    assert record is not None and record.settlement().outcome is TurnOutcome.INDETERMINATE
    assert record.termination_code == "close-indeterminate" and record.output_reference is None
    assert operation.close() == cleanup
    with pytest.raises(RuntimeProtocolError, match="operation-closed"):
        operation.wait()
    ledger.close()


def test_replayed_operation_obeys_close_then_wait_contract(tmp_path: Path) -> None:
    path = tmp_path / "ledger" / "operations.sqlite3"
    rig = Rig(tmp_path / "rig")
    invocation, _ = rig.invocation("replay-close")
    ledger = SqlitePiOperationLedger(path)
    runtime = PiRecoveredRuntime(rig.adapter, ledger)
    operation = runtime.start(invocation)
    operation.wait(3)
    operation.close()
    ledger.close()

    reopened = SqlitePiOperationLedger(path)
    replay = PiRecoveredRuntime(rig.adapter, reopened).start(invocation)
    cleanup = replay.close()
    assert replay.close() == cleanup
    with pytest.raises(RuntimeProtocolError, match="operation-closed"):
        replay.wait()
    reopened.close()


def test_lost_ledger_acknowledgements_retry_without_changing_the_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = Rig(tmp_path / "rig")
    invocation, _ = rig.invocation("lost-ledger-ack")
    ledger = SqlitePiOperationLedger(tmp_path / "ledger" / "operations.sqlite3")
    operation = PiRecoveredRuntime(rig.adapter, ledger).start(invocation)
    settle = ledger.settle
    settle_calls = 0

    def lost_settlement_ack(operation_id, result):
        nonlocal settle_calls
        settle_calls += 1
        record = settle(operation_id, result)
        if settle_calls == 1:
            raise StorageError("synthetic lost settlement acknowledgement")
        return record

    monkeypatch.setattr(ledger, "settle", lost_settlement_ack)
    with pytest.raises(StorageError, match="lost settlement acknowledgement"):
        operation.wait(3)
    result = operation.wait(3)
    assert ledger.lookup(invocation.operation_id).settlement() == result  # type: ignore[union-attr]

    upgrade = ledger.upgrade_cleanup
    upgrade_calls = 0

    def lost_cleanup_ack(operation_id, cleanup):
        nonlocal upgrade_calls
        upgrade_calls += 1
        record = upgrade(operation_id, cleanup)
        if upgrade_calls == 1:
            raise StorageError("synthetic lost cleanup acknowledgement")
        return record

    monkeypatch.setattr(ledger, "upgrade_cleanup", lost_cleanup_ack)
    with pytest.raises(StorageError, match="lost cleanup acknowledgement"):
        operation.close()
    cleanup = operation.close()
    assert cleanup.verified and ledger.lookup(invocation.operation_id).cleanup is cleanup.disposition  # type: ignore[union-attr]
    ledger.close()


def test_durable_fingerprint_ignores_reconstructed_fences_but_rejects_stable_route_change(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    invocation, _ = rig.invocation("fingerprint")
    original = pi.pi_durable_fingerprint(rig.adapter.config, invocation)
    reconstructed = replace(
        invocation,
        connection=replace(
            invocation.connection,
            authority_epoch=invocation.connection.authority_epoch + 1,
            state_version=invocation.connection.state_version + 1,
        ),
        grant_epoch=invocation.grant_epoch + 1,
    )
    assert pi.pi_durable_fingerprint(rig.adapter.config, reconstructed) == original
    changed_identity = replace(
        invocation,
        connection=replace(
            invocation.connection,
            identity=replace(invocation.connection.identity, connection_id="connection-other"),
        ),
    )
    assert pi.pi_durable_fingerprint(rig.adapter.config, changed_identity) != original


def test_start_failure_and_ledger_cleanup_recovery_are_safe_and_secret_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "ledger" / "operations.sqlite3"
    rig = Rig(tmp_path / "rig")
    invocation, _ = rig.invocation("failure")
    ledger = SqlitePiOperationLedger(path)
    runtime = PiRecoveredRuntime(rig.adapter, ledger)
    monkeypatch.setattr(rig.adapter, "start", lambda value: (_ for _ in ()).throw(RuntimeError(PROMPT)))
    with pytest.raises(RuntimeProtocolError, match="runtime-start-failed"):
        runtime.start(invocation)
    record = ledger.lookup(invocation.operation_id)
    assert record is not None and record.phase is PiOperationPhase.SETTLED
    assert record.cleanup is RuntimeCleanupDisposition.NOT_CREATED
    ledger.close()
    body = path.read_bytes()
    for secret in (PROMPT.encode(), AUTH, SESSION_CANARY.encode(), str(rig.adapter.config.working_directory).encode()):
        assert secret not in body
    reopened = SqlitePiOperationLedger(path)
    assert reopened.lookup(invocation.operation_id).cleanup is RuntimeCleanupDisposition.NOT_CREATED  # type: ignore[union-attr]
    reopened.close()
