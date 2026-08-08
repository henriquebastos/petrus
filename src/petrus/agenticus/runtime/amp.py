"""Exact Amp A1 provider-managed runtime lane.

Amp owns its agent loop, thread service, tools, and Orb placement.  Agenticus
owns only the Episode/Turn lifecycle candidate, logical connection fence,
provider-managed attachment, and opaque Continuation/output custody references.
The optional Amp SDK is loaded only by ``probe`` or an actual operation.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import importlib.metadata
import inspect
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Protocol, runtime_checkable

from petrus.agenticus.attachment.binding import BindingSettlement
from petrus.agenticus.attachment.episode import EpisodeAttachment
from petrus.agenticus.catalog.descriptor import CapabilityDescriptor, DescriptorIdentity, DescriptorKind
from petrus.agenticus.connection.custody import ConnectionStatus, ConnectionView
from petrus.agenticus.program.descriptor import (
    AgentProgramDescriptor,
    ContinuationRequirement,
    ProgramOwnership,
)
from petrus.agenticus.runtime.installation import (
    InstalledComponent,
    ProbeDisposition,
    ProbeIssue,
    RuntimeInstallation,
    RuntimeProbeResult,
)
from petrus.agenticus.runtime.operation import (
    RuntimeCleanupDisposition,
    RuntimeOperation,
    RuntimeOperationCleanup,
    RuntimeProtocolError,
)
from petrus.agenticus.runtime.profiles import AMP_A1
from petrus.agenticus.runtime.result import RuntimeTurnSettlement
from petrus.agenticus.thread.continuation import Continuation, ContinuationDescriptor
from petrus.agenticus.thread.identity import EpisodeId, TurnId
from petrus.agenticus.thread.lifecycle import CancellationDisposition, TurnOutcome

AMP_SDK_VERSION = "0.1.20260729121202"
AMP_CLI_VERSION = "0.0.1785733786-gde6a10"
AMP_SDK_SOURCE = (
    "pypi:amp-sdk==0.1.20260729121202#sha256=83d0f4805ddfa836c690419a88f4fd35f1505e03dd772e0831d802db42ca33d7"
)
AMP_CLI_SOURCE = (
    "npm:@ampcode/cli@0.0.1785733786-gde6a10#sha512="
    "oqErM5EQmPmQ2yzoRk/vbWRvvkcRMDV8IjJniLFCFldTlDzq8KDHq43XBo3ktDqy6bV09aWrkwIo4zs1DrRGrA=="
)

_PROGRAM_ID = DescriptorIdentity(DescriptorKind.PROGRAM, "amp.provider-managed", 1)
_CONTINUATION_ID = DescriptorIdentity(DescriptorKind.CONTINUATION, "amp.native", 1)
_CONNECTION_ID = DescriptorIdentity(DescriptorKind.CONNECTION, "amp.platform-managed", 1)
_HANDS_ID = DescriptorIdentity(DescriptorKind.HANDS, "amp.provider-managed", 1)
_TERRITORY_ID = DescriptorIdentity(DescriptorKind.TERRITORY, "amp.provider-managed", 1)

AMP_CONTINUATION_DESCRIPTOR = ContinuationDescriptor(_CONTINUATION_ID, _PROGRAM_ID)
AMP_PROGRAM = AgentProgramDescriptor(
    identity=_PROGRAM_ID,
    ownership=ProgramOwnership.PROVIDER,
    accepted_continuations=(ContinuationRequirement(_CONTINUATION_ID, _PROGRAM_ID),),
    produced_continuation=_CONTINUATION_ID,
    owns_steering=False,
    owns_evaluation=False,
)

# Concrete descriptors make the A1 composition resolvable without teaching the
# static profile table about provider SDKs or installation authority.
AMP_PROGRAM_CAPABILITIES = CapabilityDescriptor(_PROGRAM_ID, frozenset({"program.provider-owned"}))
AMP_CONTINUATION_CAPABILITIES = CapabilityDescriptor(
    _CONTINUATION_ID,
    frozenset({"continuation.amp-native"}),
)
AMP_CONNECTION_CAPABILITIES = CapabilityDescriptor(_CONNECTION_ID, frozenset({"connection.amp"}))
AMP_PROVIDER_MANAGED_HANDS = CapabilityDescriptor(_HANDS_ID, frozenset({"hands.provider-managed"}))
AMP_PROVIDER_MANAGED_TERRITORY = CapabilityDescriptor(_TERRITORY_ID, frozenset())

_MAX_OPERATION_ID_BYTES = 256
_MAX_PROJECT_BYTES = 512
_MAX_PROMPT_BYTES = 64 * 1024
_MAX_REFERENCE_BYTES = 512
_THREAD_ID = re.compile(r"T-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+")
_ANSI_ESCAPE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")


def _bounded_text(value: object, name: str, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value.encode()) > maximum
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError(f"{name} must be bounded non-empty text")
    return value


def _operation_id(value: object) -> str:
    return _bounded_text(value, "Amp operation identity", _MAX_OPERATION_ID_BYTES)


def _thread_id(value: object) -> str:
    value = _bounded_text(value, "Amp thread identity", 128)
    if _THREAD_ID.fullmatch(value) is None:
        raise ValueError("Amp thread identity must be a T-prefixed provider thread ID")
    return value


def _opaque_reference(value: object, name: str) -> str:
    return _bounded_text(value, name, _MAX_REFERENCE_BYTES)


def _positive_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive finite number")
    return float(value)


@dataclass(frozen=True, order=True)
class AmpContinuationPayloadV1:
    """The provider thread identity behind one Amp-native Continuation."""

    thread_id: str
    schema_version: int = field(default=1, init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "thread_id", _thread_id(self.thread_id))

    def to_data(self) -> dict[str, object]:
        return {"schema_version": self.schema_version, "thread_id": self.thread_id}

    @classmethod
    def from_data(cls, data: object) -> AmpContinuationPayloadV1:
        if not isinstance(data, dict) or set(data) != {"schema_version", "thread_id"}:
            raise ValueError("Amp Continuation payload requires exact versioned fields")
        values: dict[str, object] = {str(key): value for key, value in data.items()}
        if values["schema_version"] != 1 or type(values["schema_version"]) is not int:
            raise ValueError("Amp Continuation schema_version must be integer 1")
        return cls(_thread_id(values["thread_id"]))


@runtime_checkable
class AmpContinuationOperations(Protocol):
    """Installation-owned immutable custody for Amp Continuation payloads."""

    def store(self, operation_id: str, payload: AmpContinuationPayloadV1) -> str: ...

    def load(self, state_reference: str) -> AmpContinuationPayloadV1: ...


@runtime_checkable
class AmpTurnOperations(Protocol):
    """Immutable custody for one complete accepted Amp runtime Turn batch."""

    def store_turn(self, operation_id: str, thread_id: str, final_text: str) -> str: ...


class AmpContinuationCodec:
    """Resolve only exact Amp-native references through their owning custody."""

    descriptor = AMP_CONTINUATION_DESCRIPTOR

    def __init__(self, operations: AmpContinuationOperations) -> None:
        if not isinstance(operations, AmpContinuationOperations):
            raise TypeError("Amp Continuation codec requires AmpContinuationOperations")
        self._operations = operations

    def store(self, operation_id: str, payload: AmpContinuationPayloadV1) -> str:
        if not isinstance(payload, AmpContinuationPayloadV1):
            raise TypeError("Amp Continuation store requires AmpContinuationPayloadV1")
        reference = self._operations.store(_operation_id(operation_id), payload)
        return _opaque_reference(reference, "Amp Continuation state reference")

    def load(self, continuation: Continuation, /) -> AmpContinuationPayloadV1:
        if not isinstance(continuation, Continuation):
            raise TypeError("Amp Continuation codec requires a Continuation")
        if continuation.descriptor != self.descriptor:
            raise ValueError("Amp Continuation descriptor does not match the Amp runtime")
        payload = self._operations.load(continuation.state_reference)
        if not isinstance(payload, AmpContinuationPayloadV1):
            raise TypeError("Amp Continuation custody returned a foreign payload")
        return payload


@dataclass(frozen=True)
class AmpRuntimeConfig:
    """One exact qualified A1 installation and provider execution policy."""

    project: str
    mode: str = "medium"
    visibility: str = "private"
    no_archive_after_execute: bool = False
    sdk_version: str = AMP_SDK_VERSION
    cli_version: str = AMP_CLI_VERSION
    max_events: int = 10_000
    max_event_bytes: int = 1_000_000
    max_total_event_bytes: int = 4_000_000
    max_final_text_bytes: int = 1_000_000
    cancellation_grace: float = 10.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "project", _bounded_text(self.project, "Amp project", _MAX_PROJECT_BYTES))
        if self.mode not in {"low", "medium", "high", "ultra"}:
            raise ValueError("Amp A1 mode must be one exact built-in mode")
        if self.visibility not in {"private", "unlisted", "workspace", "group"}:
            raise ValueError("Amp A1 visibility is not supported")
        if type(self.no_archive_after_execute) is not bool:
            raise TypeError("Amp archive policy must be a boolean")
        if self.sdk_version != AMP_SDK_VERSION or self.cli_version != AMP_CLI_VERSION:
            raise ValueError("Amp A1 requires the exact qualified SDK and CLI pair")
        for value, name in (
            (self.max_events, "max_events"),
            (self.max_event_bytes, "max_event_bytes"),
            (self.max_total_event_bytes, "max_total_event_bytes"),
            (self.max_final_text_bytes, "max_final_text_bytes"),
        ):
            if type(value) is not int or value <= 0:
                raise ValueError(f"Amp {name} must be a positive integer")
        _positive_number(self.cancellation_grace, "Amp cancellation grace")


@dataclass(frozen=True)
class AmpRuntimeInvocation:
    """One provider-managed Amp Turn request with no model-provider authority."""

    operation_id: str
    episode_id: EpisodeId
    turn_id: TurnId
    prompt: str = field(repr=False)
    connection: ConnectionView
    attachment: EpisodeAttachment = field(repr=False)
    continuation: Continuation | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "operation_id", _operation_id(self.operation_id))
        if not isinstance(self.episode_id, EpisodeId) or not isinstance(self.turn_id, TurnId):
            raise TypeError("Amp invocation requires exact EpisodeId and TurnId values")
        if not isinstance(self.prompt, str) or not self.prompt or len(self.prompt.encode()) > _MAX_PROMPT_BYTES:
            raise ValueError("Amp prompt must be bounded non-empty text")
        if not isinstance(self.connection, ConnectionView):
            raise TypeError("Amp invocation connection must be a ConnectionView")
        if self.connection.status is not ConnectionStatus.READY:
            raise ValueError("Amp platform-managed connection must be ready")
        if self.connection.identity.provider != "amp" or self.connection.identity.profile != "platform-managed":
            raise ValueError("Amp invocation requires the platform-managed Amp connection profile")
        if not isinstance(self.attachment, EpisodeAttachment):
            raise TypeError("Amp invocation attachment must be EpisodeAttachment")
        if self.attachment.episode_id != self.episode_id:
            raise ValueError("Amp invocation Episode and attachment must match")
        if self.continuation is not None and not isinstance(self.continuation, Continuation):
            raise TypeError("Amp invocation continuation must be Continuation or None")


SdkExecute = Callable[[str, Mapping[str, object]], AsyncIterator[object]]


def _official_execute(prompt: str, options: Mapping[str, object]) -> AsyncIterator[object]:
    sdk = importlib.import_module("amp_sdk")
    amp_options = getattr(sdk, "AmpOptions")(**dict(options))
    execute = getattr(sdk, "execute")
    return execute(prompt, amp_options)


def _event_value(event: object, name: str, default: object = None) -> object:
    if isinstance(event, Mapping):
        return event.get(name, default)
    return getattr(event, name, default)


def _event_size(event: object) -> int:
    serializer = getattr(event, "model_dump_json", None)
    if callable(serializer):
        value = serializer()
        if not isinstance(value, str):
            raise RuntimeProtocolError("malformed-event")
        return len(value.encode())
    size = getattr(event, "encoded_size", None)
    if type(size) is not int or size < 0:
        raise RuntimeProtocolError("malformed-event")
    return size


def _safe_final_text(value: object, maximum: int) -> str:
    if not isinstance(value, str):
        raise RuntimeProtocolError("malformed-result")
    sanitized = _ANSI_ESCAPE.sub("", value)
    sanitized = "".join(
        character if character in "\n\r\t" or 32 <= ord(character) != 127 else "�" for character in sanitized
    )
    if len(sanitized.encode()) > maximum:
        raise RuntimeProtocolError("output-overflow")
    return sanitized


def _resolve_amp_cli() -> tuple[str, ...] | None:
    """Mirror the SDK's higher-priority CLI discovery without importing it."""

    explicit = os.environ.get("AMP_CLI_PATH")
    if explicit and os.path.isfile(explicit):
        return ("node", explicit) if explicit.endswith(".js") else (explicit,)
    home = os.path.expanduser("~")
    amp_home = os.environ.get("AMP_HOME") or os.path.join(home, ".amp")
    binary = "amp.exe" if sys.platform == "win32" else "amp"
    for candidate in (
        os.path.join(amp_home, "sdk", "bin", binary),
        os.path.join(amp_home, "bin", binary),
        os.path.join(home, ".local", "bin", binary),
    ):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return (candidate,)
    on_path = shutil.which("amp")
    return None if on_path is None else (on_path,)


def _probe_cli_version(cli: tuple[str, ...]) -> str:
    result = subprocess.run(
        [*cli, "--version"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    raw_version = result.stdout.strip()
    return raw_version.split(maxsplit=1)[0] if raw_version else ""


def _observed_installation(
    runtime: DescriptorIdentity,
    cli_version: str,
    sdk_version: str,
) -> RuntimeInstallation:
    return RuntimeInstallation(
        runtime=runtime,
        adapter_contract_version=1,
        components=(
            InstalledComponent("amp-cli", cli_version or "unparseable", AMP_CLI_SOURCE),
            InstalledComponent("amp-sdk", sdk_version, AMP_SDK_SOURCE),
        ),
        platform=platform.system().lower() or "unknown",
        architecture=platform.machine().lower() or "unknown",
        capabilities=frozenset({"runtime.cancel", "runtime.continue", "runtime.orb", "runtime.provider-managed"}),
    )


def _protocol_ready(cli: tuple[str, ...]) -> bool:
    try:
        result = subprocess.run(
            [*cli, "--help"],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if not all(option in result.stdout for option in ("--orb-execute", "--project", "--stream-json")):
            return False
        sdk = importlib.import_module("amp_sdk")
        amp_options = getattr(sdk, "AmpOptions")
        fields = getattr(amp_options, "model_fields", {})
        execute = getattr(sdk, "execute")
        return {"executor", "project", "continue_thread"}.issubset(fields) and "options" in inspect.signature(
            execute
        ).parameters
    except Exception:
        return False


@dataclass(frozen=True)
class _Candidate:
    outcome: TurnOutcome
    accepted_appends: int
    termination_code: str
    thread_id: str | None
    final_text: str | None = field(default=None, repr=False)
    provider_terminal: bool = False


@dataclass(frozen=True)
class _OperationKey:
    episode_id: str
    turn_id: str
    prompt_digest: str
    connection_id: str
    authority_epoch: int
    attachment_id: str
    attachment_epoch: int
    continuation_thread_id: str | None


class AmpProviderManagedBinding:
    """DS6 binding for one Amp-owned thread/Orb lifecycle, never a Motus lease."""

    binding_kind = "amp-provider-managed"

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._operation: RuntimeOperation | None = None
        self._cancel_reason: str | None = None

    def bind(self, operation: RuntimeOperation) -> None:
        if not isinstance(operation, RuntimeOperation):
            raise TypeError("Amp provider-managed binding requires a RuntimeOperation")
        with self._lock:
            if self._operation is not None and self._operation is not operation:
                raise RuntimeProtocolError("binding-conflict")
            self._operation = operation
            reason = self._cancel_reason
        if reason is not None:
            operation.cancel(reason)

    def cancel(self, reason: str) -> None:
        reason = _bounded_text(reason, "Amp cancellation reason", 256)
        with self._lock:
            if self._cancel_reason is None:
                self._cancel_reason = reason
            operation = self._operation
        if operation is not None:
            operation.cancel(reason)

    def export_archive(self) -> bytes:
        """Amp A1 has no Agenticus-owned workspace to export."""

        return b""

    def settle(self) -> BindingSettlement:
        with self._lock:
            operation = self._operation
        if operation is None:
            return BindingSettlement(self.binding_kind, "not-created", True)
        cleanup = operation.close()
        if not cleanup.verified:
            return BindingSettlement(self.binding_kind, "unverified", False)
        return BindingSettlement(self.binding_kind, "client-closed", True)


class _AmpRuntimeOperation:
    def __init__(
        self,
        invocation: AmpRuntimeInvocation,
        key: _OperationKey,
        config: AmpRuntimeConfig,
        continuation_codec: AmpContinuationCodec,
        turns: AmpTurnOperations,
        execute: SdkExecute,
        continuation_thread_id: str | None,
        *,
        clock: Callable[[], float],
    ) -> None:
        self._invocation = invocation
        self.key = key
        self._config = config
        self._codec = continuation_codec
        self._turns = turns
        self._execute = execute
        self._continuation_thread_id = continuation_thread_id
        self._clock = clock
        self._condition = threading.Condition(threading.RLock())
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task[RuntimeTurnSettlement] | None = None
        self._result: RuntimeTurnSettlement | None = None
        self._cleanup: RuntimeOperationCleanup | None = None
        self._cancel_requested = False
        self._sdk_started = False
        self._provider_terminal = False

    @property
    def operation_id(self) -> str:
        return self._invocation.operation_id

    def start(self) -> None:
        with self._condition:
            if self._thread is not None:
                return
            self._thread = threading.Thread(
                target=self._run_thread,
                name=f"amp-runtime-{sha256(self.operation_id.encode()).hexdigest()[:12]}",
                daemon=True,
            )
            self._thread.start()

    def wait(self, timeout: float | None = None) -> RuntimeTurnSettlement:
        if timeout is not None:
            timeout = _positive_number(timeout, "Amp operation wait timeout")
        with self._condition:
            if self._cleanup is not None:
                raise RuntimeProtocolError("operation-closed")
            if self._result is None:
                self._condition.wait_for(lambda: self._result is not None, timeout)
            if self._result is None:
                raise TimeoutError("Amp runtime operation has not settled")
            return self._result

    def cancel(self, reason: str) -> CancellationDisposition:
        _bounded_text(reason, "Amp cancellation reason", 256)
        with self._condition:
            if self._result is not None:
                return CancellationDisposition.TOO_LATE
            if self._cancel_requested:
                return CancellationDisposition.ALREADY_REQUESTED
            self._cancel_requested = True
            loop, task = self._loop, self._task
        if loop is not None and task is not None:
            try:
                loop.call_soon_threadsafe(task.cancel)
            except RuntimeError:
                # The worker closes its private loop immediately before it
                # publishes settlement under the condition.
                pass
        return CancellationDisposition.REQUESTED

    def close(self) -> RuntimeOperationCleanup:
        with self._condition:
            if self._cleanup is not None:
                return self._cleanup
            if self._result is None and not self._cancel_requested:
                raise RuntimeProtocolError("operation-active")
            worker = self._thread
        if worker is not None and worker is not threading.current_thread():
            worker.join(self._config.cancellation_grace)
        with self._condition:
            worker_absent = worker is None or not worker.is_alive()
            if not worker_absent:
                disposition = RuntimeCleanupDisposition.UNVERIFIED
                code = "client-cleanup-uncertain"
            elif self._provider_terminal:
                disposition = RuntimeCleanupDisposition.CLEAN
                code = "client-closed"
            elif not self._sdk_started:
                disposition = RuntimeCleanupDisposition.NOT_CREATED
                code = "client-not-created"
            else:
                # Killing the local SDK/CLI client cannot prove that remote Amp
                # work stopped, archived, or left no resumable provider state.
                disposition = RuntimeCleanupDisposition.UNVERIFIED
                code = "provider-state-uncertain"
            self._cleanup = RuntimeOperationCleanup(self.operation_id, disposition, code)
            return self._cleanup

    def _run_thread(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        task = loop.create_task(self._run())
        with self._condition:
            self._loop = loop
            self._task = task
            cancel = self._cancel_requested
        if cancel:
            task.cancel()
        try:
            result = loop.run_until_complete(task)
        except asyncio.CancelledError:
            result = self._settlement(TurnOutcome.CANCELLED, 0, "cancelled")
        finally:
            pending = asyncio.all_tasks(loop)
            for item in pending:
                item.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()
            with self._condition:
                self._loop = None
                self._task = None
        with self._condition:
            self._result = result
            self._condition.notify_all()

    async def _run(self) -> RuntimeTurnSettlement:
        try:
            remaining = self._invocation.attachment.deadline - self._clock()
            if remaining <= 0:
                return self._settlement(TurnOutcome.FAILED, 0, "deadline-exceeded")
            async with asyncio.timeout(remaining):
                candidate = await self._consume()
            self._provider_terminal = candidate.provider_terminal
            return self._publish(candidate)
        except TimeoutError:
            return self._settlement(TurnOutcome.FAILED, 0, "deadline-exceeded")
        except asyncio.CancelledError:
            return self._settlement(TurnOutcome.CANCELLED, 0, "cancelled")
        except RuntimeProtocolError as error:
            return self._settlement(TurnOutcome.FAILED, 0, error.code)
        except Exception:
            return self._settlement(TurnOutcome.FAILED, 0, "client-failed")

    async def _consume(self) -> _Candidate:
        options = self._execution_options()
        self._sdk_started = True
        stream = self._execute(self._invocation.prompt, options)
        try:
            return await self._read_stream(stream)
        except BaseException:
            # The pinned SDK kills/reaps its local CLI when CancelledError is
            # injected into its generator. A plain aclose/GeneratorExit does
            # not enter that cleanup branch.
            athrow = getattr(stream, "athrow", None)
            if callable(athrow):
                with contextlib.suppress(BaseException):
                    await athrow(asyncio.CancelledError())
            raise
        finally:
            aclose = getattr(stream, "aclose", None)
            if callable(aclose):
                with contextlib.suppress(BaseException):
                    await aclose()

    async def _read_stream(self, stream: AsyncIterator[object]) -> _Candidate:
        thread_id: str | None = None
        terminal: _Candidate | None = None
        event_count = 0
        total_bytes = 0
        async for event in stream:
            event_count += 1
            if event_count > self._config.max_events:
                raise RuntimeProtocolError("event-count-overflow")
            event_bytes = _event_size(event)
            if event_bytes > self._config.max_event_bytes:
                raise RuntimeProtocolError("event-overflow")
            total_bytes += event_bytes
            if total_bytes > self._config.max_total_event_bytes:
                raise RuntimeProtocolError("event-total-overflow")
            if terminal is not None:
                raise RuntimeProtocolError("duplicate-terminal")
            if event_count == 1:
                thread_id = self._admit_initial(event)
                continue
            terminal = self._admit_later(event, thread_id)
        if terminal is None:
            raise RuntimeProtocolError("terminal-result-missing")
        return terminal

    def _execution_options(self) -> dict[str, object]:
        options: dict[str, object] = {
            "executor": "orb",
            "project": self._config.project,
            "mode": self._config.mode,
            "visibility": self._config.visibility,
            "no_archive_after_execute": self._config.no_archive_after_execute,
        }
        if self._continuation_thread_id is not None:
            options["continue_thread"] = self._continuation_thread_id
        return options

    def _admit_initial(self, event: object) -> str:
        if _event_value(event, "type") != "system" or _event_value(event, "subtype") != "init":
            raise RuntimeProtocolError("missing-system-init")
        try:
            thread_id = _thread_id(_event_value(event, "session_id"))
        except TypeError, ValueError:
            raise RuntimeProtocolError("malformed-thread-id") from None
        if self._continuation_thread_id is not None and thread_id != self._continuation_thread_id:
            raise RuntimeProtocolError("continuation-thread-mismatch")
        return thread_id

    def _admit_later(self, event: object, thread_id: str | None) -> _Candidate | None:
        if thread_id is None:
            raise RuntimeProtocolError("missing-system-init")
        if _event_value(event, "session_id") != thread_id:
            raise RuntimeProtocolError("event-thread-mismatch")
        event_type = _event_value(event, "type")
        if event_type in {"assistant", "user"}:
            return None
        if event_type != "result":
            raise RuntimeProtocolError("unknown-event")
        return self._admit_terminal(event, thread_id)

    def _admit_terminal(self, event: object, thread_id: str) -> _Candidate:
        is_error = _event_value(event, "is_error")
        subtype = _event_value(event, "subtype")
        if is_error is False and subtype == "success":
            return _Candidate(
                TurnOutcome.COMPLETED,
                1,
                "turn-completed",
                thread_id,
                _safe_final_text(_event_value(event, "result"), self._config.max_final_text_bytes),
                True,
            )
        if is_error is True and subtype in {"error_during_execution", "error_max_turns"}:
            code = "provider-max-turns" if subtype == "error_max_turns" else "provider-failed"
            return _Candidate(TurnOutcome.FAILED, 0, code, thread_id, provider_terminal=True)
        raise RuntimeProtocolError("malformed-terminal")

    def _publish(self, candidate: _Candidate) -> RuntimeTurnSettlement:
        continuation_reference = None
        if candidate.thread_id is not None:
            continuation_reference = self._codec.store(
                self.operation_id,
                AmpContinuationPayloadV1(candidate.thread_id),
            )
        output_reference = None
        if candidate.final_text is not None:
            output_reference = _opaque_reference(
                self._turns.store_turn(self.operation_id, candidate.thread_id or "", candidate.final_text),
                "Amp Turn output reference",
            )
        return self._settlement(
            candidate.outcome,
            candidate.accepted_appends,
            candidate.termination_code,
            output_reference,
            continuation_reference,
        )

    def _settlement(
        self,
        outcome: TurnOutcome,
        appends: int,
        code: str,
        output_reference: str | None = None,
        continuation_reference: str | None = None,
    ) -> RuntimeTurnSettlement:
        return RuntimeTurnSettlement(
            self._invocation.episode_id,
            self._invocation.turn_id,
            outcome,
            appends,
            code,
            output_reference,
            continuation_reference,
        )


class AmpRuntimeAdapter:
    """One concrete adapter for the exact Amp A1 Orb-backed profile."""

    descriptor = AMP_A1
    program = AMP_PROGRAM
    continuation_descriptor = AMP_CONTINUATION_DESCRIPTOR

    def __init__(
        self,
        config: AmpRuntimeConfig,
        continuation_codec: AmpContinuationCodec,
        turns: AmpTurnOperations,
        *,
        sdk_execute: SdkExecute = _official_execute,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(config, AmpRuntimeConfig):
            raise TypeError("Amp runtime adapter requires AmpRuntimeConfig")
        if not isinstance(continuation_codec, AmpContinuationCodec):
            raise TypeError("Amp runtime adapter requires AmpContinuationCodec")
        if not isinstance(turns, AmpTurnOperations):
            raise TypeError("Amp runtime adapter requires AmpTurnOperations")
        self._config = config
        self._codec = continuation_codec
        self._turns = turns
        self._sdk_execute = sdk_execute
        self._clock = clock
        self._installation: RuntimeInstallation | None = None
        self._operations: dict[str, _AmpRuntimeOperation] = {}
        self._lock = threading.RLock()

    def __repr__(self) -> str:
        ready = self._installation is not None
        return f"AmpRuntimeAdapter(project={self._config.project!r}, mode={self._config.mode!r}, ready={ready!r})"

    def probe(self) -> RuntimeProbeResult:
        """Probe the exact SDK/CLI pair without model use or connection materialization."""

        cli = _resolve_amp_cli()
        if cli is None:
            return self._record_probe(
                RuntimeProbeResult(
                    self.descriptor.identity,
                    ProbeDisposition.NOT_INSTALLED,
                    issues=(ProbeIssue("client-not-installed", "amp-cli"),),
                )
            )
        try:
            sdk_version = importlib.metadata.version("amp-sdk")
        except importlib.metadata.PackageNotFoundError:
            return self._record_probe(
                RuntimeProbeResult(
                    self.descriptor.identity,
                    ProbeDisposition.NOT_INSTALLED,
                    issues=(ProbeIssue("sdk-not-installed", "amp-sdk"),),
                )
            )
        try:
            cli_version = _probe_cli_version(cli)
        except OSError, subprocess.SubprocessError:
            return self._record_probe(
                RuntimeProbeResult(
                    self.descriptor.identity,
                    ProbeDisposition.UNAVAILABLE,
                    issues=(ProbeIssue("client-unavailable", "amp-cli"),),
                )
            )
        installation = _observed_installation(self.descriptor.identity, cli_version, sdk_version)
        issues = []
        if cli_version != self._config.cli_version:
            issues.append(ProbeIssue("version-mismatch", "amp-cli"))
        if sdk_version != self._config.sdk_version:
            issues.append(ProbeIssue("version-mismatch", "amp-sdk"))
        if issues:
            return self._record_probe(
                RuntimeProbeResult(
                    self.descriptor.identity,
                    ProbeDisposition.INCOMPATIBLE,
                    installation,
                    tuple(issues),
                )
            )
        if not _protocol_ready(cli):
            return self._record_probe(
                RuntimeProbeResult(
                    self.descriptor.identity,
                    ProbeDisposition.UNAVAILABLE,
                    installation,
                    (ProbeIssue("protocol-unavailable", "amp-sdk"),),
                )
            )
        return self._record_probe(RuntimeProbeResult(self.descriptor.identity, ProbeDisposition.READY, installation))

    def start(self, invocation: AmpRuntimeInvocation) -> RuntimeOperation:
        if not isinstance(invocation, AmpRuntimeInvocation):
            raise TypeError("Amp runtime start requires AmpRuntimeInvocation")
        if self._installation is None:
            raise RuntimeProtocolError("runtime-not-ready")
        self._validate_snapshot(invocation.attachment)
        binding = invocation.attachment.binding
        if not isinstance(binding, AmpProviderManagedBinding):
            raise RuntimeProtocolError("attachment-binding-mismatch")
        continuation_thread_id = None
        if invocation.continuation is not None:
            continuation_thread_id = self._codec.load(invocation.continuation).thread_id
        coordinates = invocation.attachment.coordinates()
        key = _OperationKey(
            invocation.episode_id.value,
            invocation.turn_id.value,
            sha256(invocation.prompt.encode()).hexdigest(),
            invocation.connection.identity.connection_id,
            invocation.connection.authority_epoch,
            coordinates.attachment_id,
            coordinates.attachment_epoch,
            continuation_thread_id,
        )
        with self._lock:
            existing = self._operations.get(invocation.operation_id)
            if existing is not None:
                if existing.key != key:
                    raise RuntimeProtocolError("operation-conflict")
                binding.bind(existing)
                return existing
            operation = _AmpRuntimeOperation(
                invocation,
                key,
                self._config,
                self._codec,
                self._turns,
                self._sdk_execute,
                continuation_thread_id,
                clock=self._clock,
            )
            self._operations[invocation.operation_id] = operation
        try:
            binding.bind(operation)
            operation.start()
        except Exception:
            with self._lock:
                self._operations.pop(invocation.operation_id, None)
            raise
        return operation

    def _record_probe(self, result: RuntimeProbeResult) -> RuntimeProbeResult:
        self._installation = result.installation if result.disposition is ProbeDisposition.READY else None
        return result

    @staticmethod
    def _validate_snapshot(attachment: EpisodeAttachment) -> None:
        expected = {
            DescriptorKind.RUNTIME: AMP_A1.identity,
            DescriptorKind.CONNECTION: AMP_CONNECTION_CAPABILITIES.identity,
            DescriptorKind.PROGRAM: AMP_PROGRAM_CAPABILITIES.identity,
            DescriptorKind.HANDS: AMP_PROVIDER_MANAGED_HANDS.identity,
            DescriptorKind.TERRITORY: AMP_PROVIDER_MANAGED_TERRITORY.identity,
            DescriptorKind.CONTINUATION: AMP_CONTINUATION_CAPABILITIES.identity,
        }
        for kind, identity in expected.items():
            descriptor = attachment.snapshot.descriptor(kind)
            if descriptor is None or descriptor.identity != identity:
                raise RuntimeProtocolError("resolution-mismatch")
        effect = attachment.snapshot.descriptor(DescriptorKind.EFFECT)
        if effect is None or "effect.host-fenced" not in effect.offers:
            raise RuntimeProtocolError("resolution-mismatch")


__all__ = [
    "AMP_CLI_VERSION",
    "AMP_CONNECTION_CAPABILITIES",
    "AMP_CONTINUATION_CAPABILITIES",
    "AMP_CONTINUATION_DESCRIPTOR",
    "AMP_PROGRAM",
    "AMP_PROGRAM_CAPABILITIES",
    "AMP_PROVIDER_MANAGED_HANDS",
    "AMP_PROVIDER_MANAGED_TERRITORY",
    "AMP_SDK_VERSION",
    "AmpContinuationCodec",
    "AmpContinuationOperations",
    "AmpContinuationPayloadV1",
    "AmpProviderManagedBinding",
    "AmpRuntimeAdapter",
    "AmpRuntimeConfig",
    "AmpRuntimeInvocation",
    "AmpTurnOperations",
]
