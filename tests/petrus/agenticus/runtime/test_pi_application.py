"""Deterministic acceptance matrix for the application-owned Pi A5 boundary."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, cast

import pytest

import petrus.agenticus.runtime.pi as native
import petrus.agenticus.runtime.pi_application as app
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
from petrus.agenticus.connection.materialization import MaterializedState
from petrus.agenticus.hands.conformance import SevenStepEpisodePolicy
from petrus.agenticus.hands.contract import RejectionCategory, ToolError, ToolMethod, ToolResult
from petrus.agenticus.hands.workspace import MotusWorkspaceAdapter
from petrus.agenticus.program.descriptor import ProgramOwnership
from petrus.agenticus.runtime.installation import InstalledComponent, RuntimeInstallation
from petrus.agenticus.runtime.operation import RuntimeCleanupDisposition, RuntimeProtocolError
from petrus.agenticus.runtime.profiles import PI_APPLICATION_A5_E2B, PI_APPLICATION_A5_GONDOLIN
from petrus.agenticus.thread.continuation import Continuation, ContinuationDescriptor, ContinuationState
from petrus.agenticus.thread.identity import ContinuationId, EpisodeId, ThreadId, TurnId
from petrus.agenticus.thread.lifecycle import CancellationDisposition, TurnOutcome
from petrus.motus.execution import EnvironmentSpec
from petrus.motus.execution.archive import workspace_archive
from petrus.motus.execution.providers import LocalProcessEnvironment

EFFECT = CapabilityDescriptor(
    DescriptorIdentity(DescriptorKind.EFFECT, "host.fenced", 1), frozenset({"effect.host-fenced"})
)
KEY = b"credential-canary"


class Continuations:
    def __init__(self) -> None:
        self.values: dict[str, app.PiApplicationContinuationPayloadV1] = {}
        self.fail = False

    def store(self, operation_id: str, payload: app.PiApplicationContinuationPayloadV1) -> str:
        if self.fail:
            raise RuntimeError("store failed")
        reference = f"continuation-{operation_id}"
        prior = self.values.get(reference)
        if prior is not None and prior != payload:
            raise RuntimeError("conflict")
        self.values[reference] = payload
        return reference

    def load(self, state_reference: str) -> app.PiApplicationContinuationPayloadV1:
        return self.values[state_reference]


class Turns:
    def __init__(self) -> None:
        self.values: dict[str, app.PiApplicationStepPayloadV1] = {}
        self.fail = False

    def store_turn(self, operation_id: str, payload: app.PiApplicationStepPayloadV1) -> str:
        if self.fail:
            raise RuntimeError("store failed")
        self.values[operation_id] = payload
        return f"turn-{operation_id}"


class Home:
    def read(self) -> bytes:
        return KEY

    def __repr__(self) -> str:
        return "Home(<opaque>)"


class Custody:
    def __init__(self, provider: str = "anthropic") -> None:
        self.provider = provider
        self.records: list[tuple[str, str]] = []
        self.clean = True
        self.admit = True

    def view(self, *, profile: str = "api-key") -> ConnectionView:
        return ConnectionView(
            ConnectionIdentity("connection", self.provider, "account", profile), ConnectionStatus.READY, 3, 4, None
        )

    def materialize(self, connection_id, host_id, *, mode, ttl, operation_id):
        assert mode is LeaseMode.READ
        self.records.append(("materialize", operation_id))
        return Materialization(
            AttachmentFence("credential", "lease", connection_id, host_id, 1, 3, 4),
            mode,
            time.monotonic() + ttl,
            cast(MaterializedState, Home()),
        )

    def admit_result(self, fence, *, operation_id):
        self.records.append(("admit", operation_id))
        if not self.admit:
            raise RuntimeError("stale")
        return AdmissionResult(operation_id, "result", fence.attachment_id)

    def release(self, materialization, *, operation_id):
        self.records.append(("release", operation_id))
        return ReleaseResult(
            operation_id,
            CleanupEvidence(
                materialization.fence.attachment_id, self.clean, False, len(KEY), security_violation=not self.clean
            ),
        )


@dataclass
class Plan:
    method: ToolMethod | None = None
    params: dict[str, object] | None = None
    text: str = "ok"
    error: str | None = None
    block: bool = False
    clean: bool = True
    synthetic_write: bool = False


class Client:
    def __init__(self, plan: Plan, prior: app.PiApplicationContinuationPayloadV1 | None) -> None:
        self.plan, self.prior = plan, prior
        self.entered = threading.Event()

    def run(self, gateway, invocation, current, deadline):
        self.entered.set()
        while self.plan.block and current() and time.monotonic() < deadline:
            time.sleep(0.002)
        if self.plan.error:
            raise RuntimeProtocolError(self.plan.error)
        if not current():
            raise RuntimeProtocolError("cancelled")
        if time.monotonic() >= deadline:
            raise RuntimeProtocolError("deadline-exceeded")
        results: tuple[ToolResult, ...] = ()
        if self.plan.method is not None:
            coordinates = invocation.attachment.coordinates()
            if self.plan.synthetic_write:
                result = ToolResult(
                    f"call-{invocation.operation_id}",
                    coordinates.attachment_id,
                    coordinates.attachment_epoch,
                    False,
                    None,
                    ToolError(RejectionCategory.WRITE, "application guard blocked workspace write"),
                )
            else:
                result = gateway.submit(
                    {
                        "version": 1,
                        "call_id": f"call-{invocation.operation_id}",
                        "episode_id": coordinates.episode_id,
                        "attachment_id": coordinates.attachment_id,
                        "attachment_epoch": coordinates.attachment_epoch,
                        "grant_epoch": invocation.grant_epoch,
                        "method": self.plan.method.value,
                        "params": self.plan.params or {},
                    }
                )
            results = (result,)
        prior = json.loads((self.prior.transcript_json if self.prior else b"[]").decode())
        transcript = json.dumps(
            [
                *prior,
                {"role": "user", "content": invocation.observation},
                {"role": "assistant", "content": self.plan.text},
            ],
            separators=(",", ":"),
        ).encode()
        return app._Candidate(self.plan.text, transcript, results)

    def close(self) -> bool:
        return self.plan.clean


class Factory:
    def __init__(self, *plans: Plan) -> None:
        self.plans = list(plans) or [Plan()]
        self.calls: list[dict[str, Any]] = []
        self.clients: list[Client] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        client = Client(self.plans.pop(0), kwargs["prior"])
        self.clients.append(client)
        return client


def snapshot(profile: str) -> ResolutionSnapshot:
    runtime = PI_APPLICATION_A5_GONDOLIN if profile == "gondolin" else PI_APPLICATION_A5_E2B
    return ResolutionSnapshot(
        1,
        (
            runtime,
            app.PI_APPLICATION_CONNECTION_CAPABILITIES,
            app.PI_APPLICATION_PROGRAM_CAPABILITIES,
            app.PI_APPLICATION_HANDS,
            CapabilityDescriptor(
                DescriptorIdentity(DescriptorKind.TERRITORY, f"motus.{profile}", 1), frozenset({f"territory.{profile}"})
            ),
            app.PI_APPLICATION_CONTINUATION_CAPABILITIES,
            EFFECT,
        ),
    )


class Rig:
    def __init__(self, tmp_path: Path, profile: str = "gondolin", *plans: Plan, wall_timeout: float = 1) -> None:
        self.profile = profile
        working, runtime, source = tmp_path / "working", tmp_path / "runtime", tmp_path / "source"
        for path in (working, runtime, source):
            path.mkdir(parents=True, exist_ok=True)
        runtime.chmod(0o700)
        (source / "message.txt").write_text("before")
        (source / "verify.sh").write_text("#!/bin/sh\ngrep -q after message.txt\n")
        provider = LocalProcessEnvironment()
        binding = MotusAttachmentBinding.open(
            provider,
            f"territory-{profile}",
            EnvironmentSpec(),
            workspace_archive_bytes=workspace_archive(source),
            input_digest="input",
        )
        # A bounded provider double: retain production Motus lifecycle/workspace,
        # but expose the exact qualified provider name to the runtime fence.
        object.__setattr__(binding.execution.lease, "provider", profile)
        object.__setattr__(binding._lease, "provider", profile)  # noqa: SLF001
        provider.provider = profile
        provider._leases[binding.lease_identity.operation_id] = binding._lease  # noqa: SLF001
        self.provider, self.binding = provider, binding
        self.episode = EpisodeId("episode")
        self.attachment = EpisodeAttachment(
            episode_id=self.episode,
            snapshot=snapshot(profile),
            binding=binding,
            attachment_id=f"attachment-{profile}",
            deadline=time.monotonic() + 10,
        )
        self.gateway = self.attachment.gateway(
            MotusWorkspaceAdapter(provider, binding.execution, test_command=("/bin/sh", "verify.sh"))
        )
        self.custody, self.continuations, self.turns, self.factory = (
            Custody(),
            Continuations(),
            Turns(),
            Factory(*plans),
        )
        self.adapter = app.PiApplicationRuntimeAdapter(
            app.PiApplicationRuntimeConfig(
                "anthropic",
                "claude-sonnet-4-5",
                profile,
                working,
                runtime,
                host_id="host",
                wall_timeout=wall_timeout,
                cancellation_grace=0.03,
            ),
            app.PiApplicationContinuationCodec(self.continuations),
            self.turns,
            self.custody,
            client_factory=self.factory,
        )
        self.adapter._installation = RuntimeInstallation(
            self.adapter.descriptor.identity,
            1,
            (InstalledComponent("pi-agent-core", "0.83.0", "test"),),
            "test",
            "test",
        )
        self.adapter._node = self.adapter._coding = self.adapter._core = self.adapter._ai = "/fake"

    def invocation(
        self,
        name: str,
        capabilities: tuple[ToolMethod, ...],
        *,
        continuation: Continuation | None = None,
        observation: str | None = None,
        grant_epoch: int | None = None,
        connection: ConnectionView | None = None,
    ) -> app.PiApplicationRuntimeInvocation:
        grant = self.attachment.grants().open(
            capabilities,
            writable_paths=("message.txt", "continuity.txt"),
            allowed_argv=(("/bin/cat", "message.txt"),),
            deadline=self.attachment.deadline,
            max_calls=8,
        )
        return app.PiApplicationRuntimeInvocation(
            name,
            self.episode,
            TurnId(f"turn-{name}"),
            observation or name,
            connection or self.custody.view(),
            self.attachment,
            self.gateway,
            grant.grant_epoch if grant_epoch is None else grant_epoch,
            continuation,
        )

    def run(self, name: str, capabilities: tuple[ToolMethod, ...], continuation: Continuation | None = None):
        operation = self.adapter.start(self.invocation(name, capabilities, continuation=continuation))
        result = operation.wait(2)
        cleanup = operation.close()
        return result, cleanup


def claimed(
    reference: str, *, descriptor=app.PI_APPLICATION_CONTINUATION_DESCRIPTOR, state=ContinuationState.IN_USE
) -> Continuation:
    return Continuation(ContinuationId(f"id-{reference}"), ThreadId("thread"), descriptor, reference, state)


def test_exact_identities_capabilities_ownership_and_snapshots() -> None:
    assert app.PI_APPLICATION_PROGRAM.ownership is ProgramOwnership.HARNESS
    assert app.PI_APPLICATION_PROGRAM.identity == DescriptorIdentity(DescriptorKind.PROGRAM, "pi.application-owned", 1)
    assert app.PI_APPLICATION_PROGRAM.owns_steering and app.PI_APPLICATION_PROGRAM.owns_evaluation
    assert app.PI_APPLICATION_PROGRAM_CAPABILITIES.offers == frozenset({"program.application-owned"})
    assert app.PI_APPLICATION_CONNECTION_CAPABILITIES.offers == frozenset({"connection.pi-compatible"})
    assert app.PI_APPLICATION_HANDS.offers == frozenset({"hands.capability-scoped"})
    for profile, descriptor in (("gondolin", PI_APPLICATION_A5_GONDOLIN), ("e2b", PI_APPLICATION_A5_E2B)):
        selected = snapshot(profile)
        assert selected.descriptor(DescriptorKind.RUNTIME) is descriptor
        territory = selected.descriptor(DescriptorKind.TERRITORY)
        assert territory is not None and territory.identity.name == f"motus.{profile}"
        assert descriptor.offers == frozenset({"archetype.a5", "loop.application-owned", "topology.split"})


@pytest.mark.parametrize(("provider", "model"), native.PI_API_KEY_CATALOG)
def test_api_key_direct_catalog_is_exact(tmp_path: Path, provider: str, model: str) -> None:
    (tmp_path / "w").mkdir()
    (tmp_path / "r").mkdir(mode=0o700)
    assert (
        app.PiApplicationRuntimeConfig(provider, model, "gondolin", tmp_path / "w", tmp_path / "r").provider == provider
    )


@pytest.mark.parametrize("profile", ["subscription", "cc-patch-subscription", "openai-codex"])
def test_subscription_and_codex_profiles_are_rejected(tmp_path: Path, profile: str) -> None:
    rig = Rig(tmp_path, "gondolin", Plan())
    try:
        with pytest.raises(ValueError, match="only an api-key connection"):
            rig.invocation("foreign-authority", (), connection=rig.custody.view(profile=profile))
    finally:
        rig.attachment.settle()


def test_seven_separate_operations_drive_policy_and_real_gateway(tmp_path: Path) -> None:
    plans = (
        Plan(ToolMethod.WORKSPACE_WRITE, {"path": "message.txt", "content": "after"}, synthetic_write=True),
        Plan(ToolMethod.WORKSPACE_READ, {"path": "message.txt"}),
        Plan(ToolMethod.WORKSPACE_SEARCH, {"query": "before", "path": "message.txt"}),
        Plan(ToolMethod.WORKSPACE_SHELL, {"argv": ["/bin/cat", "message.txt"], "cwd": "."}),
        Plan(ToolMethod.WORKSPACE_WRITE, {"path": "message.txt", "content": "after"}),
        Plan(ToolMethod.WORKSPACE_TEST, {}),
        Plan(text="ES049_APP_E1_OK"),
    )
    rig = Rig(tmp_path, "gondolin", *plans)
    policy = SevenStepEpisodePolicy(
        attachment_id=rig.attachment.attachment_id, attachment_epoch=1, expected_marker="ES049_APP_E1_OK"
    )
    continuation = None
    for index, capabilities in enumerate(
        (
            (ToolMethod.WORKSPACE_READ,),
            (ToolMethod.WORKSPACE_READ,),
            (ToolMethod.WORKSPACE_SEARCH,),
            (ToolMethod.WORKSPACE_SHELL,),
            (ToolMethod.WORKSPACE_WRITE,),
            (ToolMethod.WORKSPACE_TEST,),
            (),
        )
    ):
        policy.begin_turn()
        result, cleanup = rig.run(f"op-{index}", capabilities, continuation)
        assert result.outcome is TurnOutcome.COMPLETED and cleanup.disposition is RuntimeCleanupDisposition.CLEAN
        step = rig.turns.values[f"op-{index}"]
        for tool_result in step.results:
            method = plans[index].method
            assert method is not None
            policy.observe(method, tool_result)
        if policy.write_grant_ready:
            policy.note_grant_opened()
        policy.append_observation()
        continuation = claimed(result.continuation_reference)
    assert policy.admit_marker("ES049_APP_E1_OK").admitted
    assert policy.turns == policy.appends == 7
    assert rig.gateway.counters().adapter_entries == 5
    assert rig.gateway.counters().target_mutations == 1
    assert [name for name, _ in rig.custody.records].count("materialize") == 7
    assert len(json.loads(rig.continuations.values["continuation-op-6"].transcript_json)) == 14
    rig.attachment.settle()


def test_gondolin_settles_before_e2b_and_continuation_crosses_without_authority_leak(tmp_path: Path) -> None:
    e1 = Rig(tmp_path / "e1", "gondolin", Plan(text="E1"))
    first, _ = e1.run("e1", ())
    continuation = e1.continuations.values[first.continuation_reference]
    settlement = e1.attachment.settle()
    assert settlement.settlement.verified and e1.provider.lookup("territory-gondolin") is None
    e2 = Rig(tmp_path / "e2", "e2b", Plan(text="E2"))
    e2.adapter._config = replace(  # noqa: SLF001 - one project, fresh territory/runtime root
        e2.adapter._config, working_directory=e1.adapter._config.working_directory
    )
    e2.continuations.values[first.continuation_reference] = continuation
    second, _ = e2.run("e2", (), claimed(first.continuation_reference))
    transcript = json.loads(e2.continuations.values[second.continuation_reference].transcript_json)
    assert [message["content"] for message in transcript] == ["e1", "E1", "e2", "E2"]
    rendered = e2.continuations.values[second.continuation_reference].transcript_json.decode()
    assert all(
        value not in rendered for value in ("gondolin", "attachment-gondolin", "credential", "grant_epoch", "workspace")
    )


def test_closed_write_is_synthetic_and_crossing_flat(tmp_path: Path) -> None:
    rig = Rig(
        tmp_path,
        "gondolin",
        Plan(ToolMethod.WORKSPACE_WRITE, {"path": "message.txt", "content": "after"}, synthetic_write=True),
    )
    result, _ = rig.run("blocked", (ToolMethod.WORKSPACE_READ,))
    tool = rig.turns.values["blocked"].results[0]
    assert tool.error and tool.error.category is RejectionCategory.WRITE
    counters = rig.gateway.counters()
    assert (counters.adapter_entries, counters.stages, counters.commits, counters.target_mutations) == (0, 0, 0, 0)
    assert result.outcome is TurnOutcome.COMPLETED


def test_shared_model_tool_result_projection_excludes_attachment_custody() -> None:
    result = ToolResult(
        "call",
        "attachment-gondolin",
        7,
        True,
        {"text": "bounded"},
        None,
    )
    assert result.to_model_data() == {
        "version": 1,
        "ok": True,
        "data": {"text": "bounded"},
        "error": None,
    }
    assert result.to_data()["attachment_id"] == "attachment-gondolin"
    assert result.to_data()["epoch"] == 7
    denied = ToolResult(
        "denied",
        "attachment-e2b",
        11,
        False,
        None,
        ToolError(RejectionCategory.WRITE, "application guard blocked workspace write"),
    )
    assert denied.to_model_data() == {
        "version": 1,
        "ok": False,
        "data": None,
        "error": {"category": "write", "detail": "application guard blocked workspace write"},
    }


@pytest.mark.qualification_installation
def test_real_framed_helper_blocks_write_and_round_trips_permitted_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    node = Path("/tmp/petrus-pi-a2-probe/node_modules/node/bin/node")
    if not node.is_file():
        pytest.skip("exact qualification Node required")
    coding = tmp_path / "coding.mjs"
    core = tmp_path / "core.mjs"
    ai = tmp_path / "ai.mjs"
    coding.write_text(
        """export const convertToLlm=x=>x;
export class ModelRuntime {
  static async create(options) {
    if (options.modelsPath !== null || options.allowModelNetwork !== false) throw Error('shape');
    return new ModelRuntime();
  }
  async setRuntimeApiKey(provider,key) { if (provider !== 'anthropic' || !key) throw Error('key'); }
  getModel(provider,id) { return {provider,id}; }
  streamSimple() { throw Error('network'); }
}
"""
    )
    core.write_text(
        """export async function runAgentLoop(prompts,context,config,emit,signal,streamFn) {
  if (arguments.length !== 6 || config.shouldStopAfterTurn() !== true || context.messages.length !== 1) throw Error('shape');
  const observation=prompts[0].content[0].text;
  if (observation === 'blocked') {
    const args={path:'message.txt',content:'after'};
    const blocked=await config.beforeToolCall({toolCall:{id:'blocked-call',name:'workspace_write',arguments:args},args,context},signal);
    if (!blocked?.block) throw Error('guard');
  } else {
    const tool=config.tools.find(candidate=>candidate.name==='workspace_read');
    await tool.execute('read-call',{path:'message.txt'},signal);
    if (observation === 'overflow') await tool.execute('read-call-2',{path:'message.txt'},signal);
  }
  return [prompts[0],{role:'assistant',content:[{type:'text',text:observation}],stopReason:'stop'}];
}
"""
    )
    ai.write_text("export const createProvider=()=>{throw Error('network')};\n")
    helper = Path(app.__file__).with_name("pi_application_helper.mjs")
    for observation, capabilities in (
        ("blocked", (ToolMethod.WORKSPACE_READ,)),
        ("read", (ToolMethod.WORKSPACE_READ,)),
    ):
        rig = Rig(tmp_path / observation, "gondolin", Plan())
        invocation = rig.invocation(observation, capabilities, observation=observation)
        prior = app.PiApplicationContinuationPayloadV1(
            app._working_binding(rig.adapter._config.working_directory),
            b'[{"role":"user","content":"prior"}]',
        )
        private_root = tmp_path / f"private-{observation}"
        private_root.mkdir(mode=0o700)
        client = app._SubprocessClient(
            node=str(node),
            coding_entrypoint=str(coding),
            core_entrypoint=str(core),
            ai_entrypoint=str(ai),
            helper=helper,
            private_root=private_root,
            config=rig.adapter._config,
            invocation=invocation,
            prior=prior,
            api_key=KEY.decode(),
        )
        candidate = client.run(rig.gateway, invocation, lambda: True, time.monotonic() + 2)
        assert client.close()
        transcript = json.loads(candidate.transcript)
        assert [message["content"] for message in transcript[:1]] == ["prior"]
        assert [message["role"] for message in transcript[1:]] == ["user", "assistant"]
        counters = rig.gateway.counters()
        if observation == "blocked":
            assert candidate.results[0].error
            assert candidate.results[0].error.category is RejectionCategory.WRITE
            assert (counters.adapter_entries, counters.stages, counters.commits, counters.target_mutations) == (
                0,
                0,
                0,
                0,
            )
        else:
            assert candidate.results[0].ok and counters.adapter_entries == 1
        rig.attachment.settle()

    rig = Rig(tmp_path / "overflow", "gondolin", Plan())
    invocation = rig.invocation("overflow", (ToolMethod.WORKSPACE_READ,), observation="overflow")
    private_root = tmp_path / "private-overflow"
    private_root.mkdir(mode=0o700)
    client = app._SubprocessClient(
        node=str(node),
        coding_entrypoint=str(coding),
        core_entrypoint=str(core),
        ai_entrypoint=str(ai),
        helper=helper,
        private_root=private_root,
        config=replace(rig.adapter._config, max_tool_calls=1),
        invocation=invocation,
        prior=app.PiApplicationContinuationPayloadV1(
            app._working_binding(rig.adapter._config.working_directory),
            b'[{"role":"user","content":"prior"}]',
        ),
        api_key=KEY.decode(),
    )
    with pytest.raises(RuntimeProtocolError, match="protocol-failed"):
        client.run(rig.gateway, invocation, lambda: True, time.monotonic() + 2)
    assert client.close() and rig.gateway.counters().adapter_entries == 1
    rig.attachment.settle()

    monkeypatch.setattr(ToolResult, "to_model_data", lambda result: result.to_data())
    rig = Rig(tmp_path / "full-result", "gondolin", Plan())
    invocation = rig.invocation("full-result", (ToolMethod.WORKSPACE_READ,), observation="read")
    private_root = tmp_path / "private-full-result"
    private_root.mkdir(mode=0o700)
    client = app._SubprocessClient(
        node=str(node),
        coding_entrypoint=str(coding),
        core_entrypoint=str(core),
        ai_entrypoint=str(ai),
        helper=helper,
        private_root=private_root,
        config=rig.adapter._config,
        invocation=invocation,
        prior=app.PiApplicationContinuationPayloadV1(
            app._working_binding(rig.adapter._config.working_directory),
            b'[{"role":"user","content":"prior"}]',
        ),
        api_key=KEY.decode(),
    )
    with pytest.raises(RuntimeProtocolError, match="protocol-failed"):
        client.run(rig.gateway, invocation, lambda: True, time.monotonic() + 2)
    assert client.close() and rig.gateway.counters().adapter_entries == 1
    rig.attachment.settle()


@pytest.mark.qualification_installation
def test_real_framed_tool_projection_preserves_prefix_without_attachment_custody(tmp_path: Path) -> None:
    node = Path("/tmp/petrus-pi-a2-probe/node_modules/node/bin/node")
    if not node.is_file():
        pytest.skip("exact qualification Node required")
    coding = tmp_path / "coding.mjs"
    core = tmp_path / "core.mjs"
    ai = tmp_path / "ai.mjs"
    coding.write_text(
        """export const convertToLlm=x=>x;
export class ModelRuntime {
  static async create(options) {
    if (options.modelsPath !== null || options.allowModelNetwork !== false) throw Error('shape');
    return new ModelRuntime();
  }
  async setRuntimeApiKey(provider,key) { if (provider !== 'anthropic' || !key) throw Error('key'); }
  getModel(provider,id) { return {provider,id}; }
  streamSimple() { throw Error('network'); }
}
"""
    )
    core.write_text(
        """export async function runAgentLoop(prompts,context,config,emit,signal,streamFn) {
  if (arguments.length !== 6 || config.shouldStopAfterTurn() !== true) throw Error('shape');
  const tool=config.tools.find(candidate=>candidate.name==='workspace_read');
  const callId=`read-${prompts[0].content[0].text}`;
  const result=await tool.execute(callId,{path:'message.txt'},signal);
  return [
    prompts[0],
    {role:'toolResult',toolCallId:callId,toolName:'workspace_read',content:result.content,isError:false,timestamp:0},
    {role:'assistant',content:[{type:'text',text:'done'}],stopReason:'stop',timestamp:0},
  ];
}
"""
    )
    ai.write_text("export const createProvider=()=>{throw Error('network')};\n")
    helper = Path(app.__file__).with_name("pi_application_helper.mjs")
    prior = None
    accepted: list[dict[str, object]] | None = None
    prior_attachment: str | None = None
    for profile in ("gondolin", "e2b"):
        rig = Rig(tmp_path / profile, profile, Plan())
        invocation = rig.invocation(profile, (ToolMethod.WORKSPACE_READ,), observation=profile)
        private_root = tmp_path / f"private-{profile}"
        private_root.mkdir(mode=0o700)
        client = app._SubprocessClient(
            node=str(node),
            coding_entrypoint=str(coding),
            core_entrypoint=str(core),
            ai_entrypoint=str(ai),
            helper=helper,
            private_root=private_root,
            config=rig.adapter._config,
            invocation=invocation,
            prior=prior,
            api_key=KEY.decode(),
        )
        candidate = client.run(rig.gateway, invocation, lambda: True, time.monotonic() + 2)
        assert client.close()
        transcript = json.loads(candidate.transcript)
        if accepted is not None:
            assert transcript[: len(accepted)] == accepted
        projection = json.loads(transcript[-2]["content"][0]["text"])
        assert projection == {
            "version": 1,
            "ok": True,
            "data": {"content": "before"},
            "error": None,
        }
        assert candidate.results[0].attachment_id == rig.attachment.attachment_id
        assert candidate.results[0].epoch == rig.attachment.coordinates().attachment_epoch
        assert rig.attachment.attachment_id not in candidate.transcript.decode()
        if prior_attachment is not None:
            assert prior_attachment not in candidate.transcript.decode()
        else:
            prior_attachment = rig.attachment.attachment_id
        prior = app.PiApplicationContinuationPayloadV1(
            app._working_binding(rig.adapter._config.working_directory),
            candidate.transcript,
        )
        accepted = transcript
        rig.attachment.settle()


@pytest.mark.qualification_installation
def test_real_protocol_rejects_post_terminal_and_post_abort_frames_before_gateway(tmp_path: Path) -> None:
    node = Path("/tmp/petrus-pi-a2-probe/node_modules/node/bin/node")
    if not node.is_file():
        pytest.skip("exact qualification Node required")

    def client_for(script: str, name: str) -> tuple[app._SubprocessClient, Rig, app.PiApplicationRuntimeInvocation]:
        helper = tmp_path / f"{name}.mjs"
        helper.write_text(script)
        rig = Rig(tmp_path / name, "gondolin", Plan())
        invocation = rig.invocation(name, (ToolMethod.WORKSPACE_READ,))
        private_root = tmp_path / f"private-{name}"
        private_root.mkdir(mode=0o700)
        return (
            app._SubprocessClient(
                node=str(node),
                coding_entrypoint="/unused/coding",
                core_entrypoint="/unused/core",
                ai_entrypoint="/unused/ai",
                helper=helper,
                private_root=private_root,
                config=rig.adapter._config,
                invocation=invocation,
                prior=None,
                api_key=KEY.decode(),
            ),
            rig,
            invocation,
        )

    delta = base64.b64encode(b"[]").decode()
    batched = f"""import readline from 'node:readline';
const reader=readline.createInterface({{input:process.stdin}});
reader.once('line',()=>{{process.stdout.write('{{"type":"ready"}}\\n{{"type":"complete","text":"done","transcript":"{delta}"}}\\n{{"type":"tool_call","id":"late","method":"workspace_read","params":{{"path":"message.txt"}}}}\\n');}});
"""
    client, rig, invocation = client_for(batched, "post-terminal")
    with pytest.raises(RuntimeProtocolError, match="frame-order"):
        client.run(rig.gateway, invocation, lambda: True, time.monotonic() + 2)
    assert client.close() and rig.gateway.counters().adapter_entries == 0
    rig.attachment.settle()

    after_abort = f"""import readline from 'node:readline';
const reader=readline.createInterface({{input:process.stdin}});let first=true;
reader.on('line',line=>{{if(first){{first=false;process.stdout.write('{{"type":"ready"}}\\n');}}else{{process.stdout.write('{{"type":"complete","text":"late","transcript":"{delta}"}}\\n');}}}});
"""
    client, rig, invocation = client_for(after_abort, "post-abort")
    with pytest.raises(RuntimeProtocolError, match="deadline-exceeded"):
        client.run(rig.gateway, invocation, lambda: True, time.monotonic() + 0.01)
    assert client.close() and rig.gateway.counters().adapter_entries == 0
    rig.attachment.settle()

    noncanonical = """import readline from 'node:readline';
const reader=readline.createInterface({input:process.stdin});
reader.once('line',()=>{process.stdout.write('{"type":"ready"}\\n{"type":"complete","text":"done","transcript":"W10=="}\\n');reader.close();});
"""
    client, rig, invocation = client_for(noncanonical, "noncanonical")
    with pytest.raises(RuntimeProtocolError, match="malformed-complete"):
        client.run(rig.gateway, invocation, lambda: True, time.monotonic() + 2)
    assert client.close() and rig.gateway.counters().adapter_entries == 0
    rig.attachment.settle()


def test_immutable_prior_transcript_plus_delta_and_payload_bounds() -> None:
    raw = b'[{"role":"user","content":"prior"}]'
    value = app.PiApplicationContinuationPayloadV1("d" * 64, raw)
    assert value.transcript_json is raw
    with pytest.raises((ValueError, TypeError)):
        app.PiApplicationContinuationPayloadV1("d" * 64, b"[NaN]")
    with pytest.raises(ValueError, match="byte bound"):
        app._transcript(b"[] " * 10, 2, 10)
    with pytest.raises(ValueError, match="message array"):
        app._transcript(b"[{},{}]", 100, 1)
    for encoded in ("W10", "W10==", "!!!!"):
        with pytest.raises(Exception):
            decoded = base64.b64decode(encoded, validate=True)
            if base64.b64encode(decoded).decode() != encoded:
                raise ValueError


def test_foreign_continuation_project_binding_and_claim_state_rejected(tmp_path: Path) -> None:
    rig = Rig(tmp_path, "gondolin", Plan())
    foreign = ContinuationDescriptor(
        DescriptorIdentity(DescriptorKind.CONTINUATION, "foreign", 1),
        DescriptorIdentity(DescriptorKind.PROGRAM, "foreign", 1),
    )
    with pytest.raises(ValueError):
        rig.adapter.start(rig.invocation("foreign", (), continuation=claimed("missing", descriptor=foreign)))
    rig.continuations.values["bad"] = app.PiApplicationContinuationPayloadV1("e" * 64, b"[]")
    with pytest.raises(RuntimeProtocolError, match="project-mismatch"):
        rig.adapter.start(rig.invocation("project", (), continuation=claimed("bad")))
    with pytest.raises(RuntimeProtocolError, match="not-claimed"):
        rig.adapter.start(rig.invocation("state", (), continuation=claimed("bad", state=ContinuationState.AVAILABLE)))


def test_resolution_grant_runtime_and_connection_bindings_reject_stale(tmp_path: Path) -> None:
    rig = Rig(tmp_path, "gondolin", Plan())
    stale = rig.invocation("stale", (), grant_epoch=999)
    with pytest.raises(RuntimeProtocolError, match="grant-mismatch"):
        rig.adapter.start(stale)
    wrong = replace(rig.custody.view(), identity=ConnectionIdentity("connection", "openai", "account", "api-key"))
    with pytest.raises(RuntimeProtocolError, match="provider-mismatch"):
        rig.adapter.start(rig.invocation("provider", (), connection=wrong))
    object.__setattr__(rig.binding.execution.lease, "provider", "e2b")
    with pytest.raises(RuntimeProtocolError, match="territory-lease"):
        rig.adapter.start(rig.invocation("territory", ()))


def test_application_a5_post_run_lease_drift_releases_authority_without_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = Rig(tmp_path, "gondolin", Plan())
    invocation = rig.invocation("post-run-stale", ())
    run = Client.run

    def complete_then_replace(self, gateway, current_invocation, current, deadline):
        result = run(self, gateway, current_invocation, current, deadline)
        object.__setattr__(rig.binding.execution.lease, "provider", "e2b")
        return result

    monkeypatch.setattr(Client, "run", complete_then_replace)
    operation = rig.adapter.start(invocation)
    result = operation.wait(2)

    assert result.outcome is TurnOutcome.FAILED
    assert result.termination_code == "runtime-territory-lease-required"
    assert result.output_reference is result.continuation_reference is None
    assert not rig.turns.values and not rig.continuations.values
    assert [name for name, _ in rig.custody.records] == ["materialize", "release"]
    assert operation.close().disposition is RuntimeCleanupDisposition.CLEAN
    object.__setattr__(rig.binding.execution.lease, "provider", "gondolin")
    assert rig.attachment.settle().settlement.verified


@pytest.mark.parametrize(
    "error", ["provider-failed", "protocol-failed", "terminal-missing", "frame-order", "malformed-frame"]
)
def test_helper_failures_do_not_publish(tmp_path: Path, error: str) -> None:
    rig = Rig(tmp_path, "gondolin", Plan(error=error))
    result, cleanup = rig.run("failure", ())
    assert (result.outcome, result.termination_code, result.output_reference, result.continuation_reference) == (
        TurnOutcome.FAILED,
        error,
        None,
        None,
    )
    assert (
        cleanup.disposition is RuntimeCleanupDisposition.CLEAN and not rig.turns.values and not rig.continuations.values
    )


def test_cancellation_deadline_and_cleanup_failure_prevent_publication(tmp_path: Path) -> None:
    rig = Rig(tmp_path / "cancel", "gondolin", Plan(block=True))
    operation = rig.adapter.start(rig.invocation("cancel", ()))
    for _ in range(100):
        if rig.factory.clients:
            break
        time.sleep(0.002)
    assert rig.factory.clients[0].entered.wait(1)
    assert operation.cancel("stop") is CancellationDisposition.REQUESTED
    assert operation.wait(2).outcome is TurnOutcome.CANCELLED
    assert operation.close().disposition is RuntimeCleanupDisposition.CLEAN
    deadline = Rig(tmp_path / "deadline", "gondolin", Plan(block=True), wall_timeout=0.02)
    assert deadline.run("deadline", ())[0].termination_code == "deadline-exceeded"
    dirty = Rig(tmp_path / "dirty", "gondolin", Plan(clean=False))
    result, cleanup = dirty.run("dirty", ())
    assert (
        result.termination_code == "cleanup-unverified" and cleanup.disposition is RuntimeCleanupDisposition.UNVERIFIED
    )
    assert not dirty.turns.values and not dirty.continuations.values


@pytest.mark.parametrize("profile", ["gondolin", "e2b"])
def test_application_a5_cancellation_wins_while_remote_publication_lookup_is_stalled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, profile: str
) -> None:
    rig = Rig(tmp_path, profile, Plan())
    invocation = rig.invocation("stalled-publication", ())
    lookup_started, release_lookup = threading.Event(), threading.Event()
    binding_current = rig.adapter._binding_current
    calls = 0

    def stall_after_initial_validation(current: app.PiApplicationRuntimeInvocation) -> bool:
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

    result = operation.wait(2)
    assert result.outcome is TurnOutcome.CANCELLED
    assert result.output_reference is result.continuation_reference is None
    assert not rig.turns.values and not rig.continuations.values
    assert [name for name, _ in rig.custody.records] == ["materialize", "release"]
    assert operation.close().disposition is RuntimeCleanupDisposition.CLEAN
    assert rig.attachment.settle().settlement.verified


@pytest.mark.parametrize("profile", ["gondolin", "e2b"])
@pytest.mark.parametrize("lapse", ["grant", "deadline"])
def test_application_a5_rechecks_publication_admission_after_remote_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, profile: str, lapse: str
) -> None:
    rig = Rig(tmp_path, profile, Plan())
    invocation = rig.invocation("stale-admission", ())
    now = [time.monotonic()]
    rig.adapter._clock = lambda: now[0]
    lookup_started, release_lookup = threading.Event(), threading.Event()
    binding_current = rig.adapter._binding_current
    calls = 0

    def stall_after_initial_validation(current: app.PiApplicationRuntimeInvocation) -> bool:
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
        rig.attachment.grants().close()
        expected = "grant-mismatch"
    else:
        now[0] = rig.attachment.deadline
        expected = "deadline-exceeded"
    release_lookup.set()

    result = operation.wait(2)
    assert result.outcome is TurnOutcome.FAILED
    assert result.termination_code == expected
    assert result.output_reference is result.continuation_reference is None
    assert not rig.turns.values and not rig.continuations.values
    assert [name for name, _ in rig.custody.records] == ["materialize", "release"]
    assert operation.close().disposition is RuntimeCleanupDisposition.CLEAN
    assert rig.attachment.settle().settlement.verified


def test_application_a5_publication_claim_makes_later_cancellation_too_late(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = Rig(tmp_path, "gondolin", Plan())
    invocation = rig.invocation("claimed-publication", ())
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

    result = operation.wait(2)
    assert result.outcome is TurnOutcome.COMPLETED
    assert result.output_reference is not None and result.continuation_reference is not None
    assert operation.close().disposition is RuntimeCleanupDisposition.CLEAN
    assert rig.attachment.settle().settlement.verified


@pytest.mark.parametrize("failure", ["admit", "turn", "continuation"])
def test_publication_failures_return_no_references_and_release_authority(tmp_path: Path, failure: str) -> None:
    rig = Rig(tmp_path, "gondolin", Plan())
    if failure == "admit":
        rig.custody.admit = False
    elif failure == "turn":
        rig.turns.fail = True
    else:
        rig.continuations.fail = True
    result, cleanup = rig.run("publication", ())
    assert result.outcome is TurnOutcome.FAILED
    assert result.output_reference is result.continuation_reference is None
    assert cleanup.disposition is RuntimeCleanupDisposition.CLEAN
    assert [name for name, _ in rig.custody.records][-1] == "release"
    if failure in {"admit", "turn"}:
        assert not rig.turns.values
    if failure != "continuation":
        assert not rig.continuations.values


def test_idempotent_redelivery_and_operation_conflict(tmp_path: Path) -> None:
    rig = Rig(tmp_path, "gondolin", Plan(block=True))
    invocation = rig.invocation("same", ())
    first = rig.adapter.start(invocation)
    assert rig.adapter.start(invocation) is first
    with pytest.raises(RuntimeProtocolError, match="operation-conflict"):
        rig.adapter.start(replace(invocation, observation="different"))
    first.cancel("done")
    first.wait(2)
    first.close()


@pytest.mark.parametrize(
    ("provider", "model", "profile"),
    [("unknown", "x", "gondolin"), ("anthropic", "unknown", "gondolin"), ("anthropic", "claude-sonnet-4-5", "local")],
)
def test_unsupported_provider_model_or_territory(tmp_path: Path, provider: str, model: str, profile: str) -> None:
    (tmp_path / "w").mkdir()
    (tmp_path / "r").mkdir(mode=0o700)
    with pytest.raises(ValueError):
        app.PiApplicationRuntimeConfig(provider, model, profile, tmp_path / "w", tmp_path / "r")


def test_package_source_versions_node_syntax_and_credential_free_probe_shape() -> None:
    assert (
        app.PI_APPLICATION_CODING_AGENT_VERSION
        == app.PI_APPLICATION_AGENT_CORE_VERSION
        == app.PI_APPLICATION_AI_VERSION
        == "0.83.0"
    )
    assert app.PI_APPLICATION_SOURCE_COMMIT == native.PI_SDK_SOURCE_COMMIT
    helper = Path(app.__file__).with_name("pi_application_helper.mjs")
    assert subprocess.run(("node", "--check", str(helper)), capture_output=True, check=False).returncode == 0


@pytest.mark.qualification_installation
def test_exact_helper_core_loop_fake_stream_is_one_turn_delta_only_and_authority_free(tmp_path: Path) -> None:
    prefix = Path("/tmp/petrus-pi-a2-probe")
    root = prefix / "node_modules/@earendil-works/pi-coding-agent"
    node = prefix / "node_modules/node/bin/node"
    if not node.is_file() or not root.is_dir():
        pytest.skip("exact Pi qualification packages required")
    helper = Path(app.__file__).with_name("pi_application_helper.mjs")
    core = root / "node_modules/@earendil-works/pi-agent-core/dist/index.js"
    ai = root / "node_modules/@earendil-works/pi-ai/dist/index.js"
    coding = root / "dist/index.js"
    result = subprocess.run(
        (str(node), str(helper), str(coding), str(core), str(ai), "--test-probe"),
        capture_output=True,
        text=True,
        check=False,
        env={"HOME": str(tmp_path), "PATH": str(Path(node).parent), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report == {
        "type": "test-probe",
        "ok": True,
        "stream_calls": 1,
        "context_ok": True,
        "prior_immutable": True,
        "delta_only": True,
        "network": False,
    }


@pytest.mark.qualification_installation
@pytest.mark.skipif(
    os.environ.get("PETRUS_CV16_PI_APPLICATION_QUALIFY") != "1",
    reason="set PETRUS_CV16_PI_APPLICATION_QUALIFY=1 for exact installed-package probe",
)
def test_exact_installed_application_package_probe(tmp_path: Path) -> None:
    prefix = Path("/tmp/petrus-pi-a2-probe")
    root, cli, node = (
        prefix / "node_modules/@earendil-works/pi-coding-agent",
        prefix / "node_modules/.bin/pi",
        prefix / "node_modules/node/bin/node",
    )
    working, runtime = tmp_path / "working", tmp_path / "runtime"
    working.mkdir()
    runtime.mkdir(mode=0o700)
    custody, continuations, turns = Custody(), Continuations(), Turns()
    adapter = app.PiApplicationRuntimeAdapter(
        app.PiApplicationRuntimeConfig("anthropic", "claude-sonnet-4-5", "gondolin", working, runtime),
        app.PiApplicationContinuationCodec(continuations),
        turns,
        custody,
    )
    result = adapter.probe(cli_path=str(cli), node_path=str(node), package_root=str(root))
    assert result.disposition.value == "ready", result.issues
