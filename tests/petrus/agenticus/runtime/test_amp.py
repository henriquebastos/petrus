"""Amp A1 provider-managed runtime conformance without provider use."""

from __future__ import annotations

import importlib.metadata
import json
import subprocess
import sys
import threading
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

import petrus.agenticus.runtime.amp as amp_module
from petrus.agenticus.attachment.episode import EpisodeAttachment
from petrus.agenticus.catalog.descriptor import CapabilityDescriptor, DescriptorIdentity, DescriptorKind
from petrus.agenticus.catalog.resolution import ResolutionSnapshot
from petrus.agenticus.connection.custody import ConnectionIdentity, ConnectionStatus, ConnectionView
from petrus.agenticus.runtime.amp import (
    AMP_CLI_VERSION,
    AMP_CONNECTION_CAPABILITIES,
    AMP_CONTINUATION_CAPABILITIES,
    AMP_CONTINUATION_DESCRIPTOR,
    AMP_PROGRAM,
    AMP_PROGRAM_CAPABILITIES,
    AMP_PROVIDER_MANAGED_HANDS,
    AMP_PROVIDER_MANAGED_TERRITORY,
    AMP_SDK_VERSION,
    AmpContinuationCodec,
    AmpContinuationPayloadV1,
    AmpProviderManagedBinding,
    AmpRuntimeAdapter,
    AmpRuntimeConfig,
    AmpRuntimeInvocation,
)
from petrus.agenticus.runtime.installation import ProbeDisposition
from petrus.agenticus.runtime.operation import RuntimeCleanupDisposition, RuntimeProtocolError
from petrus.agenticus.runtime.profiles import AMP_A1
from petrus.agenticus.thread.continuation import Continuation, ContinuationState
from petrus.agenticus.thread.identity import ContinuationId, EpisodeId, ThreadId, TurnId
from petrus.agenticus.thread.lifecycle import CancellationDisposition, TurnOutcome

THREAD_ID = "T-11111111-1111-1111-1111-111111111111"
OTHER_THREAD_ID = "T-22222222-2222-2222-2222-222222222222"
PROMPT_CANARY = "prompt-canary-never-render"
ERROR_CANARY = "provider-error-canary-never-render"
HOST_FENCED_EFFECT = CapabilityDescriptor(
    DescriptorIdentity(DescriptorKind.EFFECT, "host.fenced", 1),
    frozenset({"effect.host-fenced"}),
)


@dataclass(frozen=True)
class Event:
    values: dict[str, object]

    def __getattr__(self, name: str) -> object:
        try:
            return self.values[name]
        except KeyError as error:
            raise AttributeError(name) from error

    def model_dump_json(self) -> str:
        return json.dumps(self.values, separators=(",", ":"))


def event(**values: object) -> Event:
    return Event(values)


def successful_events(thread_id: str = THREAD_ID, text: str = "safe result") -> tuple[Event, ...]:
    return (
        event(type="system", subtype="init", session_id=thread_id),
        event(type="assistant", session_id=thread_id, message={"content": [{"type": "text", "text": text}]}),
        event(
            type="result",
            subtype="success",
            session_id=thread_id,
            is_error=False,
            result=text,
        ),
    )


class Continuations:
    def __init__(self) -> None:
        self.values: dict[str, AmpContinuationPayloadV1] = {}
        self.operations: dict[str, str] = {}

    def store(self, operation_id: str, payload: AmpContinuationPayloadV1) -> str:
        reference = f"amp-continuation-{operation_id}"
        existing = self.values.get(reference)
        if existing is not None and existing != payload:
            raise RuntimeError("conflicting synthetic Continuation")
        self.values[reference] = payload
        self.operations[operation_id] = reference
        return reference

    def load(self, state_reference: str) -> AmpContinuationPayloadV1:
        return self.values[state_reference]


class Turns:
    def __init__(self) -> None:
        self.values: dict[str, tuple[str, str]] = {}

    def store_turn(self, operation_id: str, thread_id: str, final_text: str) -> str:
        reference = f"amp-turn-{operation_id}"
        value = (thread_id, final_text)
        existing = self.values.get(reference)
        if existing is not None and existing != value:
            raise RuntimeError("conflicting synthetic Turn")
        self.values[reference] = value
        return reference


@dataclass
class Rig:
    adapter: AmpRuntimeAdapter
    continuations: Continuations
    turns: Turns
    calls: list[tuple[str, dict[str, object]]]


def connection() -> ConnectionView:
    return ConnectionView(
        ConnectionIdentity("amp-connection", "amp", "safe-account-fingerprint", "platform-managed"),
        ConnectionStatus.READY,
        3,
        4,
        None,
    )


def snapshot(*, runtime: CapabilityDescriptor = AMP_A1) -> ResolutionSnapshot:
    return ResolutionSnapshot(
        1,
        (
            runtime,
            AMP_CONNECTION_CAPABILITIES,
            AMP_PROGRAM_CAPABILITIES,
            AMP_PROVIDER_MANAGED_HANDS,
            AMP_PROVIDER_MANAGED_TERRITORY,
            AMP_CONTINUATION_CAPABILITIES,
            HOST_FENCED_EFFECT,
        ),
    )


def attachment(
    episode_id: str,
    *,
    binding: AmpProviderManagedBinding | None = None,
    selected: ResolutionSnapshot | None = None,
) -> EpisodeAttachment:
    return EpisodeAttachment(
        episode_id=EpisodeId(episode_id),
        snapshot=selected or snapshot(),
        binding=binding or AmpProviderManagedBinding(),
        attachment_id=f"attachment-{episode_id}",
        deadline=100,
        clock=lambda: 1,
    )


def invocation(
    episode_id: str = "episode-1",
    turn_id: str = "turn-1",
    operation_id: str = "operation-1",
    *,
    attached: EpisodeAttachment | None = None,
    continuation: Continuation | None = None,
    prompt: str = PROMPT_CANARY,
) -> AmpRuntimeInvocation:
    return AmpRuntimeInvocation(
        operation_id,
        EpisodeId(episode_id),
        TurnId(turn_id),
        prompt,
        connection(),
        attached or attachment(episode_id),
        continuation,
    )


def continuation(reference: str, *, descriptor=AMP_CONTINUATION_DESCRIPTOR) -> Continuation:
    return Continuation(
        ContinuationId("continuation-1"),
        ThreadId("agenticus-thread-1"),
        descriptor,
        reference,
        ContinuationState.IN_USE,
    )


def ready_probe(monkeypatch: pytest.MonkeyPatch, adapter: AmpRuntimeAdapter) -> None:
    monkeypatch.setattr(amp_module, "_resolve_amp_cli", lambda: ("/qualified/amp",))
    monkeypatch.setattr(amp_module.importlib.metadata, "version", lambda name: AMP_SDK_VERSION)

    def run(argv, **kwargs):
        if argv[-1] == "--version":
            return SimpleNamespace(stdout=f"{AMP_CLI_VERSION} (released safely)\n")
        return SimpleNamespace(stdout="--orb-execute --project --stream-json")

    monkeypatch.setattr(amp_module.subprocess, "run", run)

    class AmpOptions:
        model_fields = {"executor": object(), "project": object(), "continue_thread": object()}

    async def execute(prompt, options):
        yield prompt, options

    fake_sdk = SimpleNamespace(AmpOptions=AmpOptions, execute=execute)
    original_import = amp_module.importlib.import_module
    monkeypatch.setattr(
        amp_module.importlib,
        "import_module",
        lambda name: fake_sdk if name == "amp_sdk" else original_import(name),
    )
    assert adapter.probe().disposition is ProbeDisposition.READY


def rig(monkeypatch: pytest.MonkeyPatch, events: tuple[Event, ...] | None = None) -> Rig:
    calls: list[tuple[str, dict[str, object]]] = []

    async def execute(prompt: str, options):
        calls.append((prompt, dict(options)))
        for item in events or successful_events():
            yield item

    continuations = Continuations()
    turns = Turns()
    adapter = AmpRuntimeAdapter(
        AmpRuntimeConfig("henriquebastos/petrus"),
        AmpContinuationCodec(continuations),
        turns,
        sdk_execute=execute,
        clock=lambda: 1,
    )
    ready_probe(monkeypatch, adapter)
    return Rig(adapter, continuations, turns, calls)


def test_descriptors_freeze_provider_owned_amp_native_profile() -> None:
    assert AMP_PROGRAM.ownership.value == "provider-owned"
    assert AMP_PROGRAM.accepts_fresh_start
    assert AMP_PROGRAM.produced_continuation == AMP_CONTINUATION_DESCRIPTOR.identity
    assert AMP_PROGRAM.accepted_continuations[0].identity == AMP_CONTINUATION_DESCRIPTOR.identity
    assert not AMP_PROGRAM.owns_steering and not AMP_PROGRAM.owns_evaluation
    assert AMP_A1.offers == frozenset({"archetype.a1", "loop.provider-owned", "topology.provider-managed"})


def test_continuation_payload_and_codec_are_exact_and_opaque() -> None:
    operations = Continuations()
    codec = AmpContinuationCodec(operations)
    payload = AmpContinuationPayloadV1(THREAD_ID)
    reference = codec.store("operation-1", payload)
    value = continuation(reference)

    assert AmpContinuationPayloadV1.from_data(payload.to_data()) == payload
    assert codec.load(value) == payload
    assert THREAD_ID not in repr(value)
    with pytest.raises(ValueError, match="exact versioned"):
        AmpContinuationPayloadV1.from_data({"schema_version": 1, "thread_id": THREAD_ID, "project": "foreign"})
    with pytest.raises(ValueError, match="T-prefixed"):
        AmpContinuationPayloadV1("session-1")


def test_config_and_invocation_hide_prompt_and_reject_implicit_profile_changes() -> None:
    config = AmpRuntimeConfig("henriquebastos/petrus")
    requested = invocation()

    assert PROMPT_CANARY not in repr(requested)
    assert config.sdk_version == AMP_SDK_VERSION and config.cli_version == AMP_CLI_VERSION
    with pytest.raises(ValueError, match="built-in mode"):
        AmpRuntimeConfig("henriquebastos/petrus", mode="custom-fallback")
    with pytest.raises(ValueError, match="exact qualified"):
        AmpRuntimeConfig("henriquebastos/petrus", sdk_version="latest")
    with pytest.raises(ValueError, match="platform-managed"):
        AmpRuntimeInvocation(
            "operation-1",
            EpisodeId("episode-1"),
            TurnId("turn-1"),
            "safe",
            ConnectionView(
                ConnectionIdentity("connection", "openai", "fingerprint", "api-key"),
                ConnectionStatus.READY,
                1,
                1,
                None,
            ),
            attachment("episode-1"),
        )


def test_probe_requires_exact_sdk_cli_and_orb_protocol_before_start(monkeypatch: pytest.MonkeyPatch) -> None:
    current = rig(monkeypatch)
    result = current.adapter.probe()

    assert result.disposition is ProbeDisposition.READY
    assert result.installation is not None
    assert tuple(component.version for component in result.installation.components) == (
        AMP_CLI_VERSION,
        AMP_SDK_VERSION,
    )
    assert result.installation.capabilities == frozenset(
        {"runtime.cancel", "runtime.continue", "runtime.orb", "runtime.provider-managed"}
    )

    monkeypatch.setattr(amp_module.importlib.metadata, "version", lambda name: "0.1.6")
    mismatch = current.adapter.probe()
    assert mismatch.disposition is ProbeDisposition.INCOMPATIBLE
    assert mismatch.issues[0].code == "version-mismatch"
    with pytest.raises(RuntimeProtocolError, match="runtime-not-ready"):
        current.adapter.start(invocation())


def test_probe_reports_absent_sdk_without_importing_or_materializing(monkeypatch: pytest.MonkeyPatch) -> None:
    operations = Continuations()
    adapter = AmpRuntimeAdapter(
        AmpRuntimeConfig("henriquebastos/petrus"),
        AmpContinuationCodec(operations),
        Turns(),
    )
    monkeypatch.setattr(amp_module, "_resolve_amp_cli", lambda: ("/qualified/amp",))

    def absent(name: str) -> str:
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(amp_module.importlib.metadata, "version", absent)
    result = adapter.probe()

    assert result.disposition is ProbeDisposition.NOT_INSTALLED
    assert result.issues[0].code == "sdk-not-installed"


def test_new_turn_uses_only_orb_project_policy_and_settles_one_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    current = rig(monkeypatch, successful_events(text="safe\x1b[31m result\x1b[0m\x00"))
    requested = invocation()
    operation = current.adapter.start(requested)
    result = operation.wait(2)

    assert result.outcome is TurnOutcome.COMPLETED
    assert result.accepted_appends == 1 and result.termination_code == "turn-completed"
    assert result.output_reference == "amp-turn-operation-1"
    assert result.continuation_reference == "amp-continuation-operation-1"
    assert current.calls == [
        (
            PROMPT_CANARY,
            {
                "executor": "orb",
                "project": "henriquebastos/petrus",
                "mode": "medium",
                "visibility": "private",
                "no_archive_after_execute": False,
            },
        )
    ]
    assert current.turns.values[result.output_reference] == (THREAD_ID, "safe result�")
    assert current.continuations.values[result.continuation_reference].thread_id == THREAD_ID
    assert not hasattr(requested.attachment.binding, "lease_identity")
    settlement = requested.attachment.settle()
    assert settlement.settlement.verified and settlement.archive == b""
    assert operation.close().disposition is RuntimeCleanupDisposition.CLEAN
    with pytest.raises(RuntimeProtocolError, match="operation-closed"):
        operation.wait()


def test_continue_loads_only_exact_amp_thread_and_reuses_provider_placement(monkeypatch: pytest.MonkeyPatch) -> None:
    current = rig(monkeypatch)
    first = current.adapter.start(invocation()).wait(2)
    previous = continuation(first.continuation_reference or "")
    next_attachment = attachment("episode-2")
    second = current.adapter.start(
        invocation(
            "episode-2",
            "turn-2",
            "operation-2",
            attached=next_attachment,
            continuation=previous,
            prompt="second prompt",
        )
    ).wait(2)

    assert second.outcome is TurnOutcome.COMPLETED
    assert current.calls[1][1]["continue_thread"] == THREAD_ID
    assert current.calls[1][1]["executor"] == "orb"
    assert current.continuations.values[second.continuation_reference or ""].thread_id == THREAD_ID


@pytest.mark.parametrize(
    ("events", "code"),
    (
        ((event(type="assistant", session_id=THREAD_ID),), "missing-system-init"),
        ((event(type="system", subtype="init", session_id="not-a-thread"),), "malformed-thread-id"),
        (
            (
                event(type="system", subtype="init", session_id=THREAD_ID),
                event(type="assistant", session_id=OTHER_THREAD_ID),
            ),
            "event-thread-mismatch",
        ),
        ((event(type="system", subtype="init", session_id=THREAD_ID),), "terminal-result-missing"),
        (
            successful_events()
            + (event(type="result", subtype="success", session_id=THREAD_ID, is_error=False, result="again"),),
            "duplicate-terminal",
        ),
    ),
)
def test_malformed_or_incomplete_stream_fails_without_an_append(
    monkeypatch: pytest.MonkeyPatch,
    events: tuple[Event, ...],
    code: str,
) -> None:
    current = rig(monkeypatch, events)
    operation = current.adapter.start(invocation())
    result = operation.wait(2)

    assert result.outcome is TurnOutcome.FAILED
    assert result.accepted_appends == 0 and result.termination_code == code
    assert result.output_reference is None and result.continuation_reference is None
    assert operation.close().disposition is RuntimeCleanupDisposition.UNVERIFIED


def test_provider_error_is_typed_without_retaining_raw_diagnostic(monkeypatch: pytest.MonkeyPatch) -> None:
    events = (
        event(type="system", subtype="init", session_id=THREAD_ID),
        event(
            type="result",
            subtype="error_during_execution",
            session_id=THREAD_ID,
            is_error=True,
            error=ERROR_CANARY,
        ),
    )
    current = rig(monkeypatch, events)
    operation = current.adapter.start(invocation())
    result = operation.wait(2)

    assert result.outcome is TurnOutcome.FAILED and result.termination_code == "provider-failed"
    assert result.accepted_appends == 0 and result.output_reference is None
    assert result.continuation_reference == "amp-continuation-operation-1"
    assert ERROR_CANARY not in repr(result) and ERROR_CANARY not in repr(operation.close())
    assert operation.close().disposition is RuntimeCleanupDisposition.CLEAN


def test_protocol_failure_finalizes_the_sdk_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    finalized = threading.Event()

    async def execute(prompt: str, options):
        try:
            yield event(type="system", subtype="init", session_id=THREAD_ID)
            yield event(type="assistant", session_id=OTHER_THREAD_ID)
        finally:
            finalized.set()

    continuations = Continuations()
    adapter = AmpRuntimeAdapter(
        AmpRuntimeConfig("henriquebastos/petrus"),
        AmpContinuationCodec(continuations),
        Turns(),
        sdk_execute=execute,
        clock=lambda: 1,
    )
    ready_probe(monkeypatch, adapter)
    operation = adapter.start(invocation())

    result = operation.wait(2)
    assert result.termination_code == "event-thread-mismatch"
    assert finalized.wait(2)


def test_cancellation_is_idempotent_but_remote_provider_cleanup_stays_unverified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered = threading.Event()
    stopped = threading.Event()

    async def execute(prompt: str, options):
        yield event(type="system", subtype="init", session_id=THREAD_ID)
        entered.set()
        try:
            await __import__("asyncio").Event().wait()
        finally:
            stopped.set()

    continuations = Continuations()
    adapter = AmpRuntimeAdapter(
        AmpRuntimeConfig("henriquebastos/petrus"),
        AmpContinuationCodec(continuations),
        Turns(),
        sdk_execute=execute,
        clock=lambda: 1,
    )
    ready_probe(monkeypatch, adapter)
    operation = adapter.start(invocation())
    assert entered.wait(2)

    assert operation.cancel("stop") is CancellationDisposition.REQUESTED
    assert operation.cancel("stop") is CancellationDisposition.ALREADY_REQUESTED
    result = operation.wait(2)
    assert stopped.wait(2)
    assert result.outcome is TurnOutcome.CANCELLED and result.accepted_appends == 0
    cleanup = operation.close()
    assert cleanup.disposition is RuntimeCleanupDisposition.UNVERIFIED
    assert cleanup.code == "provider-state-uncertain"


def test_wait_timeout_does_not_change_operation_and_active_close_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    entered = threading.Event()

    async def execute(prompt: str, options):
        yield event(type="system", subtype="init", session_id=THREAD_ID)
        entered.set()
        await __import__("asyncio").Event().wait()

    operations = Continuations()
    adapter = AmpRuntimeAdapter(
        AmpRuntimeConfig("henriquebastos/petrus"),
        AmpContinuationCodec(operations),
        Turns(),
        sdk_execute=execute,
        clock=lambda: 1,
    )
    ready_probe(monkeypatch, adapter)
    operation = adapter.start(invocation())
    assert entered.wait(2)
    with pytest.raises(TimeoutError):
        operation.wait(0.01)
    with pytest.raises(RuntimeProtocolError, match="operation-active"):
        operation.close()
    assert operation.cancel("cleanup") is CancellationDisposition.REQUESTED
    assert operation.wait(2).outcome is TurnOutcome.CANCELLED


def test_operation_identity_is_lookup_first_and_conflicts_fail_before_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = rig(monkeypatch)
    requested = invocation()
    first = current.adapter.start(requested)
    assert current.adapter.start(requested) is first
    assert first.wait(2).outcome is TurnOutcome.COMPLETED
    assert len(current.calls) == 1

    with pytest.raises(RuntimeProtocolError, match="operation-conflict"):
        current.adapter.start(invocation(prompt="different", attached=requested.attachment))
    assert len(current.calls) == 1


def test_wrong_catalog_snapshot_fails_before_sdk_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    current = rig(monkeypatch)
    wrong = CapabilityDescriptor(
        DescriptorIdentity(DescriptorKind.RUNTIME, "amp.lookalike", 1),
        AMP_A1.offers,
        AMP_A1.requires,
    )
    attached = attachment("episode-1", selected=snapshot(runtime=wrong))
    with pytest.raises(RuntimeProtocolError, match="resolution-mismatch"):
        current.adapter.start(invocation(attached=attached))
    assert current.calls == []


def test_amp_defining_module_imports_without_optional_sdk() -> None:
    code = r"""
import importlib.abc
import sys

class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'amp_sdk' or fullname.startswith('amp_sdk.'):
            raise AssertionError('optional Amp SDK imported')
        return None

sys.meta_path.insert(0, Blocker())
from petrus.agenticus.runtime.amp import AmpRuntimeAdapter, AMP_PROGRAM
assert AmpRuntimeAdapter is not None and AMP_PROGRAM is not None
"""
    subprocess.run([sys.executable, "-c", code], check=True)
