from __future__ import annotations

import base64
import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

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
from petrus.agenticus.program.agent_net import (
    AGENT_AS_NET,
    DONE,
    MAX_PROPOSALS,
    MODEL_PHASE_ACTIVITY,
    LoopState,
    ModelResult,
    ModelSettlement,
    StopReason,
    agent_net_guards,
    agent_net_handlers,
    initial_marking,
)
from petrus.agenticus.runtime import pi_model_phase as phase
from petrus.agenticus.runtime.operation import RuntimeProtocolError
from petrus.engine import Engine
from petrus.impetus.history_store import InMemoryHistoryStore
from petrus.motus.activity import ActivityInvocation
from petrus.motus.dispatch import InlineDispatch

KEY = b"credential-canary"
USAGE = {
    "input": 1,
    "output": 2,
    "cacheRead": 0,
    "cacheWrite": 0,
    "totalTokens": 3,
    "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "total": 0},
}


def assistant(
    stop: StopReason | str = StopReason.STOP,
    content: list[dict[str, object]] | None = None,
    **extra: object,
) -> dict[str, object]:
    return {
        "role": "assistant",
        "content": content if content is not None else [{"type": "text", "text": "private-model-output"}],
        "api": "anthropic-messages",
        "provider": "anthropic",
        "model": "claude-sonnet-4-5",
        "usage": USAGE,
        "stopReason": stop.value if isinstance(stop, StopReason) else stop,
        "timestamp": 0,
        **extra,
    }


def encoded(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()


def state(
    *,
    phase_ordinal: int = 1,
    output_ref: str | None = None,
    continuation_ref: str | None = None,
    results: tuple[ModelResult, ...] = (),
) -> LoopState:
    return LoopState(
        "episode",
        "turn",
        phase_ordinal,
        4,
        0,
        8,
        output_ref,
        continuation_ref,
        1,
        ("workspace_read", "workspace_test"),
        results,
    )


class Home:
    def read(self) -> bytes:
        return KEY


class Custody:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.admit = True
        self.clean = True
        self.release_raises = False
        self.mode = LeaseMode.READ
        self.authority_epoch = 3
        self.base_version = 4

    def materialize(self, connection_id, host_id, *, mode, ttl, operation_id):
        self.events.append("materialize")
        assert mode is LeaseMode.READ and ttl > 0
        return Materialization(
            AttachmentFence("credential", "lease", connection_id, host_id, 1, self.authority_epoch, self.base_version),
            self.mode,
            time.monotonic() + ttl,
            cast(MaterializedState, Home()),
        )

    def admit_result(self, fence, *, operation_id):
        self.events.append("admit")
        return AdmissionResult(operation_id, "result", fence.attachment_id if self.admit else "wrong")

    def release(self, materialization, *, operation_id):
        self.events.append("release")
        if self.release_raises:
            raise RuntimeError("private release diagnostic")
        return ReleaseResult(
            operation_id,
            CleanupEvidence(
                materialization.fence.attachment_id,
                self.clean,
                False,
                len(KEY),
                security_violation=not self.clean,
            ),
        )


class Operations:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.continuations: dict[str, phase.PiModelPhaseContinuationPayloadV1] = {}
        self.publications: dict[
            str, tuple[phase.PiModelPhaseOutputPayloadV1, phase.PiModelPhaseContinuationPayloadV1]
        ] = {}
        self.load_raises = False
        self.publish_raises = False

    def load_continuation(self, reference):
        self.events.append("load")
        if self.load_raises:
            raise RuntimeError("private load diagnostic")
        return self.continuations[reference]

    def publish(self, operation_id, output, continuation):
        self.events.append("publish")
        if self.publish_raises:
            raise RuntimeError("private publication diagnostic")
        self.publications[operation_id] = (output, continuation)
        return phase.PiModelPhasePublication(f"output-{operation_id}", f"continuation-{operation_id}")


@dataclass
class ClientPlan:
    final: dict[str, object]
    clean: bool = True
    error: str | None = None
    candidate: phase._Candidate | None = None


class Client:
    def __init__(self, plan: ClientPlan, events: list[str], private_root: Path) -> None:
        self.plan = plan
        self.events = events
        self.private_root = private_root
        self.frame: dict[str, object] | None = None

    def run(self, frame, timeout, heartbeat):
        self.events.append("run")
        self.frame = frame
        assert timeout > 0 and self.private_root.is_dir()
        heartbeat()
        if self.plan.error:
            raise RuntimeProtocolError(self.plan.error)
        if self.plan.candidate is not None:
            return self.plan.candidate
        prior = json.loads(base64.b64decode(cast(str, frame["transcript"])))
        messages = list(prior)
        if frame["observation"] is not None:
            messages.append(
                {"role": "user", "content": [{"type": "text", "text": frame["observation"]}], "timestamp": 0}
            )
        for item in frame["results"]:
            messages.append(
                {
                    "role": "toolResult",
                    "toolCallId": item["id"],
                    "toolName": item["method"],
                    "content": [{"type": "text", "text": json.dumps(item["result"], separators=(",", ":"))}],
                    "isError": not item["result"]["ok"],
                    "timestamp": 0,
                }
            )
        messages.append(self.plan.final)
        return phase._Candidate(encoded(self.plan.final), encoded(messages))

    def close(self):
        self.events.append("client-close")
        return self.plan.clean


class Factory:
    def __init__(self, plan: ClientPlan, events: list[str]) -> None:
        self.plan = plan
        self.events = events
        self.clients: list[Client] = []

    def create(self, **kwargs):
        self.events.append("client-create")
        client = Client(self.plan, self.events, kwargs["private_root"])
        self.clients.append(client)
        return client


class RealFactory:
    def create(self, **kwargs):
        return phase._SubprocessFactory().create(**kwargs)


class Rig:
    def __init__(
        self,
        tmp_path: Path,
        final: dict[str, object] | None = None,
        *,
        observation: str = "Continue.",
    ) -> None:
        self.events: list[str] = []
        self.runtime_root = tmp_path / "runtime"
        self.runtime_root.mkdir(parents=True, mode=0o700)
        self.config = phase.PiModelPhaseConfig(
            "anthropic",
            "claude-sonnet-4-5",
            "host",
            self.runtime_root,
            "episode",
            "turn",
            observation=observation,
            timeout=1,
        )
        self.connection = ConnectionView(
            ConnectionIdentity("connection", "anthropic", "account", "api-key"),
            ConnectionStatus.READY,
            3,
            4,
            None,
        )
        self.custody = Custody(self.events)
        self.operations = Operations(self.events)
        self.plan = ClientPlan(final or assistant())
        self.factory = Factory(self.plan, self.events)
        self.adapter = phase.PiModelPhaseAdapter(
            self.config,
            self.connection,
            self.custody,
            self.operations,
            sdk_entrypoint="/fake/pi/index.js",
            client_factory=self.factory,
        )

    def invoke(self, value: LoopState, *, identity: str = "operation") -> ModelSettlement:
        result = self.adapter(
            ActivityInvocation(MODEL_PHASE_ACTIVITY, input=value.to_data(), idempotency=identity),
            context=cast(object, SimpleNamespace(attempt_id="attempt", heartbeat=lambda **_: None)),
        )
        return ModelSettlement.from_data(result)


def test_payloads_publication_and_config_are_strict_and_bounded(tmp_path: Path) -> None:
    assert phase.PiModelPhaseContinuationPayloadV1(b"[]").schema_version == 1
    assert phase.PiModelPhaseOutputPayloadV1(b"{}").schema_version == 1
    assert phase.PiModelPhasePublication("output", "continuation").output_reference == "output"
    for raw in (b"[NaN]", b'[{"x":1,"x":2}]', b"null"):
        with pytest.raises(ValueError):
            phase.PiModelPhaseContinuationPayloadV1(raw)
    with pytest.raises(ValueError):
        phase.PiModelPhaseOutputPayloadV1(b"[]")
    with pytest.raises(ValueError):
        phase.PiModelPhasePublication("", "continuation")
    runtime = tmp_path / "config"
    runtime.mkdir(mode=0o700)
    with pytest.raises(ValueError, match="direct API-key catalog"):
        phase.PiModelPhaseConfig("unknown", "model", "host", runtime, "episode", "turn")
    with pytest.raises(ValueError, match="positive and finite"):
        phase.PiModelPhaseConfig("anthropic", "claude-sonnet-4-5", "host", runtime, "episode", "turn", timeout=True)
    runtime.chmod(0o755)
    with pytest.raises(ValueError, match="mode-0700"):
        phase.PiModelPhaseConfig("anthropic", "claude-sonnet-4-5", "host", runtime, "episode", "turn")
    runtime.chmod(0o700)
    assert (
        "\n"
        in phase.PiModelPhaseConfig(
            "anthropic", "claude-sonnet-4-5", "host", runtime, "episode", "turn", observation="one\ntwo"
        ).observation
    )
    with pytest.raises(ValueError, match="observation is invalid"):
        phase.PiModelPhaseConfig(
            "anthropic", "claude-sonnet-4-5", "host", runtime, "episode", "turn", observation="bad\0value"
        )


@pytest.mark.parametrize("stop", list(StopReason))
def test_candidate_preserves_stop_optional_private_fields_and_source_order(stop: StopReason) -> None:
    final = assistant(
        stop,
        [
            {
                "type": "toolCall",
                "id": "first",
                "name": "workspace_read",
                "arguments": {"path": "a"},
                "thoughtSignature": "private-signature",
            },
            {"type": "text", "text": "between"},
            {"type": "toolCall", "id": "second", "name": "workspace_test", "arguments": {}},
        ],
        errorMessage="private-provider-diagnostic",
        responseId="private-response",
    )
    user = {"role": "user", "content": [{"type": "text", "text": "Continue."}], "timestamp": 0}
    _, _, proposals, observed = phase._validate_candidate(
        b"[]",
        phase._Candidate(encoded(final), encoded([user, final])),
        state(),
        "Continue.",
        "anthropic",
        "claude-sonnet-4-5",
    )
    assert observed is stop
    assert [proposal.id for proposal in proposals] == ["first", "second"]


@pytest.mark.parametrize("stop", ["pending", "deferred", "foreign"])
def test_candidate_rejects_unsupported_terminal_stops(stop: str) -> None:
    final = assistant(stop)
    user = {"role": "user", "content": [{"type": "text", "text": "Continue."}], "timestamp": 0}
    with pytest.raises(RuntimeProtocolError, match="malformed-complete"):
        phase._validate_candidate(
            b"[]",
            phase._Candidate(encoded(final), encoded([user, final])),
            state(),
            "Continue.",
            "anthropic",
            "claude-sonnet-4-5",
        )


def test_success_cleans_and_releases_before_atomic_private_publication(tmp_path: Path) -> None:
    rig = Rig(
        tmp_path,
        assistant(
            StopReason.TOOL_USE,
            [
                {"type": "text", "text": "private-model-output"},
                {"type": "toolCall", "id": "call", "name": "workspace_read", "arguments": {"path": "a"}},
            ],
        ),
    )
    settlement = rig.invoke(state())
    assert settlement.stop is StopReason.TOOL_USE
    assert settlement.output_ref == "output-operation"
    assert settlement.continuation_ref == "continuation-operation"
    assert [proposal.id for proposal in settlement.proposals] == ["call"]
    assert rig.events == ["materialize", "client-create", "run", "client-close", "admit", "release", "publish"]
    assert not tuple(rig.runtime_root.iterdir())
    output, continuation = rig.operations.publications["operation"]
    assert b"private-model-output" in output.assistant_json
    assert continuation.transcript_json.endswith(b"]")
    rendered = json.dumps(settlement.to_data())
    assert all(value not in rendered for value in ("credential-canary", "private-model-output", "api_key"))


def test_phase_one_resume_adds_observation_after_prior_continuation(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    prior = [assistant()]
    rig.operations.continuations["prior"] = phase.PiModelPhaseContinuationPayloadV1(encoded(prior))
    rig.invoke(state(output_ref="old-output", continuation_ref="prior"))
    frame = rig.factory.clients[0].frame
    assert frame is not None and frame["observation"] == "Continue."
    transcript = json.loads(rig.operations.publications["operation"][1].transcript_json)
    assert transcript[:1] == prior
    assert [message["role"] for message in transcript[1:]] == ["user", "assistant"]


def test_phase_two_injects_exact_ordered_results_without_observation(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    prior_assistant = assistant(
        StopReason.TOOL_USE,
        [
            {"type": "toolCall", "id": "one", "name": "workspace_read", "arguments": {"path": "a"}},
            {"type": "toolCall", "id": "two", "name": "workspace_test", "arguments": {}},
        ],
    )
    rig.operations.continuations["prior"] = phase.PiModelPhaseContinuationPayloadV1(encoded([prior_assistant]))
    results = (
        ModelResult("one", True, {"content": "a"}, None),
        ModelResult("two", False, None, {"category": "unknown", "detail": "bounded failure"}),
    )
    rig.invoke(state(phase_ordinal=2, output_ref="old-output", continuation_ref="prior", results=results))
    frame = rig.factory.clients[0].frame
    assert frame is not None and frame["observation"] is None
    assert [item["id"] for item in frame["results"]] == ["one", "two"]
    assert [item["method"] for item in frame["results"]] == ["workspace_read", "workspace_test"]
    transcript = json.loads(rig.operations.publications["operation"][1].transcript_json)
    assert [message["role"] for message in transcript] == ["assistant", "toolResult", "toolResult", "assistant"]
    assert set(json.loads(transcript[1]["content"][0]["text"])) == {"version", "ok", "data", "error"}
    assert all("attachment" not in json.dumps(message) for message in transcript[1:3])


def test_result_identity_mismatch_fails_before_authority_use(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    prior_assistant = assistant(
        StopReason.TOOL_USE,
        [{"type": "toolCall", "id": "expected", "name": "workspace_read", "arguments": {"path": "a"}}],
    )
    rig.operations.continuations["prior"] = phase.PiModelPhaseContinuationPayloadV1(encoded([prior_assistant]))
    with pytest.raises(RuntimeProtocolError, match="result-mismatch"):
        rig.invoke(
            state(
                phase_ordinal=2,
                output_ref="old-output",
                continuation_ref="prior",
                results=(ModelResult("wrong", True, {"content": "a"}, None),),
            )
        )
    assert rig.events == ["load"]


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        ("client", "helper-protocol"),
        ("client-clean", "cleanup-unverified"),
        ("admit", "custody-admission-mismatch"),
        ("release", "cleanup-unverified"),
        ("release-raises", "cleanup-unverified"),
        ("publish", "runtime-failed"),
    ],
)
def test_failures_release_authority_and_publish_nothing(tmp_path: Path, failure: str, code: str) -> None:
    rig = Rig(tmp_path)
    if failure == "client":
        rig.plan.error = "helper-protocol"
    elif failure == "client-clean":
        rig.plan.clean = False
    elif failure == "admit":
        rig.custody.admit = False
    elif failure == "release":
        rig.custody.clean = False
    elif failure == "release-raises":
        rig.custody.release_raises = True
    else:
        rig.operations.publish_raises = True
    with pytest.raises(RuntimeProtocolError, match=code):
        rig.invoke(state())
    assert "release" in rig.events
    assert not rig.operations.publications
    assert not tuple(rig.runtime_root.iterdir())


@pytest.mark.parametrize("mismatch", ["mode", "authority", "version"])
def test_materialization_fence_mismatch_releases_without_provider_use(tmp_path: Path, mismatch: str) -> None:
    rig = Rig(tmp_path)
    if mismatch == "mode":
        rig.custody.mode = LeaseMode.REFRESH
        code = "custody-materialization-mismatch"
    elif mismatch == "authority":
        rig.custody.authority_epoch += 1
        code = "custody-state-mismatch"
    else:
        rig.custody.base_version += 1
        code = "custody-state-mismatch"
    with pytest.raises(RuntimeProtocolError, match=code):
        rig.invoke(state())
    assert rig.events == ["materialize", "release"]
    assert not rig.operations.publications


@pytest.mark.parametrize("status", [ConnectionStatus.REVOKED, ConnectionStatus.REAUTHORIZATION_REQUIRED])
def test_not_ready_connection_is_rejected_at_construction(tmp_path: Path, status: ConnectionStatus) -> None:
    rig = Rig(tmp_path)
    connection = ConnectionView(rig.connection.identity, status, 3, 4, None)
    with pytest.raises(ValueError, match="ready api-key"):
        phase.PiModelPhaseAdapter(
            rig.config,
            connection,
            rig.custody,
            rig.operations,
            sdk_entrypoint="/fake/pi/index.js",
            client_factory=rig.factory,
        )


def test_private_load_failure_and_state_mismatch_are_sanitized_pre_authority(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.operations.load_raises = True
    with pytest.raises(RuntimeProtocolError, match="continuation-load-failed") as error:
        rig.invoke(state(output_ref="old-output", continuation_ref="missing"))
    assert "private load diagnostic" not in str(error.value)
    assert rig.events == ["load"]
    bad = state()
    object.__setattr__(rig.config, "episode_id", "other")
    with pytest.raises(RuntimeProtocolError, match="state-mismatch"):
        rig.invoke(bad)
    assert rig.events == ["load"]


def test_stale_activity_claim_rejects_before_authority(tmp_path: Path) -> None:
    rig = Rig(tmp_path)

    def stale(**_: object) -> None:
        raise RuntimeError("private claim diagnostic")

    with pytest.raises(RuntimeProtocolError, match="activity-stale") as error:
        rig.adapter(
            ActivityInvocation(MODEL_PHASE_ACTIVITY, input=state().to_data(), idempotency="operation"),
            context=cast(object, SimpleNamespace(attempt_id="attempt", heartbeat=stale)),
        )
    assert "private claim diagnostic" not in str(error.value)
    assert rig.events == []


def test_malformed_candidate_and_proposal_overflow_publish_nothing(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.plan.candidate = phase._Candidate(encoded(assistant()), b"[]")
    with pytest.raises(RuntimeProtocolError, match="transcript-mismatch"):
        rig.invoke(state())
    assert not rig.operations.publications
    calls = [
        {"type": "toolCall", "id": f"call-{index}", "name": "workspace_test", "arguments": {}}
        for index in range(MAX_PROPOSALS + 1)
    ]
    final = assistant(StopReason.TOOL_USE, calls)
    user = {"role": "user", "content": [{"type": "text", "text": "Continue."}], "timestamp": 0}
    with pytest.raises(RuntimeProtocolError, match="proposal-overflow"):
        phase._validate_candidate(
            b"[]",
            phase._Candidate(encoded(final), encoded([user, final])),
            state(),
            "Continue.",
            "anthropic",
            "claude-sonnet-4-5",
        )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update(provider="wrong"),
        lambda value: value.update(timestamp=float("inf")),
        lambda value: value.update(usage={"input": 1}),
        lambda value: value.update(content=[{"type": "foreign", "text": "x"}]),
        lambda value: value.update(content=[{"type": "text", "text": "x", "foreign": True}]),
    ],
)
def test_candidate_rejects_malformed_public_assistant(mutation) -> None:
    final = assistant()
    mutation(final)
    user = {"role": "user", "content": [{"type": "text", "text": "Continue."}], "timestamp": 0}
    with pytest.raises(RuntimeProtocolError, match="malformed-complete"):
        phase._validate_candidate(
            b"[]",
            phase._Candidate(encoded(final), encoded([user, final])),
            state(),
            "Continue.",
            "anthropic",
            "claude-sonnet-4-5",
        )


def test_duplicate_tool_call_identity_is_rejected_before_publication(tmp_path: Path) -> None:
    calls = [
        {"type": "toolCall", "id": "duplicate", "name": "workspace_test", "arguments": {}},
        {"type": "toolCall", "id": "duplicate", "name": "workspace_test", "arguments": {}},
    ]
    rig = Rig(tmp_path, assistant(StopReason.TOOL_USE, calls))
    with pytest.raises(RuntimeProtocolError, match="malformed-proposal"):
        rig.invoke(state())
    assert not rig.operations.publications


@pytest.mark.parametrize(
    ("body", "code"),
    [
        (
            'process.stdout.write(\'{"type":"complete","assistant":"e30=","assistant":"e30=","transcript":"W10="}\\n\')',
            "malformed-frame",
        ),
        (
            'process.stdout.write(\'{"type":"complete","assistant":"e30=","transcript":"W10="}\\n'
            '{"type":"complete","assistant":"e30=","transcript":"W10="}\\n\')',
            "helper-protocol",
        ),
        (
            'process.stdout.write(\'{"type":"complete","assistant":"e30","transcript":"W10="}\\n\')',
            "malformed-complete",
        ),
    ],
)
def test_subprocess_rejects_duplicate_post_terminal_and_noncanonical_frames(
    tmp_path: Path, body: str, code: str
) -> None:
    node = shutil.which("node")
    assert node is not None
    helper = tmp_path / "bad.mjs"
    helper.write_text(f"process.stdin.resume();process.stdin.on('end',()=>{{{body};}});\n")
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    client = phase._SubprocessClient(node=node, helper=helper, entrypoint="/unused", private_root=root)
    with pytest.raises(RuntimeProtocolError, match=code):
        client.run({}, 1, lambda: None)
    assert client.close()


def test_subprocess_rejects_a_relative_node_before_launch(tmp_path: Path) -> None:
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    with pytest.raises(RuntimeProtocolError, match="runtime-not-ready"):
        phase._SubprocessClient(
            node="node",
            helper=tmp_path / "helper.mjs",
            entrypoint="/unused",
            private_root=root,
        )


def test_subprocess_deadline_kills_the_helper_group_and_discards_stderr(tmp_path: Path) -> None:
    node = shutil.which("node")
    assert node is not None
    helper = tmp_path / "slow.mjs"
    helper.write_text("process.stderr.write('PRIVATE PROVIDER DIAGNOSTIC');setTimeout(()=>{},10000);\n")
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    client = phase._SubprocessClient(node=node, helper=helper, entrypoint="/unused", private_root=root)
    with pytest.raises(RuntimeProtocolError, match="deadline-exceeded") as error:
        client.run({"blob": "x" * 1_000_000}, 0.03, lambda: None)
    assert "PRIVATE" not in str(error.value)
    assert client.close() and client.process.poll() is not None


def test_subprocess_heartbeat_refusal_stops_before_the_wall_deadline(tmp_path: Path) -> None:
    node = shutil.which("node")
    assert node is not None
    helper = tmp_path / "slow.mjs"
    helper.write_text("process.stdin.resume();setTimeout(()=>{},10000);\n")
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    client = phase._SubprocessClient(node=node, helper=helper, entrypoint="/unused", private_root=root)

    def stale() -> None:
        raise RuntimeError("private claim diagnostic")

    with pytest.raises(RuntimeProtocolError, match="activity-stale") as error:
        client.run({}, 0.1, stale)
    assert "private claim diagnostic" not in str(error.value)
    assert client.close()


def write_fake_coding(path: Path) -> Path:
    entry = path / "coding.mjs"
    entry.write_text(
        """
export const convertToLlm=messages=>messages;
export class ModelRuntime {
  static async create(options){if(options.modelsPath!==null||options.allowModelNetwork!==false)throw Error('shape');return new ModelRuntime();}
  async setRuntimeApiKey(provider,key,options){if(provider!=='anthropic'||!key||options?.allowNetwork!==false)throw Error('key');}
  getModel(provider,id){return {provider,id};}
  streamSimple(_model,context){
    if(context.tools.some(tool=>Object.hasOwn(tool,'execute')))throw Error('tool-executor');
    const roles=context.messages.map(message=>message.role).join(',');const prompt=context.messages.at(-1).content[0].text.length;
    const message={role:'assistant',content:[{type:'text',text:`calls=1;roles=${roles};declarations=${context.tools.length};prompt=${prompt}`}],api:'anthropic-messages',provider:'anthropic',model:'claude-sonnet-4-5',usage:{input:0,output:0,cacheRead:0,cacheWrite:0,totalTokens:0,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}},stopReason:'stop',timestamp:0};
    return {result:async()=>message};
  }
}
"""
    )
    return entry


def test_real_helper_runs_one_public_stream_with_declarations_and_no_tool_executor(tmp_path: Path) -> None:
    node = shutil.which("node")
    assert node is not None
    rig = Rig(tmp_path)
    rig.adapter.node = node
    rig.adapter.sdk_entrypoint = str(write_fake_coding(tmp_path))
    rig.adapter.factory = RealFactory()
    settlement = rig.invoke(state())
    assert settlement.stop is StopReason.STOP
    output = rig.operations.publications["operation"][0]
    private = json.loads(output.assistant_json)
    assert private["content"][0]["text"] == "calls=1;roles=user;declarations=5;prompt=9"
    helper = Path(phase.__file__).with_name("pi_model_phase_helper.mjs")
    source = helper.read_text()
    assert all(name not in source for name in ("runAgentLoop", "AgentSession", "shouldStopAfterTurn"))
    assert ".execute" not in source


def test_real_helper_accepts_bounded_multiline_observation(tmp_path: Path) -> None:
    node = shutil.which("node")
    assert node is not None
    observation = "line one\n" + "x" * 300
    rig = Rig(tmp_path, observation=observation)
    rig.adapter.node = node
    rig.adapter.sdk_entrypoint = str(write_fake_coding(tmp_path))
    rig.adapter.factory = RealFactory()
    rig.invoke(state())
    private = json.loads(rig.operations.publications["operation"][0].assistant_json)
    assert private["content"][0]["text"].endswith(f"prompt={len(observation)}")


def test_real_subprocess_requires_the_exact_installed_probe_before_authority(tmp_path: Path) -> None:
    node = shutil.which("node")
    assert node is not None
    rig = Rig(tmp_path)
    rig.adapter.node = node
    rig.adapter.sdk_entrypoint = str(write_fake_coding(tmp_path))
    rig.adapter.factory = phase._SubprocessFactory()
    with pytest.raises(RuntimeProtocolError, match="runtime-not-ready"):
        rig.invoke(state())
    assert rig.events == []


def test_activity_adapter_drives_the_real_static_net_to_completion(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    history = InMemoryHistoryStore()
    engine = Engine.create(
        AGENT_AS_NET,
        "model-phase-net",
        history=history,
        dispatch=InlineDispatch({MODEL_PHASE_ACTIVITY: rig.adapter}),
        marking=initial_marking(state()),
        handlers=agent_net_handlers(),
        guards=agent_net_guards(),
    )
    while engine.advance().ready:
        pass
    assert engine.marking.place(DONE)[0].data["code"] == "completed"
    assert len(rig.operations.publications) == 1


def test_helper_syntax_and_exact_hands_bounds() -> None:
    helper = Path(phase.__file__).with_name("pi_model_phase_helper.mjs")
    assert subprocess.run(("node", "--check", str(helper)), capture_output=True, check=False).returncode == 0
    source = helper.read_text()
    assert "maxItems:4" in source and "maxLength:64" in source
    assert "maxLength:8" in source and "maxLength:1024" in source


@pytest.mark.qualification_installation
def test_exact_installed_model_phase_probe(tmp_path: Path) -> None:
    helper = Path(phase.__file__).with_name("pi_model_phase_helper.mjs")
    prefix = Path("/tmp/petrus-pi-a2-probe")
    root = prefix / "node_modules/@earendil-works/pi-coding-agent"
    node = prefix / "node_modules/node/bin/node"
    if not node.is_file() or not root.is_dir():
        pytest.skip("exact Pi qualification packages required")
    rig = Rig(tmp_path / "probe")
    rig.adapter.node = str(node)
    assert rig.adapter.probe(root)
    assert Path(rig.adapter.node).is_absolute()
    run = subprocess.run(
        (str(node), str(helper), str(root / "dist/index.js"), "--test-probe"),
        capture_output=True,
        text=True,
        check=False,
        env={"HOME": str(tmp_path), "PATH": str(node.parent), "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
    )
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout) == {
        "type": "test-probe",
        "ok": True,
        "stream_calls": 1,
        "convert": True,
        "tool_execute": False,
        "network": False,
        "complete": True,
    }
